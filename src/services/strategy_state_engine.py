# -*- coding: utf-8 -*-
"""
Deterministic individual-stock strategy state engine (pure policy core).

Motivation (Phase 27 audit, see
openspec/changes/phase27-strategy-inertia/worklogs/PHASE_27_INDIVIDUAL_STOCK_STRATEGY_INERTIA_AUDIT.md):
production reports exhibited structural LLM inertia — sentiment tracking the
sign of the daily move, identical inputs flipping between 觀望/賣出 across
re-runs, buy zones that are literally the current price rationalized by the
nearest short MA, re-entry bars that fall with the falling MAs, and the
"wait for pullback, then turn bearish when the pullback arrives" contradiction
(2454 2026-07-07 → 07-09, live production instance).

This module began as the isolated Phase 27.1 slice and now owns
strategy state, actionability, operation advice, decision type, buy zone,
invalidation level, and transition rule — deterministically.

Hard boundaries:
- Production reaches this module only through ``strategy_state_orchestrator``;
  the policy core remains unaware of pipeline, persistence, and UI concerns.
- No database access, no ORM, no provider calls, no LLM calls, no environment
  reads, no filesystem access, no wall-clock reads — every timestamp comes
  from the caller-supplied ``as_of``/previous-snapshot fields.
- Same input + same previous snapshot must produce a byte-equivalent logical
  output (pure function, zero randomness).

Phase 27.3R semantics:
- confirmed price/support breaks are temporary ``REDUCE_RISK`` states;
- ``INVALIDATED`` is terminal and requires deterministic thesis evidence;
- two consecutive market observations reclaiming the breached level return
  to ``WATCHLIST`` without reactivating the old buy zone.

Explicitly forbidden inputs (the whole point is to break the narrative loop):
LLM support/resistance claims, LLM sentiment score, LLM trend prediction,
LLM operation advice, LLM-generated buy prices, free-form prose, news text,
raw valuation-river series, future-return labels.

Forbidden outputs (same contract as Phase 26): target_price, fair_value,
recommendation, buy_signal, sell_signal are never emitted.

Insufficient-data policy (documented for Test 9):
- ``close`` missing, or ``data_quality_status`` in {"missing", "fetch_failed"}
  → ``UNSUPPORTED`` with ``RULE_INSUFFICIENT_DATA`` (cannot even observe
  honestly).
- ``close`` present but no deterministic zone basis (no support levels, no
  MA20/MA60) → ``WATCHLIST`` with limitation code ``no_deterministic_zone_basis``
  (we can observe, but must not fabricate an actionable zone).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Tuple

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class StrategyState(str, Enum):
    WATCHLIST = "WATCHLIST"
    WAIT_FOR_PULLBACK = "WAIT_FOR_PULLBACK"
    ACCUMULATE_ZONE = "ACCUMULATE_ZONE"
    DO_NOT_CHASE = "DO_NOT_CHASE"
    HOLD_ONLY = "HOLD_ONLY"
    REDUCE_RISK = "REDUCE_RISK"
    INVALIDATED = "INVALIDATED"
    UNSUPPORTED = "UNSUPPORTED"


# ---------------------------------------------------------------------------
# Stable transition rule IDs
# ---------------------------------------------------------------------------

RULE_UNSUPPORTED_INSTRUMENT = "RULE_UNSUPPORTED_INSTRUMENT"
RULE_INSUFFICIENT_DATA = "RULE_INSUFFICIENT_DATA"
RULE_INITIAL_WATCHLIST = "RULE_INITIAL_WATCHLIST"
RULE_VALID_BUY_ZONE_ENTERED = "RULE_VALID_BUY_ZONE_ENTERED"
RULE_WAIT_FOR_PULLBACK = "RULE_WAIT_FOR_PULLBACK"
RULE_RISK_REWARD_OVEREXTENDED = "RULE_RISK_REWARD_OVEREXTENDED"
RULE_HOLD_EXISTING_ONLY = "RULE_HOLD_EXISTING_ONLY"
RULE_CONFIRMED_SUPPORT_BREAK = "RULE_CONFIRMED_SUPPORT_BREAK"
RULE_SUPPORT_RECLAIM_PENDING = "RULE_SUPPORT_RECLAIM_PENDING"
RULE_CONFIRMED_SUPPORT_RECLAIM = "RULE_CONFIRMED_SUPPORT_RECLAIM"
RULE_THESIS_INVALIDATED = "RULE_THESIS_INVALIDATED"
RULE_TERMINAL_STATE_PERSISTED = "RULE_TERMINAL_STATE_PERSISTED"
RULE_RISK_FLAG_REDUCE = "RULE_RISK_FLAG_REDUCE"
RULE_HYSTERESIS_HOLD = "RULE_HYSTERESIS_HOLD"
RULE_STATE_UNCHANGED = "RULE_STATE_UNCHANGED"

# Rules that bypass hysteresis: risk-off / invalidity must never be delayed
# by the anti-flip window.
CRITICAL_RULES = frozenset({
    RULE_UNSUPPORTED_INSTRUMENT,
    RULE_INSUFFICIENT_DATA,
    RULE_THESIS_INVALIDATED,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_RISK_FLAG_REDUCE,
})

# Zone entry is also hysteresis-exempt: "close enters the prior valid zone and
# no invalidation trigger exists → ACCUMULATE_ZONE" is an unconditional
# contract (the audited 2454 07-07→07-09 contradiction is exactly a delayed/
# denied zone entry). Oscillation is still damped because every SUBSEQUENT
# non-critical flip after the entry remains suppressed by the window.
HYSTERESIS_EXEMPT_RULES = CRITICAL_RULES | {
    RULE_VALID_BUY_ZONE_ENTERED,
    RULE_CONFIRMED_SUPPORT_RECLAIM,
}

# Issue / limitation codes
BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED = "BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED"
SHORT_MA_ONLY_BASIS_REJECTED = "short_ma_only_basis_rejected"
SUPPORT_AND_VALUATION_DO_NOT_OVERLAP = "support_and_valuation_do_not_overlap"
RISK_REWARD_BELOW_THRESHOLD = "risk_reward_below_threshold"
NO_DETERMINISTIC_ZONE_BASIS = "no_deterministic_zone_basis"
INVALIDATION_BREACH_PENDING = "invalidation_breach_pending_confirmation"
NO_RESISTANCE_REFERENCE = "no_resistance_reference"

# Zone types
ZONE_VALUATION_AND_TECHNICAL = "VALUATION_AND_TECHNICAL"
ZONE_TECHNICAL_ONLY = "TECHNICAL_ONLY"

# Deterministic risk flags that force REDUCE_RISK (input contract: these are
# rule-computed upstream, never LLM-authored).
REDUCE_RISK_FLAGS = frozenset({
    "confirmed_distribution",
    "leverage_forced_selling",
    "regulatory_halt_risk",
})

_SHORT_MA_BASES = frozenset({"ma5", "ma10"})
_LEVEL_MATCH_REL_TOLERANCE = 1e-6
_LEVEL_MATCH_ABS_TOLERANCE = 1e-8


# ---------------------------------------------------------------------------
# Policy (single immutable home for every threshold — no scattered magic numbers)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrategyPolicy:
    support_tolerance_pct: float = 0.02
    anchor_lint_tolerance_pct: float = 0.01
    minimum_risk_reward: float = 2.0
    hysteresis_days: int = 3
    invalidation_confirmation_days: int = 2
    reclaim_confirmation_days: int = 2


DEFAULT_POLICY = StrategyPolicy()


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrategyStateInput:
    """Deterministic inputs only — every field has a rule-computed source."""

    symbol: str
    market: str
    instrument_type: str
    as_of: date

    close: Optional[float]
    previous_close: Optional[float] = None
    daily_change_pct: Optional[float] = None

    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None

    deterministic_support_levels: Tuple[float, ...] = ()
    deterministic_resistance_levels: Tuple[float, ...] = ()

    multi_period_trend: Optional[str] = None
    volume_ratio: Optional[float] = None
    capital_flow_bias: Optional[str] = None

    valuation_zone: Optional[str] = None
    valuation_band_low: Optional[float] = None
    valuation_band_high: Optional[float] = None

    thesis_status: Optional[str] = None
    deterministic_risk_flags: Tuple[str, ...] = ()

    data_quality_status: str = "available"


@dataclass(frozen=True)
class BuyZone:
    low: float
    high: float
    basis: Tuple[str, ...]
    created_at: date
    revision: int
    zone_type: str

    def to_dict(self) -> dict:
        return {
            "low": self.low,
            "high": self.high,
            "basis": list(self.basis),
            "created_at": self.created_at.isoformat(),
            "revision": self.revision,
            "zone_type": self.zone_type,
        }

    @staticmethod
    def from_dict(d: dict) -> "BuyZone":
        return BuyZone(
            low=float(d["low"]),
            high=float(d["high"]),
            basis=tuple(d.get("basis") or ()),
            created_at=date.fromisoformat(d["created_at"]),
            revision=int(d.get("revision", 0)),
            zone_type=str(d.get("zone_type", ZONE_TECHNICAL_ONLY)),
        )


@dataclass(frozen=True)
class StrategyStateSnapshot:
    schema_version: int

    symbol: str
    market: str
    as_of: date

    state: StrategyState
    previous_state: Optional[StrategyState]

    actionability: str
    operation_advice: str
    decision_type: str

    buy_zone: Optional[BuyZone]
    invalidation_level: Optional[float]

    transition_rule_id: str
    transition_triggered: bool

    state_entered_at: date
    last_transition_at: date
    days_in_state: int
    transition_count_in_window: int
    invalidation_confirm_count: int
    reclaim_confirm_count: int = 0

    reasons: Tuple[str, ...] = ()
    data_limitations: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "market": self.market,
            "as_of": self.as_of.isoformat(),
            "state": self.state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "actionability": self.actionability,
            "operation_advice": self.operation_advice,
            "decision_type": self.decision_type,
            "buy_zone": self.buy_zone.to_dict() if self.buy_zone else None,
            "invalidation_level": self.invalidation_level,
            "transition_rule_id": self.transition_rule_id,
            "transition_triggered": self.transition_triggered,
            "state_entered_at": self.state_entered_at.isoformat(),
            "last_transition_at": self.last_transition_at.isoformat(),
            "days_in_state": self.days_in_state,
            "transition_count_in_window": self.transition_count_in_window,
            "invalidation_confirm_count": self.invalidation_confirm_count,
            "reclaim_confirm_count": self.reclaim_confirm_count,
            "reasons": list(self.reasons),
            "data_limitations": list(self.data_limitations),
        }

    @staticmethod
    def from_dict(d: dict) -> "StrategyStateSnapshot":
        return StrategyStateSnapshot(
            schema_version=int(d["schema_version"]),
            symbol=str(d["symbol"]),
            market=str(d["market"]),
            as_of=date.fromisoformat(d["as_of"]),
            state=StrategyState(d["state"]),
            previous_state=StrategyState(d["previous_state"]) if d.get("previous_state") else None,
            actionability=str(d["actionability"]),
            operation_advice=str(d["operation_advice"]),
            decision_type=str(d["decision_type"]),
            buy_zone=BuyZone.from_dict(d["buy_zone"]) if d.get("buy_zone") else None,
            invalidation_level=(
                float(d["invalidation_level"]) if d.get("invalidation_level") is not None else None
            ),
            transition_rule_id=str(d["transition_rule_id"]),
            transition_triggered=bool(d["transition_triggered"]),
            state_entered_at=date.fromisoformat(d["state_entered_at"]),
            last_transition_at=date.fromisoformat(d["last_transition_at"]),
            days_in_state=int(d["days_in_state"]),
            transition_count_in_window=int(d["transition_count_in_window"]),
            invalidation_confirm_count=int(d["invalidation_confirm_count"]),
            reclaim_confirm_count=int(d.get("reclaim_confirm_count", 0)),
            reasons=tuple(d.get("reasons") or ()),
            data_limitations=tuple(d.get("data_limitations") or ()),
        )


# ---------------------------------------------------------------------------
# Fixed state → action mapping (single central table; never LLM-derived)
# ---------------------------------------------------------------------------

STATE_ACTION_MAP: dict = {
    StrategyState.WATCHLIST: ("WATCH", "觀察", "watch"),
    StrategyState.WAIT_FOR_PULLBACK: ("ACTIONABLE_WAIT", "等待回檔", "wait"),
    StrategyState.ACCUMULATE_ZONE: ("ACTIONABLE_ACCUMULATE", "分批布局", "buy"),
    StrategyState.DO_NOT_CHASE: ("DO_NOT_BUY", "不追價", "avoid"),
    StrategyState.HOLD_ONLY: ("HOLD_ONLY", "僅續抱，不新增部位", "hold"),
    StrategyState.REDUCE_RISK: ("REDUCE", "降低風險曝險", "reduce"),
    StrategyState.INVALIDATED: ("INVALIDATED_NO_TRADE", "論點失效，不執行原買進計畫", "invalidated"),
    StrategyState.UNSUPPORTED: ("NOT_SUPPORTED", "不支援策略狀態", "unsupported"),
}


# ---------------------------------------------------------------------------
# Buy-zone anchor lint
# ---------------------------------------------------------------------------

def lint_buy_zone(
    zone: BuyZone,
    close: float,
    policy: StrategyPolicy = DEFAULT_POLICY,
) -> Optional[str]:
    """Return an issue code when the zone is a disguised current-price anchor.

    Fails when the zone midpoint sits within ±anchor_lint_tolerance_pct of the
    current close AND the basis contains only short-MA anchors (ma5/ma10) with
    no valuation or longer-term support basis — the exact pattern found in
    production (LLY「1216-1220（MA5附近，當前價格區間）」at px=1216.95).
    """
    if close is None or close <= 0:
        return None
    bases = {b.split(":", 1)[0] for b in zone.basis}
    short_ma_only = bool(bases) and bases <= _SHORT_MA_BASES
    if not short_ma_only:
        return None
    midpoint = (zone.low + zone.high) / 2.0
    if abs(midpoint - close) / close <= policy.anchor_lint_tolerance_pct:
        return BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED
    return SHORT_MA_ONLY_BASIS_REJECTED


# ---------------------------------------------------------------------------
# Internal helpers (pure)
# ---------------------------------------------------------------------------

def _round(v: float) -> float:
    return round(v, 4)


def _nearest_support_below(input_data: StrategyStateInput) -> Optional[Tuple[float, str]]:
    """Strongest deterministic support below close, with its basis tag.

    Priority: explicit deterministic support levels, then long MAs (ma60,
    ma20). Short MAs (ma5/ma10) are deliberately NOT acceptable zone bases —
    they are the production anchor-drift vector.
    """
    close = input_data.close
    serialized_mas = tuple(
        value for value in (input_data.ma5, input_data.ma10, input_data.ma20) if value is not None
    )
    candidates = [
        (s, f"support:{_round(s)}")
        for s in input_data.deterministic_support_levels
        if (
            s is not None
            and 0 < s < close
            and not any(
                math.isclose(
                    s,
                    short_ma,
                    rel_tol=_LEVEL_MATCH_REL_TOLERANCE,
                    abs_tol=_LEVEL_MATCH_ABS_TOLERANCE,
                )
                for short_ma in serialized_mas
            )
        )
    ]
    if candidates:
        best = max(candidates, key=lambda item: item[0])
        return best
    for value, tag in ((input_data.ma60, "ma60"), (input_data.ma20, "ma20")):
        if value is not None and 0 < value < close:
            return (value, tag)
    return None


def _nearest_resistance_above(input_data: StrategyStateInput, ref: float) -> Optional[float]:
    ups = [r for r in input_data.deterministic_resistance_levels if r is not None and r > ref]
    return min(ups) if ups else None


def _generate_buy_zone(
    input_data: StrategyStateInput,
    policy: StrategyPolicy,
    reasons: list,
    limitations: list,
) -> Optional[BuyZone]:
    """Deterministic zone: technical support band ∩ valuation band, RR-gated.

    Never derived from previous_close-minus-fixed-discount and never defaulted
    to close ± small pct. An empty intersection or a failing RR yields None —
    honest non-actionability instead of fake precision.
    """
    close = input_data.close
    anchor = _nearest_support_below(input_data)
    if anchor is None:
        # Last-resort short-MA candidate exists only so the lint can reject it
        # explicitly (production pattern evidence C). It never survives. A
        # short MA marginally ABOVE close still counts — that is precisely the
        # "zone = current price" production pattern being rejected.
        for value, tag in ((input_data.ma10, "ma10"), (input_data.ma5, "ma5")):
            if value is not None and 0 < value <= close * (1 + policy.support_tolerance_pct):
                candidate = BuyZone(
                    low=_round(value * (1 - policy.support_tolerance_pct)),
                    high=_round(value * (1 + policy.support_tolerance_pct)),
                    basis=(tag,),
                    created_at=input_data.as_of,
                    revision=0,
                    zone_type=ZONE_TECHNICAL_ONLY,
                )
                issue = lint_buy_zone(candidate, close, policy)
                if issue:
                    reasons.append(issue)
                    return None
                # Unreachable by construction (short-MA-only always lints),
                # kept for safety: refuse anyway.
                reasons.append(SHORT_MA_ONLY_BASIS_REJECTED)
                return None
        limitations.append(NO_DETERMINISTIC_ZONE_BASIS)
        return None

    support, basis_tag = anchor
    tech_low = support * (1 - policy.support_tolerance_pct)
    tech_high = support * (1 + policy.support_tolerance_pct)
    basis = [basis_tag]
    zone_type = ZONE_TECHNICAL_ONLY

    val_low = input_data.valuation_band_low
    val_high = input_data.valuation_band_high
    if val_low is not None or val_high is not None:
        inter_low = max(tech_low, val_low) if val_low is not None else tech_low
        inter_high = min(tech_high, val_high) if val_high is not None else tech_high
        if inter_low > inter_high:
            reasons.append(SUPPORT_AND_VALUATION_DO_NOT_OVERLAP)
            return None
        tech_low, tech_high = inter_low, inter_high
        basis.append("valuation_band")
        zone_type = ZONE_VALUATION_AND_TECHNICAL

    zone = BuyZone(
        low=_round(tech_low),
        high=_round(tech_high),
        basis=tuple(basis),
        created_at=input_data.as_of,
        revision=0,
        zone_type=zone_type,
    )

    issue = lint_buy_zone(zone, close, policy)
    if issue:
        reasons.append(issue)
        return None

    # Risk-reward gate: reward to the nearest deterministic resistance above
    # the zone vs. risk down to the invalidation level.
    invalidation = zone.low * (1 - policy.support_tolerance_pct)
    resistance = _nearest_resistance_above(input_data, zone.high)
    if resistance is None:
        limitations.append(NO_RESISTANCE_REFERENCE)
    else:
        risk = zone.high - invalidation
        reward = resistance - zone.high
        if risk <= 0 or (reward / risk) < policy.minimum_risk_reward:
            reasons.append(RISK_REWARD_BELOW_THRESHOLD)
            return None

    return zone


def _zone_revision_trigger(
    previous_zone: BuyZone,
    input_data: StrategyStateInput,
    policy: StrategyPolicy,
) -> Optional[str]:
    """Deterministic reasons the persisted zone must be revised. MA drift is
    deliberately NOT a trigger — that is the moving-anchor failure mode."""
    val_low = input_data.valuation_band_low
    val_high = input_data.valuation_band_high
    if val_low is not None and previous_zone.high < val_low:
        return "valuation_band_moved_above_zone"
    if val_high is not None and previous_zone.low > val_high:
        return "valuation_band_moved_below_zone"
    return None


def _rr_at_price(input_data: StrategyStateInput, downside_ref: Optional[float]) -> Optional[float]:
    """Risk-reward of buying at the CURRENT price (chase check)."""
    close = input_data.close
    resistance = _nearest_resistance_above(input_data, close)
    if resistance is None:
        # Above every known deterministic resistance: reward reference is
        # exhausted — treat as maximally overextended (RR = 0).
        return 0.0 if input_data.deterministic_resistance_levels else None
    if downside_ref is None or downside_ref >= close:
        return None
    risk = close - downside_ref
    reward = resistance - close
    if risk <= 0:
        return None
    return reward / risk


# ---------------------------------------------------------------------------
# Snapshot assembly helper
# ---------------------------------------------------------------------------

def _make_snapshot(
    input_data: StrategyStateInput,
    previous: Optional[StrategyStateSnapshot],
    state: StrategyState,
    rule_id: str,
    *,
    buy_zone: Optional[BuyZone],
    invalidation_level: Optional[float],
    invalidation_confirm_count: int,
    reasons: Tuple[str, ...],
    limitations: Tuple[str, ...],
    policy: StrategyPolicy,
    reclaim_confirm_count: int = 0,
) -> StrategyStateSnapshot:
    prev_state = previous.state if previous else None
    transitioned = prev_state is not None and state != prev_state
    if previous is None:
        state_entered_at = input_data.as_of
        last_transition_at = input_data.as_of
        window_count = 1 if transitioned else 0
    elif transitioned:
        state_entered_at = input_data.as_of
        last_transition_at = input_data.as_of
        gap = (input_data.as_of - previous.last_transition_at).days
        window_count = 1 if gap >= policy.hysteresis_days else previous.transition_count_in_window + 1
    else:
        state_entered_at = previous.state_entered_at
        last_transition_at = previous.last_transition_at
        window_count = previous.transition_count_in_window

    actionability, advice, decision = STATE_ACTION_MAP[state]
    return StrategyStateSnapshot(
        schema_version=SCHEMA_VERSION,
        symbol=input_data.symbol,
        market=input_data.market,
        as_of=input_data.as_of,
        state=state,
        previous_state=prev_state,
        actionability=actionability,
        operation_advice=advice,
        decision_type=decision,
        buy_zone=buy_zone,
        invalidation_level=_round(invalidation_level) if invalidation_level is not None else None,
        transition_rule_id=rule_id,
        transition_triggered=transitioned,
        state_entered_at=state_entered_at,
        last_transition_at=last_transition_at,
        days_in_state=max(0, (input_data.as_of - state_entered_at).days),
        transition_count_in_window=window_count,
        invalidation_confirm_count=invalidation_confirm_count,
        reclaim_confirm_count=reclaim_confirm_count,
        reasons=reasons,
        data_limitations=limitations,
    )


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def evaluate_strategy_state(
    input_data: StrategyStateInput,
    previous: Optional[StrategyStateSnapshot],
    policy: StrategyPolicy = DEFAULT_POLICY,
) -> StrategyStateSnapshot:
    """Pure deterministic state evaluation. Same (input, previous, policy)
    always yields an identical snapshot."""
    reasons: list = []
    limitations: list = []

    # -- 1. Unsupported instrument ----------------------------------------
    if input_data.instrument_type != "stock":
        return _make_snapshot(
            input_data, previous, StrategyState.UNSUPPORTED, RULE_UNSUPPORTED_INSTRUMENT,
            buy_zone=None, invalidation_level=None, invalidation_confirm_count=0,
            reasons=(f"instrument_type={input_data.instrument_type}",),
            limitations=(), policy=policy,
        )

    # -- 2. Insufficient data ----------------------------------------------
    if input_data.close is None or input_data.data_quality_status in ("missing", "fetch_failed"):
        return _make_snapshot(
            input_data, previous, StrategyState.UNSUPPORTED, RULE_INSUFFICIENT_DATA,
            buy_zone=None, invalidation_level=None, invalidation_confirm_count=0,
            reasons=(), limitations=(f"data_quality={input_data.data_quality_status}",),
            policy=policy,
        )

    # -- 3. Thesis invalidation (critical, bypasses hysteresis) ------------
    if input_data.thesis_status == "invalidated":
        return _make_snapshot(
            input_data, previous, StrategyState.INVALIDATED, RULE_THESIS_INVALIDATED,
            buy_zone=None,
            invalidation_level=previous.invalidation_level if previous else None,
            invalidation_confirm_count=(previous.invalidation_confirm_count if previous else 0),
            reasons=("thesis_status=invalidated",), limitations=(), policy=policy,
        )

    # Terminal invalidation is absorbing until a future deterministic
    # reinstatement contract is explicitly designed. Legacy technical
    # INVALIDATED snapshots are handled by the reclaim path below.
    if (
        previous is not None
        and previous.state == StrategyState.INVALIDATED
        and previous.transition_rule_id != RULE_CONFIRMED_SUPPORT_BREAK
    ):
        return _make_snapshot(
            input_data, previous, StrategyState.INVALIDATED, RULE_TERMINAL_STATE_PERSISTED,
            buy_zone=None, invalidation_level=previous.invalidation_level,
            invalidation_confirm_count=previous.invalidation_confirm_count,
            reclaim_confirm_count=0,
            reasons=("terminal_invalidation_persisted",), limitations=(), policy=policy,
        )

    # -- 4. Deterministic risk flags (critical) -----------------------------
    fired_flags = tuple(f for f in input_data.deterministic_risk_flags if f in REDUCE_RISK_FLAGS)
    if fired_flags:
        return _make_snapshot(
            input_data, previous, StrategyState.REDUCE_RISK, RULE_RISK_FLAG_REDUCE,
            buy_zone=None,
            invalidation_level=previous.invalidation_level if previous else None,
            invalidation_confirm_count=(previous.invalidation_confirm_count if previous else 0),
            reasons=tuple(f"risk_flag:{f}" for f in fired_flags), limitations=(), policy=policy,
        )

    close = float(input_data.close)

    # A technical breakdown is temporary risk control, not terminal thesis
    # failure. Reclaim is counted in consecutive market observations and
    # exits only to WATCHLIST; the old zone is never reactivated.
    technical_risk_state = (
        previous is not None
        and previous.invalidation_level is not None
        and (
            previous.state == StrategyState.REDUCE_RISK
            and previous.transition_rule_id in {
                RULE_CONFIRMED_SUPPORT_BREAK,
                RULE_SUPPORT_RECLAIM_PENDING,
            }
            or previous.state == StrategyState.INVALIDATED
            and previous.transition_rule_id == RULE_CONFIRMED_SUPPORT_BREAK
        )
    )
    if technical_risk_state:
        inv_level = previous.invalidation_level
        if close >= inv_level:
            reclaim_count = previous.reclaim_confirm_count + 1
            if reclaim_count >= policy.reclaim_confirmation_days:
                return _make_snapshot(
                    input_data, previous, StrategyState.WATCHLIST,
                    RULE_CONFIRMED_SUPPORT_RECLAIM,
                    buy_zone=None, invalidation_level=None,
                    invalidation_confirm_count=0, reclaim_confirm_count=0,
                    reasons=(
                        f"close_reclaimed_invalidation_for_{reclaim_count}_days",
                    ),
                    limitations=(), policy=policy,
                )
            return _make_snapshot(
                input_data, previous, StrategyState.REDUCE_RISK,
                RULE_SUPPORT_RECLAIM_PENDING,
                buy_zone=None, invalidation_level=inv_level,
                invalidation_confirm_count=previous.invalidation_confirm_count,
                reclaim_confirm_count=reclaim_count,
                reasons=("invalidation_reclaim_pending_confirmation",),
                limitations=(), policy=policy,
            )
        return _make_snapshot(
            input_data, previous, StrategyState.REDUCE_RISK,
            RULE_CONFIRMED_SUPPORT_BREAK,
            buy_zone=None, invalidation_level=inv_level,
            invalidation_confirm_count=max(
                previous.invalidation_confirm_count,
                policy.invalidation_confirmation_days,
            ),
            reclaim_confirm_count=0,
            reasons=("technical_break_remains_below_invalidation",),
            limitations=(), policy=policy,
        )

    # -- 5. Invalidation-level breach tracking (critical when confirmed) ---
    prev_zone = previous.buy_zone if previous else None
    inv_level = previous.invalidation_level if previous else None
    confirm_count = previous.invalidation_confirm_count if previous else 0
    if inv_level is not None:
        if close < inv_level:
            confirm_count += 1
            if confirm_count >= policy.invalidation_confirmation_days:
                return _make_snapshot(
                    input_data, previous, StrategyState.REDUCE_RISK, RULE_CONFIRMED_SUPPORT_BREAK,
                    buy_zone=None, invalidation_level=inv_level,
                    invalidation_confirm_count=confirm_count,
                    reclaim_confirm_count=0,
                    reasons=(
                        f"close_below_invalidation_for_{confirm_count}_days",
                    ),
                    limitations=(), policy=policy,
                )
            reasons.append(INVALIDATION_BREACH_PENDING)
        else:
            confirm_count = 0

    # -- 6. Buy zone: inherit persisted zone, else generate ----------------
    zone: Optional[BuyZone] = None
    if prev_zone is not None:
        trigger = _zone_revision_trigger(prev_zone, input_data, policy)
        if trigger is None:
            zone = prev_zone  # persisted verbatim — MAs moving is NOT a revision trigger
        else:
            reasons.append(f"zone_revised:{trigger}")
            regenerated = _generate_buy_zone(input_data, policy, reasons, limitations)
            if regenerated is not None:
                zone = BuyZone(
                    low=regenerated.low,
                    high=regenerated.high,
                    basis=regenerated.basis,
                    created_at=input_data.as_of,
                    revision=prev_zone.revision + 1,
                    zone_type=regenerated.zone_type,
                )
    else:
        zone = _generate_buy_zone(input_data, policy, reasons, limitations)

    new_inv_level = zone.low * (1 - policy.support_tolerance_pct) if zone else inv_level

    # -- 7. Proposed state from zone geometry ------------------------------
    if zone is not None and zone.low <= close <= zone.high:
        proposed, rule = StrategyState.ACCUMULATE_ZONE, RULE_VALID_BUY_ZONE_ENTERED
    elif zone is not None and close > zone.high:
        rr = _rr_at_price(input_data, downside_ref=new_inv_level)
        if rr is not None and rr < policy.minimum_risk_reward:
            proposed, rule = StrategyState.DO_NOT_CHASE, RULE_RISK_REWARD_OVEREXTENDED
            reasons.append(f"rr_at_price={_round(rr)}")
        elif previous is not None and previous.state == StrategyState.ACCUMULATE_ZONE:
            proposed, rule = StrategyState.HOLD_ONLY, RULE_HOLD_EXISTING_ONLY
        else:
            proposed, rule = StrategyState.WAIT_FOR_PULLBACK, RULE_WAIT_FOR_PULLBACK
    elif zone is not None:
        # Below the zone with an unconfirmed breach: hold the prior state
        # (pending confirmation) instead of flapping.
        proposed = previous.state if previous else StrategyState.WATCHLIST
        rule = RULE_STATE_UNCHANGED if previous else RULE_INITIAL_WATCHLIST
    else:
        # No valid zone: observe honestly; check chase condition if possible.
        anchor = _nearest_support_below(input_data)
        rr = _rr_at_price(input_data, downside_ref=anchor[0] if anchor else None)
        if rr is not None and rr < policy.minimum_risk_reward:
            proposed, rule = StrategyState.DO_NOT_CHASE, RULE_RISK_REWARD_OVEREXTENDED
            reasons.append(f"rr_at_price={_round(rr)}")
        else:
            proposed = StrategyState.WATCHLIST
            rule = RULE_INITIAL_WATCHLIST if previous is None else (
                RULE_STATE_UNCHANGED if previous.state == StrategyState.WATCHLIST else RULE_INITIAL_WATCHLIST
            )

    # -- 8. Hysteresis: suppress non-critical flips inside the window ------
    if (
        previous is not None
        and proposed != previous.state
        and rule not in HYSTERESIS_EXEMPT_RULES
        and (input_data.as_of - previous.last_transition_at).days < policy.hysteresis_days
    ):
        return _make_snapshot(
            input_data, previous, previous.state, RULE_HYSTERESIS_HOLD,
            buy_zone=zone, invalidation_level=new_inv_level,
            invalidation_confirm_count=confirm_count,
            reasons=tuple(reasons) + (f"suppressed_transition_to={proposed.value}",),
            limitations=tuple(limitations), policy=policy,
        )

    if previous is not None and proposed == previous.state:
        rule = RULE_STATE_UNCHANGED

    return _make_snapshot(
        input_data, previous, proposed, rule,
        buy_zone=zone, invalidation_level=new_inv_level,
        invalidation_confirm_count=confirm_count,
        reasons=tuple(reasons), limitations=tuple(limitations), policy=policy,
    )

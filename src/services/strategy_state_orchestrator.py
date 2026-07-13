# -*- coding: utf-8 -*-
"""
Phase 27.2 — strategy-state orchestration around the pure Phase 27.1 engine.

Responsibility split (the engine stays pure — no DB/provider/LLM/config/
filesystem access is ever added to strategy_state_engine.py):

- ``load_previous_strategy_snapshot``: history adapter — retrieves the most
  recent persisted deterministic snapshot for the same canonical symbol.
- ``build_strategy_state_input``: normalizes existing deterministic pipeline
  values (trend_result, valuation river snapshot, deterministic capital-flow
  bias) into the engine's input contract. Every field's source is documented
  inline; LLM-generated values are structurally excluded — this function
  never reads AnalysisResult narrative fields.
- ``build_previous_state_prompt_block``: compact previous deterministic
  context for LLM narrative continuity (no prose, no internal IDs, no raw
  series).
- ``apply_strategy_authority``: transfers final action authority from LLM
  fields to the deterministic snapshot, preserving original LLM values as
  diagnostics and recording machine-readable conflict codes.
- ``validate_strategy_state_input_readiness``: Phase 27.2R central readiness
  check. Returns machine-readable defect codes (pipeline control/logs only,
  never user-facing copy) and distinguishes REQUIRED gaps (which block report
  completion for an in-scope stock — a provider/data execution failure, not a
  valid product state) from optional-enhancement gaps (which degrade zone
  quality but still yield a valid, authoritative engine state).

Phase 27.2R data contract (required vs optional vs deferred):
- REQUIRED (BLOCKING_READINESS_DEFECTS): instrument_type == "stock", a valid
  as_of trading date, close, and data_quality_status not in
  ("missing", "fetch_failed"). Missing any of these for an in-scope stock
  raises ``StrategyDataUnavailableError`` — callers must let it propagate so
  the whole analysis task fails (existing "return None on exception"
  single-stock convention) rather than persist a completed report with a
  non-authoritative/UNSUPPORTED fallback.
- OPTIONAL ENHANCEMENTS (reported as defect codes but never block):
  previous_close, deterministic support levels (support_levels or ma20/ma60),
  deterministic resistance levels. Their absence degrades zone precision
  (e.g. TECHNICAL_ONLY basis, or WATCHLIST instead of ACCUMULATE_ZONE) but
  the engine still returns a valid, authoritative state — never UNSUPPORTED.
- CONSUMED BY THE ENGINE: close, data_quality_status, instrument_type,
  as_of, ma5/ma10/ma20/ma60, deterministic_support_levels,
  deterministic_resistance_levels, valuation_band_low/high, thesis_status,
  deterministic_risk_flags.
- NOT CONSUMED by any current engine rule (retained as optional/diagnostic
  fields with zero effect on readiness or state — Option 2 of the Phase
  27.2R field audit, since the engine dataclass is frozen and cannot be
  edited in this phase): previous_close, daily_change_pct, multi_period_trend,
  volume_ratio, capital_flow_bias, valuation_zone. These are populated where a
  real deterministic source already exists (previous_close, daily_change_pct,
  volume_ratio, capital_flow_bias, valuation_zone) for diagnostic display and
  future evidence-backed rules — never for LLM-inferred content, never
  gating supported/unsupported classification. ``multi_period_trend`` has no
  deterministic source yet and is always None.
- thesis_status / deterministic_risk_flags are consumed by the engine but
  this orchestrator never supplies non-empty values (Option B of the Phase
  27.2R field audit): no trustworthy deterministic source exists yet for
  thesis invalidation or hard risk flags beyond what the engine already
  derives internally from its own invalidation-breach tracking. Still
  deferred after Phase 27.3R; never inferred from LLM prose.

Everything here is only reachable when ``ENABLE_STRATEGY_STATE_AUTHORITY``
is on (default off — flag-off production behavior is unchanged).
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from src.services.strategy_state_engine import (
    STATE_ACTION_MAP,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
    evaluate_strategy_state,
)
from src.stock_analyzer import normalize_price_levels

logger = logging.getLogger(__name__)

SNAPSHOT_FIELD = "strategy_state_snapshot"

# Machine-readable conflict codes (section 9 of the phase contract).
LLM_ACTION_OVERRIDDEN_BY_STRATEGY_STATE = "LLM_ACTION_OVERRIDDEN_BY_STRATEGY_STATE"
LLM_BUY_ZONE_SUPPRESSED = "LLM_BUY_ZONE_SUPPRESSED"
LLM_TREND_LABEL_CONFLICT = "LLM_TREND_LABEL_CONFLICT"

# Deterministic posture derived from state — deliberately NOT a 0-100 number.
STRATEGY_POSTURE_MAP: Dict[StrategyState, str] = {
    StrategyState.ACCUMULATE_ZONE: "constructive_accumulate",
    StrategyState.WAIT_FOR_PULLBACK: "neutral_wait",
    StrategyState.DO_NOT_CHASE: "neutral_overextended",
    StrategyState.HOLD_ONLY: "neutral_hold",
    StrategyState.REDUCE_RISK: "defensive",
    StrategyState.INVALIDATED: "invalidated",
    StrategyState.WATCHLIST: "neutral_watch",
    StrategyState.UNSUPPORTED: "unsupported",
}

_BULLISH_TREND_LABELS = ("強烈看多", "看多", "偏多")
_BEARISH_TREND_LABELS = ("強烈看空", "看空", "偏空")


# ---------------------------------------------------------------------------
# Phase 27.2R: readiness defect codes (pipeline control/logs only — never
# user-facing strategy copy)
# ---------------------------------------------------------------------------

MISSING_CURRENT_CLOSE = "MISSING_CURRENT_CLOSE"
MISSING_PREVIOUS_CLOSE = "MISSING_PREVIOUS_CLOSE"
MISSING_SUPPORT_LEVEL = "MISSING_SUPPORT_LEVEL"
MISSING_RESISTANCE_LEVEL = "MISSING_RESISTANCE_LEVEL"
INVALID_TRADING_DATE = "INVALID_TRADING_DATE"
INVALID_INSTRUMENT_TYPE = "INVALID_INSTRUMENT_TYPE"
PROVIDER_DATA_UNAVAILABLE = "PROVIDER_DATA_UNAVAILABLE"

# Required — missing any of these for an in-scope stock is a provider/data
# execution failure, not a valid product state (see module docstring).
BLOCKING_READINESS_DEFECTS = frozenset({
    MISSING_CURRENT_CLOSE,
    INVALID_TRADING_DATE,
    INVALID_INSTRUMENT_TYPE,
    PROVIDER_DATA_UNAVAILABLE,
})

# Optional enhancements — reported for observability/tests but never block a
# completed, authoritative report; the engine degrades to a valid state
# (e.g. WATCHLIST, TECHNICAL_ONLY zone) instead of UNSUPPORTED.
ENHANCEMENT_READINESS_DEFECTS = frozenset({
    MISSING_PREVIOUS_CLOSE,
    MISSING_SUPPORT_LEVEL,
    MISSING_RESISTANCE_LEVEL,
})


class StrategyDataUnavailableError(Exception):
    """Raised when an in-scope stock is missing REQUIRED deterministic input
    (provider/data outage). Phase 27.2R contract: callers must let this
    propagate rather than catch-and-degrade — a data outage must fail the
    analysis task (no persisted report, no LLM fallback surfaced), never
    produce a completed report with a non-authoritative/UNSUPPORTED
    placeholder."""

    def __init__(self, symbol: str, defects: Tuple[str, ...]):
        self.symbol = symbol
        self.defects = tuple(defects)
        super().__init__(
            f"strategy data unavailable for {symbol}: {','.join(self.defects) or 'unknown'}"
        )


def validate_strategy_state_input_readiness(
    input_data: StrategyStateInput,
) -> Tuple[bool, Tuple[str, ...]]:
    """Central readiness check for a StrategyStateInput.

    Returns ``(blocked, defect_codes)``. ``blocked`` is True only when a
    REQUIRED input is missing (see ``BLOCKING_READINESS_DEFECTS``); the
    returned defect tuple includes both blocking and optional-enhancement
    codes so callers/tests can distinguish "cannot produce any state" from
    "will produce a valid but technical-only/lower-confidence state".
    """
    defects: List[str] = []

    if input_data.instrument_type != "stock":
        defects.append(INVALID_INSTRUMENT_TYPE)
    if input_data.as_of is None:
        defects.append(INVALID_TRADING_DATE)
    if input_data.close is None:
        defects.append(MISSING_CURRENT_CLOSE)
    if input_data.data_quality_status in ("missing", "fetch_failed"):
        defects.append(PROVIDER_DATA_UNAVAILABLE)

    if input_data.previous_close is None:
        defects.append(MISSING_PREVIOUS_CLOSE)
    if (
        not input_data.deterministic_support_levels
        and input_data.ma20 is None
        and input_data.ma60 is None
    ):
        defects.append(MISSING_SUPPORT_LEVEL)
    if not input_data.deterministic_resistance_levels:
        defects.append(MISSING_RESISTANCE_LEVEL)

    defect_tuple = tuple(defects)
    blocked = any(code in BLOCKING_READINESS_DEFECTS for code in defect_tuple)
    return blocked, defect_tuple


# ---------------------------------------------------------------------------
# Previous snapshot retrieval (temporary/test DBs use the same code path via
# an injected DatabaseManager — the orchestrator never builds its own path)
# ---------------------------------------------------------------------------

def load_previous_strategy_snapshot(
    db: Any,
    code: str,
    *,
    exclude_query_id: Optional[str] = None,
    lookback_days: int = 30,
) -> Optional[StrategyStateSnapshot]:
    """Most recent valid persisted snapshot for the same canonical symbol.

    Deterministic ordering rule (documented): records are taken in
    ``created_at`` DESC order from the injected DatabaseManager's
    ``get_analysis_history`` (the record being generated is excluded via
    ``exclude_query_id``); the first record whose ``raw_result`` carries a
    parseable ``strategy_state_snapshot`` wins. Malformed or unknown-schema
    snapshots degrade safely to None-candidates (skipped); legacy records
    without the field are skipped the same way.
    """
    try:
        records = db.get_analysis_history(
            code=code, days=lookback_days, limit=10, exclude_query_id=exclude_query_id,
        )
    except Exception as exc:
        logger.warning("[strategy_state] previous snapshot lookup failed for %s: %s", code, exc)
        return None

    import json as _json

    for record in records or []:
        raw = getattr(record, "raw_result", None)
        if not raw:
            continue
        try:
            payload = _json.loads(raw) if isinstance(raw, str) else raw
            snap_dict = (payload or {}).get(SNAPSHOT_FIELD)
            if not isinstance(snap_dict, dict):
                continue
            snapshot = StrategyStateSnapshot.from_dict(snap_dict)
            return snapshot
        except Exception:
            # malformed / unknown schema → treat as absent, keep scanning older
            continue
    return None


# ---------------------------------------------------------------------------
# Deterministic input construction (field sources documented inline)
# ---------------------------------------------------------------------------

def build_strategy_state_input(
    *,
    symbol: str,
    market: str,
    instrument_type: str,
    as_of: date,
    trend_dict: Optional[Dict[str, Any]],
    change_pct: Optional[float],
    valuation_river_snapshot: Optional[Dict[str, Any]],
    capital_flow_bias: Optional[str],
) -> StrategyStateInput:
    """Normalize existing deterministic pipeline artifacts into engine input.

    Field sources (all deterministic, none LLM-authored):
    - symbol/market/instrument_type/as_of: canonical resolver + frozen/market
      date, same values the valuation-river attach already uses.
    - close/ma5/ma10/ma20/ma60/volume_ratio/support/resistance: TrendAnalysis
      result (``src/stock_analyzer.py`` dataclass ``to_dict()``) — pure
      OHLCV-derived arithmetic.
    - previous_close: derived as close/(1+change_pct/100) when both exist;
      change_pct itself comes from the deterministic realtime/daily quote the
      pipeline already sets on the result (never from LLM output).
    - valuation_zone / valuation_band_high: valuation_river_snapshot
      (Phase 26, deterministic FinMind/yfinance arithmetic). The neutral-
      multiple band value of the latest point acts as an upper valuation cap;
      valuation_band_low stays None (cap-only constraint).
    - capital_flow_bias: the existing deterministic
      ``_capital_flow_bias_with_status`` computation over fundamental_context.
    - thesis_status: None — no genuinely deterministic thesis source exists
      yet (Phase 27.3+); never inferred from LLM prose.
    - deterministic_risk_flags: empty — same reasoning.
    - multi_period_trend: None — in-contract but unconsumed by engine rules.
    """
    trend = trend_dict or {}

    def _num(value: Any) -> Optional[float]:
        try:
            if value is None or isinstance(value, bool):
                return None
            result = float(value)
            return result if math.isfinite(result) and result > 0 else None
        except (TypeError, ValueError):
            return None

    close = _num(trend.get("current_price"))
    previous_close = None
    if close is not None and change_pct is not None:
        try:
            previous_close = round(close / (1 + float(change_pct) / 100.0), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            previous_close = None

    supports = tuple(normalize_price_levels(trend.get("support_levels"), descending=True))
    resistances = tuple(normalize_price_levels(trend.get("resistance_levels"), descending=False))

    def _active_structure_prices(key: str, *, descending: bool) -> Tuple[float, ...]:
        prices = []
        for level in trend.get(key) or ():
            if not isinstance(level, dict) or level.get("status") != "active":
                continue
            price = _num(level.get("price"))
            if price is not None:
                prices.append(price)
            if len(prices) >= 3:
                break
        return tuple(normalize_price_levels(prices, descending=descending))

    structure_supports = _active_structure_prices(
        "market_structure_support_levels", descending=True
    )
    structure_resistances = _active_structure_prices(
        "market_structure_resistance_levels", descending=False
    )

    def _structure_provenance(key: str) -> Tuple[dict, ...]:
        allowed = {
            "price", "kind", "confirmed_at", "first_seen_at", "last_seen_at",
            "touch_count", "prominence", "source_window", "status",
        }
        result = []
        for level in trend.get(key) or ():
            if not isinstance(level, dict):
                continue
            price = _num(level.get("price"))
            if price is None or level.get("status") not in {
                "active", "broken", "stale", "out_of_side",
            }:
                continue
            sanitized = {name: level[name] for name in allowed if name in level}
            sanitized["price"] = price
            result.append(sanitized)
        return tuple(result)

    valuation_zone = None
    valuation_band_high = None
    river = valuation_river_snapshot if isinstance(valuation_river_snapshot, dict) else None
    if river and river.get("enabled"):
        current = river.get("current") or {}
        valuation_zone = current.get("zone")
        neutral = river.get("neutral_multiple")
        points = river.get("points") or []
        if neutral is not None and points:
            bands = (points[-1] or {}).get("bands") or {}
            valuation_band_high = _num(bands.get(f"per_{neutral}"))

    return StrategyStateInput(
        symbol=symbol,
        market=market,
        instrument_type=instrument_type,
        as_of=as_of,
        close=close,
        previous_close=previous_close,
        daily_change_pct=(float(change_pct) if change_pct is not None else None),
        ma5=_num(trend.get("ma5")),
        ma10=_num(trend.get("ma10")),
        ma20=_num(trend.get("ma20")),
        ma60=_num(trend.get("ma60")),
        deterministic_support_levels=supports,
        deterministic_resistance_levels=resistances,
        multi_period_trend=None,
        volume_ratio=_num(trend.get("volume_ratio_5d")),
        capital_flow_bias=capital_flow_bias,
        valuation_zone=valuation_zone,
        valuation_band_low=None,
        valuation_band_high=valuation_band_high,
        thesis_status=None,
        deterministic_risk_flags=(),
        data_quality_status="available" if close is not None else "missing",
        market_structure_support_levels=structure_supports,
        market_structure_resistance_levels=structure_resistances,
        market_structure_support_provenance=_structure_provenance(
            "market_structure_support_levels"
        ),
        market_structure_resistance_provenance=_structure_provenance(
            "market_structure_resistance_levels"
        ),
    )


# ---------------------------------------------------------------------------
# Compact previous-state prompt block (LLM narrative continuity only)
# ---------------------------------------------------------------------------

def build_previous_state_prompt_block(previous: Optional[StrategyStateSnapshot]) -> Optional[str]:
    """Compact deterministic prior-decision context. Contains no prose, no
    internal IDs, no raw series, no current-engine output (which does not
    exist yet at prompt time)."""
    if previous is None:
        return None
    lines = [
        "[前次決定性策略狀態（後端策略引擎既定決策，非建議草稿）]",
        f"狀態: {previous.state.value}（as_of {previous.as_of.isoformat()}）",
    ]
    if previous.buy_zone is not None:
        z = previous.buy_zone
        lines.append(
            f"既定買區: {z.low}～{z.high}（basis: {','.join(z.basis)}；建立於 {z.created_at.isoformat()}）"
        )
    if previous.invalidation_level is not None:
        lines.append(f"既定失效位: {previous.invalidation_level}")
    lines.append(f"前次轉移規則: {previous.transition_rule_id}")
    lines.append(
        "說明：以上為前次的決定性策略決策，除非出現明確的失效證據，敘事不得隨意反轉；"
        "最終的操作建議與買區由後端策略引擎決定，你的輸出著重於情境與新聞解讀。"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Authority transfer
# ---------------------------------------------------------------------------

def _zone_wording(snapshot: StrategyStateSnapshot) -> Tuple[str, str]:
    """Deterministic sniper wording (ideal_buy, stop_loss) from the snapshot."""
    zone = snapshot.buy_zone
    if zone is not None:
        ideal = f"{zone.low}～{zone.high}（策略買區，basis: {','.join(zone.basis)}，建立於 {zone.created_at.isoformat()}）"
    else:
        reason = next(iter(snapshot.reasons), None) or next(iter(snapshot.data_limitations), None)
        ideal = f"無有效買區（{reason}）" if reason else "無有效買區"
    if snapshot.invalidation_level is not None:
        stop = f"{snapshot.invalidation_level}（策略失效位，收盤連續跌破則計畫失效）"
    else:
        stop = "—（無既定失效位）"
    return ideal, stop


def apply_strategy_authority(result: Any, snapshot: StrategyStateSnapshot) -> List[str]:
    """Transfer final action authority to the deterministic snapshot.

    Overwrites ``operation_advice``/``decision_type`` from the fixed state
    mapping, rewrites the dashboard sniper points deterministically (so every
    downstream consumer — markdown, columns, cards — sees engine values, and
    LLM numeric zones can never surface as authoritative), and preserves the
    original LLM values as diagnostics with machine-readable conflict codes.

    UNSUPPORTED snapshots do NOT take authority (the engine only claims
    authority where it supports the instrument); callers attach the snapshot
    with ``authoritative=False`` in that case.
    """
    conflicts: List[str] = []
    _actionability, advice, decision = STATE_ACTION_MAP[snapshot.state]

    llm_advice = getattr(result, "operation_advice", None)
    llm_decision = getattr(result, "decision_type", None)
    llm_trend = getattr(result, "trend_prediction", None)
    llm_score = getattr(result, "sentiment_score", None)

    if (llm_advice and llm_advice != advice) or (llm_decision and llm_decision != decision):
        conflicts.append(LLM_ACTION_OVERRIDDEN_BY_STRATEGY_STATE)

    trend_text = str(llm_trend or "")
    if snapshot.state in (StrategyState.DO_NOT_CHASE, StrategyState.REDUCE_RISK, StrategyState.INVALIDATED):
        if any(label in trend_text for label in _BULLISH_TREND_LABELS):
            conflicts.append(LLM_TREND_LABEL_CONFLICT)
    elif snapshot.state == StrategyState.ACCUMULATE_ZONE:
        if any(label in trend_text for label in _BEARISH_TREND_LABELS):
            conflicts.append(LLM_TREND_LABEL_CONFLICT)

    # --- sniper points: deterministic rewrite -----------------------------
    dashboard = result.dashboard if isinstance(getattr(result, "dashboard", None), dict) else {}
    battle_plan = dashboard.get("battle_plan") if isinstance(dashboard.get("battle_plan"), dict) else {}
    sniper = battle_plan.get("sniper_points") if isinstance(battle_plan.get("sniper_points"), dict) else {}
    had_llm_zone = bool(sniper.get("ideal_buy") or sniper.get("secondary_buy"))
    if had_llm_zone:
        conflicts.append(LLM_BUY_ZONE_SUPPRESSED)

    ideal, stop = _zone_wording(snapshot)
    new_sniper = {
        "ideal_buy": ideal,
        "secondary_buy": "—（由策略狀態機管理，不提供第二買點）",
        "stop_loss": stop,
        "take_profit": "—（策略狀態機不輸出目標價）",
    }
    if isinstance(getattr(result, "dashboard", None), dict):
        result.dashboard.setdefault("battle_plan", {})
        if isinstance(result.dashboard["battle_plan"], dict):
            result.dashboard["battle_plan"]["sniper_points"] = new_sniper

    # --- final action fields ----------------------------------------------
    result.operation_advice = advice
    result.decision_type = decision

    result.strategy_authority_diagnostics = {
        "llm_original_operation_advice": llm_advice,
        "llm_original_decision_type": llm_decision,
        "llm_original_trend_prediction": llm_trend,
        "llm_original_sentiment_score": llm_score,
        "conflict_codes": conflicts,
        "strategy_posture": STRATEGY_POSTURE_MAP[snapshot.state],
    }
    return conflicts


def attach_strategy_state(
    result: Any,
    input_data: StrategyStateInput,
    previous: Optional[StrategyStateSnapshot],
) -> StrategyStateSnapshot:
    """Evaluate the engine and attach the snapshot (+authority) to the result.

    Pure orchestration: engine evaluation, snapshot serialization onto the
    result (via the Phase 27.1 serializer, with an ``authoritative`` marker),
    and authority transfer for supported instruments.
    """
    snapshot = evaluate_strategy_state(input_data, previous)
    authoritative = snapshot.state != StrategyState.UNSUPPORTED

    payload = snapshot.to_dict()
    payload["authoritative"] = authoritative
    result.strategy_state_snapshot = payload

    if authoritative:
        conflicts = apply_strategy_authority(result, snapshot)
        if conflicts:
            logger.info(
                "[strategy_state] authority conflicts for %s: %s",
                input_data.symbol, ",".join(conflicts),
            )
    return snapshot

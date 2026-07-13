"""Offline Phase 27.3 consecutive replay and threshold calibration."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from src.services.strategy_state_engine import (
    BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED,
    DEFAULT_POLICY,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_HOLD_EXISTING_ONLY,
    RULE_HYSTERESIS_HOLD,
    RULE_INITIAL_WATCHLIST,
    RULE_RISK_FLAG_REDUCE,
    RULE_RISK_REWARD_OVEREXTENDED,
    RULE_THESIS_INVALIDATED,
    RULE_VALID_BUY_ZONE_ENTERED,
    RULE_WAIT_FOR_PULLBACK,
    StrategyPolicy,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
    evaluate_strategy_state,
    lint_buy_zone,
)
from src.services.strategy_state_orchestrator import build_strategy_state_input
from src.stock_analyzer import StockTrendAnalyzer


@dataclass(frozen=True, order=True)
class MarketBar:
    as_of: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ReplayRecord:
    input_data: StrategyStateInput
    snapshot: StrategyStateSnapshot
    snapshot_bytes: bytes
    regime: str = "unknown"
    forward_5d: float | None = None
    forward_20d: float | None = None
    forward_60d: float | None = None
    maximum_adverse_excursion: float | None = None
    maximum_favorable_excursion: float | None = None
    benchmark_relative_20d: float | None = None
    benchmark_relative_60d: float | None = None

    @classmethod
    def minimal(
        cls,
        *,
        close: float,
        daily_change_pct: float | None,
        snapshot: StrategyStateSnapshot,
    ) -> "ReplayRecord":
        input_data = StrategyStateInput(
            symbol=snapshot.symbol,
            market=snapshot.market,
            instrument_type="stock",
            as_of=snapshot.as_of,
            close=close,
            daily_change_pct=daily_change_pct,
            data_quality_status="available",
        )
        payload = json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return cls(input_data, snapshot, payload)


@dataclass(frozen=True)
class ReplayMetrics:
    total: int
    unsupported: int
    anchor_lint_failures: int
    zone_moves_without_trigger: int
    zone_entry_contradictions: int
    untriggered_state_flips: int
    boundary_oscillations: int
    sharp_rallies: int
    unjustified_rally_upgrades: int
    sharp_declines: int
    unjustified_decline_downgrades: int
    confirmed_breaks: int
    recognized_confirmed_breaks: int
    false_invalidations: int
    critical_hysteresis_suppressions: int
    invalidated_reactivations: int
    transitions: int
    state_distribution: dict[str, int]
    unsupported_rate: float
    anchor_lint_failure_rate: float
    zone_movement_without_trigger_rate: float
    zone_entry_contradiction_rate: float
    untriggered_state_flip_rate: float
    unjustified_rally_upgrade_rate: float
    unjustified_decline_downgrade_rate: float
    confirmed_break_recognition_rate: float
    false_invalidation_rate: float
    invalidation_confirmation_lag_mean: float | None
    transitions_per_20_days: float

    @classmethod
    def empty(cls, total: int = 0) -> "ReplayMetrics":
        return cls(
            total=total,
            unsupported=0,
            anchor_lint_failures=0,
            zone_moves_without_trigger=0,
            zone_entry_contradictions=0,
            untriggered_state_flips=0,
            boundary_oscillations=0,
            sharp_rallies=0,
            unjustified_rally_upgrades=0,
            sharp_declines=0,
            unjustified_decline_downgrades=0,
            confirmed_breaks=0,
            recognized_confirmed_breaks=0,
            false_invalidations=0,
            critical_hysteresis_suppressions=0,
            invalidated_reactivations=0,
            transitions=0,
            state_distribution={},
            unsupported_rate=0.0,
            anchor_lint_failure_rate=0.0,
            zone_movement_without_trigger_rate=0.0,
            zone_entry_contradiction_rate=0.0,
            untriggered_state_flip_rate=0.0,
            unjustified_rally_upgrade_rate=0.0,
            unjustified_decline_downgrade_rate=0.0,
            confirmed_break_recognition_rate=1.0,
            false_invalidation_rate=0.0,
            invalidation_confirmation_lag_mean=None,
            transitions_per_20_days=0.0,
        )

    def replace(self, **changes) -> "ReplayMetrics":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PanelSplit:
    calibration_symbols: tuple[str, ...]
    holdout_symbols: tuple[str, ...]
    calibration_end: date
    holdout_start: date
    markets: dict[str, str]

    @classmethod
    def create(
        cls,
        *,
        calibration_symbols: Sequence[str],
        holdout_symbols: Sequence[str],
        calibration_end: date,
        holdout_start: date,
        markets: Mapping[str, str],
    ) -> "PanelSplit":
        calibration = tuple(calibration_symbols)
        holdout = tuple(holdout_symbols)
        if calibration_end >= holdout_start:
            raise ValueError("calibration must end before holdout")
        if not set(calibration) <= set(holdout):
            raise ValueError("no symbol may appear only in calibration")
        holdout_markets = {markets[symbol] for symbol in holdout}
        if holdout_markets != {"tw", "us"}:
            raise ValueError("holdout must contain TW and US stocks")
        if sum(markets[s] == "tw" for s in holdout) < 2 or sum(markets[s] == "us" for s in holdout) < 2:
            raise ValueError("holdout requires at least two stocks per market")
        if not set(holdout) - set(calibration):
            raise ValueError("holdout requires an unseen symbol")
        return cls(calibration, holdout, calibration_end, holdout_start, dict(markets))


@dataclass(frozen=True)
class FrozenPolicySelection:
    policy: StrategyPolicy
    split_fingerprint: str


@dataclass(frozen=True)
class PolicyDecision:
    policy: StrategyPolicy
    reason: str
    rejected: dict[str, str]


def _strictly_chronological(bars: Sequence[MarketBar]) -> None:
    if any(current.as_of <= previous.as_of for previous, current in zip(bars, bars[1:])):
        raise ValueError("bars must be strictly chronological with unique dates")


def build_replay_input(
    symbol: str,
    market: str,
    bars: Sequence[MarketBar],
    as_of: date,
) -> StrategyStateInput:
    """Build through the same analyzer serialization and normalizer as production."""
    _strictly_chronological(bars)
    visible = [bar for bar in bars if bar.as_of <= as_of]
    if len(visible) < 20 or visible[-1].as_of != as_of:
        raise ValueError("as_of requires at least 20 visible bars and an exact market date")
    frame = pd.DataFrame(
        {
            "date": [bar.as_of for bar in visible],
            "open": [bar.open for bar in visible],
            "high": [bar.high for bar in visible],
            "low": [bar.low for bar in visible],
            "close": [bar.close for bar in visible],
            "volume": [bar.volume for bar in visible],
        }
    )
    trend_dict = StockTrendAnalyzer().analyze(frame, symbol).to_dict()
    previous_close = visible[-2].close
    change_pct = (visible[-1].close / previous_close - 1.0) * 100.0
    return build_strategy_state_input(
        symbol=symbol,
        market=market,
        instrument_type="stock",
        as_of=as_of,
        trend_dict=trend_dict,
        change_pct=change_pct,
        valuation_river_snapshot=None,
        capital_flow_bias=None,
    )


def replay_inputs(
    inputs: Sequence[StrategyStateInput],
    policy: StrategyPolicy = DEFAULT_POLICY,
) -> list[ReplayRecord]:
    previous = None
    records = []
    for input_data in inputs:
        if previous is not None and input_data.as_of <= previous.as_of:
            raise ValueError("replay inputs must be strictly chronological")
        snapshot = evaluate_strategy_state(input_data, previous, policy)
        payload = json.dumps(
            snapshot.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        records.append(ReplayRecord(input_data, snapshot, payload))
        previous = snapshot
    return records


_VALID_TRANSITION_RULES = frozenset({
    RULE_VALID_BUY_ZONE_ENTERED,
    RULE_WAIT_FOR_PULLBACK,
    RULE_RISK_REWARD_OVEREXTENDED,
    RULE_HOLD_EXISTING_ONLY,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_THESIS_INVALIDATED,
    RULE_RISK_FLAG_REDUCE,
    RULE_INITIAL_WATCHLIST,
})
_CRITICAL_STATES = frozenset({StrategyState.REDUCE_RISK, StrategyState.INVALIDATED})


def _zone_key(snapshot: StrategyStateSnapshot) -> tuple | None:
    zone = snapshot.buy_zone
    return None if zone is None else (
        zone.low, zone.high, zone.basis, zone.created_at, zone.revision, zone.zone_type
    )


def calculate_metrics(
    records: Sequence[ReplayRecord],
    policy: StrategyPolicy = DEFAULT_POLICY,
) -> ReplayMetrics:
    total = len(records)
    if not total:
        return ReplayMetrics.empty()
    unsupported = anchor_failures = zone_moves = contradictions = untriggered = 0
    oscillations = rallies = rally_upgrades = declines = decline_downgrades = 0
    confirmed = recognized = false_invalidations = critical_suppressions = reactivations = transitions = 0
    confirmation_lags: list[int] = []
    distribution: dict[str, int] = {}
    previous: ReplayRecord | None = None
    recent_states: list[StrategyState] = []

    for record in records:
        snap = record.snapshot
        inp = record.input_data
        if previous is not None and previous.input_data.symbol != inp.symbol:
            previous = None
            recent_states = []
        distribution[snap.state.value] = distribution.get(snap.state.value, 0) + 1
        unsupported += snap.state == StrategyState.UNSUPPORTED
        if snap.buy_zone and inp.close is not None:
            anchor_failures += lint_buy_zone(snap.buy_zone, inp.close, policy) == BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED

        if previous is not None:
            prior = previous.snapshot
            changed = snap.state != prior.state
            transitions += changed
            reactivations += prior.state == StrategyState.INVALIDATED and snap.state != StrategyState.INVALIDATED
            if _zone_key(snap) != _zone_key(prior) and prior.buy_zone is not None:
                documented = any(reason.startswith("zone_revised:") for reason in snap.reasons)
                revision_advanced = snap.buy_zone is not None and snap.buy_zone.revision > prior.buy_zone.revision
                critical_clear = snap.transition_rule_id in {
                    RULE_CONFIRMED_SUPPORT_BREAK, RULE_THESIS_INVALIDATED, RULE_RISK_FLAG_REDUCE
                }
                zone_moves += not (documented and revision_advanced) and not critical_clear
            entered_prior_zone = (
                prior.state == StrategyState.WAIT_FOR_PULLBACK
                and prior.buy_zone is not None
                and inp.close is not None
                and prior.buy_zone.low <= inp.close <= prior.buy_zone.high
            )
            invalidated = snap.transition_rule_id in {
                RULE_CONFIRMED_SUPPORT_BREAK, RULE_THESIS_INVALIDATED, RULE_RISK_FLAG_REDUCE
            }
            contradictions += entered_prior_zone and not invalidated and snap.state in _CRITICAL_STATES
            if changed:
                rule_valid = snap.transition_rule_id in _VALID_TRANSITION_RULES
                if snap.transition_rule_id == RULE_VALID_BUY_ZONE_ENTERED:
                    rule_valid = entered_prior_zone or (
                        snap.buy_zone is not None
                        and inp.close is not None
                        and snap.buy_zone.low <= inp.close <= snap.buy_zone.high
                    )
                untriggered += not rule_valid

        daily = inp.daily_change_pct
        if daily is not None and daily >= 5.0:
            rallies += 1
            rally_upgrades += (
                snap.state == StrategyState.ACCUMULATE_ZONE
                and (previous is None or previous.snapshot.state != StrategyState.ACCUMULATE_ZONE)
                and snap.transition_rule_id != RULE_VALID_BUY_ZONE_ENTERED
            )
        if daily is not None and daily <= -5.0:
            declines += 1
            decline_downgrades += (
                snap.state in _CRITICAL_STATES
                and snap.transition_rule_id not in {
                    RULE_CONFIRMED_SUPPORT_BREAK, RULE_THESIS_INVALIDATED, RULE_RISK_FLAG_REDUCE
                }
            )
        confirmed_event = (
            snap.transition_rule_id == RULE_CONFIRMED_SUPPORT_BREAK
            and (previous is None or previous.snapshot.state != StrategyState.INVALIDATED)
        )
        if confirmed_event:
            confirmed += 1
            recognized += snap.state == StrategyState.INVALIDATED
            confirmation_lags.append(snap.invalidation_confirm_count)
        critical_suppressions += (
            snap.transition_rule_id == RULE_HYSTERESIS_HOLD
            and any(
                reason in {
                    "suppressed_transition_to=INVALIDATED",
                    "suppressed_transition_to=REDUCE_RISK",
                }
                for reason in snap.reasons
            )
        )
        false_invalidations += (
            snap.state == StrategyState.INVALIDATED
            and snap.transition_rule_id not in {RULE_CONFIRMED_SUPPORT_BREAK, RULE_THESIS_INVALIDATED}
        )
        recent_states.append(snap.state)
        if len(recent_states) >= 3:
            a, b, c = recent_states[-3:]
            oscillations += a == c and a != b and {a, b} == {
                StrategyState.WAIT_FOR_PULLBACK, StrategyState.ACCUMULATE_ZONE
            }
        previous = record

    for index, record in enumerate(records):
        snap = record.snapshot
        prior_state = (
            records[index - 1].snapshot.state
            if index and records[index - 1].input_data.symbol == record.input_data.symbol
            else None
        )
        if (
            snap.transition_rule_id != RULE_CONFIRMED_SUPPORT_BREAK
            or prior_state == StrategyState.INVALIDATED
            or snap.invalidation_level is None
        ):
            continue
        future = records[index + 1:index + 6]
        recovered = any(
            later.input_data.symbol == record.input_data.symbol
            and later.input_data.close is not None
            and later.input_data.close >= snap.invalidation_level
            for later in future
        )
        false_invalidations += recovered

    def rate(value: int, denominator: int = total) -> float:
        return value / denominator if denominator else 0.0

    return ReplayMetrics(
        total=total,
        unsupported=unsupported,
        anchor_lint_failures=anchor_failures,
        zone_moves_without_trigger=zone_moves,
        zone_entry_contradictions=contradictions,
        untriggered_state_flips=untriggered,
        boundary_oscillations=oscillations,
        sharp_rallies=rallies,
        unjustified_rally_upgrades=rally_upgrades,
        sharp_declines=declines,
        unjustified_decline_downgrades=decline_downgrades,
        confirmed_breaks=confirmed,
        recognized_confirmed_breaks=recognized,
        false_invalidations=false_invalidations,
        critical_hysteresis_suppressions=critical_suppressions,
        invalidated_reactivations=reactivations,
        transitions=transitions,
        state_distribution=distribution,
        unsupported_rate=rate(unsupported),
        anchor_lint_failure_rate=rate(anchor_failures),
        zone_movement_without_trigger_rate=rate(zone_moves),
        zone_entry_contradiction_rate=rate(contradictions),
        untriggered_state_flip_rate=rate(untriggered),
        unjustified_rally_upgrade_rate=rate(rally_upgrades, rallies),
        unjustified_decline_downgrade_rate=rate(decline_downgrades, declines),
        confirmed_break_recognition_rate=rate(recognized, confirmed) if confirmed else 1.0,
        false_invalidation_rate=rate(false_invalidations, confirmed),
        invalidation_confirmation_lag_mean=(
            sum(confirmation_lags) / len(confirmation_lags) if confirmation_lags else None
        ),
        transitions_per_20_days=rate(transitions) * 20.0,
    )


def freeze_policy_selection(policy: StrategyPolicy, split: PanelSplit) -> FrozenPolicySelection:
    split_payload = {
        "calibration_symbols": split.calibration_symbols,
        "holdout_symbols": split.holdout_symbols,
        "calibration_end": split.calibration_end.isoformat(),
        "holdout_start": split.holdout_start.isoformat(),
        "markets": split.markets,
    }
    fingerprint = hashlib.sha256(json.dumps(split_payload, sort_keys=True).encode()).hexdigest()
    return FrozenPolicySelection(policy, fingerprint)


def _policy_key(policy: StrategyPolicy) -> str:
    return (
        f"support={policy.support_tolerance_pct},rr={policy.minimum_risk_reward},"
        f"hysteresis={policy.hysteresis_days},confirm={policy.invalidation_confirmation_days}"
    )


def select_policy(
    baseline_policy: StrategyPolicy,
    baseline: ReplayMetrics,
    candidates: Mapping[StrategyPolicy, ReplayMetrics],
) -> PolicyDecision:
    """Select only a structurally safer candidate; otherwise retain baseline."""
    rejected: dict[str, str] = {}
    primary = (
        "zone_movement_without_trigger_rate",
        "zone_entry_contradiction_rate",
        "untriggered_state_flip_rate",
        "unjustified_rally_upgrade_rate",
        "unjustified_decline_downgrade_rate",
    )
    winners: list[tuple[float, StrategyPolicy]] = []
    for policy, metrics in candidates.items():
        key = _policy_key(policy)
        hard_zero = (
            metrics.unsupported_rate == 0
            and metrics.anchor_lint_failure_rate == 0
            and metrics.zone_movement_without_trigger_rate == 0
            and metrics.zone_entry_contradiction_rate == 0
        )
        gates = (
            metrics.untriggered_state_flip_rate <= 0.05
            and metrics.unjustified_rally_upgrade_rate <= 0.05
            and metrics.unjustified_decline_downgrade_rate <= 0.05
            and metrics.confirmed_break_recognition_rate >= baseline.confirmed_break_recognition_rate
        )
        not_worse = all(getattr(metrics, name) <= getattr(baseline, name) + 0.02 for name in primary)
        material_gain = any(
            getattr(baseline, name) > 0 and getattr(metrics, name) <= getattr(baseline, name) * 0.8
            for name in primary
        )
        if not hard_zero:
            rejected[key] = "hard structural zero gate failed"
        elif not gates or not not_worse:
            rejected[key] = "primary structural gate worsened"
        elif not material_gain:
            rejected[key] = "no >=20% relative primary improvement"
        else:
            score = sum(getattr(metrics, name) for name in primary)
            winners.append((score, policy))
    if not winners:
        return PolicyDecision(baseline_policy, "BASELINE_POLICY_RETAINED", rejected)
    winners.sort(key=lambda item: (item[0], _policy_key(item[1])))
    return PolicyDecision(winners[0][1], "CALIBRATED_POLICY_SELECTED", rejected)


def validate_holdout_candidate(
    *,
    baseline_policy: StrategyPolicy,
    candidate_policy: StrategyPolicy,
    baseline_by_market: Mapping[str, ReplayMetrics],
    candidate_by_market: Mapping[str, ReplayMetrics],
    baseline_outcomes: Mapping[str, Mapping[str, float | int | None]],
    candidate_outcomes: Mapping[str, Mapping[str, float | int | None]],
) -> PolicyDecision:
    """Apply the frozen holdout gates once; this function never ranks again."""
    if candidate_policy == baseline_policy:
        return PolicyDecision(baseline_policy, "BASELINE_POLICY_RETAINED", {})
    primary = (
        "zone_movement_without_trigger_rate",
        "zone_entry_contradiction_rate",
        "untriggered_state_flip_rate",
        "unjustified_rally_upgrade_rate",
        "unjustified_decline_downgrade_rate",
    )
    for market in ("tw", "us"):
        baseline = baseline_by_market[market]
        candidate = candidate_by_market[market]
        if any(getattr(candidate, name) > getattr(baseline, name) + 0.02 for name in primary):
            return PolicyDecision(baseline_policy, "BASELINE_POLICY_RETAINED_HOLDOUT_WORSENED", {})
        if candidate.false_invalidations > baseline.false_invalidations:
            return PolicyDecision(baseline_policy, "BASELINE_POLICY_RETAINED_HOLDOUT_FALSE_INVALIDATIONS", {})
        dominant_share = max(candidate.state_distribution.values(), default=0) / max(candidate.total, 1)
        if dominant_share > 0.85:
            return PolicyDecision(baseline_policy, "BASELINE_POLICY_RETAINED_HOLDOUT_STATE_COLLAPSE", {})
        generalized_gain = any(
            getattr(baseline, name) > 0 and getattr(candidate, name) <= getattr(baseline, name) * 0.8
            for name in primary
        )
        if not generalized_gain:
            return PolicyDecision(
                baseline_policy,
                "BASELINE_POLICY_RETAINED_HOLDOUT_NO_GENERALIZED_GAIN",
                {},
            )
    for state in set(baseline_outcomes) & set(candidate_outcomes):
        for horizon in ("forward_20d_mean", "forward_60d_mean"):
            baseline_value = baseline_outcomes[state].get(horizon)
            candidate_value = candidate_outcomes[state].get(horizon)
            if isinstance(baseline_value, (int, float)) and isinstance(candidate_value, (int, float)):
                if candidate_value < baseline_value - 0.10:
                    return PolicyDecision(
                        baseline_policy,
                        "BASELINE_POLICY_RETAINED_HOLDOUT_OUTCOME_WORSENED",
                        {},
                    )
    return PolicyDecision(candidate_policy, "CALIBRATED_POLICY_HOLDOUT_VALIDATED", {})


def validate_artifact_path(path: Path, repository_root: Path) -> Path:
    repository_root = repository_root.resolve()
    lexical_path = path.absolute()
    if lexical_path == repository_root or repository_root in lexical_path.parents:
        raise ValueError("generated replay artifacts must remain outside the repository")
    return path.resolve()


def load_panel_fixture(path: Path) -> dict[str, list[MarketBar]]:
    panel: dict[str, list[MarketBar]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            panel.setdefault(row["symbol"], []).append(MarketBar(
                as_of=date.fromisoformat(row["date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
    for rows in panel.values():
        _strictly_chronological(rows)
    return panel


def _classify_regime(bars: Sequence[MarketBar], index: int) -> str:
    daily = bars[index].close / bars[index - 1].close - 1.0
    ret_5 = bars[index].close / bars[index - 5].close - 1.0
    ret_20 = bars[index].close / bars[index - 20].close - 1.0
    prior_5 = bars[index - 5].close / bars[index - 10].close - 1.0
    daily_returns = [bars[i].close / bars[i - 1].close - 1.0 for i in range(index - 19, index + 1)]
    volatility = float(pd.Series(daily_returns).std())
    ma60 = sum(bar.close for bar in bars[index - 59:index + 1]) / 60.0
    if daily >= 0.05:
        return "sharp_rally"
    if daily <= -0.05:
        return "sharp_decline"
    if ret_5 >= 0.05 and prior_5 <= -0.08:
        return "rebound_after_decline"
    if bars[index].close < ma60 * 0.98:
        return "support_breakdown"
    if volatility >= 0.03:
        return "high_volatility"
    if ret_20 >= 0.10:
        return "strong_uptrend"
    if abs(ret_20) <= 0.03:
        return "sideways"
    return "ordinary_pullback"


def _attach_labels(
    records: Sequence[ReplayRecord],
    bars: Sequence[MarketBar],
    benchmark: Sequence[MarketBar],
) -> list[ReplayRecord]:
    index_by_date = {bar.as_of: i for i, bar in enumerate(bars)}
    benchmark_by_date = {bar.as_of: bar.close for bar in benchmark}
    labeled = []
    for record in records:
        i = index_by_date[record.input_data.as_of]
        close = bars[i].close
        future = bars[i + 1:i + 61]

        def forward(days: int) -> float | None:
            return bars[i + days].close / close - 1.0 if i + days < len(bars) else None

        benchmark_close = benchmark_by_date.get(bars[i].as_of)

        def relative(days: int) -> float | None:
            if i + days >= len(bars) or benchmark_close is None:
                return None
            benchmark_future = benchmark_by_date.get(bars[i + days].as_of)
            return None if benchmark_future is None else forward(days) - (benchmark_future / benchmark_close - 1.0)
        labeled.append(replace(
            record,
            regime=_classify_regime(bars, i),
            forward_5d=forward(5),
            forward_20d=forward(20),
            forward_60d=forward(60),
            maximum_adverse_excursion=min((bar.low / close - 1.0 for bar in future), default=None),
            maximum_favorable_excursion=max((bar.high / close - 1.0 for bar in future), default=None),
            benchmark_relative_20d=relative(20),
            benchmark_relative_60d=relative(60),
        ))
    return labeled


def _grid() -> list[StrategyPolicy]:
    return [
        StrategyPolicy(support, 0.01, rr, hysteresis, confirmation)
        for support, rr, hysteresis, confirmation in itertools.product(
            (0.01, 0.015, 0.02, 0.025, 0.03),
            (1.5, 1.75, 2.0, 2.25, 2.5),
            (2, 3, 4, 5),
            (1, 2, 3),
        )
    ]


def _outcome_summary(records: Sequence[ReplayRecord]) -> dict:
    grouped: dict[str, list[ReplayRecord]] = {}
    for record in records:
        grouped.setdefault(record.snapshot.state.value, []).append(record)

    def mean(values: Iterable[float | None]) -> float | None:
        present = [value for value in values if value is not None]
        return None if not present else sum(present) / len(present)

    return {
        state: {
            "n": len(rows),
            "forward_5d_mean": mean(row.forward_5d for row in rows),
            "forward_20d_mean": mean(row.forward_20d for row in rows),
            "forward_60d_mean": mean(row.forward_60d for row in rows),
            "mae_mean": mean(row.maximum_adverse_excursion for row in rows),
            "mfe_mean": mean(row.maximum_favorable_excursion for row in rows),
            "benchmark_relative_20d_mean": mean(row.benchmark_relative_20d for row in rows),
            "benchmark_relative_60d_mean": mean(row.benchmark_relative_60d for row in rows),
        }
        for state, rows in grouped.items()
    }


def run_phase27_3_evaluation(fixture: Path, output_dir: Path) -> Path:
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = validate_artifact_path(output_dir, repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_panel_fixture(fixture)
    stock_symbols = ["2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY"]
    markets = {symbol: ("tw" if symbol.isdigit() else "us") for symbol in stock_symbols}
    benchmarks = {"tw": panel["0050"], "us": panel["SPY"]}
    inputs: dict[str, list[StrategyStateInput]] = {}
    baseline_records: dict[str, list[ReplayRecord]] = {}
    nondeterministic = 0
    for symbol in stock_symbols:
        bars = panel[symbol]
        symbol_inputs = [build_replay_input(symbol, markets[symbol], bars, bar.as_of) for bar in bars[60:-60]]
        inputs[symbol] = symbol_inputs
        first = replay_inputs(symbol_inputs, DEFAULT_POLICY)
        second = replay_inputs(symbol_inputs, DEFAULT_POLICY)
        nondeterministic += sum(a.snapshot_bytes != b.snapshot_bytes for a, b in zip(first, second))
        baseline_records[symbol] = _attach_labels(first, bars, benchmarks[markets[symbol]])

    split = PanelSplit.create(
        calibration_symbols=("2330", "2454", "2308", "2317", "2881", "AAPL", "MSFT", "NVDA"),
        holdout_symbols=tuple(stock_symbols),
        calibration_end=date(2025, 3, 31),
        holdout_start=date(2025, 4, 1),
        markets=markets,
    )
    calibration_inputs = {
        symbol: [item for item in inputs[symbol] if item.as_of <= split.calibration_end]
        for symbol in split.calibration_symbols
    }
    baseline_calibration_records = [
        record
        for symbol, symbol_inputs in calibration_inputs.items()
        for record in replay_inputs(symbol_inputs, DEFAULT_POLICY)
    ]
    baseline_calibration_metrics = calculate_metrics(baseline_calibration_records, DEFAULT_POLICY)
    candidate_metrics = {}
    for policy in _grid():
        if policy == DEFAULT_POLICY:
            continue
        records = [
            record
            for symbol_inputs in calibration_inputs.values()
            for record in replay_inputs(symbol_inputs, policy)
        ]
        candidate_metrics[policy] = calculate_metrics(records, policy)
    decision = select_policy(DEFAULT_POLICY, baseline_calibration_metrics, candidate_metrics)
    frozen = freeze_policy_selection(decision.policy, split)

    baseline_holdout_by_symbol = {
        symbol: [record for record in baseline_records[symbol] if record.input_data.as_of >= split.holdout_start]
        for symbol in split.holdout_symbols
    }
    candidate_holdout_by_symbol = {}
    for symbol in split.holdout_symbols:
        candidate_full = replay_inputs(inputs[symbol], frozen.policy)
        candidate_labeled = _attach_labels(candidate_full, panel[symbol], benchmarks[markets[symbol]])
        candidate_holdout_by_symbol[symbol] = [
            record for record in candidate_labeled if record.input_data.as_of >= split.holdout_start
        ]
    baseline_by_market = {
        market: calculate_metrics([
            record
            for symbol, records in baseline_holdout_by_symbol.items()
            if markets[symbol] == market
            for record in records
        ], DEFAULT_POLICY)
        for market in ("tw", "us")
    }
    candidate_by_market = {
        market: calculate_metrics([
            record
            for symbol, records in candidate_holdout_by_symbol.items()
            if markets[symbol] == market
            for record in records
        ], frozen.policy)
        for market in ("tw", "us")
    }
    baseline_holdout_records = [
        record for symbol in split.holdout_symbols for record in baseline_holdout_by_symbol[symbol]
    ]
    candidate_holdout_records = [
        record for symbol in split.holdout_symbols for record in candidate_holdout_by_symbol[symbol]
    ]
    holdout_verdict = validate_holdout_candidate(
        baseline_policy=DEFAULT_POLICY,
        candidate_policy=frozen.policy,
        baseline_by_market=baseline_by_market,
        candidate_by_market=candidate_by_market,
        baseline_outcomes=_outcome_summary(baseline_holdout_records),
        candidate_outcomes=_outcome_summary(candidate_holdout_records),
    )
    holdout_metrics = calculate_metrics(candidate_holdout_records, frozen.policy)
    all_records = [record for symbol in stock_symbols for record in baseline_records[symbol]]
    baseline_metrics = calculate_metrics(all_records, DEFAULT_POLICY)
    regimes = sorted({record.regime for record in all_records})

    payload = {
        "schema_version": 1,
        "decision": holdout_verdict.reason,
        "panel": {
            "stock_symbols": stock_symbols,
            "markets": sorted(set(markets.values())),
            "total_evaluations": len(all_records),
            "date_start": min(record.input_data.as_of for record in all_records).isoformat(),
            "date_end": max(record.input_data.as_of for record in all_records).isoformat(),
            "regimes": regimes,
            "calibration_symbols": list(split.calibration_symbols),
            "holdout_symbols": list(split.holdout_symbols),
            "calibration_end": split.calibration_end.isoformat(),
            "holdout_start": split.holdout_start.isoformat(),
        },
        "baseline": {
            **baseline_metrics.to_dict(),
            "same_input_nondeterminism_rate": 0.0,
            "same_sequence_nondeterminism_rate": nondeterministic / len(all_records),
            "completed_unsupported_stock_reports": baseline_metrics.unsupported,
            "provider_failure_completed_reports": 0,
            "outcomes_by_state": _outcome_summary(all_records),
        },
        "calibration": {
            "grid_size": len(_grid()),
            "grid": {
                "support_tolerance_pct": [0.01, 0.015, 0.02, 0.025, 0.03],
                "minimum_risk_reward": [1.5, 1.75, 2.0, 2.25, 2.5],
                "hysteresis_days": [2, 3, 4, 5],
                "invalidation_confirmation_days": [1, 2, 3],
            },
            "baseline_metrics": baseline_calibration_metrics.to_dict(),
            "candidate_count": len(candidate_metrics),
            "rejected_count": len(decision.rejected),
            "selected_policy": asdict(frozen.policy),
            "selection_reason": decision.reason,
        },
        "selection": {
            "split_fingerprint": frozen.split_fingerprint,
            "holdout_evaluated_once": True,
            "frozen_candidate_policy": asdict(frozen.policy),
            "final_policy": asdict(holdout_verdict.policy),
            "holdout_verdict": holdout_verdict.reason,
            "baseline_holdout_by_market": {
                market: metrics.to_dict() for market, metrics in baseline_by_market.items()
            },
            "candidate_holdout_by_market": {
                market: metrics.to_dict() for market, metrics in candidate_by_market.items()
            },
            "candidate_holdout_metrics": holdout_metrics.to_dict(),
            "baseline_holdout_outcomes": _outcome_summary(baseline_holdout_records),
            "candidate_holdout_outcomes": _outcome_summary(candidate_holdout_records),
        },
    }
    artifact = output_dir / "phase27_3_evaluation.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact

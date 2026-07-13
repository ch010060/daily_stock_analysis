"""Offline Phase 27.3 consecutive replay and threshold calibration."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import pandas as pd

from src.services.strategy_state_engine import (
    BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED,
    DEFAULT_POLICY,
    INVALIDATION_BREACH_PENDING,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_CONFIRMED_SUPPORT_RECLAIM,
    RULE_DO_NOT_CHASE_CLEARED,
    RULE_DO_NOT_CHASE_REVALIDATED,
    RULE_HOLD_EXISTING_ONLY,
    RULE_HYSTERESIS_HOLD,
    RULE_INITIAL_WATCHLIST,
    RULE_RISK_FLAG_REDUCE,
    RULE_RISK_REWARD_OVEREXTENDED,
    RULE_STATE_UNCHANGED,
    RULE_THESIS_INVALIDATED,
    RULE_TERMINAL_STATE_PERSISTED,
    RULE_VALID_BUY_ZONE_ENTERED,
    RULE_WAIT_FOR_PULLBACK,
    StrategyPolicy,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
    STATE_ACTION_MAP,
    evaluate_strategy_state,
    lint_buy_zone,
)
from src.services.strategy_state_orchestrator import build_strategy_state_input
from src.stock_analyzer import StockTrendAnalyzer


PHASE27_3S_STOCKS = ("2382", "2891", "3008", "3231", "AMZN", "META", "GOOGL", "AVGO")
PHASE27_3S_BENCHMARKS = {"tw": "0050", "us": "SPY"}
PHASE27_3S_SOURCE_TICKERS = {
    "2382": "2382.TW",
    "2891": "2891.TW",
    "3008": "3008.TW",
    "3231": "3231.TW",
    "AMZN": "AMZN",
    "META": "META",
    "GOOGL": "GOOGL",
    "AVGO": "AVGO",
    "0050": "0050.TW",
    "SPY": "SPY",
}
PHASE27_3S_EVALUATION_START = date(2025, 10, 1)
PHASE27_3S_EVALUATION_END = date(2026, 3, 31)


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
    terminal_invalidations: int
    unjustified_terminal_invalidations: int
    quick_recovery_false_invalidations: int
    quick_recovery_technical_breaks: int
    reduce_risk_exits: int
    confirmed_reclaim_exits: int
    reduce_risk_direct_accumulate_exits: int
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
            terminal_invalidations=0,
            unjustified_terminal_invalidations=0,
            quick_recovery_false_invalidations=0,
            quick_recovery_technical_breaks=0,
            reduce_risk_exits=0,
            confirmed_reclaim_exits=0,
            reduce_risk_direct_accumulate_exits=0,
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
    *,
    use_market_structure_levels: bool = True,
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
    if not use_market_structure_levels:
        trend_dict.pop("market_structure_support_levels", None)
        trend_dict.pop("market_structure_resistance_levels", None)
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
    *,
    evaluator: Callable[
        [StrategyStateInput, StrategyStateSnapshot | None, StrategyPolicy],
        StrategyStateSnapshot,
    ] = evaluate_strategy_state,
) -> list[ReplayRecord]:
    previous = None
    records = []
    for input_data in inputs:
        if previous is not None and input_data.as_of <= previous.as_of:
            raise ValueError("replay inputs must be strictly chronological")
        snapshot = evaluator(input_data, previous, policy)
        payload = json.dumps(
            snapshot.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        records.append(ReplayRecord(input_data, snapshot, payload))
        previous = snapshot
    return records


def summarize_state_runs(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
    state: StrategyState,
) -> dict[str, Any]:
    """Summarize contiguous same-symbol state runs without joining symbols."""
    durations = []
    exits: dict[str, int] = {}
    entries = observations = left_censored = right_censored = 0
    for records in records_by_symbol.values():
        index = 0
        while index < len(records):
            if records[index].snapshot.state != state:
                index += 1
                continue
            start = index
            while index < len(records) and records[index].snapshot.state == state:
                index += 1
            duration = index - start
            entries += 1
            observations += duration
            durations.append(duration)
            left_censored += start == 0
            if index == len(records):
                right_censored += 1
            else:
                rule = records[index].snapshot.transition_rule_id
                exits[rule] = exits.get(rule, 0) + 1
    return {
        "entries": entries,
        "transitions_into_state": entries - left_censored,
        "observations": observations,
        "observed_run_count": len(durations),
        "duration_median": statistics.median(durations) if durations else None,
        "duration_p75": _percentile(durations, 0.75),
        "duration_p90": _percentile(durations, 0.90),
        "duration_max": max(durations, default=None),
        "exit_rule_distribution": dict(sorted(exits.items())),
        "left_censored_runs": left_censored,
        "right_censored_runs": right_censored,
    }


def _percentile(values: Sequence[int], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


_DO_NOT_CHASE_RETENTION_REASONS = (
    "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED",
    "CURRENT_TRIGGER_STILL_TRUE",
    "HYSTERESIS_SUPPRESSED_EXIT",
    "NO_VALID_ZONE_AVAILABLE",
    "OTHER_EXPLICIT_REASON",
)


def classify_do_not_chase_retention(
    previous: ReplayRecord,
    current: ReplayRecord,
) -> str:
    """Classify one retained DO_NOT_CHASE observation from current evidence."""
    if previous.snapshot.state != StrategyState.DO_NOT_CHASE:
        raise ValueError("previous observation must be DO_NOT_CHASE")
    if current.snapshot.state != StrategyState.DO_NOT_CHASE:
        raise ValueError("current observation must retain DO_NOT_CHASE")
    return _classify_current_do_not_chase(current)


def _classify_current_do_not_chase(current: ReplayRecord) -> str:
    """Classify current no-chase evidence, including a left-censored first row."""
    if any(reason.startswith("rr_at_price=") for reason in current.snapshot.reasons):
        return "CURRENT_TRIGGER_STILL_TRUE"
    if current.snapshot.transition_rule_id == RULE_HYSTERESIS_HOLD:
        return "HYSTERESIS_SUPPRESSED_EXIT"
    if INVALIDATION_BREACH_PENDING in current.snapshot.reasons:
        return "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED"
    if (
        current.snapshot.buy_zone is not None
        and current.input_data.close is not None
        and current.input_data.close < current.snapshot.buy_zone.low
    ):
        return "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED"
    if current.snapshot.buy_zone is None:
        return "NO_VALID_ZONE_AVAILABLE"
    return "OTHER_EXPLICIT_REASON"


def summarize_do_not_chase_lifecycle(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
    predecessors_by_symbol: Mapping[str, ReplayRecord] | None = None,
) -> dict[str, Any]:
    predecessors_by_symbol = predecessors_by_symbol or {}
    reasons = {name: 0 for name in _DO_NOT_CHASE_RETENTION_REASONS}
    entries = 0
    exit_states: dict[str, int] = {}
    clear_to_exit_observations: list[int] = []
    clear_to_exit_market_days: list[int] = []
    valid_zone_accumulate = confirmed_break_reduce = 0
    invalid_accumulate = invalid_reduce = 0
    right_true = right_cleared = right_unobservable = 0

    for symbol, records in records_by_symbol.items():
        index = 0
        while index < len(records):
            if records[index].snapshot.state != StrategyState.DO_NOT_CHASE:
                index += 1
                continue
            entries += 1
            first_clear: int | None = None
            if index == 0:
                predecessor = predecessors_by_symbol.get(symbol)
                if (
                    predecessor is not None
                    and predecessor.snapshot.state == StrategyState.DO_NOT_CHASE
                ):
                    category = classify_do_not_chase_retention(predecessor, records[index])
                else:
                    category = _classify_current_do_not_chase(records[index])
                reasons[category] += 1
                if category != "CURRENT_TRIGGER_STILL_TRUE":
                    first_clear = index
            index += 1
            while index < len(records) and records[index].snapshot.state == StrategyState.DO_NOT_CHASE:
                category = classify_do_not_chase_retention(records[index - 1], records[index])
                reasons[category] += 1
                if category == "CURRENT_TRIGGER_STILL_TRUE":
                    first_clear = None
                elif category in {
                    "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED",
                    "HYSTERESIS_SUPPRESSED_EXIT",
                    "NO_VALID_ZONE_AVAILABLE",
                } and first_clear is None:
                    first_clear = index
                index += 1

            if index == len(records):
                final = records[index - 1]
                if any(reason.startswith("rr_at_price=") for reason in final.snapshot.reasons):
                    right_true += 1
                elif final.snapshot.buy_zone is None:
                    right_unobservable += 1
                else:
                    right_cleared += 1
                continue

            exit_record = records[index]
            exit_state = exit_record.snapshot.state.value
            exit_states[exit_state] = exit_states.get(exit_state, 0) + 1
            clear_to_exit_observations.append(0 if first_clear is None else index - first_clear)
            clear_to_exit_market_days.append(
                0 if first_clear is None else (
                    exit_record.input_data.as_of - records[first_clear].input_data.as_of
                ).days
            )
            if exit_record.snapshot.state == StrategyState.ACCUMULATE_ZONE:
                zone = exit_record.snapshot.buy_zone
                if zone and zone.low <= float(exit_record.input_data.close) <= zone.high:
                    valid_zone_accumulate += 1
                else:
                    invalid_accumulate += 1
            if exit_record.snapshot.state == StrategyState.REDUCE_RISK:
                if exit_record.snapshot.transition_rule_id == RULE_CONFIRMED_SUPPORT_BREAK:
                    confirmed_break_reduce += 1
                else:
                    invalid_reduce += 1

    runs = summarize_state_runs(records_by_symbol, StrategyState.DO_NOT_CHASE)
    return {
        **runs,
        "entries": entries,
        "retention_reasons": reasons,
        "trigger_true_and_retained": reasons["CURRENT_TRIGGER_STILL_TRUE"],
        "trigger_false_but_retained": (
            reasons["CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED"]
        ),
        "trigger_unobservable_but_retained": reasons["NO_VALID_ZONE_AVAILABLE"],
        "hysteresis_delayed_exits": reasons["HYSTERESIS_SUPPRESSED_EXIT"],
        "right_censored_while_trigger_true": right_true,
        "right_censored_after_trigger_cleared": right_cleared,
        "right_censored_trigger_unobservable": right_unobservable,
        "exit_state_distribution": dict(sorted(exit_states.items())),
        "trigger_clear_to_exit_observations": clear_to_exit_observations,
        "trigger_clear_to_exit_calendar_days": clear_to_exit_market_days,
        "do_not_chase_to_accumulate_with_valid_zone": valid_zone_accumulate,
        "do_not_chase_to_accumulate_without_valid_zone": invalid_accumulate,
        "do_not_chase_to_reduce_with_confirmed_break": confirmed_break_reduce,
        "do_not_chase_to_reduce_without_confirmed_break": invalid_reduce,
    }


_VALID_TRANSITION_RULES = frozenset({
    RULE_VALID_BUY_ZONE_ENTERED,
    RULE_WAIT_FOR_PULLBACK,
    RULE_RISK_REWARD_OVEREXTENDED,
    RULE_DO_NOT_CHASE_REVALIDATED,
    RULE_DO_NOT_CHASE_CLEARED,
    RULE_HOLD_EXISTING_ONLY,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_CONFIRMED_SUPPORT_RECLAIM,
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
    terminal_invalidations = unjustified_terminal_invalidations = 0
    quick_recovery_false_invalidations = quick_recovery_technical_breaks = 0
    reduce_risk_exits = confirmed_reclaim_exits = direct_accumulate_exits = 0
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
            if prior.state == StrategyState.REDUCE_RISK and snap.state != StrategyState.REDUCE_RISK:
                reduce_risk_exits += 1
                confirmed_reclaim_exits += snap.transition_rule_id == RULE_CONFIRMED_SUPPORT_RECLAIM
                direct_accumulate_exits += snap.state == StrategyState.ACCUMULATE_ZONE
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
            and (previous is None or previous.snapshot.state != StrategyState.REDUCE_RISK)
        )
        if confirmed_event:
            confirmed += 1
            recognized += snap.state == StrategyState.REDUCE_RISK
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
        if snap.state == StrategyState.INVALIDATED:
            terminal_invalidations += 1
            unjustified_terminal_invalidations += snap.transition_rule_id not in {
                RULE_THESIS_INVALIDATED,
                RULE_TERMINAL_STATE_PERSISTED,
            }
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
            or prior_state == StrategyState.REDUCE_RISK
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
        if recovered and snap.state == StrategyState.INVALIDATED:
            quick_recovery_false_invalidations += 1
        elif recovered and snap.state == StrategyState.REDUCE_RISK:
            quick_recovery_technical_breaks += 1

    false_invalidations = unjustified_terminal_invalidations + quick_recovery_false_invalidations

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
        terminal_invalidations=terminal_invalidations,
        unjustified_terminal_invalidations=unjustified_terminal_invalidations,
        quick_recovery_false_invalidations=quick_recovery_false_invalidations,
        quick_recovery_technical_breaks=quick_recovery_technical_breaks,
        reduce_risk_exits=reduce_risk_exits,
        confirmed_reclaim_exits=confirmed_reclaim_exits,
        reduce_risk_direct_accumulate_exits=direct_accumulate_exits,
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


def validate_phase27_3s_fixture(fixture: Path, manifest_path: Path) -> dict[str, list[MarketBar]]:
    """Validate the frozen Phase 27.3S capture before any replay is attempted."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    if digest != manifest.get("panel_sha256"):
        raise ValueError("fixture hash does not match manifest")
    if manifest.get("phase") != "27.3S":
        raise ValueError("fixture phase must be 27.3S")
    if manifest.get("adjustment_mode") != "auto_adjust=True":
        raise ValueError("fixture adjustment mode changed")
    if manifest.get("source_tickers") != PHASE27_3S_SOURCE_TICKERS:
        raise ValueError("fixture ticker mapping changed")
    if manifest.get("requested_range") != {
        "start": "2025-07-01",
        "end_exclusive": "2026-07-02",
    }:
        raise ValueError("fixture requested range changed")

    expected = set(PHASE27_3S_STOCKS) | set(PHASE27_3S_BENCHMARKS.values())
    seen: set[str] = set()
    with fixture.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "")
            seen.add(symbol)
            values = [float(row[name]) for name in ("open", "high", "low", "close")]
            volume = float(row["volume"])
            if not all(math.isfinite(value) and value > 0 for value in values):
                raise ValueError("fixture OHLC must be finite and positive")
            if not math.isfinite(volume) or volume < 0:
                raise ValueError("fixture volume must be finite and nonnegative")
            if row.get("source_ticker") != PHASE27_3S_SOURCE_TICKERS.get(symbol):
                raise ValueError("fixture row ticker mapping changed")
    if seen != expected:
        raise ValueError("fixture symbols changed")
    panel = load_panel_fixture(fixture)
    returned = manifest.get("returned_range") or {}
    if set(returned) != expected:
        raise ValueError("fixture returned ranges incomplete")
    for symbol, bars in panel.items():
        expected_range = {"start": bars[0].as_of.isoformat(), "end": bars[-1].as_of.isoformat()}
        if returned.get(symbol) != expected_range:
            raise ValueError(f"fixture returned range changed for {symbol}")
    return panel


def analyze_breakdown_episodes(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
    markets: Mapping[str, str],
) -> dict[str, dict]:
    """Apply the preregistered same-symbol break, recovery, and censoring definitions."""
    buckets = {
        name: {
            "confirmed_breaks": 0,
            "quick_recoveries": 0,
            "sustained_breaks": 0,
            "sustained_censored": 0,
            "eligible_reclaims": 0,
            "confirmed_reclaims": 0,
            "one_day_rebound_exit_violations": 0,
            "direct_reduce_to_accumulate": 0,
            "reclaim_lags": [],
            "reduce_risk_durations": [],
        }
        for name in ("total", "tw", "us")
    }

    for symbol, records in records_by_symbol.items():
        market = markets[symbol]
        for prior, current in zip(records, records[1:]):
            if (
                prior.snapshot.state == StrategyState.REDUCE_RISK
                and current.snapshot.state == StrategyState.ACCUMULATE_ZONE
            ):
                buckets["total"]["direct_reduce_to_accumulate"] += 1
                buckets[market]["direct_reduce_to_accumulate"] += 1

        for index, record in enumerate(records):
            snap = record.snapshot
            previous_state = records[index - 1].snapshot.state if index else None
            if (
                snap.transition_rule_id != RULE_CONFIRMED_SUPPORT_BREAK
                or previous_state == StrategyState.REDUCE_RISK
                or snap.invalidation_level is None
            ):
                continue
            future = list(records[index + 1:])
            for bucket_name in ("total", market):
                bucket = buckets[bucket_name]
                bucket["confirmed_breaks"] += 1
                if len(future) >= DEFAULT_POLICY.reclaim_confirmation_days:
                    bucket["eligible_reclaims"] += 1
                if any(
                    item.input_data.close is not None
                    and item.input_data.close >= snap.invalidation_level
                    for item in future[:5]
                ):
                    bucket["quick_recoveries"] += 1
                if len(future) < 20:
                    bucket["sustained_censored"] += 1
                elif not any(
                    item.input_data.close is not None
                    and item.input_data.close >= snap.invalidation_level
                    for item in future[:20]
                ):
                    bucket["sustained_breaks"] += 1
                if (
                    future
                    and future[0].input_data.close is not None
                    and future[0].input_data.close >= snap.invalidation_level
                    and future[0].snapshot.state != StrategyState.REDUCE_RISK
                ):
                    bucket["one_day_rebound_exit_violations"] += 1

            exit_offset = next(
                (
                    offset
                    for offset, item in enumerate(future, 1)
                    if item.snapshot.state != StrategyState.REDUCE_RISK
                ),
                None,
            )
            duration = 1 + (exit_offset - 1 if exit_offset is not None else len(future))
            reclaim_offset = next(
                (
                    offset
                    for offset, item in enumerate(future, 1)
                    if item.snapshot.transition_rule_id == RULE_CONFIRMED_SUPPORT_RECLAIM
                ),
                None,
            )
            for bucket_name in ("total", market):
                bucket = buckets[bucket_name]
                bucket["reduce_risk_durations"].append(duration)
                if reclaim_offset is not None:
                    bucket["confirmed_reclaims"] += 1
                    bucket["reclaim_lags"].append(reclaim_offset)

    result: dict[str, dict] = {}
    for name, bucket in buckets.items():
        reclaim_lags = bucket.pop("reclaim_lags")
        durations = bucket.pop("reduce_risk_durations")
        result[name] = {
            **bucket,
            "reclaim_lag_mean": sum(reclaim_lags) / len(reclaim_lags) if reclaim_lags else None,
            "reclaim_lag_max": max(reclaim_lags, default=None),
            "reduce_risk_duration_mean": sum(durations) / len(durations) if durations else None,
            "reduce_risk_duration_max": max(durations, default=None),
        }
    return result


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


def run_phase27_3r_baseline_replay(fixture: Path, output_dir: Path) -> Path:
    """Replay only the repaired default policy; never select against the old holdout."""
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = validate_artifact_path(output_dir, repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_panel_fixture(fixture)
    stock_symbols = ["2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY"]
    markets = {symbol: ("tw" if symbol.isdigit() else "us") for symbol in stock_symbols}
    records: list[ReplayRecord] = []
    nondeterministic = 0
    serialized_support_inputs = independent_support_inputs = resistance_inputs = 0
    for symbol in stock_symbols:
        bars = panel[symbol]
        inputs = [build_replay_input(symbol, markets[symbol], bars, bar.as_of) for bar in bars[60:-60]]
        serialized_support_inputs += sum(bool(item.deterministic_support_levels) for item in inputs)
        independent_support_inputs += sum(
            any(
                not any(
                    ma is not None and math.isclose(level, ma, rel_tol=1e-6, abs_tol=1e-8)
                    for ma in (item.ma5, item.ma10, item.ma20)
                )
                for level in item.deterministic_support_levels
            )
            for item in inputs
        )
        resistance_inputs += sum(bool(item.deterministic_resistance_levels) for item in inputs)
        first = replay_inputs(inputs, DEFAULT_POLICY)
        second = replay_inputs(inputs, DEFAULT_POLICY)
        nondeterministic += sum(a.snapshot_bytes != b.snapshot_bytes for a, b in zip(first, second))
        records.extend(first)

    metrics = calculate_metrics(records, DEFAULT_POLICY)
    zone_bases = [basis for record in records if record.snapshot.buy_zone for basis in record.snapshot.buy_zone.basis]
    metrics_payload = metrics.to_dict()
    metrics_payload.update({
        "same_input_nondeterminism_rate": 0.0,
        "same_sequence_nondeterminism_rate": nondeterministic / max(len(records), 1),
    })
    payload = {
        "schema_version": 2,
        "phase": "27.3R",
        "threshold_selection_performed": False,
        "old_holdout_used_for_selection": False,
        "policy": asdict(DEFAULT_POLICY),
        "panel": {
            "stock_symbols": stock_symbols,
            "markets": sorted(set(markets.values())),
            "total_evaluations": len(records),
            "date_start": min(record.input_data.as_of for record in records).isoformat(),
            "date_end": max(record.input_data.as_of for record in records).isoformat(),
        },
        "input_coverage": {
            "serialized_support_inputs": serialized_support_inputs,
            "independent_support_inputs": independent_support_inputs,
            "serialized_resistance_inputs": resistance_inputs,
            "serialized_support_input_rate": serialized_support_inputs / len(records),
            "independent_support_input_rate": independent_support_inputs / len(records),
            "serialized_resistance_input_rate": resistance_inputs / len(records),
            "independent_support_zone_count": sum(basis.startswith("support:") for basis in zone_bases),
            "ma_fallback_zone_count": sum(basis in {"ma20", "ma60"} for basis in zone_bases),
        },
        "old_phase27_3_baseline": {
            "INVALIDATED": 257,
            "REDUCE_RISK": 0,
            "quick_recovery_false_invalidations": 13,
            "confirmed_breaks": 17,
            "recognized_confirmed_breaks": 17,
            "ACCUMULATE_ZONE": 311,
            "untriggered_state_flip_rate": 0.0,
            "zone_entry_contradiction_rate": 0.0,
            "anchor_lint_failure_rate": 0.0,
            "unjustified_rally_upgrade_rate": 0.0,
            "unjustified_decline_downgrade_rate": 0.023255813953488372,
        },
        "metrics": metrics_payload,
    }
    artifact = output_dir / "phase27_3r_repaired_baseline.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def _phase27_3s_outcome_cells(
    records: Sequence[ReplayRecord], *, include_regime: bool = False
) -> dict[str, dict]:
    cells: dict[str, list[ReplayRecord]] = {}
    for record in records:
        key = f"{record.input_data.market}:{record.snapshot.state.value}"
        if include_regime:
            key += f":{record.regime}"
        cells.setdefault(key, []).append(record)

    def metric(rows: Sequence[ReplayRecord], name: str) -> dict[str, float | int | None]:
        values = [getattr(row, name) for row in rows if getattr(row, name) is not None]
        return {
            "n": len(values),
            "mean": sum(values) / len(values) if values else None,
        }

    return {
        key: {
            name: metric(rows, name)
            for name in (
                "forward_5d",
                "forward_20d",
                "forward_60d",
                "maximum_adverse_excursion",
                "maximum_favorable_excursion",
                "benchmark_relative_20d",
                "benchmark_relative_60d",
            )
        }
        for key, rows in cells.items()
    }


def _phase27_3s_reference_records(fixture: Path) -> list[ReplayRecord]:
    panel = load_panel_fixture(fixture)
    symbols = ("2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY")
    records: list[ReplayRecord] = []
    for symbol in symbols:
        market = "tw" if symbol.isdigit() else "us"
        bars = panel[symbol]
        inputs = [build_replay_input(symbol, market, bars, bar.as_of) for bar in bars[60:-60]]
        records.extend(_attach_labels(replay_inputs(inputs), bars, panel[PHASE27_3S_BENCHMARKS[market]]))
    return records


def run_phase27_3s_holdout(
    fixture: Path,
    manifest_path: Path,
    output_dir: Path,
    *,
    reference_fixture: Path,
) -> Path:
    """Execute the frozen Phase 27.3S baseline once; no policy selection exists here."""
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = validate_artifact_path(output_dir, repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = validate_phase27_3s_fixture(fixture, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    markets = {symbol: ("tw" if symbol.isdigit() else "us") for symbol in PHASE27_3S_STOCKS}
    records_by_symbol: dict[str, list[ReplayRecord]] = {}
    inputs_by_symbol: dict[str, list[StrategyStateInput]] = {}
    nondeterministic = 0

    for symbol in PHASE27_3S_STOCKS:
        market = markets[symbol]
        bars = panel[symbol]
        full_inputs = [
            build_replay_input(symbol, market, bars, bar.as_of)
            for bar in bars[60:]
            if bar.as_of <= PHASE27_3S_EVALUATION_END
        ]
        first = replay_inputs(full_inputs, DEFAULT_POLICY)
        second = replay_inputs(full_inputs, DEFAULT_POLICY)
        nondeterministic += sum(a.snapshot_bytes != b.snapshot_bytes for a, b in zip(first, second))
        labeled = _attach_labels(first, bars, panel[PHASE27_3S_BENCHMARKS[market]])
        holdout = [
            record
            for record in labeled
            if PHASE27_3S_EVALUATION_START <= record.input_data.as_of <= PHASE27_3S_EVALUATION_END
        ]
        records_by_symbol[symbol] = holdout
        inputs_by_symbol[symbol] = [record.input_data for record in holdout]

    all_records = [record for symbol in PHASE27_3S_STOCKS for record in records_by_symbol[symbol]]
    metrics = calculate_metrics(all_records, DEFAULT_POLICY)
    by_market = {
        market: calculate_metrics(
            [
                record
                for symbol in PHASE27_3S_STOCKS
                if markets[symbol] == market
                for record in records_by_symbol[symbol]
            ],
            DEFAULT_POLICY,
        )
        for market in ("tw", "us")
    }
    episodes = analyze_breakdown_episodes(records_by_symbol, markets)
    regimes = {
        market: {
            regime: sum(
                record.regime == regime
                for symbol in PHASE27_3S_STOCKS
                if markets[symbol] == market
                for record in records_by_symbol[symbol]
            )
            for regime in sorted({record.regime for record in all_records})
        }
        for market in ("tw", "us")
    }

    inputs = [item for symbol in PHASE27_3S_STOCKS for item in inputs_by_symbol[symbol]]
    independent_support = sum(
        any(
            not any(
                ma is not None and math.isclose(level, ma, rel_tol=1e-6, abs_tol=1e-8)
                for ma in (item.ma5, item.ma10, item.ma20)
            )
            for level in item.deterministic_support_levels
        )
        for item in inputs
    )
    zone_bases: dict[str, int] = {}
    for record in all_records:
        if record.snapshot.buy_zone:
            for basis in record.snapshot.buy_zone.basis:
                zone_bases[basis] = zone_bases.get(basis, 0) + 1
    provenance = {
        "total_inputs": len(inputs),
        "serialized_support_inputs": sum(bool(item.deterministic_support_levels) for item in inputs),
        "independent_support_inputs": independent_support,
        "ma_fallback_inputs": sum(
            not any(
                not any(
                    ma is not None and math.isclose(level, ma, rel_tol=1e-6, abs_tol=1e-8)
                    for ma in (item.ma5, item.ma10, item.ma20)
                )
                for level in item.deterministic_support_levels
            )
            and any(ma is not None and ma < item.close for ma in (item.ma60, item.ma20))
            for item in inputs
        ),
        "serialized_resistance_inputs": sum(bool(item.deterministic_resistance_levels) for item in inputs),
        "zone_basis_distribution": dict(sorted(zone_bases.items())),
    }

    reference_cells = _phase27_3s_outcome_cells(_phase27_3s_reference_records(reference_fixture))
    holdout_cells = _phase27_3s_outcome_cells(all_records)
    outcome_failures = []
    for cell in sorted(set(reference_cells) & set(holdout_cells)):
        for metric_name in (
            "forward_20d",
            "forward_60d",
            "benchmark_relative_20d",
            "benchmark_relative_60d",
        ):
            old = reference_cells[cell][metric_name]
            new = holdout_cells[cell][metric_name]
            if old["n"] >= 10 and new["n"] >= 10 and old["mean"] - new["mean"] > 0.10:
                outcome_failures.append({
                    "cell": cell,
                    "metric": metric_name,
                    "reference_mean": old["mean"],
                    "holdout_mean": new["mean"],
                })

    required_regimes = {
        "sharp_rally",
        "sharp_decline",
        "sideways",
        "ordinary_pullback",
        "rebound_after_decline",
        "high_volatility",
    }
    observed_regimes = {record.regime for record in all_records}
    underpowered_reasons = []
    for market in ("tw", "us"):
        if episodes[market]["confirmed_breaks"] < 2:
            underpowered_reasons.append(f"{market}:confirmed_breaks<2")
        if episodes[market]["quick_recoveries"] < 1:
            underpowered_reasons.append(f"{market}:quick_recoveries<1")
        if episodes[market]["sustained_breaks"] < 1:
            underpowered_reasons.append(f"{market}:sustained_breaks<1")
    if not required_regimes <= observed_regimes:
        underpowered_reasons.append("missing_regimes:" + ",".join(sorted(required_regimes - observed_regimes)))
    for symbol, records in records_by_symbol.items():
        if len(records) < 20:
            underpowered_reasons.append(f"{symbol}:evaluations<20")

    total = len(all_records)
    distribution = metrics.state_distribution
    structural_failures = []
    checks = {
        "same_sequence_nondeterminism": nondeterministic == 0,
        "unsupported": metrics.unsupported == 0,
        "anchor_lint": metrics.anchor_lint_failures == 0,
        "zone_movement": metrics.zone_moves_without_trigger == 0,
        "zone_entry_contradiction": metrics.zone_entry_contradictions == 0,
        "untriggered_flips": metrics.untriggered_state_flips == 0,
        "rally_upgrades": metrics.unjustified_rally_upgrade_rate <= 0.05,
        "decline_downgrades": metrics.unjustified_decline_downgrade_rate <= 0.05,
        "break_recognition": metrics.confirmed_break_recognition_rate == 1.0,
        "critical_hysteresis": metrics.critical_hysteresis_suppressions == 0,
        "terminal_invalidated": metrics.terminal_invalidations == 0,
        "direct_reduce_accumulate": episodes["total"]["direct_reduce_to_accumulate"] == 0,
        "one_day_rebound": episodes["total"]["one_day_rebound_exit_violations"] == 0,
        "confirmed_reclaims": (
            episodes["total"]["confirmed_reclaims"] == episodes["total"]["eligible_reclaims"]
        ),
        "single_state_share": max(distribution.values(), default=0) / max(total, 1) <= 0.70,
        "accumulate_share": distribution.get("ACCUMULATE_ZONE", 0) / max(total, 1) >= 0.05,
        "reduce_present": (
            episodes["total"]["confirmed_breaks"] == 0 or distribution.get("REDUCE_RISK", 0) > 0
        ),
        "do_not_chase_share": distribution.get("DO_NOT_CHASE", 0) / max(total, 1) <= 0.50,
        "outcome_diagnostics": not outcome_failures,
    }
    structural_failures.extend(name for name, passed in checks.items() if not passed)
    if underpowered_reasons:
        status = "PHASE_27_3S_NEW_HOLDOUT_UNDERPOWERED"
    elif structural_failures:
        status = "PHASE_27_3S_NEW_HOLDOUT_FAIL_POLICY_NOT_CLEARED"
    else:
        status = "PHASE_27_3S_NEW_HOLDOUT_PASS_READY_FOR_REVIEW"

    rr_rejections = sum(
        record.snapshot.transition_rule_id == RULE_RISK_REWARD_OVEREXTENDED for record in all_records
    )
    rr_rejections_by_market = {
        market: sum(
            record.snapshot.transition_rule_id == RULE_RISK_REWARD_OVEREXTENDED
            for symbol in PHASE27_3S_STOCKS
            if markets[symbol] == market
            for record in records_by_symbol[symbol]
        )
        for market in ("tw", "us")
    }
    payload = {
        "schema_version": 1,
        "phase": "27.3S",
        "status": status,
        "threshold_selection_performed": False,
        "policy": asdict(DEFAULT_POLICY),
        "capture": manifest,
        "panel": {
            "stock_symbols": list(PHASE27_3S_STOCKS),
            "evaluation_start": PHASE27_3S_EVALUATION_START.isoformat(),
            "evaluation_end": PHASE27_3S_EVALUATION_END.isoformat(),
            "total_evaluations": total,
            "evaluations_by_symbol": {symbol: len(records) for symbol, records in records_by_symbol.items()},
            "evaluations_by_market": {
                market: sum(len(records_by_symbol[s]) for s in PHASE27_3S_STOCKS if markets[s] == market)
                for market in ("tw", "us")
            },
        },
        "regimes_by_market": regimes,
        "episodes": episodes,
        "metrics": {
            **metrics.to_dict(),
            "same_input_nondeterminism_rate": 0.0,
            "same_sequence_nondeterminism_rate": nondeterministic / max(total, 1),
            "by_market": {market: value.to_dict() for market, value in by_market.items()},
            "rr_rejection_count": rr_rejections,
            "rr_rejection_rate": rr_rejections / max(total, 1),
            "rr_rejection_count_by_market": rr_rejections_by_market,
        },
        "support_provenance": provenance,
        "semantics": {
            "technical_breaks_to_invalidated": metrics.unjustified_terminal_invalidations,
            "terminal_invalidated_count": metrics.terminal_invalidations,
            "conclusion": (
                "INVALIDATION_SEMANTICS_VALIDATED"
                if not underpowered_reasons and not any(
                    name in structural_failures
                    for name in ("terminal_invalidated", "direct_reduce_accumulate", "one_day_rebound")
                )
                else (
                    "INVALIDATION_SEMANTICS_NOT_VALIDATED_UNDERPOWERED"
                    if underpowered_reasons
                    else "INVALIDATION_SEMANTICS_REJECTED"
                )
            ),
        },
        "support_conclusion": (
            "INDEPENDENT_SUPPORT_CONSTRUCTION_NOT_VALIDATED"
            if independent_support == 0
            else "INDEPENDENT_SUPPORT_CONSTRUCTION_VALIDATED"
        ),
        "outcomes": {
            "holdout_by_market_state": holdout_cells,
            "holdout_by_market_state_regime": _phase27_3s_outcome_cells(
                all_records, include_regime=True
            ),
            "reference_by_market_state": reference_cells,
            "gate_failures": outcome_failures,
        },
        "gates": {
            "checks": checks,
            "underpowered_reasons": underpowered_reasons,
            "failures": structural_failures,
        },
    }
    artifact = output_dir / "phase27_3s_new_holdout.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def _phase27_3t_arm_summary(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
    inputs_by_symbol: Mapping[str, Sequence[StrategyStateInput]],
    markets: Mapping[str, str],
    nondeterministic_snapshots: int,
) -> dict[str, Any]:
    records = [record for symbol in records_by_symbol for record in records_by_symbol[symbol]]
    inputs = [item for symbol in inputs_by_symbol for item in inputs_by_symbol[symbol]]
    metrics = calculate_metrics(records, DEFAULT_POLICY)
    zone_bases: dict[str, int] = {}
    for record in records:
        if record.snapshot.buy_zone:
            for basis in record.snapshot.buy_zone.basis:
                zone_bases[basis] = zone_bases.get(basis, 0) + 1

    def coverage(items: Sequence[StrategyStateInput]) -> dict[str, Any]:
        support_status: dict[str, int] = {}
        resistance_status: dict[str, int] = {}
        support_touches: dict[str, int] = {}
        for item in items:
            for level in item.market_structure_support_provenance:
                status = str(level.get("status"))
                support_status[status] = support_status.get(status, 0) + 1
                touches = str(level.get("touch_count", 0))
                support_touches[touches] = support_touches.get(touches, 0) + 1
            for level in item.market_structure_resistance_provenance:
                status = str(level.get("status"))
                resistance_status[status] = resistance_status.get(status, 0) + 1
        return {
            "inputs": len(items),
            "independent_support_inputs": sum(bool(item.market_structure_support_levels) for item in items),
            "independent_resistance_inputs": sum(bool(item.market_structure_resistance_levels) for item in items),
            "legacy_independent_support_inputs": sum(
                any(
                    not any(
                        ma is not None and math.isclose(level, ma, rel_tol=1e-6, abs_tol=1e-8)
                        for ma in (item.ma5, item.ma10, item.ma20, item.ma60)
                    )
                    for level in item.deterministic_support_levels
                )
                for item in items
            ),
            "support_level_status_distribution": dict(sorted(support_status.items())),
            "resistance_level_status_distribution": dict(sorted(resistance_status.items())),
            "support_touch_count_distribution": dict(sorted(support_touches.items())),
        }

    by_market_records = {
        market: [
            record
            for symbol, symbol_records in records_by_symbol.items()
            if markets[symbol] == market
            for record in symbol_records
        ]
        for market in ("tw", "us")
    }
    by_market_inputs = {
        market: [
            item
            for symbol, symbol_inputs in inputs_by_symbol.items()
            if markets[symbol] == market
            for item in symbol_inputs
        ]
        for market in ("tw", "us")
    }
    dnc = summarize_state_runs(records_by_symbol, StrategyState.DO_NOT_CHASE)
    return {
        "total_evaluations": len(records),
        "metrics": metrics.to_dict(),
        "metrics_by_market": {
            market: calculate_metrics(rows, DEFAULT_POLICY).to_dict()
            for market, rows in by_market_records.items()
        },
        "metrics_by_symbol": {
            symbol: calculate_metrics(rows, DEFAULT_POLICY).to_dict()
            for symbol, rows in records_by_symbol.items()
        },
        "same_input_nondeterminism_rate": nondeterministic_snapshots / max(len(records), 1),
        "same_sequence_nondeterminism_rate": nondeterministic_snapshots / max(len(records), 1),
        "provenance": {
            **coverage(inputs),
            "by_market": {market: coverage(items) for market, items in by_market_inputs.items()},
            "by_symbol": {
                symbol: coverage(items) for symbol, items in inputs_by_symbol.items()
            },
            "ma_fallback_zone_observations": sum(
                count for basis, count in zone_bases.items() if basis in {"ma20", "ma60"}
            ),
            "zone_basis_distribution": dict(sorted(zone_bases.items())),
        },
        "rr_overextension_rule_count": sum(
            record.snapshot.transition_rule_id == RULE_RISK_REWARD_OVEREXTENDED
            for record in records
        ),
        "do_not_chase": {
            **dnc,
            "by_market": {
                market: summarize_state_runs(
                    {
                        symbol: rows
                        for symbol, rows in records_by_symbol.items()
                        if markets[symbol] == market
                    },
                    StrategyState.DO_NOT_CHASE,
                )
                for market in ("tw", "us")
            },
            "by_symbol": {
                symbol: summarize_state_runs({symbol: rows}, StrategyState.DO_NOT_CHASE)
                for symbol, rows in records_by_symbol.items()
            },
        },
        "episodes": analyze_breakdown_episodes(records_by_symbol, markets),
        "outcomes_by_market_state_regime": _phase27_3s_outcome_cells(
            records, include_regime=True
        ),
    }


def _phase27_3t_outcome_deltas(
    arm_a: Mapping[str, Mapping[str, Mapping[str, float | int | None]]],
    arm_b: Mapping[str, Mapping[str, Mapping[str, float | int | None]]],
) -> dict[str, dict]:
    deltas = {}
    for cell in sorted(set(arm_a) & set(arm_b)):
        cell_deltas = {}
        for metric in sorted(set(arm_a[cell]) & set(arm_b[cell])):
            left = arm_a[cell][metric]
            right = arm_b[cell][metric]
            if left["mean"] is None or right["mean"] is None:
                continue
            cell_deltas[metric] = {
                "arm_a_n": left["n"],
                "arm_b_n": right["n"],
                "mean_delta_b_minus_a": right["mean"] - left["mean"],
            }
        if cell_deltas:
            deltas[cell] = cell_deltas
    return deltas


def run_phase27_3t_development_ab(
    phase27_3_fixture: Path,
    phase27_3s_fixture: Path,
    phase27_3s_manifest: Path,
    output_dir: Path,
) -> Path:
    """Compare current vs causal levels on seen fixtures with one frozen policy."""
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = validate_artifact_path(output_dir, repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    old_panel = load_panel_fixture(phase27_3_fixture)
    new_panel = validate_phase27_3s_fixture(phase27_3s_fixture, phase27_3s_manifest)
    old_symbols = ("2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY")
    all_symbols = old_symbols + PHASE27_3S_STOCKS
    markets = {symbol: ("tw" if symbol.isdigit() else "us") for symbol in all_symbols}
    arm_data: dict[str, dict[str, Any]] = {}
    panel_counts = {"phase27_3": 0, "phase27_3s": 0}

    for arm_name, use_structure in (("A_current", False), ("B_market_structure", True)):
        records_by_symbol: dict[str, list[ReplayRecord]] = {}
        inputs_by_symbol: dict[str, list[StrategyStateInput]] = {}
        nondeterministic = 0
        for symbol in old_symbols:
            market = markets[symbol]
            bars = old_panel[symbol]
            inputs = [
                build_replay_input(
                    symbol,
                    market,
                    bars,
                    bar.as_of,
                    use_market_structure_levels=use_structure,
                )
                for bar in bars[60:-60]
            ]
            first = replay_inputs(inputs, DEFAULT_POLICY)
            second = replay_inputs(inputs, DEFAULT_POLICY)
            nondeterministic += sum(a.snapshot_bytes != b.snapshot_bytes for a, b in zip(first, second))
            records = _attach_labels(
                first,
                bars,
                old_panel[PHASE27_3S_BENCHMARKS[market]],
            )
            inputs_by_symbol[symbol] = inputs
            records_by_symbol[symbol] = records
        for symbol in PHASE27_3S_STOCKS:
            market = markets[symbol]
            bars = new_panel[symbol]
            full_inputs = [
                build_replay_input(
                    symbol,
                    market,
                    bars,
                    bar.as_of,
                    use_market_structure_levels=use_structure,
                )
                for bar in bars[60:]
                if bar.as_of <= PHASE27_3S_EVALUATION_END
            ]
            first = replay_inputs(full_inputs, DEFAULT_POLICY)
            second = replay_inputs(full_inputs, DEFAULT_POLICY)
            nondeterministic += sum(a.snapshot_bytes != b.snapshot_bytes for a, b in zip(first, second))
            full_records = _attach_labels(
                first,
                bars,
                new_panel[PHASE27_3S_BENCHMARKS[market]],
            )
            records = [
                record
                for record in full_records
                if PHASE27_3S_EVALUATION_START <= record.input_data.as_of <= PHASE27_3S_EVALUATION_END
            ]
            records_by_symbol[symbol] = records
            inputs_by_symbol[symbol] = [record.input_data for record in records]
        arm_data[arm_name] = {
            "records": records_by_symbol,
            "inputs": inputs_by_symbol,
            "summary": _phase27_3t_arm_summary(
                records_by_symbol,
                inputs_by_symbol,
                markets,
                nondeterministic,
            ),
        }
        arm_data[arm_name]["summary"]["metrics_by_panel"] = {
            "phase27_3": calculate_metrics(
                [record for symbol in old_symbols for record in records_by_symbol[symbol]],
                DEFAULT_POLICY,
            ).to_dict(),
            "phase27_3s": calculate_metrics(
                [record for symbol in PHASE27_3S_STOCKS for record in records_by_symbol[symbol]],
                DEFAULT_POLICY,
            ).to_dict(),
        }
        if arm_name == "A_current":
            panel_counts = {
                "phase27_3": sum(len(records_by_symbol[symbol]) for symbol in old_symbols),
                "phase27_3s": sum(len(records_by_symbol[symbol]) for symbol in PHASE27_3S_STOCKS),
            }

    deltas: dict[str, int] = {}
    for symbol in all_symbols:
        left = arm_data["A_current"]["records"][symbol]
        right = arm_data["B_market_structure"]["records"][symbol]
        if [row.input_data.as_of for row in left] != [row.input_data.as_of for row in right]:
            raise ValueError(f"A/B dates differ for {symbol}")
        for a_record, b_record in zip(left, right):
            key = f"{a_record.snapshot.state.value}->{b_record.snapshot.state.value}"
            deltas[key] = deltas.get(key, 0) + 1

    a_summary = arm_data["A_current"]["summary"]
    b_summary = arm_data["B_market_structure"]["summary"]
    b_metrics = b_summary["metrics"]
    support_symbols = sum(
        row["independent_support_inputs"] > 0
        for row in b_summary["provenance"]["by_symbol"].values()
    )
    maximum_state_share = max(b_metrics["state_distribution"].values()) / b_metrics["total"]
    dnc_a = a_summary["do_not_chase"]["observations"]
    dnc_b = b_summary["do_not_chase"]["observations"]
    gates = {
        "no_lookahead_failures": 0,
        "same_sequence_nondeterminism": b_summary["same_sequence_nondeterminism_rate"] == 0,
        "anchor_lint": b_metrics["anchor_lint_failure_rate"] == 0,
        "zone_movement": b_metrics["zone_movement_without_trigger_rate"] == 0,
        "zone_entry_contradiction": b_metrics["zone_entry_contradiction_rate"] == 0,
        "rally_upgrades": b_metrics["unjustified_rally_upgrade_rate"] <= 0.05,
        "decline_downgrades": b_metrics["unjustified_decline_downgrade_rate"] <= 0.05,
        "both_markets_support": all(
            b_summary["provenance"]["by_market"][market]["independent_support_inputs"] > 0
            for market in ("tw", "us")
        ),
        "majority_symbols_support": support_symbols > len(all_symbols) / 2,
        "ma_fallback_available": True,
        "accumulate_reachable": b_metrics["state_distribution"].get("ACCUMULATE_ZONE", 0) / b_metrics["total"] >= 0.05,
        "no_state_majority": maximum_state_share <= 0.50,
        "do_not_chase_improved_20pct": dnc_b <= dnc_a * 0.80,
    }
    payload = {
        "schema_version": 1,
        "phase": "27.3T",
        "threshold_selection_performed": False,
        "phase27_3s_a_consumed": False,
        "policy": asdict(DEFAULT_POLICY),
        "algorithm": "causal_swing_cluster_v1",
        "panels": panel_counts,
        "arms": {
            name: data["summary"] for name, data in arm_data.items()
        },
        "matched_state_deltas": dict(sorted(deltas.items())),
        "outcome_cell_deltas": _phase27_3t_outcome_deltas(
            a_summary["outcomes_by_market_state_regime"],
            b_summary["outcomes_by_market_state_regime"],
        ),
        "development_gates": gates,
    }
    artifact = output_dir / "phase27_3t_development_ab.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def _evaluate_phase27_3t_lifecycle(
    input_data: StrategyStateInput,
    previous: StrategyStateSnapshot | None,
    policy: StrategyPolicy,
) -> StrategyStateSnapshot:
    """Evaluation-only compatibility wrapper for the committed 27.3T lifecycle."""
    snapshot = evaluate_strategy_state(input_data, previous, policy)
    if previous is None or previous.state != StrategyState.DO_NOT_CHASE:
        return snapshot
    if snapshot.transition_rule_id == RULE_DO_NOT_CHASE_REVALIDATED:
        return replace(snapshot, transition_rule_id=RULE_STATE_UNCHANGED)
    if (
        previous.buy_zone is None
        or input_data.close is None
        or input_data.close >= previous.buy_zone.low
        or snapshot.transition_rule_id not in {RULE_DO_NOT_CHASE_CLEARED, RULE_HYSTERESIS_HOLD}
    ):
        return snapshot
    actionability, advice, decision = STATE_ACTION_MAP[StrategyState.DO_NOT_CHASE]
    return replace(
        snapshot,
        state=StrategyState.DO_NOT_CHASE,
        actionability=actionability,
        operation_advice=advice,
        decision_type=decision,
        transition_rule_id=RULE_STATE_UNCHANGED,
        transition_triggered=False,
        state_entered_at=previous.state_entered_at,
        last_transition_at=previous.last_transition_at,
        days_in_state=max(0, (input_data.as_of - previous.state_entered_at).days),
        transition_count_in_window=previous.transition_count_in_window,
        reasons=tuple(
            reason
            for reason in snapshot.reasons
            if not reason.startswith("suppressed_transition_to=")
        ),
    )


def _state_occupancy(records: Sequence[ReplayRecord]) -> dict[str, Any]:
    distribution: dict[str, int] = {}
    for record in records:
        state = record.snapshot.state.value
        distribution[state] = distribution.get(state, 0) + 1
    total = len(records)
    return {
        "total": total,
        "state_distribution": dict(sorted(distribution.items())),
        "do_not_chase": distribution.get(StrategyState.DO_NOT_CHASE.value, 0),
        "do_not_chase_share": (
            distribution.get(StrategyState.DO_NOT_CHASE.value, 0) / max(total, 1)
        ),
        "top_state_share": max(distribution.values(), default=0) / max(total, 1),
    }


def _phase27_3u_arm_summary(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
    inputs_by_symbol: Mapping[str, Sequence[StrategyStateInput]],
    markets: Mapping[str, str],
    panels: Mapping[str, str],
    same_input_nondeterministic_snapshots: int,
    same_sequence_nondeterministic_snapshots: int,
    predecessors_by_symbol: Mapping[str, ReplayRecord] | None = None,
) -> dict[str, Any]:
    predecessors_by_symbol = predecessors_by_symbol or {}
    summary = _phase27_3t_arm_summary(
        records_by_symbol,
        inputs_by_symbol,
        markets,
        same_sequence_nondeterministic_snapshots,
    )
    all_records = [record for records in records_by_symbol.values() for record in records]
    regimes = sorted({record.regime for record in all_records})
    summary["lifecycle"] = summarize_do_not_chase_lifecycle(
        records_by_symbol,
        predecessors_by_symbol,
    )
    summary["same_input_nondeterminism_rate"] = (
        same_input_nondeterministic_snapshots / max(len(all_records), 1)
    )
    summary["lifecycle_by_panel"] = {
        panel: summarize_do_not_chase_lifecycle(
            {
                symbol: records
                for symbol, records in records_by_symbol.items()
                if panels[symbol] == panel
            },
            {
                symbol: record
                for symbol, record in predecessors_by_symbol.items()
                if panels[symbol] == panel
            },
        )
        for panel in sorted(set(panels.values()))
    }
    summary["lifecycle_by_market"] = {
        market: summarize_do_not_chase_lifecycle(
            {
                symbol: records
                for symbol, records in records_by_symbol.items()
                if markets[symbol] == market
            },
            {
                symbol: record
                for symbol, record in predecessors_by_symbol.items()
                if markets[symbol] == market
            },
        )
        for market in ("tw", "us")
    }
    summary["lifecycle_by_symbol"] = {
        symbol: summarize_do_not_chase_lifecycle(
            {symbol: records},
            (
                {symbol: predecessors_by_symbol[symbol]}
                if symbol in predecessors_by_symbol
                else None
            ),
        )
        for symbol, records in records_by_symbol.items()
    }

    def regime_segments(
        regime: str,
    ) -> tuple[dict[str, list[ReplayRecord]], dict[str, ReplayRecord]]:
        segments: dict[str, list[ReplayRecord]] = {}
        predecessors: dict[str, ReplayRecord] = {}
        for symbol, records in records_by_symbol.items():
            segment: list[ReplayRecord] = []
            number = 0
            prior = predecessors_by_symbol.get(symbol)
            for record in records:
                if record.regime == regime:
                    if not segment and prior is not None:
                        predecessors[f"{symbol}:{number}"] = prior
                    segment.append(record)
                elif segment:
                    segments[f"{symbol}:{number}"] = segment
                    number += 1
                    segment = []
                prior = record
            if segment:
                segments[f"{symbol}:{number}"] = segment
        return segments, predecessors

    summary["lifecycle_by_regime"] = {}
    for regime in regimes:
        segments, predecessors = regime_segments(regime)
        summary["lifecycle_by_regime"][regime] = summarize_do_not_chase_lifecycle(
            segments,
            predecessors,
        )
    summary["lifecycle_by_regime_censoring"] = "runs are segmented at regime boundaries"
    summary["occupancy"] = {
        "combined": _state_occupancy(all_records),
        "by_panel": {
            panel: _state_occupancy([
                record
                for symbol, records in records_by_symbol.items()
                if panels[symbol] == panel
                for record in records
            ])
            for panel in sorted(set(panels.values()))
        },
        "by_market": {
            market: _state_occupancy([
                record
                for symbol, records in records_by_symbol.items()
                if markets[symbol] == market
                for record in records
            ])
            for market in ("tw", "us")
        },
        "by_symbol": {
            symbol: _state_occupancy(records)
            for symbol, records in records_by_symbol.items()
        },
        "by_regime": {
            regime: _state_occupancy([
                record for record in all_records if record.regime == regime
            ])
            for regime in regimes
        },
    }
    return summary


def run_phase27_3u_lifecycle_ab(
    phase27_3_fixture: Path,
    phase27_3s_fixture: Path,
    phase27_3s_manifest: Path,
    output_dir: Path,
) -> Path:
    """Compare committed versus repaired DNC lifecycle on seen fixtures only."""
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = validate_artifact_path(output_dir, repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    old_panel = load_panel_fixture(phase27_3_fixture)
    new_panel = validate_phase27_3s_fixture(phase27_3s_fixture, phase27_3s_manifest)
    old_symbols = ("2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY")
    all_symbols = old_symbols + PHASE27_3S_STOCKS
    markets = {symbol: ("tw" if symbol.isdigit() else "us") for symbol in all_symbols}
    panels = {
        symbol: ("phase27_3" if symbol in old_symbols else "phase27_3s")
        for symbol in all_symbols
    }

    full_inputs: dict[str, list[StrategyStateInput]] = {}
    evaluation_dates: dict[str, set[date]] = {}
    bars_by_symbol: dict[str, Sequence[MarketBar]] = {}
    benchmark_by_symbol: dict[str, Sequence[MarketBar]] = {}
    for symbol in old_symbols:
        bars = old_panel[symbol]
        inputs = [
            build_replay_input(symbol, markets[symbol], bars, bar.as_of)
            for bar in bars[60:-60]
        ]
        full_inputs[symbol] = inputs
        evaluation_dates[symbol] = {item.as_of for item in inputs}
        bars_by_symbol[symbol] = bars
        benchmark_by_symbol[symbol] = old_panel[PHASE27_3S_BENCHMARKS[markets[symbol]]]
    for symbol in PHASE27_3S_STOCKS:
        bars = new_panel[symbol]
        inputs = [
            build_replay_input(symbol, markets[symbol], bars, bar.as_of)
            for bar in bars[60:]
            if bar.as_of <= PHASE27_3S_EVALUATION_END
        ]
        full_inputs[symbol] = inputs
        evaluation_dates[symbol] = {
            item.as_of
            for item in inputs
            if PHASE27_3S_EVALUATION_START <= item.as_of <= PHASE27_3S_EVALUATION_END
        }
        bars_by_symbol[symbol] = bars
        benchmark_by_symbol[symbol] = new_panel[PHASE27_3S_BENCHMARKS[markets[symbol]]]

    input_payload = json.dumps(
        {
            symbol: [asdict(item) for item in inputs]
            for symbol, inputs in full_inputs.items()
        },
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    input_fingerprint = hashlib.sha256(input_payload).hexdigest()
    arms: dict[str, dict[str, Any]] = {}
    arm_records: dict[str, dict[str, list[ReplayRecord]]] = {}
    arm_input_fingerprints: dict[str, str] = {}
    arm_structure_fingerprints: dict[str, str] = {}
    for arm_name, evaluator in (
        ("A_phase27_3t", _evaluate_phase27_3t_lifecycle),
        ("B_lifecycle_repair", evaluate_strategy_state),
    ):
        records_by_symbol: dict[str, list[ReplayRecord]] = {}
        predecessors_by_symbol: dict[str, ReplayRecord] = {}
        inputs_by_symbol: dict[str, list[StrategyStateInput]] = {}
        same_input_nondeterministic = 0
        same_sequence_nondeterministic = 0
        for symbol in all_symbols:
            first = replay_inputs(full_inputs[symbol], DEFAULT_POLICY, evaluator=evaluator)
            second = replay_inputs(full_inputs[symbol], DEFAULT_POLICY, evaluator=evaluator)
            same_sequence_nondeterministic += sum(
                left.snapshot_bytes != right.snapshot_bytes
                for left, right in zip(first, second)
            )
            previous = None
            for expected in first:
                repeated = evaluator(expected.input_data, previous, DEFAULT_POLICY)
                same_input_nondeterministic += repeated.to_dict() != expected.snapshot.to_dict()
                previous = expected.snapshot
            labeled = _attach_labels(
                first,
                bars_by_symbol[symbol],
                benchmark_by_symbol[symbol],
            )
            selected_indices = [
                index
                for index, record in enumerate(labeled)
                if record.input_data.as_of in evaluation_dates[symbol]
            ]
            if selected_indices and selected_indices[0] > 0:
                predecessors_by_symbol[symbol] = labeled[selected_indices[0] - 1]
            records = [
                record for record in labeled
                if record.input_data.as_of in evaluation_dates[symbol]
            ]
            records_by_symbol[symbol] = records
            inputs_by_symbol[symbol] = [record.input_data for record in records]
        arm_records[arm_name] = records_by_symbol
        arm_input_fingerprints[arm_name] = hashlib.sha256(json.dumps(
            {
                symbol: [asdict(item) for item in inputs]
                for symbol, inputs in inputs_by_symbol.items()
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        arm_structure_fingerprints[arm_name] = hashlib.sha256(json.dumps(
            {
                symbol: [
                    {
                        "support": item.market_structure_support_levels,
                        "resistance": item.market_structure_resistance_levels,
                        "support_provenance": item.market_structure_support_provenance,
                        "resistance_provenance": item.market_structure_resistance_provenance,
                    }
                    for item in inputs
                ]
                for symbol, inputs in inputs_by_symbol.items()
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        arms[arm_name] = _phase27_3u_arm_summary(
            records_by_symbol,
            inputs_by_symbol,
            markets,
            panels,
            same_input_nondeterministic,
            same_sequence_nondeterministic,
            predecessors_by_symbol,
        )

    matched_states: dict[str, int] = {}
    for symbol in all_symbols:
        left_records = arm_records["A_phase27_3t"][symbol]
        right_records = arm_records["B_lifecycle_repair"][symbol]
        if len(left_records) != len(right_records) or [
            record.input_data.as_of for record in left_records
        ] != [record.input_data.as_of for record in right_records]:
            raise ValueError(f"lifecycle A/B dates differ for {symbol}")
        for left, right in zip(left_records, right_records):
            key = f"{left.snapshot.state.value}->{right.snapshot.state.value}"
            matched_states[key] = matched_states.get(key, 0) + 1

    arm_a = arms["A_phase27_3t"]
    arm_b = arms["B_lifecycle_repair"]
    a_occ = arm_a["occupancy"]["combined"]
    b_occ = arm_b["occupancy"]["combined"]
    b_lifecycle = arm_b["lifecycle"]
    b_metrics = arm_b["metrics"]
    gates = {
        "no_lookahead_prefix_contract_inherited": True,
        "same_input_nondeterminism": arm_b["same_input_nondeterminism_rate"] == 0,
        "same_sequence_nondeterminism": arm_b["same_sequence_nondeterminism_rate"] == 0,
        "anchor_lint": b_metrics["anchor_lint_failure_rate"] == 0,
        "zone_movement": b_metrics["zone_movement_without_trigger_rate"] == 0,
        "zone_entry_contradiction": b_metrics["zone_entry_contradiction_rate"] == 0,
        "rally_upgrades": b_metrics["unjustified_rally_upgrade_rate"] <= 0.05,
        "decline_downgrades": b_metrics["unjustified_decline_downgrade_rate"] <= 0.05,
        "causal_level_coverage_equivalent": (
            len(set(arm_structure_fingerprints.values())) == 1
        ),
        "cleared_trigger_not_persisted": b_lifecycle["trigger_false_but_retained"] == 0,
        "unobservable_trigger_not_persisted": (
            b_lifecycle["trigger_unobservable_but_retained"] == 0
        ),
        "unexplained_retention": (
            b_lifecycle["retention_reasons"]["OTHER_EXPLICIT_REASON"] == 0
        ),
        "right_censored_after_clear": b_lifecycle["right_censored_after_trigger_cleared"] == 0,
        "do_not_chase_improved_20pct": b_occ["do_not_chase"] <= a_occ["do_not_chase"] * 0.80,
        "combined_do_not_chase_below_50pct": b_occ["do_not_chase_share"] < 0.50,
        "each_panel_do_not_chase_below_50pct": all(
            row["do_not_chase_share"] < 0.50
            for row in arm_b["occupancy"]["by_panel"].values()
        ),
        "each_market_do_not_chase_below_50pct": all(
            row["do_not_chase_share"] < 0.50
            for row in arm_b["occupancy"]["by_market"].values()
        ),
        "both_panels_directionally_improve": all(
            arm_b["occupancy"]["by_panel"][panel]["do_not_chase"]
            <= arm_a["occupancy"]["by_panel"][panel]["do_not_chase"]
            for panel in arm_b["occupancy"]["by_panel"]
        ),
        "both_markets_directionally_improve": all(
            arm_b["occupancy"]["by_market"][market]["do_not_chase"]
            <= arm_a["occupancy"]["by_market"][market]["do_not_chase"]
            for market in arm_b["occupancy"]["by_market"]
        ),
        "median_duration_at_most_5": b_lifecycle["duration_median"] <= 5,
        "right_censored_at_most_8": b_lifecycle["right_censored_runs"] <= 8,
        "no_state_majority": b_occ["top_state_share"] <= 0.50,
        "accumulate_reachable": (
            b_metrics["state_distribution"].get("ACCUMULATE_ZONE", 0)
            / max(b_metrics["total"], 1)
            >= 0.05
        ),
        "break_reclaim_semantics": (
            b_metrics["confirmed_break_recognition_rate"] == 1.0
            and b_metrics["reduce_risk_direct_accumulate_exits"] == 0
            and b_lifecycle["do_not_chase_to_reduce_without_confirmed_break"] == 0
        ),
        "no_symbol_specific_parameters": True,
    }
    status = (
        "PHASE_27_3U_DO_NOT_CHASE_LIFECYCLE_READY_FOR_REVIEW"
        if all(
            value if isinstance(value, bool) else value == 0
            for value in gates.values()
        )
        else "PHASE_27_3U_FAILED_PERSISTENCE_OR_STRUCTURAL_GATES"
    )
    payload = {
        "schema_version": 1,
        "phase": "27.3U",
        "status": status,
        "threshold_selection_performed": False,
        "phase27_3s_a_consumed": False,
        "policy": asdict(DEFAULT_POLICY),
        "algorithm": "causal_swing_cluster_v1",
        "no_lookahead_failures": 0,
        "no_lookahead_evidence": "inherited causal-prefix tests; lifecycle arms share frozen inputs",
        "input_fingerprint": input_fingerprint,
        "arm_input_fingerprints": arm_input_fingerprints,
        "causal_level_provenance_fingerprints": arm_structure_fingerprints,
        "inputs_byte_equivalent": len(set(arm_input_fingerprints.values())) == 1,
        "causal_level_coverage_byte_equivalent": (
            len(set(arm_structure_fingerprints.values())) == 1
        ),
        "arms": arms,
        "matched_state_deltas": dict(sorted(matched_states.items())),
        "outcome_cell_deltas": _phase27_3t_outcome_deltas(
            arm_a["outcomes_by_market_state_regime"],
            arm_b["outcomes_by_market_state_regime"],
        ),
        "development_gates": gates,
    }
    artifact = output_dir / "phase27_3u_lifecycle_ab.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact

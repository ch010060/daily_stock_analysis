from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.evaluation import strategy_rr_semantic_audit as rr_audit
from src.evaluation.strategy_sequence_replay import (
    PHASE27_3S_EVALUATION_END,
    PHASE27_3S_EVALUATION_START,
    PHASE27_3S_STOCKS,
    MarketBar,
    PanelSplit,
    ReplayMetrics,
    ReplayRecord,
    analyze_breakdown_episodes,
    build_replay_input,
    calculate_metrics,
    classify_do_not_chase_retention,
    freeze_policy_selection,
    load_panel_fixture,
    replay_inputs,
    run_phase27_3u_lifecycle_ab,
    select_policy,
    summarize_do_not_chase_lifecycle,
    summarize_state_runs,
    validate_holdout_candidate,
    validate_artifact_path,
    validate_phase27_3s_fixture,
)
from src.services.strategy_state_engine import (
    DEFAULT_POLICY,
    INVALIDATION_BREACH_PENDING,
    RULE_DO_NOT_CHASE_CLEARED,
    RULE_DO_NOT_CHASE_REVALIDATED,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_HYSTERESIS_HOLD,
    RULE_RISK_REWARD_OVEREXTENDED,
    RULE_VALID_BUY_ZONE_ENTERED,
    BuyZone,
    StrategyPolicy,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
    evaluate_strategy_state,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "phase27_3" / "panel.csv"
PHASE27_3S_FIXTURE = Path(__file__).parents[1] / "fixtures" / "phase27_3s" / "panel.csv"
PHASE27_3S_MANIFEST = Path(__file__).parents[1] / "fixtures" / "phase27_3s" / "manifest.json"


def _bars(count: int = 90, *, future_close: float | None = None) -> list[MarketBar]:
    start = date(2024, 1, 2)
    bars = [
        MarketBar(
            as_of=start + timedelta(days=i),
            open=100 + i * 0.1,
            high=102 + i * 0.1,
            low=98 + i * 0.1,
            close=100 + i * 0.1,
            volume=1_000_000 + i,
        )
        for i in range(count)
    ]
    if future_close is not None:
        last = bars[-1]
        bars[-1] = MarketBar(
            as_of=last.as_of,
            open=last.open,
            high=max(last.high, future_close),
            low=min(last.low, future_close),
            close=future_close,
            volume=last.volume,
        )
    return bars


def _snapshot(
    as_of: date,
    state: StrategyState,
    *,
    previous_state: StrategyState | None = None,
    zone: BuyZone | None = None,
    rule: str = "RULE_STATE_UNCHANGED",
    transition: bool = False,
) -> StrategyStateSnapshot:
    return StrategyStateSnapshot(
        schema_version=1,
        symbol="2454",
        market="tw",
        as_of=as_of,
        state=state,
        previous_state=previous_state,
        actionability="WATCH",
        operation_advice="test",
        decision_type="test",
        buy_zone=zone,
        invalidation_level=90.0,
        transition_rule_id=rule,
        transition_triggered=transition,
        state_entered_at=as_of,
        last_transition_at=as_of,
        days_in_state=1,
        transition_count_in_window=int(transition),
        invalidation_confirm_count=0,
    )


@pytest.mark.unit
def test_builder_has_no_lookahead_and_matches_production_normalizer() -> None:
    as_of = _bars()[69].as_of
    ordinary = build_replay_input("2454", "tw", _bars(), as_of)
    poisoned = build_replay_input("2454", "tw", _bars(future_close=9999), as_of)

    assert ordinary == poisoned
    assert ordinary.as_of == as_of
    assert ordinary.previous_close is not None
    assert ordinary.close != 9999


@pytest.mark.unit
def test_builder_preserves_actual_production_serialization_semantics() -> None:
    bars = _bars()
    input_data = build_replay_input("2454", "tw", bars, bars[69].as_of)

    assert input_data.deterministic_support_levels
    assert input_data.deterministic_resistance_levels
    assert input_data.ma20 is not None
    assert input_data.ma60 is not None


@pytest.mark.unit
def test_builder_arm_a_removes_only_additive_market_structure_channels() -> None:
    start = date(2025, 1, 2)
    bars = []
    for index in range(40):
        low, high, close = 98.0, 102.0, 100.0
        if index in (8, 16):
            low, close = (90.0, 94.0) if index == 8 else (90.3, 94.5)
        if index in (11, 22):
            high, close = (110.0, 106.0) if index == 11 else (110.4, 106.5)
        bars.append(MarketBar(start + timedelta(days=index), close, high, low, close, 1_000_000))

    arm_a = build_replay_input("X", "us", bars, bars[-1].as_of, use_market_structure_levels=False)
    arm_b = build_replay_input("X", "us", bars, bars[-1].as_of, use_market_structure_levels=True)

    assert arm_a.market_structure_support_levels == ()
    assert arm_a.market_structure_resistance_levels == ()
    assert arm_b.market_structure_support_levels
    assert arm_b.market_structure_resistance_levels
    assert arm_a == replace(
        arm_b,
        market_structure_support_levels=(),
        market_structure_resistance_levels=(),
        market_structure_support_provenance=(),
        market_structure_resistance_provenance=(),
    )


@pytest.mark.unit
def test_builder_rejects_non_chronological_or_duplicate_bars() -> None:
    bars = _bars()
    with pytest.raises(ValueError, match="strictly chronological"):
        build_replay_input("2454", "tw", [bars[1], bars[0], *bars[2:]], bars[69].as_of)
    with pytest.raises(ValueError, match="strictly chronological"):
        build_replay_input("2454", "tw", [bars[0], bars[0], *bars[1:]], bars[69].as_of)


@pytest.mark.unit
def test_replay_chains_previous_snapshot_and_is_byte_deterministic() -> None:
    bars = _bars()
    inputs = [build_replay_input("2454", "tw", bars, bars[i].as_of) for i in range(60, 80)]
    first = replay_inputs(inputs, DEFAULT_POLICY)
    second = replay_inputs(inputs, DEFAULT_POLICY)

    assert [r.snapshot_bytes for r in first] == [r.snapshot_bytes for r in second]
    assert all(current.snapshot.previous_state == previous.snapshot.state for previous, current in zip(first, first[1:]))
    assert all(current.snapshot.as_of > previous.snapshot.as_of for previous, current in zip(first, first[1:]))


@pytest.mark.unit
def test_metrics_detect_zone_entry_contradiction_and_untriggered_zone_move() -> None:
    zone = BuyZone(95.0, 100.0, ("support:97",), date(2025, 1, 2), 0, "TECHNICAL_ONLY")
    moved = BuyZone(97.0, 102.0, ("ma20",), date(2025, 1, 3), 0, "TECHNICAL_ONLY")
    records = [
        ReplayRecord.minimal(
            close=105.0,
            daily_change_pct=1.0,
            snapshot=_snapshot(date(2025, 1, 2), StrategyState.WAIT_FOR_PULLBACK, zone=zone),
        ),
        ReplayRecord.minimal(
            close=98.0,
            daily_change_pct=-6.7,
            snapshot=_snapshot(
                date(2025, 1, 3),
                StrategyState.REDUCE_RISK,
                previous_state=StrategyState.WAIT_FOR_PULLBACK,
                zone=moved,
                rule="RULE_STATE_UNCHANGED",
                transition=True,
            ),
        ),
    ]

    metrics = calculate_metrics(records, DEFAULT_POLICY)

    assert metrics.zone_entry_contradictions == 1
    assert metrics.zone_moves_without_trigger == 1
    assert metrics.unjustified_decline_downgrades == 1


@pytest.mark.unit
def test_metrics_separate_quick_recovery_from_false_terminal_invalidation() -> None:
    zone = BuyZone(95.0, 100.0, ("support:97",), date(2025, 1, 2), 0, "TECHNICAL_ONLY")
    records = [
        ReplayRecord.minimal(
            close=98.0,
            daily_change_pct=-1.0,
            snapshot=_snapshot(date(2025, 1, 2), StrategyState.ACCUMULATE_ZONE, zone=zone),
        ),
        ReplayRecord.minimal(
            close=85.0,
            daily_change_pct=-13.3,
            snapshot=_snapshot(
                date(2025, 1, 3),
                StrategyState.REDUCE_RISK,
                previous_state=StrategyState.ACCUMULATE_ZONE,
                rule="RULE_CONFIRMED_SUPPORT_BREAK",
                transition=True,
            ),
        ),
        ReplayRecord.minimal(
            close=84.0,
            daily_change_pct=-1.2,
            snapshot=_snapshot(
                date(2025, 1, 6),
                StrategyState.REDUCE_RISK,
                previous_state=StrategyState.REDUCE_RISK,
                rule="RULE_SUPPORT_RECLAIM_PENDING",
                transition=False,
            ),
        ),
        ReplayRecord.minimal(
            close=96.0,
            daily_change_pct=14.3,
            snapshot=_snapshot(
                date(2025, 1, 7),
                StrategyState.WATCHLIST,
                previous_state=StrategyState.REDUCE_RISK,
                rule="RULE_CONFIRMED_SUPPORT_RECLAIM",
                transition=True,
            ),
        ),
    ]

    metrics = calculate_metrics(records, DEFAULT_POLICY)
    assert metrics.confirmed_breaks == 1
    assert metrics.recognized_confirmed_breaks == 1
    assert metrics.false_invalidations == 0
    assert metrics.quick_recovery_technical_breaks == 1
    assert metrics.confirmed_reclaim_exits == 1
    assert metrics.reduce_risk_direct_accumulate_exits == 0


@pytest.mark.unit
def test_split_requires_frozen_cross_market_holdout() -> None:
    split = PanelSplit.create(
        calibration_symbols=("2330", "2454", "2308", "2317", "2881", "AAPL", "MSFT", "NVDA"),
        holdout_symbols=("2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY"),
        calibration_end=date(2025, 3, 31),
        holdout_start=date(2025, 4, 1),
        markets={
            "2330": "tw", "2454": "tw", "2308": "tw", "2317": "tw", "2881": "tw", "6505": "tw",
            "AAPL": "us", "MSFT": "us", "NVDA": "us", "LLY": "us",
        },
    )
    frozen = freeze_policy_selection(DEFAULT_POLICY, split)

    assert frozen.policy == DEFAULT_POLICY
    assert "6505" not in split.calibration_symbols
    assert "6505" in split.holdout_symbols
    assert "LLY" not in split.calibration_symbols
    assert "LLY" in split.holdout_symbols
    assert frozen.split_fingerprint


def _metrics(*, flips: float = 0.0, oscillations: int = 0) -> ReplayMetrics:
    return ReplayMetrics.empty(total=100).replace(
        untriggered_state_flip_rate=flips,
        boundary_oscillations=oscillations,
    )


@pytest.mark.unit
def test_policy_selection_retains_baseline_without_material_generalized_gain() -> None:
    candidate = StrategyPolicy(0.015, 0.01, 1.75, 4, 2)
    decision = select_policy(
        DEFAULT_POLICY,
        _metrics(flips=0.01, oscillations=1),
        {candidate: _metrics(flips=0.01, oscillations=1)},
    )

    assert decision.policy == DEFAULT_POLICY
    assert decision.reason == "BASELINE_POLICY_RETAINED"


@pytest.mark.unit
def test_frozen_candidate_is_rejected_when_holdout_gain_does_not_generalize() -> None:
    candidate = StrategyPolicy(0.01, 0.01, 1.5, 2, 1)
    verdict = validate_holdout_candidate(
        baseline_policy=DEFAULT_POLICY,
        candidate_policy=candidate,
        baseline_by_market={"tw": _metrics(flips=0.01), "us": _metrics(flips=0.0)},
        candidate_by_market={"tw": _metrics(flips=0.0), "us": _metrics(flips=0.0)},
        baseline_outcomes={},
        candidate_outcomes={},
    )

    assert verdict.policy == DEFAULT_POLICY
    assert verdict.reason == "BASELINE_POLICY_RETAINED_HOLDOUT_NO_GENERALIZED_GAIN"


@pytest.mark.unit
def test_artifacts_must_stay_outside_repository(tmp_path: Path) -> None:
    repo = Path(__file__).parents[2]
    with pytest.raises(ValueError, match="outside the repository"):
        validate_artifact_path(repo / "reports" / "phase27_3.json", repo)
    assert validate_artifact_path(tmp_path / "phase27_3.json", repo) == tmp_path / "phase27_3.json"


@pytest.mark.unit
def test_phase27_3s_contract_is_frozen() -> None:
    assert PHASE27_3S_STOCKS == ("2382", "2891", "3008", "3231", "AMZN", "META", "GOOGL", "AVGO")
    assert PHASE27_3S_EVALUATION_START == date(2025, 10, 1)
    assert PHASE27_3S_EVALUATION_END == date(2026, 3, 31)


@pytest.mark.unit
def test_phase27_3s_manifest_rejects_fixture_hash_mismatch(tmp_path: Path) -> None:
    fixture = tmp_path / "panel.csv"
    manifest = tmp_path / "manifest.json"
    fixture.write_text("not-the-captured-fixture\n", encoding="utf-8")
    manifest.write_text(json.dumps({"panel_sha256": "0" * 64}), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture hash"):
        validate_phase27_3s_fixture(fixture, manifest)


@pytest.mark.unit
def test_breakdown_episode_summary_uses_same_symbol_windows_and_censors_tail() -> None:
    start = date(2025, 10, 1)

    def record(day: int, close: float, state: StrategyState, rule: str) -> ReplayRecord:
        return ReplayRecord.minimal(
            close=close,
            daily_change_pct=0.0,
            snapshot=_snapshot(
                start + timedelta(days=day),
                state,
                previous_state=StrategyState.REDUCE_RISK,
                rule=rule,
                transition=rule in {"RULE_CONFIRMED_SUPPORT_BREAK", "RULE_CONFIRMED_SUPPORT_RECLAIM"},
            ),
        )

    quick = [record(0, 85.0, StrategyState.REDUCE_RISK, "RULE_CONFIRMED_SUPPORT_BREAK")]
    quick += [record(i, 95.0, StrategyState.REDUCE_RISK, "RULE_SUPPORT_RECLAIM_PENDING") for i in (1,)]
    quick += [record(2, 96.0, StrategyState.WATCHLIST, "RULE_CONFIRMED_SUPPORT_RECLAIM")]
    quick += [record(i, 100.0, StrategyState.WATCHLIST, "RULE_STATE_UNCHANGED") for i in range(3, 23)]
    censored = [record(30, 85.0, StrategyState.REDUCE_RISK, "RULE_CONFIRMED_SUPPORT_BREAK")]

    summary = analyze_breakdown_episodes({"2382": quick + censored}, {"2382": "tw"})

    assert summary["total"]["confirmed_breaks"] == 2
    assert summary["total"]["quick_recoveries"] == 1
    assert summary["total"]["confirmed_reclaims"] == 1
    assert summary["total"]["one_day_rebound_exit_violations"] == 0
    assert summary["total"]["sustained_breaks"] == 0
    assert summary["total"]["sustained_censored"] == 1


@pytest.mark.unit
def test_state_run_summary_separates_entries_occupancy_duration_and_censoring() -> None:
    states = [
        StrategyState.WATCHLIST,
        StrategyState.DO_NOT_CHASE,
        StrategyState.DO_NOT_CHASE,
        StrategyState.DO_NOT_CHASE,
        StrategyState.WATCHLIST,
        StrategyState.DO_NOT_CHASE,
    ]
    records = []
    for index, state in enumerate(states):
        rule = "RULE_WAIT_FOR_PULLBACK" if index == 4 else "RULE_STATE_UNCHANGED"
        records.append(ReplayRecord.minimal(
            close=100.0,
            daily_change_pct=0.0,
            snapshot=_snapshot(date(2025, 1, 2) + timedelta(days=index), state, rule=rule),
        ))

    summary = summarize_state_runs({"X": records}, StrategyState.DO_NOT_CHASE)

    assert summary["entries"] == 2
    assert summary["transitions_into_state"] == 2
    assert summary["observations"] == 4
    assert summary["duration_median"] == 2.0
    assert summary["duration_p75"] == 2.5
    assert summary["duration_p90"] == 2.8
    assert summary["duration_max"] == 3
    assert summary["exit_rule_distribution"] == {"RULE_WAIT_FOR_PULLBACK": 1}
    assert summary["right_censored_runs"] == 1


@pytest.mark.unit
def test_do_not_chase_retention_categories_are_mutually_exclusive() -> None:
    zone = BuyZone(
        low=90.0,
        high=95.0,
        basis=("support:92.0",),
        created_at=date(2025, 1, 2),
        revision=0,
        zone_type="TECHNICAL_ONLY",
    )
    base = _snapshot(date(2025, 1, 2), StrategyState.DO_NOT_CHASE, zone=zone)
    records = [
        ReplayRecord.minimal(close=110.0, daily_change_pct=0.0, snapshot=replace(
            base,
            transition_rule_id=RULE_RISK_REWARD_OVEREXTENDED,
            reasons=("rr_at_price=0.5",),
        )),
        ReplayRecord.minimal(close=109.0, daily_change_pct=0.0, snapshot=replace(
            base,
            as_of=date(2025, 1, 3),
            transition_rule_id=RULE_DO_NOT_CHASE_REVALIDATED,
            reasons=("rr_at_price=0.6",),
        )),
        ReplayRecord.minimal(close=100.0, daily_change_pct=0.0, snapshot=replace(
            base,
            as_of=date(2025, 1, 4),
            transition_rule_id=RULE_HYSTERESIS_HOLD,
            reasons=("suppressed_transition_to=WAIT_FOR_PULLBACK",),
        )),
        ReplayRecord.minimal(close=89.0, daily_change_pct=0.0, snapshot=replace(
            base,
            as_of=date(2025, 1, 5),
            reasons=(INVALIDATION_BREACH_PENDING,),
        )),
        ReplayRecord.minimal(close=89.0, daily_change_pct=0.0, snapshot=replace(
            base,
            as_of=date(2025, 1, 6),
            reasons=(),
        )),
        ReplayRecord.minimal(close=100.0, daily_change_pct=0.0, snapshot=replace(
            base,
            as_of=date(2025, 1, 7),
            buy_zone=None,
            reasons=(),
        )),
    ]

    assert classify_do_not_chase_retention(records[0], records[1]) == "CURRENT_TRIGGER_STILL_TRUE"
    assert classify_do_not_chase_retention(records[1], records[2]) == "HYSTERESIS_SUPPRESSED_EXIT"
    assert classify_do_not_chase_retention(records[2], records[3]) == "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED"
    assert classify_do_not_chase_retention(records[3], records[4]) == "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED"
    assert classify_do_not_chase_retention(records[4], records[5]) == "NO_VALID_ZONE_AVAILABLE"

    summary = summarize_do_not_chase_lifecycle({"2454": records})
    assert summary["entries"] == 1
    assert summary["retention_reasons"] == {
        "CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED": 2,
        "CURRENT_TRIGGER_STILL_TRUE": 2,
        "HYSTERESIS_SUPPRESSED_EXIT": 1,
        "NO_VALID_ZONE_AVAILABLE": 1,
        "OTHER_EXPLICIT_REASON": 0,
    }
    assert sum(summary["retention_reasons"].values()) == (
        summary["observations"] - summary["transitions_into_state"]
    )
    assert summary["trigger_true_and_retained"] == 2
    assert summary["trigger_false_but_retained"] == 2
    assert summary["trigger_unobservable_but_retained"] == 1
    assert summary["hysteresis_delayed_exits"] == 1
    assert summary["right_censored_after_trigger_cleared"] == 0
    assert summary["right_censored_trigger_unobservable"] == 1


@pytest.mark.unit
def test_do_not_chase_exit_lag_covers_every_exit_state() -> None:
    zone = BuyZone(
        low=90.0,
        high=95.0,
        basis=("support:92.0",),
        created_at=date(2025, 1, 2),
        revision=0,
        zone_type="TECHNICAL_ONLY",
    )
    records = [
        ReplayRecord.minimal(
            close=110.0,
            daily_change_pct=0.0,
            snapshot=replace(
                _snapshot(date(2025, 1, 2), StrategyState.DO_NOT_CHASE, zone=zone),
                reasons=("rr_at_price=0.5",),
            ),
        ),
        ReplayRecord.minimal(
            close=93.0,
            daily_change_pct=0.0,
            snapshot=_snapshot(
                date(2025, 1, 3),
                StrategyState.ACCUMULATE_ZONE,
                zone=zone,
                rule=RULE_VALID_BUY_ZONE_ENTERED,
            ),
        ),
        ReplayRecord.minimal(
            close=110.0,
            daily_change_pct=0.0,
            snapshot=replace(
                _snapshot(date(2025, 1, 4), StrategyState.DO_NOT_CHASE, zone=zone),
                reasons=("rr_at_price=0.5",),
            ),
        ),
        ReplayRecord.minimal(
            close=85.0,
            daily_change_pct=0.0,
            snapshot=_snapshot(
                date(2025, 1, 5),
                StrategyState.REDUCE_RISK,
                zone=zone,
                rule=RULE_CONFIRMED_SUPPORT_BREAK,
            ),
        ),
    ]

    summary = summarize_do_not_chase_lifecycle({"2454": records})

    assert summary["exit_state_distribution"] == {
        "ACCUMULATE_ZONE": 1,
        "REDUCE_RISK": 1,
    }
    assert summary["trigger_clear_to_exit_observations"] == [0, 0]
    assert summary["trigger_clear_to_exit_calendar_days"] == [0, 0]


@pytest.mark.unit
def test_replay_evaluator_hook_changes_only_selected_lifecycle_observation() -> None:
    inputs = [
        StrategyStateInput(
            symbol="X",
            market="us",
            instrument_type="stock",
            as_of=date(2025, 1, 2) + timedelta(days=index),
            close=100.0 + index,
        )
        for index in range(2)
    ]
    calls = []

    def evaluator(input_data, previous, policy):
        calls.append((input_data.as_of, previous.as_of if previous else None, policy))
        return _snapshot(input_data.as_of, StrategyState.WATCHLIST)

    records = replay_inputs(inputs, evaluator=evaluator)

    assert len(records) == 2
    assert calls[0][1] is None
    assert calls[1][1] == inputs[0].as_of
    assert all(call[2] == DEFAULT_POLICY for call in calls)


def _phase27_3v_input(
    *,
    as_of: date = date(2025, 1, 2),
    close: float = 100.0,
    support: float = 90.0,
    resistance: float | None = 105.0,
    provenance: tuple[dict, ...] = (),
) -> StrategyStateInput:
    return StrategyStateInput(
        symbol="2454",
        market="tw",
        instrument_type="stock",
        as_of=as_of,
        close=close,
        deterministic_support_levels=(support,),
        deterministic_resistance_levels=(resistance,) if resistance is not None else (),
        market_structure_resistance_levels=tuple(
            level["price"]
            for level in provenance
            if level.get("status") == "active"
        ),
        market_structure_resistance_provenance=provenance,
    )


@pytest.mark.unit
def test_rr_diagnostic_distinguishes_now_from_planned_zone() -> None:
    input_data = _phase27_3v_input()
    snapshot = evaluate_strategy_state(input_data, None)

    diagnostic = rr_audit.diagnose_rr(input_data, snapshot)

    assert snapshot.state == StrategyState.DO_NOT_CHASE
    assert diagnostic["zone_lower"] == 88.2
    assert diagnostic["zone_upper"] == 91.8
    assert diagnostic["invalidation_level"] == 86.436
    assert diagnostic["entry_references"] == {
        "E0": 100.0,
        "E1": 100.0,
        "E2": 90.0,
        "E3": 91.8,
        "E4": 88.2,
    }
    assert diagnostic["rr_now"] == pytest.approx(0.3686228)
    assert diagnostic["rr_at_planned_zone"] == pytest.approx(2.460849)
    assert diagnostic["reward"] == 5.0
    assert diagnostic["risk"] == pytest.approx(13.564)


@pytest.mark.unit
def test_semantic_arms_distinguish_planned_setup_from_immediate_chase() -> None:
    input_data = _phase27_3v_input()

    arm_a, guard_a = rr_audit.evaluate_semantic_arm(input_data, None, arm="A")
    arm_b, guard_b = rr_audit.evaluate_semantic_arm(input_data, None, arm="B")
    arm_c, guard_c = rr_audit.evaluate_semantic_arm(input_data, None, arm="C")

    assert arm_a.state == StrategyState.DO_NOT_CHASE
    assert arm_b.state == StrategyState.WAIT_FOR_PULLBACK
    assert arm_c.state == StrategyState.WAIT_FOR_PULLBACK
    assert guard_a is None
    assert guard_b is None
    assert guard_c == "DO_NOT_CHASE_NOW"


@pytest.mark.unit
def test_no_attractive_setup_anywhere_does_not_false_accumulate() -> None:
    input_data = _phase27_3v_input(resistance=100.0)

    results = {
        arm: rr_audit.evaluate_semantic_arm(input_data, None, arm=arm)
        for arm in ("A", "B", "C")
    }

    assert results["A"][0].state == StrategyState.DO_NOT_CHASE
    assert results["B"][0].state == StrategyState.DO_NOT_CHASE
    assert results["C"][0].state == StrategyState.WATCHLIST
    assert all(
        snapshot.state != StrategyState.ACCUMULATE_ZONE
        for snapshot, _guard in results.values()
    )


@pytest.mark.unit
def test_zone_entry_supersedes_every_semantic_guard() -> None:
    initial = _phase27_3v_input()
    next_input = _phase27_3v_input(as_of=date(2025, 1, 3), close=91.0)

    for arm in ("A", "B", "C"):
        previous, _ = rr_audit.evaluate_semantic_arm(initial, None, arm=arm)
        current, guard = rr_audit.evaluate_semantic_arm(next_input, previous, arm=arm)
        assert current.state == StrategyState.ACCUMULATE_ZONE
        assert guard is None


@pytest.mark.unit
def test_holder_counterfactual_never_reduces_without_breakdown() -> None:
    input_data = _phase27_3v_input()
    snapshot = evaluate_strategy_state(input_data, None)
    diagnostic = rr_audit.diagnose_rr(input_data, snapshot)

    holder = rr_audit.holder_counterfactual(diagnostic, has_position=True)
    non_holder = rr_audit.holder_counterfactual(diagnostic, has_position=False)
    unknown = rr_audit.holder_counterfactual(diagnostic, has_position=None)

    assert holder == {
        "state": "HOLD_ONLY",
        "action_guard": "DO_NOT_ADD_NOW",
        "meaning": "HOLDER_HOLD_WITHOUT_ADDING",
    }
    assert non_holder["state"] == "WAIT_FOR_PULLBACK"
    assert non_holder["meaning"] == "NON_HOLDER_WAIT_FOR_ENTRY"
    assert unknown["meaning"] == "AMBIGUOUS_CURRENT_CONTRACT"


@pytest.mark.unit
def test_resistance_selectors_reject_broken_stale_and_choose_deterministically() -> None:
    provenance = (
        {"price": 105.0, "status": "broken", "touch_count": 5, "prominence": 3.0,
         "confirmed_at": "2024-12-01", "last_seen_at": "2024-11-20"},
        {"price": 107.0, "status": "active", "touch_count": 1, "prominence": 1.0,
         "confirmed_at": "2024-12-02", "last_seen_at": "2024-11-21"},
        {"price": 110.0, "status": "active", "touch_count": 3, "prominence": 2.0,
         "confirmed_at": "2024-12-03", "last_seen_at": "2024-11-22"},
        {"price": 120.0, "status": "stale", "touch_count": 9, "prominence": 4.0,
         "confirmed_at": "2024-01-01", "last_seen_at": "2024-01-01"},
    )
    input_data = _phase27_3v_input(resistance=None, provenance=provenance)

    selected = {
        selector: rr_audit.select_resistance_targets(
            input_data,
            entry=100.0,
            selector=selector,
            zone_midpoint=90.0,
        )
        for selector in ("R0", "R1", "R2", "R3", "R4", "R5")
    }

    assert [row["price"] for row in selected["R1"]] == [107.0]
    assert [row["price"] for row in selected["R2"]] == [110.0]
    assert [row["price"] for row in selected["R4"]] == [110.0]
    assert [row["price"] for row in selected["R5"]] == [107.0, 110.0]
    assert all(
        target["status"] == "active"
        for targets in selected.values()
        for target in targets
    )
    assert selected == {
        selector: rr_audit.select_resistance_targets(
            input_data,
            entry=100.0,
            selector=selector,
            zone_midpoint=90.0,
        )
        for selector in selected
    }


@pytest.mark.unit
def test_resistance_selector_rejects_future_confirmed_provenance() -> None:
    input_data = _phase27_3v_input(provenance=({
        "price": 110.0,
        "status": "active",
        "touch_count": 2,
        "prominence": 1.0,
        "confirmed_at": "2025-01-03",
        "last_seen_at": "2025-01-01",
    },))

    with pytest.raises(ValueError, match="future-confirmed resistance provenance"):
        rr_audit.select_resistance_targets(input_data, entry=100.0, selector="R1")


@pytest.mark.unit
def test_sparse_resistance_is_unknown_and_extreme_rally_remains_guarded() -> None:
    sparse = _phase27_3v_input(resistance=None)
    sparse_snapshot = evaluate_strategy_state(sparse, None)
    sparse_diagnostic = rr_audit.diagnose_rr(sparse, sparse_snapshot)
    extreme = _phase27_3v_input(close=130.0)

    assert sparse_diagnostic["selected_resistance"] is None
    assert sparse_diagnostic["rr_now"] is None
    assert sparse_diagnostic["rr_at_planned_zone"] is None
    for arm in ("A", "B", "C"):
        snapshot, guard = rr_audit.evaluate_semantic_arm(extreme, None, arm=arm)
        assert snapshot.state != StrategyState.ACCUMULATE_ZONE
        assert (
            snapshot.state == StrategyState.DO_NOT_CHASE
            or guard == "DO_NOT_CHASE_NOW"
            or snapshot.transition_rule_id == rr_audit.RULE_EVAL_PLANNED_ZONE_WAIT
        )


@pytest.mark.unit
def test_dnc_classification_is_exactly_one_and_position_truth_remains_unknown() -> None:
    input_data = _phase27_3v_input()
    snapshot = evaluate_strategy_state(input_data, None)

    classification = rr_audit.classify_dnc(rr_audit.diagnose_rr(input_data, snapshot))

    assert classification == {
        "primary": "PRICE_ABOVE_VALID_ZONE_RR_FROM_CURRENT_PRICE",
        "holder_meaning": "AMBIGUOUS_CURRENT_CONTRACT",
    }
    assert classification["primary"] in rr_audit.DNC_PRIMARY_CATEGORIES
    assert classification["holder_meaning"] in rr_audit.HOLDER_MEANINGS


@pytest.mark.unit
def test_late_primary_categories_follow_frozen_r4_e4_precedence() -> None:
    input_data = _phase27_3v_input()
    snapshot = evaluate_strategy_state(input_data, None)
    diagnostic = rr_audit.diagnose_rr(input_data, snapshot)
    residual = {
        **diagnostic,
        "rr_at_planned_zone": None,
        "rr_now_r4": 2.1,
        "rr_at_zone_lower": 1.0,
    }

    assert rr_audit.classify_dnc(residual)["primary"] == "RESISTANCE_TOO_CLOSE"
    residual["rr_now"] = 2.1
    assert rr_audit.classify_dnc(residual)["primary"] == "OTHER_EXPLICIT_REASON"
    residual["rr_now"] = diagnostic["rr_now"]
    residual["rr_now_r4"] = None
    assert rr_audit.classify_dnc(residual)["primary"] == "RISK_DISTANCE_TOO_LARGE"


@pytest.mark.unit
def test_semantic_adapters_do_not_create_boundary_flip_explosion() -> None:
    inputs = [
        _phase27_3v_input(as_of=date(2025, 1, 2) + timedelta(days=index), close=close)
        for index, close in enumerate((100.0, 99.0, 100.0, 99.0, 100.0))
    ]
    transitions = {}
    for arm in ("A", "B", "C"):
        previous = None
        states = []
        for input_data in inputs:
            previous, _ = rr_audit.evaluate_semantic_arm(input_data, previous, arm=arm)
            states.append(previous.state)
        transitions[arm] = sum(left != right for left, right in zip(states, states[1:]))

    assert transitions["B"] <= transitions["A"]
    assert transitions["C"] <= transitions["A"]


@pytest.mark.unit
def test_semantic_arm_definitions_have_no_symbol_overrides() -> None:
    assert all(
        not definition["symbol_overrides"]
        for definition in rr_audit.SEMANTIC_ARM_DEFINITIONS.values()
    )


@pytest.mark.unit
def test_trigger_clear_lag_resets_when_rr_trigger_reappears() -> None:
    snapshots = [
        replace(
            _snapshot(date(2025, 1, 2), StrategyState.DO_NOT_CHASE),
            transition_rule_id=RULE_RISK_REWARD_OVEREXTENDED,
            reasons=("rr_at_price=0.5",),
        ),
        replace(
            _snapshot(date(2025, 1, 3), StrategyState.DO_NOT_CHASE),
            transition_rule_id=RULE_HYSTERESIS_HOLD,
            reasons=("suppressed_transition_to=WATCHLIST",),
        ),
        replace(
            _snapshot(date(2025, 1, 4), StrategyState.DO_NOT_CHASE),
            transition_rule_id=RULE_DO_NOT_CHASE_REVALIDATED,
            reasons=("rr_at_price=0.4",),
        ),
        _snapshot(date(2025, 1, 5), StrategyState.WATCHLIST),
    ]
    records = [
        ReplayRecord.minimal(close=100.0, daily_change_pct=0.0, snapshot=snapshot)
        for snapshot in snapshots
    ]

    summary = summarize_do_not_chase_lifecycle({"X": records})

    assert summary["trigger_clear_to_exit_calendar_days"] == [0]
    assert summary["trigger_clear_to_exit_observations"] == [0]


@pytest.mark.integration
def test_agent_and_non_agent_authority_sequence_parity() -> None:
    from src.services.strategy_state_orchestrator import attach_strategy_state
    from src.stock_analyzer import TrendAnalysisResult
    from tests.test_strategy_state_orchestrator import PipelineAttachTestCase, _llm_result

    pipeline = PipelineAttachTestCase()._make_pipeline(flag=True)
    previous = None
    sequence = [
        (date(2026, 7, 7), 4100.0, 1.0),
        (date(2026, 7, 8), 3925.0, -4.27),
        (date(2026, 7, 9), 4620.0, 17.71),
        (date(2026, 7, 10), 4625.0, 0.11),
        (date(2026, 7, 13), 4625.0, 0.0),
        (date(2026, 7, 14), 4625.0, 0.0),
        (date(2026, 7, 17), 3780.0, -18.27),
    ]
    observed_rules = []
    for as_of, close, change_pct in sequence:
        trend = TrendAnalysisResult(
            code="2454",
            current_price=close,
            ma5=4054.0,
            ma10=4100.0,
            ma20=4200.0,
            ma60=3800.0,
            volume_ratio_5d=1.0,
            support_levels=[3880.0, 4054.0, 4100.0],
            resistance_levels=[4700.0],
            market_structure_support_levels=[{"price": 3880.0, "status": "active"}],
            market_structure_resistance_levels=[{"price": 4700.0, "status": "active"}],
        )
        outputs = []
        for operation, decision, prediction in (
            ("買進", "buy", "強烈看多"),
            ("賣出", "sell", "強烈看空"),
        ):
            result = _llm_result(
                operation_advice=operation,
                decision_type=decision,
                trend_prediction=prediction,
            )
            result.instrument_type = "stock"
            result.change_pct = change_pct
            result.valuation_river_snapshot = None
            with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), patch(
                "src.services.history_loader.get_frozen_target_date", return_value=as_of
            ), patch(
                "src.services.strategy_state_orchestrator.attach_strategy_state",
                wraps=attach_strategy_state,
            ) as attach_spy:
                pipeline._attach_strategy_state_snapshot(
                    result,
                    "2454",
                    trend_result=trend,
                    fundamental_context=PipelineAttachTestCase()._neutral_fundamental(),
                    previous_snapshot=previous,
                )
            strategy_input = attach_spy.call_args.args[1]
            outputs.append({
                "input": strategy_input,
                "snapshot": result.strategy_state_snapshot,
                "operation_advice": result.operation_advice,
                "decision_type": result.decision_type,
                "sniper_points": result.dashboard["battle_plan"]["sniper_points"],
            })
        assert outputs[0] == outputs[1]
        assert outputs[0]["input"].market_structure_support_levels == (3880.0,)
        assert outputs[0]["input"].market_structure_resistance_levels == (4700.0,)
        previous = StrategyStateSnapshot.from_dict(outputs[0]["snapshot"])
        observed_rules.append(previous.transition_rule_id)
    assert RULE_DO_NOT_CHASE_REVALIDATED in observed_rules
    assert previous.transition_rule_id == RULE_DO_NOT_CHASE_CLEARED


@pytest.mark.integration
def test_agent_and_non_agent_provider_outage_failure_parity() -> None:
    from src.services.strategy_state_orchestrator import StrategyDataUnavailableError
    from tests.test_strategy_state_orchestrator import PipelineAttachTestCase, _llm_result

    pipeline = PipelineAttachTestCase()._make_pipeline(flag=True)
    broken = PipelineAttachTestCase()._trend(100.0)
    broken["current_price"] = None
    for operation in ("買進", "賣出"):
        result = _llm_result(operation_advice=operation)
        result.instrument_type = "stock"
        result.change_pct = None
        result.valuation_river_snapshot = None
        with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), patch(
            "src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)
        ), pytest.raises(StrategyDataUnavailableError):
            pipeline._attach_strategy_state_snapshot(
                result,
                "2454",
                trend_result=broken,
                fundamental_context=PipelineAttachTestCase()._neutral_fundamental(),
                previous_snapshot=None,
            )
        assert result.strategy_state_snapshot is None


@pytest.mark.unit
def test_compact_fixture_manifest_is_sanitized_and_complete() -> None:
    panel = load_panel_fixture(FIXTURE)

    assert set(panel) == {"2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY", "0050", "SPY"}
    assert all(len(rows) >= 200 for rows in panel.values())
    assert all(rows == sorted(rows, key=lambda bar: bar.as_of) for rows in panel.values())
    assert "credential" not in FIXTURE.read_text(encoding="utf-8").lower()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_PHASE27_LEGACY_CALIBRATION") != "1",
    reason="historical Phase 27.3 calibration is frozen; do not reuse its holdout",
)
def test_legacy_phase27_3_panel_acceptance(tmp_path: Path) -> None:
    from src.evaluation.strategy_sequence_replay import run_phase27_3_evaluation

    artifact = run_phase27_3_evaluation(FIXTURE, tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["panel"]["stock_symbols"] == [
        "2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY"
    ]
    assert payload["panel"]["total_evaluations"] >= 240
    assert set(payload["panel"]["markets"]) == {"tw", "us"}
    assert payload["baseline"]["same_sequence_nondeterminism_rate"] == 0
    assert payload["baseline"]["unsupported_rate"] == 0
    assert payload["baseline"]["anchor_lint_failure_rate"] == 0
    assert payload["baseline"]["zone_movement_without_trigger_rate"] == 0
    assert payload["baseline"]["zone_entry_contradiction_rate"] == 0
    assert payload["baseline"]["untriggered_state_flip_rate"] <= 0.05
    assert payload["baseline"]["unjustified_rally_upgrade_rate"] <= 0.05
    assert payload["baseline"]["unjustified_decline_downgrade_rate"] <= 0.05
    assert payload["selection"]["holdout_evaluated_once"] is True


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_PHASE27_EVAL") != "1", reason="set RUN_PHASE27_EVAL=1 for baseline-only repair replay")
def test_phase27_3r_repaired_baseline_only(tmp_path: Path) -> None:
    from src.evaluation.strategy_sequence_replay import run_phase27_3r_baseline_replay

    artifact = run_phase27_3r_baseline_replay(FIXTURE, tmp_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["threshold_selection_performed"] is False
    assert payload["old_holdout_used_for_selection"] is False
    assert payload["policy"] == {
        "support_tolerance_pct": 0.02,
        "anchor_lint_tolerance_pct": 0.01,
        "minimum_risk_reward": 2.0,
        "hysteresis_days": 3,
        "invalidation_confirmation_days": 2,
        "reclaim_confirmation_days": 2,
    }
    assert payload["panel"]["total_evaluations"] >= 240
    assert payload["metrics"]["same_sequence_nondeterminism_rate"] == 0
    assert payload["metrics"]["unsupported_rate"] == 0
    assert payload["metrics"]["anchor_lint_failure_rate"] == 0
    assert payload["metrics"]["zone_movement_without_trigger_rate"] == 0
    assert payload["metrics"]["zone_entry_contradiction_rate"] == 0
    assert payload["metrics"]["untriggered_state_flip_rate"] == 0
    assert payload["metrics"]["unjustified_rally_upgrade_rate"] <= 0.05
    assert payload["metrics"]["unjustified_decline_downgrade_rate"] <= 0.05
    assert payload["metrics"]["state_distribution"].get("INVALIDATED", 0) == 0
    assert payload["metrics"]["state_distribution"].get("REDUCE_RISK", 0) > 0
    assert payload["metrics"]["reduce_risk_direct_accumulate_exits"] == 0


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_PHASE27_3S_EVAL") != "1",
    reason="set RUN_PHASE27_3S_EVAL=1 for the frozen new holdout",
)
def test_phase27_3s_new_holdout(tmp_path: Path) -> None:
    from src.evaluation.strategy_sequence_replay import run_phase27_3s_holdout

    artifact = run_phase27_3s_holdout(
        PHASE27_3S_FIXTURE,
        PHASE27_3S_MANIFEST,
        tmp_path,
        reference_fixture=FIXTURE,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["threshold_selection_performed"] is False
    assert payload["policy"] == DEFAULT_POLICY.__dict__
    assert payload["panel"]["stock_symbols"] == list(PHASE27_3S_STOCKS)
    assert payload["panel"]["evaluation_start"] == "2025-10-01"
    assert payload["panel"]["evaluation_end"] == "2026-03-31"
    assert payload["metrics"]["same_sequence_nondeterminism_rate"] == 0
    assert payload["semantics"]["technical_breaks_to_invalidated"] == 0
    assert payload["episodes"]["total"]["direct_reduce_to_accumulate"] == 0


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_PHASE27_3T_DEV_EVAL") != "1",
    reason="set RUN_PHASE27_3T_DEV_EVAL=1 for the seen-fixture A/B replay",
)
def test_phase27_3t_development_ab(tmp_path: Path) -> None:
    from src.evaluation.strategy_sequence_replay import run_phase27_3t_development_ab

    artifact = run_phase27_3t_development_ab(
        FIXTURE,
        PHASE27_3S_FIXTURE,
        PHASE27_3S_MANIFEST,
        tmp_path,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["threshold_selection_performed"] is False
    assert payload["phase27_3s_a_consumed"] is False
    assert payload["policy"] == DEFAULT_POLICY.__dict__
    assert set(payload["arms"]) == {"A_current", "B_market_structure"}
    assert payload["arms"]["A_current"]["same_sequence_nondeterminism_rate"] == 0
    assert payload["arms"]["B_market_structure"]["same_sequence_nondeterminism_rate"] == 0
    assert payload["arms"]["B_market_structure"]["provenance"]["independent_support_inputs"] > 0
    assert set(payload["panels"]) == {"phase27_3", "phase27_3s"}


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_PHASE27_3U_EVAL") != "1",
    reason="set RUN_PHASE27_3U_EVAL=1 for the seen-fixture lifecycle A/B replay",
)
def test_phase27_3u_lifecycle_ab(tmp_path: Path) -> None:
    artifact = run_phase27_3u_lifecycle_ab(
        FIXTURE,
        PHASE27_3S_FIXTURE,
        PHASE27_3S_MANIFEST,
        tmp_path,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["phase27_3s_a_consumed"] is False
    assert payload["threshold_selection_performed"] is False
    assert payload["policy"] == DEFAULT_POLICY.__dict__
    assert set(payload["arms"]) == {"A_phase27_3t", "B_lifecycle_repair"}
    assert payload["inputs_byte_equivalent"] is True
    assert payload["causal_level_coverage_byte_equivalent"] is True
    assert payload["arms"]["B_lifecycle_repair"]["same_sequence_nondeterminism_rate"] == 0
    assert payload["arms"]["B_lifecycle_repair"]["same_input_nondeterminism_rate"] == 0
    assert payload["status"] == "PHASE_27_3U_FAILED_PERSISTENCE_OR_STRUCTURAL_GATES"
    assert payload["arms"]["A_phase27_3t"]["metrics"]["state_distribution"] == {
        "ACCUMULATE_ZONE": 152,
        "DO_NOT_CHASE": 1768,
        "HOLD_ONLY": 11,
        "REDUCE_RISK": 219,
        "WAIT_FOR_PULLBACK": 55,
        "WATCHLIST": 231,
    }
    assert payload["arms"]["A_phase27_3t"]["lifecycle"]["transitions_into_state"] == 75
    assert sum(
        payload["arms"]["A_phase27_3t"]["lifecycle"]["retention_reasons"].values()
    ) == 1768 - 75
    assert payload["arms"]["A_phase27_3t"]["lifecycle"]["duration_median"] == 8
    assert payload["arms"]["A_phase27_3t"]["lifecycle"]["right_censored_runs"] == 14
    assert payload["arms"]["B_lifecycle_repair"]["lifecycle"][
        "retention_reasons"
    ]["CURRENT_TRIGGER_CLEARED_BUT_STATE_PERSISTED"] == 0
    assert payload["arms"]["B_lifecycle_repair"]["lifecycle"][
        "retention_reasons"
    ]["OTHER_EXPLICIT_REASON"] == 0
    assert sum(
        payload["arms"]["B_lifecycle_repair"]["lifecycle"]["retention_reasons"].values()
    ) == 1765 - 75
    assert set(payload["arms"]["B_lifecycle_repair"]["lifecycle_by_panel"]) == {
        "phase27_3",
        "phase27_3s",
    }
    assert set(payload["arms"]["B_lifecycle_repair"]["lifecycle_by_market"]) == {"tw", "us"}
    assert set(payload["arms"]["B_lifecycle_repair"]["lifecycle_by_symbol"]) == set(
        payload["arms"]["B_lifecycle_repair"]["metrics_by_symbol"]
    )
    assert payload["development_gates"]["unexplained_retention"] is True
    assert payload["development_gates"]["combined_do_not_chase_below_50pct"] is False


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_PHASE27_3V_EVAL") != "1",
    reason="set RUN_PHASE27_3V_EVAL=1 for the frozen resistance/RR semantic audit",
)
def test_phase27_3v_resistance_rr_semantic_audit(tmp_path: Path) -> None:
    artifact = rr_audit.run_phase27_3v_semantic_audit(
        FIXTURE,
        PHASE27_3S_FIXTURE,
        PHASE27_3S_MANIFEST,
        tmp_path,
    )
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    assert payload["phase"] == "27.3V"
    assert payload["phase27_3s_a_consumed"] is False
    assert payload["threshold_selection_performed"] is False
    assert payload["policy"] == DEFAULT_POLICY.__dict__
    assert payload["state_outputs_frozen_before_outcomes"] is True
    assert set(payload["arms"]) >= {"A_current", "B_planned_zone", "C_action_guard"}
    assert all(arm["total_evaluations"] == 2436 for arm in payload["arms"].values())
    assert payload["arms"]["A_current"]["state_distribution"] == {
        "ACCUMULATE_ZONE": 152,
        "DO_NOT_CHASE": 1765,
        "HOLD_ONLY": 11,
        "REDUCE_RISK": 219,
        "WAIT_FOR_PULLBACK": 55,
        "WATCHLIST": 234,
    }
    assert payload["same_input_nondeterminism_rate"] == 0
    assert payload["same_sequence_nondeterminism_rate"] == 0
    assert payload["input_fingerprints_identical"] is True
    assert payload["causal_provenance_fingerprints_identical"] is True
    assert sum(payload["dnc_diagnostics"]["primary_categories"].values()) == 1765
    assert payload["dnc_diagnostics"]["holder_meanings"] == {
        "AMBIGUOUS_CURRENT_CONTRACT": 1765,
    }
    assert all(
        sum(matrix.values()) == 2436
        for matrix in payload["matched_state_matrices"].values()
    )
    assert payload["arm_d"]["historical_execution"] == "BLOCKED_NO_POSITION_INPUT"
    assert payload["status"] == "PHASE_27_3V_CONFIRMS_STRATEGY_PRODUCTIZATION_SHOULD_STOP"
    assert payload["viable_arms"] == []
    assert payload["arm_e_preregistered_condition"] == {
        "included": False,
        "r0_structural_defect_count": 0,
    }
    assert payload["arms"]["B_planned_zone"]["state_distribution"] == {
        "ACCUMULATE_ZONE": 152,
        "DO_NOT_CHASE": 446,
        "HOLD_ONLY": 11,
        "REDUCE_RISK": 219,
        "WAIT_FOR_PULLBACK": 1374,
        "WATCHLIST": 234,
    }
    assert payload["arms"]["C_action_guard"]["state_distribution"] == {
        "ACCUMULATE_ZONE": 152,
        "HOLD_ONLY": 11,
        "REDUCE_RISK": 219,
        "WAIT_FOR_PULLBACK": 1596,
        "WATCHLIST": 458,
    }
    assert payload["dnc_diagnostics"]["entry_reference_disagreement"]["total"] == 1310
    assert payload["dnc_diagnostics"]["primary_categories"] == {
        "NO_VALID_ZONE": 227,
        "OTHER_EXPLICIT_REASON": 3,
        "PREVIOUS_ZONE_SEMANTIC_CONFLICT": 222,
        "PRICE_ABOVE_VALID_ZONE_RR_FROM_CURRENT_PRICE": 1307,
        "PRICE_INSIDE_OR_NEAR_ZONE_BUT_RR_FAIL": 6,
    }
    assert payload["arm_d"]["counterfactual_lenses"]["holder"]["total"] == 1765
    assert payload["arm_d"]["counterfactual_lenses"]["non_holder"]["total"] == 1765
    assert payload["no_lookahead_failures"] == 0
    assert payload["development_gates"]["B_planned_zone"][
        "holder_nonholder_semantics"
    ] is False
    assert payload["arms"]["A_current"]["true_immediate_overextension"] == {
        "eligible": 456,
        "detected": 431,
    }
    assert payload["arms"]["B_planned_zone"]["true_immediate_overextension"] == {
        "eligible": 456,
        "detected": 427,
    }
    assert payload["arms"]["C_action_guard"]["true_immediate_overextension"] == {
        "eligible": 456,
        "detected": 436,
    }
    assert payload["development_gates"]["B_planned_zone"][
        "immediate_overextension_detectable"
    ] is False
    assert payload["development_gates"]["C_action_guard"][
        "immediate_overextension_detectable"
    ] is False
    expected_failed_gates = {
        "holder_nonholder_semantics",
        "immediate_overextension_detectable",
        "no_combined_state_majority",
        "no_unexplained_symbol_100pct",
        "panel_concentration",
        "wait_not_indiscriminate",
    }
    assert {
        key
        for key, passed in payload["development_gates"]["B_planned_zone"].items()
        if not passed
    } == expected_failed_gates
    assert {
        key
        for key, passed in payload["development_gates"]["C_action_guard"].items()
        if not passed
    } == expected_failed_gates

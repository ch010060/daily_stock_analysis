from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.evaluation.strategy_sequence_replay import (
    MarketBar,
    PanelSplit,
    ReplayMetrics,
    ReplayRecord,
    build_replay_input,
    calculate_metrics,
    freeze_policy_selection,
    load_panel_fixture,
    replay_inputs,
    select_policy,
    validate_holdout_candidate,
    validate_artifact_path,
)
from src.services.strategy_state_engine import (
    DEFAULT_POLICY,
    BuyZone,
    StrategyPolicy,
    StrategyState,
    StrategyStateSnapshot,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "phase27_3" / "panel.csv"


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

    # TrendAnalysisResult.to_dict() currently omits calculated S/R arrays.
    # The replay intentionally preserves that production behavior instead of
    # inventing a more favorable second input contract.
    assert input_data.deterministic_support_levels == ()
    assert input_data.deterministic_resistance_levels == ()
    assert input_data.ma20 is not None
    assert input_data.ma60 is not None


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
def test_metrics_count_confirmed_break_that_quickly_recovers_as_false_invalidation() -> None:
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
                StrategyState.INVALIDATED,
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
                StrategyState.INVALIDATED,
                previous_state=StrategyState.INVALIDATED,
                rule="RULE_CONFIRMED_SUPPORT_BREAK",
                transition=False,
            ),
        ),
        ReplayRecord.minimal(
            close=96.0,
            daily_change_pct=14.3,
            snapshot=_snapshot(
                date(2025, 1, 7),
                StrategyState.WATCHLIST,
                previous_state=StrategyState.INVALIDATED,
                rule="RULE_INITIAL_WATCHLIST",
                transition=True,
            ),
        ),
    ]

    metrics = calculate_metrics(records, DEFAULT_POLICY)
    assert metrics.confirmed_breaks == 1
    assert metrics.false_invalidations == 1


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


@pytest.mark.integration
def test_agent_and_non_agent_authority_sequence_parity() -> None:
    from tests.test_strategy_state_orchestrator import PipelineAttachTestCase, _llm_result

    pipeline = PipelineAttachTestCase()._make_pipeline(flag=True)
    previous = None
    sequence = [
        (date(2026, 7, 7), 4100.0, 1.0),
        (date(2026, 7, 8), 3925.0, -4.27),
        (date(2026, 7, 9), 4620.0, 17.71),
    ]
    for as_of, close, change_pct in sequence:
        trend = PipelineAttachTestCase()._trend(close)
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
            ):
                pipeline._attach_strategy_state_snapshot(
                    result,
                    "2454",
                    trend_result=trend,
                    fundamental_context=PipelineAttachTestCase()._neutral_fundamental(),
                    previous_snapshot=previous,
                )
            outputs.append({
                "snapshot": result.strategy_state_snapshot,
                "operation_advice": result.operation_advice,
                "decision_type": result.decision_type,
                "sniper_points": result.dashboard["battle_plan"]["sniper_points"],
            })
        assert outputs[0] == outputs[1]
        previous = StrategyStateSnapshot.from_dict(outputs[0]["snapshot"])


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
@pytest.mark.skipif(os.environ.get("RUN_PHASE27_EVAL") != "1", reason="set RUN_PHASE27_EVAL=1 for the heavy replay")
def test_real_panel_acceptance(tmp_path: Path) -> None:
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

# -*- coding: utf-8 -*-
"""
Phase 27.1 — offline fixture replay for the deterministic strategy state engine.

Not a backtest framework. A fixed multi-day sequence of deterministic inputs is
replayed through ``evaluate_strategy_state`` and the resulting state trajectory
is checked against explicit expectations plus four aggregate metrics:

    same-input nondeterminism rate       = 0%
    engine-generated anchor lint failure = 0%
    untriggered state flip rate          <= 5% (sequence level)
    fixture expectation pass rate        = 100%

No provider calls, no LLM calls, no DB access, no future-price scoring.
Runs by default (fast, fully offline) — unlike the gated Phase 25 replays.
"""
import json
import unittest
from datetime import date

from src.services.strategy_state_engine import (
    StrategyState,
    StrategyStateInput,
    evaluate_strategy_state,
    lint_buy_zone,
)


def _day(as_of: date, close: float, **overrides) -> StrategyStateInput:
    base = dict(
        symbol="FIX1",
        market="tw",
        instrument_type="stock",
        as_of=as_of,
        close=close,
        previous_close=None,
        daily_change_pct=None,
        ma5=None,
        ma10=None,
        ma20=close * 0.97,
        ma60=close * 0.93,
        deterministic_support_levels=(3880.0,),
        deterministic_resistance_levels=(5200.0,),
        multi_period_trend=None,
        volume_ratio=1.0,
        capital_flow_bias="neutral",
        valuation_zone=None,
        valuation_band_low=None,
        valuation_band_high=None,
        thesis_status="intact",
        deterministic_risk_flags=(),
        data_quality_status="available",
    )
    base.update(overrides)
    return StrategyStateInput(**base)


# One fixed scenario sequence covering the required regimes. Each step:
# (as_of, input_overrides, expected_state_or_None). None = no specific
# expectation for that step (trajectory metrics still apply).
D = date
SEQUENCE = [
    # -- normal trend continuation: price above zone, first sight → wait ----
    (_day(D(2026, 1, 5), 4100.0), StrategyState.WAIT_FOR_PULLBACK),
    (_day(D(2026, 1, 6), 4120.0), StrategyState.WAIT_FOR_PULLBACK),
    # -- sharp rise: overextended vs resistance → do not chase (hysteresis
    #    may hold WAIT for the first days; final expectation checked later) --
    (_day(D(2026, 1, 12), 4550.0), None),
    (_day(D(2026, 1, 13), 4560.0), None),
    # -- sharp drop back toward the zone: single red candle must not reduce --
    (_day(D(2026, 1, 20), 4000.0), None),
    # -- pullback enters the persisted zone → accumulate -------------------
    (_day(D(2026, 1, 21), 3940.0), StrategyState.ACCUMULATE_ZONE),
    # -- boundary oscillation: hysteresis must prevent daily flips ----------
    (_day(D(2026, 1, 22), 3962.0), StrategyState.ACCUMULATE_ZONE),   # just above high, suppressed
    (_day(D(2026, 1, 23), 3941.0), StrategyState.ACCUMULATE_ZONE),
    # -- support break: two consecutive closes below invalidation ----------
    (_day(D(2026, 1, 26), 3700.0), None),                            # breach day 1: pending
    (_day(D(2026, 1, 27), 3690.0), StrategyState.REDUCE_RISK),       # confirmed technical break
]

THESIS_INVALIDATION_STEP = _day(
    D(2026, 2, 2), 4100.0, thesis_status="invalidated"
)


class FixtureReplayTestCase(unittest.TestCase):
    def _replay(self):
        current = None
        trajectory = []
        for inp, expected in SEQUENCE:
            snap = evaluate_strategy_state(inp, previous=current)
            trajectory.append((inp, expected, snap))
            current = snap
        return trajectory

    def test_expectation_pass_rate_100(self) -> None:
        trajectory = self._replay()
        failures = [
            (inp.as_of.isoformat(), expected.value, snap.state.value)
            for inp, expected, snap in trajectory
            if expected is not None and snap.state != expected
        ]
        self.assertEqual(failures, [], f"fixture expectations failed: {failures}")

    def test_sharp_rise_never_becomes_accumulate(self) -> None:
        trajectory = self._replay()
        for inp, _expected, snap in trajectory:
            if inp.close >= 4550.0:
                self.assertNotEqual(snap.state, StrategyState.ACCUMULATE_ZONE)
                self.assertIn(
                    snap.state,
                    (StrategyState.DO_NOT_CHASE, StrategyState.WAIT_FOR_PULLBACK),
                )

    def test_sharp_drop_day_never_reduces_without_trigger(self) -> None:
        trajectory = self._replay()
        drop_day = [t for t in trajectory if t[0].as_of == D(2026, 1, 20)][0]
        self.assertNotIn(
            drop_day[2].state,
            (StrategyState.REDUCE_RISK, StrategyState.INVALIDATED),
        )

    def test_zone_is_persisted_not_recomputed(self) -> None:
        trajectory = self._replay()
        zones = [snap.buy_zone for _i, _e, snap in trajectory if snap.buy_zone]
        self.assertTrue(zones)
        self.assertEqual(len({(z.low, z.high, z.created_at) for z in zones}), 1)
        self.assertTrue(all(z.revision == 0 for z in zones))

    def test_same_input_nondeterminism_rate_zero(self) -> None:
        current = None
        for inp, _expected in SEQUENCE:
            payloads = {
                json.dumps(evaluate_strategy_state(inp, previous=current).to_dict(), sort_keys=True)
                for _ in range(50)
            }
            self.assertEqual(len(payloads), 1, f"nondeterminism at {inp.as_of}")
            current = evaluate_strategy_state(inp, previous=current)

    def test_engine_anchor_lint_failure_rate_zero(self) -> None:
        trajectory = self._replay()
        emitted_zones = [(snap.buy_zone, inp.close) for inp, _e, snap in trajectory if snap.buy_zone]
        self.assertTrue(emitted_zones)
        lint_failures = [
            issue for zone, close in emitted_zones
            if (issue := lint_buy_zone(zone, close)) is not None
        ]
        self.assertEqual(lint_failures, [])

    def test_untriggered_state_flip_rate_within_threshold(self) -> None:
        trajectory = self._replay()
        prev_state = None
        untriggered_flips = 0
        for _inp, _expected, snap in trajectory:
            if prev_state is not None and snap.state != prev_state and not snap.transition_triggered:
                untriggered_flips += 1
            prev_state = snap.state
        rate = untriggered_flips / len(trajectory)
        self.assertEqual(untriggered_flips, 0)
        self.assertLessEqual(rate, 0.05)

    def test_thesis_invalidation_fires_from_any_state(self) -> None:
        trajectory = self._replay()
        final = trajectory[-1][2]
        snap = evaluate_strategy_state(THESIS_INVALIDATION_STEP, previous=final)
        self.assertEqual(snap.state, StrategyState.INVALIDATED)

    def test_no_forbidden_fields_in_any_emitted_snapshot(self) -> None:
        trajectory = self._replay()
        for _inp, _expected, snap in trajectory:
            blob = json.dumps(snap.to_dict(), ensure_ascii=False)
            for forbidden in ("target_price", "fair_value", "recommendation",
                              "buy_signal", "sell_signal"):
                self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main()

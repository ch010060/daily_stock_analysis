# -*- coding: utf-8 -*-
"""
Phase 27.1 — tests for src.services.strategy_state_engine.

Pure-function tests: no DB, no network, no LLM, no providers, no production
history rows. Fixtures encode sanitized numeric facts from the Phase 27 audit
(the 2454 limit-down day and the 07-07 → 07-09 pullback-into-zone
contradiction) without copying any report prose.
"""
import json
import unittest
from datetime import date

from src.services.strategy_state_engine import (
    BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED,
    DEFAULT_POLICY,
    NO_DETERMINISTIC_ZONE_BASIS,
    RULE_CONFIRMED_SUPPORT_BREAK,
    RULE_CONFIRMED_SUPPORT_RECLAIM,
    RULE_HYSTERESIS_HOLD,
    RULE_INSUFFICIENT_DATA,
    RULE_RISK_REWARD_OVEREXTENDED,
    RULE_SUPPORT_RECLAIM_PENDING,
    RULE_TERMINAL_STATE_PERSISTED,
    RULE_THESIS_INVALIDATED,
    RULE_UNSUPPORTED_INSTRUMENT,
    RULE_VALID_BUY_ZONE_ENTERED,
    SUPPORT_AND_VALUATION_DO_NOT_OVERLAP,
    STATE_ACTION_MAP,
    BuyZone,
    StrategyPolicy,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
    evaluate_strategy_state,
    lint_buy_zone,
)


def _input(**overrides) -> StrategyStateInput:
    base = dict(
        symbol="2454",
        market="tw",
        instrument_type="stock",
        as_of=date(2026, 7, 9),
        close=3925.0,
        previous_close=3995.0,
        daily_change_pct=-1.75,
        ma5=4054.0,
        ma10=4100.0,
        ma20=4200.0,
        ma60=3900.0,
        deterministic_support_levels=(3880.0,),
        deterministic_resistance_levels=(4500.0,),
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


def _wait_snapshot(zone_low=3880.0, zone_high=3950.0, as_of=date(2026, 7, 7)) -> StrategyStateSnapshot:
    """A persisted WAIT_FOR_PULLBACK snapshot mirroring the audited 2454 case."""
    zone = BuyZone(
        low=zone_low, high=zone_high,
        basis=("support:3880.0", "valuation_band"),
        created_at=date(2026, 7, 1), revision=0,
        zone_type="VALUATION_AND_TECHNICAL",
    )
    return StrategyStateSnapshot(
        schema_version=1,
        symbol="2454", market="tw", as_of=as_of,
        state=StrategyState.WAIT_FOR_PULLBACK, previous_state=StrategyState.WATCHLIST,
        actionability="ACTIONABLE_WAIT", operation_advice="等待回檔", decision_type="wait",
        buy_zone=zone, invalidation_level=zone_low * (1 - 0.02),
        transition_rule_id="RULE_WAIT_FOR_PULLBACK", transition_triggered=True,
        state_entered_at=date(2026, 7, 1), last_transition_at=date(2026, 7, 1),
        days_in_state=6, transition_count_in_window=0, invalidation_confirm_count=0,
        reasons=(), data_limitations=(),
    )


class LargeRallyTestCase(unittest.TestCase):
    """Test 1 — a large green candle alone must not become bullish action."""

    def test_limit_up_without_thesis_improvement_is_do_not_chase(self) -> None:
        inp = _input(
            close=4620.0, previous_close=4200.0, daily_change_pct=9.9,
            deterministic_support_levels=(3880.0,),
            deterministic_resistance_levels=(4700.0,),  # reward 80 vs risk ~817 → RR << 2
            ma5=4300.0, ma10=4250.0, ma20=4150.0, ma60=3900.0,
        )
        snap = evaluate_strategy_state(inp, previous=None)

        self.assertNotEqual(snap.state, StrategyState.ACCUMULATE_ZONE)
        self.assertEqual(snap.state, StrategyState.DO_NOT_CHASE)
        self.assertEqual(snap.transition_rule_id, RULE_RISK_REWARD_OVEREXTENDED)
        # no actionable buy zone fabricated near current close
        if snap.buy_zone is not None:
            midpoint = (snap.buy_zone.low + snap.buy_zone.high) / 2
            self.assertGreater(abs(midpoint - inp.close) / inp.close, 0.01)

    def test_above_all_resistance_is_do_not_chase(self) -> None:
        inp = _input(
            close=4800.0, daily_change_pct=9.9,
            deterministic_support_levels=(3880.0,),
            deterministic_resistance_levels=(4500.0,),  # close above every resistance
        )
        snap = evaluate_strategy_state(inp, previous=None)
        self.assertEqual(snap.state, StrategyState.DO_NOT_CHASE)


class LargeDropTestCase(unittest.TestCase):
    """Test 2 — a large red candle alone must not become REDUCE/INVALIDATED
    (fixture modeled on the audited 2454 −9.98% day)."""

    def test_limit_down_without_invalidation_keeps_state(self) -> None:
        prev = _wait_snapshot(zone_low=3900.0, zone_high=3980.0)
        # close 3880 < zone.low but above invalidation (3900*0.98=3822); one
        # day only — not confirmed.
        inp = _input(
            as_of=date(2026, 7, 9), close=3880.0, previous_close=4310.0,
            daily_change_pct=-9.98,
            deterministic_support_levels=(3800.0,),
        )
        snap = evaluate_strategy_state(inp, previous=prev)

        self.assertNotEqual(snap.state, StrategyState.REDUCE_RISK)
        self.assertNotEqual(snap.state, StrategyState.INVALIDATED)
        self.assertNotIn(snap.decision_type, ("sell", "reduce", "invalidated"))

    def test_breach_requires_confirmation_days(self) -> None:
        prev = _wait_snapshot(zone_low=3900.0, zone_high=3980.0)
        below_invalidation = 3700.0  # < 3822 invalidation level

        day1 = evaluate_strategy_state(
            _input(as_of=date(2026, 7, 9), close=below_invalidation), previous=prev
        )
        self.assertNotEqual(day1.state, StrategyState.INVALIDATED)
        self.assertEqual(day1.invalidation_confirm_count, 1)

        day2 = evaluate_strategy_state(
            _input(as_of=date(2026, 7, 10), close=below_invalidation), previous=day1
        )
        self.assertEqual(day2.state, StrategyState.REDUCE_RISK)
        self.assertEqual(day2.transition_rule_id, RULE_CONFIRMED_SUPPORT_BREAK)
        self.assertIsNone(day2.buy_zone)

    def test_one_day_reclaim_does_not_reactivate(self) -> None:
        prev = _wait_snapshot(zone_low=3900.0, zone_high=3980.0)
        day1 = evaluate_strategy_state(
            _input(as_of=date(2026, 7, 9), close=3700.0), previous=prev
        )
        reduced = evaluate_strategy_state(
            _input(as_of=date(2026, 7, 10), close=3700.0), previous=day1
        )
        bounced = evaluate_strategy_state(
            _input(as_of=date(2026, 7, 13), close=3850.0), previous=reduced
        )

        self.assertEqual(bounced.state, StrategyState.REDUCE_RISK)
        self.assertEqual(bounced.transition_rule_id, RULE_SUPPORT_RECLAIM_PENDING)
        self.assertEqual(bounced.reclaim_confirm_count, 1)
        self.assertIsNone(bounced.buy_zone)

    def test_confirmed_reclaim_exits_to_watchlist_without_old_zone(self) -> None:
        prev = _wait_snapshot(zone_low=3900.0, zone_high=3980.0)
        day1 = evaluate_strategy_state(_input(as_of=date(2026, 7, 9), close=3700.0), previous=prev)
        reduced = evaluate_strategy_state(_input(as_of=date(2026, 7, 10), close=3700.0), previous=day1)
        reclaim1 = evaluate_strategy_state(_input(as_of=date(2026, 7, 13), close=3850.0), previous=reduced)
        reclaim2 = evaluate_strategy_state(_input(as_of=date(2026, 7, 14), close=3860.0), previous=reclaim1)

        self.assertEqual(reclaim2.state, StrategyState.WATCHLIST)
        self.assertEqual(reclaim2.transition_rule_id, RULE_CONFIRMED_SUPPORT_RECLAIM)
        self.assertNotEqual(reclaim2.state, StrategyState.ACCUMULATE_ZONE)
        self.assertIsNone(reclaim2.buy_zone)
        self.assertIsNone(reclaim2.invalidation_level)
        self.assertEqual(reclaim2.reclaim_confirm_count, 0)

    def test_reclaim_counter_resets_below_breached_level(self) -> None:
        prev = _wait_snapshot(zone_low=3900.0, zone_high=3980.0)
        day1 = evaluate_strategy_state(_input(as_of=date(2026, 7, 9), close=3700.0), previous=prev)
        reduced = evaluate_strategy_state(_input(as_of=date(2026, 7, 10), close=3700.0), previous=day1)
        reclaim1 = evaluate_strategy_state(_input(as_of=date(2026, 7, 13), close=3850.0), previous=reduced)
        failed = evaluate_strategy_state(_input(as_of=date(2026, 7, 14), close=3700.0), previous=reclaim1)

        self.assertEqual(failed.state, StrategyState.REDUCE_RISK)
        self.assertEqual(failed.reclaim_confirm_count, 0)
        self.assertEqual(failed.transition_rule_id, RULE_CONFIRMED_SUPPORT_BREAK)

    def test_thesis_invalidated_bypasses_hysteresis(self) -> None:
        prev = _wait_snapshot()
        inp = _input(thesis_status="invalidated", as_of=date(2026, 7, 8))
        snap = evaluate_strategy_state(inp, previous=prev)
        self.assertEqual(snap.state, StrategyState.INVALIDATED)
        self.assertEqual(snap.transition_rule_id, RULE_THESIS_INVALIDATED)

    def test_terminal_invalidation_is_absorbing_without_reinstatement_contract(self) -> None:
        terminal = evaluate_strategy_state(
            _input(thesis_status="invalidated", as_of=date(2026, 7, 8)),
            previous=_wait_snapshot(),
        )
        persisted = evaluate_strategy_state(
            _input(thesis_status=None, as_of=date(2026, 7, 9)),
            previous=terminal,
        )

        self.assertEqual(persisted.state, StrategyState.INVALIDATED)
        self.assertEqual(persisted.transition_rule_id, RULE_TERMINAL_STATE_PERSISTED)


class PullbackIntoZoneTestCase(unittest.TestCase):
    """Test 3 — the audited 2454 07-07 → 07-09 contradiction, fixed."""

    def test_pullback_into_persisted_zone_becomes_accumulate(self) -> None:
        prev = _wait_snapshot(zone_low=3880.0, zone_high=3950.0, as_of=date(2026, 7, 7))
        inp = _input(as_of=date(2026, 7, 9), close=3925.0, ma5=4054.0)
        snap = evaluate_strategy_state(inp, previous=prev)

        self.assertEqual(snap.state, StrategyState.ACCUMULATE_ZONE)
        self.assertEqual(snap.transition_rule_id, RULE_VALID_BUY_ZONE_ENTERED)
        # the zone is the persisted one — NOT moved up to the new MA5 (4054)
        self.assertEqual(snap.buy_zone.low, 3880.0)
        self.assertEqual(snap.buy_zone.high, 3950.0)
        self.assertEqual(snap.buy_zone.created_at, date(2026, 7, 1))
        self.assertEqual(snap.buy_zone.revision, 0)
        self.assertEqual(snap.decision_type, "buy")

    def test_short_ma_values_in_explicit_array_do_not_bypass_anchor_guard(self) -> None:
        inp = _input(
            close=100.0,
            ma5=99.0,
            ma10=98.0,
            ma20=90.0,
            ma60=80.0,
            deterministic_support_levels=(99.0, 98.0, 90.0),
            deterministic_resistance_levels=(130.0,),
        )

        snap = evaluate_strategy_state(inp, previous=None)

        self.assertIsNotNone(snap.buy_zone)
        self.assertEqual(snap.buy_zone.basis, ("ma60",))

    def test_distinct_explicit_support_remains_preferred_over_ma_fallback(self) -> None:
        inp = _input(
            close=100.0,
            ma5=99.0,
            ma10=98.0,
            ma20=90.0,
            ma60=80.0,
            deterministic_support_levels=(92.0, 99.0, 98.0),
            deterministic_resistance_levels=(130.0,),
        )

        snap = evaluate_strategy_state(inp, previous=None)

        self.assertIsNotNone(snap.buy_zone)
        self.assertEqual(snap.buy_zone.basis, ("support:92.0",))

    def test_market_structure_support_precedes_legacy_and_retains_provenance_at_ma_collision(self) -> None:
        inp = _input(
            close=100.0,
            ma20=92.0,
            ma60=80.0,
            market_structure_support_levels=(92.0,),
            market_structure_resistance_levels=(130.0,),
            deterministic_support_levels=(91.0,),
            deterministic_resistance_levels=(140.0,),
        )

        snap = evaluate_strategy_state(inp, previous=None)

        self.assertIsNotNone(snap.buy_zone)
        self.assertEqual(snap.buy_zone.basis, ("market_structure_support:92.0",))

    def test_legacy_missing_support_array_uses_long_ma_fallback(self) -> None:
        inp = _input(
            close=100.0,
            ma5=99.0,
            ma10=98.0,
            ma20=90.0,
            ma60=80.0,
            deterministic_support_levels=(),
            deterministic_resistance_levels=(130.0,),
        )

        snap = evaluate_strategy_state(inp, previous=None)

        self.assertIsNotNone(snap.buy_zone)
        self.assertEqual(snap.buy_zone.basis, ("ma60",))


class SameInputDeterminismTestCase(unittest.TestCase):
    """Test 4 — 50 repetitions, byte-identical serialized output."""

    def test_fifty_repetitions_identical(self) -> None:
        prev = _wait_snapshot()
        inp = _input()
        payloads = {
            json.dumps(evaluate_strategy_state(inp, previous=prev).to_dict(), sort_keys=True)
            for _ in range(50)
        }
        self.assertEqual(len(payloads), 1)


class UnchangedSnapshotTestCase(unittest.TestCase):
    """Test 5 — unchanged deterministic technical snapshot ⇒ unchanged state,
    zone, and invalidation level across two evaluations."""

    def test_two_days_same_technicals_same_outputs(self) -> None:
        prev = _wait_snapshot()
        day1 = evaluate_strategy_state(_input(as_of=date(2026, 7, 10), close=4000.0), previous=prev)
        day2 = evaluate_strategy_state(_input(as_of=date(2026, 7, 11), close=4000.0), previous=day1)

        self.assertEqual(day2.state, day1.state)
        self.assertEqual(day2.buy_zone, day1.buy_zone)
        self.assertEqual(day2.invalidation_level, day1.invalidation_level)


class AnchorLintTestCase(unittest.TestCase):
    """Test 6 — current-price short-MA-only zones are rejected."""

    def test_ma5_anchored_zone_near_close_is_rejected(self) -> None:
        # No support levels, no long MAs — only MA5/MA10 near the close, the
        # exact production pattern (LLY zone = current price ± ~0.3%).
        inp = _input(
            close=1216.95, ma5=1217.0, ma10=1220.0, ma20=None, ma60=None,
            deterministic_support_levels=(),
            deterministic_resistance_levels=(1300.0,),
        )
        snap = evaluate_strategy_state(inp, previous=None)

        self.assertIsNone(snap.buy_zone)
        self.assertIn(BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED, snap.reasons)
        self.assertNotEqual(snap.state, StrategyState.ACCUMULATE_ZONE)

    def test_lint_function_direct(self) -> None:
        zone = BuyZone(low=1210.0, high=1224.0, basis=("ma5",),
                       created_at=date(2026, 7, 9), revision=0, zone_type="TECHNICAL_ONLY")
        self.assertEqual(lint_buy_zone(zone, close=1216.95), BUY_ZONE_CURRENT_PRICE_ANCHOR_REJECTED)

    def test_lint_passes_for_support_based_zone(self) -> None:
        zone = BuyZone(low=3802.0, high=3958.0, basis=("support:3880.0",),
                       created_at=date(2026, 7, 9), revision=0, zone_type="TECHNICAL_ONLY")
        self.assertIsNone(lint_buy_zone(zone, close=3925.0))


class HysteresisTestCase(unittest.TestCase):
    """Test 7 — three-day oscillation inside support ±2% produces at most one
    state transition."""

    def test_boundary_oscillation_capped_at_one_transition(self) -> None:
        prev = _wait_snapshot(zone_low=3880.0, zone_high=3950.0, as_of=date(2026, 7, 4))
        transitions = 0
        current = prev
        sequence = [
            (date(2026, 7, 7), 3940.0),   # dips into zone → transition allowed
            (date(2026, 7, 8), 3960.0),   # pops just above zone.high
            (date(2026, 7, 9), 3935.0),   # dips back in
        ]
        rule_ids = []
        for as_of, close in sequence:
            snap = evaluate_strategy_state(_input(as_of=as_of, close=close), previous=current)
            if snap.transition_triggered:
                transitions += 1
            rule_ids.append(snap.transition_rule_id)
            current = snap

        self.assertLessEqual(transitions, 1)
        self.assertIn(RULE_HYSTERESIS_HOLD, rule_ids)
        # zone never revised during the oscillation
        self.assertEqual(current.buy_zone.revision, 0)


class EmptyIntersectionTestCase(unittest.TestCase):
    """Test 8 — support band and valuation band do not overlap ⇒ no zone."""

    def test_disjoint_bands_produce_no_zone(self) -> None:
        inp = _input(
            close=4100.0,
            deterministic_support_levels=(3880.0,),   # tech band ≈ [3802, 3958]
            valuation_band_low=3000.0, valuation_band_high=3500.0,  # far below
        )
        snap = evaluate_strategy_state(inp, previous=None)

        self.assertIsNone(snap.buy_zone)
        self.assertIn(SUPPORT_AND_VALUATION_DO_NOT_OVERLAP, snap.reasons)
        self.assertNotEqual(snap.state, StrategyState.ACCUMULATE_ZONE)


class InsufficientDataTestCase(unittest.TestCase):
    """Test 9 — documented policy: missing close/quality ⇒ UNSUPPORTED;
    no zone basis ⇒ WATCHLIST with limitation code."""

    def test_missing_close_is_unsupported(self) -> None:
        snap = evaluate_strategy_state(_input(close=None), previous=None)
        self.assertEqual(snap.state, StrategyState.UNSUPPORTED)
        self.assertEqual(snap.transition_rule_id, RULE_INSUFFICIENT_DATA)
        self.assertIsNone(snap.buy_zone)

    def test_fetch_failed_quality_is_unsupported(self) -> None:
        snap = evaluate_strategy_state(_input(data_quality_status="fetch_failed"), previous=None)
        self.assertEqual(snap.state, StrategyState.UNSUPPORTED)

    def test_no_zone_basis_is_watchlist_with_limitation(self) -> None:
        inp = _input(
            deterministic_support_levels=(), ma5=None, ma10=None, ma20=None, ma60=None,
            deterministic_resistance_levels=(),
        )
        snap = evaluate_strategy_state(inp, previous=None)
        self.assertEqual(snap.state, StrategyState.WATCHLIST)
        self.assertIn(NO_DETERMINISTIC_ZONE_BASIS, snap.data_limitations)
        self.assertIsNone(snap.buy_zone)

    def test_etf_is_unsupported(self) -> None:
        snap = evaluate_strategy_state(_input(instrument_type="etf"), previous=None)
        self.assertEqual(snap.state, StrategyState.UNSUPPORTED)
        self.assertEqual(snap.transition_rule_id, RULE_UNSUPPORTED_INSTRUMENT)


class SerializationTestCase(unittest.TestCase):
    """Test 10 — JSON round trip preserves the full contract."""

    def test_round_trip(self) -> None:
        prev = _wait_snapshot()
        snap = evaluate_strategy_state(_input(), previous=prev)
        payload = json.dumps(snap.to_dict(), sort_keys=True, ensure_ascii=False)
        restored = StrategyStateSnapshot.from_dict(json.loads(payload))
        self.assertEqual(restored, snap)
        self.assertEqual(
            json.dumps(restored.to_dict(), sort_keys=True, ensure_ascii=False), payload
        )

    def test_forbidden_fields_absent(self) -> None:
        snap = evaluate_strategy_state(_input(), previous=_wait_snapshot())
        blob = json.dumps(snap.to_dict(), ensure_ascii=False)
        for forbidden in ("target_price", "fair_value", "recommendation", "buy_signal", "sell_signal"):
            self.assertNotIn(forbidden, blob)

    def test_legacy_snapshot_without_reclaim_counter_defaults_to_zero(self) -> None:
        payload = evaluate_strategy_state(_input(), previous=_wait_snapshot()).to_dict()
        payload.pop("reclaim_confirm_count")

        restored = StrategyStateSnapshot.from_dict(payload)

        self.assertEqual(restored.reclaim_confirm_count, 0)


class FixedMappingTestCase(unittest.TestCase):
    def test_every_state_has_exactly_one_mapping(self) -> None:
        self.assertEqual(set(STATE_ACTION_MAP.keys()), set(StrategyState))
        for actionability, advice, decision in STATE_ACTION_MAP.values():
            self.assertTrue(actionability and advice and decision)

    def test_policy_is_frozen_single_source(self) -> None:
        with self.assertRaises(Exception):
            DEFAULT_POLICY.minimum_risk_reward = 1.0  # type: ignore[misc]
        self.assertEqual(DEFAULT_POLICY, StrategyPolicy())
        self.assertEqual(DEFAULT_POLICY.reclaim_confirmation_days, 2)


class IsolationGuardTestCase(unittest.TestCase):
    """Production-path protection: engine stays pure and unintegrated."""

    _ENGINE_PATH = "src/services/strategy_state_engine.py"
    _FORBIDDEN_IMPORT_TOKENS = (
        "import sqlite3", "sqlalchemy", "from src.storage", "src.core.pipeline",
        "src.analyzer", "data_provider", "litellm", "openai", "requests",
        "yfinance", "FinMind", "os.environ", "getenv", "load_dotenv",
        "datetime.now", "date.today",
    )
    _PRODUCTION_CONSUMERS = (
        "src/core/pipeline.py",
        "src/analyzer.py",
        "src/services/history_service.py",
    )

    def test_engine_has_no_forbidden_imports_or_calls(self) -> None:
        with open(self._ENGINE_PATH, encoding="utf-8") as f:
            source = f.read()
        for token in self._FORBIDDEN_IMPORT_TOKENS:
            self.assertNotIn(token, source, f"engine must not reference {token!r}")

    def test_engine_never_references_production_db(self) -> None:
        # literals split so this test file never contains the joined tokens
        prod_db_token = "stock_analysis." + "db"
        prod_table_token = "analysis_" + "history"
        with open(self._ENGINE_PATH, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn(prod_db_token, source)
        self.assertNotIn(prod_table_token, source)
        with open(__file__, encoding="utf-8") as f:
            test_source = f.read()
        # this test file itself must not resolve to the production DB either
        self.assertNotIn(prod_db_token, test_source)

    def test_no_production_path_imports_engine(self) -> None:
        import glob
        consumers = list(self._PRODUCTION_CONSUMERS)
        consumers += glob.glob("api/**/*.py", recursive=True)
        for path in consumers:
            with open(path, encoding="utf-8") as f:
                self.assertNotIn(
                    "strategy_state_engine", f.read(),
                    f"{path} must not import the engine in Phase 27.1",
                )

    def test_engine_importable_without_env_or_db(self) -> None:
        import importlib
        import src.services.strategy_state_engine as engine_module
        importlib.reload(engine_module)  # re-import cleanly; no env/db needed


if __name__ == "__main__":
    unittest.main()

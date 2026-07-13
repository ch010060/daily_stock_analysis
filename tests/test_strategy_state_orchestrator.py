# -*- coding: utf-8 -*-
"""
Phase 27.2 — tests for strategy-state orchestration, persistence, and
report authority transfer.

Database rule: every DB-touching test in this file uses a TEMPORARY SQLite
database created under a per-test temp directory. A fail-fast guard aborts
if the resolved path ever points at the production database. The production
DB is never opened.
"""
import json
import os
import tempfile
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.strategy_state_engine import (
    STATE_ACTION_MAP,
    BuyZone,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
)
from src.services.strategy_state_orchestrator import (
    BLOCKING_READINESS_DEFECTS,
    ENHANCEMENT_READINESS_DEFECTS,
    INVALID_INSTRUMENT_TYPE,
    INVALID_TRADING_DATE,
    LLM_ACTION_OVERRIDDEN_BY_STRATEGY_STATE,
    LLM_BUY_ZONE_SUPPRESSED,
    LLM_TREND_LABEL_CONFLICT,
    MISSING_CURRENT_CLOSE,
    MISSING_PREVIOUS_CLOSE,
    MISSING_RESISTANCE_LEVEL,
    MISSING_SUPPORT_LEVEL,
    PROVIDER_DATA_UNAVAILABLE,
    STRATEGY_POSTURE_MAP,
    StrategyDataUnavailableError,
    apply_strategy_authority,
    attach_strategy_state,
    build_previous_state_prompt_block,
    build_strategy_state_input,
    load_previous_strategy_snapshot,
    validate_strategy_state_input_readiness,
)

_PROD_DB_TOKEN = "stock_analysis." + "db"


def _snapshot(
    state: StrategyState,
    *,
    zone: BuyZone = None,
    invalidation: float = None,
    as_of: date = date(2026, 7, 7),
) -> StrategyStateSnapshot:
    actionability, advice, decision = STATE_ACTION_MAP[state]
    return StrategyStateSnapshot(
        schema_version=1,
        symbol="2454", market="tw", as_of=as_of,
        state=state, previous_state=None,
        actionability=actionability, operation_advice=advice, decision_type=decision,
        buy_zone=zone, invalidation_level=invalidation,
        transition_rule_id="RULE_WAIT_FOR_PULLBACK", transition_triggered=False,
        state_entered_at=as_of, last_transition_at=date(2026, 7, 1),
        days_in_state=0, transition_count_in_window=0, invalidation_confirm_count=0,
        reasons=(), data_limitations=(),
    )


def _zone_2454() -> BuyZone:
    return BuyZone(
        low=3880.0, high=3950.0, basis=("support:3880.0", "valuation_band"),
        created_at=date(2026, 7, 1), revision=0, zone_type="VALUATION_AND_TECHNICAL",
    )


def _llm_result(**overrides) -> SimpleNamespace:
    base = dict(
        code="2454", name="聯發科",
        operation_advice="買進", decision_type="buy",
        trend_prediction="強烈看多", sentiment_score=82,
        dashboard={
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "4050-4080（回踩MA5附近）",
                    "secondary_buy": "4000",
                    "stop_loss": "3900",
                    "take_profit": "4400",
                }
            }
        },
        strategy_state_snapshot=None,
        strategy_authority_diagnostics=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Authority transfer (pure — no DB)
# ---------------------------------------------------------------------------

class AuthorityTransferTestCase(unittest.TestCase):
    def test_llm_buy_overridden_by_do_not_chase(self) -> None:
        result = _llm_result()
        snap = _snapshot(StrategyState.DO_NOT_CHASE)
        conflicts = apply_strategy_authority(result, snap)

        self.assertEqual(result.operation_advice, "不追價")
        self.assertEqual(result.decision_type, "avoid")
        self.assertIn(LLM_ACTION_OVERRIDDEN_BY_STRATEGY_STATE, conflicts)
        diags = result.strategy_authority_diagnostics
        self.assertEqual(diags["llm_original_operation_advice"], "買進")
        self.assertEqual(diags["llm_original_decision_type"], "buy")
        self.assertEqual(diags["strategy_posture"], "neutral_overextended")

    def test_llm_sell_overridden_by_wait_for_pullback(self) -> None:
        result = _llm_result(operation_advice="賣出", decision_type="sell", trend_prediction="強烈看空", sentiment_score=22)
        snap = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454())
        apply_strategy_authority(result, snap)

        self.assertEqual(result.operation_advice, "等待回檔")
        self.assertEqual(result.decision_type, "wait")

    def test_low_llm_score_cannot_override_accumulate(self) -> None:
        result = _llm_result(operation_advice="觀望", decision_type="hold", sentiment_score=25, trend_prediction="看空")
        snap = _snapshot(StrategyState.ACCUMULATE_ZONE, zone=_zone_2454(), invalidation=3802.4)
        conflicts = apply_strategy_authority(result, snap)

        self.assertEqual(result.decision_type, "buy")
        self.assertEqual(result.operation_advice, "分批布局")
        # score is preserved as diagnostics only, never drives the action
        self.assertEqual(result.strategy_authority_diagnostics["llm_original_sentiment_score"], 25)
        self.assertIn(LLM_TREND_LABEL_CONFLICT, conflicts)  # 看空 vs ACCUMULATE

    def test_high_llm_score_cannot_override_do_not_chase(self) -> None:
        result = _llm_result(sentiment_score=95, trend_prediction="強烈看多")
        snap = _snapshot(StrategyState.DO_NOT_CHASE)
        conflicts = apply_strategy_authority(result, snap)

        self.assertEqual(result.decision_type, "avoid")
        self.assertIn(LLM_TREND_LABEL_CONFLICT, conflicts)

    def test_engine_zone_overrides_llm_zone(self) -> None:
        result = _llm_result()
        snap = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), invalidation=3802.4)
        conflicts = apply_strategy_authority(result, snap)

        sniper = result.dashboard["battle_plan"]["sniper_points"]
        self.assertIn("3880.0～3950.0", sniper["ideal_buy"])
        self.assertNotIn("4050", sniper["ideal_buy"])  # LLM zone gone
        self.assertIn("3802.4", sniper["stop_loss"])
        self.assertIn(LLM_BUY_ZONE_SUPPRESSED, conflicts)

    def test_engine_none_zone_suppresses_llm_zone(self) -> None:
        result = _llm_result()
        snap = StrategyStateSnapshot(
            schema_version=1, symbol="2454", market="tw", as_of=date(2026, 7, 7),
            state=StrategyState.WATCHLIST, previous_state=None,
            actionability="WATCH", operation_advice="觀察", decision_type="watch",
            buy_zone=None, invalidation_level=None,
            transition_rule_id="RULE_INITIAL_WATCHLIST", transition_triggered=False,
            state_entered_at=date(2026, 7, 7), last_transition_at=date(2026, 7, 7),
            days_in_state=0, transition_count_in_window=0, invalidation_confirm_count=0,
            reasons=("risk_reward_below_threshold",), data_limitations=(),
        )
        conflicts = apply_strategy_authority(result, snap)

        sniper = result.dashboard["battle_plan"]["sniper_points"]
        self.assertIn("無有效買區", sniper["ideal_buy"])
        self.assertIn("risk_reward_below_threshold", sniper["ideal_buy"])
        self.assertNotIn("4050", sniper["ideal_buy"])
        self.assertIn(LLM_BUY_ZONE_SUPPRESSED, conflicts)

    def test_unsupported_state_does_not_take_authority(self) -> None:
        result = _llm_result(operation_advice="持有", decision_type="hold")
        input_data = MagicMock()
        with patch(
            "src.services.strategy_state_orchestrator.evaluate_strategy_state",
            return_value=_snapshot(StrategyState.UNSUPPORTED),
        ):
            attach_strategy_state(result, input_data, None)

        # snapshot attached but marked non-authoritative; LLM fields intact
        self.assertFalse(result.strategy_state_snapshot["authoritative"])
        self.assertEqual(result.operation_advice, "持有")
        self.assertEqual(result.decision_type, "hold")
        self.assertIsNone(result.strategy_authority_diagnostics)

    def test_posture_map_covers_all_states_without_numbers(self) -> None:
        self.assertEqual(set(STRATEGY_POSTURE_MAP.keys()), set(StrategyState))
        for posture in STRATEGY_POSTURE_MAP.values():
            self.assertIsInstance(posture, str)
            self.assertFalse(any(ch.isdigit() for ch in posture))


# ---------------------------------------------------------------------------
# Input construction (deterministic sources only)
# ---------------------------------------------------------------------------

class InputConstructionTestCase(unittest.TestCase):
    def test_builds_from_trend_and_river(self) -> None:
        trend = {
            "current_price": 3925.0, "ma5": 4054.0, "ma10": 4100.0,
            "ma20": 4200.0, "ma60": 3900.0, "volume_ratio_5d": 1.2,
            "support_levels": [3880.0, 3700.0], "resistance_levels": [4500.0],
        }
        river = {
            "enabled": True, "neutral_multiple": 26,
            "current": {"zone": "overvalued"},
            "points": [{"bands": {"per_26": 4100.5}}],
        }
        inp = build_strategy_state_input(
            symbol="2454", market="tw", instrument_type="stock",
            as_of=date(2026, 7, 9), trend_dict=trend, change_pct=-1.75,
            valuation_river_snapshot=river, capital_flow_bias="neutral",
        )
        self.assertEqual(inp.close, 3925.0)
        self.assertEqual(inp.deterministic_support_levels, (3880.0, 3700.0))
        self.assertEqual(inp.valuation_zone, "overvalued")
        self.assertEqual(inp.valuation_band_high, 4100.5)
        self.assertAlmostEqual(inp.previous_close, 3994.9109, places=3)
        self.assertEqual(inp.data_quality_status, "available")
        # deterministic-only contract: thesis/flags never fabricated
        self.assertIsNone(inp.thesis_status)
        self.assertEqual(inp.deterministic_risk_flags, ())

    def test_missing_trend_degrades_to_missing_quality(self) -> None:
        inp = build_strategy_state_input(
            symbol="X", market="us", instrument_type="stock",
            as_of=date(2026, 7, 9), trend_dict=None, change_pct=None,
            valuation_river_snapshot=None, capital_flow_bias=None,
        )
        self.assertIsNone(inp.close)
        self.assertEqual(inp.data_quality_status, "missing")


# ---------------------------------------------------------------------------
# Phase 27.2R: central readiness validator
# ---------------------------------------------------------------------------

def _full_input(**overrides) -> StrategyStateInput:
    base = dict(
        symbol="2454", market="tw", instrument_type="stock", as_of=date(2026, 7, 9),
        close=3925.0, previous_close=3994.91, daily_change_pct=-1.75,
        ma5=4054.0, ma10=4100.0, ma20=4200.0, ma60=3900.0,
        deterministic_support_levels=(3880.0,), deterministic_resistance_levels=(4500.0,),
        data_quality_status="available",
    )
    base.update(overrides)
    return StrategyStateInput(**base)


class ReadinessValidatorTestCase(unittest.TestCase):
    def test_fully_populated_input_is_never_blocked(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(_full_input())
        self.assertFalse(blocked)
        self.assertEqual(defects, ())

    def test_missing_close_blocks(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(_full_input(close=None))
        self.assertTrue(blocked)
        self.assertIn(MISSING_CURRENT_CLOSE, defects)

    def test_provider_data_unavailable_blocks(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(
            _full_input(data_quality_status="fetch_failed")
        )
        self.assertTrue(blocked)
        self.assertIn(PROVIDER_DATA_UNAVAILABLE, defects)

    def test_non_stock_instrument_blocks(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(
            _full_input(instrument_type="etf")
        )
        self.assertTrue(blocked)
        self.assertIn(INVALID_INSTRUMENT_TYPE, defects)

    def test_invalid_trading_date_blocks(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(_full_input(as_of=None))
        self.assertTrue(blocked)
        self.assertIn(INVALID_TRADING_DATE, defects)

    def test_missing_previous_close_alone_does_not_block(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(
            _full_input(previous_close=None)
        )
        self.assertFalse(blocked)
        self.assertIn(MISSING_PREVIOUS_CLOSE, defects)

    def test_missing_support_alone_does_not_block(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(
            _full_input(deterministic_support_levels=(), ma20=None, ma60=None)
        )
        self.assertFalse(blocked)
        self.assertIn(MISSING_SUPPORT_LEVEL, defects)

    def test_long_ma_alone_satisfies_support_requirement(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(
            _full_input(deterministic_support_levels=(), ma20=None, ma60=3900.0)
        )
        self.assertFalse(blocked)
        self.assertNotIn(MISSING_SUPPORT_LEVEL, defects)

    def test_missing_resistance_alone_does_not_block(self) -> None:
        blocked, defects = validate_strategy_state_input_readiness(
            _full_input(deterministic_resistance_levels=())
        )
        self.assertFalse(blocked)
        self.assertIn(MISSING_RESISTANCE_LEVEL, defects)

    def test_missing_valuation_alone_produces_no_defect_code(self) -> None:
        """Valuation isn't in the required/optional defect vocabulary at all —
        its absence is handled natively by the engine's TECHNICAL_ONLY path."""
        blocked, defects = validate_strategy_state_input_readiness(_full_input())
        self.assertFalse(blocked)
        self.assertNotIn("MISSING_VALUATION", defects)

    def test_blocking_and_enhancement_sets_are_disjoint(self) -> None:
        self.assertEqual(BLOCKING_READINESS_DEFECTS & ENHANCEMENT_READINESS_DEFECTS, frozenset())

    def test_strategy_data_unavailable_error_carries_symbol_and_defects(self) -> None:
        err = StrategyDataUnavailableError("2454", (MISSING_CURRENT_CLOSE, PROVIDER_DATA_UNAVAILABLE))
        self.assertEqual(err.symbol, "2454")
        self.assertEqual(err.defects, (MISSING_CURRENT_CLOSE, PROVIDER_DATA_UNAVAILABLE))
        self.assertIn("2454", str(err))


# ---------------------------------------------------------------------------
# Prompt continuity block
# ---------------------------------------------------------------------------

class PromptBlockTestCase(unittest.TestCase):
    def test_none_previous_yields_none(self) -> None:
        self.assertIsNone(build_previous_state_prompt_block(None))

    def test_block_is_compact_and_deterministic_only(self) -> None:
        prev = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), invalidation=3802.4)
        block = build_previous_state_prompt_block(prev)

        self.assertIn("WAIT_FOR_PULLBACK", block)
        self.assertIn("3880.0～3950.0", block)
        self.assertIn("3802.4", block)
        self.assertIn("RULE_WAIT_FOR_PULLBACK", block)
        self.assertIn("2026-07-07", block)
        # no internal IDs, no prose fields, bounded size
        self.assertNotIn("id=", block)
        self.assertLess(len(block), 600)


# ---------------------------------------------------------------------------
# Temp-DB persistence + previous snapshot retrieval
# ---------------------------------------------------------------------------

class _TempDbTestCase(unittest.TestCase):
    """Isolated temp SQLite; fail-fast if anything resolves to production."""

    def setUp(self) -> None:
        from src.config import Config
        from src.storage import DatabaseManager

        self._temp_dir = tempfile.TemporaryDirectory(prefix="phase27_2_isolated_")
        self._db_path = os.path.join(self._temp_dir.name, "phase27_2_temp.sqlite3")
        self._old_db_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = self._db_path

        # fail-fast isolation guard
        assert _PROD_DB_TOKEN not in self._db_path, "temp DB must not be the production DB"
        assert self._db_path.startswith(tempfile.gettempdir()) or "/T/" in self._db_path or self._temp_dir.name in self._db_path
        assert not os.path.abspath(self._db_path).startswith(
            os.path.abspath(os.path.join(os.getcwd(), "data"))
        ), "temp DB must not live under the production data/ directory"

        # Save the ambient Config singleton so other test modules never see a
        # temp-DB-flavored Config leak after this test finishes.
        self._old_config_instance = Config._instance
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        resolved = str(getattr(self.db, "db_path", self._db_path))
        assert _PROD_DB_TOKEN not in resolved, f"resolved DB path leaked to production: {resolved}"

    def tearDown(self) -> None:
        from src.config import Config
        from src.storage import DatabaseManager

        DatabaseManager.reset_instance()
        if self._old_db_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self._old_db_path
        Config._instance = self._old_config_instance
        self._temp_dir.cleanup()

    def _save(self, query_id: str, snapshot_payload=None, code: str = "2454") -> int:
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code=code, name="聯發科", sentiment_score=50,
            trend_prediction="震盪", operation_advice="觀望",
        )
        if snapshot_payload is not None:
            result.strategy_state_snapshot = snapshot_payload
        saved = self.db.save_analysis_history(
            result=result, query_id=query_id, report_type="simple",
            news_content=None, context_snapshot=None, save_snapshot=False,
        )
        self.assertEqual(saved, 1)
        return saved


class PersistenceRoundTripTestCase(_TempDbTestCase):
    def test_snapshot_survives_save_and_history_rebuild(self) -> None:
        payload = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), invalidation=3802.4).to_dict()
        payload["authoritative"] = True
        self._save("q_roundtrip_1", payload)

        records = self.db.get_analysis_history(code="2454", days=7, limit=5)
        self.assertEqual(len(records), 1)
        raw = json.loads(records[0].raw_result)
        self.assertEqual(raw["strategy_state_snapshot"]["state"], "WAIT_FOR_PULLBACK")

        from src.services.history_service import HistoryService

        service = HistoryService(self.db)
        rebuilt = service._rebuild_analysis_result(raw, records[0])
        self.assertEqual(rebuilt.strategy_state_snapshot["state"], "WAIT_FOR_PULLBACK")
        self.assertEqual(rebuilt.strategy_state_snapshot["buy_zone"]["low"], 3880.0)
        self.assertTrue(rebuilt.strategy_state_snapshot["authoritative"])

    def test_legacy_record_without_snapshot_rebuilds_to_none(self) -> None:
        self._save("q_legacy_1", snapshot_payload=None)
        records = self.db.get_analysis_history(code="2454", days=7, limit=5)
        raw = json.loads(records[0].raw_result)

        from src.services.history_service import HistoryService

        rebuilt = HistoryService(self.db)._rebuild_analysis_result(raw, records[0])
        self.assertIsNone(rebuilt.strategy_state_snapshot)
        self.assertIsNone(rebuilt.strategy_authority_diagnostics)


class PreviousSnapshotRetrievalTestCase(_TempDbTestCase):
    def test_latest_valid_snapshot_wins(self) -> None:
        older = _snapshot(StrategyState.WATCHLIST, as_of=date(2026, 7, 5)).to_dict()
        newer = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), as_of=date(2026, 7, 7)).to_dict()
        self._save("q_prev_older", older)
        self._save("q_prev_newer", newer)

        prev = load_previous_strategy_snapshot(self.db, "2454")
        self.assertIsNotNone(prev)
        self.assertEqual(prev.state, StrategyState.WAIT_FOR_PULLBACK)
        self.assertEqual(prev.buy_zone.low, 3880.0)

    def test_malformed_newest_is_skipped_for_older_valid(self) -> None:
        valid = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), as_of=date(2026, 7, 7)).to_dict()
        self._save("q_prev_valid", valid)
        self._save("q_prev_malformed", {"schema_version": "garbage", "state": 123})

        prev = load_previous_strategy_snapshot(self.db, "2454")
        self.assertIsNotNone(prev)
        self.assertEqual(prev.state, StrategyState.WAIT_FOR_PULLBACK)

    def test_exclude_query_id_skips_current_generation(self) -> None:
        only = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454()).to_dict()
        self._save("q_prev_self", only)

        prev = load_previous_strategy_snapshot(self.db, "2454", exclude_query_id="q_prev_self")
        self.assertIsNone(prev)

    def test_no_records_returns_none(self) -> None:
        self.assertIsNone(load_previous_strategy_snapshot(self.db, "0000"))


# ---------------------------------------------------------------------------
# Pipeline attach (both paths call the same helper; parity by construction)
# ---------------------------------------------------------------------------

class PipelineAttachTestCase(unittest.TestCase):
    def _make_pipeline(self, flag: bool):
        with patch("src.core.pipeline.get_config") as mock_config, \
             patch("src.core.pipeline.get_db"), \
             patch("src.core.pipeline.DataFetcherManager"), \
             patch("src.core.pipeline.GeminiAnalyzer"), \
             patch("src.core.pipeline.NotificationService"), \
             patch("src.core.pipeline.SearchService"):
            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_cfg.enable_strategy_state_authority = flag
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            return StockAnalysisPipeline(config=mock_cfg)

    def _trend(self, close: float) -> dict:
        return {
            "current_price": close, "ma5": 4054.0, "ma10": 4100.0,
            "ma20": 4200.0, "ma60": 3800.0, "volume_ratio_5d": 1.0,
            "support_levels": [3880.0], "resistance_levels": [4500.0],
        }

    def _neutral_fundamental(self) -> dict:
        return {"capital_flow": {"data": {"stock_flow": {
            "main_net_inflow": 5.0, "inflow_5d": -5.0, "inflow_10d": None,
        }}}}

    def test_flag_off_is_a_complete_noop(self) -> None:
        pipeline = self._make_pipeline(flag=False)
        result = _llm_result()
        pipeline._attach_strategy_state_snapshot(
            result, "2454", trend_result=self._trend(3925.0),
            fundamental_context=self._neutral_fundamental(), previous_snapshot=None,
        )
        self.assertIsNone(result.strategy_state_snapshot)
        self.assertEqual(result.operation_advice, "買進")  # untouched
        self.assertEqual(result.decision_type, "buy")

    def test_pullback_into_previous_zone_becomes_accumulate_authority(self) -> None:
        pipeline = self._make_pipeline(flag=True)
        result = _llm_result(operation_advice="觀望", decision_type="hold", trend_prediction="看空", sentiment_score=35)
        result.instrument_type = "stock"
        result.change_pct = -1.75
        result.valuation_river_snapshot = None
        prev = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), invalidation=3802.4)

        with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), \
             patch("src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)):
            pipeline._attach_strategy_state_snapshot(
                result, "2454", trend_result=self._trend(3925.0),
                fundamental_context=self._neutral_fundamental(), previous_snapshot=prev,
            )

        snap = result.strategy_state_snapshot
        self.assertEqual(snap["state"], "ACCUMULATE_ZONE")
        self.assertTrue(snap["authoritative"])
        self.assertEqual(snap["buy_zone"]["low"], 3880.0)  # persisted zone, not new MA
        self.assertEqual(result.operation_advice, "分批布局")
        self.assertEqual(result.decision_type, "buy")

    def test_sharp_rally_becomes_do_not_chase_overriding_llm_buy(self) -> None:
        pipeline = self._make_pipeline(flag=True)
        result = _llm_result()  # LLM says 買進/buy
        result.instrument_type = "stock"
        result.change_pct = 9.9
        result.valuation_river_snapshot = None

        trend = self._trend(4620.0)
        trend["resistance_levels"] = [4700.0]
        with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), \
             patch("src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)):
            pipeline._attach_strategy_state_snapshot(
                result, "2454", trend_result=trend,
                fundamental_context=self._neutral_fundamental(), previous_snapshot=None,
            )

        self.assertEqual(result.strategy_state_snapshot["state"], "DO_NOT_CHASE")
        self.assertEqual(result.operation_advice, "不追價")
        self.assertEqual(result.decision_type, "avoid")

    def test_same_inputs_produce_identical_persisted_payload(self) -> None:
        pipeline = self._make_pipeline(flag=True)
        prev = _snapshot(StrategyState.WAIT_FOR_PULLBACK, zone=_zone_2454(), invalidation=3802.4)
        payloads = []
        for _ in range(2):
            result = _llm_result(operation_advice="觀望", decision_type="hold")
            result.instrument_type = "stock"
            result.change_pct = -1.75
            result.valuation_river_snapshot = None
            with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), \
                 patch("src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)):
                pipeline._attach_strategy_state_snapshot(
                    result, "2454", trend_result=self._trend(3925.0),
                    fundamental_context=self._neutral_fundamental(), previous_snapshot=prev,
                )
            payloads.append(json.dumps(result.strategy_state_snapshot, sort_keys=True))
        self.assertEqual(payloads[0], payloads[1])

    def test_etf_gets_no_snapshot_at_all_routed_before_engine(self) -> None:
        """Phase 27.2R: instrument routing happens BEFORE the stock engine is
        ever called — ETF gets no strategy_state_snapshot key whatsoever, not
        even a non-authoritative UNSUPPORTED one."""
        pipeline = self._make_pipeline(flag=True)
        result = _llm_result(operation_advice="持有", decision_type="hold")
        result.instrument_type = "etf"
        result.change_pct = 0.5
        result.valuation_river_snapshot = None

        with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), \
             patch("src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)):
            pipeline._attach_strategy_state_snapshot(
                result, "0050", trend_result=self._trend(200.0),
                fundamental_context=self._neutral_fundamental(), previous_snapshot=None,
            )

        self.assertIsNone(result.strategy_state_snapshot)
        self.assertIsNone(result.strategy_authority_diagnostics)
        self.assertEqual(result.operation_advice, "持有")
        self.assertEqual(result.decision_type, "hold")

    def test_provider_data_unavailable_raises_and_blocks_completion(self) -> None:
        """Phase 27.2R: an in-scope stock missing the current close (provider
        outage) must raise StrategyDataUnavailableError — never a completed
        report with an UNSUPPORTED/non-authoritative fallback."""
        from src.services.strategy_state_orchestrator import StrategyDataUnavailableError

        pipeline = self._make_pipeline(flag=True)
        result = _llm_result(operation_advice="持有", decision_type="hold")
        result.instrument_type = "stock"
        result.change_pct = None
        result.valuation_river_snapshot = None

        broken_trend = self._trend(3925.0)
        broken_trend["current_price"] = None  # simulate provider outage

        with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), \
             patch("src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)):
            with self.assertRaises(StrategyDataUnavailableError) as ctx:
                pipeline._attach_strategy_state_snapshot(
                    result, "2454", trend_result=broken_trend,
                    fundamental_context=self._neutral_fundamental(), previous_snapshot=None,
                )
        self.assertIn("MISSING_CURRENT_CLOSE", ctx.exception.defects)
        self.assertIsNone(result.strategy_state_snapshot)
        # LLM fields untouched — no fallback report authority was granted.
        self.assertEqual(result.operation_advice, "持有")
        self.assertEqual(result.decision_type, "hold")

    def test_missing_valuation_alone_is_supported_not_blocking(self) -> None:
        """Missing valuation is an optional enhancement gap — the engine must
        still return a valid, authoritative (TECHNICAL_ONLY-capable) state."""
        pipeline = self._make_pipeline(flag=True)
        result = _llm_result(operation_advice="觀望", decision_type="hold")
        result.instrument_type = "stock"
        result.change_pct = -1.75
        result.valuation_river_snapshot = None  # no valuation at all

        with patch("src.core.pipeline.get_market_for_stock", return_value="tw"), \
             patch("src.services.history_loader.get_frozen_target_date", return_value=date(2026, 7, 9)):
            pipeline._attach_strategy_state_snapshot(
                result, "2454", trend_result=self._trend(3925.0),
                fundamental_context=self._neutral_fundamental(), previous_snapshot=None,
            )

        self.assertIsNotNone(result.strategy_state_snapshot)
        self.assertTrue(result.strategy_state_snapshot["authoritative"])
        self.assertNotEqual(result.strategy_state_snapshot["state"], "UNSUPPORTED")

    def test_both_paths_share_the_same_helpers(self) -> None:
        """Parity by construction: exactly two call sites for the attach and
        two for the prompt augmentation (direct + Agent paths)."""
        with open("src/core/pipeline.py", encoding="utf-8") as f:
            source = f.read()
        self.assertEqual(source.count("self._attach_strategy_state_snapshot("), 2)
        self.assertEqual(source.count("self._augment_summary_with_previous_strategy_state("), 2)


# ---------------------------------------------------------------------------
# Stabilization guard S/R priority (flag-gated deterministic-first)
# ---------------------------------------------------------------------------

class StabilizePriorityTestCase(unittest.TestCase):
    def _result_with_llm_resistance(self):
        from src.analyzer import AnalysisResult

        result = AnalysisResult(
            code="2330", name="台積電", sentiment_score=70,
            trend_prediction="看多", operation_advice="買進",
        )
        result.decision_type = "buy"
        result.current_price = 100.0
        result.dashboard = {
            "data_perspective": {
                "price_position": {
                    "support_level": None,
                    "resistance_level": 200.0,  # LLM claims far resistance
                }
            }
        }
        return result

    def _trend(self):
        return {"current_price": 100.0, "support_levels": [90.0], "resistance_levels": [101.0]}

    def _neutral_fundamental(self):
        return {"capital_flow": {"data": {"stock_flow": {
            "main_net_inflow": 5.0, "inflow_5d": -5.0, "inflow_10d": None,
        }}}}

    def test_legacy_order_uses_llm_claimed_resistance(self) -> None:
        from src.analyzer import stabilize_decision_with_structure

        result = self._result_with_llm_resistance()
        stabilize_decision_with_structure(
            result, self._trend(), self._neutral_fundamental(), deterministic_priority=False,
        )
        blob = json.dumps(result.dashboard, ensure_ascii=False)
        self.assertIn("支撐與壓力之間", blob)  # mid-range verdict from LLM's far resistance

    def test_deterministic_priority_uses_trend_resistance(self) -> None:
        from src.analyzer import stabilize_decision_with_structure

        result = self._result_with_llm_resistance()
        stabilize_decision_with_structure(
            result, self._trend(), self._neutral_fundamental(), deterministic_priority=True,
        )
        blob = json.dumps(result.dashboard, ensure_ascii=False)
        self.assertIn("接近壓力位", blob)  # near-resistance verdict from trend's 101


# ---------------------------------------------------------------------------
# Isolation guards
# ---------------------------------------------------------------------------

class IsolationGuardTestCase(unittest.TestCase):
    def test_engine_still_has_no_db_access(self) -> None:
        with open("src/services/strategy_state_engine.py", encoding="utf-8") as f:
            source = f.read()
        for token in ("import sqlite3", "sqlalchemy", "from src.storage", "get_session"):
            self.assertNotIn(token, source)

    def test_orchestrator_has_no_provider_or_llm_imports(self) -> None:
        with open("src/services/strategy_state_orchestrator.py", encoding="utf-8") as f:
            import_lines = [
                line for line in f.read().splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
        blob = "\n".join(import_lines)
        for token in ("data_provider", "litellm", "openai", "yfinance", "FinMind", "requests", "src.storage", "sqlalchemy"):
            self.assertNotIn(token, blob)

    def test_no_production_db_token_in_phase27_2_files(self) -> None:
        for path in (
            "src/services/strategy_state_orchestrator.py",
            "src/services/strategy_state_engine.py",
        ):
            with open(path, encoding="utf-8") as f:
                self.assertNotIn(_PROD_DB_TOKEN, f.read(), path)

    def test_pipeline_imports_orchestrator_lazily_only(self) -> None:
        with open("src/core/pipeline.py", encoding="utf-8") as f:
            head = f.read(4000)
        self.assertNotIn("strategy_state_orchestrator", head)


if __name__ == "__main__":
    unittest.main()

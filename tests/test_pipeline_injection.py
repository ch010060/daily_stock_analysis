"""
Phase 2.3 — Pipeline prebuilt context injection tests.

Validates that data_context_mode and analysis_mode are independent dimensions
and that the injection does not regress existing A/H behaviour.

All tests run offline — no external network, no LLM endpoint, no DB write.
"""

import json
import os
import types
import unittest
from unittest.mock import MagicMock, patch, call

from adapters.snapshot_schema import make_minimal_snapshot, SnapshotContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline(**kwargs):
    """Build a StockAnalysisPipeline with all heavy dependencies mocked out."""
    from src.core.pipeline import StockAnalysisPipeline

    with patch("src.core.pipeline.DataFetcherManager"), \
         patch("src.core.pipeline.GeminiAnalyzer"), \
         patch("src.core.pipeline.NotificationService"), \
         patch("src.core.pipeline.SearchService"), \
         patch("src.core.pipeline.get_db"), \
         patch("src.core.pipeline.get_config") as mock_cfg:
        mock_cfg.return_value = MagicMock(
            max_workers=1,
            save_context_snapshot=False,
            enable_realtime_quote=False,
            searxng_base_urls=[],
            searxng_public_instances_enabled=False,
            news_max_age_days=7,
            news_strategy_profile="short",
            bocha_api_keys=[],
            tavily_api_keys=[],
            anspire_api_keys=[],
            brave_api_keys=[],
            serpapi_keys=[],
            minimax_api_keys=[],
            report_language="zh",
        )
        pipeline = StockAnalysisPipeline(**kwargs)

    return pipeline


def _make_analysis_result(code="TW:2330"):
    from src.analyzer import AnalysisResult
    return AnalysisResult(
        code=code,
        name="台積電",
        sentiment_score=72,
        trend_prediction="看多",
        operation_advice="持有",
        success=True,
    )


# ---------------------------------------------------------------------------
# snapshot_schema
# ---------------------------------------------------------------------------

class TestSnapshotSchema(unittest.TestCase):

    def test_make_minimal_snapshot_returns_dict_with_required_keys(self):
        snap = make_minimal_snapshot("TW:2330", "台積電")
        self.assertEqual(snap["code"], "TW:2330")
        self.assertEqual(snap["name"], "台積電")
        for key in ("history", "today", "yesterday", "realtime", "chip", "trend",
                    "fundamental", "market_phase_context"):
            self.assertIn(key, snap)
            self.assertEqual(snap[key], {})

    def test_make_minimal_snapshot_default_name_is_code(self):
        snap = make_minimal_snapshot("US:AAPL")
        self.assertEqual(snap["name"], "US:AAPL")


# ---------------------------------------------------------------------------
# data_context_mode
# ---------------------------------------------------------------------------

class TestDataContextMode(unittest.TestCase):

    def setUp(self):
        self.pipeline = _make_pipeline()

    def _patch_process_internals(self):
        """Patch everything inside process_single_stock except the branches under test."""
        patches = [
            patch.object(self.pipeline, "fetch_and_save_stock_data", return_value=(True, None)),
            patch.object(self.pipeline, "analyze_stock", return_value=_make_analysis_result()),
            patch.object(self.pipeline, "_resolve_resume_target_date", return_value=None),
            # set/reset_frozen_target_date are imported locally inside process_single_stock
            patch("src.services.history_loader.set_frozen_target_date", return_value=MagicMock()),
            patch("src.services.history_loader.reset_frozen_target_date"),
            # diagnostic context helpers are imported at module level in pipeline
            patch("src.core.pipeline.activate_run_diagnostic_context", return_value=MagicMock()),
            patch("src.core.pipeline.reset_run_diagnostic_context"),
            patch("src.core.pipeline.get_current_diagnostic_context", return_value=None),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

    def test_fetch_mode_calls_fetch_and_save(self):
        self._patch_process_internals()
        self.pipeline.process_single_stock("TW:2330", data_context_mode="fetch")
        self.pipeline.fetch_and_save_stock_data.assert_called_once()

    def test_prebuilt_mode_skips_fetch(self):
        self._patch_process_internals()
        snap = make_minimal_snapshot("TW:2330")
        self.pipeline.process_single_stock(
            "TW:2330",
            data_context_mode="prebuilt",
            pre_built_context=snap,
        )
        self.pipeline.fetch_and_save_stock_data.assert_not_called()

    def test_prebuilt_and_fetch_are_independent_of_analysis_mode(self):
        """prebuilt + dry_run: neither fetch nor analyze should be called."""
        self._patch_process_internals()
        snap = make_minimal_snapshot("TW:2330")
        result = self.pipeline.process_single_stock(
            "TW:2330",
            data_context_mode="prebuilt",
            analysis_mode="dry_run",
            pre_built_context=snap,
        )
        self.assertIsNone(result)
        self.pipeline.fetch_and_save_stock_data.assert_not_called()
        self.pipeline.analyze_stock.assert_not_called()


# ---------------------------------------------------------------------------
# analysis_mode
# ---------------------------------------------------------------------------

class TestAnalysisMode(unittest.TestCase):

    def setUp(self):
        self.pipeline = _make_pipeline()

    def _patch_process_internals(self):
        patches = [
            patch.object(self.pipeline, "fetch_and_save_stock_data", return_value=(True, None)),
            patch.object(self.pipeline, "analyze_stock", return_value=_make_analysis_result()),
            patch.object(self.pipeline, "_resolve_resume_target_date", return_value=None),
            patch("src.services.history_loader.set_frozen_target_date", return_value=MagicMock()),
            patch("src.services.history_loader.reset_frozen_target_date"),
            patch("src.core.pipeline.activate_run_diagnostic_context", return_value=MagicMock()),
            patch("src.core.pipeline.reset_run_diagnostic_context"),
            patch("src.core.pipeline.get_current_diagnostic_context", return_value=None),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

    def test_dry_run_returns_none_and_skips_analyze(self):
        self._patch_process_internals()
        result = self.pipeline.process_single_stock("TW:2330", analysis_mode="dry_run")
        self.assertIsNone(result)
        self.pipeline.analyze_stock.assert_not_called()

    def test_full_mode_calls_analyze_stock(self):
        self._patch_process_internals()
        result = self.pipeline.process_single_stock("TW:2330", analysis_mode="full")
        self.pipeline.analyze_stock.assert_called_once()
        self.assertIsNotNone(result)

    def test_fixture_mode_does_not_call_analyze_stock(self):
        self._patch_process_internals()
        with patch.object(self.pipeline, "_load_llm_fixture",
                          return_value=_make_analysis_result()) as mock_fixture:
            result = self.pipeline.process_single_stock("TW:2330", analysis_mode="fixture")
        mock_fixture.assert_called_once_with("TW:2330")
        self.pipeline.analyze_stock.assert_not_called()
        self.assertIsNotNone(result)

    def test_full_mode_with_prebuilt_calls_analyze_with_prebuilt(self):
        self._patch_process_internals()
        snap = make_minimal_snapshot("TW:2330")
        with patch.object(self.pipeline, "_analyze_with_prebuilt",
                          return_value=_make_analysis_result()) as mock_prebuilt:
            self.pipeline.process_single_stock(
                "TW:2330",
                data_context_mode="prebuilt",
                analysis_mode="full",
                pre_built_context=snap,
            )
        mock_prebuilt.assert_called_once()
        self.pipeline.analyze_stock.assert_not_called()

    def test_prebuilt_without_context_falls_back_to_analyze_stock(self):
        """If pre_built_context is None, fall back to normal analyze_stock."""
        self._patch_process_internals()
        self.pipeline.process_single_stock(
            "TW:2330",
            data_context_mode="prebuilt",
            analysis_mode="full",
            pre_built_context=None,
        )
        self.pipeline.analyze_stock.assert_called_once()


# ---------------------------------------------------------------------------
# fixture loader
# ---------------------------------------------------------------------------

class TestLoadLlmFixture(unittest.TestCase):

    def setUp(self):
        self.pipeline = _make_pipeline()

    def test_loads_existing_fixture(self):
        result = self.pipeline._load_llm_fixture("TW:2330")
        self.assertTrue(result.success)
        self.assertEqual(result.code, "TW:2330")
        self.assertEqual(result.name, "台積電")
        self.assertGreater(result.sentiment_score, 0)

    def test_missing_fixture_returns_failure_result(self):
        result = self.pipeline._load_llm_fixture("TW:9999")
        self.assertFalse(result.success)
        self.assertIn("fixture_not_found", result.error_message)

    def test_fixture_deterministic(self):
        r1 = self.pipeline._load_llm_fixture("TW:2330")
        r2 = self.pipeline._load_llm_fixture("TW:2330")
        self.assertEqual(r1.sentiment_score, r2.sentiment_score)
        self.assertEqual(r1.operation_advice, r2.operation_advice)
        self.assertEqual(r1.trend_prediction, r2.trend_prediction)

    def test_colon_in_code_becomes_underscore_in_filename(self):
        """Ensure the safe-name conversion matches the fixture file on disk."""
        fixture_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tests", "fixtures", "llm",
        )
        expected_file = os.path.join(fixture_dir, "TW_2330.json")
        self.assertTrue(os.path.exists(expected_file),
                        f"Expected fixture file missing: {expected_file}")

    def test_path_traversal_attempt_is_sanitized_not_escaped(self):
        """Code with '..' is sanitized by regex; path stays inside fixture_dir."""
        result = self.pipeline._load_llm_fixture("TW:../../etc/passwd")
        self.assertFalse(result.success)
        # Regex converts all non-alnum chars to '_' so '..' and '/' cannot escape;
        # sanitized filename doesn't exist → fixture_not_found (not a crash)
        self.assertIn("fixture_not_found", result.error_message)

    def test_dot_dot_input_sanitized_to_fixture_not_found(self):
        """Bare '../sneaky' is sanitized; no files outside fixture_dir are accessed."""
        result = self.pipeline._load_llm_fixture("../sneaky")
        self.assertFalse(result.success)
        self.assertIn("fixture_not_found", result.error_message)

    def test_valid_symbol_loads_after_path_guard_applied(self):
        """Path guard must not break normal TW:2330 fixture load."""
        result = self.pipeline._load_llm_fixture("TW:2330")
        self.assertTrue(result.success)
        self.assertEqual(result.code, "TW:2330")


# ---------------------------------------------------------------------------
# A/H regression — original flow unchanged
# ---------------------------------------------------------------------------

class TestAHRegression(unittest.TestCase):
    """Verify that existing A/H callers with no new params behave identically."""

    def setUp(self):
        self.pipeline = _make_pipeline()

    def test_default_params_are_fetch_and_full(self):
        """Default data_context_mode and analysis_mode do not alter old behaviour."""
        import inspect
        sig = inspect.signature(self.pipeline.process_single_stock)
        self.assertEqual(sig.parameters["data_context_mode"].default, "fetch")
        self.assertEqual(sig.parameters["analysis_mode"].default, "full")
        self.assertIsNone(sig.parameters["pre_built_context"].default)

    def test_existing_skip_analysis_still_works(self):
        patches = [
            patch.object(self.pipeline, "fetch_and_save_stock_data", return_value=(True, None)),
            patch.object(self.pipeline, "analyze_stock", return_value=_make_analysis_result()),
            patch.object(self.pipeline, "_resolve_resume_target_date", return_value=None),
            patch("src.services.history_loader.set_frozen_target_date", return_value=MagicMock()),
            patch("src.services.history_loader.reset_frozen_target_date"),
            patch("src.core.pipeline.activate_run_diagnostic_context", return_value=MagicMock()),
            patch("src.core.pipeline.reset_run_diagnostic_context"),
            patch("src.core.pipeline.get_current_diagnostic_context", return_value=None),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])

        result = self.pipeline.process_single_stock("600519", skip_analysis=True)
        self.assertIsNone(result)
        self.pipeline.analyze_stock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

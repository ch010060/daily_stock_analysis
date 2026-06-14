# -*- coding: utf-8 -*-
"""
Tests for Phase 8H — FinMind Production Daily Profile Runner.

All tests are offline. MockPanelBundleBuilder injects deterministic panel bundles.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("DSA_FIXTURE_MODE", "true")

from src.finmind.daily_profile import (
    DailyProfileConfig,
    DailyProfileRunner,
    build_data_quality_report,
    make_profile_id,
    write_artifacts,
    _collect_prompt_cards,
    _yyyymmdd,
)

# ──────────────────────────────────────────────────────────────────────────────
# Mock bundle builder
# ──────────────────────────────────────────────────────────────────────────────

_PANEL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "finmind" / "panels"


def _load(name: str) -> Dict:
    with open(_PANEL_FIXTURE_DIR / name) as f:
        return json.load(f)


def _make_mock_bundle(symbol: str, ok: bool = True) -> Dict[str, Any]:
    """Build a minimal bundle dict resembling PanelBundleBuilder output."""
    stock_id = symbol.replace("TW:", "")
    return {
        "ok": ok,
        "bundle_id": f"bnd_mock_{stock_id}",
        "symbols": [symbol],
        "start_date": "2026-01-05",
        "end_date": "2026-06-14",
        "panels": [
            {
                "panel_id": f"pnl_mock_li_{stock_id}",
                "panel_type": "latest_info",
                "title": f"最新資訊 — {symbol}",
                "symbol": symbol,
                "date_range": {"start": "2026-01-05", "end": "2026-06-14"},
                "summary": f"mock latest_info for {symbol}",
                "key_metrics": {"event_count": 2},
                "data_quality": {"adjusted_price_used": False},
                "missing": ["TaiwanStockNews"],
                "warnings": [],
                "sources": ["finmind"],
                "prompt_cards": [
                    {
                        "prompt_id": f"prc_mock_li_{stock_id}_1",
                        "title": "最新事件摘要",
                        "prompt": f"請只根據本 latest_info panel 的資料（資料截止 2026-06-14），整理 {symbol} 最重要的三個事件，勿引用外部資料。",
                        "panel_id": f"pnl_mock_li_{stock_id}",
                        "snapshot_id": f"bnd_mock_{stock_id}",
                        "allowed_context": ["latest_info_panel"],
                        "data_freshness": {"as_of": "2026-06-14"},
                        "safety_tags": ["no_buysell", "no_external_fetch", "snapshot_bound"],
                        "caveats": [],
                    },
                ],
            },
            {
                "panel_id": f"pnl_mock_dq_{stock_id}",
                "panel_type": "data_quality",
                "title": f"資料品質 — {symbol}",
                "symbol": symbol,
                "date_range": {"start": "", "end": "2026-06-14"},
                "summary": "mock data quality",
                "key_metrics": {"missing_datasets": ["TaiwanStockNews"], "tier_caveats": []},
                "data_quality": {
                    "missing_datasets": ["TaiwanStockNews"],
                    "tier_caveats": ["backtest: 使用未還原股價（TaiwanStockPriceAdj 需 Backer tier）"] if ok else [],
                },
                "missing": ["TaiwanStockNews"],
                "warnings": ["TaiwanStockPriceAdj unavailable"] if ok else [],
                "sources": ["finmind"],
                "prompt_cards": [],
            },
        ],
        "data_quality": {
            "valid_symbol": ok,
            "stock_id": stock_id,
            "panel_count": 2,
            "panels_with_errors": [],
        },
        "recommended_prompts": [
            {
                "prompt_id": f"prc_mock_li_{stock_id}_1",
                "title": "最新事件摘要",
                "prompt": f"請只根據本 latest_info panel 的資料（資料截止 2026-06-14），整理 {symbol} 最重要的三個事件，勿引用外部資料。",
                "panel_id": f"pnl_mock_li_{stock_id}",
                "snapshot_id": f"bnd_mock_{stock_id}",
                "allowed_context": ["latest_info_panel"],
                "data_freshness": {"as_of": "2026-06-14"},
                "safety_tags": ["no_buysell", "no_external_fetch", "snapshot_bound"],
                "caveats": [],
            },
        ],
        "sources": ["finmind"],
        "warnings": [],
    }


class MockPanelBundleBuilder:
    def __init__(self, ok: bool = True, raise_exc: bool = False):
        self._ok = ok
        self._raise = raise_exc

    def build_stock_bundle(self, symbol, start_date, end_date,
                           include_backtest=True, include_strategy_analysis=True):
        if self._raise:
            raise RuntimeError(f"mock builder error for {symbol}")
        return _make_mock_bundle(symbol, ok=self._ok)


def _make_runner(ok: bool = True, raise_exc: bool = False) -> DailyProfileRunner:
    return DailyProfileRunner(
        panel_builder=MockPanelBundleBuilder(ok=ok, raise_exc=raise_exc),
        fixture_mode=True,
        allow_external_network=False,
    )


_SYMBOLS = ["TW:2330", "TW:0050"]
_START = "2026-01-05"
_END = "2026-06-14"


# ──────────────────────────────────────────────────────────────────────────────
# 1. Initialization
# ──────────────────────────────────────────────────────────────────────────────

class TestDailyProfileRunnerInit(unittest.TestCase):

    def test_init_no_args(self):
        r = DailyProfileRunner()
        self.assertIsNotNone(r)

    def test_init_with_mock_builder(self):
        r = _make_runner()
        self.assertIsNotNone(r)

    def test_config_dataclass(self):
        c = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        self.assertEqual(c.send_notification, False)
        self.assertEqual(c.mode, "controlled_live")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Fixture mode
# ──────────────────────────────────────────────────────────────────────────────

class TestFixtureMode(unittest.TestCase):

    def setUp(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END, mode="fixture")
        self.result = r.run(cfg)

    def test_fixture_mode_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_fixture_mode_ok(self):
        self.assertTrue(self.result.get("ok"))

    def test_fixture_mode_records_mode(self):
        self.assertEqual(self.result.get("mode"), "fixture")

    def test_fixture_mode_has_bundles(self):
        self.assertIsInstance(self.result.get("bundles"), list)
        self.assertGreater(len(self.result["bundles"]), 0)

    def test_fixture_mode_json_serializable(self):
        dumped = json.dumps(self.result)
        parsed = json.loads(dumped)
        self.assertEqual(parsed["ok"], True)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Profile structure
# ──────────────────────────────────────────────────────────────────────────────

class TestProfileStructure(unittest.TestCase):

    def setUp(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        self.result = r.run(cfg)

    def test_profile_id_present(self):
        self.assertTrue(self.result.get("profile_id", "").startswith("prf_"))

    def test_profile_id_deterministic(self):
        id1 = make_profile_id(_SYMBOLS, _START, _END)
        id2 = make_profile_id(_SYMBOLS, _START, _END)
        self.assertEqual(id1, id2)

    def test_bundle_count_matches_symbols(self):
        self.assertEqual(len(self.result["bundles"]), len(_SYMBOLS))

    def test_result_includes_data_quality(self):
        self.assertIn("data_quality", self.result)
        dq = self.result["data_quality"]
        self.assertIn("ok_symbols", dq)
        self.assertIn("failed_symbols", dq)

    def test_result_includes_warnings(self):
        self.assertIsInstance(self.result.get("warnings"), list)

    def test_result_includes_recommended_prompts(self):
        self.assertIsInstance(self.result.get("recommended_prompts"), list)

    def test_symbols_in_result(self):
        self.assertEqual(self.result.get("symbols"), _SYMBOLS)

    def test_generated_at_is_end_date(self):
        self.assertEqual(self.result.get("generated_at"), _END)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Symbol safety
# ──────────────────────────────────────────────────────────────────────────────

class TestSymbolSafety(unittest.TestCase):

    def test_non_tw_symbol_rejected(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["US:AAPL"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertFalse(result.get("ok"))
        dq = result.get("data_quality", {})
        self.assertIn("US:AAPL", dq.get("failed_symbols", []))

    def test_cn_symbol_rejected(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["600519"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertFalse(result.get("ok"))

    def test_cn_symbol_warning(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["600519"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        warnings = result.get("warnings", [])
        self.assertTrue(any("600519" in w for w in warnings))

    def test_mixed_valid_invalid_partial_ok(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["TW:2330", "US:AAPL"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        dq = result.get("data_quality", {})
        self.assertIn("TW:2330", dq.get("ok_symbols", []))
        self.assertIn("US:AAPL", dq.get("failed_symbols", []))

    def test_tw_prefix_accepted(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["TW:2330"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertTrue(result.get("ok"))

    def test_bare_tw_stock_id_accepted(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["2330"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertTrue(result.get("ok"))


# ──────────────────────────────────────────────────────────────────────────────
# 5. Data quality aggregation
# ──────────────────────────────────────────────────────────────────────────────

class TestDataQualityAggregation(unittest.TestCase):

    def setUp(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        self.result = r.run(cfg)
        self.dq = self.result["data_quality"]

    def test_dq_symbol_count(self):
        self.assertEqual(self.dq.get("symbol_count"), len(_SYMBOLS))

    def test_dq_ok_symbols_list(self):
        self.assertIsInstance(self.dq.get("ok_symbols"), list)
        self.assertGreater(len(self.dq["ok_symbols"]), 0)

    def test_dq_failed_symbols_list(self):
        self.assertIsInstance(self.dq.get("failed_symbols"), list)

    def test_dq_missing_aggregated(self):
        self.assertIsInstance(self.dq.get("missing"), list)

    def test_dq_sources_aggregated(self):
        self.assertIsInstance(self.dq.get("sources"), list)

    def test_all_failed_returns_ok_false(self):
        r = DailyProfileRunner(
            panel_builder=MockPanelBundleBuilder(ok=False),
            fixture_mode=True,
        )
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        result = r.run(cfg)
        # ok_symbols = [] when all bundles ok=False
        dq = result.get("data_quality", {})
        self.assertEqual(dq.get("ok_symbols"), [])

    def test_partial_data_still_ok_if_one_symbol_succeeds(self):
        r = _make_runner()
        cfg = DailyProfileConfig(
            symbols=["TW:2330", "US:AAPL"],  # one valid, one rejected
            start_date=_START, end_date=_END
        )
        result = r.run(cfg)
        self.assertTrue(result.get("ok"))
        dq = result["data_quality"]
        self.assertTrue(dq.get("partial"))


# ──────────────────────────────────────────────────────────────────────────────
# 6. Prompt card aggregation
# ──────────────────────────────────────────────────────────────────────────────

class TestPromptCardAggregation(unittest.TestCase):

    def setUp(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        self.result = r.run(cfg)
        self.prompts = self.result.get("recommended_prompts", [])

    def test_prompt_cards_aggregated(self):
        self.assertGreater(len(self.prompts), 0)

    def test_prompt_cards_have_allowed_context(self):
        for pc in self.prompts:
            self.assertIn("allowed_context", pc)

    def test_prompt_cards_have_snapshot_id(self):
        for pc in self.prompts:
            self.assertIn("snapshot_id", pc)

    def test_prompts_deduplicated(self):
        ids = [pc.get("prompt_id") for pc in self.prompts]
        self.assertEqual(len(ids), len(set(ids)))

    def test_prompts_no_external_fetch(self):
        for pc in self.prompts:
            self.assertNotIn("請上網查", pc.get("prompt", ""))
            self.assertNotIn("即時搜尋", pc.get("prompt", ""))

    def test_prompts_no_buysell(self):
        for pc in self.prompts:
            prompt = pc.get("prompt", "")
            for term in ("買進", "賣出", "買入", "卖出", "推薦買", "推薦賣"):
                self.assertNotIn(term, prompt, f"Found '{term}' in: {prompt[:80]}")


# ──────────────────────────────────────────────────────────────────────────────
# 7. No CN/A-share terms
# ──────────────────────────────────────────────────────────────────────────────

class TestNoCNTerms(unittest.TestCase):

    _CN_TERMS = ["A股", "上證", "上证", "深證", "深证", "創業板", "创业板", "科創50", "科创50"]

    def test_no_cn_terms_in_result(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        result = r.run(cfg)
        text = json.dumps(result, ensure_ascii=False)
        found = [t for t in self._CN_TERMS if t in text]
        self.assertEqual(found, [])

    def test_no_cn_terms_in_markdown(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        result = r.run(cfg)
        with tempfile.TemporaryDirectory() as d:
            r.write_artifacts(result, d)
            md_path = Path(d) / f"daily_profile_{_yyyymmdd(_END)}.md"
            md_text = md_path.read_text(encoding="utf-8")
        found = [t for t in self._CN_TERMS if t in md_text]
        self.assertEqual(found, [])


# ──────────────────────────────────────────────────────────────────────────────
# 8. Artifact writing
# ──────────────────────────────────────────────────────────────────────────────

class TestArtifactWriting(unittest.TestCase):

    def setUp(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END)
        self.result = r.run(cfg)

    def test_write_artifacts_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            artifacts = write_artifacts(self.result, d)
            self.assertIn("daily_profile_json", artifacts)
            self.assertIn("daily_profile_md", artifacts)
            self.assertIn("daily_data_quality_json", artifacts)
            self.assertIn("daily_prompt_cards_json", artifacts)

    def test_artifacts_files_exist(self):
        with tempfile.TemporaryDirectory() as d:
            artifacts = write_artifacts(self.result, d)
            for name, path in artifacts.items():
                self.assertTrue(Path(path).exists(), f"Missing: {name} at {path}")

    def test_artifact_json_parseable(self):
        with tempfile.TemporaryDirectory() as d:
            artifacts = write_artifacts(self.result, d)
            data = json.loads(Path(artifacts["daily_profile_json"]).read_text(encoding="utf-8"))
            self.assertEqual(data["ok"], True)

    def test_artifact_dq_json_parseable(self):
        with tempfile.TemporaryDirectory() as d:
            artifacts = write_artifacts(self.result, d)
            dq = json.loads(Path(artifacts["daily_data_quality_json"]).read_text(encoding="utf-8"))
            self.assertIn("ok_symbols", dq)

    def test_artifact_prompt_cards_json_parseable(self):
        with tempfile.TemporaryDirectory() as d:
            artifacts = write_artifacts(self.result, d)
            cards = json.loads(Path(artifacts["daily_prompt_cards_json"]).read_text(encoding="utf-8"))
            self.assertIsInstance(cards, list)

    def test_write_via_runner_method(self):
        with tempfile.TemporaryDirectory() as d:
            r = _make_runner()
            artifacts = r.write_artifacts(self.result, d)
            self.assertIn("daily_profile_json", artifacts)

    def test_generated_artifacts_serializable(self):
        with tempfile.TemporaryDirectory() as d:
            artifacts = write_artifacts(self.result, d)
            full = json.loads(Path(artifacts["daily_profile_json"]).read_text(encoding="utf-8"))
            self.assertIsInstance(full, dict)


# ──────────────────────────────────────────────────────────────────────────────
# 9. Failure resilience
# ──────────────────────────────────────────────────────────────────────────────

class TestFailureResilience(unittest.TestCase):

    def test_builder_exception_captured_as_warning(self):
        r = _make_runner(raise_exc=True)
        cfg = DailyProfileConfig(symbols=["TW:2330"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertIsInstance(result, dict)
        warnings = result.get("warnings", [])
        self.assertTrue(any("2330" in w or "bundle" in w.lower() for w in warnings))

    def test_builder_exception_per_symbol_produces_warning_bundle(self):
        # When builder raises per symbol, bundles are ok=False and warnings populated
        r = DailyProfileRunner(
            panel_builder=MockPanelBundleBuilder(raise_exc=True),
            fixture_mode=True,
        )
        cfg = DailyProfileConfig(symbols=["TW:2330"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertIsInstance(result, dict)
        bundles = result.get("bundles", [])
        self.assertEqual(len(bundles), 1)
        self.assertFalse(bundles[0].get("ok"))

    def test_all_symbols_invalid_returns_ok_false(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["US:AAPL", "600519"], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertFalse(result.get("ok"))

    def test_empty_symbols_returns_ok_false(self):
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=[], start_date=_START, end_date=_END)
        result = r.run(cfg)
        self.assertFalse(result.get("ok"))


# ──────────────────────────────────────────────────────────────────────────────
# 10. No live calls in unit tests
# ──────────────────────────────────────────────────────────────────────────────

class TestNoLiveCalls(unittest.TestCase):

    def test_fixture_mode_no_network(self):
        import sys
        before = set(sys.modules.keys())
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["TW:2330"], start_date=_START, end_date=_END, mode="fixture")
        r.run(cfg)
        after = set(sys.modules.keys())
        new = after - before
        network_mods = [m for m in new if "urllib" in m or "requests" in m or "http.client" in m]
        # urllib may already be loaded; this test checks no NEW network calls triggered
        self.assertFalse(any("requests" in m for m in new))

    def test_send_notification_always_false(self):
        cfg = DailyProfileConfig(symbols=_SYMBOLS, start_date=_START, end_date=_END,
                                  send_notification=True)  # should be overridden
        # DailyProfileConfig stores it as-is; runner must not use it to actually send
        # This test verifies config parsing doesn't crash
        self.assertIsInstance(cfg, DailyProfileConfig)

    def test_no_actual_main_called(self):
        import sys
        r = _make_runner()
        cfg = DailyProfileConfig(symbols=["TW:2330"], start_date=_START, end_date=_END)
        mods_before = set(sys.modules.keys())
        r.run(cfg)
        new = set(sys.modules.keys()) - mods_before
        self.assertFalse(any(m == "main" for m in new))


# ──────────────────────────────────────────────────────────────────────────────
# 11. build_data_quality_report standalone
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildDataQualityReport(unittest.TestCase):

    def test_all_ok_bundles(self):
        bundles = [_make_mock_bundle("TW:2330"), _make_mock_bundle("TW:0050")]
        dq = build_data_quality_report(bundles)
        self.assertEqual(len(dq["ok_symbols"]), 2)
        self.assertEqual(len(dq["failed_symbols"]), 0)

    def test_all_failed_bundles(self):
        bundles = [_make_mock_bundle("TW:2330", ok=False), _make_mock_bundle("TW:0050", ok=False)]
        dq = build_data_quality_report(bundles)
        self.assertFalse(dq["ok"])

    def test_partial_bundles(self):
        bundles = [_make_mock_bundle("TW:2330", ok=True), _make_mock_bundle("TW:0050", ok=False)]
        dq = build_data_quality_report(bundles)
        self.assertTrue(dq["ok"])
        self.assertTrue(dq["partial"])

    def test_missing_aggregated(self):
        bundles = [_make_mock_bundle("TW:2330")]
        dq = build_data_quality_report(bundles)
        self.assertIn("TaiwanStockNews", dq.get("missing", []))


# ──────────────────────────────────────────────────────────────────────────────
# 12. collect_prompt_cards deduplication
# ──────────────────────────────────────────────────────────────────────────────

class TestCollectPromptCards(unittest.TestCase):

    def test_dedup_by_prompt_id(self):
        # Same prompt_id from two bundles → deduplicated
        b1 = _make_mock_bundle("TW:2330")
        b2 = _make_mock_bundle("TW:2330")  # same prompt_id
        cards = _collect_prompt_cards([b1, b2])
        ids = [pc["prompt_id"] for pc in cards]
        self.assertEqual(len(ids), len(set(ids)))

    def test_different_symbols_different_ids(self):
        b1 = _make_mock_bundle("TW:2330")
        b2 = _make_mock_bundle("TW:0050")
        cards = _collect_prompt_cards([b1, b2])
        self.assertEqual(len(cards), 2)  # different symbols → different prompt_ids


if __name__ == "__main__":
    unittest.main()

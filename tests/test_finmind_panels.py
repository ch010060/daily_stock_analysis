# -*- coding: utf-8 -*-
"""
Tests for Phase 8G — FinMind Panel Bundle and LLM-safe Prompt Interaction.

All tests are offline. Mock collectors inject deterministic fixture results.
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("DSA_FIXTURE_MODE", "true")

from src.finmind.panels import (
    PanelBundleBuilder,
    build_prompt_card,
    check_prompt_safety,
    make_bundle_id,
    make_panel_id,
    make_prompt_id,
    _build_data_quality_panel,
    _failure_panel,
    _FORBIDDEN_PROMPT_TERMS,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "finmind" / "panels"


def _load(name: str) -> Dict:
    with open(FIXTURE_DIR / name) as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────────────
# Mock collectors
# ──────────────────────────────────────────────────────────────────────────────

class MockLICollector:
    """Injects latest_info_snapshot.json."""

    def __init__(self, ok: bool = True, raise_exc: bool = False):
        self._ok = ok
        self._raise = raise_exc

    def collect_latest_info_snapshot(self, symbols, start_date, end_date):
        if self._raise:
            raise RuntimeError("mock LI error")
        data = _load("latest_info_snapshot.json")
        if not self._ok:
            data["ok"] = False
            data["events"] = []
            data["event_count"] = 0
        return data


class MockSACollector:
    """Injects stock_analysis_snapshot.json."""

    def __init__(self, ok: bool = True, raise_exc: bool = False):
        self._ok = ok
        self._raise = raise_exc

    def collect_stock_analysis_snapshot(self, symbol, start_date, end_date):
        if self._raise:
            raise RuntimeError("mock SA error")
        data = _load("stock_analysis_snapshot.json")
        return _DictSnapshot(data)


class _DictSnapshot:
    def __init__(self, d: Dict):
        self._d = d

    def to_dict(self):
        return self._d


class MockBacktestEngine:
    """Injects backtest_result.json."""

    def __init__(self, ok: bool = True, raise_exc: bool = False):
        self._ok = ok
        self._raise = raise_exc

    def run(self, config):
        if self._raise:
            raise RuntimeError("mock BT error")
        data = _load("backtest_result.json")
        if not self._ok:
            data["ok"] = False
        return data


class MockStrategyAnalyzer:
    """Injects strategy_analysis_result.json."""

    def __init__(self, ok: bool = True, raise_exc: bool = False):
        self._ok = ok
        self._raise = raise_exc

    def analyze(self, config):
        if self._raise:
            raise RuntimeError("mock STRAT error")
        data = _load("strategy_analysis_result.json")
        if not self._ok:
            data["ok"] = False
        return data


def _make_builder(
    li_ok: bool = True,
    sa_ok: bool = True,
    bt_ok: bool = True,
    strat_ok: bool = True,
    li_exc: bool = False,
    sa_exc: bool = False,
    bt_exc: bool = False,
    strat_exc: bool = False,
) -> PanelBundleBuilder:
    return PanelBundleBuilder(
        latest_info_collector=MockLICollector(ok=li_ok, raise_exc=li_exc),
        stock_analysis_collector=MockSACollector(ok=sa_ok, raise_exc=sa_exc),
        backtest_engine=MockBacktestEngine(ok=bt_ok, raise_exc=bt_exc),
        strategy_analyzer=MockStrategyAnalyzer(ok=strat_ok, raise_exc=strat_exc),
    )


_SYMBOL = "TW:2330"
_START = "2026-01-05"
_END = "2026-06-14"

# ──────────────────────────────────────────────────────────────────────────────
# 1. Initialization
# ──────────────────────────────────────────────────────────────────────────────

class TestPanelBundleBuilderInit(unittest.TestCase):

    def test_init_no_args(self):
        b = PanelBundleBuilder()
        self.assertIsNotNone(b)

    def test_init_with_mocks(self):
        b = _make_builder()
        self.assertIsNotNone(b)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Bundle structure
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildStockBundle(unittest.TestCase):

    def setUp(self):
        self.builder = _make_builder()
        self.bundle = self.builder.build_stock_bundle(
            symbol=_SYMBOL,
            start_date=_START,
            end_date=_END,
            include_backtest=True,
            include_strategy_analysis=True,
        )

    def test_build_stock_bundle_returns_dict(self):
        self.assertIsInstance(self.bundle, dict)

    def test_bundle_ok_true(self):
        self.assertTrue(self.bundle.get("ok"))

    def test_bundle_id_present(self):
        self.assertTrue(self.bundle.get("bundle_id", "").startswith("bnd_"))

    def test_symbols_list(self):
        self.assertIn(_SYMBOL, self.bundle.get("symbols", []))

    def test_panels_is_list(self):
        self.assertIsInstance(self.bundle.get("panels"), list)

    def test_bundle_serializable_to_json(self):
        dumped = json.dumps(self.bundle)
        parsed = json.loads(dumped)
        self.assertEqual(parsed["ok"], True)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Panel presence
# ──────────────────────────────────────────────────────────────────────────────

class TestPanelPresence(unittest.TestCase):

    def setUp(self):
        self.builder = _make_builder()
        self.bundle = self.builder.build_stock_bundle(
            symbol=_SYMBOL,
            start_date=_START,
            end_date=_END,
            include_backtest=True,
            include_strategy_analysis=True,
        )
        self.panel_types = [p.get("panel_type") for p in self.bundle.get("panels", [])]

    def test_latest_info_panel_created(self):
        self.assertIn("latest_info", self.panel_types)

    def test_stock_analysis_panel_created(self):
        self.assertIn("stock_analysis", self.panel_types)

    def test_backtest_panel_created_when_enabled(self):
        self.assertIn("backtest", self.panel_types)

    def test_strategy_analysis_panel_created_when_enabled(self):
        self.assertIn("strategy_analysis", self.panel_types)

    def test_data_quality_panel_created(self):
        self.assertIn("data_quality", self.panel_types)

    def test_disabling_backtest_omits_backtest_panel(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END, include_backtest=False)
        types = [p.get("panel_type") for p in bundle.get("panels", [])]
        self.assertNotIn("backtest", types)

    def test_disabling_strategy_omits_strategy_panel(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END, include_strategy_analysis=False)
        types = [p.get("panel_type") for p in bundle.get("panels", [])]
        self.assertNotIn("strategy_analysis", types)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Bundle aggregation
# ──────────────────────────────────────────────────────────────────────────────

class TestBundleAggregation(unittest.TestCase):

    def setUp(self):
        self.builder = _make_builder()
        self.bundle = self.builder.build_stock_bundle(
            symbol=_SYMBOL, start_date=_START, end_date=_END
        )

    def test_bundle_aggregates_sources(self):
        self.assertIsInstance(self.bundle.get("sources"), list)

    def test_bundle_aggregates_warnings(self):
        self.assertIsInstance(self.bundle.get("warnings"), list)

    def test_recommended_prompts_is_list(self):
        self.assertIsInstance(self.bundle.get("recommended_prompts"), list)

    def test_data_quality_has_panel_count(self):
        dq = self.bundle.get("data_quality", {})
        self.assertIn("panel_count", dq)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Prompt card bindings
# ──────────────────────────────────────────────────────────────────────────────

class TestPromptCardBindings(unittest.TestCase):

    def setUp(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(
            symbol=_SYMBOL, start_date=_START, end_date=_END
        )
        self.prompt_cards = bundle.get("recommended_prompts", [])
        self.bundle_id = bundle.get("bundle_id")
        self.panels = bundle.get("panels", [])

    def test_prompt_cards_not_empty(self):
        self.assertGreater(len(self.prompt_cards), 0)

    def test_prompt_cards_include_panel_id(self):
        for pc in self.prompt_cards:
            self.assertIn("panel_id", pc, f"Missing panel_id in {pc.get('title')}")
            self.assertTrue(pc["panel_id"].startswith("pnl_"))

    def test_prompt_cards_include_snapshot_id(self):
        for pc in self.prompt_cards:
            self.assertIn("snapshot_id", pc)
            self.assertEqual(pc["snapshot_id"], self.bundle_id)

    def test_prompt_ids_are_deterministic(self):
        panel = self.panels[0]
        pid = panel["panel_id"]
        first_card = panel["prompt_cards"][0]
        expected_id = make_prompt_id(pid, first_card["title"])
        self.assertEqual(first_card["prompt_id"], expected_id)

    def test_prompt_ids_stable_across_builds(self):
        b = _make_builder()
        bundle2 = b.build_stock_bundle(_SYMBOL, _START, _END)
        ids1 = {pc["prompt_id"] for pc in self.prompt_cards}
        ids2 = {pc["prompt_id"] for pc in bundle2.get("recommended_prompts", [])}
        self.assertEqual(ids1, ids2)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Prompt safety
# ──────────────────────────────────────────────────────────────────────────────

class TestPromptSafety(unittest.TestCase):

    def setUp(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        self.prompt_cards = bundle.get("recommended_prompts", [])

    def _all_prompts(self) -> List[str]:
        return [pc.get("prompt", "") for pc in self.prompt_cards]

    def test_prompts_say_panel_only(self):
        for prompt in self._all_prompts():
            self.assertIn("panel", prompt, f"Missing 'panel' in prompt: {prompt[:80]}")

    def test_prompts_include_data_freshness_caveat(self):
        for pc in self.prompt_cards:
            self.assertIn("data_freshness", pc)
            self.assertIsInstance(pc["data_freshness"], dict)

    def test_prompts_contain_no_buy_sell(self):
        for pc in self.prompt_cards:
            violations = check_prompt_safety(pc.get("prompt", ""))
            self.assertEqual(violations, [], f"Forbidden terms in '{pc.get('title')}': {violations}")

    def test_prompts_no_external_fetch_request(self):
        for prompt in self._all_prompts():
            self.assertNotIn("請上網查", prompt)
            self.assertNotIn("即時搜尋", prompt)

    def test_prompts_reference_date_range(self):
        for prompt in self._all_prompts():
            self.assertIn(_END, prompt, f"Date not in prompt: {prompt[:80]}")

    def test_safety_tags_present_on_clean_prompts(self):
        for pc in self.prompt_cards:
            self.assertIn("safety_tags", pc)
            tags = pc["safety_tags"]
            self.assertIn("no_buysell", tags, f"no_buysell missing in {pc.get('title')}")

    def test_allowed_context_present(self):
        for pc in self.prompt_cards:
            self.assertIn("allowed_context", pc)
            self.assertIsInstance(pc["allowed_context"], list)


# ──────────────────────────────────────────────────────────────────────────────
# 7. Failure resilience
# ──────────────────────────────────────────────────────────────────────────────

class TestFailureResilience(unittest.TestCase):

    def test_li_failure_creates_warning_not_crash(self):
        b = _make_builder(li_exc=True)
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        self.assertIsInstance(bundle, dict)
        warnings = bundle.get("warnings", [])
        self.assertTrue(any("latest_info" in w for w in warnings))

    def test_sa_failure_creates_warning_not_crash(self):
        b = _make_builder(sa_exc=True)
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        self.assertIsInstance(bundle, dict)
        warnings = bundle.get("warnings", [])
        self.assertTrue(any("stock_analysis" in w for w in warnings))

    def test_bt_failure_creates_warning_not_crash(self):
        b = _make_builder(bt_exc=True)
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        self.assertIsInstance(bundle, dict)
        warnings = bundle.get("warnings", [])
        self.assertTrue(any("backtest" in w for w in warnings))

    def test_strat_failure_creates_warning_not_crash(self):
        b = _make_builder(strat_exc=True)
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        self.assertIsInstance(bundle, dict)
        warnings = bundle.get("warnings", [])
        self.assertTrue(any("strategy_analysis" in w for w in warnings))

    def test_failure_panel_has_error_flag(self):
        panel = _failure_panel("bnd_test", "backtest", "TW:2330", _END, "test error")
        self.assertTrue(panel.get("_error"))

    def test_failure_panel_included_in_missing(self):
        panel = _failure_panel("bnd_test", "backtest", "TW:2330", _END, "test error")
        self.assertIn("backtest", panel.get("missing", []))


# ──────────────────────────────────────────────────────────────────────────────
# 8. Symbol safety
# ──────────────────────────────────────────────────────────────────────────────

class TestSymbolSafety(unittest.TestCase):

    def test_non_tw_symbol_rejected(self):
        b = _make_builder()
        bundle = b.build_stock_bundle("US:AAPL", _START, _END)
        self.assertFalse(bundle.get("ok"))
        dq = bundle.get("data_quality", {})
        self.assertFalse(dq.get("valid_symbol"))

    def test_cn_symbol_rejected(self):
        b = _make_builder()
        bundle = b.build_stock_bundle("2330", _START, _END)
        self.assertFalse(bundle.get("ok"))

    def test_cn_symbol_rejected_with_warning(self):
        b = _make_builder()
        bundle = b.build_stock_bundle("2330", _START, _END)
        warnings = bundle.get("warnings", [])
        self.assertGreater(len(warnings), 0)

    def test_tw_symbol_prefix_accepted(self):
        b = _make_builder()
        bundle = b.build_stock_bundle("TW:2330", _START, _END)
        self.assertTrue(bundle.get("ok"))

    def test_bare_tw_symbol_accepted(self):
        b = _make_builder()
        bundle = b.build_stock_bundle("2330", _START, _END)
        self.assertTrue(bundle.get("ok"))


# ──────────────────────────────────────────────────────────────────────────────
# 9. No CN/A-share terms in bundle
# ──────────────────────────────────────────────────────────────────────────────

class TestNoCNTerms(unittest.TestCase):

    _CN_TERMS = ["台股", "上證", "上證", "深證", "深證", "創業板", "創業板", "科創50", "科創50"]

    def test_no_cn_terms_in_bundle(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        bundle_text = json.dumps(bundle, ensure_ascii=False)
        found = [t for t in self._CN_TERMS if t in bundle_text]
        self.assertEqual(found, [])

    def test_no_cn_terms_in_prompt_cards(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        for pc in bundle.get("recommended_prompts", []):
            prompt = pc.get("prompt", "")
            found = [t for t in self._CN_TERMS if t in prompt]
            self.assertEqual(found, [], f"CN terms in prompt: {found}")


# ──────────────────────────────────────────────────────────────────────────────
# 10. No LLM calls
# ──────────────────────────────────────────────────────────────────────────────

class TestNoLLMCall(unittest.TestCase):

    def test_no_openai_import(self):
        import sys
        b = _make_builder()
        before_modules = set(sys.modules.keys())
        b.build_stock_bundle(_SYMBOL, _START, _END)
        after_modules = set(sys.modules.keys())
        new_modules = after_modules - before_modules
        llm_modules = [m for m in new_modules if "openai" in m or "anthropic" in m or "langchain" in m]
        self.assertEqual(llm_modules, [])

    def test_build_does_not_call_actual_main(self):
        import sys
        b = _make_builder()
        mods_before = set(sys.modules.keys())
        b.build_stock_bundle(_SYMBOL, _START, _END)
        new = set(sys.modules.keys()) - mods_before
        self.assertFalse(any(m == "main" for m in new))


# ──────────────────────────────────────────────────────────────────────────────
# 11. Deterministic IDs
# ──────────────────────────────────────────────────────────────────────────────

class TestDeterministicIDs(unittest.TestCase):

    def test_bundle_id_is_deterministic(self):
        id1 = make_bundle_id(["TW:2330"], _START, _END)
        id2 = make_bundle_id(["TW:2330"], _START, _END)
        self.assertEqual(id1, id2)

    def test_bundle_id_starts_with_bnd(self):
        self.assertTrue(make_bundle_id(["TW:2330"], _START, _END).startswith("bnd_"))

    def test_panel_id_is_deterministic(self):
        bnd = make_bundle_id(["TW:2330"], _START, _END)
        p1 = make_panel_id(bnd, "backtest", "TW:2330")
        p2 = make_panel_id(bnd, "backtest", "TW:2330")
        self.assertEqual(p1, p2)

    def test_panel_id_differs_by_type(self):
        bnd = make_bundle_id(["TW:2330"], _START, _END)
        self.assertNotEqual(
            make_panel_id(bnd, "backtest", "TW:2330"),
            make_panel_id(bnd, "strategy_analysis", "TW:2330"),
        )

    def test_prompt_id_is_deterministic(self):
        p1 = make_prompt_id("pnl_abc", "回測成本分析")
        p2 = make_prompt_id("pnl_abc", "回測成本分析")
        self.assertEqual(p1, p2)

    def test_prompt_id_starts_with_prc(self):
        self.assertTrue(make_prompt_id("pnl_abc", "title").startswith("prc_"))


# ──────────────────────────────────────────────────────────────────────────────
# 12. Data quality panel
# ──────────────────────────────────────────────────────────────────────────────

class TestDataQualityPanel(unittest.TestCase):

    def setUp(self):
        b = _make_builder()
        bundle = b.build_stock_bundle(_SYMBOL, _START, _END)
        panels = bundle.get("panels", [])
        self.dq_panel = next(
            (p for p in panels if p.get("panel_type") == "data_quality"), None
        )

    def test_data_quality_panel_exists(self):
        self.assertIsNotNone(self.dq_panel)

    def test_data_quality_has_missing_datasets(self):
        km = self.dq_panel.get("key_metrics", {})
        self.assertIn("missing_datasets", km)

    def test_data_quality_has_tier_caveats(self):
        km = self.dq_panel.get("key_metrics", {})
        self.assertIn("tier_caveats", km)

    def test_data_quality_prompt_is_safe(self):
        for pc in self.dq_panel.get("prompt_cards", []):
            self.assertNotIn("買進", pc.get("prompt", ""))
            self.assertNotIn("買進", pc.get("prompt", ""))


# ──────────────────────────────────────────────────────────────────────────────
# 13. Market bundle
# ──────────────────────────────────────────────────────────────────────────────

class TestMarketBundle(unittest.TestCase):

    def test_build_market_bundle_returns_dict(self):
        b = _make_builder()
        result = b.build_market_bundle(
            symbols=["TW:2330", "TW:2317"],
            start_date=_START,
            end_date=_END,
        )
        self.assertIsInstance(result, dict)

    def test_market_bundle_has_panel_list(self):
        b = _make_builder()
        result = b.build_market_bundle(["TW:2330"], _START, _END)
        self.assertIsInstance(result.get("panels"), list)

    def test_market_bundle_no_backtest_panels(self):
        b = _make_builder()
        result = b.build_market_bundle(["TW:2330"], _START, _END)
        types = [p.get("panel_type") for p in result.get("panels", [])]
        self.assertNotIn("backtest", types)

    def test_market_bundle_no_strategy_panels(self):
        b = _make_builder()
        result = b.build_market_bundle(["TW:2330"], _START, _END)
        types = [p.get("panel_type") for p in result.get("panels", [])]
        self.assertNotIn("strategy_analysis", types)


# ──────────────────────────────────────────────────────────────────────────────
# 14. build_prompt_card standalone
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildPromptCard(unittest.TestCase):

    def test_clean_prompt_gets_safety_tags(self):
        pc = build_prompt_card(
            panel_id="pnl_test",
            snapshot_id="bnd_test",
            title="測試 prompt",
            prompt="請只根據本 backtest panel 的資料，不引用外部資訊。",
            allowed_context=["backtest_panel"],
            data_freshness={"as_of": "2026-06-14"},
        )
        self.assertIn("no_buysell", pc["safety_tags"])
        self.assertIn("snapshot_bound", pc["safety_tags"])

    def test_forbidden_prompt_gets_violation_tag(self):
        pc = build_prompt_card(
            panel_id="pnl_test",
            snapshot_id="bnd_test",
            title="危險 prompt",
            prompt="請推薦買進 2330。",
            allowed_context=[],
            data_freshness={},
        )
        self.assertIn("safety_violation", pc["safety_tags"])

    def test_check_prompt_safety_detects_forbidden(self):
        found = check_prompt_safety("應該買進 2330。")
        self.assertIn("買進", found)

    def test_check_prompt_safety_clean_returns_empty(self):
        found = check_prompt_safety("請只根據本 panel 資料描述趨勢。")
        self.assertEqual(found, [])

    def test_prompt_card_has_all_required_fields(self):
        pc = build_prompt_card(
            panel_id="pnl_x",
            snapshot_id="bnd_y",
            title="X",
            prompt="請只根據本 panel 描述。",
            allowed_context=["panel_x"],
            data_freshness={"as_of": "2026-06-14"},
            caveats=["note 1"],
        )
        for field in ["prompt_id", "title", "prompt", "panel_id", "snapshot_id",
                      "allowed_context", "data_freshness", "safety_tags", "caveats"]:
            self.assertIn(field, pc, f"Missing field: {field}")


if __name__ == "__main__":
    unittest.main()

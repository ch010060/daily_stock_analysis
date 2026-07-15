# -*- coding: utf-8 -*-
"""
Tests for TW market review rendering path (Phase 7E.3).

All tests use fixtures/mocks only — no live provider calls.
"""

import os
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from src.core.tw_market_review import (
    build_tw_market_review_context,
    render_tw_market_review_text,
)
from src.core.market_review import _MARKET_REVIEW_MARKETS, _get_market_review_text
from src.core.market_review_scope_gate import (
    _DEFERRED_REGIONS,
    filter_regions_for_route_b,
)

_FORBIDDEN_CN_TERMS = [
    "上證", "上证", "深證", "深证", "創業板", "创业板",
    "科創50", "科创50", "沪深", "滬深", "大盘复盘",
]

_FIXTURE_ENV = {
    "DSA_FIXTURE_MODE": "true",
    "DSA_ALLOW_EXTERNAL_NETWORK": "false",
}


def _full_fixture_snapshot() -> Dict[str, Any]:
    """Build a full snapshot using TaiwanMarketDataFetcher in fixture mode (no network)."""
    with patch.dict(os.environ, _FIXTURE_ENV):
        from data_provider.taiwan_market import TaiwanMarketDataFetcher
        fetcher = TaiwanMarketDataFetcher()
        return fetcher.get_tw_market_snapshot("2026-06-10", "2026-06-12")


def _unavail(dataset: str, data_id: str = None, reason: str = "test_unavailable") -> Dict[str, Any]:
    return {
        "ok": False,
        "source": "finmind",
        "dataset": dataset,
        "data_id": data_id,
        "rows": [],
        "columns": [],
        "row_count": 0,
        "start_date": "2026-06-10",
        "end_date": "2026-06-12",
        "error": reason,
        "unavailable_reason": reason,
        "cache_meta": {},
    }


def _success(dataset: str, data_id: str, rows: List[Dict]) -> Dict[str, Any]:
    return {
        "ok": True,
        "source": "finmind",
        "dataset": dataset,
        "data_id": data_id,
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "row_count": len(rows),
        "start_date": "2026-06-10",
        "end_date": "2026-06-12",
        "error": None,
        "unavailable_reason": None,
        "cache_meta": {},
    }


def _empty_snapshot() -> Dict[str, Any]:
    """Snapshot where all sections are unavailable."""
    base = {
        "taiex": _unavail("TaiwanStockTotalReturnIndex", "TAIEX"),
        "tpex": _unavail("TaiwanStockTotalReturnIndex", "TPEx", "yfinance_no_symbol"),
        "institutional_total": _unavail("TaiwanStockTotalInstitutionalInvestors"),
        "margin_total": _unavail("TaiwanStockTotalMarginPurchaseShortSale"),
        "trading_dates": _unavail("TaiwanStockTradingDate"),
        "ref_0050": _unavail("TaiwanStockPrice", "0050"),
        "ref_2330": _unavail("TaiwanStockPrice", "2330"),
    }
    base["availability"] = {
        "required_ok": False,
        "partial": False,
        "missing_required": ["taiex", "institutional_total", "margin_total", "trading_dates"],
        "missing_optional": ["tpex", "ref_0050", "ref_2330"],
        "sources": [],
        "as_of": None,
    }
    return base


class TestTWMarketReviewTitle(unittest.TestCase):
    """Test 1: Fixture snapshot renders title # 台股大盤回顧"""

    def test_title_in_fixture_render(self):
        snapshot = _full_fixture_snapshot()
        text = render_tw_market_review_text(snapshot)
        self.assertIn("# 台股大盤回顧", text)


class TestTWMarketTechnicalNarrativeRendering(unittest.TestCase):
    def test_analysis_article_is_rendered_as_integrated_prose(self):
        snapshot = _full_fixture_snapshot()
        snapshot["tw_daily_snapshot"]["tw_market_analysis_snapshot"] = {
            "kind": "tw_market_analysis_snapshot",
            "analysis_ready": True,
            "data_date": "2026-07-14",
            "market_state": "closed",
            "analysis_article": {
                "status": "available",
                "headline": "台股加權指數最新技術分析",
                "market_context": "資料時間：2026 年 7 月 15 日 06:30（台股尚未開盤）",
                "session_summary": "最新完整交易日加權指數收在 44,737.95 點，下跌 642.57 點。",
                "core_judgement": {"label": "短空中多", "summary": "低檔出現承接，但尚未確認止跌。"},
                "trend_paragraphs": [
                    "指數低於 MA5、MA10 與 MA20，但仍高於 MA60 與 MA120，因此短線偏空、中期多頭結構尚未破壞。",
                    "RSI14 位於中性偏弱區，MACD 仍處空方結構，反彈動能尚未確認。",
                ],
                "price_action_paragraphs": ["指數下探支撐區後收回部分跌幅，成交金額接近近期均值，顯示低檔有承接但止跌尚未確認。"],
                "confirmation_paragraph": "收盤先站回 MA5 再收復 MA10 與 MA20，反彈確認度才會提高；跌破主要支撐則修正風險升高。",
                "supporting_context": ["外資偏賣、投信偏買，法人方向分歧，尚不足以改變技術面判斷。"],
                "tpex_context": "櫃買指數弱於加權指數，市場廣度尚未止穩。",
            },
            "narrative": {
                "title": "不應優先使用的舊 checklist",
                "moving_average_analysis": ["指數低於 MA5，距離 -1.32%。"],
            },
        }

        text = render_tw_market_review_text(snapshot)

        self.assertTrue(text.startswith("# 台股加權指數最新技術分析"))
        self.assertIn("**短空中多｜低檔出現承接，但尚未確認止跌。**", text)
        self.assertIn("MA5、MA10 與 MA20，但仍高於 MA60 與 MA120", text)
        self.assertIn("RSI14 位於中性偏弱區，MACD 仍處空方結構", text)
        self.assertIn("成交金額接近近期均值", text)
        self.assertIn("收盤先站回 MA5", text)
        self.assertIn("法人方向分歧", text)
        self.assertNotIn("均線位置與結構", text)
        self.assertNotIn("- 指數低於 MA5", text)
        self.assertNotIn("不應優先使用的舊 checklist", text)

    def test_usable_analysis_snapshot_becomes_primary_markdown_body(self):
        snapshot = _full_fixture_snapshot()
        snapshot["tw_daily_snapshot"]["tw_market_analysis_snapshot"] = {
            "kind": "tw_market_analysis_snapshot",
            "analysis_ready": True,
            "data_date": "2026-06-12",
            "market_state": "closed",
            "narrative": {
                "title": "台股加權指數最新技術分析",
                "opening_summary": "加權指數收在 22,100 點，單日上漲 120 點。",
                "core_judgement": ["反彈中但未確認翻多"],
                "moving_average_analysis": ["指數仍低於 MA20。"],
                "momentum_analysis": ["RSI14 回升，MACD 空方動能收斂。"],
                "price_action_analysis": ["K 線出現長下影線。"],
                "volume_analysis": ["TWSE 成交金額低於近 20 日均值。"],
                "support_resistance_analysis": ["支撐區 21,800–22,000 點。"],
                "confirmation_conditions": ["收盤站回 MA20。"],
                "invalidation_conditions": ["收盤跌破近期低點。"],
                "tpex_breadth": ["櫃買指數同步止穩。"],
            },
        }

        text = render_tw_market_review_text(snapshot)

        self.assertTrue(text.startswith("# 台股加權指數最新技術分析"))
        for heading in ("核心判斷", "均線位置與結構", "動能 / 指標解讀", "K 線與量價訊號", "支撐 / 壓力 / 觀察區", "反彈確認條件", "失效 / 轉弱條件", "TPEx / 廣度補充"):
            self.assertIn(heading, text)
        self.assertNotIn("## 資料可用性說明", text)

    def test_unavailable_analysis_snapshot_keeps_legacy_markdown(self):
        snapshot = _full_fixture_snapshot()
        snapshot["tw_daily_snapshot"]["tw_market_analysis_snapshot"] = {
            "kind": "tw_market_analysis_snapshot",
            "analysis_ready": False,
            "narrative": {},
        }

        text = render_tw_market_review_text(snapshot)

        self.assertTrue(text.startswith("# 台股大盤回顧"))
        self.assertIn("## 指數表現", text)

    def test_title_in_degraded_render(self):
        text = render_tw_market_review_text(_empty_snapshot())
        self.assertIn("# 台股大盤回顧", text)


class TestTWMarketReviewRequiredKeywords(unittest.TestCase):
    """Tests 2-7: Rendered text includes required labels."""

    def setUp(self):
        self._snapshot = _full_fixture_snapshot()

    def test_contains_taiex_label(self):
        text = render_tw_market_review_text(self._snapshot)
        self.assertIn("加權", text)

    def test_contains_tpex_label(self):
        text = render_tw_market_review_text(self._snapshot)
        self.assertIn("櫃買", text)

    def test_contains_institutional_label(self):
        text = render_tw_market_review_text(self._snapshot)
        self.assertIn("法人", text)

    def test_contains_margin_label(self):
        text = render_tw_market_review_text(self._snapshot)
        self.assertIn("融資", text)

    def test_contains_0050_label(self):
        text = render_tw_market_review_text(self._snapshot)
        self.assertIn("0050", text)

    def test_contains_2330_label(self):
        text = render_tw_market_review_text(self._snapshot)
        self.assertIn("臺積電", text)


class TestTWMarketReviewMissingData(unittest.TestCase):
    """Tests 8-12: Missing data sections render explicit unavailable status."""

    def _snapshot_without_taiex(self) -> Dict[str, Any]:
        snapshot = _full_fixture_snapshot()
        snapshot["taiex"] = _unavail("TaiwanStockTotalReturnIndex", "TAIEX")
        snapshot["availability"]["required_ok"] = False
        snapshot["availability"]["missing_required"] = ["taiex"]
        return snapshot

    def _snapshot_without_tpex(self) -> Dict[str, Any]:
        snapshot = _full_fixture_snapshot()
        snapshot["tpex"] = _unavail(
            "TaiwanStockTotalReturnIndex", "TPEx", "yfinance_no_symbol"
        )
        snap_opt = list(snapshot["availability"].get("missing_optional", []))
        if "tpex" not in snap_opt:
            snap_opt.append("tpex")
        snapshot["availability"]["missing_optional"] = snap_opt
        return snapshot

    def _snapshot_without_institutional(self) -> Dict[str, Any]:
        snapshot = _full_fixture_snapshot()
        snapshot["institutional_total"] = _unavail("TaiwanStockTotalInstitutionalInvestors")
        snapshot["availability"]["required_ok"] = False
        snapshot["availability"]["missing_required"] = ["institutional_total"]
        return snapshot

    def _snapshot_without_margin(self) -> Dict[str, Any]:
        snapshot = _full_fixture_snapshot()
        snapshot["margin_total"] = _unavail("TaiwanStockTotalMarginPurchaseShortSale")
        snapshot["availability"]["required_ok"] = False
        snapshot["availability"]["missing_required"] = ["margin_total"]
        return snapshot

    def test_missing_taiex_renders_unavailable(self):
        """Test 8: Missing TAIEX renders explicit unavailable."""
        text = render_tw_market_review_text(self._snapshot_without_taiex())
        self.assertIn("資料暫不可用", text)

    def test_missing_tpex_does_not_raise(self):
        """Test 9: Missing TPEx does not fail the whole report."""
        try:
            text = render_tw_market_review_text(self._snapshot_without_tpex())
        except Exception as exc:
            self.fail(f"render_tw_market_review_text raised {exc} on missing TPEx")
        self.assertIn("台股大盤回顧", text)

    def test_missing_tpex_shows_unavailable_without_cn_fallback(self):
        """Test 9b: Missing TPEx shows unavailable and no CN fallback."""
        text = render_tw_market_review_text(self._snapshot_without_tpex())
        self.assertIn("資料暫不可用", text)
        for term in _FORBIDDEN_CN_TERMS:
            self.assertNotIn(term, text, f"Forbidden CN term '{term}' found in missing-TPEx render")

    def test_missing_institutional_renders_unavailable(self):
        """Test 10: Missing institutional rows renders explicit unavailable."""
        text = render_tw_market_review_text(self._snapshot_without_institutional())
        self.assertIn("資料暫不可用", text)
        self.assertIn("本段略過，未 fallback 至其他市場", text)

    def test_missing_margin_renders_unavailable(self):
        """Test 11: Missing margin rows renders explicit unavailable."""
        text = render_tw_market_review_text(self._snapshot_without_margin())
        self.assertIn("資料暫不可用", text)
        self.assertIn("本段略過，未 fallback 至其他市場", text)


class TestTWMarketReviewNoCNTerms(unittest.TestCase):
    """Tests 12-13: No forbidden CN/A-share terms in any render."""

    def test_no_forbidden_terms_in_full_render(self):
        """Test 12: No CN/A-share forbidden terms in full fixture render."""
        snapshot = _full_fixture_snapshot()
        text = render_tw_market_review_text(snapshot)
        found = [t for t in _FORBIDDEN_CN_TERMS if t in text]
        self.assertEqual([], found, f"Forbidden CN terms found: {found}")

    def test_no_forbidden_terms_in_degraded_render(self):
        """Test 13: No CN/A-share forbidden terms even when all data is unavailable."""
        text = render_tw_market_review_text(_empty_snapshot())
        found = [t for t in _FORBIDDEN_CN_TERMS if t in text]
        self.assertEqual([], found, f"Forbidden CN terms found in degraded render: {found}")


class TestTWMarketReviewZhTW(unittest.TestCase):
    """Test 14: TW rendering uses zh_TW Traditional Chinese headings."""

    def test_output_uses_zh_tw_headings(self):
        snapshot = _full_fixture_snapshot()
        text = render_tw_market_review_text(snapshot)
        for heading in (
            "台股大盤回顧",
            "指數表現",
            "法人與資金面",
            "融資融券觀察",
            "風險與注意事項",
            "資料可用性說明",
        ):
            self.assertIn(heading, text, f"zh_TW heading '{heading}' missing from output")

    def test_output_contains_zh_tw_section_summary(self):
        snapshot = _full_fixture_snapshot()
        text = render_tw_market_review_text(snapshot)
        self.assertIn("今日盤勢摘要", text)


class TestTWMarketReviewNumericValues(unittest.TestCase):
    """Test 15: TW formatter preserves numeric values from fixture."""

    def test_formatter_preserves_taiex_last_price(self):
        """TAIEX last fixture price (100933.47) must appear formatted in output."""
        snapshot = _full_fixture_snapshot()
        text = render_tw_market_review_text(snapshot)
        self.assertIn("100,933.47", text)

    def test_formatter_preserves_2330_close(self):
        """2330 close from fixture (2310.0) must appear in output."""
        snapshot = _full_fixture_snapshot()
        text = render_tw_market_review_text(snapshot)
        self.assertIn("2310", text)

    def test_custom_taiex_price_preserved(self):
        """Custom TAIEX price value must appear in formatted output."""
        rows = [
            {"date": "2026-06-10", "stock_id": "TAIEX", "price": 99000.00},
            {"date": "2026-06-12", "stock_id": "TAIEX", "price": 101234.56},
        ]
        snapshot = _full_fixture_snapshot()
        snapshot["taiex"] = _success("TaiwanStockTotalReturnIndex", "TAIEX", rows)
        text = render_tw_market_review_text(snapshot)
        self.assertIn("101,234.56", text)


class TestTWMarketReviewUsesCorrectProvider(unittest.TestCase):
    """Test 16: TW formatter uses TaiwanMarketDataFetcher snapshot, not CN/US analyzer."""

    def test_formatter_accepts_tw_snapshot_shape(self):
        snapshot = _full_fixture_snapshot()
        # Verify snapshot has the expected TaiwanMarketDataFetcher keys
        for key in ("taiex", "institutional_total", "margin_total", "availability"):
            self.assertIn(key, snapshot, f"Expected key '{key}' missing from snapshot")
        # Formatter must produce output without MarketAnalyzer
        text = render_tw_market_review_text(snapshot)
        self.assertIn("台股大盤回顧", text)

    def test_formatter_module_has_no_cn_provider_imports(self):
        """tw_market_review.py must not import CN/A-share provider names."""
        import inspect
        import src.core.tw_market_review as mod
        source = inspect.getsource(mod)
        for forbidden_import in (
            "AkShare", "akshare", "eastmoney", "TaiwanFinMindFetcher",
            "cn_provider", "上证", "深证",
        ):
            self.assertNotIn(
                forbidden_import, source,
                f"Forbidden import '{forbidden_import}' found in tw_market_review.py",
            )

    def test_renderer_has_no_provider_or_llm_runtime_dependency(self):
        import inspect
        import src.core.tw_market_review as mod

        source = inspect.getsource(mod)
        for forbidden in (
            "OfficialTaiwanExchangeProvider",
            "from data_provider",
            "requests.get",
            "GeminiAnalyzer",
            "OpenAI",
        ):
            self.assertNotIn(forbidden, source)

    def test_build_context_returns_required_keys(self):
        snapshot = _full_fixture_snapshot()
        ctx = build_tw_market_review_context(snapshot)
        for key in (
            "taiex_ok", "tpex_ok", "institutional_ok", "margin_ok",
            "ref_0050_ok", "ref_2330_ok", "required_ok", "as_of",
        ):
            self.assertIn(key, ctx, f"Context missing key '{key}'")


class TestMarketReviewMapsHasTW(unittest.TestCase):
    """Test 17: _MARKET_REVIEW_MARKETS has TW handler and _get_market_review_text has tw_title."""

    def test_market_review_markets_has_tw(self):
        regions = [mkt for mkt, _, _ in _MARKET_REVIEW_MARKETS]
        self.assertIn("tw", regions)

    def test_market_review_markets_tw_label(self):
        labels = {mkt: label for mkt, _, label in _MARKET_REVIEW_MARKETS}
        self.assertEqual("台股", labels["tw"])

    def test_get_market_review_text_zh_tw_has_tw_title(self):
        texts = _get_market_review_text("zh_TW")
        self.assertIn("tw_title", texts)
        self.assertIn("台股", texts["tw_title"])

    def test_get_market_review_text_en_has_tw_title(self):
        texts = _get_market_review_text("en")
        self.assertIn("tw_title", texts)
        self.assertIn("TW", texts["tw_title"])

    def test_get_market_review_text_zh_has_tw_title(self):
        texts = _get_market_review_text("zh")
        self.assertIn("tw_title", texts)

    def test_tw_title_zh_tw_no_simplified(self):
        texts = _get_market_review_text("zh_TW")
        tw_title = texts["tw_title"]
        for simplified in ("大盘", "复盘"):
            self.assertNotIn(simplified, tw_title, f"Simplified '{simplified}' in TW zh_TW title")


class TestScopeGateStillDefersTW(unittest.TestCase):
    """Test 18: market_review_scope_gate — TW is now implemented (Phase 7E-FINAL)."""

    def test_tw_not_in_deferred_regions(self):
        self.assertNotIn("tw", _DEFERRED_REGIONS)

    def test_filter_regions_tw_routes_to_run(self):
        run, _, deferred_tw = filter_regions_for_route_b(["tw", "us"])
        self.assertIn("tw", run)
        self.assertEqual(deferred_tw, [])

    def test_filter_regions_tw_only_returns_tw_in_run(self):
        run, _, _ = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run)

    def test_us_still_runs_after_tw_added_to_map(self):
        """Adding TW to _MARKET_REVIEW_MARKETS must not block US from running."""
        run, _, _ = filter_regions_for_route_b(["us"])
        self.assertIn("us", run)


if __name__ == "__main__":
    unittest.main()

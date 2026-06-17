# -*- coding: utf-8 -*-
"""Tests for Route B zh_TW localization module."""

import unittest
from unittest.mock import patch

from src.core.zh_tw_localization import (
    localize_route_b_zh_tw_text,
    localize_if_route_b,
    is_route_b_zh_tw_active,
)
from src.core.market_review import _get_market_review_text


class TestLocalizeRouteBZhTwText(unittest.TestCase):
    """Unit tests for localize_route_b_zh_tw_text()."""

    def test_none_returns_empty_string(self):
        self.assertEqual(localize_route_b_zh_tw_text(None), "")

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(localize_route_b_zh_tw_text(""), "")

    def test_decision_dashboard(self):
        result = localize_route_b_zh_tw_text("决策仪表盘日报")
        self.assertIn("決策儀錶板", result)
        self.assertNotIn("决策仪表盘", result)

    def test_watch_term(self):
        result = localize_route_b_zh_tw_text("操作建议：观望")
        self.assertIn("觀望", result)
        self.assertNotIn("观望", result)

    def test_score_term(self):
        result = localize_route_b_zh_tw_text("评分 45")
        self.assertIn("評分", result)
        self.assertNotIn("评分", result)

    def test_risk_term(self):
        result = localize_route_b_zh_tw_text("风险提示：价格波动")
        self.assertIn("風險", result)
        self.assertNotIn("风险", result)

    def test_suggestion_term(self):
        result = localize_route_b_zh_tw_text("建议持有")
        self.assertIn("建議", result)
        self.assertNotIn("建议", result)

    def test_volume_unit(self):
        result = localize_route_b_zh_tw_text("成交量 100万股")
        self.assertIn("萬股", result)
        self.assertNotIn("万股", result)

    def test_amount_unit(self):
        result = localize_route_b_zh_tw_text("成交额 50亿元")
        self.assertIn("億元", result)
        self.assertNotIn("亿元", result)

    def test_sp500_term(self):
        result = localize_route_b_zh_tw_text("标普500指数")
        self.assertIn("標普", result)
        self.assertIn("指數", result)
        self.assertNotIn("标普", result)
        self.assertNotIn("指数", result)

    def test_market_review_title(self):
        result = localize_route_b_zh_tw_text("大盘复盘")
        self.assertIn("大盤回顧", result)
        self.assertNotIn("大盘复盘", result)

    def test_buy_sell_terms(self):
        result = localize_route_b_zh_tw_text("买入 / 卖出")
        self.assertIn("買進", result)
        self.assertIn("賣出", result)

    def test_trend_terms(self):
        result = localize_route_b_zh_tw_text("上涨趋势，压力位支撑")
        self.assertIn("上漲", result)
        self.assertIn("趨勢", result)
        self.assertIn("壓力", result)
        self.assertIn("支撐", result)

    def test_us_stock_symbol_preserved(self):
        text = "分析 US:AAPL 的评分"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn("US:AAPL", result)
        self.assertIn("評分", result)

    def test_tw_stock_symbol_preserved(self):
        text = "TW:2330 风险分析"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn("TW:2330", result)
        self.assertIn("風險", result)

    def test_url_preserved(self):
        url = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
        text = f"数据来源: {url}"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn(url, result)
        self.assertIn("來源", result)

    def test_inline_code_preserved(self):
        text = "运行 `观望` 模式"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn("`观望`", result)

    def test_fenced_code_preserved(self):
        text = "示例：\n```\n观望\n```\n说明"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn("观望", result)

    def test_markdown_preserved(self):
        md = "## 风险提示\n\n- 评分 50\n- 建议观望"
        result = localize_route_b_zh_tw_text(md)
        self.assertIn("## 風險提示", result)
        self.assertIn("- 評分 50", result)
        self.assertIn("- 建議觀望", result)


class TestLocalizeIfRouteB(unittest.TestCase):
    """Tests for localize_if_route_b() conditional wrapper."""

    def test_passthrough_when_route_b_inactive(self):
        text = "观望 评分 风险"
        with patch(
            "src.core.zh_tw_localization.is_route_b_zh_tw_active", return_value=False
        ):
            result = localize_if_route_b(text)
        self.assertEqual(result, text)

    def test_converts_when_route_b_active(self):
        text = "观望 评分 风险"
        with patch(
            "src.core.zh_tw_localization.is_route_b_zh_tw_active", return_value=True
        ):
            result = localize_if_route_b(text)
        self.assertIn("觀望", result)
        self.assertIn("評分", result)
        self.assertIn("風險", result)

    def test_none_returns_empty_when_active(self):
        with patch(
            "src.core.zh_tw_localization.is_route_b_zh_tw_active", return_value=True
        ):
            self.assertEqual(localize_if_route_b(None), "")

    def test_none_returns_empty_when_inactive(self):
        with patch(
            "src.core.zh_tw_localization.is_route_b_zh_tw_active", return_value=False
        ):
            self.assertEqual(localize_if_route_b(None), "")


class TestMarketReviewTitles(unittest.TestCase):
    """Tests for _get_market_review_text() zh_TW variant."""

    def test_zh_tw_root_title_no_simplified(self):
        texts = _get_market_review_text("zh_TW")
        self.assertNotIn("大盘复盘", texts["root_title"])
        self.assertIn("大盤回顧", texts["root_title"])

    def test_zh_tw_us_title(self):
        texts = _get_market_review_text("zh_TW")
        self.assertEqual(texts["us_title"], "# 美股大盤回顧")

    def test_zh_tw_cn_title(self):
        texts = _get_market_review_text("zh_TW")
        self.assertEqual(texts["cn_title"], "# A股大盤回顧")

    def test_zh_tw_hk_title(self):
        texts = _get_market_review_text("zh_TW")
        self.assertEqual(texts["hk_title"], "# 港股大盤回顧")

    def test_zh_tw_alias_resolves(self):
        texts = _get_market_review_text("zh-tw")
        self.assertIn("大盤回顧", texts["root_title"])

    def test_zh_default_unchanged(self):
        texts = _get_market_review_text("zh")
        self.assertIn("大盤", texts["root_title"])

    def test_en_unchanged(self):
        texts = _get_market_review_text("en")
        self.assertIn("Market Review", texts["root_title"])

    def test_zh_tw_no_simplified_terms_in_separator(self):
        texts = _get_market_review_text("zh_TW")
        simplified_terms = ["盘", "场", "报"]
        for term in simplified_terms:
            self.assertNotIn(term, texts["separator"], f"simplified '{term}' in separator")


class TestRouteBreportForbiddenTerms(unittest.TestCase):
    """Verify that Route B output does not contain known simplified-Chinese terms."""

    FORBIDDEN_SIMPLIFIED = [
        "大盘复盘",
        "决策仪表盘",
        "观望",
        "评分",
        "风险",
        "建议",
        "标普",
        "指数",
        "市场",
        "万股",
        "亿元",
    ]

    def _make_sample_report(self) -> str:
        return (
            "# 🎯 大盘复盘\n\n"
            "## 决策仪表盘\n\n"
            "操作建议：观望\n"
            "评分：45\n"
            "风险提示：高\n"
            "标普500指数 下跌\n"
            "市场 数据 报告\n"
            "成交量 100万股 50亿元\n"
        )

    def test_localized_report_has_no_forbidden_simplified(self):
        raw = self._make_sample_report()
        localized = localize_route_b_zh_tw_text(raw)
        for term in self.FORBIDDEN_SIMPLIFIED:
            self.assertNotIn(term, localized, f"simplified term '{term}' still present after localization")

    def test_localized_market_review_title_no_simplified(self):
        raw_title = "# 🎯 大盘复盘"
        result = localize_route_b_zh_tw_text(raw_title)
        self.assertNotIn("大盘复盘", result)
        self.assertIn("大盤回顧", result)

    def test_localized_us_market_review_no_simplified(self):
        raw = "# 美股大盘复盘\n\n标普500指数 今日上涨，市场情绪积极。"
        result = localize_route_b_zh_tw_text(raw)
        self.assertNotIn("大盘复盘", result)
        self.assertNotIn("标普", result)
        self.assertNotIn("指数", result)
        self.assertNotIn("市场", result)
        self.assertIn("大盤回顧", result)
        self.assertIn("標普", result)
        self.assertIn("指數", result)
        self.assertIn("市場", result)


if __name__ == "__main__":
    unittest.main()

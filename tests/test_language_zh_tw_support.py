# -*- coding: utf-8 -*-
"""Tests for zh_TW Traditional Chinese language support.

Covers:
- normalize_report_language aliases
- Config default language
- Report labels distinction (zh vs zh_TW)
- zh_TW localization term conversion
- Existing zh/en paths unchanged
"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.report_language import (
    SUPPORTED_REPORT_LANGUAGES,
    get_report_labels,
    normalize_report_language,
    is_supported_report_language_value,
    localize_operation_advice as _real_localize_op,
    localize_trend_prediction as _real_localize_trend,
)
from src.core.zh_tw_localization import (
    localize_route_b_zh_tw_text,
    localize_if_route_b,
)


class TestNormalizeReportLanguage(unittest.TestCase):
    """normalize_report_language handles zh_TW and all its aliases."""

    def test_zh_tw_passthrough(self):
        self.assertEqual(normalize_report_language("zh_TW"), "zh_TW")

    def test_zh_tw_hyphen_alias(self):
        self.assertEqual(normalize_report_language("zh-TW"), "zh_TW")

    def test_zh_hant_alias(self):
        self.assertEqual(normalize_report_language("zh_Hant"), "zh_TW")

    def test_zh_hant_hyphen_alias(self):
        self.assertEqual(normalize_report_language("zh-Hant"), "zh_TW")

    def test_traditional_alias(self):
        self.assertEqual(normalize_report_language("traditional"), "zh_TW")

    def test_tw_alias(self):
        self.assertEqual(normalize_report_language("tw"), "zh_TW")

    def test_zh_distinct_from_zh_tw(self):
        self.assertEqual(normalize_report_language("zh"), "zh")
        self.assertNotEqual(normalize_report_language("zh"), "zh_TW")

    def test_en_passthrough(self):
        self.assertEqual(normalize_report_language("en"), "en")

    def test_default_is_zh_tw(self):
        # When value is None, default kicks in. Default is zh_TW per config.
        result = normalize_report_language(None, default="zh_TW")
        self.assertEqual(result, "zh_TW")

    def test_invalid_value_falls_back_to_zh_tw_default(self):
        result = normalize_report_language("invalid_lang", default="zh_TW")
        self.assertEqual(result, "zh_TW")


class TestSupportedLanguages(unittest.TestCase):
    """SUPPORTED_REPORT_LANGUAGES contains zh_TW."""

    def test_zh_tw_in_supported(self):
        self.assertIn("zh_TW", SUPPORTED_REPORT_LANGUAGES)

    def test_zh_in_supported(self):
        self.assertIn("zh", SUPPORTED_REPORT_LANGUAGES)

    def test_en_in_supported(self):
        self.assertIn("en", SUPPORTED_REPORT_LANGUAGES)

    def test_is_supported_value_zh_tw(self):
        self.assertTrue(is_supported_report_language_value("zh_TW"))

    def test_is_supported_alias_zh_tw_hyphen(self):
        self.assertTrue(is_supported_report_language_value("zh-TW"))

    def test_is_supported_alias_traditional(self):
        self.assertTrue(is_supported_report_language_value("traditional"))

    def test_is_supported_alias_tw(self):
        self.assertTrue(is_supported_report_language_value("tw"))


class TestReportLabelsZhTW(unittest.TestCase):
    """zh_TW report labels use Traditional Chinese terminology."""

    def setUp(self):
        self.zh_tw_labels = get_report_labels("zh_TW")
        self.zh_labels = get_report_labels("zh")
        self.en_labels = get_report_labels("en")

    def test_buy_label_traditional(self):
        self.assertEqual(self.zh_tw_labels["buy_label"], "買進")
        self.assertEqual(self.zh_labels["buy_label"], "買進")

    def test_sell_label_traditional(self):
        self.assertEqual(self.zh_tw_labels["sell_label"], "賣出")
        self.assertEqual(self.zh_labels["sell_label"], "賣出")

    def test_dashboard_title_traditional(self):
        self.assertEqual(self.zh_tw_labels["dashboard_title"], "決策儀錶板")
        self.assertIn("决策仪表盘", self.zh_labels["dashboard_title"])

    def test_change_pct_traditional(self):
        self.assertEqual(self.zh_tw_labels["change_pct_label"], "漲跌幅")
        self.assertEqual(self.zh_labels["change_pct_label"], "漲跌幅")

    def test_stop_loss_taiwan_term(self):
        self.assertEqual(self.zh_tw_labels["stop_loss_label"], "停損位")
        self.assertEqual(self.zh_labels["stop_loss_label"], "止損位")

    def test_no_obvious_simplified_in_zh_tw_labels(self):
        simplified_only = ["買進", "賣出", "仪表盘", "复盘", "设置", "数据"]
        for term in simplified_only:
            for _key, value in self.zh_tw_labels.items():
                self.assertNotIn(term, value, f"Found simplified term '{term}' in zh_TW label '{_key}'")

    def test_not_investment_advice_traditional(self):
        label = self.zh_tw_labels["not_investment_advice"]
        self.assertIn("僅供參考", label)
        self.assertNotIn("仅供参考", label)

    def test_all_zh_tw_labels_present(self):
        for key in self.zh_labels:
            self.assertIn(key, self.zh_tw_labels, f"zh_TW missing label key: {key}")

    def test_en_labels_unaffected(self):
        self.assertEqual(self.en_labels["buy_label"], "Buy")
        self.assertEqual(self.en_labels["sell_label"], "Sell")


class TestZhTwLocalization(unittest.TestCase):
    """localize_route_b_zh_tw_text converts simplified terms to traditional."""

    def test_buy_converted(self):
        result = localize_route_b_zh_tw_text("建议买入操作")
        self.assertIn("買進", result)
        self.assertIn("建議", result)
        self.assertNotIn("買進", result)

    def test_market_term_converted(self):
        result = localize_route_b_zh_tw_text("当前市场趋势")
        self.assertIn("市場", result)
        self.assertIn("趨勢", result)

    def test_report_converted(self):
        result = localize_route_b_zh_tw_text("今日报告")
        self.assertIn("報告", result)

    def test_new_terms_涨跌幅(self):
        result = localize_route_b_zh_tw_text("涨跌幅 -2.3%")
        self.assertIn("漲跌幅", result)
        self.assertNotIn("漲跌幅", result)

    def test_new_terms_成交额(self):
        result = localize_route_b_zh_tw_text("今日成交额 1000亿元")
        self.assertIn("成交金額", result)
        self.assertIn("億元", result)

    def test_new_terms_减仓(self):
        result = localize_route_b_zh_tw_text("建议减仓操作")
        self.assertIn("減碼", result)

    def test_new_terms_加仓(self):
        result = localize_route_b_zh_tw_text("适当加仓")
        self.assertIn("加碼", result)

    def test_stop_loss_converted(self):
        result = localize_route_b_zh_tw_text("止损位设在100元")
        self.assertIn("停損位", result)

    def test_code_blocks_protected(self):
        text = "```\n买入信号\n```"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn("买入信号", result)

    def test_urls_protected(self):
        text = "详情见 https://example.com/market-data 买入确认"
        result = localize_route_b_zh_tw_text(text)
        self.assertIn("https://example.com/market-data", result)

    def test_localize_if_route_b_active(self):
        mock_config = SimpleNamespace(route_b_enforce_market_scope=True)
        with patch("src.core.zh_tw_localization.is_route_b_zh_tw_active", return_value=True):
            result = localize_if_route_b("买入建议")
        self.assertIn("買進", result)

    def test_localize_if_route_b_inactive(self):
        with patch("src.core.zh_tw_localization.is_route_b_zh_tw_active", return_value=False):
            result = localize_if_route_b("买入建议")
        self.assertEqual(result, "买入建议")


class TestZhEnPathsUnchanged(unittest.TestCase):
    """Existing zh and en paths remain working after zh_TW addition."""

    def test_zh_buy_label_unchanged(self):
        labels = get_report_labels("zh")
        self.assertEqual(labels["buy_label"], "買進")

    def test_zh_normalize_unchanged(self):
        self.assertEqual(normalize_report_language("zh"), "zh")

    def test_en_normalize_unchanged(self):
        self.assertEqual(normalize_report_language("en"), "en")

    def test_zh_cn_alias_still_maps_to_zh(self):
        self.assertEqual(normalize_report_language("zh-CN"), "zh")
        self.assertEqual(normalize_report_language("zh_CN"), "zh")

    def test_en_labels_buy_label(self):
        labels = get_report_labels("en")
        self.assertEqual(labels["buy_label"], "Buy")


class TestZhTWFallbackHardening(unittest.TestCase):
    """Phase 9G: verify fallback decision labels are language-aware and never emit
    obvious Simplified Chinese when report_language is zh_TW."""

    def setUp(self):
        # Use module-level references captured before test_llm_precheck_fallback patches them.
        self.localize_op = _real_localize_op
        self.localize_trend = _real_localize_trend

    def test_watch_localizes_to_traditional_for_zh_tw(self):
        """'watch' canonical → '觀望' in zh_TW, not '观望'."""
        result = self.localize_op("watch", "zh_TW")
        self.assertEqual(result, "觀望")
        self.assertNotIn("观望", result)

    def test_watch_localizes_to_simplified_for_zh(self):
        """zh path still returns '观望'."""
        result = self.localize_op("watch", "zh")
        self.assertEqual(result, "观望")

    def test_watch_localizes_to_english_for_en(self):
        result = self.localize_op("watch", "en")
        self.assertEqual(result, "Watch")

    def test_sideways_localizes_to_traditional_for_zh_tw(self):
        """'sideways' canonical → '震盪' in zh_TW, not '震荡'."""
        result = self.localize_trend("sideways", "zh_TW")
        self.assertEqual(result, "震盪")
        self.assertNotIn("震荡", result)

    def test_buy_localizes_to_traditional_for_zh_tw(self):
        result = self.localize_op("buy", "zh_TW")
        self.assertEqual(result, "買進")
        self.assertNotIn("買進", result)

    def test_sell_localizes_to_traditional_for_zh_tw(self):
        result = self.localize_op("sell", "zh_TW")
        self.assertEqual(result, "賣出")
        self.assertNotIn("賣出", result)

    def test_strong_buy_localizes_to_traditional_for_zh_tw(self):
        result = self.localize_op("strong_buy", "zh_TW")
        self.assertEqual(result, "強烈買進")

    def test_strong_sell_localizes_to_traditional_for_zh_tw(self):
        result = self.localize_op("strong_sell", "zh_TW")
        self.assertEqual(result, "強烈賣出")

    def test_reduce_localizes_to_traditional_for_zh_tw(self):
        result = self.localize_op("reduce", "zh_TW")
        self.assertEqual(result, "減倉")

    def test_input_simplified_watch_is_recognized_and_converted(self):
        """Input '观望' recognized as 'watch' canonical and converted to '觀望' for zh_TW."""
        result = self.localize_op("观望", "zh_TW")
        self.assertEqual(result, "觀望")

    def test_input_simplified_buy_is_recognized_and_converted(self):
        result = self.localize_op("買進", "zh_TW")
        self.assertEqual(result, "買進")

    def test_input_simplified_sideways_is_recognized_and_converted(self):
        result = self.localize_trend("震荡", "zh_TW")
        self.assertEqual(result, "震盪")

    def test_pipeline_fallback_labels_not_simplified_for_zh_tw(self):
        """All label helpers used in pipeline fallback emit Traditional for zh_TW."""
        watch = self.localize_op("watch", "zh_TW")
        sideways = self.localize_trend("sideways", "zh_TW")
        self.assertNotIn("观望", watch)
        self.assertNotIn("震荡", sideways)
        self.assertIn("觀望", watch)
        self.assertIn("震盪", sideways)

    def test_zh_tw_market_review_labels_not_simplified(self):
        """Market review zh_TW title labels use Traditional Chinese."""
        from src.core.market_review import _get_market_review_text
        text = _get_market_review_text("zh_TW")
        for key in ("root_title", "tw_title", "us_title", "separator"):
            val = text[key]
            self.assertNotIn("报告", val, f"{key} contains Simplified '报告'")
            self.assertNotIn("诊断", val, f"{key} contains Simplified '诊断'")
            self.assertNotIn("市场", val, f"{key} contains Simplified '市场'")

    def test_zh_tw_market_review_titles_contain_traditional(self):
        from src.core.market_review import _get_market_review_text
        text = _get_market_review_text("zh_TW")
        self.assertIn("大盤", text["root_title"])
        self.assertIn("台股", text["tw_title"])
        self.assertIn("美股", text["us_title"])

    def test_zh_tw_report_labels_no_simplified_watch_buy(self):
        """Report label dict for zh_TW has no '观望' or '买入'."""
        labels = get_report_labels("zh_TW")
        self.assertNotIn("观望", labels.get("watch_label", ""))
        self.assertNotIn("買進", labels.get("buy_label", ""))
        self.assertNotIn("賣出", labels.get("sell_label", ""))

    def test_zh_tw_report_labels_traditional_values(self):
        """Report label dict for zh_TW uses Traditional."""
        labels = get_report_labels("zh_TW")
        self.assertEqual(labels.get("watch_label"), "觀望")
        self.assertEqual(labels.get("buy_label"), "買進")
        self.assertEqual(labels.get("sell_label"), "賣出")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Tests for TW market profile hardening — Phase 7E.1.

Covers:
- TW_PROFILE existence and correctness
- get_profile("tw") returns TW_PROFILE, not CN_PROFILE
- get_profile raises ValueError for unknown regions
- get_market_strategy_blueprint raises ValueError for unknown regions
- MarketAnalyzer(region="tw") accepts "tw", uses TW profile
- MarketAnalyzer(region="tw") region methods return TW-specific values
- TW news queries contain Taiwan terms, not A-share terms
- Scope gate still defers TW (unchanged from Phase 7A)
- US and CN profile/strategy behavior unchanged
"""

import unittest
from unittest.mock import patch, MagicMock

from src.core.market_profile import (
    CN_PROFILE,
    US_PROFILE,
    HK_PROFILE,
    TW_PROFILE,
    get_profile,
)
from src.core.market_strategy import (
    CN_BLUEPRINT,
    US_BLUEPRINT,
    TW_BLUEPRINT,
    get_market_strategy_blueprint,
)
from src.core.market_review_scope_gate import filter_regions_for_route_b


_FORBIDDEN_CN_TERMS = [
    "A股", "上證", "上證", "深證", "深證",
    "創業板", "創業板", "科創50", "科創50", "滬深", "滬深",
]

_REQUIRED_TW_TERMS = [
    "台股", "加權", "TAIEX",
]


class TestTWProfile(unittest.TestCase):
    """TW_PROFILE constant correctness."""

    def test_tw_profile_exists(self):
        self.assertIsNotNone(TW_PROFILE)

    def test_tw_profile_region(self):
        self.assertEqual(TW_PROFILE.region, "tw")

    def test_tw_profile_mood_index_code(self):
        self.assertEqual(TW_PROFILE.mood_index_code, "TAIEX")

    def test_tw_profile_has_news_queries(self):
        self.assertGreater(len(TW_PROFILE.news_queries), 0)

    def test_tw_news_queries_contain_required_terms(self):
        all_queries = " ".join(TW_PROFILE.news_queries)
        for term in _REQUIRED_TW_TERMS:
            self.assertIn(term, all_queries, f"Required term {term!r} missing from TW news queries")

    def test_tw_news_queries_no_forbidden_cn_terms(self):
        all_queries = " ".join(TW_PROFILE.news_queries)
        for term in _FORBIDDEN_CN_TERMS:
            self.assertNotIn(term, all_queries, f"Forbidden CN term {term!r} found in TW news queries")

    def test_tw_profile_has_market_stats_false(self):
        self.assertFalse(TW_PROFILE.has_market_stats)

    def test_tw_profile_has_sector_rankings_false(self):
        self.assertFalse(TW_PROFILE.has_sector_rankings)

    def test_tw_prompt_index_hint_contains_taiex(self):
        self.assertIn("TAIEX", TW_PROFILE.prompt_index_hint)

    def test_tw_prompt_index_hint_no_cn_terms(self):
        for term in _FORBIDDEN_CN_TERMS:
            self.assertNotIn(term, TW_PROFILE.prompt_index_hint,
                             f"Forbidden CN term {term!r} in TW prompt_index_hint")

    def test_tw_profile_not_equal_cn_profile(self):
        self.assertIsNot(TW_PROFILE, CN_PROFILE)
        self.assertNotEqual(TW_PROFILE.region, CN_PROFILE.region)
        self.assertNotEqual(TW_PROFILE.mood_index_code, CN_PROFILE.mood_index_code)


class TestGetProfile(unittest.TestCase):
    """get_profile() routing and ValueError guard."""

    def test_get_profile_tw_returns_tw_profile(self):
        self.assertIs(get_profile("tw"), TW_PROFILE)

    def test_get_profile_tw_not_cn_profile(self):
        self.assertIsNot(get_profile("tw"), CN_PROFILE)

    def test_get_profile_us_returns_us_profile(self):
        self.assertIs(get_profile("us"), US_PROFILE)

    def test_get_profile_cn_returns_cn_profile(self):
        self.assertIs(get_profile("cn"), CN_PROFILE)

    def test_get_profile_hk_returns_hk_profile(self):
        self.assertIs(get_profile("hk"), HK_PROFILE)

    def test_get_profile_unknown_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_profile("jp")
        self.assertIn("jp", str(ctx.exception))

    def test_get_profile_empty_string_raises(self):
        with self.assertRaises(ValueError):
            get_profile("")

    def test_get_profile_unknown_does_not_return_cn(self):
        with self.assertRaises(ValueError):
            result = get_profile("xx")
            self.assertIsNot(result, CN_PROFILE)


class TestTWBlueprint(unittest.TestCase):
    """TW_BLUEPRINT correctness."""

    def test_tw_blueprint_exists(self):
        self.assertIsNotNone(TW_BLUEPRINT)

    def test_tw_blueprint_region(self):
        self.assertEqual(TW_BLUEPRINT.region, "tw")

    def test_get_market_strategy_tw(self):
        self.assertIs(get_market_strategy_blueprint("tw"), TW_BLUEPRINT)

    def test_get_market_strategy_unknown_raises(self):
        with self.assertRaises(ValueError) as ctx:
            get_market_strategy_blueprint("jp")
        self.assertIn("jp", str(ctx.exception))

    def test_tw_blueprint_no_cn_terms(self):
        block = TW_BLUEPRINT.to_prompt_block()
        for term in ["A股", "上証", "深証", "創業板", "創業板"]:
            self.assertNotIn(term, block, f"Forbidden term {term!r} in TW blueprint")

    def test_tw_blueprint_contains_tw_terms(self):
        block = TW_BLUEPRINT.to_prompt_block()
        for term in ["加權指數", "外資", "台股"]:
            self.assertIn(term, block, f"Required term {term!r} missing from TW blueprint")

    def test_us_blueprint_unchanged(self):
        self.assertIs(get_market_strategy_blueprint("us"), US_BLUEPRINT)

    def test_cn_blueprint_unchanged(self):
        self.assertIs(get_market_strategy_blueprint("cn"), CN_BLUEPRINT)


class TestMarketAnalyzerTWRegion(unittest.TestCase):
    """MarketAnalyzer(region="tw") hardening."""

    def _make_analyzer(self, region: str):
        from src.market_analyzer import MarketAnalyzer
        with patch("src.market_analyzer.get_config") as mock_cfg, \
             patch("src.market_analyzer.DataFetcherManager"):
            mock_cfg.return_value = MagicMock(
                report_language="zh",
                market_review_color_scheme="green_up",
            )
            return MarketAnalyzer(region=region)

    def test_tw_region_accepted(self):
        ma = self._make_analyzer("tw")
        self.assertEqual(ma.region, "tw")

    def test_tw_uses_tw_profile(self):
        ma = self._make_analyzer("tw")
        self.assertIs(ma.profile, TW_PROFILE)

    def test_tw_not_cn_profile(self):
        ma = self._make_analyzer("tw")
        self.assertIsNot(ma.profile, CN_PROFILE)

    def test_tw_uses_tw_blueprint(self):
        ma = self._make_analyzer("tw")
        self.assertIs(ma.strategy, TW_BLUEPRINT)

    def test_unknown_region_raises(self):
        from src.market_analyzer import MarketAnalyzer
        with patch("src.market_analyzer.get_config"), \
             patch("src.market_analyzer.DataFetcherManager"), \
             self.assertRaises(ValueError):
            MarketAnalyzer(region="jp")

    def test_tw_market_scope_name_zh(self):
        ma = self._make_analyzer("tw")
        self.assertIn("台股", ma._get_market_scope_name("zh"))

    def test_tw_market_scope_name_en(self):
        ma = self._make_analyzer("tw")
        self.assertIn("Taiwan", ma._get_market_scope_name("en"))

    def test_tw_review_title_zh(self):
        ma = self._make_analyzer("tw")
        title = ma._get_review_title("2026-06-14")
        self.assertIn("台股大盤回顧", title)
        self.assertNotIn("大盤覆盤", title)
        self.assertNotIn("A-share", title)

    def test_tw_review_title_en(self):
        from src.market_analyzer import MarketAnalyzer
        with patch("src.market_analyzer.get_config") as mock_cfg, \
             patch("src.market_analyzer.DataFetcherManager"):
            mock_cfg.return_value = MagicMock(
                report_language="en",
                market_review_color_scheme="green_up",
            )
            ma = MarketAnalyzer(region="tw")
        title = ma._get_review_title("2026-06-14")
        self.assertIn("Taiwan", title)
        self.assertNotIn("A-share", title)

    def test_tw_turnover_unit_zh(self):
        ma = self._make_analyzer("tw")
        self.assertIn("億元臺幣", ma._get_turnover_unit_label())

    def test_tw_index_hint_zh(self):
        ma = self._make_analyzer("tw")
        hint = ma._get_index_hint()
        self.assertIn("TAIEX", hint)
        self.assertNotIn("上證", hint)
        self.assertNotIn("S&P 500", hint)

    def test_us_region_unchanged(self):
        ma = self._make_analyzer("us")
        self.assertEqual(ma.region, "us")
        self.assertIs(ma.profile, US_PROFILE)

    def test_cn_region_unchanged(self):
        ma = self._make_analyzer("cn")
        self.assertEqual(ma.region, "cn")
        self.assertIs(ma.profile, CN_PROFILE)


class TestScopeGateStillDefersTV(unittest.TestCase):
    """TW market review scope gate: TW is now implemented (Phase 7E-FINAL unlocked)."""

    def test_tw_implemented_in_scope_gate(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run, "TW should be in run_regions after Phase 7E-FINAL unlock")
        self.assertEqual(deferred_tw, [])

    def test_us_still_runs_in_scope_gate(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["us"])
        self.assertIn("us", run)
        self.assertNotIn("us", deferred_tw)

    def test_cn_still_blocked_in_scope_gate(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["cn"])
        self.assertIn("cn", skipped_cn)
        self.assertNotIn("cn", run)


if __name__ == "__main__":
    unittest.main()

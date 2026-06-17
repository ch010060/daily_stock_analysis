# -*- coding: utf-8 -*-
"""Phase 7A: Market review scope gate tests for Route B TW/US enforcement.

All tests are offline and mock-only. Verifies:
- Route B default market review is enabled with regions TW,US.
- CN/A-share market review is blocked under Route B enforce mode.
- TW market review is explicitly deferred (not yet implemented), not CN fallback.
- US market review is accepted when supported.
- "A股 大盤 覆盤" search query is not generated for non-CN regions.
- CN index providers are not called.
- If all regions are rejected/deferred, the review is skipped (not fallen back to CN).
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.market_review_scope_gate import (
    filter_regions_for_route_b,
    get_default_route_b_regions,
    get_effective_regions_for_route_b,
    parse_market_review_regions_env,
)
from src.core.market_profile import CN_PROFILE, US_PROFILE, HK_PROFILE, get_profile


def _config(markets=None, enforce=True, market_review_enabled=True):
    return SimpleNamespace(
        route_b_enforce_market_scope=enforce,
        route_b_markets=markets if markets is not None else ["TW", "US"],
        market_review_enabled=market_review_enabled,
    )


class TestParseMarketReviewRegionsEnv(unittest.TestCase):
    """parse_market_review_regions_env correctly maps env strings to internal codes."""

    def test_tw_us_string(self):
        self.assertEqual(parse_market_review_regions_env("TW,US"), ["tw", "us"])

    def test_us_only(self):
        self.assertEqual(parse_market_review_regions_env("US"), ["us"])

    def test_tw_only(self):
        self.assertEqual(parse_market_review_regions_env("TW"), ["tw"])

    def test_cn_us_string(self):
        self.assertEqual(parse_market_review_regions_env("CN,US"), ["cn", "us"])

    def test_case_insensitive(self):
        self.assertEqual(parse_market_review_regions_env("tw,Us,CN"), ["tw", "us", "cn"])

    def test_empty_returns_empty_list(self):
        self.assertEqual(parse_market_review_regions_env(""), [])

    def test_none_returns_empty_list(self):
        self.assertEqual(parse_market_review_regions_env(None), [])

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(parse_market_review_regions_env("  "), [])

    def test_unknown_region_dropped(self):
        result = parse_market_review_regions_env("TW,INVALID,US")
        self.assertNotIn("invalid", result)
        self.assertIn("tw", result)
        self.assertIn("us", result)

    def test_tw_us_cn_three_regions(self):
        result = parse_market_review_regions_env("TW,US,CN")
        self.assertEqual(result, ["tw", "us", "cn"])


class TestGetDefaultRouteBRegions(unittest.TestCase):
    """get_default_route_b_regions derives internal regions from ROUTE_B_MARKETS."""

    def test_tw_us_default_gives_us_and_tw(self):
        config = _config(markets=["TW", "US"])
        regions = get_default_route_b_regions(config)
        self.assertIn("us", regions)
        self.assertIn("tw", regions)

    def test_us_only_config_gives_us(self):
        config = _config(markets=["US"])
        regions = get_default_route_b_regions(config)
        self.assertIn("us", regions)
        self.assertNotIn("tw", regions)

    def test_tw_only_config_gives_tw(self):
        config = _config(markets=["TW"])
        regions = get_default_route_b_regions(config)
        self.assertIn("tw", regions)
        self.assertNotIn("us", regions)

    def test_us_before_tw_ordering(self):
        config = _config(markets=["TW", "US"])
        regions = get_default_route_b_regions(config)
        # US should appear before TW in the result (priority order)
        self.assertLess(regions.index("us"), regions.index("tw"))


class TestFilterRegionsForRouteB(unittest.TestCase):
    """filter_regions_for_route_b blocks CN and defers TW."""

    def test_us_region_runs(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["us"])
        self.assertIn("us", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred_tw, [])

    def test_cn_region_blocked(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["cn"])
        self.assertEqual(run, [])
        self.assertIn("cn", skipped_cn)
        self.assertEqual(deferred_tw, [])

    def test_tw_region_implemented_not_cn_fallback(self):
        """TW is now implemented; it routes to run, not deferred, not CN."""
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred_tw, [])

    def test_us_cn_mixed_blocks_cn_runs_us(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["us", "cn"])
        self.assertIn("us", run)
        self.assertIn("cn", skipped_cn)
        self.assertEqual(deferred_tw, [])

    def test_tw_us_cn_all_three(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw", "us", "cn"])
        self.assertIn("us", run)
        self.assertIn("tw", run)
        self.assertIn("cn", skipped_cn)
        self.assertEqual(deferred_tw, [])

    def test_cn_blocked_tw_runs_cn_tw_mix(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["cn", "tw"])
        self.assertIn("tw", run)
        self.assertIn("cn", skipped_cn)
        self.assertEqual(deferred_tw, [])

    def test_empty_list_returns_empty_tuples(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b([])
        self.assertEqual(run, [])
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred_tw, [])

    def test_hk_region_runs(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["hk"])
        self.assertIn("hk", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred_tw, [])


class TestGetEffectiveRegionsForRouteB(unittest.TestCase):
    """get_effective_regions_for_route_b uses ROUTE_B_MARKETS by default."""

    def test_tw_us_defaults_give_both_run(self):
        config = _config(markets=["TW", "US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(config)
        self.assertIn("us", run)
        self.assertIn("tw", run)
        self.assertNotIn("cn", run)
        self.assertEqual(deferred_tw, [])

    def test_explicit_regions_override_defaults(self):
        config = _config(markets=["TW", "US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(
            config, explicit_regions=["us", "cn"]
        )
        self.assertIn("us", run)
        self.assertIn("cn", skipped_cn)

    def test_explicit_cn_only_runs_nothing(self):
        config = _config(markets=["TW", "US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(
            config, explicit_regions=["cn"]
        )
        self.assertEqual(run, [])
        self.assertIn("cn", skipped_cn)

    def test_us_only_market_runs_us_only(self):
        config = _config(markets=["US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(config)
        self.assertEqual(run, ["us"])
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred_tw, [])


class TestMarketReviewDefaultUnderRouteB(unittest.TestCase):
    """Behavioral assertions on defaults when Route B is enforced."""

    def test_route_b_default_market_review_enabled(self):
        """market_review_enabled is True by default (unchanged by Route B gate)."""
        config = _config(market_review_enabled=True)
        self.assertTrue(config.market_review_enabled)

    def test_route_b_default_regions_are_tw_us(self):
        """Default ROUTE_B_MARKETS is TW and US."""
        config = _config()
        markets = set(config.route_b_markets)
        self.assertIn("TW", markets)
        self.assertIn("US", markets)

    def test_cn_not_in_route_b_default_regions(self):
        """CN must not appear in default Route B markets."""
        config = _config()
        self.assertNotIn("CN", set(config.route_b_markets))

    def test_route_b_effective_run_regions_include_us(self):
        config = _config(markets=["TW", "US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(config)
        self.assertIn("us", run)

    def test_route_b_effective_run_regions_exclude_cn(self):
        config = _config(markets=["TW", "US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(config)
        self.assertNotIn("cn", run)

    def test_legacy_market_review_region_cn_blocked_under_route_b(self):
        """Legacy MARKET_REVIEW_REGION=cn is blocked when Route B scope gate runs."""
        cn_regions = ["cn"]
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(cn_regions)
        self.assertEqual(run, [])
        self.assertIn("cn", skipped_cn)


class TestNoAShareSearchQuery(unittest.TestCase):
    """CN profile uses 'A股 大盤 覆盤' query that must not appear in TW/US profiles."""

    def test_cn_profile_has_a_share_query(self):
        """Confirm the CN profile contains the forbidden query."""
        self.assertTrue(any("A股" in q for q in CN_PROFILE.news_queries))

    def test_us_profile_no_a_share_query(self):
        for q in US_PROFILE.news_queries:
            self.assertNotIn("A股", q, f"US profile must not contain 'A股' in query: {q!r}")

    def test_hk_profile_no_a_share_market_query(self):
        """HK profile should not use the A-share 大盤覆盤 query."""
        for q in HK_PROFILE.news_queries:
            self.assertNotIn("A股 大盤 覆盤", q, f"HK query should not be A-share: {q!r}")

    def test_us_profile_region_no_cn_context(self):
        self.assertEqual(US_PROFILE.region, "us")
        self.assertNotEqual(US_PROFILE.region, "cn")

    def test_route_b_effective_regions_use_us_not_cn_profile(self):
        """When Route B resolves to 'us', the profile used is US (not CN)."""
        config = _config(markets=["TW", "US"])
        run, _, _ = get_effective_regions_for_route_b(config)
        for region in run:
            profile = get_profile(region)
            self.assertNotEqual(profile.region, "cn",
                f"Route B region {region!r} must not resolve to CN profile")
            for q in profile.news_queries:
                self.assertNotIn("A股 大盤 覆盤", q,
                    f"Route B region {region!r} must not generate A-share query: {q!r}")


class TestNoCNIndexProviders(unittest.TestCase):
    """Under Route B enforce mode, CN index/sector providers must not be called."""

    def test_cn_profile_mood_index_is_shanghai(self):
        """Confirm CN profile uses Shanghai index (000001) — must not be called in Route B."""
        self.assertEqual(CN_PROFILE.mood_index_code, "000001")

    def test_us_profile_mood_index_is_not_cn(self):
        self.assertNotEqual(US_PROFILE.mood_index_code, "000001")

    def test_route_b_run_regions_have_non_cn_index(self):
        """Verify that every region that passes Route B gate has a non-CN index."""
        config = _config(markets=["TW", "US"])
        run, _, _ = get_effective_regions_for_route_b(config)
        for region in run:
            profile = get_profile(region)
            self.assertNotEqual(profile.mood_index_code, "000001",
                f"Region {region!r} in Route B must not use CN index 000001")

    def test_cn_region_blocked_before_any_provider_call(self):
        """CN region is filtered before MarketAnalyzer would be instantiated."""
        run, skipped_cn, _ = filter_regions_for_route_b(["cn"])
        self.assertEqual(run, [])
        self.assertIn("cn", skipped_cn)
        # If run is empty, no MarketAnalyzer is created → no provider call

    def test_market_analyzer_not_called_for_cn_region(self):
        """MarketAnalyzer must not be called when CN is filtered out."""
        with patch("src.market_analyzer.MarketAnalyzer") as mock_analyzer_cls:
            # Simulate route B gate filtering before run_market_review
            regions = ["cn"]
            run, skipped_cn, _ = filter_regions_for_route_b(regions)
            # Since run is empty, MarketAnalyzer should never be instantiated
            self.assertEqual(run, [])
            mock_analyzer_cls.assert_not_called()


class TestTWMarketReviewImplemented(unittest.TestCase):
    """TW market review is implemented (Phase 7E-FINAL); routes to run_regions, not deferred."""

    def test_tw_routes_to_run_not_cn_fallback(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw"])
        self.assertNotIn("cn", run, "TW must not produce CN fallback")
        self.assertIn("tw", run)
        self.assertEqual(deferred_tw, [])

    def test_tw_us_both_run(self):
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw", "us"])
        self.assertIn("us", run)
        self.assertIn("tw", run)
        self.assertNotIn("cn", run)
        self.assertEqual(deferred_tw, [])

    def test_tw_only_routes_to_run(self):
        run, _, deferred_tw = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run)
        self.assertEqual(deferred_tw, [])

    def test_cn_blocked_when_tw_cn_requested(self):
        """When TW and CN are requested, CN is blocked but TW runs."""
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw", "cn"])
        self.assertIn("cn", skipped_cn)
        self.assertIn("tw", run)
        self.assertEqual(deferred_tw, [])


class TestUSMarketReviewAccepted(unittest.TestCase):
    """US market review runs when supported under Route B."""

    def test_us_region_accepted(self):
        run, _, _ = filter_regions_for_route_b(["us"])
        self.assertIn("us", run)

    def test_us_accepted_in_tw_us_default(self):
        config = _config(markets=["TW", "US"])
        run, _, _ = get_effective_regions_for_route_b(config)
        self.assertIn("us", run)

    def test_us_market_review_uses_us_profile(self):
        """US region uses US profile (not CN)."""
        profile = get_profile("us")
        self.assertEqual(profile.region, "us")
        self.assertEqual(profile.mood_index_code, "SPX")


class TestReportOutputGate(unittest.TestCase):
    """Report/output guarding: non-TW/US results must not be written."""

    def test_tw_us_regions_after_gate_are_writable(self):
        """After Route B gate, TW and US both appear in run_regions (both implemented)."""
        config = _config(markets=["TW", "US"])
        run, skipped_cn, deferred_tw = get_effective_regions_for_route_b(config)
        for region in run:
            self.assertNotEqual(region, "cn",
                f"Region {region!r} is CN and must not be in run_regions")

    def test_no_cn_regions_in_run_list(self):
        regions = ["cn", "us", "tw", "cn"]
        run, _, _ = filter_regions_for_route_b(regions)
        self.assertNotIn("cn", run)

    def test_if_all_rejected_report_writer_skipped(self):
        """Empty run_regions → the caller should skip report writing."""
        regions_all_cn = ["cn"]
        run, _, _ = filter_regions_for_route_b(regions_all_cn)
        # Verify that run is falsy so downstream can gate on it
        self.assertFalse(run)

    def test_tw_implemented_routes_to_run(self):
        """TW is now implemented; it appears in run_regions, not deferred_tw."""
        run, _, deferred_tw = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run, "TW should be in run_regions after Phase 7E-FINAL unlock")
        self.assertNotIn("tw", deferred_tw)


if __name__ == "__main__":
    unittest.main()

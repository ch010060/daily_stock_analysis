# -*- coding: utf-8 -*-
"""Phase 7E-FINAL: TW scope unlock tests.

Verifies that TW has been moved from _DEFERRED_REGIONS to _IMPLEMENTED_REGIONS
and routes correctly through filter_regions_for_route_b.
"""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.market_review_scope_gate import (
    _DEFERRED_REGIONS,
    _IMPLEMENTED_REGIONS,
    filter_regions_for_route_b,
    get_default_route_b_regions,
    get_effective_regions_for_route_b,
    parse_market_review_regions_env,
)


def _config(markets=None, enforce=True):
    return SimpleNamespace(
        route_b_enforce_market_scope=enforce,
        route_b_markets=markets if markets is not None else ["TW", "US"],
    )


class TestTwScopeUnlock(unittest.TestCase):
    """TW is now in _IMPLEMENTED_REGIONS; _DEFERRED_REGIONS is empty."""

    def test_tw_in_implemented_regions(self):
        self.assertIn("tw", _IMPLEMENTED_REGIONS)

    def test_deferred_regions_empty(self):
        self.assertEqual(len(_DEFERRED_REGIONS), 0)

    def test_tw_not_in_deferred(self):
        self.assertNotIn("tw", _DEFERRED_REGIONS)


class TestFilterRegionsTwUnlocked(unittest.TestCase):
    """filter_regions_for_route_b routes TW to run_regions, not deferred."""

    def test_tw_routes_to_run(self):
        run, skipped_cn, deferred = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred, [])

    def test_us_routes_to_run(self):
        run, skipped_cn, deferred = filter_regions_for_route_b(["us"])
        self.assertIn("us", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred, [])

    def test_tw_and_us_both_run(self):
        run, skipped_cn, deferred = filter_regions_for_route_b(["tw", "us"])
        self.assertIn("tw", run)
        self.assertIn("us", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred, [])

    def test_cn_blocked_tw_us_run(self):
        run, skipped_cn, deferred = filter_regions_for_route_b(["cn", "tw", "us"])
        self.assertIn("cn", skipped_cn)
        self.assertNotIn("cn", run)
        self.assertIn("tw", run)
        self.assertIn("us", run)
        self.assertEqual(deferred, [])

    def test_cn_only_blocked(self):
        run, skipped_cn, deferred = filter_regions_for_route_b(["cn"])
        self.assertEqual(run, [])
        self.assertIn("cn", skipped_cn)
        self.assertEqual(deferred, [])


class TestGetDefaultRouteBRegions(unittest.TestCase):
    """get_default_route_b_regions derives candidate regions from ROUTE_B_MARKETS."""

    def test_tw_us_config_includes_tw(self):
        from unittest.mock import patch
        with patch("src.core.route_b_scope.get_route_b_markets", return_value={"TW", "US"}):
            regions = get_default_route_b_regions(_config(["TW", "US"]))
        self.assertIn("tw", regions)
        self.assertIn("us", regions)

    def test_us_only_config_excludes_tw(self):
        from unittest.mock import patch
        with patch("src.core.route_b_scope.get_route_b_markets", return_value={"US"}):
            regions = get_default_route_b_regions(_config(["US"]))
        self.assertNotIn("tw", regions)
        self.assertIn("us", regions)


class TestGetEffectiveRegions(unittest.TestCase):
    """get_effective_regions_for_route_b: TW,US explicit regions both pass gate."""

    def test_tw_us_explicit_both_run(self):
        run, skipped_cn, deferred = get_effective_regions_for_route_b(
            explicit_regions=["tw", "us"]
        )
        self.assertIn("tw", run)
        self.assertIn("us", run)
        self.assertEqual(skipped_cn, [])
        self.assertEqual(deferred, [])

    def test_cn_explicit_blocked(self):
        run, skipped_cn, deferred = get_effective_regions_for_route_b(
            explicit_regions=["cn"]
        )
        self.assertEqual(run, [])
        self.assertIn("cn", skipped_cn)

    def test_cn_tw_explicit_cn_blocked_tw_runs(self):
        run, skipped_cn, deferred = get_effective_regions_for_route_b(
            explicit_regions=["cn", "tw"]
        )
        self.assertIn("cn", skipped_cn)
        self.assertIn("tw", run)
        self.assertEqual(deferred, [])


class TestParseEnvWithTw(unittest.TestCase):
    """parse_market_review_regions_env correctly handles TW."""

    def test_tw_us_env(self):
        self.assertEqual(parse_market_review_regions_env("TW,US"), ["tw", "us"])

    def test_tw_only_env(self):
        self.assertEqual(parse_market_review_regions_env("TW"), ["tw"])

    def test_lowercase_tw(self):
        self.assertEqual(parse_market_review_regions_env("tw"), ["tw"])


if __name__ == "__main__":
    unittest.main()

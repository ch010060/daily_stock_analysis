# -*- coding: utf-8 -*-
"""Regression tests for the active Route B scope gate in run_market_review().

Phase 9E-FIX3: market_review_scope_gate.py was previously dead code.
After the fix, run_market_review() calls get_effective_regions_for_route_b()
when ROUTE_B_ENFORCE_MARKET_SCOPE=true.

Tests verify the active path — not the helper functions in isolation.
All tests are offline / mock-only; no live providers called.
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

import src.core.market_review as market_review_module

run_market_review = market_review_module.run_market_review

_LOCALIZE_PATH = "src.core.zh_tw_localization.localize_if_route_b"


def _make_notifier() -> MagicMock:
    notifier = MagicMock()
    notifier.save_report_to_file.return_value = "/tmp/test_market_review.md"
    notifier.is_available.return_value = False
    notifier.send.return_value = False
    return notifier


def _route_b_config(
    *,
    market_review_region: str = "cn",
    market_review_regions: list | None = None,
    route_b_markets: list | None = None,
    report_language: str = "zh_TW",
) -> SimpleNamespace:
    """Build a config stub that activates Route B scope enforcement."""
    return SimpleNamespace(
        route_b_enforce_market_scope=True,
        route_b_markets=route_b_markets if route_b_markets is not None else ["TW", "US"],
        market_review_region=market_review_region,
        market_review_regions=market_review_regions if market_review_regions is not None else [],
        report_language=report_language,
    )


def _legacy_config(
    *,
    market_review_region: str = "cn",
    market_review_regions: list | None = None,
    report_language: str = "zh",
) -> SimpleNamespace:
    """Build a config stub with Route B enforcement disabled (legacy mode)."""
    return SimpleNamespace(
        route_b_enforce_market_scope=False,
        market_review_region=market_review_region,
        market_review_regions=market_review_regions if market_review_regions is not None else [],
        report_language=report_language,
    )


class TestRunMarketReviewRouteBGating(unittest.TestCase):
    """run_market_review() applies Route B scope gate on the active code path."""

    # ------------------------------------------------------------------
    # Case 1: Route B on, MARKET_REVIEW_REGIONS unset (default → cn)
    # ------------------------------------------------------------------

    def test_route_b_on_regions_unset_returns_none(self):
        """When MARKET_REVIEW_REGIONS is unset and default falls to cn, must return None."""
        config = _route_b_config(market_review_region="cn", market_review_regions=[])
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history") as persist, \
             patch.object(market_review_module, "MarketAnalyzer") as analyzer_cls:
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNone(result, "CN-only regions must abort when Route B is enforced")
        analyzer_cls.assert_not_called()
        persist.assert_not_called()

    def test_route_b_on_regions_unset_no_notification_sent(self):
        """No notification must be sent when all regions are blocked under Route B."""
        config = _route_b_config(market_review_region="cn", market_review_regions=[])
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "MarketAnalyzer"):
            run_market_review(notifier, send_notification=True)

        notifier.send.assert_not_called()

    # ------------------------------------------------------------------
    # Case 2: Route B on, MARKET_REVIEW_REGIONS=TW,US,CN → CN filtered
    # ------------------------------------------------------------------

    def test_route_b_on_tw_us_cn_filters_cn(self):
        """When MARKET_REVIEW_REGIONS includes CN, CN must be removed under Route B."""
        config = _route_b_config(market_review_regions=["tw", "us", "cn"])
        notifier = _make_notifier()

        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body",
            market_light_snapshot={"region": "us"},
        )

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history"), \
             patch(_LOCALIZE_PATH, side_effect=lambda t: t), \
             patch.object(market_review_module, "_run_tw_market_review_section",
                          return_value=("TW body", {"region": "tw"})), \
             patch.object(market_review_module, "MarketAnalyzer",
                          return_value=us_analyzer) as analyzer_cls:
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNotNone(result)
        self.assertIn("US body", result)
        self.assertIn("TW body", result)
        for call_item in analyzer_cls.call_args_list:
            self.assertNotEqual(call_item.kwargs.get("region"), "cn",
                "MarketAnalyzer must not be called with region='cn'")

    def test_route_b_on_tw_us_cn_no_cn_content_in_result(self):
        """Result text must not contain A-share review markers when CN is filtered."""
        config = _route_b_config(market_review_regions=["tw", "us", "cn"])
        notifier = _make_notifier()

        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US market summary",
            market_light_snapshot={"region": "us"},
        )

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history"), \
             patch(_LOCALIZE_PATH, side_effect=lambda t: t), \
             patch.object(market_review_module, "_run_tw_market_review_section",
                          return_value=("TW market summary", {"region": "tw"})), \
             patch.object(market_review_module, "MarketAnalyzer", return_value=us_analyzer):
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNotNone(result)
        for cn_marker in ("台股", "上證", "深證", "創業板", "滬深"):
            self.assertNotIn(cn_marker, result,
                f"Result must not contain CN marker {cn_marker!r} when CN is filtered")

    # ------------------------------------------------------------------
    # Case 3: Route B on, MARKET_REVIEW_REGIONS=CN only → return None
    # ------------------------------------------------------------------

    def test_route_b_on_cn_only_regions_returns_none(self):
        """If MARKET_REVIEW_REGIONS=CN and Route B is on, no regions remain → return None."""
        config = _route_b_config(market_review_regions=["cn"])
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history") as persist, \
             patch.object(market_review_module, "MarketAnalyzer") as analyzer_cls:
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNone(result)
        analyzer_cls.assert_not_called()
        persist.assert_not_called()

    def test_route_b_on_cn_only_no_notification_sent(self):
        """No notification when Route B blocks the only configured CN region."""
        config = _route_b_config(market_review_regions=["cn"])
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "MarketAnalyzer"):
            run_market_review(notifier, send_notification=True)

        notifier.send.assert_not_called()

    # ------------------------------------------------------------------
    # Case 4: Route B off still keeps active market review TW/US-only
    # ------------------------------------------------------------------

    def test_route_b_off_cn_returns_none(self):
        """CN review is no longer an active market even when Route B enforcement is off."""
        config = _legacy_config(market_review_region="cn")
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history") as persist, \
             patch.object(market_review_module, "MarketAnalyzer") as analyzer_cls:
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNone(result, "CN review must not run in active TW/US-only scope")
        analyzer_cls.assert_not_called()
        persist.assert_not_called()

    def test_route_b_off_us_cn_regions_runs_us_only(self):
        """When Route B is off, CN is still dropped and US remains runnable."""
        config = _legacy_config(market_review_regions=["cn", "us"])
        notifier = _make_notifier()

        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body", market_light_snapshot={"region": "us"},
        )

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history"), \
             patch.object(market_review_module, "MarketAnalyzer",
                          return_value=us_analyzer) as analyzer_cls:
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNotNone(result)
        self.assertIn("US body", result)
        analyzer_cls.assert_called_once()
        self.assertEqual(analyzer_cls.call_args.kwargs.get("region"), "us")

    # ------------------------------------------------------------------
    # Case 5: Route B on, TW,US — no CN involved
    # ------------------------------------------------------------------

    def test_route_b_on_tw_us_no_cn_analysis(self):
        """Route B with TW,US: no CN analysis executed; TW and US both run."""
        config = _route_b_config(market_review_regions=["tw", "us"])
        notifier = _make_notifier()

        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US review body",
            market_light_snapshot={"region": "us"},
        )

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history") as persist, \
             patch(_LOCALIZE_PATH, side_effect=lambda t: t), \
             patch.object(market_review_module, "_run_tw_market_review_section",
                          return_value=("TW review body", {"region": "tw"})) as tw_fn, \
             patch.object(market_review_module, "MarketAnalyzer",
                          return_value=us_analyzer) as analyzer_cls:
            result = run_market_review(notifier, send_notification=False)

        self.assertIsNotNone(result)
        self.assertIn("US review body", result)
        tw_fn.assert_called_once()
        for c in analyzer_cls.call_args_list:
            self.assertNotEqual(c.kwargs.get("region"), "cn")
        persist.assert_called_once()

    def test_route_b_on_tw_us_persist_excludes_cn_key(self):
        """Persisted market_light_snapshots must not contain a 'cn' key under Route B."""
        config = _route_b_config(market_review_regions=["tw", "us"])
        notifier = _make_notifier()

        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body",
            market_light_snapshot={"region": "us"},
        )

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history") as persist, \
             patch(_LOCALIZE_PATH, side_effect=lambda t: t), \
             patch.object(market_review_module, "_run_tw_market_review_section",
                          return_value=("TW body", {"region": "tw"})), \
             patch.object(market_review_module, "MarketAnalyzer", return_value=us_analyzer):
            run_market_review(notifier, send_notification=False)

        persist.assert_called_once()
        snapshots = persist.call_args.kwargs["market_light_snapshots"]
        self.assertNotIn("cn", snapshots, "Persisted snapshots must not contain 'cn' key")
        self.assertIn("us", snapshots)
        self.assertIn("tw", snapshots)

    # ------------------------------------------------------------------
    # Case 6: override_region=CN cannot bypass Route B scope gate
    # ------------------------------------------------------------------

    def test_override_region_cn_still_blocked_by_route_b(self):
        """override_region='cn' must not bypass Route B — CN is still filtered."""
        config = _route_b_config(market_review_regions=[])
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "_persist_market_review_history") as persist, \
             patch.object(market_review_module, "MarketAnalyzer") as analyzer_cls:
            result = run_market_review(notifier, send_notification=False, override_region="cn")

        self.assertIsNone(result, "override_region=cn must be blocked by Route B scope gate")
        analyzer_cls.assert_not_called()
        persist.assert_not_called()

    def test_override_region_cn_no_notification_sent_route_b(self):
        """No notification when override_region=cn is blocked under Route B."""
        config = _route_b_config(market_review_regions=[])
        notifier = _make_notifier()

        with patch.object(market_review_module, "get_config", return_value=config), \
             patch.object(market_review_module, "MarketAnalyzer"):
            run_market_review(notifier, send_notification=True, override_region="cn")

        notifier.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()

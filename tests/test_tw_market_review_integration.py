# -*- coding: utf-8 -*-
"""Phase 7E-FINAL: TW market review integration tests.

Verifies:
- _run_tw_market_review_section() calls TaiwanMarketDataFetcher + render_tw_market_review_text
- run_market_review(override_region="tw") uses TW path, never MarketAnalyzer
- run_market_review with multi-market "TW,US" uses TW path for tw, MarketAnalyzer for us
- Output contains "台股大盤回顧"; CN terms are absent
- MarketAnalyzer is NOT instantiated for TW region
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


_FIXTURE_ENV = {
    "DSA_FIXTURE_MODE": "true",
    "DSA_ALLOW_EXTERNAL_NETWORK": "false",
}

_FORBIDDEN_CN_TERMS = [
    "上證", "上证", "深證", "深证", "創業板", "创业板",
    "科創50", "科创50", "滬深", "沪深",
]


def _make_config(**kwargs):
    defaults = dict(
        report_language="zh_TW",
        route_b_enforce_market_scope=True,
        market_review_region="tw",
        market_review_enabled=True,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _fixture_snapshot():
    with patch.dict(os.environ, _FIXTURE_ENV):
        from data_provider.taiwan_market import TaiwanMarketDataFetcher
        fetcher = TaiwanMarketDataFetcher()
        return fetcher.get_tw_market_snapshot("2026-06-01", "2026-06-12")


class TestRunTwMarketReviewSection(unittest.TestCase):
    """_run_tw_market_review_section returns (text, mls) without hitting live network."""

    def test_returns_text_and_mls_in_fixture_mode(self):
        with patch.dict(os.environ, _FIXTURE_ENV):
            from src.core.market_review import _run_tw_market_review_section
            text, mls = _run_tw_market_review_section()
        self.assertIsNotNone(text)
        self.assertIn("台股大盤回顧", text)
        self.assertEqual(mls.get("region"), "tw")
        self.assertIn("source", mls)

    def test_text_starts_with_header(self):
        with patch.dict(os.environ, _FIXTURE_ENV):
            from src.core.market_review import _run_tw_market_review_section
            text, _ = _run_tw_market_review_section()
        self.assertTrue(text.startswith("# 台股大盤回顧"))

    def test_no_cn_terms_in_output(self):
        with patch.dict(os.environ, _FIXTURE_ENV):
            from src.core.market_review import _run_tw_market_review_section
            text, _ = _run_tw_market_review_section()
        for term in _FORBIDDEN_CN_TERMS:
            self.assertNotIn(term, text, msg=f"CN term '{term}' found in TW market review output")

    def test_exception_returns_none_and_empty_mls(self):
        # TaiwanMarketDataFetcher is lazy-imported inside _run_tw_market_review_section;
        # patch at the data_provider module level.
        with patch("data_provider.taiwan_market.TaiwanMarketDataFetcher") as mock_cls:
            mock_cls.side_effect = RuntimeError("fetcher init failed")
            from src.core.market_review import _run_tw_market_review_section
            result = _run_tw_market_review_section()
        self.assertIsNone(result[0])
        self.assertEqual(result[1], {})


class TestRunMarketReviewTwSingleRegion(unittest.TestCase):
    """run_market_review with override_region='tw' uses TW path, not MarketAnalyzer."""

    def _make_notifier(self):
        n = MagicMock()
        n.is_available.return_value = False
        n.save_report_to_file.return_value = "/tmp/test_report.md"
        return n

    def test_tw_single_region_calls_tw_section(self):
        with patch.dict(os.environ, _FIXTURE_ENV):
            with patch("src.core.market_review.get_config", return_value=_make_config()):
                with patch("src.core.market_review._persist_market_review_history"):
                    with patch("src.core.market_review.MarketAnalyzer") as mock_analyzer:
                        from src.core.market_review import run_market_review
                        result = run_market_review(
                            notifier=self._make_notifier(),
                            send_notification=False,
                            override_region="tw",
                        )
        # MarketAnalyzer must NOT be instantiated for TW
        mock_analyzer.assert_not_called()
        self.assertIsNotNone(result)
        self.assertIn("台股大盤回顧", result)

    def test_tw_result_no_cn_terms(self):
        with patch.dict(os.environ, _FIXTURE_ENV):
            with patch("src.core.market_review.get_config", return_value=_make_config()):
                with patch("src.core.market_review._persist_market_review_history"):
                    from src.core.market_review import run_market_review
                    result = run_market_review(
                        notifier=self._make_notifier(),
                        send_notification=False,
                        override_region="tw",
                    )
        for term in _FORBIDDEN_CN_TERMS:
            self.assertNotIn(term, result or "", msg=f"CN term '{term}' found in TW output")


class TestRunMarketReviewTwUsMultiRegion(unittest.TestCase):
    """run_market_review with tw,us multi-region: TW uses TW path, US uses MarketAnalyzer."""

    def _make_notifier(self):
        n = MagicMock()
        n.is_available.return_value = False
        n.save_report_to_file.return_value = "/tmp/test_report.md"
        return n

    def _make_us_review_result(self):
        rr = MagicMock()
        rr.report = "US market recap text"
        rr.market_light_snapshot = {"region": "us", "source": "mock"}
        return rr

    def test_tw_us_multi_region_tw_no_marketanalyzer(self):
        us_result = self._make_us_review_result()
        mock_us_analyzer = MagicMock()
        mock_us_analyzer.run_daily_review_with_snapshot.return_value = us_result

        with patch.dict(os.environ, _FIXTURE_ENV):
            with patch("src.core.market_review.get_config", return_value=_make_config(market_review_region="tw,us")):
                with patch("src.core.market_review._persist_market_review_history"):
                    with patch("src.core.market_review.MarketAnalyzer", return_value=mock_us_analyzer) as mock_analyzer_cls:
                        from src.core.market_review import run_market_review
                        result = run_market_review(
                            notifier=self._make_notifier(),
                            send_notification=False,
                            override_region="tw,us",
                        )
        # MarketAnalyzer must be called for US, but the region arg must NOT be "tw"
        for c in mock_analyzer_cls.call_args_list:
            region_arg = c.kwargs.get("region") or (c.args[0] if c.args else None)
            self.assertNotEqual(region_arg, "tw", "MarketAnalyzer must not be called with region='tw'")

        # Result contains TW header
        self.assertIsNotNone(result)
        self.assertIn("台股大盤回顧", result)

    def test_tw_us_multi_region_us_uses_marketanalyzer(self):
        us_result = self._make_us_review_result()
        mock_us_analyzer = MagicMock()
        mock_us_analyzer.run_daily_review_with_snapshot.return_value = us_result

        with patch.dict(os.environ, _FIXTURE_ENV):
            with patch("src.core.market_review.get_config", return_value=_make_config(market_review_region="tw,us")):
                with patch("src.core.market_review._persist_market_review_history"):
                    with patch("src.core.market_review.MarketAnalyzer", return_value=mock_us_analyzer) as mock_analyzer_cls:
                        from src.core.market_review import run_market_review
                        result = run_market_review(
                            notifier=self._make_notifier(),
                            send_notification=False,
                            override_region="tw,us",
                        )
        # MarketAnalyzer was called (for US)
        self.assertTrue(mock_analyzer_cls.called)
        # And US recap text appears in the result
        self.assertIn("US market recap text", result or "")


class TestCnNotCalledWhenTwRequested(unittest.TestCase):
    """Even if 'cn' appears in regions, CN providers must not be called for TW."""

    def _make_notifier(self):
        n = MagicMock()
        n.is_available.return_value = False
        n.save_report_to_file.return_value = "/tmp/test_report.md"
        return n

    def test_cn_market_analyzer_not_called_for_tw(self):
        with patch.dict(os.environ, _FIXTURE_ENV):
            with patch("src.core.market_review.get_config", return_value=_make_config()):
                with patch("src.core.market_review._persist_market_review_history"):
                    with patch("src.core.market_review.MarketAnalyzer") as mock_analyzer_cls:
                        from src.core.market_review import run_market_review
                        run_market_review(
                            notifier=self._make_notifier(),
                            send_notification=False,
                            override_region="tw",
                        )
        for c in mock_analyzer_cls.call_args_list:
            region_arg = c.kwargs.get("region") or (c.args[0] if c.args else None)
            self.assertNotEqual(region_arg, "cn", "MarketAnalyzer must not be called with region='cn'")
            self.assertNotEqual(region_arg, "tw", "MarketAnalyzer must not be called with region='tw'")


if __name__ == "__main__":
    unittest.main()

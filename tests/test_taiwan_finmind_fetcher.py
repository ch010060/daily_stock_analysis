# -*- coding: utf-8 -*-

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import BaseFetcher, DataFetchError, DataFetcherManager, STANDARD_COLUMNS
from data_provider.taiwan_finmind_fetcher import TaiwanFinMindFetcher


class TestTaiwanFinMindFetcher(unittest.TestCase):
    def test_fixture_daily_data_returns_normalized_dataframe(self):
        fetcher = TaiwanFinMindFetcher()

        df = fetcher.get_daily_data(
            "TW:2330",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        self.assertFalse(df.empty)
        self.assertEqual(df.iloc[0]["code"], "2330")
        for column in ["code", *STANDARD_COLUMNS, "ma5", "ma10", "ma20", "volume_ratio"]:
            self.assertIn(column, df.columns)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["date"]))

    def test_fixture_accepts_dot_tw_symbol(self):
        fetcher = TaiwanFinMindFetcher()

        df = fetcher.get_daily_data(
            "2454.TW",
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        self.assertFalse(df.empty)
        self.assertEqual(df.iloc[0]["code"], "2454")

    def test_live_mode_is_fail_closed_without_network_permission(self):
        # DSA_ALLOW_EXTERNAL_NETWORK defaults to false → guard 2 returns fixture,
        # no error raised even when finmind_enabled=True
        fetcher = TaiwanFinMindFetcher(finmind_enabled=True)

        df = fetcher._fetch_raw_data("TW:2330", "2025-01-01", "2025-03-31")

        self.assertFalse(df.empty)
        self.assertEqual(df.attrs.get("_cache_source"), "fixture")

    def test_get_chips_is_taiwan_fetcher_only(self):
        fetcher = TaiwanFinMindFetcher()

        chips = fetcher.get_chips("2330")

        self.assertEqual(chips["stock_id"], "2330")
        self.assertFalse(hasattr(BaseFetcher, "get_chips"))


class TestTaiwanFinMindRegistration(unittest.TestCase):
    @patch("src.config.get_config")
    def test_registered_after_existing_default_fetchers(self, mock_get_config):
        mock_get_config.return_value = MagicMock(
            tushare_token=None,
            longbridge_app_key=None,
            longbridge_app_secret=None,
            longbridge_access_token=None,
            finnhub_api_key=None,
            alphavantage_api_key=None,
            tickflow_api_key=None,
        )

        manager = DataFetcherManager()
        names = [fetcher.name for fetcher in manager._get_fetchers_snapshot()]

        self.assertIn("TaiwanFinMindFetcher", names)
        self.assertLess(names.index("EfinanceFetcher"), names.index("AkshareFetcher"))
        self.assertLess(names.index("AkshareFetcher"), names.index("YfinanceFetcher"))
        self.assertLess(names.index("YfinanceFetcher"), names.index("TaiwanFinMindFetcher"))


if __name__ == "__main__":
    unittest.main()

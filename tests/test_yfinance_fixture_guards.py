# -*- coding: utf-8 -*-
"""Offline guard tests for YfinanceFetcher US fixtures."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import DataFetchError
from data_provider.yfinance_fetcher import YfinanceFetcher


class TestYfinanceFixtureGuards(unittest.TestCase):
    def _poison_yfinance(self):
        return SimpleNamespace(
            download=MagicMock(side_effect=AssertionError("yfinance.download must not be called"))
        )

    def test_fixture_mode_uses_us_fixture_without_yfinance_download(self):
        fake_yfinance = self._poison_yfinance()
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"yfinance": fake_yfinance}):
                raw = YfinanceFetcher()._fetch_raw_data("US:AAPL", "2025-01-01", "2025-03-31")

        fake_yfinance.download.assert_not_called()
        self.assertFalse(raw.empty)
        self.assertEqual(raw.attrs.get("_cache_source"), "fixture")
        self.assertEqual(raw.attrs.get("_cache_symbol"), "AAPL")

    def test_no_network_permission_uses_fixture_without_yfinance_download(self):
        fake_yfinance = self._poison_yfinance()
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"yfinance": fake_yfinance}):
                df = YfinanceFetcher().get_daily_data(
                    "AAPL",
                    start_date="2025-01-01",
                    end_date="2025-03-31",
                )

        fake_yfinance.download.assert_not_called()
        self.assertFalse(df.empty)
        self.assertIn("close", df.columns)

    def test_missing_us_fixture_does_not_fallback_live(self):
        fake_yfinance = self._poison_yfinance()
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"yfinance": fake_yfinance}):
                with self.assertRaises(DataFetchError) as ctx:
                    YfinanceFetcher()._fetch_raw_data("US:MSFT", "2025-01-01", "2025-03-31")

        fake_yfinance.download.assert_not_called()
        self.assertIn("fixture not found", str(ctx.exception))

    def test_live_allowed_preserves_existing_yfinance_path(self):
        live_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [12345],
            },
            index=pd.to_datetime(["2025-01-02"]),
        )
        fake_yfinance = SimpleNamespace(download=MagicMock(return_value=live_df))
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"yfinance": fake_yfinance}):
                raw = YfinanceFetcher()._fetch_raw_data("AAPL", "2025-01-01", "2025-03-31")

        fake_yfinance.download.assert_called_once()
        self.assertFalse(raw.empty)

    def test_us_fixture_has_cache_meta_source_fixture(self):
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            fetcher = YfinanceFetcher()
            raw = fetcher._fetch_raw_data("AAPL", "2025-01-01", "2025-03-31")
            out = fetcher._normalize_data(raw, "AAPL")

        meta = out.attrs.get("cache_meta")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["source"], "fixture")
        self.assertEqual(meta["market"], "US")
        self.assertEqual(meta["symbol"], "US:AAPL")


if __name__ == "__main__":
    unittest.main()

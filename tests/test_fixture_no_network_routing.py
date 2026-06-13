# -*- coding: utf-8 -*-
"""Manager-level fixture/no-network routing guards for TW/US dry runs."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import BaseFetcher, DataFetcherManager
from data_provider.taiwan_finmind_fetcher import TaiwanFinMindFetcher
from data_provider.yfinance_fetcher import YfinanceFetcher


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-05-01",
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 1000,
                "amount": 101000.0,
                "pct_chg": 1.0,
            }
        ]
    )


class _PoisonLegacyFetcher(BaseFetcher):
    def __init__(self, name: str, priority: int) -> None:
        self.name = name
        self.priority = priority

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise AssertionError(f"{self.name} must not fetch in fixture/no-network mode")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df

    def get_stock_name(self, stock_code: str, allow_realtime: bool = True):
        raise AssertionError(f"{self.name} must not resolve names in fixture/no-network mode")


class _RecordingDailyFetcher(BaseFetcher):
    def __init__(self, name: str, priority: int) -> None:
        self.name = name
        self.priority = priority
        self.calls = []

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append((stock_code, start_date, end_date))
        return _sample_df()

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df


def _legacy_fetchers():
    return [
        _PoisonLegacyFetcher("EfinanceFetcher", 0),
        _PoisonLegacyFetcher("AkshareFetcher", 1),
        _PoisonLegacyFetcher("PytdxFetcher", 2),
        _PoisonLegacyFetcher("BaostockFetcher", 3),
    ]


class TestFixtureNoNetworkRouting(unittest.TestCase):
    def _manager(self) -> DataFetcherManager:
        return DataFetcherManager(
            fetchers=[
                *_legacy_fetchers(),
                YfinanceFetcher(),
                TaiwanFinMindFetcher(),
            ]
        )

    def _poison_yfinance(self):
        return SimpleNamespace(
            download=MagicMock(side_effect=AssertionError("yfinance.download must not be called"))
        )

    def test_no_network_tw_symbol_uses_taiwan_fixture_without_legacy_providers(self):
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            manager = self._manager()
            name = manager.get_stock_name("TW:2330", allow_realtime=False)
            df, source = manager.get_daily_data("TW:2330")

        self.assertEqual(name, "Taiwan Semiconductor Manufacturing Co.")
        self.assertEqual(source, "TaiwanFinMindFetcher")
        self.assertFalse(df.empty)
        self.assertGreaterEqual(str(df["date"].min().date()), "2025-01-01")
        self.assertLessEqual(str(df["date"].max().date()), "2025-03-31")

    def test_no_network_us_symbol_uses_yfinance_fixture_without_legacy_providers(self):
        fake_yfinance = self._poison_yfinance()
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            with patch.dict(sys.modules, {"yfinance": fake_yfinance}):
                manager = self._manager()
                name = manager.get_stock_name("US:AAPL", allow_realtime=False)
                df, source = manager.get_daily_data("US:AAPL")

        self.assertEqual(name, "Apple Inc.")
        self.assertEqual(source, "YfinanceFetcher")
        self.assertFalse(df.empty)
        self.assertIn("close", df.columns)
        fake_yfinance.download.assert_not_called()

    def test_fixture_no_network_does_not_change_live_provider_order_when_network_allowed(self):
        finnhub = _RecordingDailyFetcher("FinnhubFetcher", 2)
        yfinance = _RecordingDailyFetcher("YfinanceFetcher", 4)
        manager = DataFetcherManager(fetchers=[yfinance, finnhub])

        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env):
            df, source = manager.get_daily_data(
                "AAPL",
                start_date="2026-05-01",
                end_date="2026-05-08",
            )

        self.assertFalse(df.empty)
        self.assertEqual(source, "FinnhubFetcher")
        self.assertEqual(finnhub.calls, [("AAPL", "2026-05-01", "2026-05-08")])
        self.assertEqual(yfinance.calls, [])

    def test_fixture_dry_run_date_range_uses_fixture_available_rows(self):
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            manager = self._manager()
            tw_df, tw_source = manager.get_daily_data("TW:2330")
            us_df, us_source = manager.get_daily_data("US:AAPL")

        self.assertEqual(tw_source, "TaiwanFinMindFetcher")
        self.assertEqual(us_source, "YfinanceFetcher")
        self.assertFalse(tw_df.empty)
        self.assertFalse(us_df.empty)
        self.assertLessEqual(str(tw_df["date"].max().date()), "2025-03-31")
        self.assertLessEqual(str(us_df["date"].max().date()), "2025-03-31")


if __name__ == "__main__":
    unittest.main()

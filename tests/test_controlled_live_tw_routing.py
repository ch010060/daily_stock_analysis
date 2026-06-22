# -*- coding: utf-8 -*-
"""Controlled TW live routing guard tests."""

import os
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import BaseFetcher, DataFetcherManager


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


class _PoisonDailyFetcher(BaseFetcher):
    def __init__(self, name: str, priority: int) -> None:
        self.name = name
        self.priority = priority
        self.calls = []

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append((stock_code, start_date, end_date))
        raise AssertionError(f"{self.name} must not fetch in controlled TW live mode")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        return df

    def get_stock_name(self, stock_code: str, allow_realtime: bool = True):
        self.calls.append(("stock_name", stock_code))
        raise AssertionError(f"{self.name} must not resolve names in controlled TW live mode")


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


def _controlled_live_env(**overrides: str) -> dict:
    env = {
        "DSA_FIXTURE_MODE": "false",
        "DSA_ALLOW_EXTERNAL_NETWORK": "true",
        "FINMIND_ENABLED": "true",
    }
    env.update(overrides)
    return env


def _legacy_poison_fetchers():
    return [
        _PoisonDailyFetcher("EfinanceFetcher", 0),
        _PoisonDailyFetcher("AkshareFetcher", 1),
        _PoisonDailyFetcher("BaostockFetcher", 3),
        _PoisonDailyFetcher("YfinanceFetcher", 4),
    ]


class TestControlledLiveTWRouting(unittest.TestCase):
    def test_controlled_live_tw_symbol_routes_directly_to_finmind(self):
        finmind = _RecordingDailyFetcher("TaiwanFinMindFetcher", 99)
        legacy = _legacy_poison_fetchers()
        manager = DataFetcherManager(fetchers=[*legacy, finmind])

        with patch.dict(os.environ, _controlled_live_env(), clear=False):
            df, source = manager.get_daily_data(
                "TW:2330",
                start_date="2025-01-02",
                end_date="2025-01-10",
            )

        self.assertEqual(source, "TaiwanFinMindFetcher")
        self.assertFalse(df.empty)
        self.assertEqual(finmind.calls, [("TW:2330", "2025-01-02", "2025-01-10")])
        for fetcher in legacy:
            self.assertEqual(fetcher.calls, [])

    def test_controlled_live_tw_dot_suffix_routes_directly_to_finmind(self):
        finmind = _RecordingDailyFetcher("TaiwanFinMindFetcher", 99)
        legacy = _legacy_poison_fetchers()
        manager = DataFetcherManager(fetchers=[*legacy, finmind])

        with patch.dict(os.environ, _controlled_live_env(), clear=False):
            df, source = manager.get_daily_data(
                "2330.TW",
                start_date="2025-01-02",
                end_date="2025-01-10",
            )

        self.assertEqual(source, "TaiwanFinMindFetcher")
        self.assertFalse(df.empty)
        self.assertEqual(finmind.calls, [("TW:2330", "2025-01-02", "2025-01-10")])
        for fetcher in legacy:
            self.assertEqual(fetcher.calls, [])

    def test_controlled_live_tw_stock_name_uses_local_label_without_legacy_providers(self):
        finmind = _RecordingDailyFetcher("TaiwanFinMindFetcher", 99)
        legacy = _legacy_poison_fetchers()
        manager = DataFetcherManager(fetchers=[*legacy, finmind])

        with patch.dict(os.environ, _controlled_live_env(), clear=False):
            with patch.object(
                manager,
                "get_realtime_quote",
                side_effect=AssertionError("realtime quote must not be called"),
            ):
                name = manager.get_stock_name("TW:2330")

        self.assertEqual(name, "台積電")
        for fetcher in legacy:
            self.assertEqual(fetcher.calls, [])

    def test_finmind_disabled_preserves_existing_live_provider_order(self):
        efinance = _RecordingDailyFetcher("EfinanceFetcher", 0)
        finmind = _RecordingDailyFetcher("TaiwanFinMindFetcher", 99)
        manager = DataFetcherManager(fetchers=[efinance, finmind])

        with patch.dict(
            os.environ,
            _controlled_live_env(FINMIND_ENABLED="false"),
            clear=False,
        ):
            df, source = manager.get_daily_data(
                "TW:2330",
                start_date="2025-01-02",
                end_date="2025-01-10",
            )

        self.assertEqual(source, "EfinanceFetcher")
        self.assertFalse(df.empty)
        self.assertEqual(efinance.calls, [("2330", "2025-01-02", "2025-01-10")])
        self.assertEqual(finmind.calls, [])

    def test_us_symbol_not_affected_by_tw_live_guard(self):
        manager = DataFetcherManager(fetchers=[])

        with patch.dict(os.environ, _controlled_live_env(), clear=False):
            routed = manager._try_controlled_tw_live_daily_data(
                "US:AAPL",
                start_date="2025-01-02",
                end_date="2025-01-10",
                days=30,
            )

        self.assertIsNone(routed)

    def test_fixture_no_network_guard_still_wins(self):
        finmind = _RecordingDailyFetcher("TaiwanFinMindFetcher", 99)
        legacy = _legacy_poison_fetchers()
        manager = DataFetcherManager(fetchers=[*legacy, finmind])

        env = {
            "DSA_FIXTURE_MODE": "true",
            "DSA_ALLOW_EXTERNAL_NETWORK": "false",
            "FINMIND_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            df, source = manager.get_daily_data("TW:2330")

        self.assertEqual(source, "TaiwanFinMindFetcher")
        self.assertFalse(df.empty)
        self.assertEqual(finmind.calls, [("TW:2330", "2025-01-01", "2025-03-31")])
        for fetcher in legacy:
            self.assertEqual(fetcher.calls, [])


if __name__ == "__main__":
    unittest.main()

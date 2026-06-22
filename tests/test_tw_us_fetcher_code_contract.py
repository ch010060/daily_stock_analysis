# -*- coding: utf-8 -*-
"""Regression tests for active TW/US stock-code handling."""

import unittest
from unittest.mock import patch

import pandas as pd

from data_provider.base import DataFetcherManager, normalize_stock_code


class _RecordingDailyFetcher:
    name = "RecordingDailyFetcher"
    priority = 1

    def __init__(self) -> None:
        self.calls = []

    def get_daily_data(self, stock_code: str, *args, **kwargs) -> pd.DataFrame:
        self.calls.append(stock_code)
        return pd.DataFrame({"date": ["2026-05-22"], "close": [10.0]})


class TestDataFetcherManagerTWUSCodes(unittest.TestCase):
    def test_get_daily_data_keeps_tw_code_contract_as_bare_symbol(self) -> None:
        fetcher = _RecordingDailyFetcher()
        manager = DataFetcherManager(fetchers=[fetcher])

        with patch.dict("os.environ", {"FINMIND_ENABLED": "false"}, clear=False):
            df, source = manager.get_daily_data("2330", days=1)

        self.assertFalse(df.empty)
        self.assertEqual(source, "RecordingDailyFetcher")
        self.assertEqual(fetcher.calls, ["2330"])

class TestNormalizeStockCodeTWUSOnly(unittest.TestCase):
    def test_normalize_tw_forms(self) -> None:
        self.assertEqual(normalize_stock_code("2330"), "2330")
        self.assertEqual(normalize_stock_code("TW:2330"), "2330")
        self.assertEqual(normalize_stock_code("2330.TW"), "2330")
        self.assertEqual(normalize_stock_code("00981A"), "00981A")
        self.assertEqual(normalize_stock_code("TW:00981A"), "00981A")

    def test_normalize_us_forms(self) -> None:
        self.assertEqual(normalize_stock_code("aapl"), "AAPL")
        self.assertEqual(normalize_stock_code("US:AAPL"), "AAPL")
        self.assertEqual(normalize_stock_code("AAPL.US"), "AAPL")

    def test_unsupported_market_prefixes_are_not_silently_converted(self) -> None:
        self.assertEqual(normalize_stock_code("BADTARGET"), "BADTARGET")


if __name__ == "__main__":
    unittest.main()

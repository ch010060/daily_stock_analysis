# -*- coding: utf-8 -*-
"""Focused tests for K-line snapshot helpers."""
from __future__ import annotations

import unittest

from src.services.kline_snapshot import _yfinance_intraday_symbol


class KlineSnapshotHelperTest(unittest.TestCase):
    def test_yfinance_intraday_symbol_maps_tw_stock_and_etf(self):
        self.assertEqual(_yfinance_intraday_symbol("2330", "tw"), "2330.TW")
        self.assertEqual(_yfinance_intraday_symbol("006208", "tw"), "006208.TW")
        self.assertEqual(_yfinance_intraday_symbol("2454.TW", "tw"), "2454.TW")

    def test_yfinance_intraday_symbol_maps_us_symbols(self):
        self.assertEqual(_yfinance_intraday_symbol("MSFT", "us"), "MSFT")
        self.assertEqual(_yfinance_intraday_symbol("SPY.US", "us"), "SPY")


if __name__ == "__main__":
    unittest.main()

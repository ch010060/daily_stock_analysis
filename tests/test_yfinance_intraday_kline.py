# -*- coding: utf-8 -*-
"""Tests for yfinance-backed intraday K-line API prototype."""
from __future__ import annotations

import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd


def _make_record(code: str = "MSFT", instrument_type: str = "stock"):
    record = MagicMock()
    record.id = 65
    record.code = code
    record.created_at = datetime(2026, 6, 27, 12, 0, 0)
    record.raw_result = json.dumps({
        "instrument_type": instrument_type,
        "current_price": 123.4,
        "support_level": 110.0,
        "resistance_level": 140.0,
    })
    return record


def _make_db(code: str = "MSFT", instrument_type: str = "stock"):
    db = MagicMock()
    db.get_analysis_history_by_id.return_value = _make_record(code, instrument_type)
    db.get_latest_analysis_by_query_id.return_value = None
    db.get_data_range.return_value = []
    return db


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Open": 100.0, "High": 105.0, "Low": 99.0, "Close": 104.0, "Volume": 1000},
            {"Open": 104.0, "High": 106.0, "Low": 103.0, "Close": 105.0, "Volume": 1200},
        ],
        index=pd.DatetimeIndex([
            "2026-06-26T09:30:00-04:00",
            "2026-06-26T09:35:00-04:00",
        ]),
    )


class YfinanceIntradayKlineTest(unittest.TestCase):
    def _call(self, code="MSFT", range_value="1d", instrument_type="stock"):
        from src.services.kline_snapshot import build_history_kline

        return build_history_kline(_make_db(code, instrument_type), "65", range_value)

    def test_1d_maps_to_intraday_5m_contract(self):
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(_frame(), "USD")) as fetcher:
            result = self._call("MSFT", "1d")
        fetcher.assert_called_once_with("MSFT", "1d", "5m")
        self.assertEqual(result["granularity"], "intraday")
        self.assertEqual(result["interval"], "5m")
        self.assertEqual(result["source"], "yfinance")
        self.assertEqual(result["source_chain"], ["yfinance"])
        self.assertFalse(result["is_cached"])
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["timezone"], "UTC-04:00")
        self.assertEqual(len(result["candles"]), 2)
        self.assertEqual(result["candles"][0]["timestamp"], "2026-06-26T09:30:00-04:00")
        self.assertEqual(result["rows"], [])

    def test_5d_maps_to_intraday_15m_contract(self):
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(_frame(), "USD")) as fetcher:
            result = self._call("SPY", "5d", "etf")
        fetcher.assert_called_once_with("SPY", "5d", "15m")
        self.assertEqual(result["range"], "5d")
        self.assertEqual(result["interval"], "15m")
        self.assertEqual(result["instrument_type"], "etf")

    def test_tw_symbols_use_yfinance_tw_suffix(self):
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(_frame(), "TWD")) as fetcher:
            result = self._call("2330", "1d")
        fetcher.assert_called_once_with("2330.TW", "1d", "5m")
        self.assertEqual(result["symbol"], "2330.TW")
        self.assertEqual(result["market"], "tw")
        self.assertEqual(result["currency"], "TWD")

    def test_tw_etf_uses_yfinance_tw_suffix(self):
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(_frame(), "TWD")) as fetcher:
            result = self._call("006208", "5d", "etf")
        fetcher.assert_called_once_with("006208.TW", "5d", "15m")
        self.assertEqual(result["symbol"], "006208.TW")

    def test_empty_provider_response_returns_gap(self):
        empty = pd.DataFrame()
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(empty, "USD")):
            result = self._call("MSFT", "1d")
        self.assertEqual(result["candles"], [])
        self.assertEqual(result["granularity"], "intraday")
        self.assertEqual(result["interval"], "5m")
        self.assertEqual(result["data_gap_reason"], "provider_empty_response")

    def test_partial_ohlcv_rows_are_dropped(self):
        frame = _frame()
        frame.iloc[0, frame.columns.get_loc("Open")] = None
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(frame, "USD")):
            result = self._call("MSFT", "1d")
        self.assertEqual(len(result["candles"]), 1)
        self.assertEqual(result["candles"][0]["open"], 104.0)
        self.assertIsNone(result["data_gap_reason"])

    def test_all_partial_rows_return_explicit_gap(self):
        frame = _frame()
        frame["Open"] = None
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(frame, "USD")):
            result = self._call("MSFT", "1d")
        self.assertEqual(result["candles"], [])
        self.assertEqual(result["data_gap_reason"], "provider_partial_ohlcv")

    def test_provider_exception_returns_specific_gap(self):
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", side_effect=TimeoutError("network timeout")):
            result = self._call("MSFT", "1d")
        self.assertEqual(result["candles"], [])
        self.assertEqual(result["data_gap_reason"], "provider_network_error")


if __name__ == "__main__":
    unittest.main()

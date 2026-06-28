# -*- coding: utf-8 -*-
"""Focused tests for K-line snapshot helpers."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from src.services.kline_snapshot import (
    _yfinance_intraday_symbol,
    build_report_kline_snapshot_payload,
    persist_report_kline_snapshots,
)


class KlineSnapshotHelperTest(unittest.TestCase):
    def test_yfinance_intraday_symbol_maps_tw_stock_and_etf(self):
        self.assertEqual(_yfinance_intraday_symbol("2330", "tw"), "2330.TW")
        self.assertEqual(_yfinance_intraday_symbol("006208", "tw"), "006208.TW")
        self.assertEqual(_yfinance_intraday_symbol("2454.TW", "tw"), "2454.TW")

    def test_yfinance_intraday_symbol_maps_us_symbols(self):
        self.assertEqual(_yfinance_intraday_symbol("MSFT", "us"), "MSFT")
        self.assertEqual(_yfinance_intraday_symbol("SPY.US", "us"), "SPY")
        self.assertEqual(_yfinance_intraday_symbol("BRK.B", "us"), "BRK-B")
        self.assertEqual(_yfinance_intraday_symbol("BRK.A", "us"), "BRK-A")
        self.assertEqual(_yfinance_intraday_symbol("BF.B", "us"), "BF-B")


def _record():
    row = MagicMock()
    row.id = 65
    row.code = "MSFT"
    row.created_at = datetime(2026, 6, 27, 12, 0, 0)
    row.raw_result = '{"instrument_type":"stock"}'
    return row


def _bar(index: int):
    row = MagicMock()
    row.date = date(2026, 1, 1) + timedelta(days=index)
    row.open = 100 + index
    row.high = 101 + index
    row.low = 99 + index
    row.close = 100.5 + index
    row.volume = 1000 + index
    row.data_source = "YfinanceFetcher"
    return row


def _db():
    db = MagicMock()
    db.get_analysis_history_by_id.return_value = _record()
    db.get_latest_analysis_by_query_id.return_value = None
    db.get_data_range.return_value = [_bar(i) for i in range(300)]
    db.upsert_analysis_kline_snapshot.return_value = 1
    return db


def _frame():
    return pd.DataFrame(
        [{"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000}],
        index=pd.DatetimeIndex(["2026-06-26T09:30:00-04:00"]),
    )


class KlineSnapshotBuilderTest(unittest.TestCase):
    def test_persist_report_snapshots_includes_required_ranges(self):
        db = _db()
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(_frame(), "USD")):
            self.assertEqual(persist_report_kline_snapshots(db, 65), 6)
        ranges = [call.args[0]["range"] for call in db.upsert_analysis_kline_snapshot.call_args_list]
        self.assertEqual(ranges, ["1d", "5d", "1w", "1m", "3m", "1y"])

    def test_intraday_builder_uses_expected_intervals(self):
        db = _db()
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", return_value=(_frame(), "USD")) as fetcher:
            self.assertEqual(build_report_kline_snapshot_payload(db, "65", "1d")["interval"], "5m")
            self.assertEqual(build_report_kline_snapshot_payload(db, "65", "5d")["interval"], "15m")
        self.assertEqual(fetcher.call_args_list[0].args, ("MSFT", "1d", "5m"))
        self.assertEqual(fetcher.call_args_list[1].args, ("MSFT", "5d", "15m"))

    def test_daily_builder_uses_db_rows_not_intraday_provider(self):
        db = _db()
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame") as fetcher:
            payload = build_report_kline_snapshot_payload(db, "65", "3m")
        fetcher.assert_not_called()
        self.assertEqual(payload["granularity"], "daily")
        self.assertEqual(len(payload["rows"]), 60)

    def test_provider_failure_persists_gap_snapshot(self):
        db = _db()
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame", side_effect=TimeoutError("timeout")):
            self.assertEqual(persist_report_kline_snapshots(db, 65, ["1d"]), 1)
        payload = db.upsert_analysis_kline_snapshot.call_args.args[0]
        self.assertEqual(payload["data_gap_reason"], "provider_network_error")
        self.assertEqual(payload["candles"], [])


if __name__ == "__main__":
    unittest.main()

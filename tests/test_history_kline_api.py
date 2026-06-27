# -*- coding: utf-8 -*-
"""Tests for GET /api/v1/history/{id}/kline."""
from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi import HTTPException


def _make_bar(index: int, source: str = "YfinanceFetcher"):
    bar = MagicMock()
    bar.date = date(2026, 1, 1) + timedelta(days=index)
    bar.open = 100.0 + index
    bar.high = 105.0 + index
    bar.low = 95.0 + index
    bar.close = 101.0 + index
    bar.volume = 1_000_000 + index
    bar.data_source = source
    return bar


def _bars(count: int, source: str = "YfinanceFetcher"):
    return [_make_bar(i, source=source) for i in range(count)]


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


def _make_db(bars, record=None):
    db = MagicMock()
    db.get_analysis_history_by_id.return_value = record or _make_record()
    db.get_latest_analysis_by_query_id.return_value = None
    db.get_data_range.return_value = bars
    return db


class HistoryKlineApiTest(unittest.TestCase):
    def _call(self, rows, code="MSFT", range_value="3m", instrument_type="stock"):
        from api.v1.endpoints.history import get_history_kline

        db = _make_db(rows, _make_record(code=code, instrument_type=instrument_type))
        return get_history_kline(record_id="65", range=range_value, db_manager=db)

    def test_history_not_found_returns_404(self):
        from api.v1.endpoints.history import get_history_kline

        db = MagicMock()
        db.get_analysis_history_by_id.return_value = None
        db.get_latest_analysis_by_query_id.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            get_history_kline(record_id="999", range="3m", db_manager=db)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_valid_msft_history_returns_db_cache_rows(self):
        result = self._call(_bars(80), code="MSFT", range_value="3m")
        self.assertEqual(result.symbol, "MSFT")
        self.assertEqual(result.market, "us")
        self.assertEqual(result.instrument_type, "stock")
        self.assertEqual(result.granularity, "daily")
        self.assertEqual(result.interval, "1d")
        self.assertEqual(result.source, "YfinanceFetcher")
        self.assertEqual(result.source_type, "db_cache")
        self.assertTrue(result.is_cached)
        self.assertEqual(len(result.rows), 60)
        self.assertEqual(len(result.candles), 60)
        self.assertIsNone(result.data_gap_reason)

    def test_valid_tw_history_returns_finmind_source(self):
        result = self._call(
            _bars(80, source="TaiwanFinMindFetcher"),
            code="2454",
            range_value="3m",
        )
        self.assertEqual(result.market, "tw")
        self.assertEqual(result.source, "TaiwanFinMindFetcher")
        self.assertEqual(len(result.rows), 60)

    def test_ranges_slice_expected_row_counts(self):
        rows = _bars(300)
        self.assertEqual(len(self._call(rows, range_value="1w").rows), 10)
        self.assertEqual(len(self._call(rows, range_value="1m").rows), 20)
        self.assertEqual(len(self._call(rows, range_value="3m").rows), 60)
        self.assertEqual(len(self._call(rows, range_value="1y").rows), 252)

    def test_ma_fields_require_warmup_rows(self):
        warmed = self._call(_bars(40), range_value="1w")
        self.assertIsNotNone(warmed.rows[-1].ma20)
        cold = self._call(_bars(10), range_value="1w")
        self.assertIsNone(cold.rows[-1].ma20)

    def test_no_cached_rows_returns_explicit_gap(self):
        result = self._call([], code="MSFT", range_value="3m")
        self.assertEqual(result.rows, [])
        self.assertEqual(result.source, "YfinanceFetcher")
        self.assertEqual(result.source_type, "data_gap")
        self.assertEqual(result.data_gap_reason, "no_cached_ohlc")

    def test_unknown_instrument_type_does_not_crash(self):
        result = self._call(_bars(10), instrument_type="unknown", range_value="1w")
        self.assertEqual(result.instrument_type, "unknown")
        self.assertEqual(len(result.rows), 10)

    def test_endpoint_does_not_construct_provider_manager_on_miss(self):
        with patch("data_provider.base.DataFetcherManager") as manager:
            self._call([], code="MSFT")
        manager.assert_not_called()

    def test_daily_ranges_do_not_call_intraday_provider(self):
        with patch("src.services.kline_snapshot._fetch_yfinance_intraday_frame") as fetcher:
            self._call(_bars(80), code="MSFT", range_value="1m")
        fetcher.assert_not_called()

    def test_tw_miss_does_not_call_yfinance(self):
        with patch("data_provider.yfinance_fetcher.YfinanceFetcher") as fetcher:
            result = self._call([], code="006208", instrument_type="etf")
        fetcher.assert_not_called()
        self.assertEqual(result.source, "TaiwanFinMindFetcher")

    def test_us_miss_does_not_call_finmind(self):
        with patch("data_provider.taiwan_finmind_fetcher.TaiwanFinMindFetcher") as fetcher:
            result = self._call([], code="SPY", instrument_type="etf")
        fetcher.assert_not_called()
        self.assertEqual(result.source, "YfinanceFetcher")


if __name__ == "__main__":
    unittest.main()

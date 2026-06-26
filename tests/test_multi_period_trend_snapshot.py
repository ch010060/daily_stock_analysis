# -*- coding: utf-8 -*-
"""Phase 19B.4 — tests for the multi-period trend snapshot builder."""
import unittest
from datetime import date, timedelta

from src.services.multi_period_trend_snapshot import (
    build_multi_period_trend_snapshot,
    classify_period_trend,
    format_pct,
    normalize_ohlc_rows,
)


def _make_rows(n: int, start_price: float = 100.0, daily_step: float = 0.0):
    """n ascending-date rows, close = start_price + i*daily_step."""
    base = date(2025, 1, 1)
    rows = []
    for i in range(n):
        close = start_price + i * daily_step
        rows.append({
            "date": (base + timedelta(days=i)).isoformat(),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000,
        })
    return rows


class TestNormalizeOhlcRows(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(normalize_ohlc_rows(None), [])

    def test_malformed_returns_empty(self):
        self.assertEqual(normalize_ohlc_rows("not a list"), [])
        self.assertEqual(normalize_ohlc_rows(12345), [])

    def test_drops_rows_missing_close(self):
        rows = [{"date": "2025-01-01", "high": 10, "low": 9}, {"date": "2025-01-02", "close": 10.0}]
        result = normalize_ohlc_rows(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["close"], 10.0)

    def test_sorts_ascending_by_date(self):
        rows = [{"date": "2025-01-03", "close": 3.0}, {"date": "2025-01-01", "close": 1.0}]
        result = normalize_ohlc_rows(rows)
        self.assertEqual([r["close"] for r in result], [1.0, 3.0])


class TestFormatPct(unittest.TestCase):
    def test_none_passthrough(self):
        self.assertIsNone(format_pct(None))

    def test_rounds_to_two_decimals(self):
        self.assertEqual(format_pct(1.23456), 1.23)

    def test_malformed_returns_none(self):
        self.assertIsNone(format_pct("not a number"))


class TestClassifyPeriodTrend(unittest.TestCase):
    def test_insufficient_when_missing(self):
        self.assertEqual(classify_period_trend(None, None), "insufficient_data")
        self.assertEqual(classify_period_trend(5.0, None), "insufficient_data")

    def test_uptrend_thresholds(self):
        self.assertEqual(classify_period_trend(5.0, 0.0), "uptrend")
        self.assertEqual(classify_period_trend(10.0, 3.0), "uptrend")

    def test_downtrend_thresholds(self):
        self.assertEqual(classify_period_trend(-5.0, -0.1), "downtrend")
        self.assertEqual(classify_period_trend(-10.0, -3.0), "downtrend")

    def test_neutral_otherwise(self):
        self.assertEqual(classify_period_trend(2.0, 1.0), "neutral")
        self.assertEqual(classify_period_trend(-5.0, 1.0), "neutral")  # change<=−5 but ma-side wrong
        self.assertEqual(classify_period_trend(5.0, -1.0), "neutral")  # change>=5 but ma-side wrong


class TestBuildMultiPeriodTrendSnapshot(unittest.TestCase):
    def test_empty_input_returns_none(self):
        self.assertIsNone(build_multi_period_trend_snapshot([], source="db_cache"))
        self.assertIsNone(build_multi_period_trend_snapshot(None, source="db_cache"))

    def test_malformed_input_returns_none_without_exception(self):
        self.assertIsNone(build_multi_period_trend_snapshot("garbage", source=None))
        self.assertIsNone(build_multi_period_trend_snapshot(12345, source=None))

    def test_full_260_rows_computes_all_periods(self):
        rows = _make_rows(260, start_price=100.0, daily_step=0.5)
        snapshot = build_multi_period_trend_snapshot(rows, source="db_cache", as_of="2025-09-17")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["data_gap_fields"], [])
        self.assertEqual(len(snapshot["periods"]), 5)
        for period in snapshot["periods"]:
            self.assertEqual(period["data_gap_fields"], [])
            self.assertIsNotNone(period["change_pct"])
            self.assertIsNotNone(period["trend_status"])
            self.assertNotEqual(period["trend_status"], "insufficient_data")
        self.assertEqual(snapshot["latest_close"], rows[-1]["close"])

    def test_60_rows_computes_short_periods_and_gaps_long_periods(self):
        rows = _make_rows(60, start_price=50.0, daily_step=5.0)
        snapshot = build_multi_period_trend_snapshot(rows, source="yfinance")
        self.assertIsNotNone(snapshot)
        by_period = {p["period"]: p for p in snapshot["periods"]}
        for key in ("5D", "20D", "60D"):
            self.assertEqual(by_period[key]["data_gap_fields"], [])
            self.assertEqual(by_period[key]["trend_status"], "uptrend")
        for key in ("120D", "252D"):
            self.assertIn("change_pct", by_period[key]["data_gap_fields"])
            self.assertIsNone(by_period[key]["change_pct"])
            self.assertEqual(by_period[key]["trend_status"], "insufficient_data")
        self.assertIn("120D", snapshot["data_gap_fields"])
        self.assertIn("252D", snapshot["data_gap_fields"])

    def test_52w_drawdown_uses_period_high_not_latest_only(self):
        # Price rises then falls within the 252D window: period_high should
        # be the peak, not the latest close, and drawdown should reflect that.
        rows = _make_rows(160, start_price=100.0, daily_step=1.0)  # peak ~259
        falling = _make_rows(102, start_price=rows[-1]["close"], daily_step=-1.0)[1:]
        # re-date falling rows to continue after rows
        base_date = date.fromisoformat(rows[-1]["date"])
        for i, r in enumerate(falling):
            r["date"] = (base_date + timedelta(days=i + 1)).isoformat()
        all_rows = rows + falling
        snapshot = build_multi_period_trend_snapshot(all_rows, source="db_cache")
        by_period = {p["period"]: p for p in snapshot["periods"]}
        p252 = by_period["252D"]
        self.assertEqual(p252["data_gap_fields"], [])
        self.assertGreater(p252["period_high"], p252["end_close"])
        self.assertLess(p252["drawdown_from_high_pct"], 0)

    def test_no_raw_none_outside_contract_for_sufficient_period(self):
        rows = _make_rows(10, start_price=10.0, daily_step=0.1)
        snapshot = build_multi_period_trend_snapshot(rows, source="db_cache")
        period_5d = next(p for p in snapshot["periods"] if p["period"] == "5D")
        for field in (
            "start_close", "end_close", "change_pct", "period_high", "period_low",
            "drawdown_from_high_pct", "ma", "price_vs_ma_pct",
        ):
            self.assertIsNotNone(period_5d[field])


if __name__ == "__main__":
    unittest.main()

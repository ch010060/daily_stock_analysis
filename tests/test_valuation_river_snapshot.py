# -*- coding: utf-8 -*-
"""
Phase 26.1 — tests for src.services.valuation_river_snapshot.

Pure-function tests: no network, no FinMind fetcher involved. Feeds plain
row dicts (the shape FinMind's `TaiwanStockPER`/`TaiwanStockPrice` fetch
results already carry) directly into the deterministic builder.
"""
import unittest

from src.services.valuation_river_snapshot import (
    METHODOLOGY_NOTE,
    NEUTRAL_MULTIPLE,
    PER_BAND_MULTIPLES,
    build_tw_valuation_river_snapshot,
    build_valuation_river_snapshot_unsupported,
)


def _per_row(d: str, per: float, pbr: float = 6.0, dividend_yield: float = 1.5) -> dict:
    return {"date": d, "stock_id": "2330", "PER": per, "PBR": pbr, "dividend_yield": dividend_yield}


def _price_row(d: str, close: float) -> dict:
    return {"date": d, "stock_id": "2330", "close": close}


class BuildTwValuationRiverSnapshotTestCase(unittest.TestCase):
    def test_successful_river_from_full_overlap(self) -> None:
        per_rows = [_per_row(f"2026-01-{d:02d}", per=20.0 + d) for d in range(1, 25)]
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0 + d * 10) for d in range(1, 25)]

        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)

        self.assertTrue(snap["enabled"])
        self.assertEqual(snap["market"], "tw")
        self.assertEqual(snap["currency"], "TWD")
        self.assertEqual(snap["source"], "finmind")
        self.assertEqual(snap["method"], "per_implied_eps_river")
        self.assertEqual(snap["basis"], "implied_eps")
        self.assertEqual(len(snap["points"]), 24)
        self.assertEqual(snap["range"]["trading_days"], 24)
        self.assertEqual(snap["range"]["start_date"], "2026-01-01")
        self.assertEqual(snap["range"]["end_date"], "2026-01-24")
        self.assertEqual(snap["as_of"], "2026-01-24")
        self.assertEqual(snap["quality"]["status"], "ok")
        self.assertEqual(snap["quality"]["methodology_note"], METHODOLOGY_NOTE)
        self.assertEqual(snap["band_multiples"], list(PER_BAND_MULTIPLES))
        self.assertEqual(snap["neutral_multiple"], NEUTRAL_MULTIPLE)

        first = snap["points"][0]
        self.assertAlmostEqual(first["implied_eps"], 1010.0 / 21.0, places=4)
        self.assertIn("bands", first)
        for mult in PER_BAND_MULTIPLES:
            self.assertAlmostEqual(first["bands"][f"per_{mult}"], first["implied_eps"] * mult, places=4)

    def test_current_zone_reflects_last_observed_per(self) -> None:
        per_rows = [_per_row("2026-01-01", per=NEUTRAL_MULTIPLE - 5)] + [
            _per_row(f"2026-01-{d:02d}", per=10.0) for d in range(2, 21)
        ]
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0) for d in range(1, 21)]
        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)
        self.assertEqual(snap["current"]["zone"], "undervalued")

        per_rows_high = [_per_row(f"2026-02-{d:02d}", per=NEUTRAL_MULTIPLE + 10) for d in range(1, 21)]
        price_rows_high = [_price_row(f"2026-02-{d:02d}", close=1000.0) for d in range(1, 21)]
        snap_high = build_tw_valuation_river_snapshot("2330", per_rows_high, price_rows_high)
        self.assertEqual(snap_high["current"]["zone"], "overvalued")

        per_rows_fair = [_per_row(f"2026-03-{d:02d}", per=NEUTRAL_MULTIPLE) for d in range(1, 21)]
        price_rows_fair = [_price_row(f"2026-03-{d:02d}", close=1000.0) for d in range(1, 21)]
        snap_fair = build_tw_valuation_river_snapshot("2330", per_rows_fair, price_rows_fair)
        self.assertEqual(snap_fair["current"]["zone"], "neutral")

    def test_missing_per_rows_returns_unsupported(self) -> None:
        price_rows = [_price_row("2026-01-01", close=1000.0)]
        snap = build_tw_valuation_river_snapshot("2330", [], price_rows)
        self.assertFalse(snap["enabled"])
        self.assertEqual(snap["quality"]["status"], "unsupported")
        self.assertEqual(snap["points"], [])
        self.assertIn("TaiwanStockPER", snap["quality"]["warnings"][0])

    def test_missing_price_rows_returns_unsupported(self) -> None:
        per_rows = [_per_row("2026-01-01", per=20.0)]
        snap = build_tw_valuation_river_snapshot("2330", per_rows, [])
        self.assertFalse(snap["enabled"])
        self.assertIn("TaiwanStockPrice", snap["quality"]["warnings"][0])

    def test_no_overlapping_dates_returns_unsupported(self) -> None:
        per_rows = [_per_row("2026-01-01", per=20.0)]
        price_rows = [_price_row("2026-02-01", close=1000.0)]
        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)
        self.assertFalse(snap["enabled"])
        self.assertIn("日期無交集", snap["quality"]["warnings"][0])

    def test_partial_per_or_pbr_rows_flagged_but_still_enabled(self) -> None:
        per_rows = [_per_row(f"2026-01-{d:02d}", per=20.0) for d in range(1, 21)]
        # blank out PER for a handful of days, PBR for a couple others
        for row in per_rows[:3]:
            row["PER"] = None
        for row in per_rows[5:7]:
            row["PBR"] = None
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0) for d in range(1, 21)]

        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)

        self.assertTrue(snap["enabled"])
        self.assertEqual(snap["quality"]["status"], "ok")
        self.assertIn("per", snap["quality"]["data_gap_fields"])
        self.assertIn("pbr", snap["quality"]["data_gap_fields"])
        # rows with missing PER simply have no bands/implied_eps, never guessed
        no_per_point = snap["points"][0]
        self.assertIsNone(no_per_point["implied_eps"])
        self.assertNotIn("bands", no_per_point)

    def test_insufficient_joined_coverage_returns_unsupported(self) -> None:
        # Only 3 overlapping dates — below the GAP_JOINED_ROWS floor.
        per_rows = [_per_row(f"2026-01-0{d}", per=20.0) for d in range(1, 4)]
        price_rows = [_price_row(f"2026-01-0{d}", close=1000.0) for d in range(1, 4)]

        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)

        self.assertFalse(snap["enabled"])
        self.assertEqual(snap["quality"]["status"], "unsupported")
        self.assertIn("過少", snap["quality"]["warnings"][0])

    def test_thin_but_above_gap_floor_is_partial_not_unsupported(self) -> None:
        # 10 rows: above GAP_JOINED_ROWS(5) but below MIN_JOINED_ROWS(20).
        per_rows = [_per_row(f"2026-01-{d:02d}", per=20.0) for d in range(1, 11)]
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0) for d in range(1, 11)]

        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)

        self.assertTrue(snap["enabled"])
        self.assertEqual(snap["quality"]["status"], "partial")
        self.assertEqual(len(snap["points"]), 10)

    def test_zero_per_or_pbr_treated_as_gap_not_division_by_zero(self) -> None:
        per_rows = [_per_row(f"2026-01-{d:02d}", per=20.0, pbr=6.0) for d in range(1, 21)]
        per_rows[0]["PER"] = 0
        per_rows[0]["PBR"] = 0
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0) for d in range(1, 21)]

        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)  # must not raise

        first = snap["points"][0]
        self.assertIsNone(first["implied_eps"])
        self.assertIsNone(first["implied_bvps"])

    def test_price_row_without_close_is_skipped(self) -> None:
        per_rows = [_per_row(f"2026-01-{d:02d}", per=20.0) for d in range(1, 21)]
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0) for d in range(1, 21)]
        price_rows[0]["close"] = None

        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)

        self.assertEqual(len(snap["points"]), 19)

    def test_never_emits_forbidden_fields(self) -> None:
        per_rows = [_per_row(f"2026-01-{d:02d}", per=20.0) for d in range(1, 21)]
        price_rows = [_price_row(f"2026-01-{d:02d}", close=1000.0) for d in range(1, 21)]
        snap = build_tw_valuation_river_snapshot("2330", per_rows, price_rows)

        blob = str(snap)
        for forbidden in ("target_price", "fair_value", "recommendation", "buy_signal", "sell_signal"):
            self.assertNotIn(forbidden, blob)


class BuildValuationRiverSnapshotUnsupportedTestCase(unittest.TestCase):
    def test_us_market_shape(self) -> None:
        snap = build_valuation_river_snapshot_unsupported("us", "AAPL", "no historical data")
        self.assertFalse(snap["enabled"])
        self.assertEqual(snap["market"], "us")
        self.assertEqual(snap["currency"], "USD")
        self.assertEqual(snap["quality"]["warnings"], ["no historical data"])
        self.assertEqual(snap["current"]["zone"], "unknown")

    def test_unknown_market_has_no_currency_guess(self) -> None:
        snap = build_valuation_river_snapshot_unsupported("unknown", "XX", "unsupported instrument")
        self.assertIsNone(snap["currency"])


if __name__ == "__main__":
    unittest.main()

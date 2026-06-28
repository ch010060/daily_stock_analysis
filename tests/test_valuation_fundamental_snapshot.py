# -*- coding: utf-8 -*-
"""
Phase 19B.2 — tests for the deterministic valuation/fundamental snapshot shapers.

These builders never fetch data; they only shape already-fetched raw dicts
into the fixed report-contract shape and compute `data_gap_fields`.
"""
from __future__ import annotations

import unittest

from src.services.valuation_fundamental_snapshot import (
    FUNDAMENTAL_FIELDS,
    VALUATION_FIELDS,
    build_fundamental_snapshot,
    build_valuation_snapshot,
)


class TestBuildValuationSnapshot(unittest.TestCase):
    def test_full_fields_no_gaps(self) -> None:
        raw = {
            "pe_ttm": 32.5,
            "pe_forward": 28.1,
            "pb": 48.2,
            "dividend_yield": 0.5,
            "market_cap": 3.2e12,
        }
        snapshot = build_valuation_snapshot(raw, source="yfinance", as_of="2026-06-25")
        for field in VALUATION_FIELDS:
            self.assertEqual(snapshot[field], raw[field])
        self.assertEqual(snapshot["source"], "yfinance")
        self.assertEqual(snapshot["as_of"], "2026-06-25")
        self.assertEqual(snapshot["data_gap_fields"], [])

    def test_missing_fields_become_gaps(self) -> None:
        raw = {"pe_ttm": 23.1, "pb": 6.3}
        snapshot = build_valuation_snapshot(raw, source="finmind")
        self.assertEqual(snapshot["pe_ttm"], 23.1)
        self.assertIsNone(snapshot["pe_forward"])
        self.assertEqual(
            set(snapshot["data_gap_fields"]),
            {"pe_forward", "dividend_yield", "market_cap"},
        )

    def test_empty_raw_all_fields_are_gaps(self) -> None:
        snapshot = build_valuation_snapshot({}, source="finmind")
        self.assertEqual(set(snapshot["data_gap_fields"]), set(VALUATION_FIELDS))
        for field in VALUATION_FIELDS:
            self.assertIsNone(snapshot[field])

    def test_as_of_falls_back_to_raw(self) -> None:
        snapshot = build_valuation_snapshot({"as_of": "2026-06-14"}, source="finmind")
        self.assertEqual(snapshot["as_of"], "2026-06-14")
        # "as_of" itself is not a valuation field, so it must not leak into the
        # flat snapshot keys or the gap list.
        self.assertNotIn("as_of", VALUATION_FIELDS)


class TestBuildFundamentalSnapshot(unittest.TestCase):
    def test_full_fields_no_gaps(self) -> None:
        raw = {
            "revenue_yoy": 45.0,
            "earnings_yoy": 19.3,
            "net_profit_yoy": 16.6,
            "roe": 141.5,
            "gross_margin": 47.9,
        }
        snapshot = build_fundamental_snapshot(raw, source="yfinance")
        for field in FUNDAMENTAL_FIELDS:
            self.assertEqual(snapshot[field], raw[field])
        self.assertEqual(snapshot["data_gap_fields"], [])

    def test_tw_only_provides_revenue_yoy(self) -> None:
        """TW market only sources revenue_yoy from TaiwanStockMonthRevenue;
        the other four fundamental fields are not part of the 19B.2 TW scope
        and must show up as explicit data gaps, not be silently omitted."""
        snapshot = build_fundamental_snapshot({"revenue_yoy": 45.0}, source="finmind")
        self.assertEqual(snapshot["revenue_yoy"], 45.0)
        self.assertEqual(
            set(snapshot["data_gap_fields"]),
            {"earnings_yoy", "net_profit_yoy", "roe", "gross_margin"},
        )


if __name__ == "__main__":
    unittest.main()

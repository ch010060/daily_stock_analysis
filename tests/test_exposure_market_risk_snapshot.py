# -*- coding: utf-8 -*-
"""
Phase 19B.3 — tests for the deterministic exposure/market-risk snapshot shapers.

These builders never fetch data; they only shape already-fetched raw dicts
into the fixed report-contract shape and compute `data_gap_fields`.
"""
from __future__ import annotations

import unittest

from src.services.exposure_market_risk_snapshot import (
    EXPOSURE_FIELDS,
    MARKET_RISK_FIELDS,
    TW_MARKET_RISK_GAP_REASON,
    build_exposure_snapshot,
    build_market_risk_snapshot,
    classify_vix_status,
)


class TestBuildExposureSnapshot(unittest.TestCase):
    def test_full_fields_no_gaps(self) -> None:
        raw = {
            "underlying_index": "S&P 500",
            "leverage_factor": 2,
            "is_leveraged": True,
            "is_inverse": False,
        }
        snapshot = build_exposure_snapshot(raw, source="yfinance", as_of="2026-06-25")
        for field in EXPOSURE_FIELDS:
            self.assertEqual(snapshot[field], raw[field])
        self.assertEqual(snapshot["source"], "yfinance")
        self.assertEqual(snapshot["as_of"], "2026-06-25")
        self.assertEqual(snapshot["data_gap_fields"], [])

    def test_empty_raw_all_fields_are_gaps(self) -> None:
        snapshot = build_exposure_snapshot({}, source=None)
        self.assertEqual(set(snapshot["data_gap_fields"]), set(EXPOSURE_FIELDS))
        self.assertIsNone(snapshot["source"])

    def test_gap_reason_is_optional(self) -> None:
        snapshot = build_exposure_snapshot({}, source=None)
        self.assertNotIn("gap_reason", snapshot)


class TestBuildMarketRiskSnapshot(unittest.TestCase):
    def test_full_fields_no_gaps(self) -> None:
        raw = {
            "vix_level": 18.2,
            "vix_status": "平穩",
            "spx_change_pct": 0.4,
            "risk_level": "low",
        }
        snapshot = build_market_risk_snapshot(raw, source="yfinance")
        for field in MARKET_RISK_FIELDS:
            self.assertEqual(snapshot[field], raw[field])
        self.assertEqual(snapshot["data_gap_fields"], [])

    def test_tw_gap_reason_set_when_no_fetch_attempted(self) -> None:
        """Phase 19B.3 security constraint: TW makes no fetch attempt this
        phase at all — source stays None and gap_reason explains why, distinct
        from "fetch attempted but field missing"."""
        snapshot = build_market_risk_snapshot({}, source=None, gap_reason=TW_MARKET_RISK_GAP_REASON)
        self.assertIsNone(snapshot["source"])
        self.assertEqual(snapshot["gap_reason"], TW_MARKET_RISK_GAP_REASON)
        self.assertEqual(set(snapshot["data_gap_fields"]), set(MARKET_RISK_FIELDS))


class TestClassifyVixStatus(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(classify_vix_status(None))

    def test_thresholds(self) -> None:
        self.assertEqual(classify_vix_status(35.0), "恐慌")
        self.assertEqual(classify_vix_status(30.0), "恐慌")
        self.assertEqual(classify_vix_status(25.0), "緊張")
        self.assertEqual(classify_vix_status(20.0), "緊張")
        self.assertEqual(classify_vix_status(15.0), "平穩")


if __name__ == "__main__":
    unittest.main()

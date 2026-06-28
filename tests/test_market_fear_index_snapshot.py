# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.services.market_fear_index_snapshot import (
    TW_VIXTWN_LABEL,
    US_VIX_LABEL,
    build_tw_vixtwn_gap_snapshot,
    build_tw_vixtwn_market_fear_snapshot,
    build_us_vix_market_fear_snapshot,
)


class TestMarketFearIndexSnapshot(unittest.TestCase):
    def test_us_vix_snapshot(self) -> None:
        snapshot = build_us_vix_market_fear_snapshot(18.41, as_of="2026-06-26")
        self.assertEqual(snapshot["market"], "us")
        self.assertEqual(snapshot["kind"], "vix")
        self.assertEqual(snapshot["label"], US_VIX_LABEL)
        self.assertEqual(snapshot["value"], 18.41)
        self.assertEqual(snapshot["as_of"], "2026-06-26")
        self.assertEqual(snapshot["source"], "yfinance_yahoo_quote")
        self.assertEqual(snapshot["status"], "unknown")
        self.assertIsNone(snapshot["data_gap_reason"])

    def test_tw_vixtwn_snapshot(self) -> None:
        quote = SimpleNamespace(value=44.27, as_of="2026-06-26", source="taifex")
        snapshot = build_tw_vixtwn_market_fear_snapshot(quote)
        self.assertEqual(snapshot["market"], "tw")
        self.assertEqual(snapshot["kind"], "vixtwn")
        self.assertEqual(snapshot["label"], TW_VIXTWN_LABEL)
        self.assertEqual(snapshot["value"], 44.27)
        self.assertEqual(snapshot["as_of"], "2026-06-26")
        self.assertEqual(snapshot["status"], "unknown")

    def test_tw_gap_does_not_fake_system_score(self) -> None:
        snapshot = build_tw_vixtwn_gap_snapshot("taifex_vixtwn_fetch_failed")
        self.assertEqual(snapshot["kind"], "vixtwn")
        self.assertIsNone(snapshot["value"])
        self.assertEqual(snapshot["data_gap_reason"], "taifex_vixtwn_fetch_failed")
        self.assertNotIn("sentiment_score", snapshot)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Tests for Phase 8D — TWStockAnalysisCollector and helpers.

All tests are offline (no live network calls).
MockFetcher injects fixture data deterministically.
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

# Force fixture mode so no live calls escape
os.environ.setdefault("DSA_FIXTURE_MODE", "true")

from src.finmind.tw_stock_analysis import (
    TWStockAnalysisCollector,
    TWStockAnalysisSnapshot,
    _compute_revenue_yoy,
    _extract_dividend,
    _extract_institutional_flow,
    _extract_kv_statements,
    _extract_margin,
    _extract_market_cap,
    _extract_monthly_revenue,
    _extract_price_volume,
    _extract_valuation,
    _generate_analysis_prompts,
    normalize_tw_symbol,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "finmind" / "stock_analysis"


def _load(name: str) -> List[Dict[str, Any]]:
    with open(FIXTURE_DIR / name) as f:
        return json.load(f)


def _ok(dataset: str, rows: List[Dict]) -> Dict[str, Any]:
    return {
        "ok": True,
        "dataset": dataset,
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "row_count": len(rows),
    }


def _unavail(dataset: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "dataset": dataset,
        "rows": [],
        "columns": [],
        "row_count": 0,
        "unavailable_reason": "fixture_unavailable",
    }


# ──────────────────────────────────────────────────────────────────────────────
# MockFetcher
# ──────────────────────────────────────────────────────────────────────────────

class MockFetcher:
    """Deterministic mock for FinMindDatasetFetcher."""

    def __init__(self, symbol: str = "2330", unavailable: Optional[List[str]] = None):
        self._symbol = symbol
        self._unavailable = set(unavailable or [])
        self._fixtures: Dict[str, List[Dict]] = {
            "TaiwanStockPrice": _load("price_2330.json"),
            "TaiwanStockPER": _load("per_2330.json"),
            "TaiwanStockMarketValue": _load("market_value_2330.json"),
            "TaiwanStockMonthRevenue": _load("month_revenue_2330.json"),
            "TaiwanStockFinancialStatements": _load("financial_statements_2330.json"),
            "TaiwanStockBalanceSheet": _load("balance_sheet_2330.json"),
            "TaiwanStockCashFlowsStatement": _load("cash_flows_2330.json"),
            "TaiwanStockDividend": _load("dividend_2330.json"),
            "TaiwanStockDividendResult": _load("dividend_result_2330.json"),
            "TaiwanStockInstitutionalInvestorsBuySell": _load("institutional_2330.json"),
            "TaiwanStockMarginPurchaseShortSale": _load("margin_2330.json"),
        }

    def fetch(self, dataset: str, *, data_id: str, start_date: str, end_date: str, **kwargs) -> Dict:
        if dataset in self._unavailable:
            return _unavail(dataset)
        rows = self._fixtures.get(dataset, [])
        return _ok(dataset, rows)


class MockLatestInfoCollector:
    """Minimal mock for LatestInfoCollector."""

    def collect_stock_latest(self, symbols, start_date, end_date):
        return {
            "ok": True,
            "source": "finmind",
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "events": [],
            "event_count": 0,
            "missing": [],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Tests: symbol normalization
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizeTWSymbol(unittest.TestCase):

    def test_bare_4digit(self):
        stock_id, err = normalize_tw_symbol("2330")
        self.assertIsNone(err)
        self.assertEqual(stock_id, "2330")

    def test_tw_prefix(self):
        stock_id, err = normalize_tw_symbol("TW:2330")
        self.assertIsNone(err)
        self.assertEqual(stock_id, "2330")

    def test_tw_suffix(self):
        stock_id, err = normalize_tw_symbol("2330.TW")
        self.assertIsNone(err)
        self.assertEqual(stock_id, "2330")

    def test_tw_etf_0050(self):
        stock_id, err = normalize_tw_symbol("0050")
        self.assertIsNone(err)
        self.assertEqual(stock_id, "0050")

    def test_tw_etf_00631L(self):
        stock_id, err = normalize_tw_symbol("00631L")
        self.assertIsNone(err)
        self.assertEqual(stock_id, "00631L")

    def test_reject_us_prefix(self):
        stock_id, err = normalize_tw_symbol("US:AAPL")
        self.assertIsNone(stock_id)
        self.assertIn("non-TW", err)

    def test_reject_hk_prefix(self):
        stock_id, err = normalize_tw_symbol("HK:0700")
        self.assertIsNone(stock_id)
        self.assertIn("non-TW", err)

    def test_reject_pure_alpha(self):
        stock_id, err = normalize_tw_symbol("AAPL")
        self.assertIsNone(stock_id)
        self.assertIn("pure-alpha", err)

    def test_reject_cn_6digit(self):
        stock_id, err = normalize_tw_symbol("600519")
        self.assertIsNone(stock_id)
        self.assertIn("CN A-share", err)

    def test_reject_empty(self):
        stock_id, err = normalize_tw_symbol("")
        self.assertIsNone(stock_id)
        self.assertIsNotNone(err)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: section extraction helpers
# ──────────────────────────────────────────────────────────────────────────────

class TestExtractPriceVolume(unittest.TestCase):

    def test_latest_row(self):
        rows = _load("price_2330.json")
        result = _extract_price_volume({"rows": rows})
        self.assertTrue(result["available"])
        self.assertEqual(result["latest_date"], "2026-06-13")
        self.assertEqual(result["close"], 2395)
        self.assertEqual(result["volume"], 55000000)

    def test_empty(self):
        result = _extract_price_volume({"rows": []})
        self.assertFalse(result["available"])


class TestExtractValuation(unittest.TestCase):

    def test_latest_row(self):
        rows = _load("per_2330.json")
        result = _extract_valuation({"rows": rows})
        self.assertTrue(result["available"])
        self.assertEqual(result["latest_date"], "2026-06-13")
        self.assertAlmostEqual(result["PER"], 23.1)

    def test_empty(self):
        result = _extract_valuation({"rows": []})
        self.assertFalse(result["available"])


class TestComputeRevenueYoY(unittest.TestCase):

    def test_yoy_with_13_rows(self):
        rows = _load("month_revenue_2330.json")
        self.assertEqual(len(rows), 13)
        yoy = _compute_revenue_yoy(rows)
        # current=290B prev_year=200B → +45%
        self.assertIsNotNone(yoy)
        self.assertAlmostEqual(yoy, 45.0, places=0)

    def test_yoy_insufficient_rows(self):
        rows = _load("month_revenue_2330.json")[:5]
        yoy = _compute_revenue_yoy(rows)
        self.assertIsNone(yoy)


class TestExtractKvStatements(unittest.TestCase):

    def test_fundamentals_latest_date(self):
        rows = _load("financial_statements_2330.json")
        result = _extract_kv_statements({"rows": rows}, "fundamentals")
        self.assertTrue(result["available"])
        self.assertEqual(result["latest_date"], "2026-03-31")
        self.assertIn("Revenue", result["kv"])
        self.assertIn("EPS", result["kv"])

    def test_empty(self):
        result = _extract_kv_statements({"rows": []}, "fundamentals")
        self.assertFalse(result["available"])


class TestExtractDividend(unittest.TestCase):

    def test_with_both(self):
        div_rows = _load("dividend_2330.json")
        divr_rows = _load("dividend_result_2330.json")
        result = _extract_dividend({"rows": div_rows}, {"rows": divr_rows})
        self.assertTrue(result["available"])
        self.assertTrue(result["declared"]["available"])
        self.assertAlmostEqual(result["declared"]["cash_dividend"], 4.5)
        self.assertTrue(result["ex_dividend"]["available"])

    def test_empty_both(self):
        result = _extract_dividend({"rows": []}, {"rows": []})
        self.assertFalse(result["available"])


class TestExtractInstitutional(unittest.TestCase):

    def test_foreign_net(self):
        rows = _load("institutional_2330.json")
        result = _extract_institutional_flow({"rows": rows})
        self.assertTrue(result["available"])
        self.assertEqual(result["latest_date"], "2026-06-13")
        # foreign net = 38B - 20B = 18B
        self.assertEqual(result["foreign_net"], 18_000_000_000)
        self.assertIn("Foreign_Investor", result["by_institution"])

    def test_empty(self):
        result = _extract_institutional_flow({"rows": []})
        self.assertFalse(result["available"])


class TestExtractMargin(unittest.TestCase):

    def test_latest_row(self):
        rows = _load("margin_2330.json")
        result = _extract_margin({"rows": rows})
        self.assertTrue(result["available"])
        self.assertEqual(result["latest_date"], "2026-06-13")
        self.assertEqual(result["margin_balance"], 922000)

    def test_empty(self):
        result = _extract_margin({"rows": []})
        self.assertFalse(result["available"])


# ──────────────────────────────────────────────────────────────────────────────
# Tests: TWStockAnalysisCollector
# ──────────────────────────────────────────────────────────────────────────────

class TestTWStockAnalysisCollector(unittest.TestCase):

    def _make_collector(self, unavailable=None):
        fetcher = MockFetcher(unavailable=unavailable)
        li = MockLatestInfoCollector()
        return TWStockAnalysisCollector(fetcher=fetcher, latest_info_collector=li)

    def test_snapshot_ok_full(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertIsInstance(snap, TWStockAnalysisSnapshot)
        self.assertEqual(snap.stock_id, "2330")
        self.assertTrue(snap.ok)
        self.assertIn("price_volume", snap.sections)
        self.assertIn("valuation", snap.sections)
        self.assertIn("monthly_revenue", snap.sections)
        self.assertIn("fundamentals", snap.sections)
        self.assertIn("institutional_flow", snap.sections)

    def test_snapshot_tw_prefix_accepted(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="TW:2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertEqual(snap.stock_id, "2330")
        self.assertTrue(snap.ok)

    def test_snapshot_tw_suffix_accepted(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330.TW", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertEqual(snap.stock_id, "2330")

    def test_snapshot_invalid_symbol(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="US:AAPL", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertFalse(snap.ok)
        self.assertIsNone(snap.stock_id)
        self.assertTrue(any("normalization" in w for w in snap.warnings))

    def test_snapshot_cn_symbol_rejected(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="600519", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertFalse(snap.ok)
        self.assertIsNone(snap.stock_id)

    def test_missing_optional_section(self):
        collector = self._make_collector(unavailable=["TaiwanStockMarketValue"])
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        # market_cap optional — snapshot still ok
        self.assertTrue(snap.ok)
        self.assertIn("market_cap", snap.missing)

    def test_missing_required_section(self):
        collector = self._make_collector(unavailable=["TaiwanStockPrice"])
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertFalse(snap.ok)
        self.assertIn("price_volume", snap.missing)

    def test_to_dict_shape(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        d = snap.to_dict()
        for key in ("ok", "symbol", "stock_id", "start_date", "end_date",
                    "sections", "data_quality", "sources", "missing",
                    "warnings", "recommended_prompts"):
            self.assertIn(key, d)

    def test_prompts_generated(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertIsInstance(snap.recommended_prompts, list)
        self.assertGreater(len(snap.recommended_prompts), 0)
        for p in snap.recommended_prompts:
            self.assertNotIn("買進", p)
            self.assertNotIn("賣出", p)
            self.assertNotIn("buy", p.lower())
            self.assertNotIn("sell", p.lower())

    def test_data_quality_shape(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        dq = snap.data_quality
        self.assertIn("valid_symbol", dq)
        self.assertIn("required_ok", dq)
        self.assertIn("partial", dq)
        self.assertIn("sections_ok", dq)
        self.assertIn("sections_missing", dq)
        self.assertTrue(dq["valid_symbol"])

    def test_sources_contains_finmind(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        self.assertIn("finmind", snap.sources)

    def test_yoy_computed_in_revenue(self):
        collector = self._make_collector()
        snap = collector.collect_stock_analysis_snapshot(
            symbol="2330", start_date="2025-06-01", end_date="2026-06-14"
        )
        rev = snap.sections["monthly_revenue"]
        self.assertTrue(rev["yoy_available"])
        self.assertAlmostEqual(rev["yoy_pct"], 45.0, places=0)


if __name__ == "__main__":
    unittest.main()

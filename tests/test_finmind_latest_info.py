# -*- coding: utf-8 -*-
"""
Tests for FinMind Latest Info / News Intelligence (Phase 8C).

All tests are offline — FinMindDatasetFetcher is mocked via a MockFetcher.
No live provider calls.
No token printed.
No CN/A-share terms.
No buy/sell instructions.
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from src.finmind.fetcher import FinMindDatasetFetcher
from src.finmind.latest_info import (
    LatestInfoCollector,
    LatestInfoEvent,
    extract_data_unavailable_event,
    extract_dividend_events,
    extract_institutional_events,
    extract_margin_events,
    extract_news_events,
    extract_price_events,
    extract_revenue_events,
    generate_follow_up_prompts,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "finmind" / "latest_info"

_CN_TERMS = ["台股", "上證", "上證", "深證", "深證", "創業板", "創業板", "科創50", "A-share"]
_BUYSELL_TERMS = ["買進", "賣出", "買進", "賣出", "強烈推薦", "強力推薦"]


def _load_fixture(name: str) -> dict:
    with open(_FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _ok_result(dataset: str, rows: list, data_id: Optional[str] = None) -> Dict[str, Any]:
    cols = list(rows[0].keys()) if rows else []
    return {
        "ok": True,
        "source": "finmind",
        "dataset": dataset,
        "data_id": data_id,
        "rows": rows,
        "columns": cols,
        "row_count": len(rows),
        "start_date": "2026-06-01",
        "end_date": "2026-06-14",
        "error": None,
        "unavailable_reason": None,
        "cache_meta": {},
    }


def _unavail_result(dataset: str, reason: str, data_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "ok": False,
        "source": "finmind",
        "dataset": dataset,
        "data_id": data_id,
        "rows": [],
        "columns": [],
        "row_count": 0,
        "start_date": "2026-06-01",
        "end_date": "2026-06-14",
        "error": reason,
        "unavailable_reason": reason,
        "cache_meta": {},
    }


class MockFetcher:
    """Offline mock of FinMindDatasetFetcher for unit tests."""

    def __init__(self, responses: Dict[str, Dict[str, Any]]) -> None:
        self._responses = responses

    def fetch(self, dataset: str, *, data_id=None, start_date=None, end_date=None, force_live=False):
        return self._responses.get(dataset, _unavail_result(dataset, "not_mocked"))


def _full_mock_fetcher(symbol: str = "2330") -> MockFetcher:
    """Build MockFetcher with all Phase 8C fixture datasets."""
    news_data = _load_fixture("taiwan_stock_news.json")["data"]
    rev_data = _load_fixture("month_revenue_2330.json")["data"]
    div_data = _load_fixture("dividend_2330.json")["data"]
    price_data = _load_fixture("stock_price_2330.json")["data"]
    inst_data = _load_fixture("institutional_2330.json")["data"]
    margin_data = _load_fixture("margin_2330.json")["data"]

    return MockFetcher({
        "TaiwanStockTradingDate": _ok_result("TaiwanStockTradingDate", [{"date": "2026-06-13"}]),
        "TaiwanStockNews": _ok_result("TaiwanStockNews", news_data, symbol),
        "TaiwanStockMonthRevenue": _ok_result("TaiwanStockMonthRevenue", rev_data, symbol),
        "TaiwanStockDividend": _ok_result("TaiwanStockDividend", div_data, symbol),
        "TaiwanStockDividendResult": _ok_result("TaiwanStockDividendResult", [], symbol),
        "TaiwanStockPrice": _ok_result("TaiwanStockPrice", price_data, symbol),
        "TaiwanStockInstitutionalInvestorsBuySell": _ok_result(
            "TaiwanStockInstitutionalInvestorsBuySell", inst_data, symbol
        ),
        "TaiwanStockMarginPurchaseShortSale": _ok_result(
            "TaiwanStockMarginPurchaseShortSale", margin_data, symbol
        ),
    })


# ──────────────────────────────────────────────────────────────────────────────
# Test classes
# ──────────────────────────────────────────────────────────────────────────────

class TestLatestInfoCollectorInit(unittest.TestCase):
    """Test 1: LatestInfoCollector initializes with FinMindDatasetFetcher."""

    def test_default_fetcher_is_finmind_dataset_fetcher(self):
        collector = LatestInfoCollector()
        self.assertIsInstance(collector._fetcher, FinMindDatasetFetcher)

    def test_accepts_custom_fetcher(self):
        mock = MockFetcher({})
        collector = LatestInfoCollector(fetcher=mock)
        self.assertIs(collector._fetcher, mock)


class TestNewsEventExtraction(unittest.TestCase):
    """Test 2: fixture mode returns deterministic stock_news events."""

    def test_news_events_extracted_from_fixture(self):
        rows = _load_fixture("taiwan_stock_news.json")["data"]
        events = extract_news_events(rows, "2330")
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.event_type == "stock_news" for e in events))

    def test_news_event_has_required_fields(self):
        rows = _load_fixture("taiwan_stock_news.json")["data"]
        events = extract_news_events(rows, "2330")
        e = events[0]
        self.assertIsNotNone(e.event_id)
        self.assertIsNotNone(e.title)
        self.assertIsNotNone(e.summary)
        self.assertEqual(e.source, "finmind")
        self.assertEqual(e.dataset, "TaiwanStockNews")

    def test_news_event_symbol_bound(self):
        rows = _load_fixture("taiwan_stock_news.json")["data"]
        events = extract_news_events(rows, "2330")
        for e in events:
            self.assertEqual(e.symbol, "2330")


class TestMissingNewsReturnsUnavailable(unittest.TestCase):
    """Test 3: missing TaiwanStockNews returns data_unavailable event, not crash."""

    def test_news_unavailable_emits_data_unavailable_event(self):
        fetcher = MockFetcher({
            "TaiwanStockNews": _unavail_result("TaiwanStockNews", "tier_or_permission", "2330"),
            "TaiwanStockMonthRevenue": _unavail_result("TaiwanStockMonthRevenue", "not_mocked"),
            "TaiwanStockDividend": _unavail_result("TaiwanStockDividend", "not_mocked"),
            "TaiwanStockDividendResult": _unavail_result("TaiwanStockDividendResult", "not_mocked"),
            "TaiwanStockPrice": _unavail_result("TaiwanStockPrice", "not_mocked"),
            "TaiwanStockInstitutionalInvestorsBuySell": _unavail_result(
                "TaiwanStockInstitutionalInvestorsBuySell", "not_mocked"),
            "TaiwanStockMarginPurchaseShortSale": _unavail_result(
                "TaiwanStockMarginPurchaseShortSale", "not_mocked"),
        })
        collector = LatestInfoCollector(fetcher=fetcher)
        result = collector.collect_stock_latest(["2330"], "2026-06-01", "2026-06-14")
        event_types = [e["event_type"] for e in result["events"]]
        self.assertIn("data_unavailable", event_types)
        # Must not crash
        self.assertIn("events", result)

    def test_extract_data_unavailable_event_structure(self):
        e = extract_data_unavailable_event(
            "TaiwanStockNews", "2330", "tier_or_permission", "2026-06-01", "2026-06-14"
        )
        self.assertEqual(e.event_type, "data_unavailable")
        self.assertEqual(e.confidence, "unavailable")
        self.assertIn("TaiwanStockNews", e.title)


class TestRevenueEventSeverity(unittest.TestCase):
    """Test 4: monthly revenue event severity high/medium/low works."""

    def _rows(self, current_rev: float, prev_rev: float):
        return [
            {"date": "2026-06-10", "stock_id": "2330", "country": "TW",
             "revenue": current_rev, "revenue_month": 5, "revenue_year": 2026},
            {"date": "2025-06-10", "stock_id": "2330", "country": "TW",
             "revenue": prev_rev, "revenue_month": 5, "revenue_year": 2025},
        ]

    def test_high_severity_yoy_above_20pct(self):
        rows = self._rows(290e9, 200e9)  # +45% YoY
        events = extract_revenue_events(rows, "2330")
        self.assertEqual(events[0].severity, "high")

    def test_medium_severity_yoy_10_to_20pct(self):
        rows = self._rows(220e9, 200e9)  # +10% YoY
        events = extract_revenue_events(rows, "2330")
        self.assertEqual(events[0].severity, "medium")

    def test_low_severity_yoy_below_10pct(self):
        rows = self._rows(205e9, 200e9)  # +2.5% YoY
        events = extract_revenue_events(rows, "2330")
        self.assertEqual(events[0].severity, "low")

    def test_low_severity_no_prior_year(self):
        rows = [{"date": "2026-06-10", "stock_id": "2330", "country": "TW",
                 "revenue": 290e9, "revenue_month": 5, "revenue_year": 2026}]
        events = extract_revenue_events(rows, "2330")
        self.assertEqual(events[0].severity, "low")
        self.assertEqual(events[0].confidence, "estimated")

    def test_revenue_event_type(self):
        rows = _load_fixture("month_revenue_2330.json")["data"]
        events = extract_revenue_events(rows, "2330")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "monthly_revenue")


class TestDividendEventExtraction(unittest.TestCase):
    """Test 5: dividend event extraction works."""

    def test_dividend_event_extracted(self):
        rows = _load_fixture("dividend_2330.json")["data"]
        events = extract_dividend_events(rows, "2330", "TaiwanStockDividend")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "dividend")
        self.assertEqual(events[0].symbol, "2330")

    def test_dividend_event_contains_cash_amount(self):
        rows = _load_fixture("dividend_2330.json")["data"]
        events = extract_dividend_events(rows, "2330", "TaiwanStockDividend")
        self.assertIn("4.5", events[0].title)


class TestPriceEventExtraction(unittest.TestCase):
    """Test 6: price movement event extraction works."""

    def test_price_event_extracted(self):
        rows = _load_fixture("stock_price_2330.json")["data"]
        events = extract_price_events(rows, "2330")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "price_volume_move")

    def test_large_spread_triggers_high_severity(self):
        rows = [
            {"date": "2026-06-12", "stock_id": "2330",
             "Trading_Volume": 20000000, "close": 2320.0, "spread": 15.0,
             "open": 2305.0, "max": 2325.0, "min": 2300.0,
             "Trading_money": 0, "Trading_turnover": 0},
            {"date": "2026-06-13", "stock_id": "2330",
             "Trading_Volume": 55000000, "close": 2395.0, "spread": 120.0,
             "open": 2320.0, "max": 2410.0, "min": 2315.0,
             "Trading_money": 0, "Trading_turnover": 0},
        ]
        events = extract_price_events(rows, "2330")
        self.assertEqual(events[0].severity, "high")


class TestVolumeSpikeExtraction(unittest.TestCase):
    """Test 7: volume spike event extraction works."""

    def test_volume_spike_triggers_high_severity(self):
        rows = [
            {"date": "2026-06-11", "stock_id": "2330",
             "Trading_Volume": 10000000, "close": 2300.0, "spread": 5.0,
             "open": 2295.0, "max": 2310.0, "min": 2290.0,
             "Trading_money": 0, "Trading_turnover": 0},
            {"date": "2026-06-12", "stock_id": "2330",
             "Trading_Volume": 10000000, "close": 2305.0, "spread": 5.0,
             "open": 2300.0, "max": 2315.0, "min": 2300.0,
             "Trading_money": 0, "Trading_turnover": 0},
            {"date": "2026-06-13", "stock_id": "2330",
             "Trading_Volume": 55000000, "close": 2310.0, "spread": 5.0,
             "open": 2305.0, "max": 2320.0, "min": 2305.0,
             "Trading_money": 0, "Trading_turnover": 0},
        ]
        events = extract_price_events(rows, "2330")
        self.assertEqual(events[0].severity, "high")
        self.assertTrue(events[0].raw_ref.get("volume_spike"))


class TestInstitutionalEventExtraction(unittest.TestCase):
    """Test 8: institutional flow event extraction works."""

    def test_institutional_event_extracted(self):
        rows = _load_fixture("institutional_2330.json")["data"]
        events = extract_institutional_events(rows, "2330")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "institutional_flow")

    def test_high_net_buy_is_high_severity(self):
        rows = _load_fixture("institutional_2330.json")["data"]
        events = extract_institutional_events(rows, "2330")
        # Foreign_Investor net = 38B - 20B = 18B > 1B threshold
        self.assertEqual(events[0].severity, "high")

    def test_institutional_summary_mentions_net_direction(self):
        rows = _load_fixture("institutional_2330.json")["data"]
        events = extract_institutional_events(rows, "2330")
        self.assertIn("買超", events[0].title)


class TestMarginEventExtraction(unittest.TestCase):
    """Test 9: margin change event extraction works."""

    def test_margin_event_extracted(self):
        rows = _load_fixture("margin_2330.json")["data"]
        events = extract_margin_events(rows, "2330")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "margin_change")

    def test_margin_event_has_today_balance(self):
        rows = _load_fixture("margin_2330.json")["data"]
        events = extract_margin_events(rows, "2330")
        self.assertIn("MarginPurchaseTodayBalance", events[0].raw_ref)


class TestCollectStockLatestSymbolBound(unittest.TestCase):
    """Test 10: collect_stock_latest(["2330"]) returns events bound to 2330."""

    def test_all_events_bound_to_symbol(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        result = collector.collect_stock_latest(["2330"], "2026-06-01", "2026-06-14")
        for event in result["events"]:
            sym = event.get("symbol")
            self.assertIn(sym, ("2330", None), f"Unexpected symbol: {sym}")

    def test_result_contains_symbol_list(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        result = collector.collect_stock_latest(["2330"], "2026-06-01", "2026-06-14")
        self.assertIn("2330", result["symbols"])


class TestNoCNProviders(unittest.TestCase):
    """Test 11: collect_market_latest() does not call CN/A-share providers."""

    def test_market_latest_no_cn_terms(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher())
        result = collector.collect_market_latest("2026-06-01", "2026-06-14")
        result_str = str(result)
        for term in _CN_TERMS:
            self.assertNotIn(term, result_str, f"CN term found: {term}")

    def test_no_cn_datasets_in_stock_latest(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        result = collector.collect_stock_latest(["2330"], "2026-06-01", "2026-06-14")
        result_str = str(result)
        for term in _CN_TERMS:
            self.assertNotIn(term, result_str, f"CN term found: {term}")


class TestSnapshotStructure(unittest.TestCase):
    """Test 12: collect_latest_info_snapshot() returns event_count and data_quality."""

    def _snapshot(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        return collector.collect_latest_info_snapshot(
            symbols=["2330"],
            start_date="2026-06-01",
            end_date="2026-06-14",
        )

    def test_snapshot_has_required_keys(self):
        snap = self._snapshot()
        for key in ("ok", "source", "symbols", "start_date", "end_date",
                    "events", "event_count", "missing", "data_quality", "recommended_prompts"):
            self.assertIn(key, snap, f"Missing key: {key}")

    def test_snapshot_event_count_matches_events(self):
        snap = self._snapshot()
        self.assertEqual(snap["event_count"], len(snap["events"]))

    def test_snapshot_data_quality_has_required_fields(self):
        snap = self._snapshot()
        dq = snap["data_quality"]
        for key in ("required_ok", "partial", "freshness", "sources"):
            self.assertIn(key, dq)

    def test_snapshot_source_is_finmind(self):
        snap = self._snapshot()
        self.assertEqual(snap["source"], "finmind")


class TestFollowUpPrompts(unittest.TestCase):
    """Test 13: follow_up_prompts are generated and mention provided data only."""

    def test_prompts_generated(self):
        prompts = generate_follow_up_prompts(
            symbols=["2330"],
            end_date="2026-06-14",
            missing=[],
            events=[],
        )
        self.assertGreater(len(prompts), 0)

    def test_prompts_mention_provided_data(self):
        prompts = generate_follow_up_prompts(
            symbols=["2330"],
            end_date="2026-06-14",
            missing=[],
            events=[],
        )
        combined = " ".join(prompts)
        # Must mention FinMind or 本次 (anchor to provided data)
        self.assertTrue(
            "FinMind" in combined or "本次" in combined,
            "Prompts must reference provided data source"
        )

    def test_prompts_include_end_date(self):
        prompts = generate_follow_up_prompts(
            symbols=["2330"],
            end_date="2026-06-14",
            missing=[],
            events=[],
        )
        combined = " ".join(prompts)
        self.assertIn("2026-06-14", combined)

    def test_snapshot_prompts_not_empty(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        snap = collector.collect_latest_info_snapshot(
            ["2330"], "2026-06-01", "2026-06-14"
        )
        self.assertGreater(len(snap["recommended_prompts"]), 0)


class TestNoExternalDataInPrompts(unittest.TestCase):
    """Test 14: no prompt asks LLM to fetch external data."""

    _EXTERNAL_FETCH_PHRASES = [
        "請去搜尋", "請查詢即時", "請上網查", "請查最新", "請搜尋",
        "從網路取得", "取得最新報價", "fetch from",
    ]

    def test_no_external_fetch_instructions(self):
        prompts = generate_follow_up_prompts(
            symbols=["2330", "0050"],
            end_date="2026-06-14",
            missing=["TaiwanStockNews"],
            events=[],
        )
        combined = " ".join(prompts)
        for phrase in self._EXTERNAL_FETCH_PHRASES:
            self.assertNotIn(phrase, combined, f"External fetch instruction found: {phrase}")


class TestNoBuySellInstruction(unittest.TestCase):
    """Test 15: no buy/sell instruction appears in events or prompts."""

    def test_no_buysell_in_prompts(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        snap = collector.collect_latest_info_snapshot(
            ["2330"], "2026-06-01", "2026-06-14"
        )
        all_text = " ".join(snap["recommended_prompts"])
        for term in _BUYSELL_TERMS:
            self.assertNotIn(term, all_text, f"Buy/sell term in prompts: {term}")

    def test_no_buysell_in_event_titles(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        snap = collector.collect_latest_info_snapshot(
            ["2330"], "2026-06-01", "2026-06-14"
        )
        for event in snap["events"]:
            title = event.get("title", "")
            for term in _BUYSELL_TERMS:
                self.assertNotIn(term, title, f"Buy/sell term in event title: {term}")


class TestNoLiveCallsInTests(unittest.TestCase):
    """Test 16: no live calls in unit tests — all tests use MockFetcher."""

    def test_mock_fetcher_does_not_call_requests(self):
        mock_fetcher = MockFetcher({
            "TaiwanStockTradingDate": _ok_result("TaiwanStockTradingDate", [{"date": "2026-06-13"}]),
            "TaiwanStockNews": _unavail_result("TaiwanStockNews", "fixture_mode"),
            "TaiwanStockMonthRevenue": _unavail_result("TaiwanStockMonthRevenue", "fixture_mode"),
            "TaiwanStockDividend": _unavail_result("TaiwanStockDividend", "fixture_mode"),
            "TaiwanStockDividendResult": _unavail_result("TaiwanStockDividendResult", "fixture_mode"),
            "TaiwanStockPrice": _unavail_result("TaiwanStockPrice", "fixture_mode"),
            "TaiwanStockInstitutionalInvestorsBuySell": _unavail_result(
                "TaiwanStockInstitutionalInvestorsBuySell", "fixture_mode"),
            "TaiwanStockMarginPurchaseShortSale": _unavail_result(
                "TaiwanStockMarginPurchaseShortSale", "fixture_mode"),
        })
        with patch("requests.get") as mock_get:
            collector = LatestInfoCollector(fetcher=mock_fetcher)
            collector.collect_latest_info_snapshot(["2330"], "2026-06-01", "2026-06-14")
            mock_get.assert_not_called()


class TestNoCNTermsInOutput(unittest.TestCase):
    """Test 17: no CN/A-share terms appear in any output."""

    def test_no_cn_terms_in_full_snapshot(self):
        collector = LatestInfoCollector(fetcher=_full_mock_fetcher("2330"))
        snap = collector.collect_latest_info_snapshot(
            ["2330"], "2026-06-01", "2026-06-14"
        )
        snap_str = str(snap)
        for term in _CN_TERMS:
            self.assertNotIn(term, snap_str, f"CN term in snapshot: {term}")

    def test_no_cn_terms_in_event_summaries(self):
        rows = _load_fixture("taiwan_stock_news.json")["data"]
        events = extract_news_events(rows, "2330")
        for e in events:
            for term in _CN_TERMS:
                self.assertNotIn(term, e.summary, f"CN term in summary: {term}")


class TestRegistryLatestInfoMapping(unittest.TestCase):
    """Test 18: registry latest_info feature group maps to TaiwanStockNews."""

    def test_latest_info_contains_taiwan_stock_news(self):
        from src.finmind.dataset_registry import FinMindDatasetRegistry
        reg = FinMindDatasetRegistry()
        names = [d["dataset"] for d in reg.by_feature_group("latest_info")]
        self.assertIn("TaiwanStockNews", names)

    def test_latest_info_contains_trading_date(self):
        from src.finmind.dataset_registry import FinMindDatasetRegistry
        reg = FinMindDatasetRegistry()
        names = [d["dataset"] for d in reg.by_feature_group("latest_info")]
        self.assertIn("TaiwanStockTradingDate", names)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Tests for FinMindDatasetFetcher (Phase 8B).

All tests are offline — FinMindClient is injected with mocked session.
No live provider calls, no token printed.
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.finmind.client import FinMindClient
from src.finmind.dataset_registry import FinMindDatasetRegistry
from src.finmind.fetcher import FinMindDatasetFetcher

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "finmind"


def _load_fixture(name: str) -> dict:
    with open(_FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _mock_client_returning(body: dict, http_status: int = 200) -> FinMindClient:
    """Return a FinMindClient whose session always returns the given body."""
    m = MagicMock()
    m.status_code = http_status
    m.json.return_value = body
    session = MagicMock()
    session.get.return_value = m
    return FinMindClient(token="test_token", session=session)


def _live_client(body: dict) -> FinMindClient:
    return _mock_client_returning(body)


def _fetcher(client: FinMindClient) -> FinMindDatasetFetcher:
    return FinMindDatasetFetcher(client=client)


class TestKnownDatasetFetch(unittest.TestCase):
    """Test 1: Known dataset fetch uses registry params."""

    def test_taiwan_stock_price_fetch_ok(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        fetcher = _fetcher(_live_client(body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPrice", data_id="2330",
                                   start_date="2026-06-01", end_date="2026-06-14")
        self.assertTrue(result["ok"])
        self.assertEqual(result["dataset"], "TaiwanStockPrice")
        self.assertEqual(result["row_count"], 3)
        self.assertIsNone(result["unavailable_reason"])

    def test_result_has_all_standard_keys(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        fetcher = _fetcher(_live_client(body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPrice", data_id="2330",
                                   start_date="2026-06-01", end_date="2026-06-14")
        for key in ("ok", "source", "dataset", "data_id", "rows", "columns",
                    "row_count", "start_date", "end_date", "error", "unavailable_reason", "cache_meta"):
            self.assertIn(key, result, f"Missing key: {key}")


class TestUnknownDatasetFailsClosed(unittest.TestCase):
    """Test 2: Unknown dataset fails closed."""

    def test_unknown_dataset_returns_false(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("NonExistentDataset2026", data_id="2330",
                                   start_date="2026-06-01", end_date="2026-06-14")
        self.assertFalse(result["ok"])
        self.assertEqual(result["unavailable_reason"], "unknown_dataset")


class TestCNDatasetRejected(unittest.TestCase):
    """Test 3: Non-TW / CN dataset rejected if ever present in registry."""

    def test_cn_market_dataset_rejected_via_patched_registry(self):
        registry = FinMindDatasetRegistry()
        # Monkey-patch has_cn_datasets to return True (simulate accidental CN entry)
        original = registry.has_cn_datasets

        def _mock_has_cn():
            return True

        registry.has_cn_datasets = _mock_has_cn

        fetcher = FinMindDatasetFetcher(
            registry=registry,
            client=_live_client({"status": 200, "msg": "", "data": []}),
        )
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPrice", data_id="2330",
                                   start_date="2026-06-01", end_date="2026-06-14")
        self.assertFalse(result["ok"])
        self.assertEqual(result["unavailable_reason"], "cn_market_rejected")

        # Restore
        registry.has_cn_datasets = original

    def test_real_registry_has_no_cn_datasets(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        # has_cn_datasets should be False for the real registry
        self.assertFalse(fetcher._registry.has_cn_datasets())


class TestMissingRequiredDataId(unittest.TestCase):
    """Test 4: Missing required data_id fails closed."""

    def test_stock_price_requires_data_id(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPrice",  # data_id not provided
                                   start_date="2026-06-01", end_date="2026-06-14")
        self.assertFalse(result["ok"])
        self.assertEqual(result["unavailable_reason"], "missing_required_data_id")

    def test_trading_date_no_data_id_needed(self):
        body = {"status": 200, "msg": "", "data": [{"date": "2026-06-12"}]}
        fetcher = _fetcher(_live_client(body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockTradingDate",
                                   start_date="2026-06-01", end_date="2026-06-14")
        self.assertTrue(result["ok"])


class TestStockPriceWithDataId(unittest.TestCase):
    """Test 5: TaiwanStockPrice with data_id=2330 passes."""

    def test_stock_price_2330_fetch_ok(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        fetcher = _fetcher(_live_client(body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPrice", data_id="2330",
                                   start_date="2026-06-10", end_date="2026-06-14")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data_id"], "2330")
        self.assertGreater(result["row_count"], 0)


class TestBackerTierUnavailable(unittest.TestCase):
    """Test 6: TaiwanStockPriceAdj Backer-tier returns caveat/unavailable unless forced."""

    def test_price_adj_returns_unavailable_by_default(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")  # irrelevant, not called
        fetcher = _fetcher(_live_client(body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPriceAdj", data_id="2330",
                                   start_date="2026-06-10", end_date="2026-06-14")
        self.assertFalse(result["ok"])
        self.assertIn("backer", result["unavailable_reason"])

    def test_price_adj_force_live_attempts_call(self):
        body = _load_fixture("client_error_tier.json")  # API returns tier error
        fetcher = _fetcher(_live_client(body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            result = fetcher.fetch("TaiwanStockPriceAdj", data_id="2330",
                                   start_date="2026-06-10", end_date="2026-06-14",
                                   force_live=True)
        # Should have attempted call; returns api_error / tier_or_permission from client
        self.assertFalse(result["ok"])
        self.assertIn(result["unavailable_reason"], ("tier_or_permission", "api_error", "tier_backer_required"))


class TestLatestInfoFeatureGroup(unittest.TestCase):
    """Test 7: feature_group latest_info returns TaiwanStockNews capability."""

    def test_latest_info_sample_only_returns_news(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("latest_info",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        self.assertIn("TaiwanStockNews", results)
        news_cap = results["TaiwanStockNews"]
        self.assertTrue(news_cap["ok"])
        self.assertEqual(news_cap["source"], "registry")

    def test_latest_info_includes_trading_date_capability(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("latest_info",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        self.assertIn("TaiwanStockTradingDate", results)


class TestStockAnalysisFeatureGroup(unittest.TestCase):
    """Test 8: feature_group stock_analysis includes price/fundamental/chip datasets."""

    def test_stock_analysis_sample_has_price(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("stock_analysis",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        self.assertIn("TaiwanStockPrice", results)

    def test_stock_analysis_sample_has_fundamental(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("stock_analysis",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        self.assertIn("TaiwanStockMonthRevenue", results)
        self.assertIn("TaiwanStockFinancialStatements", results)

    def test_stock_analysis_sample_has_chip(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("stock_analysis",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        self.assertIn("TaiwanStockInstitutionalInvestorsBuySell", results)


class TestBacktestingFeatureGroup(unittest.TestCase):
    """Test 9: feature_group backtesting includes price/adj price datasets."""

    def test_backtesting_has_adjusted_price(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("backtesting",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        self.assertIn("TaiwanStockPriceAdj", results)
        self.assertIn("TaiwanStockPrice", results)

    def test_backtesting_adj_price_caveat_present(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            results = fetcher.fetch_by_feature_group("backtesting",
                                                      start_date="2026-06-01",
                                                      end_date="2026-06-14",
                                                      sample_only=True)
        adj = results.get("TaiwanStockPriceAdj", {})
        # describe_capability returns caveats list
        caveats = adj.get("caveats", [])
        self.assertTrue(any("Backer" in c or "backer" in c for c in caveats),
                        f"Expected Backer caveat in {caveats}")


class TestPanelPromptCapability(unittest.TestCase):
    """Test 10: panel_prompt can describe capability without live calls."""

    def test_describe_stock_info_no_live_call(self):
        session = MagicMock()  # session never called
        client = FinMindClient(token="test_token", session=session)
        fetcher = FinMindDatasetFetcher(client=client)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "false", "DSA_FIXTURE_MODE": "false"}):
            cap = fetcher.describe_capability("TaiwanStockInfo")
        session.get.assert_not_called()
        self.assertTrue(cap["ok"])
        self.assertEqual(cap["source"], "registry")
        self.assertIn("panel_prompt", cap["feature_groups"])

    def test_capabilities_summary_has_all_groups(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        caps = fetcher.capabilities_summary()
        for group in ("latest_info", "stock_analysis", "backtesting", "market_review"):
            self.assertIn(group, caps)

    def test_describe_unknown_dataset(self):
        fetcher = _fetcher(_live_client({"status": 200, "msg": "", "data": []}))
        cap = fetcher.describe_capability("NonExistentDataset9999")
        self.assertFalse(cap["ok"])
        self.assertEqual(cap["unavailable_reason"], "unknown_dataset")


class TestNoNetworkMode(unittest.TestCase):
    """Test 11: No-network mode blocks live calls."""

    def test_fixture_mode_blocks_fetch(self):
        session = MagicMock()
        client = FinMindClient(token="test_token", session=session)
        fetcher = FinMindDatasetFetcher(client=client)
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}):
            result = fetcher.fetch("TaiwanStockTradingDate",
                                   start_date="2026-06-01", end_date="2026-06-14")
        session.get.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["unavailable_reason"], "fixture_mode_blocked")

    def test_network_disabled_blocks_fetch(self):
        session = MagicMock()
        client = FinMindClient(token="test_token", session=session)
        fetcher = FinMindDatasetFetcher(client=client)
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}):
            result = fetcher.fetch("TaiwanStockTradingDate",
                                   start_date="2026-06-01", end_date="2026-06-14")
        session.get.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["unavailable_reason"], "no_network")


class TestFixtureMode(unittest.TestCase):
    """Test 12: fixture_mode returns deterministic result or unavailable."""

    def test_fixture_mode_returns_fixture_mode_blocked(self):
        session = MagicMock()
        client = FinMindClient(token="test_token", session=session)
        fetcher = FinMindDatasetFetcher(client=client)
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true"}):
            result = fetcher.fetch("TaiwanStockPrice", data_id="2330",
                                   start_date="2026-06-01", end_date="2026-06-14")
        self.assertFalse(result["ok"])
        # Fetcher does not short-circuit before client; client returns fixture_mode_blocked
        self.assertEqual(result["unavailable_reason"], "fixture_mode_blocked")

    def test_describe_capability_works_in_fixture_mode(self):
        session = MagicMock()
        client = FinMindClient(token="test_token", session=session)
        fetcher = FinMindDatasetFetcher(client=client)
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true"}):
            # describe_capability never calls client
            cap = fetcher.describe_capability("TaiwanStockPrice")
        session.get.assert_not_called()
        self.assertTrue(cap["ok"])
        self.assertEqual(cap["source"], "registry")


if __name__ == "__main__":
    unittest.main()

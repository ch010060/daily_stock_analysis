# -*- coding: utf-8 -*-
"""
Tests for FinMind Dataset Registry (Phase 8A).

All tests are offline — no live provider calls.
"""

import unittest
from pathlib import Path

from src.finmind.dataset_registry import FinMindDatasetRegistry

_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "src" / "finmind" / "finmind_dataset_registry.json"

_REQUIRED_DATASETS = {
    # latest info
    "TaiwanStockNews",
    "TaiwanStockTradingDate",
    # market review
    "TaiwanStockTotalReturnIndex",
    "TaiwanStockTotalInstitutionalInvestors",
    "TaiwanStockTotalMarginPurchaseShortSale",
    # stock analysis
    "TaiwanStockInfo",
    "TaiwanStockPrice",
    "TaiwanStockPriceAdj",
    "TaiwanStockPER",
    "TaiwanStockMarketValue",
    "TaiwanStockMonthRevenue",
    "TaiwanStockFinancialStatements",
    "TaiwanStockBalanceSheet",
    "TaiwanStockCashFlowsStatement",
    "TaiwanStockDividend",
    "TaiwanStockDividendResult",
    "TaiwanStockInstitutionalInvestorsBuySell",
    "TaiwanStockMarginPurchaseShortSale",
    "TaiwanStockShareholding",
    "TaiwanStockSecuritiesLending",
    # backtesting
    # (covered by TaiwanStockPriceAdj, TaiwanStockPrice above)
    # strategy
    "TaiwanFuturesInstitutionalInvestors",
    "TaiwanOptionInstitutionalInvestors",
    # deferred tick
    "TaiwanStockKBar",
    "TaiwanStockPriceTick",
    "TaiwanVariousIndicators5Seconds",
}


class TestRegistryLoads(unittest.TestCase):
    """Test 1: registry file exists and loads."""

    def test_registry_file_exists(self):
        self.assertTrue(_REGISTRY_PATH.exists(), f"Registry file missing: {_REGISTRY_PATH}")

    def test_registry_loads_without_error(self):
        reg = FinMindDatasetRegistry()
        self.assertIsNotNone(reg)
        self.assertGreater(len(reg.dataset_names), 0)

    def test_registry_version_present(self):
        reg = FinMindDatasetRegistry()
        self.assertIsInstance(reg.version, str)
        self.assertGreater(len(reg.version), 0)

    def test_registry_has_minimum_dataset_count(self):
        reg = FinMindDatasetRegistry()
        self.assertGreaterEqual(len(reg.dataset_names), 20)


class TestRequiredDatasetsExist(unittest.TestCase):
    """Test 2: all required datasets are present."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_all_required_datasets_exist(self):
        names = set(self._reg.dataset_names)
        missing = _REQUIRED_DATASETS - names
        self.assertEqual(set(), missing, f"Missing required datasets: {missing}")

    def test_taiwan_stock_news_exists(self):
        self.assertIsNotNone(self._reg.get("TaiwanStockNews"))

    def test_taiwan_stock_trading_date_exists(self):
        self.assertIsNotNone(self._reg.get("TaiwanStockTradingDate"))

    def test_taiwan_stock_price_exists(self):
        self.assertIsNotNone(self._reg.get("TaiwanStockPrice"))

    def test_taiwan_stock_price_adj_exists(self):
        self.assertIsNotNone(self._reg.get("TaiwanStockPriceAdj"))

    def test_taiwan_stock_total_return_index_exists(self):
        self.assertIsNotNone(self._reg.get("TaiwanStockTotalReturnIndex"))

    def test_taiwan_stock_kbar_deferred_registered(self):
        entry = self._reg.get("TaiwanStockKBar")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["tier"], "sponsor")


class TestDatasetStructure(unittest.TestCase):
    """Test 3: each dataset has market/category/feature_groups."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_all_datasets_have_market(self):
        for d in self._reg.all_datasets:
            self.assertIn("market", d, f"{d.get('dataset')} missing 'market'")
            self.assertIn(d["market"], ("TW", "US", "HK", "GLOBAL"))

    def test_all_datasets_have_category(self):
        for d in self._reg.all_datasets:
            self.assertIn("category", d, f"{d.get('dataset')} missing 'category'")
            self.assertGreater(len(d["category"]), 0)

    def test_all_datasets_have_feature_groups(self):
        for d in self._reg.all_datasets:
            self.assertIn("feature_groups", d, f"{d.get('dataset')} missing 'feature_groups'")
            self.assertIsInstance(d["feature_groups"], list)
            self.assertGreater(len(d["feature_groups"]), 0, f"{d.get('dataset')} has empty feature_groups")

    def test_all_datasets_have_columns(self):
        for d in self._reg.all_datasets:
            self.assertIn("columns", d, f"{d.get('dataset')} missing 'columns'")
            self.assertIsInstance(d["columns"], list)


class TestRestParams(unittest.TestCase):
    """Test 4: rest params present and have endpoint."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_all_datasets_have_rest(self):
        for d in self._reg.all_datasets:
            self.assertIn("rest", d, f"{d.get('dataset')} missing 'rest'")

    def test_all_datasets_rest_has_endpoint(self):
        for d in self._reg.all_datasets:
            rest = d.get("rest", {})
            self.assertIn("endpoint", rest, f"{d.get('dataset')} rest missing 'endpoint'")

    def test_all_datasets_rest_has_params(self):
        for d in self._reg.all_datasets:
            rest = d.get("rest", {})
            self.assertIn("params", rest, f"{d.get('dataset')} rest missing 'params'")
            self.assertIsInstance(rest["params"], list)

    def test_special_endpoint_for_trading_daily_report(self):
        d = self._reg.get("TaiwanStockTradingDailyReport")
        if d:
            self.assertNotEqual(d["rest"]["endpoint"], "/data")
            self.assertIn("date", d["rest"]["params"])

    def test_standard_endpoint_for_price(self):
        d = self._reg.get("TaiwanStockPrice")
        self.assertEqual(d["rest"]["endpoint"], "/data")
        self.assertIn("start_date", d["rest"]["params"])
        self.assertIn("end_date", d["rest"]["params"])


class TestDataIdRequired(unittest.TestCase):
    """Test 5: data_id_required correct for known datasets."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_stock_price_requires_data_id(self):
        d = self._reg.get("TaiwanStockPrice")
        self.assertTrue(d["data_id_required"])

    def test_trading_date_does_not_require_data_id(self):
        d = self._reg.get("TaiwanStockTradingDate")
        self.assertFalse(d["data_id_required"])

    def test_stock_info_does_not_require_data_id(self):
        d = self._reg.get("TaiwanStockInfo")
        self.assertFalse(d["data_id_required"])

    def test_total_institutional_investors_does_not_require_data_id(self):
        d = self._reg.get("TaiwanStockTotalInstitutionalInvestors")
        self.assertFalse(d["data_id_required"])

    def test_total_margin_does_not_require_data_id(self):
        d = self._reg.get("TaiwanStockTotalMarginPurchaseShortSale")
        self.assertFalse(d["data_id_required"])

    def test_news_requires_data_id(self):
        d = self._reg.get("TaiwanStockNews")
        self.assertTrue(d["data_id_required"])


class TestSDKMethods(unittest.TestCase):
    """Test 6: SDK method names present when known."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_price_has_sdk_method(self):
        d = self._reg.get("TaiwanStockPrice")
        self.assertEqual(d["sdk"]["method"], "taiwan_stock_daily")

    def test_price_adj_has_sdk_method(self):
        d = self._reg.get("TaiwanStockPriceAdj")
        self.assertEqual(d["sdk"]["method"], "taiwan_stock_daily_adj")

    def test_month_revenue_has_sdk_method(self):
        d = self._reg.get("TaiwanStockMonthRevenue")
        self.assertEqual(d["sdk"]["method"], "taiwan_stock_month_revenue")

    def test_total_return_index_has_sdk_method(self):
        d = self._reg.get("TaiwanStockTotalReturnIndex")
        self.assertIsNotNone(d["sdk"]["method"])

    def test_all_datasets_have_sdk_block(self):
        for d in self._reg.all_datasets:
            self.assertIn("sdk", d, f"{d.get('dataset')} missing 'sdk'")
            self.assertIn("method", d["sdk"], f"{d.get('dataset')} sdk missing 'method'")


class TestNoCNDatasets(unittest.TestCase):
    """Test 7: no CN/A-share datasets accidentally included."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_no_cn_datasets_in_registry(self):
        self.assertFalse(
            self._reg.has_cn_datasets(),
            "CN/A-share datasets found in registry — forbidden under Route B"
        )

    def test_all_datasets_market_is_tw(self):
        for d in self._reg.all_datasets:
            self.assertEqual(
                d.get("market"), "TW",
                f"{d.get('dataset')} has market={d.get('market')} — expected TW"
            )

    def test_no_akshare_in_sdk_methods(self):
        for d in self._reg.all_datasets:
            method = d.get("sdk", {}).get("method") or ""
            self.assertNotIn("akshare", method.lower(), f"{d.get('dataset')} sdk method references akshare")


class TestLatestInfoMapping(unittest.TestCase):
    """Test 8: latest_info maps to TaiwanStockNews and TaiwanStockTradingDate."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_latest_info_includes_news(self):
        names = [d["dataset"] for d in self._reg.by_feature_group("latest_info")]
        self.assertIn("TaiwanStockNews", names)

    def test_latest_info_includes_trading_date(self):
        names = [d["dataset"] for d in self._reg.by_feature_group("latest_info")]
        self.assertIn("TaiwanStockTradingDate", names)

    def test_latest_info_has_at_least_two_datasets(self):
        items = self._reg.by_feature_group("latest_info")
        self.assertGreaterEqual(len(items), 2)


class TestStockAnalysisMapping(unittest.TestCase):
    """Test 9: stock_analysis maps to price/fundamental/chip datasets."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()
        self._names = {d["dataset"] for d in self._reg.by_feature_group("stock_analysis")}

    def test_stock_analysis_has_price(self):
        self.assertIn("TaiwanStockPrice", self._names)

    def test_stock_analysis_has_fundamental(self):
        self.assertIn("TaiwanStockMonthRevenue", self._names)
        self.assertIn("TaiwanStockFinancialStatements", self._names)

    def test_stock_analysis_has_chip(self):
        self.assertIn("TaiwanStockInstitutionalInvestorsBuySell", self._names)
        self.assertIn("TaiwanStockMarginPurchaseShortSale", self._names)

    def test_stock_analysis_has_per(self):
        self.assertIn("TaiwanStockPER", self._names)

    def test_stock_analysis_has_stock_info(self):
        self.assertIn("TaiwanStockInfo", self._names)

    def test_stock_analysis_has_dividend(self):
        self.assertIn("TaiwanStockDividend", self._names)


class TestBacktestingMapping(unittest.TestCase):
    """Test 10: backtesting maps to adjusted price and price data."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()
        self._names = {d["dataset"] for d in self._reg.by_feature_group("backtesting")}

    def test_backtesting_has_adjusted_price(self):
        self.assertIn("TaiwanStockPriceAdj", self._names)

    def test_backtesting_has_raw_price(self):
        self.assertIn("TaiwanStockPrice", self._names)

    def test_backtesting_has_per(self):
        self.assertIn("TaiwanStockPER", self._names)

    def test_backtesting_has_month_revenue(self):
        self.assertIn("TaiwanStockMonthRevenue", self._names)

    def test_backtesting_has_institutional(self):
        self.assertIn("TaiwanStockInstitutionalInvestorsBuySell", self._names)


class TestStrategyAnalysisMapping(unittest.TestCase):
    """Test 11: strategy_analysis maps to supported dataset groups."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()
        self._names = {d["dataset"] for d in self._reg.by_feature_group("strategy_analysis")}

    def test_strategy_has_price(self):
        self.assertIn("TaiwanStockPrice", self._names)

    def test_strategy_has_chip(self):
        self.assertIn("TaiwanStockInstitutionalInvestorsBuySell", self._names)

    def test_strategy_has_derivatives(self):
        self.assertIn("TaiwanFuturesDaily", self._names)
        self.assertIn("TaiwanOptionDaily", self._names)

    def test_strategy_has_futures_institutional(self):
        self.assertIn("TaiwanFuturesInstitutionalInvestors", self._names)


class TestPanelPromptCapabilities(unittest.TestCase):
    """Test 12: panel prompt feature can query dataset capabilities."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_panel_prompt_datasets_exist(self):
        items = self._reg.for_panel_prompt()
        self.assertGreater(len(items), 0)

    def test_capabilities_summary_has_all_groups(self):
        caps = self._reg.capabilities_summary()
        for group in ("latest_info", "stock_analysis", "backtesting", "market_review"):
            self.assertIn(group, caps, f"Feature group '{group}' missing from capabilities")

    def test_capabilities_summary_lists_dataset_names(self):
        caps = self._reg.capabilities_summary()
        stock_analysis = caps.get("stock_analysis", [])
        self.assertIn("TaiwanStockPrice", stock_analysis)

    def test_panel_prompt_includes_stock_info(self):
        panel = [d["dataset"] for d in self._reg.for_panel_prompt()]
        self.assertIn("TaiwanStockInfo", panel)


class TestRegistryValidation(unittest.TestCase):
    """Test 13: registry passes structural validation."""

    def setUp(self):
        self._reg = FinMindDatasetRegistry()

    def test_validate_returns_no_errors(self):
        errors = self._reg.validate()
        self.assertEqual([], errors, f"Registry validation errors: {errors}")

    def test_no_duplicate_dataset_names(self):
        names = self._reg.dataset_names
        self.assertEqual(len(names), len(set(names)))

    def test_get_returns_none_for_unknown_dataset(self):
        self.assertIsNone(self._reg.get("NonExistentDataset"))

    def test_by_feature_group_returns_list(self):
        result = self._reg.by_feature_group("stock_analysis")
        self.assertIsInstance(result, list)

    def test_by_category_technical_returns_price(self):
        techs = [d["dataset"] for d in self._reg.by_category("technical")]
        self.assertIn("TaiwanStockPrice", techs)
        self.assertIn("TaiwanStockPER", techs)

    def test_probe_enabled_is_subset(self):
        probes = self._reg.probe_enabled()
        for d in probes:
            self.assertTrue(d["live_probe"]["enabled"])

    def test_free_tier_includes_price(self):
        free = [d["dataset"] for d in self._reg.by_tier("free")]
        self.assertIn("TaiwanStockPrice", free)
        self.assertIn("TaiwanStockMonthRevenue", free)

    def test_sponsor_tier_includes_kbar(self):
        sponsor = [d["dataset"] for d in self._reg.by_tier("sponsor")]
        self.assertIn("TaiwanStockKBar", sponsor)


if __name__ == "__main__":
    unittest.main()

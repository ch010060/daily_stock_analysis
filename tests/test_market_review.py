# -*- coding: utf-8 -*-
"""Tests for localized market review wrappers."""

import importlib
import os
import sys
import tempfile
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

def _build_optional_module_stubs() -> dict[str, ModuleType]:
    stubs: dict[str, ModuleType] = {}
    google_module: ModuleType | None = None

    for module_name in ("google.generativeai", "google.genai", "anthropic"):
        try:
            importlib.import_module(module_name)
            continue
        except ImportError:
            stub = ModuleType(module_name)
            stubs[module_name] = stub
            if not module_name.startswith("google."):
                continue
            if google_module is None:
                try:
                    google_module = importlib.import_module("google")
                except ImportError:
                    google_module = ModuleType("google")
                    stubs["google"] = google_module
            setattr(google_module, module_name.split(".", 1)[1], stub)

    return stubs


sys.modules.update(_build_optional_module_stubs())
import src.core.market_review as market_review_module
from data_provider.taiwan_market import TaiwanMarketDataFetcher
from src.config import Config
from src.core.tw_market_review import build_tw_market_review_context
from src.storage import AnalysisHistory, DatabaseManager

run_market_review = market_review_module.run_market_review


class TaiwanMarketSnapshotEnrichmentTestCase(unittest.TestCase):
    def test_market_snapshot_includes_representative_price_and_valuation_rows(self) -> None:
        fetcher = TaiwanMarketDataFetcher()

        snapshot = fetcher.get_tw_market_snapshot("2026-06-01", "2026-06-13")

        tw_daily = snapshot["tw_daily_snapshot"]
        self.assertEqual(tw_daily["kind"], "tw_daily_snapshot")
        self.assertEqual(tw_daily["source"], "finmind")
        self.assertEqual(tw_daily["data_date"], "2026-06-12")

        reps = {row["symbol"]: row for row in tw_daily["representatives"]}
        self.assertEqual(set(reps), {"0050", "006208", "2330"})

        self.assertEqual(reps["006208"]["name"], "富邦台50")
        self.assertEqual(reps["006208"]["close"], 117.7)
        self.assertEqual(reps["006208"]["previous_close"], 118.9)
        self.assertAlmostEqual(reps["006208"]["change"], -1.2)
        self.assertAlmostEqual(reps["006208"]["change_pct"], -1.0093, places=4)
        self.assertEqual(reps["006208"]["volume"], 28000000)
        self.assertEqual(reps["006208"]["turnover"], 3295600000)
        self.assertEqual(reps["006208"]["semantic_direction"], "tw_loss")
        self.assertIn("PER", reps["006208"]["missing_fields"])

        self.assertEqual(reps["2330"]["PER"], 25.1)
        self.assertEqual(reps["2330"]["PBR"], 6.3)
        self.assertEqual(reps["2330"]["dividend_yield"], 1.38)
        self.assertEqual(reps["2330"]["valuation_as_of"], "2026-06-12")

    def test_market_snapshot_representatives_align_to_snapshot_data_date(self) -> None:
        fetcher = TaiwanMarketDataFetcher()
        sections = {
            "availability": {"as_of": "2026-06-26"},
            "taiex": {
                "ok": True,
                "dataset": "TaiwanStockTotalReturnIndex",
                "data_id": "TAIEX",
                "source": "fixture",
                "rows": [
                    {"date": "2026-06-25", "price": 100.0},
                    {"date": "2026-06-26", "price": 101.0},
                ],
            },
            "tpex": {
                "ok": True,
                "dataset": "TaiwanStockTotalReturnIndex",
                "data_id": "TPEx",
                "source": "fixture",
                "rows": [
                    {"date": "2026-06-25", "price": 80.0},
                    {"date": "2026-06-26", "price": 81.0},
                ],
            },
            "institutional_total": {"ok": True, "dataset": "TaiwanStockTotalInstitutionalInvestors", "rows": []},
            "margin_total": {"ok": True, "dataset": "TaiwanStockTotalMarginPurchaseShortSale", "rows": []},
            "ref_0050": {
                "ok": True,
                "dataset": "TaiwanStockPrice",
                "data_id": "0050",
                "source": "fixture",
                "rows": [
                    {"date": "2026-06-25", "close": 100.0, "Trading_Volume": 1000, "Trading_money": 100000},
                    {"date": "2026-06-26", "close": 101.0, "Trading_Volume": 1100, "Trading_money": 111100},
                    {"date": "2026-06-29", "close": 120.0, "Trading_Volume": 1200, "Trading_money": 144000},
                ],
            },
            "ref_006208": {
                "ok": True,
                "dataset": "TaiwanStockPrice",
                "data_id": "006208",
                "source": "fixture",
                "rows": [
                    {"date": "2026-06-25", "close": 90.0, "Trading_Volume": 900, "Trading_money": 81000},
                    {"date": "2026-06-26", "close": 91.0, "Trading_Volume": 950, "Trading_money": 86450},
                    {"date": "2026-06-29", "close": 130.0, "Trading_Volume": 1300, "Trading_money": 169000},
                ],
            },
            "ref_2330": {
                "ok": True,
                "dataset": "TaiwanStockPrice",
                "data_id": "2330",
                "source": "fixture",
                "rows": [
                    {"date": "2026-06-25", "close": 980.0, "Trading_Volume": 10000, "Trading_money": 9800000},
                    {"date": "2026-06-26", "close": 990.0, "Trading_Volume": 11000, "Trading_money": 10890000},
                    {"date": "2026-06-29", "close": 1100.0, "Trading_Volume": 12000, "Trading_money": 13200000},
                ],
            },
            "per_0050": {"ok": True, "dataset": "TaiwanStockPER", "data_id": "0050", "rows": []},
            "per_006208": {"ok": True, "dataset": "TaiwanStockPER", "data_id": "006208", "rows": []},
            "per_2330": {
                "ok": True,
                "dataset": "TaiwanStockPER",
                "data_id": "2330",
                "source": "fixture",
                "rows": [
                    {"date": "2026-06-26", "PER": 20.0, "PBR": 5.0, "dividend_yield": 2.0},
                    {"date": "2026-06-29", "PER": 22.0, "PBR": 5.5, "dividend_yield": 1.8},
                ],
            },
        }

        tw_daily = fetcher._build_tw_daily_snapshot(sections)
        reps = {row["symbol"]: row for row in tw_daily["representatives"]}

        self.assertEqual(reps["0050"]["data_date"], "2026-06-26")
        self.assertEqual(reps["0050"]["close"], 101.0)
        self.assertEqual(reps["006208"]["data_date"], "2026-06-26")
        self.assertEqual(reps["006208"]["close"], 91.0)
        self.assertEqual(reps["2330"]["data_date"], "2026-06-26")
        self.assertEqual(reps["2330"]["close"], 990.0)
        self.assertEqual(reps["2330"]["valuation_as_of"], "2026-06-26")
        self.assertEqual(reps["2330"]["PER"], 20.0)

        ctx = build_tw_market_review_context(sections)
        self.assertEqual(ctx["last_0050"]["date"], "2026-06-26")
        self.assertEqual(ctx["last_006208"]["date"], "2026-06-26")
        self.assertEqual(ctx["last_2330"]["date"], "2026-06-26")

    def test_market_snapshot_records_semantics_and_partial_failures(self) -> None:
        class EmptyTpexFetcher(TaiwanMarketDataFetcher):
            def get_total_return_index(self, index_id, start_date, end_date):
                if index_id == "TPEx":
                    return {
                        "ok": False,
                        "source": "fixture",
                        "dataset": "TaiwanStockTotalReturnIndex",
                        "data_id": "TPEx",
                        "rows": [],
                        "columns": [],
                        "row_count": 0,
                        "start_date": start_date,
                        "end_date": end_date,
                        "error": "boom",
                        "unavailable_reason": "test_failure",
                        "cache_meta": {},
                    }
                return super().get_total_return_index(index_id, start_date, end_date)

        snapshot = EmptyTpexFetcher().get_tw_market_snapshot("2026-06-01", "2026-06-13")

        self.assertFalse(snapshot["tpex"]["ok"])
        tw_daily = snapshot["tw_daily_snapshot"]
        self.assertIn("tpex", tw_daily["data_status"]["partial_failures"])
        taiex = next(row for row in tw_daily["indices"] if row["symbol"] == "TAIEX")
        self.assertEqual(taiex["semantic_direction"], "tw_gain")
        margin = next(row for row in tw_daily["margin_short"] if row["name"] == "MarginPurchaseMoney")
        self.assertEqual(margin["semantic_type"], "risk_or_leverage")

    def test_tw_market_review_context_keeps_old_markdown_compatibility(self) -> None:
        snapshot = TaiwanMarketDataFetcher().get_tw_market_snapshot("2026-06-01", "2026-06-13")

        ctx = build_tw_market_review_context(snapshot)

        self.assertTrue(ctx["ref_0050_ok"])
        self.assertTrue(ctx["ref_006208_ok"])
        self.assertTrue(ctx["ref_2330_ok"])
        self.assertEqual(ctx["last_006208"]["close"], 117.7)


class MarketReviewLocalizationTestCase(unittest.TestCase):
    def _make_notifier(self) -> MagicMock:
        notifier = MagicMock()
        notifier.save_report_to_file.return_value = "/tmp/market_review.md"
        notifier.is_available.return_value = True
        notifier.send.return_value = True
        return notifier

    def test_resolve_market_review_regions_returns_ordered_non_empty_list(self) -> None:
        cases = [
            (None, ["tw"]),
            ("", ["tw"]),
            ("all", ["tw", "us"]),
            ("both", ["tw", "us"]),
            (" CN,US,cn ", ["us"]),
            ("us,cn,us", ["us"]),
            ("eu,apac", []),
            (",,", []),
            ("HK", []),
            ("invalid", []),
        ]

        for raw_region, expected in cases:
            with self.subTest(raw_region=raw_region):
                self.assertEqual(
                    market_review_module._resolve_market_review_regions(raw_region),
                    expected,
                )

    def test_run_market_review_uses_english_notification_title(self) -> None:
        notifier = self._make_notifier()
        market_analyzer = MagicMock()
        market_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="## 2026-04-10 US Market Recap\n\nBody",
            market_light_snapshot={"region": "us", "trade_date": "2026-04-10", "score": 60},
        )

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="en", market_review_region="us"),
        ), patch.object(
            market_review_module,
            "MarketAnalyzer",
            return_value=market_analyzer,
        ), patch.object(market_review_module, "_persist_market_review_history") as persist_history:
            result = run_market_review(notifier, send_notification=True)

        self.assertEqual(result, "## 2026-04-10 US Market Recap\n\nBody")
        saved_content = notifier.save_report_to_file.call_args.args[0]
        self.assertTrue(saved_content.startswith("# 🎯 Market Review\n\n"))
        sent_content = notifier.send.call_args.args[0]
        self.assertTrue(sent_content.startswith("🎯 Market Review\n\n"))
        self.assertTrue(notifier.send.call_args.kwargs["email_send_to_all"])
        self.assertEqual(notifier.send.call_args.kwargs["route_type"], "report")
        persist_history.assert_called_once()
        self.assertEqual(persist_history.call_args.kwargs["query_id"], None)

    def test_run_market_review_merges_both_regions_with_english_wrappers(self) -> None:
        notifier = self._make_notifier()
        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body",
            market_light_snapshot={"region": "us", "trade_date": "2026-03-06", "score": 55},
        )

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="en", market_review_region="both"),
        ), patch.object(
            market_review_module,
            "MarketAnalyzer",
            return_value=us_analyzer,
        ), patch.object(
            market_review_module,
            "_run_tw_market_review_section",
            return_value=("# TW Market Recap\n\nTW body", {"region": "tw", "score": 60}),
        ), patch.object(market_review_module, "_persist_market_review_history"):
            result = run_market_review(notifier, send_notification=False)

        self.assertIn("# TW Market Recap\n\nTW body", result)
        self.assertIn("> Next market recap follows", result)
        self.assertIn("# US Market Recap\n\nUS body", result)
        saved_content = notifier.save_report_to_file.call_args.args[0]
        self.assertTrue(saved_content.startswith("# 🎯 Market Review\n\n"))
        notifier.send.assert_not_called()

    def test_run_market_review_comma_joined_subset_tw_us(self) -> None:
        """TW/US comma value runs both supported markets."""
        notifier = self._make_notifier()
        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body",
            market_light_snapshot={"region": "us", "trade_date": "2026-03-06", "score": 55},
        )

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="zh", market_review_region="tw"),
        ), patch.object(
            market_review_module,
            "MarketAnalyzer",
            return_value=us_analyzer,
        ) as market_analyzer_factory, patch.object(
            market_review_module,
            "_run_tw_market_review_section",
            return_value=("# 台股大盤回顧\n\nTW body", {"region": "tw", "score": 60}),
        ), patch.object(market_review_module, "_persist_market_review_history"):
            result = run_market_review(
                notifier, send_notification=False, override_region="tw,us"
            )

        self.assertIn("# 台股大盤回顧\n\nTW body", result)
        self.assertIn("# 美股大盤回顧\n\nUS body", result)
        self.assertNotIn("HK", result)

    def test_run_market_review_comma_joined_subset_cn_hk_returns_none(self) -> None:
        """Unsupported CN/HK values do not run market review."""
        notifier = self._make_notifier()
        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body",
            market_light_snapshot={"region": "us", "trade_date": "2026-03-06", "score": 58},
        )

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="zh", market_review_region="tw"),
        ), patch.object(
            market_review_module,
            "MarketAnalyzer",
            return_value=us_analyzer,
        ) as market_analyzer_factory, patch.object(
            market_review_module,
            "_run_tw_market_review_section",
            return_value=("# 台股大盤回顧\n\nTW body", {"region": "tw", "score": 60}),
        ) as tw_section, patch.object(market_review_module, "_persist_market_review_history") as persist_history:
            result = run_market_review(
                notifier, send_notification=False, override_region="cn,hk"
            )

        self.assertIsNone(result)
        tw_section.assert_not_called()
        market_analyzer_factory.assert_not_called()
        persist_history.assert_not_called()

    def test_run_market_review_persists_only_current_run_market_light_snapshots(self) -> None:
        notifier = self._make_notifier()
        us_analyzer = MagicMock()
        us_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
            report="US body",
            market_light_snapshot={"region": "us", "trade_date": "2026-03-06", "score": 55},
        )

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="zh", market_review_region="tw"),
        ), patch.object(
            market_review_module,
            "MarketAnalyzer",
            return_value=us_analyzer,
        ), patch.object(
            market_review_module,
            "_run_tw_market_review_section",
            return_value=("# 台股大盤回顧\n\nTW body", {"region": "tw", "trade_date": "2026-03-06", "score": 60}),
        ), patch.object(market_review_module, "_persist_market_review_history") as persist_history:
            run_market_review(notifier, send_notification=False, override_region="tw,us")

        snapshots = persist_history.call_args.kwargs["market_light_snapshots"]
        self.assertEqual(set(snapshots), {"tw", "us"})
        self.assertEqual(snapshots["tw"]["score"], 60)
        self.assertEqual(snapshots["us"]["score"], 55)

    def test_run_market_review_normalizes_single_region_snapshot_key(self) -> None:
        notifier = self._make_notifier()

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="zh", market_review_region="tw"),
        ), patch.object(
            market_review_module,
            "_run_tw_market_review_section",
            return_value=("# 台股大盤回顧\n\nTW body", {"region": "tw", "trade_date": "2026-03-06", "score": 60}),
        ), patch.object(
            market_review_module, "_persist_market_review_history"
        ) as persist_history:
            run_market_review(notifier, send_notification=False, override_region="TW")

        persist_history.assert_called_once()
        self.assertEqual(persist_history.call_args.kwargs["region"], "tw")
        snapshots = persist_history.call_args.kwargs["market_light_snapshots"]
        self.assertEqual(set(snapshots), {"tw"})
        self.assertEqual(snapshots["tw"]["trade_date"], "2026-03-06")

    def test_run_market_review_invalid_comma_subset_returns_none(self) -> None:
        notifier = self._make_notifier()

        with patch.object(
            market_review_module,
            "get_config",
            return_value=SimpleNamespace(report_language="zh", market_review_region="tw"),
        ), patch.object(
            market_review_module,
            "_run_tw_market_review_section",
            return_value=("TW body", {"region": "tw", "trade_date": "2026-03-06", "score": 60}),
        ) as tw_section, patch.object(
            market_review_module, "_persist_market_review_history"
        ) as persist_history:
            result = run_market_review(
                notifier, send_notification=False, override_region="eu,apac"
            )

        self.assertIsNone(result)
        tw_section.assert_not_called()
        persist_history.assert_not_called()

    def test_persist_market_review_history_saves_markdown_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_db_path = os.environ.get("DATABASE_PATH")
            os.environ["DATABASE_PATH"] = os.path.join(temp_dir, "market_review_history.db")
            Config._instance = None
            DatabaseManager.reset_instance()
            try:
                saved = market_review_module._persist_market_review_history(
                    review_report="## 今日大盤\n\n覆盤正文",
                    markdown_report="# 🎯 大盤覆盤\n\n## 今日大盤\n\n覆盤正文",
                    region="tw",
                    config=SimpleNamespace(report_language="zh"),
                    query_id="market-task-001",
                    market_light_snapshots={
                        "tw": {
                            "region": "tw",
                            "trade_date": "2026-03-06",
                            "status": "red",
                            "score": 30,
                            "label": "偏防守",
                            "temperature_label": "偏弱",
                            "reasons": ["test"],
                            "guidance": "test",
                            "dimensions": {
                                "breadth": {"score": 20, "available": True},
                                "index": {"score": 30, "available": True},
                                "limit": {"score": 10, "available": True},
                            },
                            "data_quality": "ok",
                        }
                    },
                )

                self.assertEqual(saved, 1)
                db = DatabaseManager.get_instance()
                with db.get_session() as session:
                    row = session.query(AnalysisHistory).filter(
                        AnalysisHistory.query_id == "market-task-001"
                    ).first()
                    self.assertIsNotNone(row)
                    self.assertEqual(row.code, market_review_module.MARKET_REVIEW_HISTORY_CODE)
                    self.assertEqual(row.name, "台股日報")
                    self.assertEqual(row.report_type, market_review_module.MARKET_REVIEW_REPORT_TYPE)
                    self.assertEqual(row.news_content, "## 今日大盤\n\n覆盤正文")
                    self.assertIn("# 🎯 大盤覆盤", row.raw_result)
                    self.assertIn('"market_light_snapshots"', row.context_snapshot)
                    self.assertIn('"trade_date": "2026-03-06"', row.context_snapshot)
            finally:
                DatabaseManager.reset_instance()
                Config._instance = None
                if old_db_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = old_db_path

    def test_persist_market_review_history_uses_market_overview_wording_not_legacy_recap_term(self) -> None:
        """History/stock-bar card title must not surface the legacy 大盤覆盤/大盤復盤 wording."""
        with tempfile.TemporaryDirectory() as temp_dir:
            old_db_path = os.environ.get("DATABASE_PATH")
            os.environ["DATABASE_PATH"] = os.path.join(temp_dir, "market_review_history.db")
            Config._instance = None
            DatabaseManager.reset_instance()
            try:
                saved = market_review_module._persist_market_review_history(
                    review_report="## 美股大盤回顧\n\n正文",
                    markdown_report="# 🎯 大盤回顧\n\n## 美股大盤回顧\n\n正文",
                    region="us",
                    config=SimpleNamespace(report_language="zh_TW"),
                    query_id="market-task-002",
                )

                self.assertEqual(saved, 1)
                db = DatabaseManager.get_instance()
                with db.get_session() as session:
                    row = session.query(AnalysisHistory).filter(
                        AnalysisHistory.query_id == "market-task-002"
                    ).first()
                    self.assertIsNotNone(row)
                    self.assertEqual(row.name, "台股日報")
                    self.assertNotIn("大盤覆盤", row.name)
                    self.assertNotIn("大盤復盤", row.name)
                    self.assertNotIn("大盤覆盤", row.operation_advice or "")
                    self.assertNotIn("大盤覆盤", row.trend_prediction or "")
            finally:
                DatabaseManager.reset_instance()
                Config._instance = None
                if old_db_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = old_db_path


if __name__ == "__main__":
    unittest.main()

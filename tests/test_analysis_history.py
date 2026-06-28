# -*- coding: utf-8 -*-
"""
===================================
台股自選股智慧分析系統 - 分析歷史儲存單元測試
===================================

職責：
1. 驗證分析歷史儲存邏輯
2. 驗證上下文快照儲存開關
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Keep this test runnable when optional LLM runtime deps are not installed.
try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

try:
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.v1.endpoints.history import get_history_detail
except ModuleNotFoundError:
    TestClient = None
    create_app = None
    get_history_detail = None

from src.config import Config
from src.storage import DatabaseManager, AnalysisHistory, BacktestResult
from src.analyzer import AnalysisResult
from src.search_service import SearchResponse, SearchResult
from src.services.history_service import HistoryService
import src.auth as auth


def _analysis_context_pack_overview() -> dict:
    return {
        "pack_version": "1.0",
        "created_at": "2026-04-10T08:30:00+00:00",
        "subject": {
            "code": "2330",
            "stock_name": "台積電",
            "market": "cn",
        },
        "blocks": [
            {
                "key": "quote",
                "label": "行情",
                "status": "available",
                "source": "mock",
                "warnings": [],
                "missing_reasons": [],
            }
        ],
        "counts": {
            "available": 1,
            "missing": 0,
            "not_supported": 0,
            "fallback": 0,
            "stale": 0,
            "estimated": 0,
            "partial": 0,
            "fetch_failed": 0,
        },
        "data_quality": {
            "overall_score": 100,
            "level": "good",
            "block_scores": {
                "quote": 100,
                "daily_bars": 100,
                "technical": 100,
                "news": 100,
                "fundamentals": 100,
                "chip": 100,
            },
            "limitations": [],
        },
        "warnings": [],
        "metadata": {
            "trigger_source": "api",
            "news_result_count": 2,
        },
    }


def _market_phase_summary() -> dict:
    return {
        "market": "cn",
        "phase": "intraday",
        "market_local_time": "2026-03-27T10:00:00+08:00",
        "session_date": "2026-03-27",
        "effective_daily_bar_date": "2026-03-26",
        "is_trading_day": True,
        "is_market_open_now": True,
        "is_partial_bar": True,
        "minutes_to_open": None,
        "minutes_to_close": 300,
        "trigger_source": "api",
        "analysis_intent": "auto",
        "warnings": ["partial_bar"],
    }


class AnalysisHistoryTestCase(unittest.TestCase):
    """分析歷史儲存測試"""

    def setUp(self) -> None:
        """為每個用例初始化獨立資料庫"""
        auth._auth_enabled = False
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_analysis_history.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        """清理資源"""
        DatabaseManager.reset_instance()
        self._temp_dir.cleanup()

    def _build_result(self) -> AnalysisResult:
        """構造分析結果"""
        return AnalysisResult(
            code="2330",
            name="台積電",
            sentiment_score=78,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="基本面穩健，短期震盪",
        )

    def _save_history(self, query_id: str) -> int:
        """儲存一條測試歷史記錄並返回主鍵 ID。"""
        result = self._build_result()
        saved = self.db.save_analysis_history(
            result=result,
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            return row.id

    def test_save_analysis_history_with_snapshot(self) -> None:
        """儲存歷史記錄並寫入上下文快照"""
        result = self._build_result()
        result.dashboard = {
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "理想買進點：125.5元",
                    "secondary_buy": "120",
                    "stop_loss": "止損位：110元",
                    "take_profit": "目標位：150.0元",
                }
            }
        }
        context_snapshot = {"enhanced_context": {"code": "2330"}}

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_001",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True
        )

        self.assertEqual(saved, 1)

        history = self.db.get_analysis_history(code="2330", days=7, limit=10)
        self.assertEqual(len(history), 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            self.assertEqual(row.query_id, "query_001")
            self.assertIsNotNone(row.context_snapshot)
            self.assertEqual(row.ideal_buy, 125.5)
            self.assertEqual(row.secondary_buy, 120.0)
            self.assertEqual(row.stop_loss, 110.0)
            self.assertEqual(row.take_profit, 150.0)

    def test_save_analysis_history_without_snapshot(self) -> None:
        """關閉快照儲存時不寫入 context_snapshot"""
        result = self._build_result()

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_002",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot={"foo": "bar"},
            save_snapshot=False
        )

        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            self.assertIsNone(row.context_snapshot)

    def test_save_analysis_history_persists_model_used(self) -> None:
        """model_used should be persisted in raw_result for history detail."""
        result = self._build_result()
        result.model_used = "gemini/gemini-2.0-flash"

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_003",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_003").first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            payload = json.loads(row.raw_result or "{}")
            self.assertEqual(payload.get("model_used"), "gemini/gemini-2.0-flash")

    def test_save_analysis_history_backfills_missing_tw_market_fear_snapshot(self) -> None:
        """TW stock/ETF reports must persist VIXTWN even if the pipeline attach was missed."""
        result = AnalysisResult(
            code="006208",
            name="富邦台50",
            sentiment_score=43,
            trend_prediction="中性",
            operation_advice="觀望",
            analysis_summary="summary",
        )
        result.instrument_type = "etf"

        with patch(
            "src.services.taifex_vixtwn_fetcher.fetch_latest_vixtwn",
            return_value=SimpleNamespace(
                value=44.27,
                as_of="2026-06-26",
                source="taifex",
                source_url_key="taifex_vixtwn_daily_txt",
                data_gap_reason=None,
            ),
        ):
            saved = self.db.save_analysis_history(
                result=result,
                query_id="query_vixtwn_backfill",
                report_type="full",
                news_content=None,
                context_snapshot=None,
                save_snapshot=False,
            )

        self.assertEqual(saved, 1)
        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_vixtwn_backfill"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            payload = json.loads(row.raw_result or "{}")
            snapshot = payload.get("market_fear_index_snapshot")
            self.assertEqual(snapshot["kind"], "vixtwn")
            self.assertEqual(snapshot["value"], 44.27)
            self.assertEqual(snapshot["as_of"], "2026-06-26")

    def test_update_analysis_history_diagnostics_preserves_snapshot_fields(self) -> None:
        """通知傳送後補寫 diagnostics 時，不應覆蓋已有上下文欄位。"""
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id="query_diag_patch",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot={
                "enhanced_context": {"code": "2330"},
                "diagnostics": {
                    "trace_id": "trace-1",
                    "query_id": "query_diag_patch",
                    "stock_code": "2330",
                    "notification_runs": [],
                },
            },
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        updated = self.db.update_analysis_history_diagnostics(
            query_id="query_diag_patch",
            code="2330",
            notification_runs=[
                {
                    "channel": "report",
                    "status": "success",
                    "success": True,
                }
            ],
        )

        self.assertEqual(updated, 1)
        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_diag_patch"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            snapshot = json.loads(row.context_snapshot or "{}")
            self.assertEqual(snapshot["enhanced_context"]["code"], "2330")
            notification_run = snapshot["diagnostics"]["notification_runs"][-1]
            self.assertEqual(notification_run["status"], "success")
            self.assertEqual(notification_run["trace_id"], "trace-1")

    def test_history_detail_hides_placeholder_model_used(self) -> None:
        """Placeholder model values should be normalized to None in detail response."""
        result = self._build_result()
        result.model_used = "unknown"

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_004",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_004").first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        service = HistoryService(self.db)
        detail = service.get_history_detail_by_id(record_id)
        self.assertIsNotNone(detail)
        self.assertIsNone(detail.get("model_used"))

    def test_history_list_includes_timeline_summary_fields(self) -> None:
        """History list items expose the fields needed by the same-stock timeline drawer."""
        result = self._build_result()
        result.model_used = "gemini/gemini-2.5-pro"
        context_snapshot = {
            "enhanced_context": {
                "realtime": {
                    "price": "51.5",
                    "change_pct": "-4.61%",
                    "volume_ratio": "1.17",
                    "turnover_rate": "11.46",
                },
            },
        }

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_timeline_summary",
            report_type="detailed",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        service = HistoryService(self.db)
        payload = service.get_history_list(stock_code="2330.TW", page=1, limit=5)

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["stock_code"], "2330")
        self.assertEqual(item["trend_prediction"], "看多")
        self.assertEqual(item["analysis_summary"], "基本面穩健，短期震盪")
        self.assertEqual(item["operation_advice"], "持有")
        self.assertEqual(item["model_used"], "gemini/gemini-2.5-pro")
        self.assertEqual(item["current_price"], 51.5)
        self.assertEqual(item["change_pct"], -4.61)
        self.assertEqual(item["volume_ratio"], 1.17)
        self.assertEqual(item["turnover_rate"], 11.46)

    def test_history_list_matches_equivalent_suffixed_stock_codes(self) -> None:
        """Same-stock history should include rows saved with supported TW/US suffixes."""

        def save_record(code: str, query_id: str) -> None:
            result = self._build_result()
            result.code = code
            if "AAPL" in code:
                result.name = "Apple"
            saved = self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type="simple",
                news_content="新聞摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertEqual(saved, 1)

        save_record("2330.TW", "query_tw_suffix")
        save_record("2330", "query_tw_plain")
        save_record("AAPL.US", "query_us_suffix")
        save_record("AAPL", "query_us_plain")

        service = HistoryService(self.db)

        tw_from_suffix = service.get_history_list(stock_code="2330.TW", page=1, limit=10)
        self.assertEqual(tw_from_suffix["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in tw_from_suffix["items"]},
            {"2330.TW", "2330"},
        )

        tw_from_plain = service.get_history_list(stock_code="2330", page=1, limit=10)
        self.assertEqual(tw_from_plain["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in tw_from_plain["items"]},
            {"2330.TW", "2330"},
        )

        us_from_suffix = service.get_history_list(stock_code="AAPL.US", page=1, limit=10)
        self.assertEqual(us_from_suffix["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in us_from_suffix["items"]},
            {"AAPL.US", "AAPL"},
        )

        us_from_plain = service.get_history_list(stock_code="AAPL", page=1, limit=10)
        self.assertEqual(us_from_plain["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in us_from_plain["items"]},
            {"AAPL.US", "AAPL"},
        )

    def test_history_list_matches_tw_etf_letter_suffix_variants(self) -> None:
        """TW ETF letter-suffix forms should match their canonical .TW variants."""

        def save_record(code: str, query_id: str) -> None:
            result = self._build_result()
            result.code = code
            result.name = "主動統一台股增長"
            saved = self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type="simple",
                news_content="新聞摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertEqual(saved, 1)

        save_record("00981A", "query_tw_letter")
        save_record("00981A.TW", "query_tw_letter_suffix")

        service = HistoryService(self.db)

        tw_from_suffix = service.get_history_list(stock_code="00981A.TW", page=1, limit=10)
        self.assertEqual(tw_from_suffix["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in tw_from_suffix["items"]},
            {"00981A", "00981A.TW"},
        )

        tw_from_plain = service.get_history_list(stock_code="00981A", page=1, limit=10)
        self.assertEqual(tw_from_plain["total"], 2)
        self.assertEqual(
            {item["stock_code"] for item in tw_from_plain["items"]},
            {"00981A", "00981A.TW"},
        )

    def test_history_list_matches_tw_suffixed_variants(self) -> None:
        """TW suffix and bare variants should be treated as the same TW stock."""

        def save_record(code: str, query_id: str) -> None:
            result = self._build_result()
            result.code = code
            saved = self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type="simple",
                news_content="新聞摘要",
                context_snapshot=None,
                save_snapshot=False,
            )
            self.assertEqual(saved, 1)

        save_record("2330.TW", "query_tw_suffix")
        save_record("2330", "query_tw_plain")

        service = HistoryService(self.db)
        expected = {"2330.TW", "2330"}

        from_suffix = service.get_history_list(stock_code="2330.TW", page=1, limit=10)
        self.assertEqual(from_suffix["total"], 2)
        self.assertEqual({item["stock_code"] for item in from_suffix["items"]}, expected)

        from_plain = service.get_history_list(stock_code="2330", page=1, limit=10)
        self.assertEqual(from_plain["total"], 2)
        self.assertEqual({item["stock_code"] for item in from_plain["items"]}, expected)

    def test_history_detail_preserves_zero_change_pct(self) -> None:
        """change_pct=0.0（平盤）應原樣返回，而不是被當成缺失值丟失。

        Regression for issue #1084: history endpoint used `or` chains that
        treated 0.0 as falsy and silently dropped the daily change.
        """
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        context_snapshot = {
            "enhanced_context": {
                "realtime": {"price": 100.0, "change_pct": 0.0},
            }
        }
        query_id = "query_change_pct_zero"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.meta.current_price, 100.0)
        self.assertEqual(report.meta.change_pct, 0.0)

    def test_history_detail_falls_back_to_realtime_quote_raw_change_pct(self) -> None:
        """缺少 enhanced_context.realtime.change_pct 時，應回退到 realtime_quote_raw。

        Regression for issue #1084: previously the realtime_quote_raw fallback
        was only consulted when current_price was missing, so reports with
        price-only enhanced_context lost their change_pct entirely.
        """
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        context_snapshot = {
            "enhanced_context": {
                "realtime": {"price": 200.0},
            },
            "realtime_quote_raw": {"change_pct": 1.23},
        }
        query_id = "query_change_pct_fallback"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.meta.current_price, 200.0)
        self.assertEqual(report.meta.change_pct, 1.23)

    def test_history_detail_uses_quote_availability_daily_fallback_price(self) -> None:
        """TW/US history meta should expose usable daily fallback quote data.

        A missing realtime quote is still a usable quote state when the final
        diagnostics mark daily close fallback as degraded. The report header
        must not remain price-null in that case.
        """
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        context_snapshot = {
            "quote_availability": {
                "status": "degraded",
                "usable": True,
                "source_label": "備援資料",
                "fallback_used": True,
                "reason": "primary_quote_failed_fallback_used",
            },
            "enhanced_context": {
                "today": {"close": 2510.0, "pct_chg": 4.15},
                "yesterday": {"close": 2410.0},
            },
            "realtime_quote_raw": {"source": "yfinance"},
        }
        query_id = "query_quote_availability_daily_fallback"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.meta.current_price, 2510.0)
        self.assertEqual(report.meta.change_pct, 4.15)

    @patch("src.auth.is_auth_enabled", return_value=False)
    def test_history_detail_ignores_non_dict_realtime_quote_raw(self, mock_auth) -> None:
        """GET /api/v1/history/{id} should tolerate truthy non-dict realtime_quote_raw."""
        if TestClient is None or create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        context_snapshot = {
            "enhanced_context": {
                "realtime": {"price": 300.0},
            },
            "realtime_quote_raw": "not-a-dict",
        }
        query_id = "query_change_pct_non_dict_raw"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        static_dir = Path(self._temp_dir.name) / "empty-static"
        static_dir.mkdir(exist_ok=True)
        client = TestClient(create_app(static_dir=static_dir))

        response = client.get(f"/api/v1/history/{record_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["current_price"], 300.0)
        self.assertIsNone(payload["meta"]["change_pct"])

    @patch("src.auth.is_auth_enabled", return_value=False)
    def test_history_news_api_returns_persisted_news_items(self, mock_auth) -> None:
        """GET /api/v1/history/{id}/news should expose persisted related-info items."""
        if TestClient is None or create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        query_id = "query_news_api_001"
        record_id = self._save_history(query_id)
        response = SearchResponse(
            query="2330 台積電 新聞",
            results=[
                SearchResult(
                    title="台積電法說會最新重點",
                    snippet="AI 需求與先進製程仍是市場關注焦點。",
                    url="https://news.example.com/tsmc",
                    source="example.com",
                    published_date="2026-06-19",
                )
            ],
            provider="SearXNG",
            success=True,
        )

        saved = self.db.save_news_intel(
            code="2330",
            name="台積電",
            dimension="latest_news",
            query=response.query,
            response=response,
            query_context={
                "query_id": query_id,
                "query_source": "phase15_6b_test",
            },
        )
        self.assertEqual(saved, 1)

        static_dir = Path(self._temp_dir.name) / "empty-static"
        static_dir.mkdir(exist_ok=True)
        client = TestClient(create_app(static_dir=static_dir))

        api_response = client.get(f"/api/v1/history/{record_id}/news?limit=8")

        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["title"], "台積電法說會最新重點")
        self.assertEqual(payload["items"][0]["snippet"], "AI 需求與先進製程仍是市場關注焦點。")
        self.assertEqual(payload["items"][0]["url"], "https://news.example.com/tsmc")

    @patch("src.auth.is_auth_enabled", return_value=False)
    def test_history_news_api_links_duplicate_relevant_news_to_current_report(self, mock_auth) -> None:
        """Relevant duplicate URLs from prior runs should remain usable by the current report."""
        if TestClient is None or create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        result = AnalysisResult(
            code="3008",
            name="大立光",
            sentiment_score=52,
            trend_prediction="看多",
            operation_advice="觀望",
            analysis_summary="大立光測試摘要",
        )
        query_id = "query_news_rank_3008"
        saved = self.db.save_analysis_history(
            result=result,
            query_id=query_id,
            report_type="full",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        broad_response = SearchResponse(
            query="Largan stock news",
            results=[
                SearchResult(
                    title="Rosen Law Firm Encourages Unrelated Investors",
                    snippet="News Editors' Picks Stock Analysis Stock Market News.",
                    url="https://news.example.com/unrelated-legal",
                    source="example.com",
                    published_date="2026-06-21",
                ),
                SearchResult(
                    title="SEL Manufacturing promoter declares no new encumbrance",
                    snippet="A broad manufacturing update without 大立光 or Largan relevance.",
                    url="https://news.example.com/unrelated-manufacturing",
                    source="example.com",
                    published_date="2026-06-20",
                ),
            ],
            provider="Tavily",
            success=True,
        )
        relevant_response = SearchResponse(
            query="3008 大立光 新聞",
            results=[
                SearchResult(
                    title="大立光(3008)最新目標價曝光",
                    snippet="大立光與 Largan Precision 股價和 CPO 題材更新。",
                    url="https://news.example.com/largan-target",
                    source="example.com",
                    published_date=None,
                )
            ],
            provider="SearXNG",
            success=True,
        )

        prior_saved = self.db.save_news_intel(
            code="3008",
            name="大立光",
            dimension="latest_news",
            query=relevant_response.query,
            response=relevant_response,
            query_context={"query_id": "prior_query_with_largan_news"},
        )
        self.assertEqual(prior_saved, 1)

        self.db.save_news_intel(
            code="3008",
            name="大立光",
            dimension="latest_news",
            query=broad_response.query,
            response=broad_response,
            query_context={"query_id": query_id},
        )
        current_relevant_saved = self.db.save_news_intel(
            code="3008",
            name="大立光",
            dimension="latest_news",
            query=relevant_response.query,
            response=relevant_response,
            query_context={"query_id": query_id},
        )
        self.assertEqual(current_relevant_saved, 0)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == query_id,
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        static_dir = Path(self._temp_dir.name) / "empty-static"
        static_dir.mkdir(exist_ok=True)
        client = TestClient(create_app(static_dir=static_dir))

        api_response = client.get(f"/api/v1/history/{record_id}/news?limit=3")

        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertGreaterEqual(payload["total"], 3)
        self.assertEqual(payload["items"][0]["title"], "大立光(3008)最新目標價曝光")
        self.assertIn("大立光", payload["items"][0]["snippet"])

    def test_history_detail_accepts_dict_raw_result(self) -> None:
        """_record_to_detail_dict should handle dict raw_result without json.loads errors."""
        result = self._build_result()
        result.model_used = "gemini/gemini-2.0-flash"
        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_005",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_005").first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            row.raw_result = {"model_used": "unknown", "extra": "v"}

            service = HistoryService(self.db)
            detail = service._record_to_detail_dict(row)

        self.assertIsNotNone(detail)
        self.assertIsInstance(detail.get("raw_result"), dict)
        self.assertIsNone(detail.get("model_used"))

    def test_history_detail_prefers_raw_sniper_strings(self) -> None:
        """History detail should display the original sniper point strings from raw_result."""
        result = self._build_result()
        result.dashboard = {
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "理想買進點：125.5元",
                    "secondary_buy": "120-121 元分批",
                    "stop_loss": "跌破 110 元止損",
                    "take_profit": "目標位：150.0元",
                }
            }
        }

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_006",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_006").first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        service = HistoryService(self.db)
        detail = service.get_history_detail_by_id(record_id)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.get("ideal_buy"), "理想買進點：125.5元")
        self.assertEqual(detail.get("secondary_buy"), "120-121 元分批")
        self.assertEqual(detail.get("stop_loss"), "跌破 110 元止損")
        self.assertEqual(detail.get("take_profit"), "目標位：150.0元")

    def test_history_detail_falls_back_to_numeric_sniper_columns(self) -> None:
        """History detail should still fall back to stored numeric sniper columns when raw strings are unavailable."""
        result = self._build_result()
        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_007",
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == "query_007").first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            row.ideal_buy = 125.5
            row.secondary_buy = 120.0
            row.stop_loss = 110.0
            row.take_profit = 150.0
            row.raw_result = json.dumps({"model_used": "gemini/gemini-2.0-flash"})
            session.commit()
            record_id = row.id

        service = HistoryService(self.db)
        detail = service.get_history_detail_by_id(record_id)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.get("ideal_buy"), "125.5")
        self.assertEqual(detail.get("secondary_buy"), "120.0")
        self.assertEqual(detail.get("stop_loss"), "110.0")
        self.assertEqual(detail.get("take_profit"), "150.0")

    def test_history_detail_uses_fundamental_snapshot_fallback_when_context_missing(self) -> None:
        """When context_snapshot is disabled, detail API should fallback to fundamental_snapshot."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        result = self._build_result()
        query_id = "query_fundamental_fallback_001"
        saved = self.db.save_analysis_history(
            result=result,
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        self.db.save_fundamental_snapshot(
            query_id=query_id,
            code="2330",
            payload={
                "belong_boards": [{"name": "白酒", "type": "行業"}],
                "boards": {
                    "data": {
                        "top": [{"name": "白酒", "change_pct": 2.6}],
                        "bottom": [],
                    }
                },
                "earnings": {
                    "data": {
                        "financial_report": {"report_date": "2025-12-31", "revenue": 1000},
                        "dividend": {"ttm_dividend_yield_pct": 2.6, "ttm_cash_dividend_per_share": 1.3},
                    }
                }
            },
        )

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.details.financial_report["report_date"], "2025-12-31")
        self.assertEqual(report.details.dividend_metrics["ttm_dividend_yield_pct"], 2.6)
        self.assertEqual(report.details.belong_boards, [{"name": "白酒", "type": "行業"}])
        self.assertEqual(report.details.sector_rankings["top"][0]["name"], "白酒")

    def test_history_detail_preserves_unavailable_board_rankings_state(self) -> None:
        """Failed board ranking blocks should remain unavailable in detail response."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        query_id = "query_fundamental_failed_boards_001"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        fallback_fundamental = {
            "belong_boards": [{"name": "白酒", "type": "行業"}],
            "boards": {
                "status": "failed",
                "data": {},
            },
        }
        saved_snapshot = self.db.save_fundamental_snapshot(
            query_id=query_id,
            code="2330",
            payload=fallback_fundamental,
        )
        self.assertEqual(saved_snapshot, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.details.belong_boards, [{"name": "白酒", "type": "行業"}])
        self.assertIsNone(report.details.sector_rankings)

    def test_history_detail_returns_null_fundamental_fields_when_snapshot_absent(self) -> None:
        """Detail API should keep new fields nullable when no context/fundamental snapshot exists."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        query_id = "query_fundamental_fallback_002"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertIsNone(report.details.financial_report)
        self.assertIsNone(report.details.dividend_metrics)
        self.assertEqual(report.details.belong_boards, [])
        self.assertIsNone(report.details.sector_rankings)

    def test_history_detail_returns_empty_related_boards_for_non_cn(self) -> None:
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        result = AnalysisResult(
            code="AAPL",
            name="Apple",
            sentiment_score=65,
            trend_prediction="Bullish",
            operation_advice="Hold",
            analysis_summary="US stock test",
        )
        query_id = "query_non_cn_board_001"
        saved = self.db.save_analysis_history(
            result=result,
            query_id=query_id,
            report_type="simple",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.details.belong_boards, [])
        self.assertIsNone(report.details.sector_rankings)

    def test_history_detail_reads_agent_snapshot_related_boards_shape(self) -> None:
        """Agent-mode snapshots store fundamental_context/realtime_quote at the top level."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        context_snapshot = {
            "fundamental_context": {
                "belong_boards": [{"name": "白酒", "type": "行業"}],
                "boards": {
                    "data": {
                        "top": [{"name": "白酒", "change_pct": 2.8}],
                        "bottom": [],
                    }
                },
            },
            "realtime_quote": {
                "price": 1888.0,
                "change_pct": 1.56,
            },
        }
        query_id = "query_agent_snapshot_boards_001"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(report.meta.current_price, 1888.0)
        self.assertEqual(report.meta.change_pct, 1.56)
        self.assertEqual(report.details.belong_boards, [{"name": "白酒", "type": "行業"}])
        self.assertEqual(report.details.sector_rankings["top"][0]["name"], "白酒")

    def test_history_detail_returns_overview_and_sanitizes_snapshot(self) -> None:
        """History detail exposes the public overview separately from raw snapshot JSON."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        overview = _analysis_context_pack_overview()
        phase_summary = _market_phase_summary()
        query_id = "query_context_pack_overview_001"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot={
                "enhanced_context": {"code": "2330"},
                "analysis_context_pack_overview": overview,
                "market_phase_summary": {
                    **phase_summary,
                    "market_phase_context": {"raw": True},
                },
            },
            save_snapshot=True,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertEqual(
            report.details.analysis_context_pack_overview.metadata.trigger_source,
            "api",
        )
        self.assertEqual(
            report.details.analysis_context_pack_overview.data_quality.overall_score,
            100,
        )
        self.assertIsNotNone(report.meta.market_phase_summary)
        self.assertEqual(report.meta.market_phase_summary.phase, "intraday")
        self.assertEqual(report.meta.market_phase_summary.minutes_to_close, 300)
        self.assertEqual(report.details.analysis_context_pack_overview.metadata.news_result_count, 2)
        self.assertNotIn(
            "analysis_context_pack_overview",
            report.details.context_snapshot,
        )
        self.assertNotIn(
            "market_phase_summary",
            report.details.context_snapshot,
        )

    def test_history_detail_handles_missing_overview_when_snapshot_disabled(self) -> None:
        """SAVE_CONTEXT_SNAPSHOT=false style records should not require an overview."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        query_id = "query_context_pack_snapshot_disabled_001"
        saved = self.db.save_analysis_history(
            result=self._build_result(),
            query_id=query_id,
            report_type="simple",
            news_content="新聞摘要",
            context_snapshot={
                "enhanced_context": {"code": "2330"},
                "analysis_context_pack_overview": _analysis_context_pack_overview(),
            },
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(AnalysisHistory.query_id == query_id).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id
            self.assertIsNone(row.context_snapshot)

        report = get_history_detail(str(record_id), db_manager=self.db)
        self.assertIsNone(report.meta.market_phase_summary)
        self.assertIsNone(report.details.analysis_context_pack_overview)
        self.assertIsNone(report.details.context_snapshot)

    def test_history_markdown_localizes_english_report_and_placeholder_name(self) -> None:
        """History markdown should preserve report_language for English reports."""
        result = AnalysisResult(
            code="AAPL",
            name="股票AAPL",
            sentiment_score=78,
            trend_prediction="Bullish",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
            dashboard={
                "core_conclusion": {
                    "one_sentence": "Favor buying on pullbacks.",
                    "position_advice": {
                        "no_position": "Open a starter position.",
                        "has_position": "Hold and trail the stop.",
                    },
                },
                "intelligence": {
                    "risk_alerts": [],
                },
                "battle_plan": {
                    "sniper_points": {
                        "ideal_buy": "180-182",
                        "stop_loss": "172",
                        "take_profit": "195",
                    }
                },
            },
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_english_markdown_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_english_markdown_001"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertIsNotNone(markdown)
        self.assertIn("Stock Analysis Report", markdown)
        self.assertIn("Core Conclusion", markdown)
        self.assertIn("Unnamed Stock (AAPL)", markdown)
        self.assertNotIn("核心結論", markdown)

    def test_history_markdown_returns_persisted_market_review_report(self) -> None:
        """Market review history should return the saved Markdown without rebuilding a stock report."""
        result = AnalysisResult(
            code="MARKET",
            name="大盤覆盤",
            sentiment_score=50,
            trend_prediction="大盤覆盤",
            operation_advice="檢視覆盤",
            analysis_summary="今日大盤覆盤",
            raw_response="# 🎯 大盤覆盤\n\n## 今日大盤\n\n覆盤正文",
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="market_review_query_001",
            report_type="market_review",
            news_content="## 今日大盤\n\n覆盤正文",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "market_review_query_001"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertEqual(markdown, "# 🎯 大盤覆盤\n\n## 今日大盤\n\n覆盤正文")

    def test_history_markdown_suppresses_deprecated_chip_structure(self) -> None:
        result = AnalysisResult(
            code="2330",
            name="台積電",
            sentiment_score=72,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="穩健",
            dashboard={
                "data_perspective": {
                    "chip_structure": {
                        "profit_ratio": "資料缺失，無法判斷",
                        "avg_cost": "資料缺失，無法判斷",
                        "concentration": "資料缺失，無法判斷",
                        "chip_health": "資料缺失，無法判斷",
                    }
                }
            },
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_chip_unavailable_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_chip_unavailable_001"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertIsNotNone(markdown)
        self.assertNotIn("籌碼", markdown)
        self.assertEqual(markdown.count("資料缺失，無法判斷"), 0)

    def test_history_detail_returns_persisted_market_review_report(self) -> None:
        """Market review detail should surface the saved recap content for Web history clicks."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        report_content = "# 🎯 大盤覆盤\n\n## 今日大盤\n\n覆盤正文"
        result = AnalysisResult(
            code="MARKET",
            name="大盤覆盤",
            sentiment_score=50,
            trend_prediction="大盤覆盤",
            operation_advice="檢視覆盤",
            analysis_summary="今日大盤覆盤",
            raw_response=report_content,
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="market_review_query_detail_001",
            report_type="market_review",
            news_content="## 今日大盤\n\n覆盤正文",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "market_review_query_detail_001"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)

        self.assertEqual(report.meta.report_type, "market_review")
        self.assertEqual(report.summary.analysis_summary, report_content)
        self.assertEqual(report.details.news_content, report_content)

    def test_history_detail_localizes_english_summary_fields(self) -> None:
        """History detail should localize summary enums for English reports."""
        if get_history_detail is None:
            self.skipTest("fastapi is not installed in this test environment")

        result = AnalysisResult(
            code="AAPL",
            name="股票AAPL",
            sentiment_score=78,
            trend_prediction="看多",
            operation_advice="買進",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_english_detail_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_english_detail_001"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        report = get_history_detail(str(record_id), db_manager=self.db)

        self.assertEqual(report.meta.report_language, "en")
        self.assertEqual(report.meta.stock_name, "Unnamed Stock")
        self.assertEqual(report.summary.operation_advice, "Buy")
        self.assertEqual(report.summary.trend_prediction, "Bullish")
        self.assertEqual(report.summary.sentiment_label, "Bullish")

    def test_history_markdown_uses_safe_bias_emoji_for_english_status(self) -> None:
        """English bias status should keep the correct non-risk emoji in markdown."""
        result = AnalysisResult(
            code="AAPL",
            name="股票AAPL",
            sentiment_score=80,
            trend_prediction="Bullish",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
            dashboard={
                "data_perspective": {
                    "price_position": {
                        "current_price": 190.5,
                        "ma5": 188.0,
                        "ma10": 184.5,
                        "ma20": 179.2,
                        "bias_ma5": 1.33,
                        "bias_status": "Safe",
                        "support_level": 184.5,
                        "resistance_level": 195.0,
                    }
                }
            },
        )

        saved = self.db.save_analysis_history(
            result=result,
            query_id="query_english_markdown_bias_001",
            report_type="full",
            news_content="news",
            context_snapshot=None,
            save_snapshot=False,
        )
        self.assertEqual(saved, 1)

        with self.db.get_session() as session:
            row = session.query(AnalysisHistory).filter(
                AnalysisHistory.query_id == "query_english_markdown_bias_001"
            ).first()
            if row is None:
                self.fail("未找到儲存的歷史記錄")
            record_id = row.id

        markdown = HistoryService(self.db).get_markdown_report(str(record_id))

        self.assertIsNotNone(markdown)
        self.assertIn("✅Safe", markdown)
        self.assertNotIn("🚨Safe", markdown)

    def test_delete_analysis_history_records_also_cleans_backtests(self) -> None:
        """刪除歷史記錄時應一併清理關聯回測結果。"""
        record_id = self._save_history("query_delete_001")

        with self.db.session_scope() as session:
            session.add(BacktestResult(
                analysis_history_id=record_id,
                code="2330",
                analysis_date=None,
                eval_window_days=10,
                engine_version="v1",
                eval_status="pending",
            ))

        deleted = self.db.delete_analysis_history_records([record_id])
        self.assertEqual(deleted, 1)

        with self.db.get_session() as session:
            self.assertIsNone(session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first())
            self.assertEqual(
                session.query(BacktestResult).filter(BacktestResult.analysis_history_id == record_id).count(),
                0,
            )

    @patch("src.auth.is_auth_enabled", return_value=False)
    def test_delete_history_api_deletes_selected_records(self, mock_auth) -> None:
        """DELETE /api/v1/history should remove only the requested records."""
        if TestClient is None or create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        record_id_1 = self._save_history("query_delete_api_001")
        record_id_2 = self._save_history("query_delete_api_002")

        static_dir = Path(self._temp_dir.name) / "empty-static"
        static_dir.mkdir(exist_ok=True)
        client = TestClient(create_app(static_dir=static_dir))

        response = client.request(
            "DELETE",
            "/api/v1/history",
            json={"record_ids": [record_id_1]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("deleted"), 1)

        with self.db.get_session() as session:
            self.assertIsNone(session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id_1).first())
            self.assertIsNotNone(session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id_2).first())

    def test_generate_single_stock_markdown_includes_appendix_for_valid_mermaid(self) -> None:
        """Phase 18A: a valid value_network_mermaid renders as a fenced appendix near the footer."""
        from datetime import datetime as _datetime

        result = self._build_result()
        result.value_network_mermaid = "flowchart TB\n  A[供應商] --> B[公司]"
        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))

        service = HistoryService(self.db)
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertIn("## 附錄：價值網路圖", markdown)
        self.assertIn("```mermaid", markdown)
        self.assertIn("flowchart TB\n  A[供應商] --> B[公司]", markdown)

        appendix_index = markdown.index("## 附錄：價值網路圖")
        footer_index = markdown.index("*報告生成時間")
        self.assertLess(appendix_index, footer_index)

    def test_generate_single_stock_markdown_prepends_mermaid_init_line_exactly_once(self) -> None:
        """Phase 18E v3: the LLM never outputs %%{init...}%% — history_service prepends it
        deterministically inside the fenced mermaid block, exactly once, after the validated body."""
        from datetime import datetime as _datetime
        from src.services.history_service import MERMAID_INIT_LINE

        result = self._build_result()
        result.value_network_mermaid = "flowchart TB\n  A[供應商] --> B[公司]"
        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))

        service = HistoryService(self.db)
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertEqual(markdown.count(MERMAID_INIT_LINE), 1)

        fence_index = markdown.index("```mermaid")
        init_index = markdown.index(MERMAID_INIT_LINE)
        flowchart_index = markdown.index("flowchart TB\n  A[供應商] --> B[公司]")
        self.assertLess(fence_index, init_index)
        self.assertLess(init_index, flowchart_index)

    def test_generate_single_stock_markdown_omits_appendix_when_none(self) -> None:
        """When value_network_mermaid is None, no appendix section is added and generation does not raise."""
        from datetime import datetime as _datetime

        result = self._build_result()
        result.value_network_mermaid = None
        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))

        service = HistoryService(self.db)
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertNotIn("附錄：價值網路圖", markdown)

    def test_generate_single_stock_markdown_omits_appendix_when_invalid(self) -> None:
        """An invalid (forbidden diagram type) value_network_mermaid is silently dropped."""
        from datetime import datetime as _datetime

        result = self._build_result()
        result.value_network_mermaid = "sequenceDiagram\n  Alice->>Bob: Hello"
        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))

        service = HistoryService(self.db)
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertNotIn("附錄：價值網路圖", markdown)

    def test_rebuild_analysis_result_carries_value_network_mermaid(self) -> None:
        """Phase 18A: _rebuild_analysis_result carries value_network_mermaid from raw_result."""
        record_id = self._save_history("query_value_network_001")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {
                "code": "2330",
                "name": "台積電",
                "value_network_mermaid": "flowchart TB\n  A[供應商] --> B[公司]",
            }
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt.value_network_mermaid, "flowchart TB\n  A[供應商] --> B[公司]")

    def test_rebuild_analysis_result_defaults_value_network_mermaid_to_none(self) -> None:
        """When raw_result lacks the field, the rebuilt AnalysisResult defaults to None."""
        record_id = self._save_history("query_value_network_002")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {
                "code": "2330",
                "name": "台積電",
            }
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertIsNone(rebuilt.value_network_mermaid)

    def test_rebuild_analysis_result_carries_instrument_type(self) -> None:
        """Phase 19B.1: _rebuild_analysis_result carries instrument_type from raw_result."""
        record_id = self._save_history("query_instrument_type_001")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {
                "code": "0050",
                "name": "元大台灣50",
                "instrument_type": "etf",
            }
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt.instrument_type, "etf")

    def test_rebuild_analysis_result_defaults_instrument_type_to_unknown(self) -> None:
        """Phase 19B.1: old history records (no instrument_type key) rebuild as 'unknown',
        not a crash and not a missing attribute — backward compatibility contract."""
        record_id = self._save_history("query_instrument_type_002")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {
                "code": "2330",
                "name": "台積電",
            }
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt.instrument_type, "unknown")

    def test_rebuild_analysis_result_carries_exposure_and_market_risk_snapshot(self) -> None:
        """Phase 19B.3: _rebuild_analysis_result carries exposure_snapshot/
        market_risk_snapshot from raw_result, mirroring 19B.2's snapshot fields."""
        record_id = self._save_history("query_exposure_market_risk_001")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {
                "code": "0050",
                "name": "元大台灣50",
                "instrument_type": "etf",
                "exposure_snapshot": {"leverage_factor": 1, "data_gap_fields": []},
                "market_risk_snapshot": {"vix_level": 18.2, "source": "yfinance"},
                "market_fear_index_snapshot": {"market": "tw", "kind": "vixtwn", "value": 44.27},
            }
            with patch("src.services.taifex_vixtwn_fetcher.fetch_latest_vixtwn", side_effect=RuntimeError("should not fetch")):
                rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt.exposure_snapshot, {"leverage_factor": 1, "data_gap_fields": []})
        self.assertEqual(rebuilt.market_risk_snapshot, {"vix_level": 18.2, "source": "yfinance"})
        self.assertEqual(rebuilt.market_fear_index_snapshot, {"market": "tw", "kind": "vixtwn", "value": 44.27})

    def test_rebuild_analysis_result_defaults_exposure_market_risk_to_none(self) -> None:
        """Old history records (no exposure/market_risk keys) rebuild as None,
        not a crash — same backward compatibility contract as 19B.1/19B.2."""
        record_id = self._save_history("query_exposure_market_risk_002")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {"code": "2330", "name": "台積電"}
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertIsNone(rebuilt.exposure_snapshot)
        self.assertIsNone(rebuilt.market_risk_snapshot)
        self.assertIsNone(rebuilt.market_fear_index_snapshot)

    def test_generate_single_stock_markdown_renders_exposure_and_market_risk_for_etf(self) -> None:
        """Phase 19B.3: markdown renders the new sections for etf/index only,
        positioned after the 19B.2 valuation/fundamental section."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "etf"
        result.exposure_snapshot = {"underlying_index": "S&P 500", "leverage_factor": 2, "data_gap_fields": []}
        result.market_risk_snapshot = {
            "vix_level": 18.2, "vix_status": "平穩", "spx_change_pct": 0.4,
            "source": "yfinance", "data_gap_fields": [],
        }
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertIn("ETF／指數曝險摘要", markdown)
        self.assertIn("市場風險溫度計", markdown)
        self.assertIn("S&P 500", markdown)
        self.assertIn("18.2", markdown)

    def test_generate_single_stock_markdown_omits_exposure_section_for_stock(self) -> None:
        """19B.3A: stock-type results must never show the etf/index-only
        exposure section, even if the field is somehow populated
        (defensive — should not happen given the pipeline gate)."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "stock"
        result.exposure_snapshot = {"underlying_index": "should not render"}
        result.market_risk_snapshot = {"vix_level": 18.2}
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertNotIn("ETF／指數曝險摘要", markdown)

    def test_generate_single_stock_markdown_renders_market_risk_for_stock(self) -> None:
        """19B.3A: stock-type results DO render the market risk thermometer
        section (the broadened gate), as long as market_risk_snapshot is set."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "stock"
        result.exposure_snapshot = None
        result.market_risk_snapshot = {
            "vix_level": 18.2, "vix_status": "平穩", "spx_change_pct": 0.4,
            "source": "yfinance", "data_gap_fields": [],
        }
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertIn("市場風險溫度計", markdown)
        self.assertIn("18.2", markdown)
        self.assertNotIn("ETF／指數曝險摘要", markdown)

    def test_generate_single_stock_markdown_omits_both_sections_for_unknown(self) -> None:
        """19B.3A: unknown instrument_type remains a no-op for both sections,
        even if fields are somehow populated (defensive)."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "unknown"
        result.exposure_snapshot = {"underlying_index": "should not render"}
        result.market_risk_snapshot = {"vix_level": 18.2}
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertNotIn("ETF／指數曝險摘要", markdown)
        self.assertNotIn("市場風險溫度計", markdown)

    def test_market_risk_markdown_formats_vix_level_to_two_decimals(self) -> None:
        """Phase 19D-F1: raw binary-float VIX values must be rounded to 2dp in
        the rendered Markdown — regression guard for 18.889999389648438."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "stock"
        result.exposure_snapshot = None
        result.market_risk_snapshot = {
            "vix_level": 18.889999389648438,
            "vix_status": "平穩",
            "spx_change_pct": -0.01,
            "source": "yfinance",
            "data_gap_fields": [],
        }
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertIn("18.89", markdown)
        self.assertNotIn("18.889999389648438", markdown)
        self.assertIn("市場風險溫度計", markdown)

    def test_market_risk_markdown_formats_vix_level_none_as_gap(self) -> None:
        """Phase 19D-F1: vix_level=None renders 資料不足, not 'None'."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "stock"
        result.exposure_snapshot = None
        result.market_risk_snapshot = {
            "vix_level": None,
            "vix_status": None,
            "spx_change_pct": None,
            "gap_reason": "資料來源不可用",
            "data_gap_fields": ["vix_level", "vix_status", "spx_change_pct"],
        }
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertNotIn("None", markdown)
        self.assertIn("市場風險溫度計", markdown)

    def test_generate_single_stock_markdown_shows_tw_gap_reason(self) -> None:
        """TW market_risk_snapshot this phase always carries a gap_reason
        instead of source/as_of — markdown must surface that reason verbatim."""
        from datetime import datetime as _datetime
        from src.services.exposure_market_risk_snapshot import TW_MARKET_RISK_GAP_REASON

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "index"
        result.exposure_snapshot = {"data_gap_fields": ["underlying_index", "leverage_factor", "is_leveraged", "is_inverse"]}
        result.market_risk_snapshot = {
            "vix_level": None, "vix_status": None, "spx_change_pct": None,
            "source": None, "gap_reason": TW_MARKET_RISK_GAP_REASON, "data_gap_fields": [],
        }
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertIn(TW_MARKET_RISK_GAP_REASON, markdown)

    def test_rebuild_analysis_result_carries_multi_period_trend_snapshot(self) -> None:
        """Phase 19B.4: _rebuild_analysis_result carries multi_period_trend_snapshot
        from raw_result, mirroring 19B.3's snapshot fields."""
        record_id = self._save_history("query_multi_period_trend_001")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            snapshot = {
                "source": "db_cache",
                "periods": [{"period": "5D", "label": "1週", "change_pct": 1.2, "data_gap_fields": []}],
                "data_gap_fields": [],
            }
            raw_result = {
                "code": "2330",
                "name": "台積電",
                "instrument_type": "stock",
                "multi_period_trend_snapshot": snapshot,
            }
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertEqual(rebuilt.multi_period_trend_snapshot, snapshot)

    def test_rebuild_analysis_result_defaults_multi_period_trend_snapshot_to_none(self) -> None:
        """Old history records (no multi_period_trend_snapshot key) rebuild as
        None, not a crash — same backward compatibility contract as 19B.1-19B.3."""
        record_id = self._save_history("query_multi_period_trend_002")

        with self.db.get_session() as session:
            record = session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first()
            self.assertIsNotNone(record)

            service = HistoryService(self.db)
            raw_result = {"code": "2330", "name": "台積電"}
            rebuilt = service._rebuild_analysis_result(raw_result, record)

        self.assertIsNotNone(rebuilt)
        self.assertIsNone(rebuilt.multi_period_trend_snapshot)

    def test_generate_single_stock_markdown_renders_multi_period_trend_for_stock_etf_index(self) -> None:
        """Phase 19B.4: markdown renders the new section for stock/etf/index,
        positioned after the market-risk thermometer section."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        for instrument_type in ("stock", "etf", "index"):
            result = self._build_result()
            result.instrument_type = instrument_type
            result.multi_period_trend_snapshot = {
                "source": "db_cache",
                "as_of": "2026-04-09",
                "periods": [
                    {
                        "period": "5D", "label": "1週", "change_pct": 3.5,
                        "drawdown_from_high_pct": -1.2, "price_vs_ma_pct": 0.8,
                        "trend_status": "neutral", "data_gap_fields": [],
                    },
                    {
                        "period": "252D", "label": "52週", "change_pct": None,
                        "drawdown_from_high_pct": None, "price_vs_ma_pct": None,
                        "trend_status": "insufficient_data",
                        "data_gap_fields": ["change_pct", "drawdown_from_high_pct", "price_vs_ma_pct"],
                    },
                ],
                "data_gap_fields": ["252D"],
            }
            markdown = service._generate_single_stock_markdown(result, record)

            self.assertIn("多週期趨勢快照", markdown)
            self.assertIn("1週", markdown)
            self.assertIn("資料不足", markdown)
            # Mermaid appendix (if present) must still come after this section.
            market_risk_idx = markdown.find("多週期趨勢快照")
            battle_idx = markdown.find("作戰計")
            if battle_idx != -1:
                self.assertLess(market_risk_idx, battle_idx)

    def test_generate_single_stock_markdown_omits_multi_period_trend_for_unknown(self) -> None:
        """Unknown instrument_type remains a no-op, even if the field is
        somehow populated (defensive — should not happen given the pipeline gate)."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        result = self._build_result()
        result.instrument_type = "unknown"
        result.multi_period_trend_snapshot = {
            "periods": [{"period": "5D", "label": "1週", "change_pct": 1.0, "data_gap_fields": []}],
            "data_gap_fields": [],
        }
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertNotIn("多週期趨勢快照", markdown)

    def test_generate_single_stock_markdown_title_switches_by_instrument_type(self) -> None:
        """Phase 19B.1: title contract — etf/index get dedicated titles, stock/unknown
        keep the existing generic title (backward compatible with old reports)."""
        from datetime import datetime as _datetime

        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))
        service = HistoryService(self.db)

        cases = {
            "etf": "ETF分析報告",
            "index": "指數分析報告",
            "stock": "股票分析報告",
            "unknown": "股票分析報告",
        }
        for instrument_type, expected_title in cases.items():
            result = self._build_result()
            result.instrument_type = instrument_type
            markdown = service._generate_single_stock_markdown(result, record)
            self.assertIn(expected_title, markdown)

    def test_generate_single_stock_markdown_defaults_title_when_instrument_type_missing(self) -> None:
        """Old AnalysisResult objects without the instrument_type attribute must not crash
        markdown generation and must keep the existing title."""
        from datetime import datetime as _datetime

        result = self._build_result()
        del result.__dict__["instrument_type"]  # simulate a pre-19B.1 in-memory object
        record = SimpleNamespace(created_at=_datetime(2026, 4, 10, 9, 30, 0))

        service = HistoryService(self.db)
        markdown = service._generate_single_stock_markdown(result, record)

        self.assertIn("股票分析報告", markdown)


class HistoryItemSchemaNegativeSentimentTest(unittest.TestCase):
    """Regression: HistoryItem / ReportSummary must accept out-of-range sentiment_score from DB rows."""

    @classmethod
    def setUpClass(cls) -> None:
        """Import schema classes once for all tests, skipping gracefully when deps are missing."""
        try:
            from api.v1.schemas.history import HistoryItem, ReportSummary  # type: ignore
        except ModuleNotFoundError:
            cls.HistoryItem = None
            cls.ReportSummary = None
        else:
            cls.HistoryItem = HistoryItem
            cls.ReportSummary = ReportSummary

    def test_negative_sentiment_score_does_not_raise(self) -> None:
        """Bug #942: sentiment_score=-22 in DB should not cause Pydantic ValidationError."""
        if self.HistoryItem is None:
            self.skipTest("fastapi / pydantic not installed in this test environment")

        item = self.HistoryItem(query_id="q1", stock_code="2330", sentiment_score=-22)
        self.assertEqual(item.sentiment_score, -22)

    def test_out_of_range_high_sentiment_score_does_not_raise(self) -> None:
        """HistoryItem should also accept scores above 100 from legacy data."""
        if self.HistoryItem is None:
            self.skipTest("fastapi / pydantic not installed in this test environment")

        item = self.HistoryItem(query_id="q2", stock_code="2330", sentiment_score=150)
        self.assertEqual(item.sentiment_score, 150)

    def test_none_sentiment_score_is_allowed(self) -> None:
        """HistoryItem.sentiment_score=None should still be valid (optional field)."""
        if self.HistoryItem is None:
            self.skipTest("fastapi / pydantic not installed in this test environment")

        item = self.HistoryItem(query_id="q3", stock_code="2330", sentiment_score=None)
        self.assertIsNone(item.sentiment_score)

    def test_report_summary_negative_sentiment_score_does_not_raise(self) -> None:
        """ReportSummary.sentiment_score should also accept negative values from legacy DB rows."""
        if self.ReportSummary is None:
            self.skipTest("fastapi / pydantic not installed in this test environment")

        summary = self.ReportSummary(sentiment_score=-22)
        self.assertEqual(summary.sentiment_score, -22)

    def test_report_summary_out_of_range_high_sentiment_score_does_not_raise(self) -> None:
        """ReportSummary.sentiment_score should also accept scores above 100 from legacy data."""
        if self.ReportSummary is None:
            self.skipTest("fastapi / pydantic not installed in this test environment")

        summary = self.ReportSummary(sentiment_score=150)
        self.assertEqual(summary.sentiment_score, 150)

    def test_report_summary_none_sentiment_score_is_allowed(self) -> None:
        """ReportSummary.sentiment_score=None should still be valid (optional field)."""
        if self.ReportSummary is None:
            self.skipTest("fastapi / pydantic not installed in this test environment")

        summary = self.ReportSummary(sentiment_score=None)
        self.assertIsNone(summary.sentiment_score)


if __name__ == "__main__":
    unittest.main()

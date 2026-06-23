# -*- coding: utf-8 -*-
"""Regression tests for #1391 Phase 2 run diagnostic summaries."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.v1.endpoints.history import get_history_diagnostics
from src.services.history_service import HistoryService
from src.services.run_diagnostics import build_run_diagnostic_summary, sanitize_diagnostic_text


def _diagnostic_snapshot() -> dict:
    return {
        "trace_id": "trace-p2",
        "task_id": "task-p2",
        "query_id": "query-p2",
        "stock_code": "2330",
        "trigger_source": "api",
        "provider_runs": [
            {
                "trace_id": "trace-p2",
                "data_type": "realtime_quote",
                "provider": "FirstQuote",
                "operation": "get_realtime_quote",
                "success": False,
                "error_type": "TimeoutError",
                "error_message_sanitized": "token=<redacted>",
                "fallback_to": "SecondQuote",
            },
            {
                "trace_id": "trace-p2",
                "data_type": "realtime_quote",
                "provider": "SecondQuote",
                "operation": "get_realtime_quote",
                "success": True,
            },
            {
                "trace_id": "trace-p2",
                "data_type": "daily_data",
                "provider": "DailyFetcher",
                "operation": "get_daily_data",
                "success": True,
                "record_count": 30,
            },
        ],
        "llm_runs": [
            {
                "trace_id": "trace-p2",
                "model": "deepseek-chat",
                "call_type": "analysis",
                "success": True,
                "tokens": 1234,
            }
        ],
        "notification_runs": [
            {
                "trace_id": "trace-p2",
                "channel": "wechat",
                "status": "success",
                "success": True,
            }
        ],
        "history_runs": [
            {
                "trace_id": "trace-p2",
                "report_saved": True,
                "metadata_saved": True,
            }
        ],
    }


def _history_record(*, context_snapshot: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        query_id="query-p2",
        code="2330",
        name="台積電",
        report_type="detailed",
        created_at=datetime(2026, 5, 24, 12, 0, 0),
        raw_result=json.dumps(
            {
                "success": True,
                "model_used": "deepseek-chat",
                "analysis_summary": "測試摘要",
                "news_summary": "新聞摘要",
            },
            ensure_ascii=False,
        ),
        context_snapshot=(
            json.dumps(context_snapshot, ensure_ascii=False)
            if context_snapshot is not None
            else None
        ),
        sentiment_score=60,
        operation_advice="持有",
        trend_prediction="看多",
        analysis_summary="測試摘要",
        news_content="新聞摘要",
        ideal_buy=None,
        secondary_buy=None,
        stop_loss=None,
        take_profit=None,
    )


class _FakeHistoryDb:
    def __init__(self, record: SimpleNamespace | None):
        self.record = record

    def get_analysis_history_by_id(self, record_id: int):
        return self.record if record_id == 1 else None

    def get_latest_analysis_by_query_id(self, query_id: str):
        return self.record if query_id == "query-p2" else None


class _FailingHistoryDb:
    def get_analysis_history_by_id(self, record_id: int):
        raise RuntimeError("database unavailable")

    def get_latest_analysis_by_query_id(self, query_id: str):
        raise RuntimeError("database unavailable")


class RunDiagnosticsP2TestCase(unittest.TestCase):
    def test_news_diagnostics_use_retrieval_evidence_not_model_summary(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["provider_runs"] = [
            {
                "trace_id": "trace-p2",
                "data_type": "realtime_quote",
                "provider": "QuoteFetcher",
                "operation": "get_realtime_quote",
                "success": True,
            },
            {
                "trace_id": "trace-p2",
                "data_type": "daily_data",
                "provider": "DailyFetcher",
                "operation": "get_daily_data",
                "success": True,
                "record_count": 30,
            },
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": None,
            },
            raw_result={
                "success": True,
                "model_used": "deepseek-chat",
                "analysis_summary": "測試摘要",
                "news_summary": "模型生成的新聞摘要",
            },
            report_saved=True,
        )

        self.assertEqual(summary["components"]["news"]["status"], "unknown")
        self.assertEqual(summary["status"], "normal")

    def test_news_summary_string_is_not_treated_as_retrieval_evidence(self) -> None:
        diagnostics = _diagnostic_snapshot()

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": "模型生成的新聞摘要",
            },
            raw_result={
                "success": True,
                "model_used": "deepseek-chat",
                "analysis_summary": "測試摘要",
                "news_summary": "模型生成的新聞摘要",
            },
            report_saved=True,
        )

        self.assertEqual(summary["components"]["news"]["status"], "unknown")

    def test_news_result_count_zero_is_degraded_even_with_formatted_text(self) -> None:
        diagnostics = _diagnostic_snapshot()

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": "【台積電 情報搜尋結果】\n  未找到相關資訊",
                "news_result_count": 0,
            },
            raw_result={
                "success": True,
                "model_used": "deepseek-chat",
                "analysis_summary": "測試摘要",
                "news_summary": "模型生成的新聞摘要",
            },
            report_saved=True,
        )

        self.assertEqual(summary["components"]["news"]["status"], "degraded")
        self.assertEqual(summary["components"]["news"]["details"]["record_count"], 0)

    def test_report_diagnostics_include_search_attempt_metadata(self) -> None:
        diagnostics = _diagnostic_snapshot()
        secret_query = "Authorization: Bearer " + "phase15-test-token"

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": "新聞摘要",
                "news_search": {
                    "enabled": True,
                    "providers_attempted": ["SearXNG", "Tavily"],
                    "query_variants": [
                        "2330 台積電 新聞",
                        "台積電 最新消息",
                        secret_query,
                    ],
                    "attempt_count": 3,
                    "result_count": 4,
                    "fallback_used": True,
                    "final_status": "available",
                    "raw_payload": {"title": "must not leak"},
                },
            },
            raw_result={
                "success": True,
                "model_used": "deepseek-chat",
                "analysis_summary": "測試摘要",
            },
            report_saved=True,
        )

        news_details = summary["components"]["news"]["details"]
        copy_text = summary["copy_text"]
        self.assertEqual(news_details["providers_attempted"], ["SearXNG", "Tavily"])
        self.assertEqual(news_details["attempt_count"], 3)
        self.assertEqual(news_details["result_count"], 4)
        self.assertIs(news_details["fallback_used"], True)
        self.assertEqual(news_details["final_status"], "available")
        self.assertNotIn("raw_payload", news_details)
        self.assertIn("news_search: status=available", copy_text)
        self.assertIn("providers=SearXNG,Tavily", copy_text)
        self.assertIn("attempts=3", copy_text)
        self.assertIn("results=4", copy_text)
        self.assertIn("fallback_used=true", copy_text)
        self.assertIn("2330 台積電 新聞", copy_text)
        self.assertNotIn("phase15-test-token", str(news_details))
        self.assertNotIn("phase15-test-token", copy_text)

    def test_summary_classifies_provider_fallback_as_degraded_and_copy_text_is_sanitized(self) -> None:
        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": _diagnostic_snapshot(),
                "news_content": "新聞摘要",
            },
            raw_result={
                "success": True,
                "model_used": "deepseek-chat",
                "analysis_summary": "測試摘要",
            },
            report_saved=True,
        )

        self.assertEqual(summary["status"], "degraded")
        self.assertEqual(summary["status_label"], "部分降級")
        self.assertEqual(summary["components"]["realtime_quote"]["status"], "degraded")
        self.assertEqual(summary["components"]["daily_data"]["status"], "ok")
        self.assertEqual(summary["components"]["llm"]["status"], "ok")
        self.assertEqual(summary["components"]["notification"]["status"], "ok")
        self.assertIn("trace_id: trace-p2", summary["copy_text"])
        self.assertNotIn("secret", summary["copy_text"])

    def test_empty_realtime_quote_overrides_transport_success_as_missing(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["provider_runs"] = [
            {
                "trace_id": "trace-p2",
                "data_type": "realtime_quote",
                "provider": "YfinanceFetcher",
                "operation": "get_realtime_quote",
                "success": True,
            },
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "quote_availability": {
                    "status": "missing",
                    "usable": False,
                    "primary_source": "YfinanceFetcher",
                    "reason": "empty_or_incomplete_quote",
                    "user_message": "即時行情未取得可用資料",
                },
            },
            raw_result={"success": True, "model_used": "deepseek-chat"},
            report_saved=True,
        )

        quote = summary["components"]["realtime_quote"]
        self.assertEqual(quote["status"], "failed")
        self.assertIn("即時行情未取得可用資料", quote["message"])
        self.assertEqual(quote["details"]["final_quote_status"], "missing")
        self.assertFalse(quote["details"]["quote_usable"])
        self.assertNotIn("YfinanceFetcher 成功", quote["message"])

    def test_usable_quote_fallback_overrides_missing_provider_chain_as_degraded(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["provider_runs"] = [
            {
                "trace_id": "trace-p2",
                "data_type": "realtime_quote",
                "provider": "YfinanceFetcher",
                "operation": "get_realtime_quote",
                "success": False,
                "error_type": "DataFetchError",
                "error_message_sanitized": "empty or incomplete quote",
            },
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "quote_availability": {
                    "status": "degraded",
                    "usable": True,
                    "source_label": "備援資料",
                    "primary_source": "YfinanceFetcher",
                    "fallback_used": True,
                    "reason": "primary_quote_failed_fallback_used",
                    "user_message": "即時行情部分降級，但已取得可用替代資料",
                },
            },
            raw_result={"success": True, "model_used": "deepseek-chat"},
            report_saved=True,
        )

        quote = summary["components"]["realtime_quote"]
        self.assertEqual(quote["status"], "degraded")
        self.assertIn("即時行情部分降級", quote["message"])
        self.assertEqual(quote["details"]["final_quote_status"], "degraded")
        self.assertTrue(quote["details"]["quote_usable"])

    def test_valid_realtime_quote_overrides_provider_chain_as_available(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["provider_runs"] = [
            {
                "trace_id": "trace-p2",
                "data_type": "realtime_quote",
                "provider": "YfinanceFetcher",
                "operation": "get_realtime_quote",
                "success": True,
            },
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "quote_availability": {
                    "status": "available",
                    "usable": True,
                    "source_label": "Yahoo Finance / yfinance",
                    "primary_source": "YfinanceFetcher",
                    "fallback_used": False,
                },
            },
            raw_result={"success": True, "model_used": "deepseek-chat"},
            report_saved=True,
        )

        quote = summary["components"]["realtime_quote"]
        self.assertEqual(quote["status"], "ok")
        self.assertIn("即時行情可用", quote["message"])
        self.assertEqual(quote["details"]["final_quote_status"], "available")
        self.assertTrue(quote["details"]["quote_usable"])

    def test_summary_marks_llm_failure_as_failed(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["llm_runs"] = [
            {
                "trace_id": "trace-p2",
                "model": "deepseek-chat",
                "success": False,
                "error_type": "RuntimeError",
                "error_message_sanitized": "api_key=<redacted>",
            }
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": "新聞摘要",
            },
            raw_result={"success": False, "error_message": "api_key=secret-value"},
            report_saved=True,
        )

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["components"]["llm"]["status"], "failed")
        self.assertIn("LLM 失敗", summary["reason"])
        self.assertNotIn("secret-value", summary["copy_text"])

    def test_copy_text_redacts_authorization_bearer_tokens(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["llm_runs"] = [
            {
                "trace_id": "trace-p2",
                "model": "deepseek-chat",
                "success": False,
                "error_type": "Unauthorized",
                "error_message_sanitized": (
                    "request failed Authorization: Bearer sk-live-token-abc123"
                ),
            }
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": "新聞摘要",
            },
            raw_result={
                "success": False,
                "error_message": "Authorization: Bearer sk-raw-token-xyz789",
            },
            report_saved=True,
        )

        self.assertEqual(summary["status"], "failed")
        self.assertIn("authorization=<redacted>", summary["copy_text"].lower())
        self.assertNotIn("sk-live-token-abc123", summary["copy_text"])
        self.assertNotIn("sk-raw-token-xyz789", summary["copy_text"])
        self.assertNotIn("Bearer sk-", summary["copy_text"])

    def test_copy_text_redacts_env_json_and_proxy_credentials(self) -> None:
        diagnostics = _diagnostic_snapshot()
        diagnostics["llm_runs"] = [
            {
                "trace_id": "trace-p2",
                "model": "deepseek-chat",
                "success": False,
                "error_type": "ProxyError",
                "error_message_sanitized": (
                    "OPENAI_API_KEY=sk-env-secret "
                    "\"api_key\": \"sk-json-secret\" "
                    "proxy http://proxy_user:proxy_pass@proxy.example.com"
                ),
            }
        ]

        summary = build_run_diagnostic_summary(
            context_snapshot={
                "diagnostics": diagnostics,
                "news_content": "news summary",
            },
            raw_result={
                "success": False,
                "error_message": (
                    "DEEPSEEK_API_KEY=sk-raw-secret "
                    "'access_token': 'raw-token-secret' "
                    "http://raw_user:raw_pass@proxy.internal"
                ),
            },
            report_saved=True,
        )

        copy_text = summary["copy_text"]
        self.assertIn("OPENAI_API_KEY=<redacted>", copy_text)
        self.assertIn("\"api_key\": \"<redacted>\"", copy_text)
        self.assertIn("http://<redacted>:<redacted>@proxy.example.com", copy_text)
        for leaked in (
            "sk-env-secret",
            "sk-json-secret",
            "proxy_user",
            "proxy_pass",
        ):
            self.assertNotIn(leaked, copy_text)

    def test_sanitize_diagnostic_text_redacts_common_secret_shapes(self) -> None:
        text = (
            "OPENAI_API_KEY=sk-env-secret "
            "\"api_key\": \"sk-json-secret\" "
            "'access_token': 'raw-token-secret' "
            "http://proxy_user:proxy_pass@proxy.example.com "
            "Authorization: Bearer sk-auth-secret"
        )

        sanitized = sanitize_diagnostic_text(text)

        self.assertIsNotNone(sanitized)
        self.assertIn("OPENAI_API_KEY=<redacted>", sanitized)
        self.assertIn("\"api_key\": \"<redacted>\"", sanitized)
        self.assertIn("'access_token': '<redacted>'", sanitized)
        self.assertIn("http://<redacted>:<redacted>@proxy.example.com", sanitized)
        self.assertIn("Authorization=<redacted>", sanitized)
        for leaked in (
            "sk-env-secret",
            "sk-json-secret",
            "sk-raw-secret",
            "raw-token-secret",
            "proxy_user",
            "proxy_pass",
            "sk-auth-secret",
        ):
            self.assertNotIn(leaked, sanitized)

    def test_legacy_report_without_diagnostics_returns_unknown(self) -> None:
        summary = build_run_diagnostic_summary(
            context_snapshot={"news_content": "legacy news"},
            raw_result={"success": True, "model_used": "deepseek-chat"},
            report_saved=True,
            query_id="legacy-query",
            stock_code="2330",
        )

        self.assertEqual(summary["status"], "unknown")
        self.assertEqual(summary["status_label"], "未知")
        self.assertEqual(summary["query_id"], "legacy-query")

    def test_history_service_and_endpoint_return_diagnostic_summary(self) -> None:
        context_snapshot = {
            "diagnostics": _diagnostic_snapshot(),
            "news_content": "新聞摘要",
        }
        db = _FakeHistoryDb(_history_record(context_snapshot=context_snapshot))

        service_summary = HistoryService(db).resolve_and_get_diagnostics("1")
        endpoint_summary = get_history_diagnostics("1", db_manager=db)

        self.assertIsNotNone(service_summary)
        self.assertEqual(service_summary["trace_id"], "trace-p2")
        self.assertEqual(endpoint_summary.trace_id, "trace-p2")
        self.assertIn("realtime_quote", endpoint_summary.components)

    def test_history_service_returns_unknown_for_legacy_record(self) -> None:
        db = _FakeHistoryDb(_history_record(context_snapshot=None))

        summary = HistoryService(db).resolve_and_get_diagnostics("1")

        self.assertIsNotNone(summary)
        self.assertEqual(summary["status"], "unknown")
        self.assertIn("copy_text", summary)

    def test_history_diagnostics_endpoint_surfaces_lookup_errors(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            get_history_diagnostics("1", db_manager=_FailingHistoryDb())

        self.assertEqual(ctx.exception.status_code, 500)

    def test_history_diagnostics_endpoint_surfaces_malformed_payloads(self) -> None:
        record = _history_record(context_snapshot=None)
        record.context_snapshot = "{invalid-json"
        db = _FakeHistoryDb(record)

        with self.assertRaises(ValueError):
            HistoryService(db).resolve_and_get_diagnostics("1")
        with self.assertRaises(HTTPException) as ctx:
            get_history_diagnostics("1", db_manager=db)

        self.assertEqual(ctx.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()

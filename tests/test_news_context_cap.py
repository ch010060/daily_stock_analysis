# -*- coding: utf-8 -*-
"""Phase 4.2 B8-A news_context cap tests.

All tests are offline unittest coverage. They do not call search providers,
network, server/API, notifications, or LLM endpoints.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.analyzer import AnalysisResult
from src.core.pipeline import StockAnalysisPipeline, _cap_news_context
from src.enums import ReportType
from src.search_service import (
    NEWS_CONTEXT_TRUNCATION_MARKER_TEMPLATE,
    SearchResponse,
    SearchResult,
    SearchService,
)


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        code="AAPL",
        name="Apple",
        sentiment_score=62,
        trend_prediction="震盪",
        operation_advice="持有",
        decision_type="hold",
    )


def _make_pipeline() -> StockAnalysisPipeline:
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.config = SimpleNamespace(
        enable_realtime_quote=False,
        enable_chip_distribution=False,
        realtime_source_priority=[],
        agent_mode=False,
        agent_skills=[],
        save_context_snapshot=False,
        report_language="zh",
        report_integrity_enabled=False,
        fundamental_stage_timeout_seconds=1,
    )
    pipeline.source_message = None
    pipeline.query_id = None
    pipeline.query_source = "system"
    pipeline.save_context_snapshot = False
    pipeline.progress_callback = None
    pipeline.analysis_skills = None
    pipeline.analysis_phase = "auto"

    pipeline.fetcher_manager = MagicMock()
    pipeline.fetcher_manager.get_stock_name.return_value = "Apple"
    pipeline.fetcher_manager.get_realtime_quote.return_value = None
    pipeline.fetcher_manager.get_chip_distribution.return_value = None
    pipeline.fetcher_manager.get_fundamental_context.return_value = {
        "market": "us",
        "coverage": {"boards": "not_supported"},
        "source_chain": [],
    }
    pipeline.fetcher_manager.build_failed_fundamental_context.return_value = {
        "market": "us",
        "coverage": {"boards": "not_supported"},
        "source_chain": [],
    }

    pipeline.db = MagicMock()
    pipeline.db.get_data_range.return_value = []
    pipeline.db.get_analysis_context.return_value = {
        "code": "AAPL",
        "stock_name": "Apple",
        "date": "2026-06-09",
        "today": {},
        "yesterday": {},
    }

    pipeline.trend_analyzer = MagicMock()
    pipeline.trend_analyzer.analyze.return_value = None
    pipeline.analyzer = MagicMock()
    pipeline.analyzer.analyze.return_value = _analysis_result()
    pipeline._emit_progress = MagicMock()
    return pipeline


class NewsContextCapTest(unittest.TestCase):
    def test_format_intel_report_caps_total_length_and_marks_truncation(self) -> None:
        service = SearchService()
        marker = NEWS_CONTEXT_TRUNCATION_MARKER_TEMPLATE.format(max_chars=240)
        response = SearchResponse(
            query="Apple news",
            provider="UnitSearch",
            success=True,
            results=[
                SearchResult(
                    title=f"Apple oversized item {idx}",
                    snippet="N" * 300,
                    url=f"https://example.com/{idx}",
                    source="example.com",
                    published_date="2026-06-09",
                )
                for idx in range(6)
            ],
        )

        report = service.format_intel_report(
            {"latest_news": response, "risk_check": response},
            "Apple",
            max_total_chars=240,
        )

        self.assertIn(marker, report)
        self.assertLessEqual(len(report), 240 + len("\n" + marker))

    def test_pipeline_final_guard_caps_combined_news_and_social_context(self) -> None:
        pipeline = _make_pipeline()
        marker = NEWS_CONTEXT_TRUNCATION_MARKER_TEMPLATE.format(max_chars=8000)
        pipeline.search_service = MagicMock()
        pipeline.search_service.is_available = True
        pipeline.search_service.search_comprehensive_intel.return_value = {
            "latest_news": SearchResponse(query="Apple", provider="Unit", results=[])
        }
        pipeline.search_service.format_intel_report.return_value = "N" * 7990
        pipeline.social_sentiment_service = MagicMock()
        pipeline.social_sentiment_service.is_available = True
        pipeline.social_sentiment_service.get_social_context.return_value = "S" * 500

        result = pipeline.analyze_stock("AAPL", ReportType.SIMPLE, query_id="q-cap")

        self.assertIsNotNone(result)
        news_context = pipeline.analyzer.analyze.call_args.kwargs["news_context"]
        self.assertIn(marker, news_context)
        self.assertLessEqual(len(news_context), 8000 + len("\n" + marker))

    def test_short_news_context_is_not_changed(self) -> None:
        original = "short news context\n\nshort social context"

        capped = _cap_news_context(original, max_chars=8000)

        self.assertEqual(capped, original)


if __name__ == "__main__":
    unittest.main()

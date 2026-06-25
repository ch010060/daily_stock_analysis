# -*- coding: utf-8 -*-
"""
===================================
Report Engine - Schema parsing and fallback tests
===================================

Tests for AnalysisReportSchema validation and analyzer fallback behavior.
"""

import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Mock litellm before importing analyzer (optional runtime dep)
try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.schemas.report_schema import AnalysisReportSchema
from src.analyzer import GeminiAnalyzer, AnalysisResult


class TestAnalysisReportSchema(unittest.TestCase):
    """Schema parsing tests."""

    def test_valid_dashboard_parses(self) -> None:
        """Valid LLM-like JSON parses successfully."""
        data = {
            "stock_name": "台積電",
            "sentiment_score": 75,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "confidence_level": "中",
            "dashboard": {
                "core_conclusion": {"one_sentence": "持有觀望"},
                "intelligence": {"risk_alerts": []},
                "battle_plan": {"sniper_points": {"stop_loss": "110元"}},
            },
            "analysis_summary": "基本面穩健",
        }
        schema = AnalysisReportSchema.model_validate(data)
        self.assertEqual(schema.stock_name, "台積電")
        self.assertEqual(schema.sentiment_score, 75)
        self.assertIsNotNone(schema.dashboard)

    def test_schema_allows_optional_fields_missing(self) -> None:
        """Schema accepts minimal valid structure."""
        data = {
            "stock_name": "測試",
            "sentiment_score": 50,
            "trend_prediction": "震盪",
            "operation_advice": "觀望",
        }
        schema = AnalysisReportSchema.model_validate(data)
        self.assertIsNone(schema.dashboard)
        self.assertIsNone(schema.analysis_summary)

    def test_schema_accepts_phase_decision_and_defaults_lists(self) -> None:
        """Dashboard accepts the optional phase_decision contract."""
        data = {
            "stock_name": "台積電",
            "sentiment_score": 70,
            "trend_prediction": "震盪",
            "operation_advice": "持有",
            "dashboard": {
                "core_conclusion": {"one_sentence": "等待確認"},
                "phase_decision": {
                    "phase_context": {"phase": "intraday", "market": "cn"},
                    "action_window": "盤中跟蹤",
                    "immediate_action": "等待確認",
                    "next_check_time": "14:30",
                    "confidence_reason": "資料質量可用",
                },
            },
        }

        schema = AnalysisReportSchema.model_validate(data)

        self.assertIsNotNone(schema.dashboard)
        phase_decision = schema.dashboard and schema.dashboard.phase_decision
        self.assertIsNotNone(phase_decision)
        if phase_decision:
            self.assertEqual(phase_decision.watch_conditions, [])
            self.assertEqual(phase_decision.data_limitations, [])
            self.assertEqual(phase_decision.phase_context["phase"], "intraday")

    def test_schema_allows_numeric_strings(self) -> None:
        """Schema accepts string values for numeric fields (LLM may return N/A)."""
        data = {
            "stock_name": "測試",
            "sentiment_score": 60,
            "trend_prediction": "看多",
            "operation_advice": "買進",
            "dashboard": {
                "data_perspective": {
                    "price_position": {
                        "current_price": "N/A",
                        "bias_ma5": "2.5",
                    }
                }
            },
        }
        schema = AnalysisReportSchema.model_validate(data)
        self.assertIsNotNone(schema.dashboard)
        pp = schema.dashboard and schema.dashboard.data_perspective and schema.dashboard.data_perspective.price_position
        self.assertIsNotNone(pp)
        if pp:
            self.assertEqual(pp.current_price, "N/A")
            self.assertEqual(pp.bias_ma5, "2.5")

    def test_schema_fails_on_invalid_sentiment_score(self) -> None:
        """Schema validation fails when sentiment_score out of range."""
        data = {
            "stock_name": "測試",
            "sentiment_score": 150,  # out of 0-100
            "trend_prediction": "看多",
            "operation_advice": "買進",
        }
        with self.assertRaises(Exception):
            AnalysisReportSchema.model_validate(data)

    def test_schema_declares_optional_value_network_mermaid_field(self) -> None:
        """Phase 18A: value_network_mermaid is a declared optional field."""
        self.assertIn("value_network_mermaid", AnalysisReportSchema.model_fields)

        data = {
            "stock_name": "測試",
            "sentiment_score": 50,
            "trend_prediction": "震盪",
            "operation_advice": "觀望",
            "value_network_mermaid": "flowchart TB\n  A --> B",
        }
        schema = AnalysisReportSchema.model_validate(data)
        self.assertEqual(schema.value_network_mermaid, "flowchart TB\n  A --> B")

    def test_schema_instrument_type_defaults_to_unknown(self) -> None:
        """Phase 19B.1: instrument_type is declared and defaults to 'unknown'."""
        self.assertIn("instrument_type", AnalysisReportSchema.model_fields)

        data = {
            "stock_name": "測試",
            "sentiment_score": 50,
            "trend_prediction": "震盪",
            "operation_advice": "觀望",
        }
        schema = AnalysisReportSchema.model_validate(data)
        self.assertEqual(schema.instrument_type, "unknown")

    def test_schema_instrument_type_accepts_contract_values(self) -> None:
        """Phase 19B.1: only stock/etf/index/unknown are valid; others reject."""
        base = {
            "stock_name": "測試",
            "sentiment_score": 50,
            "trend_prediction": "震盪",
            "operation_advice": "觀望",
        }
        for value in ("stock", "etf", "index", "unknown"):
            schema = AnalysisReportSchema.model_validate({**base, "instrument_type": value})
            self.assertEqual(schema.instrument_type, value)

        with self.assertRaises(Exception):
            AnalysisReportSchema.model_validate({**base, "instrument_type": "warrant"})

    def test_schema_valuation_fundamental_snapshot_fields_default_to_none(self) -> None:
        """Phase 19B.2: declared, Optional[Dict], default None, extra="allow"
        means any LLM-supplied value is accepted by the schema but is later
        discarded/overwritten by the pipeline (same pattern as instrument_type)."""
        self.assertIn("valuation_snapshot", AnalysisReportSchema.model_fields)
        self.assertIn("fundamental_snapshot", AnalysisReportSchema.model_fields)

        data = {
            "stock_name": "測試",
            "sentiment_score": 50,
            "trend_prediction": "震盪",
            "operation_advice": "觀望",
        }
        schema = AnalysisReportSchema.model_validate(data)
        self.assertIsNone(schema.valuation_snapshot)
        self.assertIsNone(schema.fundamental_snapshot)

    def test_schema_valuation_fundamental_snapshot_accepts_dict(self) -> None:
        base = {
            "stock_name": "測試",
            "sentiment_score": 50,
            "trend_prediction": "震盪",
            "operation_advice": "觀望",
        }
        snapshot = {"pe_ttm": 23.1, "source": "finmind", "data_gap_fields": []}
        schema = AnalysisReportSchema.model_validate(
            {**base, "valuation_snapshot": snapshot, "fundamental_snapshot": snapshot}
        )
        self.assertEqual(schema.valuation_snapshot, snapshot)
        self.assertEqual(schema.fundamental_snapshot, snapshot)


class TestAnalyzerSchemaFallback(unittest.TestCase):
    """Analyzer fallback when schema validation fails."""

    def test_parse_response_continues_when_schema_fails(self) -> None:
        """When schema validation fails, analyzer continues with raw dict."""
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 150,  # invalid for schema
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "analysis_summary": "測試摘要",
        })
        result = analyzer._parse_response(response, "2330", "台積電")
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.code, "2330")
        self.assertEqual(result.sentiment_score, 150)  # from raw dict
        self.assertTrue(result.success)

    def test_parse_response_valid_json_succeeds(self) -> None:
        """Valid JSON produces correct AnalysisResult."""
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 72,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "confidence_level": "高",
            "analysis_summary": "技術面向好",
        })
        result = analyzer._parse_response(response, "2330", "股票2330")
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.name, "台積電")
        self.assertEqual(result.sentiment_score, 72)
        self.assertEqual(result.analysis_summary, "技術面向好")

    def test_parse_response_keeps_unknown_dashboard_fields(self) -> None:
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 72,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "analysis_summary": "技術面向好",
            "dashboard": {
                "core_conclusion": {
                    "one_sentence": "先觀察",
                    "signal_type": "🟡持有觀望",
                },
                "decision_stability": {
                    "applied": True,
                    "reason": "回測驗證",
                },
            },
        })
        result = analyzer._parse_response(response, "2330", "股票2330")
        self.assertEqual(result.dashboard["decision_stability"]["applied"], True)
        self.assertEqual(result.dashboard["decision_stability"]["reason"], "回測驗證")

    def test_parse_response_carries_value_network_mermaid_field(self) -> None:
        """Phase 18A: value_network_mermaid from the LLM JSON reaches AnalysisResult."""
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 72,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "analysis_summary": "技術面向好",
            "value_network_mermaid": "flowchart TB\n  A[供應商] --> B[公司]",
        })
        result = analyzer._parse_response(response, "2330", "股票2330")
        self.assertEqual(result.value_network_mermaid, "flowchart TB\n  A[供應商] --> B[公司]")

    def test_parse_response_defaults_value_network_mermaid_to_none(self) -> None:
        """Phase 18A: value_network_mermaid defaults to None when absent."""
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 72,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "analysis_summary": "技術面向好",
        })
        result = analyzer._parse_response(response, "2330", "股票2330")
        self.assertIsNone(result.value_network_mermaid)

    def test_parse_text_response_honors_injected_runtime_report_language(self) -> None:
        """Fallback text parsing should use the analyzer's injected config, not the global singleton."""
        with patch.object(GeminiAnalyzer, "_init_litellm", return_value=None):
            analyzer = GeminiAnalyzer(config=SimpleNamespace(report_language="en"))

        result = analyzer._parse_text_response("bullish buy setup", "AAPL", "Apple")

        self.assertEqual(result.report_language, "en")
        self.assertEqual(result.trend_prediction, "Bullish")
        self.assertEqual(result.operation_advice, "Buy")
        self.assertEqual(result.confidence_level, "Low")

    def test_parse_response_ignores_llm_supplied_instrument_type(self) -> None:
        """Phase 19B.1: instrument_type must never be LLM-inferred; it stays
        at the dataclass default regardless of what the LLM JSON contains.
        The pipeline (not the analyzer) is responsible for setting it from
        SymbolRecord."""
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 72,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "analysis_summary": "技術面向好",
            "instrument_type": "etf",
        })
        result = analyzer._parse_response(response, "2330", "股票2330")
        self.assertEqual(result.instrument_type, "unknown")

    def test_parse_response_ignores_llm_supplied_valuation_fundamental_snapshot(self) -> None:
        """Phase 19B.2: same non-LLM-inferred contract as instrument_type —
        the pipeline (not the analyzer) builds these from FinMind/yfinance."""
        analyzer = GeminiAnalyzer()
        response = json.dumps({
            "stock_name": "台積電",
            "sentiment_score": 72,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "analysis_summary": "技術面向好",
            "valuation_snapshot": {"pe_ttm": 999.0},
            "fundamental_snapshot": {"revenue_yoy": 999.0},
        })
        result = analyzer._parse_response(response, "2330", "股票2330")
        self.assertIsNone(result.valuation_snapshot)
        self.assertIsNone(result.fundamental_snapshot)

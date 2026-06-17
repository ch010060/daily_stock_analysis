# -*- coding: utf-8 -*-
"""QA read-only prebuilt context coverage."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.agent.executor import (
    AgentExecutor,
    AgentResult,
    build_prebuilt_context_summary,
)
from src.agent.llm_adapter import LLMResponse
from src.agent.orchestrator import AgentOrchestrator
from src.agent.tools.registry import ToolDefinition, ToolRegistry


def _registry_with_fetch_handlers(*handlers: MagicMock) -> ToolRegistry:
    registry = ToolRegistry()
    for name, handler in zip(
        ("get_realtime_quote", "get_daily_history", "search_stock_news"),
        handlers,
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description=f"{name} mock",
                parameters=[],
                handler=handler,
            )
        )
    return registry


def _prebuilt_result(**overrides):
    payload = {
        "code": "600519",
        "name": "貴州茅臺",
        "operation_advice": "持有",
        "trend_prediction": "震盪偏強",
        "sentiment_score": 72,
        "confidence_level": "中",
        "analysis_summary": "估值偏高但趨勢仍穩。",
        "risk_warning": "注意高估值與消費復甦不及預期。",
        "news_summary": "近期新聞情緒中性偏正面。",
        "report_language": "zh",
    }
    payload.update(overrides)
    return payload


class TestQAPrebuiltContext(unittest.TestCase):
    def test_qa_prebuilt_result_injected(self):
        executor = AgentExecutor(ToolRegistry(), MagicMock(), max_steps=1)
        captured = {}

        def fake_run_loop(messages, tool_decls, parse_dashboard, progress_callback=None):
            captured["messages"] = messages
            captured["tool_decls"] = tool_decls
            return AgentResult(success=True, content="ok")

        with patch.object(executor, "_run_loop", side_effect=fake_run_loop), \
             patch(
                 "src.agent.executor.build_agent_chat_context_bundle",
                 return_value=SimpleNamespace(context_messages=[], diagnostics={}),
             ), \
             patch("src.agent.conversation.conversation_manager.get_or_create"), \
             patch("src.agent.conversation.conversation_manager.add_message"):
            executor.chat(
                "剛才那份分析最大的風險是什麼？",
                "qa-prebuilt-1",
                context={"pre_built_result": _prebuilt_result()},
            )

        prompt_text = "\n\n".join(m["content"] for m in captured["messages"])
        self.assertIn("[系統提供的只讀預構建分析結果]", prompt_text)
        self.assertIn("code: 600519", prompt_text)
        self.assertIn("operation_advice: 持有", prompt_text)
        self.assertIn("analysis_summary: 估值偏高但趨勢仍穩。", prompt_text)
        self.assertIn("risk_warning: 注意高估值", prompt_text)
        self.assertIn("不要為回答本次追問重新獲取行情", prompt_text)

    def test_qa_prebuilt_result_does_not_fetch(self):
        quote_handler = MagicMock(return_value={"price": 1880})
        history_handler = MagicMock(return_value={"rows": []})
        search_handler = MagicMock(return_value={"items": []})
        registry = _registry_with_fetch_handlers(quote_handler, history_handler, search_handler)
        adapter = MagicMock()
        adapter.call_with_tools.return_value = LLMResponse(
            content="基於既有分析，主要風險是估值偏高。",
            tool_calls=[],
            usage={},
            provider="mock",
            model="mock-model",
        )
        orchestrator = AgentOrchestrator(
            registry,
            adapter,
            mode="full",
            config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        )

        with patch("src.agent.orchestrator.build_visible_chat_history", return_value=[]), \
             patch("src.agent.conversation.conversation_manager.get_or_create"), \
             patch("src.agent.conversation.conversation_manager.add_message"), \
             patch("src.core.pipeline.StockAnalysisPipeline.process_single_stock") as process_single_stock:
            result = orchestrator.chat(
                "延續上一份分析，現在要不要加倉？",
                "qa-prebuilt-2",
                context={"pre_built_result": _prebuilt_result()},
            )

        self.assertTrue(result.success)
        quote_handler.assert_not_called()
        history_handler.assert_not_called()
        search_handler.assert_not_called()
        process_single_stock.assert_not_called()
        tool_decls = adapter.call_with_tools.call_args.args[1]
        self.assertEqual(tool_decls, [])

    def test_qa_prebuilt_context_filters_sensitive_keys(self):
        summary = build_prebuilt_context_summary(
            {
                "pre_built_context": {
                    "code": "600519",
                    "name": "貴州茅臺",
                    "realtime": {
                        "price": 1880,
                        "api_key": "secret-key-value",
                        "token": "secret-token-value",
                        "webhook_url": "https://example.invalid/hook",
                        "password": "secret-password-value",
                    },
                    "news_context": "公開新聞摘要",
                }
            }
        )

        self.assertIn("code: 600519", summary)
        self.assertIn("price", summary)
        self.assertIn("公開新聞摘要", summary)
        self.assertNotIn("secret-key-value", summary)
        self.assertNotIn("secret-token-value", summary)
        self.assertNotIn("secret-password-value", summary)
        self.assertNotIn("https://example.invalid/hook", summary)
        self.assertNotIn("api_key", summary)
        self.assertNotIn("token", summary)
        self.assertNotIn("webhook", summary)
        self.assertNotIn("password", summary)

    def test_qa_prebuilt_context_caps_long_text(self):
        summary = build_prebuilt_context_summary(
            {
                "pre_built_context": {
                    "code": "600519",
                    "name": "貴州茅臺",
                    "news_context": "長" * 5000,
                }
            }
        )

        self.assertIn("[TRUNCATED]", summary)
        self.assertLessEqual(len(summary), 4200)

    def test_existing_context_behavior_unchanged_without_prebuilt(self):
        executor = AgentExecutor(ToolRegistry(), MagicMock(), max_steps=1)
        msg = executor._build_user_message(
            "Analyze",
            context={"stock_code": "600519", "report_type": "daily"},
        )

        self.assertIn("股票程式碼: 600519", msg)
        self.assertIn("報告型別: daily", msg)
        self.assertIn("請使用可用工具獲取缺失的資料", msg)
        self.assertNotIn("prebuilt", msg)
        self.assertNotIn("預構建分析結果", msg)

    def test_qa_prebuilt_result_preserves_report_language_zh_TW(self):
        executor = AgentExecutor(ToolRegistry(), MagicMock(), max_steps=1)
        captured = {}

        def fake_run_loop(messages, tool_decls, parse_dashboard, progress_callback=None):
            captured["messages"] = messages
            return AgentResult(success=True, content="ok")

        with patch.object(executor, "_run_loop", side_effect=fake_run_loop), \
             patch(
                 "src.agent.executor.build_agent_chat_context_bundle",
                 return_value=SimpleNamespace(context_messages=[], diagnostics={}),
             ), \
             patch("src.agent.conversation.conversation_manager.get_or_create"), \
             patch("src.agent.conversation.conversation_manager.add_message"):
            executor.chat(
                "請用剛才分析說明風險。",
                "qa-prebuilt-zh-tw",
                context={"pre_built_result": _prebuilt_result(report_language="zh_TW")},
            )

        system_prompt = captured["messages"][0]["content"]
        prompt_text = "\n\n".join(m["content"] for m in captured["messages"])
        self.assertIn("繁體中文", system_prompt)
        self.assertIn("report_language: zh_TW", prompt_text)


if __name__ == "__main__":
    unittest.main()

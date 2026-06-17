# -*- coding: utf-8 -*-
"""Unit tests for standalone Traditional Chinese report language support."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.agent.executor import AgentExecutor, _build_language_section
from src.agent.tools.registry import ToolRegistry
from src.analyzer import GeminiAnalyzer
from src.config import Config
from src.report_language import (
    get_report_labels,
    get_sentiment_label,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)


class ZhTwLanguageTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        Config.reset_instance()

    def test_normalize_report_language_accepts_zh_tw_spellings(self) -> None:
        self.assertEqual(normalize_report_language("zh_TW"), "zh_TW")
        self.assertEqual(normalize_report_language("zh-tw"), "zh_TW")
        self.assertEqual(normalize_report_language("zh_tw"), "zh_TW")

    def test_zh_tw_report_labels_are_complete_and_traditional(self) -> None:
        zh_labels = get_report_labels("zh")
        zh_tw_labels = get_report_labels("zh_TW")

        self.assertEqual(set(zh_tw_labels), set(zh_labels))
        self.assertEqual(zh_tw_labels["core_conclusion_heading"], "核心結論")
        self.assertEqual(zh_tw_labels["risk_alerts_label"], "風險提示")
        self.assertEqual(zh_tw_labels["buy_label"], "買進")

    def test_zh_tw_localized_values_use_traditional_chinese(self) -> None:
        self.assertEqual(localize_operation_advice("buy", "zh_TW"), "買進")
        self.assertEqual(localize_operation_advice("sell", "zh_TW"), "賣出")
        self.assertEqual(localize_trend_prediction("sideways", "zh_TW"), "震盪")
        self.assertEqual(get_sentiment_label(80, "zh_TW"), "極度樂觀")

    def test_analyzer_system_prompt_requires_traditional_chinese(self) -> None:
        with patch.object(GeminiAnalyzer, "_init_litellm", return_value=None):
            analyzer = GeminiAnalyzer()

        prompt = analyzer._get_analysis_system_prompt("zh_TW", stock_code="TW:2330")

        self.assertIn("繁體中文", prompt)
        self.assertIn("所有 JSON 鍵名保持不變", prompt)
        self.assertIn("decision_type", prompt)

    def test_agent_executor_language_section_requires_traditional_chinese(self) -> None:
        section = _build_language_section("zh-tw")
        chat_section = _build_language_section("zh_tw", chat_mode=True)

        self.assertIn("繁體中文", section)
        self.assertIn("所有 JSON 鍵名保持不變", section)
        self.assertIn("繁體中文", chat_section)

    def test_agent_executor_user_message_marks_zh_tw_context(self) -> None:
        executor = AgentExecutor(ToolRegistry(), MagicMock(), max_steps=1)

        message = executor._build_user_message(
            "Analyze",
            context={"stock_code": "TW:2330", "report_language": "zh_TW"},
        )

        self.assertIn("輸出語言: 繁體中文", message)

    def test_report_language_env_zh_tw_is_valid_without_warning(self) -> None:
        with self.assertNoLogs("src.config", level="WARNING"):
            self.assertEqual(Config._parse_report_language("zh_TW"), "zh_TW")
            self.assertEqual(Config._parse_report_language("zh-tw"), "zh_TW")
            self.assertEqual(Config._parse_report_language("zh_tw"), "zh_TW")

    @patch("src.config.setup_env")
    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_load_from_env_preserves_canonical_zh_tw(
        self,
        _mock_parse_yaml,
        _mock_setup_env,
    ) -> None:
        with patch.dict(os.environ, {"REPORT_LANGUAGE": "zh_TW"}, clear=True):
            with self.assertNoLogs("src.config", level="WARNING"):
                config = Config._load_from_env()

        self.assertEqual(config.report_language, "zh_TW")

    def test_existing_zh_and_en_behavior_is_unchanged(self) -> None:
        self.assertEqual(normalize_report_language("zh"), "zh")
        self.assertEqual(normalize_report_language("zh-cn"), "zh")
        self.assertEqual(normalize_report_language("en"), "en")
        self.assertEqual(normalize_report_language("english"), "en")
        self.assertEqual(get_report_labels("zh")["buy_label"], "買進")
        self.assertEqual(get_report_labels("en")["buy_label"], "Buy")


if __name__ == "__main__":
    unittest.main()

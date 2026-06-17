# -*- coding: utf-8 -*-
"""
===================================
B8-B rendering safety tests
===================================

Focused offline checks for obvious narrative HTML/script injection before report
renderer and legacy notification outputs.
"""

import sys
import unittest
from unittest import mock

for optional_module in ("litellm", "json_repair"):
    try:
        __import__(optional_module)
    except ModuleNotFoundError:
        sys.modules[optional_module] = mock.MagicMock()

from src.analyzer import AnalysisResult
from src.config import Config
from src.formatters import markdown_to_html_document
from src.notification import NotificationService
from src.services.report_renderer import render, sanitize_narrative_text


SCRIPT_PAYLOAD = "<script>alert(1)</script>"
JAVASCRIPT_PAYLOAD = "[bad link](javascript:alert(1))"
EVENT_HANDLER_PAYLOAD = "<img src=x onerror=alert(1)>"
MARKDOWN_PAYLOAD = "- markdown bullet survives\n[good link](https://example.com/news)"
CONTROL_PAYLOAD = "raw\x00control\x08chars"
ZH_TW_PAYLOAD = "繁體中文內容應保留"


def _make_renderer_config() -> mock.MagicMock:
    config = mock.MagicMock()
    config.report_templates_dir = "templates"
    config.report_language = "zh"
    config.report_show_llm_model = True
    return config


def _make_notification_config(**overrides) -> Config:
    values = {
        "stock_list": [],
        "report_renderer_enabled": False,
    }
    values.update(overrides)
    return Config(**values)


def _unsafe_text(prefix: str) -> str:
    return "\n".join([
        prefix,
        MARKDOWN_PAYLOAD,
        SCRIPT_PAYLOAD,
        JAVASCRIPT_PAYLOAD,
        EVENT_HANDLER_PAYLOAD,
        CONTROL_PAYLOAD,
        ZH_TW_PAYLOAD,
    ])


def _make_result() -> AnalysisResult:
    payload = _unsafe_text("Route B narrative")
    return AnalysisResult(
        code="TW:2330",
        name="臺積電",
        sentiment_score=72,
        trend_prediction="看多",
        operation_advice="持有",
        analysis_summary=payload,
        news_summary=payload,
        risk_warning=payload,
        trend_analysis=payload,
        technical_analysis=payload,
        fundamental_analysis=payload,
        dashboard={
            "core_conclusion": {
                "one_sentence": _unsafe_text("Core conclusion"),
                "time_sensitivity": "觀察",
                "position_advice": {
                    "no_position": _unsafe_text("No position"),
                    "has_position": _unsafe_text("Has position"),
                },
            },
            "intelligence": {
                "sentiment_summary": _unsafe_text("Sentiment"),
                "earnings_outlook": _unsafe_text("Earnings"),
                "risk_alerts": [_unsafe_text("Risk alert")],
                "positive_catalysts": [_unsafe_text("Catalyst")],
                "latest_news": _unsafe_text("Latest news"),
            },
            "battle_plan": {
                "sniper_points": {"stop_loss": "100"},
                "action_checklist": [_unsafe_text("Checklist")],
            },
        },
        report_language="zh",
    )


class TestRenderingSafety(unittest.TestCase):
    """B8-B narrative rendering safety checks."""

    def assert_payloads_neutralized(self, output: str) -> None:
        lowered = output.lower()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("</script", lowered)
        self.assertNotIn("javascript:", lowered)
        self.assertNotIn("onerror", lowered)
        self.assertNotIn("\x00", output)
        self.assertNotIn("\x08", output)

    @mock.patch("src.services.report_renderer.get_config")
    def test_report_renderer_neutralizes_script_and_javascript_payloads(
        self,
        mock_get_config: mock.MagicMock,
    ) -> None:
        mock_get_config.return_value = _make_renderer_config()

        output = render("markdown", [_make_result()], report_date="2026-06-09")

        self.assertIsNotNone(output)
        self.assert_payloads_neutralized(output or "")

    @mock.patch("src.services.report_renderer.get_config")
    def test_report_renderer_preserves_markdown_bullets_and_links(
        self,
        mock_get_config: mock.MagicMock,
    ) -> None:
        mock_get_config.return_value = _make_renderer_config()

        output = render("markdown", [_make_result()], report_date="2026-06-09")

        self.assertIsNotNone(output)
        self.assertIn("- markdown bullet survives", output)
        self.assertIn("[good link](https://example.com/news)", output)

    @mock.patch("src.notification.get_config")
    def test_notification_legacy_dashboard_neutralizes_narrative_payloads(
        self,
        mock_get_config: mock.MagicMock,
    ) -> None:
        mock_get_config.return_value = _make_notification_config()
        service = NotificationService()

        output = service.generate_dashboard_report([_make_result()], report_date="2026-06-09")

        self.assert_payloads_neutralized(output)
        self.assertIn("- markdown bullet survives", output)
        self.assertIn("[good link](https://example.com/news)", output)

    def test_sanitizer_neutralizes_event_handler_payloads(self) -> None:
        output = sanitize_narrative_text(EVENT_HANDLER_PAYLOAD)

        self.assertNotIn("onerror", output.lower())
        self.assertIn("<img", output.lower())

    def test_markdown_to_html_document_neutralizes_active_content(self) -> None:
        output = markdown_to_html_document(_unsafe_text("Browser-facing HTML"))

        self.assert_payloads_neutralized(output)

    def test_markdown_to_html_document_preserves_normal_markdown_and_zh_tw(self) -> None:
        output = markdown_to_html_document(MARKDOWN_PAYLOAD + "\n" + ZH_TW_PAYLOAD)

        self.assertIn("<li>markdown bullet survives", output)
        self.assertIn('<a href="https://example.com/news">good link</a>', output)
        self.assertIn(ZH_TW_PAYLOAD, output)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Server/API browser-facing report rendering safety tests."""

import unittest
from unittest import mock

from api.v1.endpoints.history import get_history_markdown


UNSAFE_MARKDOWN = "\n".join(
    [
        "# 報告",
        "- markdown bullet survives",
        "[good link](https://example.com/news)",
        "[bad link](javascript:alert(1))",
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "繁體中文內容應保留",
        "raw\x00control\x08chars",
    ]
)


class _FakeHistoryService:
    def __init__(self, _db_manager):
        pass

    def get_markdown_report(self, _record_id):
        return UNSAFE_MARKDOWN


class ServerRenderingSafetyTestCase(unittest.TestCase):
    def assert_active_content_neutralized(self, output: str) -> None:
        lowered = output.lower()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("</script", lowered)
        self.assertNotIn("javascript:", lowered)
        self.assertNotIn("onerror", lowered)
        self.assertNotIn("\x00", output)
        self.assertNotIn("\x08", output)

    @mock.patch("api.v1.endpoints.history.HistoryService", _FakeHistoryService)
    def test_history_markdown_response_neutralizes_active_content(self) -> None:
        response = get_history_markdown("123", db_manager=object())

        self.assert_active_content_neutralized(response.content)

    @mock.patch("api.v1.endpoints.history.HistoryService", _FakeHistoryService)
    def test_history_markdown_response_preserves_normal_markdown_and_zh_tw(self) -> None:
        response = get_history_markdown("123", db_manager=object())

        self.assertIn("- markdown bullet survives", response.content)
        self.assertIn("[good link](https://example.com/news)", response.content)
        self.assertIn("繁體中文內容應保留", response.content)


if __name__ == "__main__":
    unittest.main()

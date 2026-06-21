# -*- coding: utf-8 -*-
"""API contract tests for /api/v1/usage/dashboard endpoint."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from api.deps import get_database_manager
from src.storage import DatabaseManager


def _fake_summary():
    return {
        "total_calls": 3,
        "total_prompt_tokens": 300,
        "total_completion_tokens": 600,
        "total_tokens": 900,
        "by_call_type": [
            {"call_type": "analysis", "calls": 3, "prompt_tokens": 300, "completion_tokens": 600, "total_tokens": 900}
        ],
        "by_model": [
            {
                "model": "gemini/gemini-2.5-flash",
                "calls": 3,
                "prompt_tokens": 300,
                "completion_tokens": 600,
                "total_tokens": 900,
                "max_total_tokens": 300,
            }
        ],
    }


def _fake_records():
    return [
        {
            "id": 1,
            "called_at": datetime(2026, 6, 16, 10, 0, 0),
            "call_type": "analysis",
            "model": "gemini/gemini-2.5-flash",
            "stock_code": "2330",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300,
        }
    ]


class FakeUsageDbManager:
    """Minimal fake DatabaseManager for usage API tests."""

    def get_llm_usage_summary(self, from_dt, to_dt):
        return _fake_summary()

    def get_llm_usage_records(self, from_dt, to_dt, limit=50):
        return _fake_records()[:limit]


class UsageDashboardApiTest(unittest.TestCase):
    def setUp(self):
        DatabaseManager.reset_instance()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_db = FakeUsageDbManager()

        self.auth_enabled_patch = patch.dict(
            create_app.__globals__["add_auth_middleware"].__globals__,
            {"is_auth_enabled": lambda: False},
        )
        self.auth_enabled_patch.start()

        app = create_app(static_dir=Path(self.temp_dir.name) / "static")
        app.dependency_overrides[get_database_manager] = lambda: self.fake_db
        self.app = app

        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self):
        self.app.dependency_overrides.clear()
        self.auth_enabled_patch.stop()
        DatabaseManager.reset_instance()
        self.temp_dir.cleanup()

    def test_dashboard_returns_200(self):
        resp = self.client.get("/api/v1/usage/dashboard?period=today&limit=10")
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_response_has_total_tokens(self):
        resp = self.client.get("/api/v1/usage/dashboard?period=today&limit=10")
        data = resp.json()
        self.assertIn("total_tokens", data)
        self.assertEqual(data["total_tokens"], 900)

    def test_dashboard_response_has_prompt_and_completion_totals(self):
        resp = self.client.get("/api/v1/usage/dashboard?period=today&limit=10")
        data = resp.json()
        self.assertEqual(data["total_prompt_tokens"], 300)
        self.assertEqual(data["total_completion_tokens"], 600)

    def test_dashboard_by_model_has_max_total_tokens(self):
        resp = self.client.get("/api/v1/usage/dashboard?period=today&limit=10")
        data = resp.json()
        by_model = data.get("by_model", [])
        self.assertGreater(len(by_model), 0)
        self.assertIn("max_total_tokens", by_model[0])
        self.assertEqual(by_model[0]["max_total_tokens"], 300)

    def test_dashboard_recent_calls_has_tw_stock_code(self):
        resp = self.client.get("/api/v1/usage/dashboard?period=today&limit=10")
        data = resp.json()
        recent = data.get("recent_calls", [])
        self.assertGreater(len(recent), 0)
        self.assertEqual(recent[0]["stock_code"], "2330")

    def test_dashboard_no_upstream_only_fields(self):
        """Ensure upstream-specific fields (provider, context_window, etc.) are absent."""
        resp = self.client.get("/api/v1/usage/dashboard?period=today&limit=10")
        data = resp.json()
        self.assertNotIn("provider", data)
        self.assertNotIn("context_window", data)
        self.assertNotIn("context_usage_ratio", data)

    def test_dashboard_default_period_is_month(self):
        resp = self.client.get("/api/v1/usage/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["period"], "month")

    def test_summary_endpoint_returns_200(self):
        resp = self.client.get("/api/v1/usage/summary?period=today")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_calls", data)
        self.assertNotIn("recent_calls", data)


if __name__ == "__main__":
    unittest.main()

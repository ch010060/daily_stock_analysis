# -*- coding: utf-8 -*-
"""API contract tests for the opt-in news provider probe."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from api.v1.endpoints.diagnostics import get_news_provider_probe_service_resolver
from src.config import Config
from src.search_service import SearchResponse, SearchResult
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _result(
    title: str,
    *,
    url: str = "https://example.com/news/1",
    source: str = "Example News",
    published_date: str = "2026-06-20",
) -> SearchResult:
    return SearchResult(
        title=title,
        snippet="sample",
        url=url,
        source=source,
        published_date=published_date,
    )


def _response(
    *,
    query: str,
    provider: str,
    results: list[SearchResult],
    diagnostics: dict,
    success: bool = True,
) -> SearchResponse:
    return SearchResponse(
        query=query,
        provider=provider,
        results=results,
        success=success,
        diagnostics=diagnostics,
    )


class NewsProviderProbeApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "probe_api_test.db"
        self._saved_env = {
            key: os.environ.get(key)
            for key in (
                "ENV_FILE",
                "DATABASE_PATH",
                "DSA_ALLOW_EXTERNAL_NETWORK",
                "DSA_PUBLIC_HOST",
                "DSA_ALLOWED_HOSTS",
                "TAVILY_API_KEYS",
                "SEARXNG_BASE_URLS",
                "SEARXNG_PUBLIC_INSTANCES_ENABLED",
            )
        }
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=2330,AAPL",
                    "ADMIN_AUTH_ENABLED=false",
                    "DSA_ALLOW_EXTERNAL_NETWORK=false",
                    "TAVILY_API_KEYS=",
                    "SEARXNG_BASE_URLS=",
                    "SEARXNG_PUBLIC_INSTANCES_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["DSA_ALLOW_EXTERNAL_NETWORK"] = "false"
        os.environ["DSA_PUBLIC_HOST"] = ""
        os.environ["DSA_ALLOWED_HOSTS"] = ""
        os.environ["TAVILY_API_KEYS"] = ""
        os.environ["SEARXNG_BASE_URLS"] = ""
        os.environ["SEARXNG_PUBLIC_INSTANCES_ENABLED"] = "false"
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def _override_probe_service(self, service_by_mode: dict[str, MagicMock]) -> list[str]:
        calls: list[str] = []

        def resolve(provider_mode: str) -> MagicMock:
            calls.append(provider_mode)
            return service_by_mode[provider_mode]

        self.app.dependency_overrides[get_news_provider_probe_service_resolver] = lambda: resolve
        return calls

    def test_news_provider_probe_tw_success(self) -> None:
        service = MagicMock()
        resolver_calls = self._override_probe_service({"runtime": service})
        service.search_stock_news.return_value = _response(
            query="2330 台積電 新聞",
            provider="SearXNG",
            results=[_result("台積電 2330 法說新聞")],
            diagnostics={
                "news_search": {
                    "providers_attempted": ["SearXNG"],
                    "query_variants": ["2330 台積電 新聞", "台積電 最新消息"],
                    "attempt_count": 2,
                    "result_count": 1,
                    "fallback_used": False,
                    "final_status": "available",
                }
            },
        )

        resp = self.client.post(
            "/api/v1/diagnostics/news-provider-probe",
            json={"symbol": "2330", "market": "tw", "limit": 4},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "2330")
        self.assertEqual(data["market"], "tw")
        self.assertEqual(data["status"], "available")
        self.assertEqual(data["providers_attempted"], ["SearXNG"])
        self.assertEqual(data["query_variants"][:2], ["2330 台積電 新聞", "台積電 最新消息"])
        self.assertEqual(data["attempt_count"], 2)
        self.assertEqual(data["result_count"], 1)
        self.assertFalse(data["fallback_used"])
        self.assertGreaterEqual(data["latency_ms"], 0)
        self.assertEqual(data["items"][0]["title"], "台積電 2330 法說新聞")
        self.assertEqual(resolver_calls, ["runtime"])
        service.search_stock_news.assert_called_once_with("2330", "台積電", max_results=4)

    def test_news_provider_probe_us_success(self) -> None:
        service = MagicMock()
        resolver_calls = self._override_probe_service({"runtime": service})
        service.search_stock_news.return_value = _response(
            query="AAPL Apple stock news",
            provider="Tavily",
            results=[_result("Apple earnings lift AAPL stock", source="Tavily")],
            diagnostics={
                "news_search": {
                    "providers_attempted": ["SearXNG", "Tavily"],
                    "query_variants": ["AAPL Apple stock news", "Apple earnings stock news"],
                    "attempt_count": 3,
                    "result_count": 1,
                    "fallback_used": True,
                    "final_status": "available",
                }
            },
        )

        resp = self.client.post(
            "/api/v1/diagnostics/news-provider-probe",
            json={"symbol": "AAPL", "market": "us", "limit": 4},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "AAPL")
        self.assertEqual(data["market"], "us")
        self.assertEqual(data["providers_attempted"], ["SearXNG", "Tavily"])
        self.assertEqual(data["query_variants"][:2], ["AAPL Apple stock news", "Apple earnings stock news"])
        self.assertTrue(data["fallback_used"])
        self.assertEqual(data["items"][0]["source"], "Tavily")
        self.assertEqual(resolver_calls, ["runtime"])
        service.search_stock_news.assert_called_once_with("AAPL", "Apple", max_results=4)

    def test_news_provider_probe_sanitizes_output(self) -> None:
        service = MagicMock()
        self._override_probe_service({"runtime": service})
        service.search_stock_news.return_value = _response(
            query="AAPL Apple stock news",
            provider="Tavily",
            results=[
                _result(
                    "token=phase15-secret title",
                    source="Bearer phase15-provider-token",
                    url="https://user:pass@example.com/news?api_key=phase15-url-secret",
                )
            ],
            diagnostics={
                "news_search": {
                    "providers_attempted": ["Tavily token=phase15-provider-secret"],
                    "query_variants": ["AAPL Apple stock news Authorization: Bearer phase15-query-secret"],
                    "attempt_count": 1,
                    "result_count": 1,
                    "fallback_used": False,
                    "final_status": "available",
                    "raw_provider_payload": {"api_key": "phase15-raw-secret"},
                }
            },
        )

        resp = self.client.post(
            "/api/v1/diagnostics/news-provider-probe",
            json={"symbol": "AAPL", "market": "us", "limit": 4},
        )

        self.assertEqual(resp.status_code, 200)
        payload = json.dumps(resp.json(), ensure_ascii=False)
        for leaked in (
            "phase15-secret",
            "phase15-provider-token",
            "phase15-provider-secret",
            "phase15-query-secret",
            "phase15-url-secret",
            "phase15-raw-secret",
            "user:pass",
        ):
            self.assertNotIn(leaked, payload)
        self.assertNotIn("raw_provider_payload", payload)

    def test_news_provider_probe_provider_failure_returns_structured_status(self) -> None:
        service = MagicMock()
        self._override_probe_service({"runtime": service})
        service.search_stock_news.side_effect = RuntimeError("provider api_key=phase15-provider-secret failed")

        resp = self.client.post(
            "/api/v1/diagnostics/news-provider-probe",
            json={"symbol": "2330", "market": "tw", "limit": 4},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["result_count"], 0)
        self.assertEqual(data["items"], [])
        self.assertIn("error_message", data)
        self.assertNotIn("phase15-provider-secret", json.dumps(data, ensure_ascii=False))

    def test_news_provider_probe_tavily_mode_is_explicit_opt_in(self) -> None:
        service = MagicMock()
        resolver_calls = self._override_probe_service({"tavily": service})
        service.search_stock_news.return_value = _response(
            query="AAPL Apple stock news",
            provider="Tavily",
            results=[_result("Apple earnings lift AAPL stock", source="Tavily")],
            diagnostics={
                "news_search": {
                    "providers_attempted": ["Tavily"],
                    "query_variants": ["AAPL Apple stock news"],
                    "attempt_count": 1,
                    "result_count": 1,
                    "fallback_used": False,
                    "final_status": "available",
                }
            },
        )

        resp = self.client.post(
            "/api/v1/diagnostics/news-provider-probe",
            json={"symbol": "AAPL", "market": "us", "provider_mode": "tavily", "limit": 4},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["provider_mode"], "tavily")
        self.assertEqual(data["providers_attempted"], ["Tavily"])
        self.assertEqual(resolver_calls, ["tavily"])

    def test_news_provider_probe_uses_injected_service_after_no_provider_env_leak(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DSA_ALLOW_EXTERNAL_NETWORK": "false",
                "TAVILY_API_KEYS": "",
                "SEARXNG_BASE_URLS": "",
                "SEARXNG_PUBLIC_INSTANCES_ENABLED": "false",
            },
            clear=False,
        ):
            Config.reset_instance()
            service = MagicMock()
            resolver_calls = self._override_probe_service({"runtime": service})
            service.search_stock_news.return_value = _response(
                query="2330 台積電 新聞",
                provider="SearXNG",
                results=[_result("台積電 2330 法說新聞")],
                diagnostics={
                    "news_search": {
                        "providers_attempted": ["SearXNG"],
                        "query_variants": ["2330 台積電 新聞", "台積電 最新消息"],
                        "attempt_count": 2,
                        "result_count": 1,
                        "fallback_used": False,
                        "final_status": "available",
                    }
                },
            )

            resp = self.client.post(
                "/api/v1/diagnostics/news-provider-probe",
                json={"symbol": "2330", "market": "tw", "limit": 4},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "available")
        self.assertEqual(data["providers_attempted"], ["SearXNG"])
        self.assertEqual(resolver_calls, ["runtime"])

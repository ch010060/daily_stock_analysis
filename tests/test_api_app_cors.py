# -*- coding: utf-8 -*-
"""Tests for FastAPI app CORS configuration."""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from api.app import SafeHostMiddleware, build_server_safe_cors_origins, create_app


class AppCorsConfigTestCase(unittest.TestCase):
    """CORS configuration should stay browser-compatible."""

    def _build_app(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return create_app(static_dir=Path(temp_dir.name))

    def test_allow_all_does_not_enable_wildcard_cors(self):
        origins = build_server_safe_cors_origins()
        self.assertNotIn("*", origins)
        app = self._build_app()
        cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        self.assertNotIn("*", cors.kwargs["allow_origins"])
        self.assertTrue(cors.kwargs["allow_credentials"])

    def test_explicit_origin_list_keeps_credentials_enabled(self):
        env = {k: v for k, v in os.environ.items() if k != "CORS_ALLOW_ALL"}
        env["CORS_ALLOW_ALL"] = "false"
        with patch.dict(os.environ, env, clear=True):
            app = self._build_app()

        cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        self.assertIn("http://localhost:5173", cors.kwargs["allow_origins"])
        self.assertTrue(cors.kwargs["allow_credentials"])

    def test_unsafe_extra_origin_is_ignored(self):
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": "https://example.com,http://localhost:8080"},
            clear=False,
        ):
            app = self._build_app()

        cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        self.assertNotIn("https://example.com", cors.kwargs["allow_origins"])
        self.assertIn("http://localhost:8080", cors.kwargs["allow_origins"])

    def test_external_network_enabled_configures_lan_host_without_wildcard(self):
        with patch.dict(
            os.environ,
            {
                "DSA_ALLOW_EXTERNAL_NETWORK": "true",
                "DSA_PUBLIC_HOST": "",
                "DSA_ALLOWED_HOSTS": "",
                "WEBUI_PORT": "8000",
            },
            clear=False,
        ):
            app = self._build_app()

        cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        host_middlewares = [m for m in app.user_middleware if m.cls is SafeHostMiddleware]

        self.assertNotIn("*", cors.kwargs["allow_origins"])
        self.assertIsNotNone(cors.kwargs["allow_origin_regex"])
        self.assertTrue(cors.kwargs["allow_credentials"])
        self.assertEqual(len(host_middlewares), 1)
        self.assertTrue(host_middlewares[0].kwargs["allow_private_hosts"])
        self.assertNotIn("*", host_middlewares[0].kwargs["allowed_hosts"])

    def test_external_network_enabled_accepts_private_host_header(self):
        with patch.dict(
            os.environ,
            {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "WEBUI_HOST": "0.0.0.0"},
            clear=False,
        ):
            app = self._build_app()

        response = TestClient(app).get(
            "/api/health",
            headers={"host": "192.168.1.77:8000"},
        )

        self.assertEqual(response.status_code, 200)

    def test_external_network_enabled_rejects_public_host_header(self):
        with patch.dict(
            os.environ,
            {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "WEBUI_HOST": "0.0.0.0"},
            clear=False,
        ):
            app = self._build_app()

        response = TestClient(app).get(
            "/api/health",
            headers={"host": "8.8.8.8:8000"},
        )

        self.assertEqual(response.status_code, 400)

    def test_external_network_enabled_allows_private_cors_preflight(self):
        with patch.dict(
            os.environ,
            {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "WEBUI_HOST": "0.0.0.0"},
            clear=False,
        ):
            app = self._build_app()

        response = TestClient(app).request(
            "OPTIONS",
            "/api/v1/diagnostics/news-provider-probe",
            headers={
                "host": "192.168.1.77:8000",
                "origin": "http://192.168.1.77:8000",
                "access-control-request-method": "POST",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://192.168.1.77:8000",
        )

    def test_cors_allow_all_set_emits_deprecation_warning(self):
        with self.assertLogs("api.app", level=logging.WARNING) as cm:
            with patch.dict(os.environ, {"CORS_ALLOW_ALL": "true"}, clear=False):
                build_server_safe_cors_origins()

        self.assertTrue(any("CORS_ALLOW_ALL" in line for line in cm.output))

    def test_cors_allow_all_false_emits_no_warning(self):
        env = {k: v for k, v in os.environ.items() if k != "CORS_ALLOW_ALL"}
        env["CORS_ALLOW_ALL"] = "false"
        with patch.dict(os.environ, env, clear=True):
            with self.assertLogs("api.app", level=logging.WARNING) as cm:
                logger = logging.getLogger("api.app")
                logger.warning("sentinel")
                build_server_safe_cors_origins()

        self.assertEqual(len([l for l in cm.output if "CORS_ALLOW_ALL" in l]), 0)

    def test_cors_allow_all_absent_emits_no_warning(self):
        env = {k: v for k, v in os.environ.items() if k != "CORS_ALLOW_ALL"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertLogs("api.app", level=logging.WARNING) as cm:
                logger = logging.getLogger("api.app")
                logger.warning("sentinel")
                build_server_safe_cors_origins()

        self.assertEqual(len([l for l in cm.output if "CORS_ALLOW_ALL" in l]), 0)


if __name__ == "__main__":
    unittest.main()

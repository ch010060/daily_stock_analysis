"""Focused tests for server/WebUI/API startup safety gates."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.app import (
    ServerSafetyError,
    build_server_safe_cors_origins,
    validate_admin_auth_ready,
    validate_local_server_host,
    validate_server_startup_safety,
)
from src.auth import refresh_auth_state, set_initial_password


class ServerSecurityGateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.env_file = Path(self.temp_dir.name) / ".env"
        self.env_patch = patch.dict(
            os.environ,
            {
                "ENV_FILE": str(self.env_file),
                "DATABASE_PATH": str(self.data_dir / "stock_analysis.db"),
            },
            clear=False,
        )
        self.env_patch.start()
        refresh_auth_state()

    def tearDown(self) -> None:
        refresh_auth_state()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _write_env(self, auth_enabled: bool) -> None:
        self.env_file.write_text(
            f"ADMIN_AUTH_ENABLED={'true' if auth_enabled else 'false'}\n",
            encoding="utf-8",
        )
        refresh_auth_state()

    def test_host_default_is_local_only(self) -> None:
        self.assertEqual("127.0.0.1", validate_local_server_host("127.0.0.1"))

    def test_localhost_hosts_are_accepted(self) -> None:
        self.assertEqual("localhost", validate_local_server_host("localhost"))
        self.assertEqual("::1", validate_local_server_host("::1"))

    def test_unsafe_bind_hosts_are_rejected(self) -> None:
        for host in ("0.0.0.0", "::", "192.168.1.10", ""):
            with self.subTest(host=host):
                with self.assertRaises(ServerSafetyError):
                    validate_local_server_host(host)

    def test_wildcard_cors_is_not_constructed(self) -> None:
        origins = build_server_safe_cors_origins("*")
        self.assertNotIn("*", origins)

    def test_localhost_cors_origin_is_allowed(self) -> None:
        origins = build_server_safe_cors_origins("http://localhost:8080")
        self.assertIn("http://localhost:8080", origins)

    def test_unsafe_extra_cors_origin_is_ignored(self) -> None:
        origins = build_server_safe_cors_origins("https://example.com,http://127.0.0.1:9000")
        self.assertNotIn("https://example.com", origins)
        self.assertIn("http://127.0.0.1:9000", origins)

    def test_auth_disabled_is_rejected(self) -> None:
        self._write_env(auth_enabled=False)

        with self.assertRaisesRegex(ServerSafetyError, "ADMIN_AUTH_ENABLED"):
            validate_admin_auth_ready()

    def test_auth_enabled_without_password_hash_is_rejected(self) -> None:
        self._write_env(auth_enabled=True)

        with self.assertRaisesRegex(ServerSafetyError, "stored admin password hash"):
            validate_admin_auth_ready()

    def test_auth_enabled_with_pbkdf2_hash_is_accepted(self) -> None:
        self._write_env(auth_enabled=True)
        error = set_initial_password("safe-password")

        self.assertIsNone(error)
        validate_admin_auth_ready()
        validate_server_startup_safety("127.0.0.1")

    def test_errors_do_not_include_secret_values(self) -> None:
        self._write_env(auth_enabled=True)

        with self.assertRaises(ServerSafetyError) as ctx:
            validate_admin_auth_ready()

        message = str(ctx.exception)
        self.assertNotIn("safe-password", message)
        self.assertNotIn("ADMIN_PASSWORD", message)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Phase 3.2 — Socket-level catch-all network isolation tests (offline, unittest only).

Patches socket.create_connection to refuse all connections, then asserts fixture
data is still returned and the socket was never touched.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.taiwan_finmind_fetcher import TaiwanFinMindFetcher

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "market" / "tw"


class TestNoExternalNetwork(unittest.TestCase):

    def _fetcher(self, finmind_enabled: bool = False) -> TaiwanFinMindFetcher:
        return TaiwanFinMindFetcher(fixture_root=FIXTURE_ROOT, finmind_enabled=finmind_enabled)

    @patch("socket.create_connection", side_effect=ConnectionRefusedError("network blocked in test"))
    def test_default_env_no_socket_call(self, mock_socket):
        """Default env uses fixture path; socket.create_connection never called."""
        fetcher = self._fetcher()
        df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        mock_socket.assert_not_called()
        self.assertFalse(df.empty)

    @patch("socket.create_connection", side_effect=ConnectionRefusedError("network blocked in test"))
    def test_fixture_mode_true_no_socket_call(self, mock_socket):
        """DSA_FIXTURE_MODE=true with finmind_enabled=True never touches socket."""
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true"}):
            fetcher = self._fetcher(finmind_enabled=True)
            df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        mock_socket.assert_not_called()
        self.assertFalse(df.empty)

    @patch("socket.create_connection", side_effect=ConnectionRefusedError("network blocked in test"))
    def test_allow_external_network_false_no_socket_call(self, mock_socket):
        """DSA_ALLOW_EXTERNAL_NETWORK=false with finmind_enabled=True never touches socket."""
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            fetcher = self._fetcher(finmind_enabled=True)
            df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        mock_socket.assert_not_called()
        self.assertFalse(df.empty)


if __name__ == "__main__":
    unittest.main()

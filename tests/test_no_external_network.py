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
from src.search_service import SearchService

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "market" / "tw"


class TestNoExternalNetwork(unittest.TestCase):

    def _assert_no_external_search_providers(self, service: SearchService) -> None:
        external_names = {"Bocha", "Tavily", "Brave", "SerpAPI", "MiniMax", "Anspire"}
        self.assertTrue(
            all(provider.name not in external_names for provider in service._providers),
            f"external providers should be suppressed in no-network mode: {[provider.name for provider in service._providers]}",
        )

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

    @patch("socket.create_connection", side_effect=ConnectionRefusedError("network blocked in test"))
    def test_fixture_mode_with_fake_keys_still_has_no_external_search_providers(self, mock_socket):
        """Fixture mode suppresses all keyed external search providers even with keys."""
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}):
            service = SearchService(
                bocha_keys=["k1"],
                tavily_keys=["k2"],
                brave_keys=["k3"],
                serpapi_keys=["k4"],
                minimax_keys=["k5"],
                anspire_keys=["k6"],
            )
        mock_socket.assert_not_called()
        self._assert_no_external_search_providers(service)

    @patch("src.search_service.requests.get", side_effect=AssertionError("searx.space must not be called"))
    def test_searxng_public_discovery_disabled_in_no_network_mode(self, mock_get):
        """DSA_ALLOW_EXTERNAL_NETWORK=false prevents SearXNG public discovery provider creation."""
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            service = SearchService(searxng_public_instances_enabled=True)
        mock_get.assert_not_called()
        self.assertFalse(any(provider.name == "SearXNG" for provider in service._providers))

    @patch("src.search_service.requests.get", side_effect=AssertionError("searx.space must not be called"))
    def test_no_network_with_fake_keys_still_has_no_external_search_providers(self, mock_get):
        """DSA_ALLOW_EXTERNAL_NETWORK=false suppresses all keyed external providers."""
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            service = SearchService(
                bocha_keys=["k1"],
                tavily_keys=["k2"],
                brave_keys=["k3"],
                serpapi_keys=["k4"],
                minimax_keys=["k5"],
                anspire_keys=["k6"],
                searxng_public_instances_enabled=True,
            )
        mock_get.assert_not_called()
        self._assert_no_external_search_providers(service)
        self.assertFalse(any(provider.name == "SearXNG" for provider in service._providers))


if __name__ == "__main__":
    unittest.main()

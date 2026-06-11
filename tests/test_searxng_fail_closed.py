# -*- coding: utf-8 -*-
"""Fail-closed tests for SearXNG public discovery and local-only configuration."""

import os
import unittest
from unittest.mock import patch

from src.config import Config
from src.search_service import SearchService, SearXNGSearchProvider


class SearXNGFailClosedTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        Config.reset_instance()

    def test_default_config_disables_public_discovery(self) -> None:
        with patch("src.config.setup_env"), patch.dict(os.environ, {}, clear=True):
            config = Config._load_from_env()

        self.assertFalse(config.searxng_public_instances_enabled)

    def test_default_search_service_has_no_public_provider(self) -> None:
        service = SearchService()

        self.assertFalse(any(provider.name == "SearXNG" for provider in service._providers))

    def test_default_search_service_cannot_call_searx_space(self) -> None:
        def fail_on_searx_space(url, *_args, **_kwargs):
            if "searx.space" in url:
                raise AssertionError("searx.space discovery must not be called by default")
            raise AssertionError(f"unexpected network call: {url}")

        with patch("src.search_service.requests.get", side_effect=fail_on_searx_space):
            service = SearchService()

        self.assertFalse(any(provider.name == "SearXNG" for provider in service._providers))

    def test_fixture_mode_blocks_public_discovery(self) -> None:
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true"}, clear=False):
            service = SearchService(searxng_public_instances_enabled=True)

        self.assertFalse(any(provider.name == "SearXNG" for provider in service._providers))

    def test_no_network_mode_blocks_public_discovery(self) -> None:
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env, clear=False):
            service = SearchService(searxng_public_instances_enabled=True)

        self.assertFalse(any(provider.name == "SearXNG" for provider in service._providers))

    def test_local_self_hosted_base_url_is_accepted(self) -> None:
        provider = SearXNGSearchProvider(["http://127.0.0.1:6666"])

        self.assertTrue(provider.is_available)

    def test_public_self_hosted_base_url_is_ignored(self) -> None:
        provider = SearXNGSearchProvider(["https://searx.public.example"])

        self.assertFalse(provider.is_available)


if __name__ == "__main__":
    unittest.main()

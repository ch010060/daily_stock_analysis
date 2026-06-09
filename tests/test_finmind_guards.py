# -*- coding: utf-8 -*-
"""
Phase 3.2 — TaiwanFinMindFetcher guard tests (offline, unittest only).

All tests run without live network. No FinMind package required.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_provider.base import DataFetchError
from data_provider.taiwan_finmind_fetcher import TaiwanFinMindFetcher

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "market" / "tw"


class TestFinMindGuards(unittest.TestCase):

    def _fetcher(self, finmind_enabled: bool = False) -> TaiwanFinMindFetcher:
        return TaiwanFinMindFetcher(fixture_root=FIXTURE_ROOT, finmind_enabled=finmind_enabled)

    def test_default_env_uses_fixture(self):
        """Default env (all guards false/unset) returns fixture data without error."""
        fetcher = self._fetcher()
        df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        self.assertFalse(df.empty)
        self.assertEqual(df.attrs.get("_cache_source"), "fixture")

    def test_fixture_mode_env_forces_fixture_regardless_of_enabled(self):
        """DSA_FIXTURE_MODE=true short-circuits to fixture even when finmind_enabled=True."""
        env = {"DSA_FIXTURE_MODE": "true"}
        with patch.dict(os.environ, env):
            fetcher = self._fetcher(finmind_enabled=True)
            df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        self.assertFalse(df.empty)
        self.assertEqual(df.attrs.get("_cache_source"), "fixture")

    def test_allow_external_network_false_forces_fixture(self):
        """DSA_ALLOW_EXTERNAL_NETWORK=false returns fixture even when finmind_enabled=True."""
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env):
            fetcher = self._fetcher(finmind_enabled=True)
            df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        self.assertFalse(df.empty)
        self.assertEqual(df.attrs.get("_cache_source"), "fixture")

    def test_finmind_disabled_forces_fixture(self):
        """FINMIND_ENABLED=false (via constructor) returns fixture even with network allowed."""
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env):
            fetcher = self._fetcher(finmind_enabled=False)
            df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        self.assertFalse(df.empty)
        self.assertEqual(df.attrs.get("_cache_source"), "fixture")

    def test_missing_api_token_raises(self):
        """All gates open but FINMIND_API_TOKEN empty raises DataFetchError."""
        env = {
            "DSA_FIXTURE_MODE": "false",
            "DSA_ALLOW_EXTERNAL_NETWORK": "true",
            "FINMIND_API_TOKEN": "",
        }
        with patch.dict(os.environ, env):
            fetcher = self._fetcher(finmind_enabled=True)
            with self.assertRaises(DataFetchError) as ctx:
                fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        self.assertIn("FINMIND_API_TOKEN", str(ctx.exception))

    def test_cache_meta_attached_on_fixture_load(self):
        """Normalized fixture DataFrame carries cache_meta with required fields."""
        fetcher = self._fetcher()
        raw = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        out = fetcher._normalize_data(raw, "2330")
        meta = out.attrs.get("cache_meta")
        self.assertIsNotNone(meta, "cache_meta missing from normalized DataFrame")
        self.assertEqual(meta["source"], "fixture")
        self.assertEqual(meta["market"], "TW")
        self.assertEqual(meta["symbol"], "TW:2330")
        self.assertIn("2025-01-01", meta["request_range"])
        self.assertIn("2025-03-31", meta["request_range"])

    def test_live_mode_calls_finmind_loader_when_mocked(self):
        """All guards pass + FinMind import mocked → calls DataLoader and returns live data."""
        env = {
            "DSA_FIXTURE_MODE": "false",
            "DSA_ALLOW_EXTERNAL_NETWORK": "true",
            "FINMIND_API_TOKEN": "test-token-placeholder",
        }
        sample_raw = pd.DataFrame({
            "stock_id": ["2330"],
            "date": ["2025-01-02"],
            "Trading_Volume": [1000],
            "Trading_money": [50000],
            "open": [100.0],
            "max": [101.0],
            "min": [99.0],
            "close": [100.5],
            "spread": [0.5],
            "Trading_turnover": [10],
        })
        mock_loader_instance = MagicMock()
        mock_loader_instance.taiwan_stock_daily.return_value = sample_raw
        mock_loader_cls = MagicMock(return_value=mock_loader_instance)
        mock_finmind = MagicMock()
        mock_finmind.data = MagicMock()
        mock_finmind.data.DataLoader = mock_loader_cls
        with patch.dict("sys.modules", {
            "FinMind": mock_finmind,
            "FinMind.data": mock_finmind.data,
        }):
            with patch.dict(os.environ, env):
                fetcher = self._fetcher(finmind_enabled=True)
                df = fetcher._fetch_raw_data("2330", "2025-01-01", "2025-03-31")
        mock_loader_instance.login_by_token.assert_called_once_with(api_token="test-token-placeholder")
        mock_loader_instance.taiwan_stock_daily.assert_called_once_with(
            stock_id="2330", start_date="2025-01-01", end_date="2025-03-31"
        )
        self.assertEqual(df.attrs.get("_cache_source"), "finmind_live")
        self.assertFalse(df.empty)


if __name__ == "__main__":
    unittest.main()

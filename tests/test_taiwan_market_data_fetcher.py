# -*- coding: utf-8 -*-
"""Tests for TaiwanMarketDataFetcher — Phase 7E.2.

Coverage:
 1.  Fixture mode returns deterministic TAIEX rows.
 2.  Fixture mode returns deterministic TPEx rows.
 3.  Fixture mode returns institutional total rows.
 4.  Fixture mode returns margin total rows.
 5.  Fixture mode returns 0050 / 2330 rows.
 6.  DSA_ALLOW_EXTERNAL_NETWORK=false blocks FinMind calls.
 7.  REST success normalizes result shape.
 8.  REST 400/402/500 returns unavailable, not crash.
 9.  Missing token is allowed and recorded (no crash).
10.  yfinance fallback used only when FinMind unavailable.
11.  yfinance empty DataFrame -> unavailable, not success.
12.  TPEx fallback unavailable explicit (no reliable yfinance symbol).
13.  Snapshot includes all required sections.
14.  Snapshot required_ok false if TAIEX missing.
15.  No CN/A-share provider names or query terms.
16.  TW profile tests still pass (import guard).
17.  Route B scope gate still defers TW.
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from data_provider.taiwan_market import TaiwanMarketDataFetcher

_HERE = Path(__file__).resolve().parent
_FIXTURE_ROOT = _HERE / "fixtures" / "tw_market"
_START = "2026-06-10"
_END = "2026-06-12"

_CN_FORBIDDEN = [
    "台股", "上証", "上證", "深証", "深證",
    "創業板", "創業板", "科創50", "科創50",
    "滬深", "滬深", "baostock", "akshare", "efinance",
    "tushare", "pytdx",
]


def _make_fetcher(**env_overrides) -> TaiwanMarketDataFetcher:
    """Create a fetcher pointed at test fixtures with env overrides."""
    with patch.dict(os.environ, env_overrides, clear=False):
        return TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)


def _fixture_env() -> Dict[str, str]:
    return {
        "DSA_FIXTURE_MODE": "true",
        "DSA_ALLOW_EXTERNAL_NETWORK": "false",
    }


class TestFixtureMode(unittest.TestCase):
    """Fixture-mode deterministic data loading."""

    def _fetcher(self) -> TaiwanMarketDataFetcher:
        return TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)

    def _call_with_fixture_env(self, method_name, *args):
        with patch.dict(os.environ, _fixture_env(), clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            return getattr(fetcher, method_name)(*args)

    # Test 1 — TAIEX fixture
    def test_taiex_fixture_ok(self):
        result = self._call_with_fixture_env(
            "get_total_return_index", "TAIEX", _START, _END
        )
        self.assertTrue(result["ok"], f"TAIEX fixture failed: {result}")
        self.assertGreater(result["row_count"], 0)
        self.assertEqual(result["source"], "fixture")
        self.assertEqual(result["data_id"], "TAIEX")

    def test_taiex_fixture_rows_have_price(self):
        result = self._call_with_fixture_env(
            "get_total_return_index", "TAIEX", _START, _END
        )
        self.assertIn("price", result["columns"])
        for row in result["rows"]:
            self.assertIn("price", row)
            self.assertIsInstance(row["price"], (int, float))

    def test_taiex_fixture_no_cn_terms(self):
        result = self._call_with_fixture_env(
            "get_total_return_index", "TAIEX", _START, _END
        )
        payload_str = json.dumps(result)
        for term in _CN_FORBIDDEN:
            self.assertNotIn(term, payload_str,
                             f"Forbidden CN term {term!r} in TAIEX fixture result")

    # Test 2 — TPEx fixture
    def test_tpex_fixture_ok(self):
        result = self._call_with_fixture_env(
            "get_total_return_index", "TPEx", _START, _END
        )
        self.assertTrue(result["ok"], f"TPEx fixture failed: {result}")
        self.assertGreater(result["row_count"], 0)
        self.assertEqual(result["data_id"], "TPEx")

    def test_tpex_fixture_rows_have_price(self):
        result = self._call_with_fixture_env(
            "get_total_return_index", "TPEx", _START, _END
        )
        for row in result["rows"]:
            self.assertIn("price", row)

    # Test 3 — institutional total
    def test_institutional_total_fixture_ok(self):
        result = self._call_with_fixture_env(
            "get_institutional_investors_total", _START, _END
        )
        self.assertTrue(result["ok"], f"institutional fixture failed: {result}")
        self.assertGreater(result["row_count"], 0)
        self.assertIn("buy", result["columns"])
        self.assertIn("sell", result["columns"])

    def test_institutional_total_has_total_name_row(self):
        result = self._call_with_fixture_env(
            "get_institutional_investors_total", _START, _END
        )
        names = {r.get("name") for r in result["rows"]}
        self.assertIn("total", names)

    # Test 4 — margin total
    def test_margin_total_fixture_ok(self):
        result = self._call_with_fixture_env(
            "get_margin_purchase_short_sale_total", _START, _END
        )
        self.assertTrue(result["ok"], f"margin fixture failed: {result}")
        self.assertGreater(result["row_count"], 0)
        self.assertIn("TodayBalance", result["columns"])

    def test_margin_total_has_margin_purchase_row(self):
        result = self._call_with_fixture_env(
            "get_margin_purchase_short_sale_total", _START, _END
        )
        names = {r.get("name") for r in result["rows"]}
        self.assertIn("MarginPurchaseMoney", names)

    # Test 5a — 0050 fixture
    def test_stock_0050_fixture_ok(self):
        result = self._call_with_fixture_env(
            "get_reference_stock_daily", "0050", _START, _END
        )
        self.assertTrue(result["ok"], f"0050 fixture failed: {result}")
        self.assertGreater(result["row_count"], 0)
        self.assertEqual(result["data_id"], "0050")

    # Test 5b — 2330 fixture
    def test_stock_2330_fixture_ok(self):
        result = self._call_with_fixture_env(
            "get_reference_stock_daily", "2330", _START, _END
        )
        self.assertTrue(result["ok"], f"2330 fixture failed: {result}")
        self.assertGreater(result["row_count"], 0)
        self.assertIn("close", result["columns"])

    def test_trading_dates_fixture_ok(self):
        result = self._call_with_fixture_env("get_trading_dates", _START, _END)
        self.assertTrue(result["ok"])
        self.assertGreater(result["row_count"], 0)
        for row in result["rows"]:
            self.assertIn("date", row)


class TestNetworkGuard(unittest.TestCase):
    """DSA_ALLOW_EXTERNAL_NETWORK=false must block FinMind network calls."""

    # Test 6 — no-network guard
    def test_no_network_blocks_finmind_call(self):
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            # _no_network() must return True
            self.assertTrue(fetcher._no_network())

    def test_fixture_mode_blocks_network(self):
        env = {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            self.assertTrue(fetcher._no_network())

    def test_network_allowed_when_both_flags_set(self):
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            self.assertFalse(fetcher._no_network())


class TestRestShape(unittest.TestCase):
    """REST response normalization into standard result shape."""

    def _mock_session(self, status_code: int, body: Dict[str, Any]) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = body
        sess = MagicMock()
        sess.get.return_value = resp
        return sess

    # Test 7 — REST success normalizes shape
    def test_rest_success_normalized(self):
        body = {
            "status": 200,
            "msg": "success",
            "data": [
                {"date": "2026-06-12", "stock_id": "TAIEX", "price": 100933.47}
            ],
        }
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(
                fixture_root=_FIXTURE_ROOT, session=self._mock_session(200, body)
            )
            result = fetcher.get_total_return_index("TAIEX", _START, _END)

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "finmind")
        self.assertEqual(result["row_count"], 1)
        self.assertIn("price", result["columns"])
        self.assertIsNone(result["error"])
        self.assertIsNone(result["unavailable_reason"])
        self.assertIn("cache_meta", result)

    # Test 8 — HTTP 400/402/500 -> unavailable, no crash
    def test_http_402_returns_unavailable(self):
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(
                fixture_root=_FIXTURE_ROOT,
                session=self._mock_session(402, {"status": 402, "msg": "quota_exceeded", "data": []}),
            )
            result = fetcher.get_total_return_index("TAIEX", _START, _END)

        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["unavailable_reason"])
        self.assertEqual(result["rows"], [])

    def test_http_500_returns_unavailable(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.json.side_effect = Exception("parse error")
        sess = MagicMock()
        sess.get.return_value = resp

        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT, session=sess)
            result = fetcher.get_total_return_index("TAIEX", _START, _END)

        self.assertFalse(result["ok"])

    def test_finmind_api_status_nonzero_returns_unavailable(self):
        body = {"status": 400, "msg": "invalid_token", "data": []}
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(
                fixture_root=_FIXTURE_ROOT, session=self._mock_session(200, body)
            )
            result = fetcher.get_institutional_investors_total(_START, _END)

        self.assertFalse(result["ok"])

    # Test 9 — missing token allowed, no crash
    def test_missing_token_no_crash(self):
        body = {"status": 200, "msg": "success", "data": [
            {"date": "2026-06-12", "stock_id": "TAIEX", "price": 100933.47}
        ]}
        env = {
            "DSA_FIXTURE_MODE": "false",
            "DSA_ALLOW_EXTERNAL_NETWORK": "true",
            "FINMIND_API_TOKEN": "",
            "FINMIND_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(
                fixture_root=_FIXTURE_ROOT, session=self._mock_session(200, body)
            )
            # should not raise
            result = fetcher.get_total_return_index("TAIEX", _START, _END)
        self.assertIn("ok", result)

    def test_missing_token_get_token_returns_empty(self):
        env = {"FINMIND_API_TOKEN": "", "FINMIND_TOKEN": ""}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            token = fetcher._get_token()
        self.assertEqual(token, "")


class TestYfinanceFallback(unittest.TestCase):
    """yfinance fallback behavior."""

    # Test 10 — yfinance used only when FinMind unavailable
    def test_yfinance_not_used_when_finmind_ok(self):
        body = {"status": 200, "msg": "success", "data": [
            {"date": "2026-06-12", "stock_id": "0050", "close": 101.95}
        ]}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = body
        sess = MagicMock()
        sess.get.return_value = resp

        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT, session=sess)
            with patch("data_provider.taiwan_market.yfinance") as mock_yf:
                result = fetcher.get_reference_stock_daily("0050", _START, _END)

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "finmind")
        # yfinance must NOT have been called
        if hasattr(mock_yf, "Ticker"):
            mock_yf.Ticker.assert_not_called()

    # Test 11 — yfinance empty DataFrame -> unavailable
    def test_yfinance_empty_returns_unavailable(self):
        import pandas as pd
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        # First make FinMind fail
        body = {"status": 400, "msg": "error", "data": []}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = body
        sess = MagicMock()
        sess.get.return_value = resp

        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT, session=sess)
            with patch("data_provider.taiwan_market.yfinance") as mock_yf:
                mock_ticker = MagicMock()
                mock_ticker.history.return_value = pd.DataFrame()
                mock_yf.Ticker.return_value = mock_ticker
                result = fetcher.get_reference_stock_daily("0050", _START, _END)

        self.assertFalse(result["ok"])
        self.assertIn("yfinance_empty", (result.get("unavailable_reason") or ""))

    # Test 12 — TPEx yfinance fallback explicitly unavailable
    def test_tpex_yfinance_unavailable_no_symbol(self):
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        body = {"status": 400, "msg": "error", "data": []}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = body
        sess = MagicMock()
        sess.get.return_value = resp

        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT, session=sess)
            result = fetcher.get_total_return_index("TPEx", _START, _END)

        # TPEx uses FinMind only; no yfinance fallback registered for it
        self.assertFalse(result["ok"])


class TestSnapshot(unittest.TestCase):
    """Snapshot composition and availability flags."""

    def _fixture_snapshot(self) -> Dict[str, Any]:
        env = _fixture_env()
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            return fetcher.get_tw_market_snapshot(_START, _END)

    # Test 13 — snapshot includes required sections
    def test_snapshot_has_required_sections(self):
        snap = self._fixture_snapshot()
        for key in ("trading_dates", "taiex", "institutional_total", "margin_total", "availability"):
            self.assertIn(key, snap, f"Missing key {key!r} in snapshot")

    def test_snapshot_has_optional_sections(self):
        snap = self._fixture_snapshot()
        for key in ("tpex", "ref_0050", "ref_2330"):
            self.assertIn(key, snap)

    def test_snapshot_availability_struct(self):
        snap = self._fixture_snapshot()
        avail = snap["availability"]
        self.assertIn("required_ok", avail)
        self.assertIn("partial", avail)
        self.assertIn("missing_required", avail)
        self.assertIn("sources", avail)
        self.assertIn("as_of", avail)

    def test_snapshot_required_ok_true_in_fixture_mode(self):
        snap = self._fixture_snapshot()
        self.assertTrue(snap["availability"]["required_ok"])

    # Test 14 — required_ok false if TAIEX missing
    def test_snapshot_required_ok_false_when_taiex_missing(self):
        env = {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}
        body_error = {"status": 400, "msg": "error", "data": []}

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = body_error
        sess = MagicMock()
        sess.get.return_value = resp

        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT, session=sess)
            snap = fetcher.get_tw_market_snapshot(_START, _END)

        self.assertFalse(snap["availability"]["required_ok"])
        self.assertIn("taiex", snap["availability"]["missing_required"])

    def test_snapshot_as_of_is_last_taiex_date(self):
        snap = self._fixture_snapshot()
        if snap["taiex"]["ok"] and snap["taiex"]["rows"]:
            expected = snap["taiex"]["rows"][-1]["date"]
            self.assertEqual(snap["availability"]["as_of"], expected)


class TestNoCnFallback(unittest.TestCase):
    """No CN/A-share provider names or terms anywhere in the fetcher."""

    # Test 15 — no CN provider/query terms
    def test_no_cn_terms_in_module_source(self):
        import inspect
        import data_provider.taiwan_market as mod
        source = inspect.getsource(mod)
        for term in [
            "akshare", "baostock", "tushare", "efinance", "pytdx",
            "台股", "上證", "深證", "創業板", "滬深",
        ]:
            self.assertNotIn(term, source,
                             f"Forbidden CN term {term!r} found in taiwan_market.py")

    def test_result_shape_has_all_keys(self):
        env = _fixture_env()
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            result = fetcher.get_total_return_index("TAIEX", _START, _END)
        for key in ("ok", "source", "dataset", "data_id", "rows", "columns",
                    "row_count", "start_date", "end_date", "error",
                    "unavailable_reason", "cache_meta"):
            self.assertIn(key, result, f"Missing key {key!r} in result")

    def test_cache_meta_has_provider_field(self):
        env = _fixture_env()
        with patch.dict(os.environ, env, clear=False):
            fetcher = TaiwanMarketDataFetcher(fixture_root=_FIXTURE_ROOT)
            result = fetcher.get_total_return_index("TAIEX", _START, _END)
        self.assertIn("provider", result["cache_meta"])
        self.assertEqual(result["cache_meta"]["provider"], "TaiwanMarketDataFetcher")


class TestTWProfileStillPasses(unittest.TestCase):
    """Test 16 — TW profile tests still importable and TW_PROFILE correct."""

    def test_tw_profile_import_ok(self):
        from src.core.market_profile import TW_PROFILE, get_profile
        self.assertIsNotNone(TW_PROFILE)
        self.assertIs(get_profile("tw"), TW_PROFILE)

    def test_get_profile_unknown_raises(self):
        from src.core.market_profile import get_profile
        with self.assertRaises(ValueError):
            get_profile("jp")


class TestScopeGateStillDefersTW(unittest.TestCase):
    """Test 17 — Route B scope gate: TW is now implemented (Phase 7E-FINAL)."""

    def test_tw_now_implemented_routes_to_run(self):
        from src.core.market_review_scope_gate import filter_regions_for_route_b
        run, skipped_cn, deferred_tw = filter_regions_for_route_b(["tw"])
        self.assertIn("tw", run)
        self.assertEqual(deferred_tw, [])

    def test_us_still_runs(self):
        from src.core.market_review_scope_gate import filter_regions_for_route_b
        run, _s, _d = filter_regions_for_route_b(["us"])
        self.assertIn("us", run)


if __name__ == "__main__":
    unittest.main()

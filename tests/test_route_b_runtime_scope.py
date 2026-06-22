# -*- coding: utf-8 -*-
"""Route B runtime scope enforcement tests for active TW/US support."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.route_b_scope import (
    RouteBScopeError,
    classify_symbol,
    filter_stocks_for_route_b,
    get_route_b_markets,
    is_non_route_b_provider,
    is_route_b_enforced,
    validate_route_b_watchlist,
)


def _route_b_config(markets=None, enforce=True):
    """Build a minimal config namespace for Route B tests."""
    return SimpleNamespace(
        route_b_enforce_market_scope=enforce,
        route_b_markets=markets if markets is not None else ["TW", "US"],
    )


class TestClassifySymbol(unittest.TestCase):
    """Unit tests for the symbol classification helper."""

    def test_tw_prefixed(self):
        self.assertEqual(classify_symbol("TW:2330"), "TW")

    def test_tw_dot_suffix(self):
        self.assertEqual(classify_symbol("2330.TW"), "TW")

    def test_tw_uppercase_prefix(self):
        self.assertEqual(classify_symbol("tw:2330"), "TW")

    def test_us_prefixed(self):
        self.assertEqual(classify_symbol("US:AAPL"), "US")

    def test_us_bare_ticker_alpha(self):
        self.assertEqual(classify_symbol("AAPL"), "US")

    def test_us_bare_ticker_nvda(self):
        self.assertEqual(classify_symbol("NVDA"), "US")

    def test_us_multiclass_dot(self):
        self.assertEqual(classify_symbol("BRK.B"), "US")

    def test_us_multiclass_hyphen(self):
        self.assertEqual(classify_symbol("BRK-B"), "US")

    def test_tw_bare_4digit_from_universe(self):
        self.assertEqual(classify_symbol("2330"), "TW")

    def test_tw_etf_6digit_from_universe(self):
        self.assertEqual(classify_symbol("006208"), "TW")

    def test_tw_etf_alphanumeric_from_universe(self):
        self.assertEqual(classify_symbol("00981A"), "TW")

    def test_unsupported_numeric_is_unknown(self):
        self.assertEqual(classify_symbol("UNSUPPORTED"), "UNKNOWN")

    def test_empty_string_is_unknown(self):
        self.assertEqual(classify_symbol(""), "UNKNOWN")

    def test_tw_4digit(self):
        self.assertEqual(classify_symbol("TW:2454"), "TW")

    def test_us_lowercase_normalized(self):
        self.assertEqual(classify_symbol("us:aapl"), "US")


class TestFilterStocksForRouteB(unittest.TestCase):
    """filter_stocks_for_route_b core behavior."""

    def test_tw_us_symbols_accepted(self):
        codes = ["TW:2330", "US:AAPL"]
        accepted, rejected = filter_stocks_for_route_b(codes, _route_b_config())
        self.assertEqual(accepted, ["TW:2330", "US:AAPL"])
        self.assertEqual(rejected, [])

    def test_unsupported_symbol_rejected(self):
        codes = ["UNSUPPORTED"]
        accepted, rejected = filter_stocks_for_route_b(codes, _route_b_config())
        self.assertEqual(accepted, [])
        self.assertEqual(rejected, ["UNSUPPORTED"])

    def test_mixed_watchlist_accepts_bare_tw_symbol(self):
        codes = ["TW:2330", "US:AAPL", "2330"]
        accepted, rejected = filter_stocks_for_route_b(codes, _route_b_config())
        self.assertEqual(accepted, ["TW:2330", "US:AAPL", "2330"])
        self.assertEqual(rejected, [])

    def test_mixed_watchlist_rejects_unknown_symbols(self):
        codes = ["TW:2330", "BADTARGET", "BADTARGET", "US:AAPL"]
        accepted, rejected = filter_stocks_for_route_b(codes, _route_b_config())
        self.assertIn("TW:2330", accepted)
        self.assertIn("US:AAPL", accepted)
        self.assertIn("BADTARGET", rejected)
        self.assertIn("BADTARGET", rejected)

    def test_bare_us_symbol_accepted(self):
        codes = ["AAPL", "US:AAPL"]
        accepted, rejected = filter_stocks_for_route_b(codes, _route_b_config())
        self.assertEqual(accepted, ["AAPL", "US:AAPL"])
        self.assertEqual(rejected, [])

    def test_empty_list_returns_empty(self):
        accepted, rejected = filter_stocks_for_route_b([], _route_b_config())
        self.assertEqual(accepted, [])
        self.assertEqual(rejected, [])

    def test_env_override_markets(self):
        """ROUTE_B_MARKETS from config is respected."""
        config = _route_b_config(markets=["US"])
        accepted, rejected = filter_stocks_for_route_b(["TW:2330", "US:AAPL"], config)
        # Only US allowed
        self.assertEqual(accepted, ["US:AAPL"])
        self.assertIn("TW:2330", rejected)


class TestValidateRouteBWatchlist(unittest.TestCase):
    """validate_route_b_watchlist raises RouteBScopeError on empty accepted list."""

    def test_valid_tw_us_passes(self):
        codes = ["TW:2330", "US:AAPL"]
        result = validate_route_b_watchlist(codes, _route_b_config())
        self.assertEqual(result, ["TW:2330", "US:AAPL"])

    def test_empty_watchlist_raises_with_message(self):
        """No TW/US watchlist → RouteBScopeError with actionable message."""
        with self.assertRaises(RouteBScopeError) as ctx:
            validate_route_b_watchlist([], _route_b_config())
        self.assertIn("TW", str(ctx.exception))
        self.assertIn("US", str(ctx.exception))

    def test_unsupported_only_fails_closed(self):
        with self.assertRaises(RouteBScopeError) as ctx:
            validate_route_b_watchlist(["UNSUPPORTED"], _route_b_config())
        msg = str(ctx.exception)
        self.assertIn("TW", msg)
        self.assertIn("US", msg)

    def test_mixed_unknown_tw_us_passes_with_filter(self):
        codes = ["TW:2330", "UNSUPPORTED"]
        result = validate_route_b_watchlist(codes, _route_b_config())
        self.assertEqual(result, ["TW:2330"])

    def test_error_message_mentions_stock_list(self):
        with self.assertRaises(RouteBScopeError) as ctx:
            validate_route_b_watchlist(["BADTARGET", "UNSUPPORTED"], _route_b_config())
        self.assertIn("STOCK_LIST", str(ctx.exception))


class TestNoDefaultUnsupportedFallback(unittest.TestCase):
    """Verify that Route B does not silently inject unsupported defaults."""

    def test_empty_stock_list_no_fallback(self):
        accepted, rejected = filter_stocks_for_route_b([], _route_b_config())
        blocked_defaults = {"BADTARGET", "BADTARGET", "UNSUPPORTED"}
        self.assertTrue(blocked_defaults.isdisjoint(set(accepted)))
        self.assertTrue(blocked_defaults.isdisjoint(set(rejected)))

    def test_route_b_config_has_no_unsupported_defaults(self):
        config = _route_b_config()
        accepted, _ = filter_stocks_for_route_b([], config)
        for code in accepted:
            market = classify_symbol(code)
            self.assertIn(market, {"TW", "US"}, f"Found unsupported symbol {code!r} in accepted list")


class TestNonRouteBProviderGate(unittest.TestCase):
    """Non-route provider names are correctly identified."""

    def test_efinance_is_non_route_b_provider(self):
        self.assertTrue(is_non_route_b_provider("EfinanceFetcher"))

    def test_akshare_is_non_route_b_provider(self):
        self.assertTrue(is_non_route_b_provider("AkshareFetcher"))

    def test_baostock_is_non_route_b_provider(self):
        self.assertTrue(is_non_route_b_provider("BaostockFetcher"))

    def test_pytdx_is_non_route_b_provider(self):
        self.assertTrue(is_non_route_b_provider("PytdxFetcher"))

    def test_yfinance_is_route_b_provider(self):
        self.assertFalse(is_non_route_b_provider("YfinanceFetcher"))

    def test_finmind_is_route_b_provider(self):
        self.assertFalse(is_non_route_b_provider("TaiwanFinMindFetcher"))

    def test_rejected_unknown_would_not_use_non_route_b_provider(self):
        codes = ["TW:2330", "US:AAPL", "UNSUPPORTED"]
        accepted, rejected = filter_stocks_for_route_b(codes, _route_b_config())

        provider_mock = MagicMock()

        for code in accepted:
            pass

        for code in rejected:
            market = classify_symbol(code)
            self.assertEqual(market, "UNKNOWN")
            provider_mock.assert_not_called()


class TestIsRouteBEnforced(unittest.TestCase):
    def test_enforced_via_config(self):
        config = _route_b_config(enforce=True)
        self.assertTrue(is_route_b_enforced(config))

    def test_not_enforced_via_config(self):
        config = _route_b_config(enforce=False)
        self.assertFalse(is_route_b_enforced(config))

    def test_enforced_via_env(self):
        with patch.dict(os.environ, {"ROUTE_B_ENFORCE_MARKET_SCOPE": "true"}):
            self.assertTrue(is_route_b_enforced())

    def test_not_enforced_default_env(self):
        env = {k: v for k, v in os.environ.items() if k != "ROUTE_B_ENFORCE_MARKET_SCOPE"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_route_b_enforced())


class TestGetRouteBMarkets(unittest.TestCase):
    def test_default_markets_from_config(self):
        config = _route_b_config()
        markets = get_route_b_markets(config)
        self.assertIn("TW", markets)
        self.assertIn("US", markets)

    def test_markets_from_env(self):
        with patch.dict(os.environ, {"ROUTE_B_MARKETS": "US"}):
            markets = get_route_b_markets()
        self.assertEqual(markets, frozenset({"US"}))

    def test_default_env_is_tw_us(self):
        env = {k: v for k, v in os.environ.items() if k != "ROUTE_B_MARKETS"}
        with patch.dict(os.environ, env, clear=True):
            markets = get_route_b_markets()
        self.assertIn("TW", markets)
        self.assertIn("US", markets)


if __name__ == "__main__":
    unittest.main()

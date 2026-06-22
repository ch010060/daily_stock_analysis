# -*- coding: utf-8 -*-
"""Regression tests for Route B API scope enforcement.

The active product lookup route is TW/US only.  Unknown symbols must fail
closed instead of being ranked against unsupported market universes.
"""

import pytest


class TestClassifySymbol:
    def setup_method(self):
        from src.core.route_b_scope import classify_symbol

        self.classify = classify_symbol

    def test_tw_symbols_from_local_universe(self):
        assert self.classify("TW:2330") == "TW"
        assert self.classify("2330.TW") == "TW"
        assert self.classify("2330") == "TW"
        assert self.classify("006208") == "TW"
        assert self.classify("00981A") == "TW"

    def test_us_symbols_from_local_universe(self):
        assert self.classify("AAPL") == "US"
        assert self.classify("US:AAPL") == "US"
        assert self.classify("BRK.B") == "US"

    def test_unknown_symbols_are_not_classified_as_supported(self):
        assert self.classify("") == "UNKNOWN"
        assert self.classify("UNKNOWN_TARGET") == "UNKNOWN"


class TestIsCodeLike:
    def setup_method(self):
        from src.services.stock_code_utils import is_code_like

        self.is_code_like = is_code_like

    def test_tw_formats_are_code_like(self):
        assert self.is_code_like("2330") is True
        assert self.is_code_like("006208") is True
        assert self.is_code_like("00981A") is True
        assert self.is_code_like("TW:2330") is True
        assert self.is_code_like("2330.TW") is True

    def test_us_formats_are_code_like(self):
        assert self.is_code_like("AAPL") is True
        assert self.is_code_like("US:AAPL") is True
        assert self.is_code_like("BRK.B") is True

    def test_unknown_text_is_not_code_like(self):
        assert self.is_code_like("not_a_code") is False
        assert self.is_code_like("") is False


class TestFilterStocksForRouteB:
    def setup_method(self):
        from src.core.route_b_scope import filter_stocks_for_route_b

        self.filter = filter_stocks_for_route_b

    def test_tw_us_symbols_are_accepted(self):
        accepted, rejected = self.filter(["2330", "00981A", "AAPL"])
        assert accepted == ["2330", "00981A", "AAPL"]
        assert rejected == []

    def test_unknown_symbols_are_rejected(self):
        accepted, rejected = self.filter(["2330", "UNKNOWN_TARGET", "AAPL"])
        assert accepted == ["2330", "AAPL"]
        assert rejected == ["UNKNOWN_TARGET"]

    def test_empty_input(self):
        accepted, rejected = self.filter([])
        assert accepted == []
        assert rejected == []


class TestTriggerAnalysisRouteBGate:
    """Route gate tests must not trigger live analysis or LLM side effects."""

    def test_unknown_code_rejected_when_route_b_enforced(self, monkeypatch):
        monkeypatch.setenv("ROUTE_B_ENFORCE_MARKET_SCOPE", "true")
        monkeypatch.setenv("ROUTE_B_MARKETS", "TW,US")
        from src.core.route_b_scope import RouteBScopeError, validate_route_b_watchlist

        with pytest.raises(RouteBScopeError):
            validate_route_b_watchlist(["UNKNOWN_TARGET"])

    def test_tw_code_not_rejected_when_route_b_enforced(self, monkeypatch):
        monkeypatch.setenv("ROUTE_B_ENFORCE_MARKET_SCOPE", "true")
        monkeypatch.setenv("ROUTE_B_MARKETS", "TW,US")
        from src.core.route_b_scope import validate_route_b_watchlist

        assert validate_route_b_watchlist(["2330"]) == ["2330"]

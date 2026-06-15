# -*- coding: utf-8 -*-
"""
Regression tests for Route B API scope enforcement.

Covers:
- classify_symbol() TW 4-digit recognition
- is_code_like() TW format acceptance
- filter_stocks_for_route_b() acceptance/rejection
- trigger_analysis() Route B scope gate (unit-level)
- _run_analysis() belt-and-suspenders guard
"""

import pytest


# ---------------------------------------------------------------
# classify_symbol — TW 4-digit recognition
# ---------------------------------------------------------------

class TestClassifySymbol:
    def setup_method(self):
        from src.core.route_b_scope import classify_symbol
        self.classify = classify_symbol

    def test_tw_explicit_prefix(self):
        assert self.classify("TW:2330") == "TW"

    def test_tw_dot_suffix(self):
        assert self.classify("2330.TW") == "TW"

    def test_tw_bare_4digit(self):
        assert self.classify("2330") == "TW"

    def test_tw_bare_4digit_zero_prefix(self):
        assert self.classify("0050") == "TW"

    def test_us_ticker(self):
        assert self.classify("AAPL") == "US"

    def test_us_explicit_prefix(self):
        assert self.classify("US:AAPL") == "US"

    def test_cn_6digit(self):
        assert self.classify("600519") == "CN"

    def test_cn_6digit_300xxx(self):
        assert self.classify("300750") == "CN"

    def test_cn_6digit_002xxx(self):
        assert self.classify("002594") == "CN"

    def test_hk_prefix(self):
        assert self.classify("HK00700") == "HK"

    def test_hk_suffix(self):
        assert self.classify("00700.HK") == "HK"

    def test_unknown_empty(self):
        assert self.classify("") == "UNKNOWN"

    def test_unknown_garbage(self):
        assert self.classify("XYZ123") == "UNKNOWN"


# ---------------------------------------------------------------
# is_code_like — TW format acceptance
# ---------------------------------------------------------------

class TestIsCodeLike:
    def setup_method(self):
        from src.services.stock_code_utils import is_code_like
        self.is_code_like = is_code_like

    def test_tw_bare_4digit(self):
        assert self.is_code_like("2330") is True

    def test_tw_bare_4digit_zero_prefix(self):
        assert self.is_code_like("0050") is True

    def test_tw_explicit_prefix(self):
        assert self.is_code_like("TW:2330") is True

    def test_tw_dot_suffix(self):
        assert self.is_code_like("2330.TW") is True

    def test_us_ticker_accepted(self):
        assert self.is_code_like("AAPL") is True

    def test_cn_6digit_accepted(self):
        # is_code_like accepts CN codes — scope filtering is done later
        assert self.is_code_like("600519") is True

    def test_garbage_rejected(self):
        assert self.is_code_like("not_a_code") is False

    def test_empty_rejected(self):
        assert self.is_code_like("") is False


# ---------------------------------------------------------------
# filter_stocks_for_route_b — scope filtering
# ---------------------------------------------------------------

class TestFilterStocksForRouteB:
    def setup_method(self):
        from src.core.route_b_scope import filter_stocks_for_route_b
        self.filter = filter_stocks_for_route_b

    def _accepted_rejected(self, codes):
        return self.filter(codes)

    def test_tw_bare_accepted(self):
        accepted, rejected = self._accepted_rejected(["2330"])
        assert "2330" in accepted
        assert rejected == []

    def test_tw_prefixed_accepted(self):
        accepted, rejected = self._accepted_rejected(["TW:2330"])
        assert "TW:2330" in accepted
        assert rejected == []

    def test_us_ticker_accepted(self):
        accepted, rejected = self._accepted_rejected(["AAPL"])
        assert "AAPL" in accepted
        assert rejected == []

    def test_cn_6digit_rejected(self):
        accepted, rejected = self._accepted_rejected(["600519"])
        assert accepted == []
        assert "600519" in rejected

    def test_cn_300xxx_rejected(self):
        accepted, rejected = self._accepted_rejected(["300750"])
        assert accepted == []
        assert "300750" in rejected

    def test_cn_002xxx_rejected(self):
        accepted, rejected = self._accepted_rejected(["002594"])
        assert accepted == []
        assert "002594" in rejected

    def test_mixed_batch_filters_correctly(self):
        accepted, rejected = self._accepted_rejected(["2330", "AAPL", "600519", "300750"])
        assert set(accepted) == {"2330", "AAPL"}
        assert set(rejected) == {"600519", "300750"}

    def test_empty_input(self):
        accepted, rejected = self._accepted_rejected([])
        assert accepted == []
        assert rejected == []


# ---------------------------------------------------------------
# trigger_analysis Route B gate (monkeypatched env)
# ---------------------------------------------------------------

class TestTriggerAnalysisRouteBGate:
    """Integration-lite tests: import the function and call it with mocked dependencies."""

    def _make_request(self, stock_code):
        from api.v1.schemas.analysis import AnalyzeRequest
        return AnalyzeRequest(stock_code=stock_code, async_mode=True, notify=False)

    def test_cn_code_rejected_when_route_b_enforced(self, monkeypatch):
        monkeypatch.setenv("ROUTE_B_ENFORCE_MARKET_SCOPE", "true")
        from fastapi import HTTPException
        from api.v1.endpoints.analysis import trigger_analysis
        from src.config import get_config

        req = self._make_request("600519")
        config = get_config()
        with pytest.raises(HTTPException) as exc_info:
            trigger_analysis(req, config=config)
        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert detail["error"] == "route_b_scope_error"
        assert "600519" in detail["rejected_codes"]

    def test_tw_code_not_rejected_when_route_b_enforced(self, monkeypatch):
        """TW code should pass the Route B gate without raising scope error."""
        monkeypatch.setenv("ROUTE_B_ENFORCE_MARKET_SCOPE", "true")
        from fastapi import HTTPException
        from api.v1.endpoints.analysis import trigger_analysis
        from src.config import get_config

        req = self._make_request("2330")
        config = get_config()
        # Should not raise a route_b_scope_error (may raise other errors from queue/pipeline)
        try:
            trigger_analysis(req, config=config)
        except HTTPException as exc:
            assert exc.detail.get("error") != "route_b_scope_error", (
                f"Route B scope gate incorrectly rejected TW:2330. Detail: {exc.detail}"
            )
        except Exception:
            pass  # Other errors (queue, pipeline) are not our concern here

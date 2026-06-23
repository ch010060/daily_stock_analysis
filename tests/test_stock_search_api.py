# -*- coding: utf-8 -*-
"""Tests for TW/US stock symbol search and resolve API helpers."""

from __future__ import annotations

from api.v1.endpoints import stocks as stocks_endpoint


def _candidate_symbols(response) -> list[str]:
    return [candidate.raw_symbol for candidate in response.candidates]


def test_search_symbols_returns_route_b_tw_candidate_before_unsupported_numeric_collisions() -> None:
    response = stocks_endpoint.search_symbols(q="8299", limit=5)

    assert response.query == "8299"
    assert response.candidates
    assert response.candidates[0].raw_symbol == "8299"
    assert response.candidates[0].market == "TW"
    assert "UNSUPPORTED" not in _candidate_symbols(response)


def test_search_symbols_supports_required_tw_us_names_and_aliases() -> None:
    cases = {
        "台積電": ("TW", "2330"),
        "TSMC": ("TW", "2330"),
        "鴻海": ("TW", "2317"),
        "Hon Hai": ("TW", "2317"),
        "Foxconn": ("TW", "2317"),
        "聯發科": ("TW", "2454"),
        "MediaTek": ("TW", "2454"),
        "大立光": ("TW", "3008"),
        "Largan": ("TW", "3008"),
        "群聯": ("TW", "8299"),
        "Phison": ("TW", "8299"),
        "聯電": ("TW", "2303"),
        "2303": ("TW", "2303"),
        "國泰金": ("TW", "2882"),
        "2882": ("TW", "2882"),
        "Apple": ("US", "AAPL"),
        "AAPL": ("US", "AAPL"),
        "Microsoft": ("US", "MSFT"),
        "MSFT": ("US", "MSFT"),
        "Google": ("US", "GOOGL"),
        "Alphabet": ("US", "GOOGL"),
        "Amazon": ("US", "AMZN"),
        "AMZN": ("US", "AMZN"),
        "Tesla": ("US", "TSLA"),
        "TSLA": ("US", "TSLA"),
        "NVIDIA": ("US", "NVDA"),
        "NVDA": ("US", "NVDA"),
        "META": ("US", "META"),
        "Meta Platforms": ("US", "META"),
        "Facebook": ("US", "META"),
        "SPY": ("US", "SPY"),
        "QQQ": ("US", "QQQ"),
        "VOO": ("US", "VOO"),
        "S&P500": ("US", "SPX"),
        "^GSPC": ("US", "SPX"),
        "標普500": ("US", "SPX"),
        "00981A": ("TW", "00981A"),
        "主動統一台股增長": ("TW", "00981A"),
        "006208": ("TW", "006208"),
        "富邦台50": ("TW", "006208"),
    }

    for query, (market, symbol) in cases.items():
        response = stocks_endpoint.search_symbols(q=query, limit=5)
        assert response.candidates, query
        assert response.candidates[0].market == market
        assert response.candidates[0].raw_symbol == symbol


def test_search_symbols_supports_expanded_tw_us_matrix() -> None:
    cases = {
        "2308": ("TW", "2308"),
        "台達電": ("TW", "2308"),
        "Delta Electronics": ("TW", "2308"),
        "2382": ("TW", "2382"),
        "廣達": ("TW", "2382"),
        "Quanta": ("TW", "2382"),
        "6669": ("TW", "6669"),
        "緯穎": ("TW", "6669"),
        "Wiwynn": ("TW", "6669"),
        "3017": ("TW", "3017"),
        "奇鋐": ("TW", "3017"),
        "AVC": ("TW", "3017"),
        "Asia Vital Components": ("TW", "3017"),
        "2368": ("TW", "2368"),
        "金像電": ("TW", "2368"),
        "Kinsus": ("TW", "2368"),
        "2345": ("TW", "2345"),
        "智邦": ("TW", "2345"),
        "Accton": ("TW", "2345"),
        "3037": ("TW", "3037"),
        "欣興": ("TW", "3037"),
        "Unimicron": ("TW", "3037"),
        "3661": ("TW", "3661"),
        "世芯-KY": ("TW", "3661"),
        "Alchip": ("TW", "3661"),
        "MSFT": ("US", "MSFT"),
        "Microsoft": ("US", "MSFT"),
        "GOOGL": ("US", "GOOGL"),
        "Google": ("US", "GOOGL"),
        "Alphabet": ("US", "GOOGL"),
        "AMZN": ("US", "AMZN"),
        "Amazon": ("US", "AMZN"),
        "TSLA": ("US", "TSLA"),
        "Tesla": ("US", "TSLA"),
        "AVGO": ("US", "AVGO"),
        "Broadcom": ("US", "AVGO"),
        "AMD": ("US", "AMD"),
        "Advanced Micro Devices": ("US", "AMD"),
        "MU": ("US", "MU"),
        "Micron": ("US", "MU"),
        "ARM": ("US", "ARM"),
        "Arm Holdings": ("US", "ARM"),
        "ORCL": ("US", "ORCL"),
        "Oracle": ("US", "ORCL"),
        "PLTR": ("US", "PLTR"),
        "Palantir": ("US", "PLTR"),
    }

    for query, (market, symbol) in cases.items():
        response = stocks_endpoint.search_symbols(q=query, limit=5)
        assert response.candidates, query
        assert response.candidates[0].market == market
        assert response.candidates[0].raw_symbol == symbol
        assert all(candidate.market in {"TW", "US"} for candidate in response.candidates)


def test_search_symbols_supports_phase15_9o_alias_matrix() -> None:
    cases = {
        "Wistron": ("TW", "3231"),
        "Inventec": ("TW", "2356"),
        "Gigabyte": ("TW", "2376"),
        "Nanya Technology": ("TW", "2408"),
        "AUO": ("TW", "2409"),
        "China Steel": ("TW", "2002"),
        "CTBC Financial": ("TW", "2891"),
        "First Financial": ("TW", "2892"),
        "Taiwan Cooperative Financial": ("TW", "5880"),
        "Taiwan Cement": ("TW", "1101"),
        "Far Eastern New Century": ("TW", "1402"),
        "General Electric": ("US", "GE"),
        "Cisco": ("US", "CSCO"),
        "Costco": ("US", "COST"),
        "Salesforce": ("US", "CRM"),
    }

    for query, (market, symbol) in cases.items():
        response = stocks_endpoint.search_symbols(q=query, limit=5)
        assert response.candidates, query
        assert response.candidates[0].market == market
        assert response.candidates[0].raw_symbol == symbol
        assert all(candidate.market in {"TW", "US"} for candidate in response.candidates)


def test_resolve_symbol_does_not_return_known_wrong_phase15_9o_substitutions() -> None:
    ge = stocks_endpoint.resolve_symbol(q="General Electric", limit=5)
    assert ge.status == "resolved"
    assert ge.selected is not None
    assert ge.selected.raw_symbol == "GE"
    assert ge.selected.raw_symbol != "POR"

    first_financial = stocks_endpoint.resolve_symbol(q="First Financial", limit=5)
    assert first_financial.status == "ambiguous"
    assert first_financial.selected is None
    assert first_financial.candidates[0].market == "TW"
    assert first_financial.candidates[0].raw_symbol == "2892"
    assert any(candidate.raw_symbol == "THFF" for candidate in first_financial.candidates)

    first_financial_tw = stocks_endpoint.resolve_symbol(q="First Financial", limit=5, market="TW")
    assert first_financial_tw.status == "resolved"
    assert first_financial_tw.selected is not None
    assert first_financial_tw.selected.market == "TW"
    assert first_financial_tw.selected.raw_symbol == "2892"

    first_financial_us = stocks_endpoint.resolve_symbol(q="First Financial", limit=5, market="US")
    assert first_financial_us.status == "resolved"
    assert first_financial_us.selected is not None
    assert first_financial_us.selected.market == "US"
    assert first_financial_us.selected.raw_symbol == "THFF"


def test_search_symbols_supports_market_scoped_exact_alias_collisions() -> None:
    tw = stocks_endpoint.search_symbols(q="First Financial", limit=5, market="TW")
    us = stocks_endpoint.search_symbols(q="First Financial", limit=5, market="US")

    assert tw.candidates
    assert tw.candidates[0].market == "TW"
    assert tw.candidates[0].raw_symbol == "2892"
    assert all(candidate.market == "TW" for candidate in tw.candidates)

    assert us.candidates
    assert us.candidates[0].market == "US"
    assert us.candidates[0].raw_symbol == "THFF"
    assert all(candidate.market == "US" for candidate in us.candidates)


def test_resolve_symbol_returns_selected_candidate_for_high_confidence_matches() -> None:
    response = stocks_endpoint.resolve_symbol(q="群聯")

    assert response.status == "resolved"
    assert response.selected is not None
    assert response.selected.raw_symbol == "8299"
    assert response.selected.market == "TW"
    assert response.selected.name == "群聯"


def test_resolve_symbol_returns_not_found_without_generic_400_for_unsupported_query() -> None:
    response = stocks_endpoint.resolve_symbol(q="不存在的支援標的")

    assert response.status == "not_found"
    assert response.selected is None
    assert response.message == "找不到支援的台股 / 美股標的"


def test_search_symbols_excludes_non_tw_us_route_b_candidates() -> None:
    for query in ("UNSUPPORTED_TARGET", "不存在市場標的"):
        response = stocks_endpoint.search_symbols(q=query, limit=5)
        assert response.candidates == [], query

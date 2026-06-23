# -*- coding: utf-8 -*-
"""Expanded TW/US-only symbol resolver matrix for Route B."""

from __future__ import annotations

import sys
import types

from src.services.symbol_universe import (
    DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
    SymbolResolver,
    SymbolUniverseCache,
)


TW_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("2308", ("2308", "台達電", "Delta Electronics")),
    ("2382", ("2382", "廣達", "Quanta")),
    ("6669", ("6669", "緯穎", "Wiwynn")),
    ("3017", ("3017", "奇鋐", "AVC", "Asia Vital Components")),
    ("2368", ("2368", "金像電", "Kinsus")),
    ("2345", ("2345", "智邦", "Accton")),
    ("3037", ("3037", "欣興", "Unimicron")),
    ("3661", ("3661", "世芯-KY", "世芯", "Alchip")),
    ("2303", ("2303", "聯電", "UMC")),
    ("2882", ("2882", "國泰金", "Cathay Financial")),
    ("00981A", ("00981A", "主動統一台股增長")),
    ("006208", ("006208", "富邦台50")),
)

US_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MSFT", ("MSFT", "Microsoft")),
    ("GOOGL", ("GOOGL", "Alphabet", "Google")),
    ("AMZN", ("AMZN", "Amazon")),
    ("TSLA", ("TSLA", "Tesla")),
    ("AVGO", ("AVGO", "Broadcom")),
    ("AMD", ("AMD", "Advanced Micro Devices")),
    ("MU", ("MU", "Micron", "Micron Technology")),
    ("ARM", ("ARM", "Arm", "Arm Holdings")),
    ("ORCL", ("ORCL", "Oracle")),
    ("PLTR", ("PLTR", "Palantir", "Palantir Technologies")),
)

PHASE_15_9I_TW_ALIAS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("2379", ("Realtek",)),
    ("2357", ("ASUS", "Asus")),
    ("2327", ("Yageo",)),
    ("2395", ("Advantech",)),
    ("3711", ("ASE", "ASE Technology")),
)

PHASE_15_9I_US_ALIAS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CSCO", ("Cisco", "Cisco Systems")),
    ("COST", ("Costco", "Costco Wholesale")),
)

PHASE_15_9O_TW_ALIAS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("3231", ("Wistron",)),
    ("2356", ("Inventec",)),
    ("2376", ("Gigabyte",)),
    ("2408", ("Nanya Technology",)),
    ("2409", ("AUO",)),
    ("2002", ("China Steel",)),
    ("2891", ("CTBC Financial",)),
    ("2892", ("First Financial",)),
    ("5880", ("Taiwan Cooperative Financial",)),
    ("1101", ("Taiwan Cement",)),
    ("1402", ("Far Eastern New Century",)),
)

PHASE_15_9O_US_ALIAS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CRM", ("Salesforce",)),
    ("IBM", ("International Business Machines",)),
    ("JPM", ("JPMorgan Chase",)),
    ("BAC", ("Bank of America",)),
    ("WMT", ("Walmart",)),
    ("HD", ("Home Depot",)),
    ("DIS", ("Disney",)),
    ("UBER", ("Uber",)),
    ("SNOW", ("Snowflake",)),
    ("GE", ("General Electric",)),
    ("CAT", ("Caterpillar",)),
)


def _resolver() -> SymbolResolver:
    return SymbolResolver(SymbolUniverseCache.from_json_snapshot(DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH))


def test_expanded_tw_matrix_resolves_from_local_universe() -> None:
    resolver = _resolver()

    for expected_symbol, queries in TW_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "TW"
            assert result.selected.raw_symbol == expected_symbol
            assert all(candidate.record.market == "TW" or candidate.record.market == "US" for candidate in result.candidates)


def test_expanded_us_matrix_resolves_from_local_universe() -> None:
    resolver = _resolver()

    for expected_symbol, queries in US_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "US"
            assert result.selected.raw_symbol == expected_symbol
            assert all(candidate.record.market == "TW" or candidate.record.market == "US" for candidate in result.candidates)


def test_phase15_9i_live_blocker_aliases_resolve_to_intended_tw_targets() -> None:
    resolver = _resolver()

    for expected_symbol, queries in PHASE_15_9I_TW_ALIAS_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "TW"
            assert result.selected.raw_symbol == expected_symbol
            assert all(candidate.record.market in {"TW", "US"} for candidate in result.candidates)


def test_phase15_9i_live_blocker_aliases_resolve_to_intended_us_targets() -> None:
    resolver = _resolver()

    for expected_symbol, queries in PHASE_15_9I_US_ALIAS_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "US"
            assert result.selected.raw_symbol == expected_symbol
            assert all(candidate.record.market in {"TW", "US"} for candidate in result.candidates)


def test_phase15_9o_final_validation_tw_english_aliases_resolve() -> None:
    resolver = _resolver()

    for expected_symbol, queries in PHASE_15_9O_TW_ALIAS_TARGETS:
        for query in queries:
            market = "TW" if expected_symbol == "2892" and query == "First Financial" else None
            result = resolver.resolve(query, market=market)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "TW"
            assert result.selected.raw_symbol == expected_symbol
            assert all(candidate.record.market in {"TW", "US"} for candidate in result.candidates)


def test_phase15_9o_final_validation_us_common_names_resolve() -> None:
    resolver = _resolver()

    for expected_symbol, queries in PHASE_15_9O_US_ALIAS_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "US"
            assert result.selected.raw_symbol == expected_symbol
            assert all(candidate.record.market in {"TW", "US"} for candidate in result.candidates)


def test_phase15_9o_wrong_substitution_guards() -> None:
    resolver = _resolver()

    general_electric = resolver.resolve("General Electric")
    assert general_electric.status == "resolved"
    assert general_electric.selected is not None
    assert general_electric.selected.raw_symbol == "GE"
    assert general_electric.selected.raw_symbol != "POR"

    first_financial = resolver.resolve("First Financial")
    assert first_financial.status == "ambiguous"
    assert first_financial.selected is None
    assert first_financial.candidates[0].record.market == "TW"
    assert first_financial.candidates[0].record.raw_symbol == "2892"
    assert any(candidate.record.raw_symbol == "THFF" for candidate in first_financial.candidates)

    first_financial_tw = resolver.resolve("First Financial", market="TW")
    assert first_financial_tw.status == "resolved"
    assert first_financial_tw.selected is not None
    assert first_financial_tw.selected.market == "TW"
    assert first_financial_tw.selected.raw_symbol == "2892"

    first_financial_us = resolver.resolve("First Financial", market="US")
    assert first_financial_us.status == "resolved"
    assert first_financial_us.selected is not None
    assert first_financial_us.selected.market == "US"
    assert first_financial_us.selected.raw_symbol == "THFF"


PHASE_15_9R_PRIMARY_TARGETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("TW", "4938", ("和碩", "4938", "Pegatron")),
    ("US", "NOW", ("NOW", "ServiceNow")),
)

PHASE_15_9R_TW_ALIAS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("3443", ("Global Unichip",)),
    ("2912", ("President Chain Store",)),
)


def test_phase15_9r_primary_targets_resolve() -> None:
    resolver = _resolver()

    for expected_market, expected_symbol, queries in PHASE_15_9R_PRIMARY_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == expected_market
            assert result.selected.raw_symbol == expected_symbol


def test_phase15_9r_tw_full_english_name_aliases_resolve() -> None:
    resolver = _resolver()

    for expected_symbol, queries in PHASE_15_9R_TW_ALIAS_TARGETS:
        for query in queries:
            result = resolver.resolve(query)

            assert result.status == "resolved", query
            assert result.selected is not None
            assert result.selected.market == "TW"
            assert result.selected.raw_symbol == expected_symbol


def test_phase15_9r_team_no_market_query_does_not_auto_resolve_to_tw_4967() -> None:
    """Backend already disambiguates TW:4967's `TEAM` alias against US:TISI's `Team`
    name; this guards that behavior. The live-validation bug was in the frontend's
    local search ranking (searchStocks.ts), not in this resolver."""
    resolver = _resolver()

    result = resolver.resolve("TEAM")

    assert result.status == "ambiguous"
    assert result.selected is None
    candidate_symbols = {candidate.record.raw_symbol for candidate in result.candidates}
    assert "4967" in candidate_symbols
    assert "TISI" in candidate_symbols

    tw_scoped = resolver.resolve("TEAM", market="TW")
    assert tw_scoped.status == "resolved"
    assert tw_scoped.selected is not None
    assert tw_scoped.selected.market == "TW"
    assert tw_scoped.selected.raw_symbol == "4967"


def test_route_b_resolver_returns_not_found_for_unknown_query() -> None:
    resolver = _resolver()

    for query in ("UNSUPPORTED_TARGET", "不存在市場標的"):
        result = resolver.resolve(query)

        assert result.status == "not_found", query
        assert result.selected is None
        assert result.candidates == []


def test_route_b_resolver_does_not_call_llm(monkeypatch) -> None:
    class FailingLlmModule(types.ModuleType):
        def __getattr__(self, name: str):  # pragma: no cover - should never be reached
            raise AssertionError(f"resolver attempted to use LLM module attribute {name}")

    monkeypatch.setitem(sys.modules, "src.llm", FailingLlmModule("src.llm"))
    monkeypatch.setitem(sys.modules, "src.llm_client", FailingLlmModule("src.llm_client"))

    resolver = _resolver()
    result = resolver.resolve("Delta Electronics")

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.raw_symbol == "2308"

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

# -*- coding: utf-8 -*-
"""Tests for the provider-backed TW/US symbol universe and resolver."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from src.data.stock_mapping import STOCK_NAME_MAP
from src.services.symbol_universe import (
    CuratedSeedSymbolProvider,
    JsonSymbolUniverseProvider,
    StaticSymbolUniverseProvider,
    SymbolRecord,
    SymbolResolver,
    SymbolUniverseCache,
)


def _record(
    canonical_symbol: str,
    raw_symbol: str,
    market: str,
    name: str,
    aliases: list[str] | None = None,
    instrument_type: str = "stock",
    provider_source: str = "test_provider",
) -> SymbolRecord:
    return SymbolRecord(
        canonical_symbol=canonical_symbol,
        raw_symbol=raw_symbol,
        market=market,
        exchange=None,
        instrument_type=instrument_type,
        name=name,
        aliases=aliases or [],
        provider_source=provider_source,
        is_active=True,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


def _resolver_with_provider_records(records: list[SymbolRecord]) -> SymbolResolver:
    cache = SymbolUniverseCache.from_providers(
        [
            StaticSymbolUniverseProvider("legacy_collision_fixture", records),
            CuratedSeedSymbolProvider(),
        ]
    )
    return SymbolResolver(cache)


def test_curated_seed_contains_required_tw_us_bootstrap_records() -> None:
    cache = SymbolUniverseCache.from_providers([CuratedSeedSymbolProvider()])

    for raw_symbol, expected_name in {
        "2330": "台積電",
        "2317": "鴻海",
        "2454": "聯發科",
        "3008": "大立光",
        "8299": "群聯",
        "AAPL": "Apple",
        "NVDA": "NVIDIA",
        "META": "Meta Platforms",
        "SPY": "SPDR S&P 500 ETF",
        "SPX": "標普500指數",
    }.items():
        record = cache.get_by_raw_symbol(raw_symbol)
        assert record is not None, raw_symbol
        assert record.name == expected_name
        assert record.market in {"TW", "US"}
        assert record.provider_source == "curated_seed"


def test_symbol_universe_cache_round_trips_json_snapshot(tmp_path) -> None:
    snapshot = tmp_path / "symbol_universe.json"
    cache = SymbolUniverseCache.from_providers([CuratedSeedSymbolProvider()])

    cache.save_json_snapshot(snapshot)
    restored = SymbolUniverseCache.from_providers([
        JsonSymbolUniverseProvider("snapshot", snapshot)
    ])

    phison = restored.get_by_raw_symbol("8299")
    meta = restored.get_by_raw_symbol("META")
    assert phison is not None
    assert phison.name == "群聯"
    assert phison.provider_source == "curated_seed"
    assert meta is not None
    assert meta.name == "Meta Platforms"


def test_stock_name_map_contains_only_route_b_markets() -> None:
    assert all(
        re.fullmatch(r"\d{4}", code) or re.fullmatch(r"[A-Z]{1,5}", code)
        for code in STOCK_NAME_MAP
    )


def test_provider_records_merge_with_seed_and_ignore_non_route_b_records() -> None:
    resolver = _resolver_with_provider_records(
        [
            _record("ZZ:TEST", "TEST", "ZZ", "不支援市場測試資料"),
        ]
    )

    result = resolver.resolve("8299")

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.raw_symbol == "8299"
    assert result.selected.market == "TW"
    assert result.selected.name == "群聯"
    assert all(candidate.record.market in {"TW", "US"} for candidate in result.candidates)
    assert all(candidate.record.raw_symbol != "TEST" for candidate in result.candidates)


def test_resolver_exact_aliases_and_index_aliases_are_deterministic() -> None:
    resolver = _resolver_with_provider_records([])

    cases = {
        "群聯": ("TW", "8299", "exact_alias"),
        "Phison": ("TW", "8299", "exact_alias"),
        "META": ("US", "META", "exact_symbol"),
        "Meta Platforms": ("US", "META", "exact_alias"),
        "Facebook": ("US", "META", "exact_alias"),
        "SPY": ("US", "SPY", "exact_symbol"),
        "S&P500": ("US", "SPX", "index_alias"),
        "^GSPC": ("US", "SPX", "index_alias"),
    }

    for query, (market, symbol, reason) in cases.items():
        result = resolver.resolve(query)
        assert result.status == "resolved", query
        assert result.selected is not None
        assert result.selected.market == market
        assert result.selected.raw_symbol == symbol
        assert result.candidates[0].match_reason == reason


def test_spy_does_not_resolve_to_syre_even_when_syre_exists() -> None:
    resolver = _resolver_with_provider_records(
        [
            _record("US:SYRE", "SYRE", "US", "Spyre Therapeutics", aliases=["Spyre"]),
        ]
    )

    result = resolver.resolve("SPY")

    assert result.status == "resolved"
    assert result.selected is not None
    assert result.selected.raw_symbol == "SPY"
    assert result.selected.raw_symbol != "SYRE"


def test_weak_unrelated_fuzzy_match_is_not_auto_selected() -> None:
    resolver = _resolver_with_provider_records(
        [
            _record("US:SYRE", "SYRE", "US", "Spyre Therapeutics", aliases=["Spyre"]),
            _record("US:META", "META", "US", "Meta Platforms", aliases=["Facebook"]),
        ]
    )

    result = resolver.resolve("metabolic")

    assert result.status in {"ambiguous", "not_found"}
    assert result.selected is None

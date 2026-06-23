# -*- coding: utf-8 -*-
"""Tests for the local TW/US symbol universe snapshot and builder."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json

from scripts.generate_stock_index import generate_stock_index_from_symbol_universe
from src.services.symbol_universe import (
    CuratedSeedSymbolProvider,
    DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
    NasdaqScreenerSymbolProvider,
    NasdaqTraderSymbolDirectoryProvider,
    StaticSymbolUniverseProvider,
    SymbolRecord,
    SymbolUniverseBuilder,
    SymbolUniverseCache,
    TpexCompanyProfileProvider,
    TwseCompanyProfileProvider,
)


PUBLIC_STOCK_INDEX_PATH = (
    DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH.parents[2]
    / "apps"
    / "dsa-web"
    / "public"
    / "stocks.index.json"
)

EXPANDED_TW_TARGETS = {
    "2308": ("台達電", "Delta Electronics"),
    "2382": ("廣達", "Quanta"),
    "6669": ("緯穎", "Wiwynn"),
    "3017": ("奇鋐", "AVC", "Asia Vital Components"),
    "2368": ("金像電", "Kinsus"),
    "2345": ("智邦", "Accton"),
    "3037": ("欣興", "Unimicron"),
    "3661": ("世芯-KY", "世芯", "Alchip"),
    "2303": ("聯電", "UMC"),
    "2882": ("國泰金", "Cathay Financial"),
}

EXPANDED_US_TARGETS = {
    "MSFT": ("Microsoft",),
    "GOOGL": ("Alphabet", "Google"),
    "AMZN": ("Amazon",),
    "TSLA": ("Tesla",),
    "AVGO": ("Broadcom",),
    "AMD": ("Advanced Micro Devices",),
    "MU": ("Micron", "Micron Technology"),
    "ARM": ("Arm", "Arm Holdings"),
    "ORCL": ("Oracle",),
    "PLTR": ("Palantir", "Palantir Technologies"),
}

PHASE_15_9O_TW_OFFICIAL_ALIAS_TARGETS = {
    "3231": ("Wistron",),
    "2356": ("INVENTEC",),
    "2376": ("GIGABYTE",),
    "2409": ("AUO",),
}


def _record(
    canonical_symbol: str,
    raw_symbol: str,
    market: str,
    name: str,
    aliases: list[str] | None = None,
    instrument_type: str = "stock",
    provider_source: str = "fixture_source",
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


def test_committed_snapshot_is_local_database_not_seed_only() -> None:
    payload = json.loads(DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    metadata = payload["metadata"]
    cache = SymbolUniverseCache.from_json_snapshot(DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH)
    counts = Counter(record.market for record in cache.records)

    assert metadata["schema_version"] == 1
    assert metadata["source"] == "symbol_universe_builder"
    assert metadata["record_count"] == len(cache.records)
    assert metadata["market_count"]["TW"] == counts["TW"]
    assert metadata["market_count"]["US"] == counts["US"]
    assert counts["TW"] >= 1000
    assert counts["US"] >= 1000
    assert len(cache.records) > len(list(CuratedSeedSymbolProvider().records())) * 50

    for raw_symbol in (
        *EXPANDED_TW_TARGETS,
        *EXPANDED_US_TARGETS,
        "8299",
        "00981A",
        "006208",
        "QQQ",
        "VOO",
    ):
        assert cache.get_by_raw_symbol(raw_symbol) is not None, raw_symbol

    assert {record.market for record in cache.records} == {"TW", "US"}

    for raw_symbol, aliases in {**EXPANDED_TW_TARGETS, **EXPANDED_US_TARGETS}.items():
        record = cache.get_by_raw_symbol(raw_symbol)
        assert record is not None, raw_symbol
        searchable = {record.name, *(record.aliases or [])}
        for alias in aliases:
            assert alias in searchable, (raw_symbol, alias)

    tw_alias_records = [
        record
        for record in cache.records
        if record.market == "TW" and record.aliases
    ]
    assert len(tw_alias_records) >= 1000
    for raw_symbol, aliases in PHASE_15_9O_TW_OFFICIAL_ALIAS_TARGETS.items():
        record = cache.get_by_raw_symbol(raw_symbol)
        assert record is not None, raw_symbol
        searchable = {record.name, *(record.aliases or [])}
        for alias in aliases:
            assert alias in searchable, (raw_symbol, alias)


def test_symbol_universe_builder_rebuilds_snapshot_from_sources(tmp_path) -> None:
    snapshot_path = tmp_path / "symbol_universe.json"
    builder = SymbolUniverseBuilder(
        providers=[
            StaticSymbolUniverseProvider(
                "fixture_source",
                [
                    _record("TW:2303", "2303", "TW", "聯電", aliases=["UMC"]),
                    _record("US:MSFT", "MSFT", "US", "Microsoft", aliases=["Microsoft Corporation"]),
                    _record("ZZ:TEST", "TEST", "ZZ", "非支援市場測試標的"),
                ],
            )
        ],
        override_providers=[CuratedSeedSymbolProvider()],
    )

    result = builder.build_snapshot(snapshot_path)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    restored = SymbolUniverseCache.from_json_snapshot(snapshot_path)

    assert result.record_count == payload["metadata"]["record_count"]
    assert payload["metadata"]["source"] == "symbol_universe_builder"
    assert restored.get_by_raw_symbol("2303") is not None
    assert restored.get_by_raw_symbol("MSFT") is not None
    assert restored.get_by_raw_symbol("TEST") is None
    assert all(record.market in {"TW", "US"} for record in restored.records)


def test_us_directory_provider_excludes_single_name_derivative_etfs(tmp_path) -> None:
    nasdaq_path = tmp_path / "nasdaqlisted.txt"
    other_path = tmp_path / "otherlisted.txt"
    nasdaq_path.write_text(
        "\n".join(
            [
                "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
                "GOOD|Example Technology Inc. Common Stock|Q|N|N|100|N|N",
                "BADL|Example 2X Long Sample Daily ETF|Q|N|N|100|Y|N",
                "BADO|Example Option Income Strategy ETF|Q|N|N|100|Y|N",
                "File Creation Time: fixture",
            ]
        ),
        encoding="utf-8",
    )
    other_path.write_text(
        "\n".join(
            [
                "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
                "KEPT|Kept Broad Market ETF|P|KEPT|Y|100|N|KEPT",
                "DROP|Drop 2X Inverse Sample Daily ETF|P|DROP|Y|100|N|DROP",
                "File Creation Time: fixture",
            ]
        ),
        encoding="utf-8",
    )

    provider = NasdaqTraderSymbolDirectoryProvider(
        nasdaq_listed_url=nasdaq_path.as_uri(),
        other_listed_url=other_path.as_uri(),
    )
    records = {record.raw_symbol: record for record in provider.records()}

    assert "GOOD" in records
    assert "KEPT" in records
    assert "BADL" not in records
    assert "BADO" not in records
    assert "DROP" not in records


def test_us_screener_provider_uses_country_filtered_rows() -> None:
    provider = NasdaqScreenerSymbolProvider(
        payload={
            "data": {
                "rows": [
                    {
                        "symbol": "GOOD",
                        "name": "Example Technology Inc. Common Stock",
                        "country": "United States",
                    },
                    {
                        "symbol": "DROP",
                        "name": "Dropped Foreign Issuer Common Stock",
                        "country": "Other Market",
                    },
                    {
                        "symbol": "YUMC",
                        "name": "Excluded Outlier Common Stock",
                        "country": "United States",
                    },
                ]
            }
        }
    )

    records = {record.raw_symbol: record for record in provider.records()}

    assert records["GOOD"].market == "US"
    assert records["GOOD"].provider_source == "nasdaq_screener_stock_directory"
    assert "DROP" not in records
    assert "YUMC" not in records


def test_twse_company_profile_provider_adds_official_english_aliases() -> None:
    provider = TwseCompanyProfileProvider(
        payload=[
            {
                "公司代號": "3231",
                "公司簡稱": "緯創",
                "英文簡稱": "Wistron",
            },
            {
                "公司代號": "2356",
                "公司簡稱": "英業達",
                "英文簡稱": "INVENTEC",
            },
            {
                "公司代號": "00739",
                "公司簡稱": "排除測試",
                "英文簡稱": "DROP",
            },
        ]
    )

    records = {record.raw_symbol: record for record in provider.records()}

    assert records["3231"].aliases == ["Wistron"]
    assert records["2356"].aliases == ["INVENTEC"]
    assert "00739" not in records


def test_tpex_company_profile_provider_adds_official_english_aliases() -> None:
    provider = TpexCompanyProfileProvider(
        payload=[
            {
                "SecuritiesCompanyCode": "8299",
                "CompanyAbbreviation": "群聯",
                "Symbol": "Phison　",
            },
            {
                "SecuritiesCompanyCode": "1240",
                "CompanyAbbreviation": "茂生農經",
                "Symbol": "MORNSUN　",
            },
        ]
    )

    records = {record.raw_symbol: record for record in provider.records()}

    assert records["8299"].aliases == ["Phison"]
    assert records["1240"].aliases == ["MORNSUN"]


def test_generated_frontend_stock_index_uses_same_tw_us_universe() -> None:
    cache = SymbolUniverseCache.from_json_snapshot(DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH)
    index = generate_stock_index_from_symbol_universe(cache)

    assert index
    assert all(item["market"] in {"TW", "US"} for item in index)
    assert any(item["displayCode"] == "2303" and item["nameZh"] == "聯電" for item in index)
    assert any(item["displayCode"] == "8299" and item["nameZh"] == "群聯" for item in index)
    assert any(item["displayCode"] == "00981A" for item in index)
    assert any(item["displayCode"] == "006208" for item in index)
    assert any(item["displayCode"] == "MSFT" and item["nameZh"] == "Microsoft" for item in index)
    assert any(item["displayCode"] == "QQQ" for item in index)
    assert any(item["displayCode"] == "VOO" for item in index)
    for raw_symbol in (*EXPANDED_TW_TARGETS, *EXPANDED_US_TARGETS):
        assert any(item["displayCode"] == raw_symbol for item in index), raw_symbol
    for raw_symbol, aliases in PHASE_15_9O_TW_OFFICIAL_ALIAS_TARGETS.items():
        matching = [item for item in index if item["displayCode"] == raw_symbol]
        assert matching, raw_symbol
        assert set(aliases).issubset(set(matching[0]["aliases"])), raw_symbol

    display_codes = {str(item["displayCode"]) for item in index}
    canonical_codes = {str(item["canonicalCode"]) for item in index}
    assert "ZZ:TEST" not in canonical_codes
    assert {item["market"] for item in index} == {"TW", "US"}


def test_bundled_public_stock_index_contains_only_tw_us_snapshot_rows() -> None:
    rows = json.loads(PUBLIC_STOCK_INDEX_PATH.read_text(encoding="utf-8"))
    assert len(rows) > 1000
    assert {row[6] for row in rows} == {"TW", "US"}
    assert any(row[1] == "2303" and row[2] == "聯電" for row in rows)
    assert any(row[1] == "2882" and row[2] == "國泰金" for row in rows)
    assert any(row[1] == "00981A" for row in rows)
    assert any(row[1] == "006208" for row in rows)
    assert any(row[1] == "MSFT" and row[2] == "Microsoft" for row in rows)
    assert any(row[1] == "QQQ" and row[7] == "etf" for row in rows)
    assert any(row[1] == "VOO" and row[7] == "etf" for row in rows)
    for raw_symbol in (*EXPANDED_TW_TARGETS, *EXPANDED_US_TARGETS):
        assert any(row[1] == raw_symbol for row in rows), raw_symbol
    for raw_symbol, aliases in PHASE_15_9O_TW_OFFICIAL_ALIAS_TARGETS.items():
        matching = [row for row in rows if row[1] == raw_symbol]
        assert matching, raw_symbol
        assert set(aliases).issubset(set(matching[0][5])), raw_symbol

    display_codes = {str(row[1]) for row in rows}
    canonical_codes = {str(row[0]) for row in rows}
    assert "ZZ:TEST" not in canonical_codes
    assert {row[6] for row in rows} == {"TW", "US"}


def test_phase15_9i_bundled_public_stock_index_contains_live_blocker_aliases() -> None:
    rows = json.loads(PUBLIC_STOCK_INDEX_PATH.read_text(encoding="utf-8"))
    by_symbol = {str(row[1]): row for row in rows}

    expected_aliases = {
        "2379": {"Realtek"},
        "2357": {"ASUS", "Asus"},
        "2327": {"Yageo"},
        "2395": {"Advantech"},
        "3711": {"ASE", "ASE Technology"},
        "CSCO": {"Cisco", "Cisco Systems"},
        "COST": {"Costco", "Costco Wholesale"},
    }

    for symbol, aliases in expected_aliases.items():
        assert symbol in by_symbol
        assert aliases.issubset(set(by_symbol[symbol][5])), symbol

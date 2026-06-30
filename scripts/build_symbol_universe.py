#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the local TW/US symbol universe snapshot.

Provider calls happen here, not during runtime autocomplete/resolve. Runtime
lookup remains local-first through the generated JSON snapshot.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.symbol_universe import (  # noqa: E402
    CuratedSeedSymbolProvider,
    DEFAULT_RUNTIME_SYMBOL_UNIVERSE_CACHE_PATH,
    DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
    FinMindTaiwanStockInfoHttpProvider,
    NasdaqTraderSymbolDirectoryProvider,
    NasdaqScreenerSymbolProvider,
    SymbolUniverseBuilder,
    SymbolUniverseCache,
    SymbolUniverseProvider,
    TaiwanIsinSymbolDirectoryProvider,
    TpexCompanyProfileProvider,
    TwseCompanyProfileProvider,
)


def _parse_markets(value: str) -> set[str]:
    markets = {market.strip().upper() for market in value.split(",") if market.strip()}
    unsupported = markets - {"TW", "US"}
    if unsupported:
        raise argparse.ArgumentTypeError(
            f"unsupported market(s): {', '.join(sorted(unsupported))}; use TW, US, or TW,US"
        )
    return markets or {"TW", "US"}


def providers_for_markets(markets: set[str]) -> list[SymbolUniverseProvider]:
    providers: list[SymbolUniverseProvider] = []
    if "TW" in markets:
        providers.append(TaiwanIsinSymbolDirectoryProvider())
        providers.append(TwseCompanyProfileProvider())
        providers.append(TpexCompanyProfileProvider())
        providers.append(FinMindTaiwanStockInfoHttpProvider())
    if "US" in markets:
        providers.append(NasdaqTraderSymbolDirectoryProvider())
        providers.append(NasdaqScreenerSymbolProvider())
    return providers


def backfill_us_exchange_metadata(
    cache: SymbolUniverseCache,
    *,
    providers: list[SymbolUniverseProvider] | None = None,
) -> SymbolUniverseCache:
    """Backfill exchange metadata for existing local US records only."""
    exchange_by_symbol: dict[str, str] = {}
    for provider in providers or [NasdaqTraderSymbolDirectoryProvider()]:
        for record in provider.records():
            if record.market != "US" or not record.exchange:
                continue
            exchange_by_symbol.setdefault(record.raw_symbol.upper(), record.exchange)

    records = []
    for record in cache.records:
        if record.market == "US" and not record.exchange:
            exchange = exchange_by_symbol.get(record.raw_symbol.upper())
            if exchange:
                records.append(replace(record, exchange=exchange))
                continue
        records.append(record)
    return SymbolUniverseCache(records)


def build_symbol_universe_snapshot(
    *,
    markets: set[str],
    output: Path,
    backfill_us_exchanges: bool = False,
) -> None:
    builder = SymbolUniverseBuilder(
        providers=providers_for_markets(markets),
        override_providers=[CuratedSeedSymbolProvider()],
    )
    if backfill_us_exchanges:
        cache = SymbolUniverseCache.from_json_snapshot(output)
        backfilled = backfill_us_exchange_metadata(cache)
        SymbolUniverseBuilder.save_cache_snapshot(
            backfilled,
            output,
            provider_sources=["existing_snapshot", "nasdaq_trader_symbol_directory"],
        )
        market_counts = {
            market: sum(1 for record in backfilled.records if record.market == market)
            for market in {"TW", "US"}
        }
        counts = ", ".join(f"{market}={count}" for market, count in sorted(market_counts.items()))
        filled = sum(1 for record in backfilled.records if record.market == "US" and record.exchange)
        total = sum(1 for record in backfilled.records if record.market == "US")
        print(f"wrote {output} ({len(backfilled.records)} records; {counts}; US exchange {filled}/{total})")
        return

    result = builder.build_snapshot(output)
    counts = ", ".join(f"{market}={count}" for market, count in sorted(result.market_count.items()))
    print(f"wrote {result.path} ({result.record_count} records; {counts})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build local TW/US symbol universe snapshot")
    parser.add_argument(
        "--market",
        default="TW,US",
        type=_parse_markets,
        help="Markets to refresh: TW, US, or TW,US",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
        help="Snapshot output path",
    )
    parser.add_argument(
        "--runtime-cache",
        action="store_true",
        help=f"Write ignored runtime cache at {DEFAULT_RUNTIME_SYMBOL_UNIVERSE_CACHE_PATH}",
    )
    parser.add_argument(
        "--backfill-us-exchanges",
        action="store_true",
        help="Backfill exchange metadata for existing US records in the selected snapshot",
    )
    args = parser.parse_args(argv)

    output = DEFAULT_RUNTIME_SYMBOL_UNIVERSE_CACHE_PATH if args.runtime_cache else args.output
    build_symbol_universe_snapshot(
        markets=args.market,
        output=output,
        backfill_us_exchanges=args.backfill_us_exchanges,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

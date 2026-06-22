#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the local TW/US symbol universe snapshot.

Provider calls happen here, not during runtime autocomplete/resolve. Runtime
lookup remains local-first through the generated JSON snapshot.
"""

from __future__ import annotations

import argparse
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
    NasdaqScreenerSymbolProvider,
    SymbolUniverseBuilder,
    SymbolUniverseProvider,
    TaiwanIsinSymbolDirectoryProvider,
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
        providers.append(FinMindTaiwanStockInfoHttpProvider())
    if "US" in markets:
        providers.append(NasdaqScreenerSymbolProvider())
    return providers


def build_symbol_universe_snapshot(
    *,
    markets: set[str],
    output: Path,
) -> None:
    builder = SymbolUniverseBuilder(
        providers=providers_for_markets(markets),
        override_providers=[CuratedSeedSymbolProvider()],
    )
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
    args = parser.parse_args(argv)

    output = DEFAULT_RUNTIME_SYMBOL_UNIVERSE_CACHE_PATH if args.runtime_cache else args.output
    build_symbol_universe_snapshot(markets=args.market, output=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

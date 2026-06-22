#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the frontend autocomplete index from the TW/US symbol universe."""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from pypinyin import lazy_pinyin

    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False

from src.services.symbol_universe import (  # noqa: E402
    DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
    SymbolRecord,
    SymbolUniverseCache,
)


def normalize_name_for_pinyin(name: str) -> str:
    """Normalize display name before generating pinyin fields."""
    return unicodedata.normalize("NFKC", name).strip()


def _pinyin_fields(name: str) -> tuple[str | None, str | None]:
    if not PYPINYIN_AVAILABLE:
        return None, None
    try:
        py = lazy_pinyin(normalize_name_for_pinyin(name))
    except Exception:
        return None, None
    return "".join(py), "".join(part[0] for part in py if part)


def _popularity(record: SymbolRecord) -> int:
    if record.instrument_type == "index":
        return 99
    if record.instrument_type in {"etf", "etn", "beneficiary_security"}:
        return 97
    if record.market == "TW":
        return 95
    return 90


def _frontend_asset_type(record: SymbolRecord) -> str:
    if record.instrument_type == "index":
        return "index"
    if record.instrument_type in {"etf", "etn", "beneficiary_security"}:
        return "etf"
    return "stock"


def _index_item(record: SymbolRecord) -> dict[str, Any]:
    pinyin_full, pinyin_abbr = _pinyin_fields(record.name)
    return {
        "canonicalCode": record.raw_symbol,
        "displayCode": record.raw_symbol,
        "nameZh": record.name,
        "pinyinFull": pinyin_full,
        "pinyinAbbr": pinyin_abbr,
        "aliases": list(record.aliases or []),
        "market": record.market,
        "assetType": _frontend_asset_type(record),
        "active": record.is_active,
        "popularity": _popularity(record),
    }


def generate_stock_index_from_symbol_universe(
    cache: SymbolUniverseCache | None = None,
) -> list[dict[str, Any]]:
    """Generate frontend stock index items from the local TW/US universe."""
    symbol_cache = cache or SymbolUniverseCache.from_json_snapshot(DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH)
    items = [_index_item(record) for record in symbol_cache.records if record.market in {"TW", "US"}]
    items.sort(key=lambda item: (item["market"], item["displayCode"]))
    return items


def compress_index(index: list[dict[str, Any]]) -> list[list[Any]]:
    """Compress index to tuple format used by the web app."""
    return [
        [
            item["canonicalCode"],
            item["displayCode"],
            item["nameZh"],
            item.get("pinyinFull"),
            item.get("pinyinAbbr"),
            item.get("aliases", []),
            item["market"],
            item["assetType"],
            item["active"],
            item.get("popularity", 0),
        ]
        for item in index
    ]


def _write_compressed_json(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("[\n")
        for index, row in enumerate(rows):
            json.dump(row, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write(",\n" if index < len(rows) - 1 else "\n")
        fh.write("]\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate TW/US frontend stock index")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
        help="Local symbol universe snapshot",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "apps" / "dsa-web" / "public" / "stocks.index.json",
        help="Frontend compressed index output",
    )
    parser.add_argument(
        "--test",
        "-t",
        action="store_true",
        help="Validate and print counts without writing",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show preview rows")
    args = parser.parse_args(argv)

    cache = SymbolUniverseCache.from_json_snapshot(args.snapshot)
    index = generate_stock_index_from_symbol_universe(cache)
    compressed = compress_index(index)
    market_stats: dict[str, int] = {}
    for item in index:
        market_stats[item["market"]] = market_stats.get(item["market"], 0) + 1

    print(f"generated {len(index)} TW/US stock-index rows from {args.snapshot}")
    print(f"market distribution: {market_stats}")

    if args.verbose:
        for item in index[:10]:
            print(f"  {item['displayCode']} {item['nameZh']} ({item['market']})")

    if args.test:
        print(
            "estimated compressed size: "
            f"{len(json.dumps(compressed, ensure_ascii=False, separators=(',', ':'))) / 1024:.2f} KB"
        )
        return 0

    _write_compressed_json(args.output, compressed)
    print(f"wrote {args.output} ({args.output.stat().st_size / 1024:.2f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

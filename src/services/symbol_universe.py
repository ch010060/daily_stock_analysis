# -*- coding: utf-8 -*-
"""Provider-backed TW/US symbol universe and deterministic resolver.

The resolver is intentionally independent from LLM and analysis execution. It
turns user input into ranked TW/US candidates, and only exact/high-confidence
matches are auto-selected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import csv
from html.parser import HTMLParser
import io
import json
import re
import unicodedata
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Protocol

from src.data.stock_mapping import STOCK_NAME_MAP


SUPPORTED_MARKETS = {"TW", "US"}
EXCLUDED_TW_SYMBOLS = {
    "00739",
}
EXCLUDED_US_SYMBOLS = {
    "AEF",
    "CAF",
    "YUMC",
}
EXCLUDED_US_NAME_TERMS = (
    "united microelectronics",
)
AUTO_SELECT_REASONS = {"exact_symbol", "exact_alias", "index_alias"}
AUTO_SELECT_CONFIDENCE = 0.97
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYMBOL_UNIVERSE_SEED_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "symbol_universe_seed.json"
)
DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "symbol_universe_tw_us_snapshot.json"
)
DEFAULT_RUNTIME_SYMBOL_UNIVERSE_CACHE_PATH = (
    REPO_ROOT / "data" / "symbol_universe_tw_us_snapshot.json"
)
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NASDAQ_SCREENER_STOCKS_URL = (
    "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&download=true"
)
TWSE_ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
TPEX_ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
TW_SYMBOL_RE = re.compile(r"(?:\d{4,6}|\d{4,5}[A-Z])")


@dataclass(frozen=True)
class SymbolRecord:
    canonical_symbol: str
    raw_symbol: str
    market: str
    exchange: str | None
    instrument_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    provider_source: str = "unknown"
    is_active: bool = True
    last_updated: str | None = None


@dataclass(frozen=True)
class SymbolCandidate:
    record: SymbolRecord
    confidence: float
    match_reason: str
    matched_value: str


@dataclass(frozen=True)
class SymbolResolveResult:
    query: str
    status: str
    selected: SymbolRecord | None
    candidates: list[SymbolCandidate]
    message: str | None = None


@dataclass(frozen=True)
class SymbolUniverseBuildResult:
    path: Path
    record_count: int
    market_count: dict[str, int]
    provider_sources: list[str]


class SymbolUniverseProvider(Protocol):
    """Source adapter for symbol universe records."""

    source_name: str

    def records(self) -> Iterable[SymbolRecord]:
        """Return symbol records from this source."""
        ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_query(value: str) -> str:
    """Normalize user input while preserving Traditional Chinese content."""
    text = unicodedata.normalize("NFKC", value or "").strip()
    return re.sub(r"\s+", " ", text)


def _norm_key(value: str) -> str:
    text = _normalize_query(value).casefold()
    return re.sub(r"[\s._-]+", "", text)


def _normalize_explicit_symbol_query(value: str) -> str:
    """Collapse TW:/US: and .TW/.US inputs before local universe lookup."""
    text = _normalize_query(value)
    upper = text.upper()
    for prefix in ("TW:", "US:"):
        if upper.startswith(prefix):
            return upper[len(prefix) :]
    if "." in text:
        base, suffix = text.rsplit(".", 1)
        if suffix.upper() in {"TW", "US"} and base.strip():
            return base.strip().upper()
    return text


def _canonical(market: str, raw_symbol: str) -> str:
    return f"{market.upper()}:{raw_symbol.upper()}"


def _record(
    raw_symbol: str,
    market: str,
    name: str,
    aliases: list[str],
    instrument_type: str = "stock",
    exchange: str | None = None,
    provider_source: str = "curated_seed",
    canonical_symbol: str | None = None,
) -> SymbolRecord:
    raw = raw_symbol.upper() if raw_symbol.isascii() else raw_symbol
    market_upper = market.upper()
    return SymbolRecord(
        canonical_symbol=canonical_symbol or _canonical(market_upper, raw),
        raw_symbol=raw,
        market=market_upper,
        exchange=exchange,
        instrument_type=instrument_type,
        name=name,
        aliases=aliases,
        provider_source=provider_source,
        is_active=True,
        last_updated=_utc_now(),
    )


class CuratedSeedSymbolProvider:
    """Bootstrap/override records for Route B TW/US daily-use targets."""

    source_name = "curated_seed"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_SYMBOL_UNIVERSE_SEED_PATH

    def records(self) -> Iterable[SymbolRecord]:
        return JsonSymbolUniverseProvider(self.source_name, self.path).records()


class JsonSymbolUniverseProvider:
    """Versioned JSON snapshot provider for offline symbol universe lookup."""

    def __init__(self, source_name: str, path: Path) -> None:
        self.source_name = source_name
        self.path = path

    def records(self) -> Iterable[SymbolRecord]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = data.get("records", data) if isinstance(data, dict) else data
        records: list[SymbolRecord] = []
        for row in rows:
            records.append(_symbol_record_from_mapping(row, default_source=self.source_name))
        return records


class StaticSymbolUniverseProvider:
    """Static provider useful for tests and local snapshots."""

    def __init__(self, source_name: str, records: Iterable[SymbolRecord]) -> None:
        self.source_name = source_name
        self._records = list(records)

    def records(self) -> Iterable[SymbolRecord]:
        return list(self._records)


class StockMappingSymbolProvider:
    """Adapter that exposes supported TW/US entries from STOCK_NAME_MAP."""

    source_name = "stock_mapping"

    def records(self) -> Iterable[SymbolRecord]:
        records: list[SymbolRecord] = []
        for code, name in STOCK_NAME_MAP.items():
            if TW_SYMBOL_RE.fullmatch(code):
                records.append(
                    _record(
                        code,
                        "TW",
                        name,
                        [],
                        exchange=None,
                        provider_source=self.source_name,
                    )
                )
            elif re.fullmatch(r"[A-Z]{1,5}", code):
                records.append(
                    _record(
                        code,
                        "US",
                        name,
                        [],
                        exchange=None,
                        provider_source=self.source_name,
                    )
                )
        return records


class _IsinTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_tr = False
        self._in_cell = False
        self._row: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._in_tr = True
            self._row = []
        elif tag.lower() == "td" and self._in_tr:
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "td" and self._in_cell:
            self._row.append("".join(self._cell_parts).strip())
            self._in_cell = False
        elif tag.lower() == "tr" and self._in_tr:
            if self._row:
                self.rows.append(self._row)
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


class TaiwanIsinSymbolDirectoryProvider:
    """TWSE/TPEx ISIN directory source for local TW symbol universe refresh."""

    source_name = "taiwan_isin_directory"

    def __init__(
        self,
        *,
        twse_url: str | None = None,
        tpex_url: str | None = None,
        twse_html: str | None = None,
        tpex_html: str | None = None,
    ) -> None:
        self.twse_url = twse_url or TWSE_ISIN_URL
        self.tpex_url = tpex_url or TPEX_ISIN_URL
        self.twse_html = twse_html
        self.tpex_html = tpex_html

    def records(self) -> Iterable[SymbolRecord]:
        return [
            *self._parse_page(self.twse_html or self._fetch(self.twse_url), exchange="TWSE"),
            *self._parse_page(self.tpex_html or self._fetch(self.tpex_url), exchange="TPEx"),
        ]

    def _fetch(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read()
        for encoding in ("big5", "cp950", "utf-8"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("big5", errors="ignore")

    def _parse_page(self, html_text: str, *, exchange: str) -> list[SymbolRecord]:
        parser = _IsinTableParser()
        parser.feed(html_text)
        records: list[SymbolRecord] = []
        section = ""
        for row in parser.rows:
            if len(row) == 1:
                section = row[0]
                continue
            if not _is_supported_tw_isin_section(section):
                continue
            if not row or row[0] == "有價證券代號及名稱":
                continue
            raw_symbol, name = _parse_tw_isin_name_cell(row[0])
            if not raw_symbol or not name:
                continue
            if raw_symbol in EXCLUDED_TW_SYMBOLS:
                continue
            instrument_type = _tw_instrument_type_from_isin_section(section, raw_symbol)
            records.append(
                _record(
                    raw_symbol,
                    "TW",
                    name,
                    [],
                    instrument_type=instrument_type,
                    exchange=exchange,
                    provider_source=self.source_name,
                )
            )
        return records


class FinMindTaiwanStockInfoProvider:
    """Provider adapter boundary for FinMind TaiwanStockInfo master data.

    The default resolver does not fetch live data on request; callers can run
    this provider in a refresh job and persist the resulting records into a
    snapshot/cache.
    """

    source_name = "finmind_taiwan_stock_info"

    def __init__(self, fetcher: object) -> None:
        self.fetcher = fetcher

    def records(self) -> Iterable[SymbolRecord]:
        fetch = getattr(self.fetcher, "fetch")
        dataset = fetch(dataset="TaiwanStockInfo")
        rows = dataset.rows if hasattr(dataset, "rows") else dataset
        records: list[SymbolRecord] = []
        for row in rows or []:
            raw_symbol = str(row.get("stock_id") or "").strip()
            name = str(row.get("stock_name") or "").strip()
            if not raw_symbol or not name:
                continue
            if raw_symbol in EXCLUDED_TW_SYMBOLS:
                continue
            if not TW_SYMBOL_RE.fullmatch(raw_symbol):
                continue
            records.append(
                _record(
                    raw_symbol,
                    "TW",
                    name,
                    [],
                    exchange=None,
                    provider_source=self.source_name,
                )
            )
        return records


class FinMindTaiwanStockInfoHttpProvider:
    """Live FinMind TaiwanStockInfo source for explicit universe refresh jobs."""

    source_name = "finmind_taiwan_stock_info"

    def __init__(self, url: str | None = None) -> None:
        self.url = url or "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"

    def records(self) -> Iterable[SymbolRecord]:
        with urllib.request.urlopen(self.url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("data") or []
        records: list[SymbolRecord] = []
        for row in rows:
            raw_symbol = str(row.get("stock_id") or "").strip()
            name = str(row.get("stock_name") or "").strip()
            if not raw_symbol or not name:
                continue
            if raw_symbol in EXCLUDED_TW_SYMBOLS:
                continue
            if not TW_SYMBOL_RE.fullmatch(raw_symbol):
                continue
            exchange = _tw_exchange_from_finmind_type(str(row.get("type") or ""))
            records.append(
                _record(
                    raw_symbol,
                    "TW",
                    name,
                    [],
                    exchange=exchange,
                    provider_source=self.source_name,
                )
            )
        return records


class NasdaqTraderSymbolDirectoryProvider:
    """Nasdaq Trader symbol-directory source for explicit US universe refresh."""

    source_name = "nasdaq_trader_symbol_directory"

    def __init__(
        self,
        *,
        nasdaq_listed_url: str | None = None,
        other_listed_url: str | None = None,
        nasdaq_text: str | None = None,
        other_text: str | None = None,
    ) -> None:
        self.nasdaq_listed_url = nasdaq_listed_url or NASDAQ_LISTED_URL
        self.other_listed_url = other_listed_url or OTHER_LISTED_URL
        self.nasdaq_text = nasdaq_text
        self.other_text = other_text

    def records(self) -> Iterable[SymbolRecord]:
        return [
            *self._parse_nasdaq_listed(self.nasdaq_text or self._fetch(self.nasdaq_listed_url)),
            *self._parse_other_listed(self.other_text or self._fetch(self.other_listed_url)),
        ]

    def _fetch(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    def _parse_nasdaq_listed(self, text: str) -> list[SymbolRecord]:
        rows = _read_pipe_table(text)
        records: list[SymbolRecord] = []
        for row in rows:
            symbol = str(row.get("Symbol") or "").strip().upper()
            security_name = str(row.get("Security Name") or "").strip()
            if not _is_supported_us_symbol(symbol, security_name, row.get("Test Issue")):
                continue
            instrument_type = "etf" if str(row.get("ETF") or "").upper() == "Y" else "stock"
            name, aliases = _clean_us_security_name(symbol, security_name)
            records.append(
                _record(
                    symbol,
                    "US",
                    name,
                    aliases,
                    instrument_type=instrument_type,
                    exchange="NASDAQ",
                    provider_source=self.source_name,
                )
            )
        return records

    def _parse_other_listed(self, text: str) -> list[SymbolRecord]:
        rows = _read_pipe_table(text)
        records: list[SymbolRecord] = []
        for row in rows:
            symbol = str(row.get("ACT Symbol") or "").strip().upper()
            security_name = str(row.get("Security Name") or "").strip()
            if not _is_supported_us_symbol(symbol, security_name, row.get("Test Issue")):
                continue
            instrument_type = "etf" if str(row.get("ETF") or "").upper() == "Y" else "stock"
            name, aliases = _clean_us_security_name(symbol, security_name)
            records.append(
                _record(
                    symbol,
                    "US",
                    name,
                    aliases,
                    instrument_type=instrument_type,
                    exchange=_us_exchange_from_nasdaq_code(str(row.get("Exchange") or "")),
                    provider_source=self.source_name,
                )
            )
        return records


class NasdaqScreenerSymbolProvider:
    """Nasdaq screener source for country-filtered US stock universe refresh."""

    source_name = "nasdaq_screener_stock_directory"

    def __init__(
        self,
        *,
        url: str | None = None,
        payload: dict | None = None,
        country: str = "United States",
    ) -> None:
        self.url = url or NASDAQ_SCREENER_STOCKS_URL
        self.payload = payload
        self.country = country

    def records(self) -> Iterable[SymbolRecord]:
        payload = self.payload or self._fetch_payload()
        rows = ((payload.get("data") or {}).get("rows") or [])
        records: list[SymbolRecord] = []
        for row in rows:
            if str(row.get("country") or "").strip() != self.country:
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            security_name = str(row.get("name") or "").strip()
            if not _is_supported_us_symbol(symbol, security_name, "N"):
                continue
            name, aliases = _clean_us_security_name(symbol, security_name)
            records.append(
                _record(
                    symbol,
                    "US",
                    name,
                    aliases,
                    instrument_type="stock",
                    exchange=None,
                    provider_source=self.source_name,
                )
            )
        return records

    def _fetch_payload(self) -> dict:
        request = urllib.request.Request(
            self.url,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))


class SymbolUniverseCache:
    """Merged, queryable TW/US symbol universe cache."""

    def __init__(self, records: Iterable[SymbolRecord]) -> None:
        self.records = list(records)
        self._by_raw: dict[str, SymbolRecord] = {}
        self._exact_candidates: dict[str, list[SymbolCandidate]] = {}
        self._search_terms: list[tuple[SymbolRecord, str, str, str]] = []
        for record in self.records:
            self._by_raw[_norm_key(record.raw_symbol)] = record
            self._add_exact_candidate(
                record.raw_symbol,
                SymbolCandidate(record, 1.0, "exact_symbol", record.raw_symbol),
            )
            self._add_exact_candidate(
                record.canonical_symbol,
                SymbolCandidate(record, 1.0, "exact_symbol", record.raw_symbol),
            )
            self._add_search_term(record, record.raw_symbol, "symbol")
            self._add_search_term(record, record.name, "name")
            self._add_exact_candidate(
                record.name,
                SymbolCandidate(record, 0.98, "exact_alias", record.name),
            )
            for alias in record.aliases or []:
                reason = "index_alias" if record.instrument_type.lower() == "index" else "exact_alias"
                confidence = 1.0 if reason == "index_alias" else 0.98
                self._add_exact_candidate(
                    alias,
                    SymbolCandidate(record, confidence, reason, alias),
                )
                self._add_search_term(record, alias, "alias")

    @classmethod
    def from_providers(cls, providers: Iterable[SymbolUniverseProvider]) -> "SymbolUniverseCache":
        merged: dict[str, SymbolRecord] = {}
        for provider in providers:
            for record in provider.records():
                normalized_market = (record.market or "").upper()
                if normalized_market not in SUPPORTED_MARKETS:
                    continue
                if not record.is_active:
                    continue
                normalized_record = SymbolRecord(
                    canonical_symbol=record.canonical_symbol,
                    raw_symbol=record.raw_symbol.upper() if record.raw_symbol.isascii() else record.raw_symbol,
                    market=normalized_market,
                    exchange=record.exchange,
                    instrument_type=record.instrument_type,
                    name=record.name,
                    aliases=list(record.aliases or []),
                    provider_source=record.provider_source,
                    is_active=record.is_active,
                    last_updated=record.last_updated,
                )
                key = normalized_record.canonical_symbol.upper()
                current = merged.get(key)
                if current is None:
                    merged[key] = normalized_record
                    continue
                merged[key] = _merge_records(current, normalized_record)
        return cls(merged.values())

    @classmethod
    def from_json_snapshot(cls, path: Path) -> "SymbolUniverseCache":
        return cls.from_providers([JsonSymbolUniverseProvider("json_snapshot", path)])

    def save_json_snapshot(self, path: Path) -> None:
        SymbolUniverseBuilder.save_cache_snapshot(self, path, provider_sources=["manual"])

    def get_by_raw_symbol(self, raw_symbol: str) -> SymbolRecord | None:
        return self._by_raw.get(_norm_key(raw_symbol))

    def exact_matches(self, query: str) -> list[SymbolCandidate]:
        return list(self._exact_candidates.get(_norm_key(query), []))

    def search_terms(self) -> list[tuple[SymbolRecord, str, str, str]]:
        return self._search_terms

    def _add_exact_candidate(self, value: str, candidate: SymbolCandidate) -> None:
        key = _norm_key(value)
        if not key:
            return
        self._exact_candidates.setdefault(key, []).append(candidate)

    def _add_search_term(self, record: SymbolRecord, label: str, field_type: str) -> None:
        key = _norm_key(label)
        if not key:
            return
        self._search_terms.append((record, label, key, field_type))


def _symbol_record_from_mapping(row: dict, default_source: str) -> SymbolRecord:
    raw_symbol = str(row.get("raw_symbol") or row.get("symbol") or "").strip()
    market = str(row.get("market") or "").strip().upper()
    canonical_symbol = str(row.get("canonical_symbol") or _canonical(market, raw_symbol)).strip()
    name = str(row.get("name") or "").strip()
    provider_source = str(row.get("provider_source") or default_source).strip()
    return SymbolRecord(
        canonical_symbol=canonical_symbol,
        raw_symbol=raw_symbol.upper() if raw_symbol.isascii() else raw_symbol,
        market=market,
        exchange=row.get("exchange"),
        instrument_type=str(row.get("instrument_type") or "stock"),
        name=name,
        aliases=list(row.get("aliases") or []),
        provider_source=provider_source,
        is_active=bool(row.get("is_active", True)),
        last_updated=row.get("last_updated"),
    )


def _symbol_record_to_mapping(record: SymbolRecord) -> dict:
    return {
        "canonical_symbol": record.canonical_symbol,
        "raw_symbol": record.raw_symbol,
        "market": record.market,
        "exchange": record.exchange,
        "instrument_type": record.instrument_type,
        "name": record.name,
        "aliases": list(record.aliases or []),
        "provider_source": record.provider_source,
        "is_active": record.is_active,
        "last_updated": record.last_updated,
    }


def _market_count(records: Iterable[SymbolRecord]) -> dict[str, int]:
    counts = {market: 0 for market in sorted(SUPPORTED_MARKETS)}
    for record in records:
        market = (record.market or "").upper()
        if market in counts:
            counts[market] += 1
    return counts


def _read_pipe_table(text: str) -> list[dict[str, str]]:
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.startswith("File Creation Time")
    ]
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|")
    return [dict(row) for row in reader]


def _is_supported_tw_isin_section(section: str) -> bool:
    if not section:
        return False
    if "認購" in section or "認售" in section or "權證" in section:
        return False
    return section in {
        "股票",
        "創新板",
        "ETF",
        "ETN",
        "臺灣存託憑證(TDR)",
        "受益證券-不動產投資信託",
        "受益證券-資產基礎證券",
        "特別股",
    }


def _parse_tw_isin_name_cell(value: str) -> tuple[str | None, str | None]:
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = re.sub(r"\s+", " ", text)
    match = re.match(rf"^({TW_SYMBOL_RE.pattern})\s+(.+)$", text)
    if not match:
        return None, None
    return match.group(1).upper(), match.group(2).strip()


def _tw_instrument_type_from_isin_section(section: str, raw_symbol: str) -> str:
    if section == "ETF":
        return "etf"
    if section == "ETN":
        return "etn"
    if "受益證券" in section:
        return "beneficiary_security"
    if "存託憑證" in section:
        return "depositary_receipt"
    if section == "特別股":
        return "preferred_stock"
    if raw_symbol.startswith("00") and len(raw_symbol) >= 4:
        return "etf"
    return "stock"


def _is_supported_us_symbol(symbol: str, security_name: str, test_issue: object) -> bool:
    if not symbol or symbol in EXCLUDED_US_SYMBOLS:
        return False
    if str(test_issue or "").upper() == "Y":
        return False
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,5}", symbol):
        return False
    lowered = security_name.casefold()
    unsupported_terms = (
        "american depositary",
        "depositary shares",
        "preferred stock",
        "warrant",
        "rights",
        " unit",
        "units",
        "note due",
        "notes due",
        "option income strategy",
        "2x long",
        "2x inverse",
        "2x short",
        "daily bull",
        "daily bear",
        "leveraged",
        "leverage shares",
    )
    if any(term in lowered for term in unsupported_terms):
        return False
    if any(term in lowered for term in EXCLUDED_US_NAME_TERMS):
        return False
    return True


def _clean_us_security_name(symbol: str, security_name: str) -> tuple[str, list[str]]:
    cleaned = unicodedata.normalize("NFKC", security_name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+-\s+.*$", "", cleaned)
    cleaned = re.sub(r"\b(Class [A-Z]) Common Stock\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCommon Stock\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCommon Shares\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bOrdinary Shares\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")

    aliases: list[str] = []
    for suffix in (
        "Corporation",
        "Corp.",
        "Corp",
        "Incorporated",
        "Inc.",
        "Inc",
        "Company",
        "Co.",
        "Co",
    ):
        if cleaned.endswith(f" {suffix}"):
            short = cleaned[: -len(suffix)].strip(" ,")
            if short and short != cleaned:
                aliases.append(cleaned)
                cleaned = short
            break

    if symbol == "QQQ":
        cleaned = "Invesco QQQ"
        aliases.extend(["Invesco QQQ Trust", "QQQ ETF"])
    elif symbol == "VOO":
        cleaned = "Vanguard S&P 500 ETF"
        aliases.extend(["Vanguard S&P 500", "VOO ETF"])
    elif symbol == "SPY":
        cleaned = "SPDR S&P 500 ETF"
        aliases.extend(["State Street SPDR S&P 500 ETF Trust", "SPY ETF"])

    return cleaned or security_name or symbol, list(dict.fromkeys(aliases))


def _tw_exchange_from_finmind_type(value: str) -> str | None:
    normalized = value.strip().casefold()
    if normalized == "twse":
        return "TWSE"
    if normalized == "tpex":
        return "TPEx"
    return None


def _us_exchange_from_nasdaq_code(value: str) -> str | None:
    return {
        "A": "NYSE American",
        "N": "NYSE",
        "P": "NYSE Arca",
        "Z": "Cboe",
        "V": "IEX",
    }.get(value.upper(), value.upper() or None)


def _candidate_sort_key(candidate: SymbolCandidate) -> tuple:
    return (
        candidate.confidence,
        candidate.record.provider_source == "curated_seed",
        candidate.record.market == "TW",
        candidate.record.instrument_type == "index",
        candidate.record.raw_symbol,
    )


def _sort_candidates(candidates: Iterable[SymbolCandidate]) -> list[SymbolCandidate]:
    return sorted(candidates, key=_candidate_sort_key, reverse=True)


def _keep_best_candidate(
    candidates: dict[str, SymbolCandidate],
    candidate: SymbolCandidate,
) -> None:
    key = candidate.record.canonical_symbol
    current = candidates.get(key)
    if current is None or _candidate_sort_key(candidate) > _candidate_sort_key(current):
        candidates[key] = candidate


def _dedupe_candidates(candidates: Iterable[SymbolCandidate]) -> list[SymbolCandidate]:
    deduped: dict[str, SymbolCandidate] = {}
    for candidate in candidates:
        _keep_best_candidate(deduped, candidate)
    return _sort_candidates(deduped.values())


class SymbolUniverseBuilder:
    """Build a local TW/US symbol universe snapshot from source providers."""

    def __init__(
        self,
        providers: Iterable[SymbolUniverseProvider],
        override_providers: Iterable[SymbolUniverseProvider] | None = None,
    ) -> None:
        self.providers = list(providers)
        self.override_providers = list(override_providers or [])

    def build_cache(self) -> SymbolUniverseCache:
        return SymbolUniverseCache.from_providers([*self.providers, *self.override_providers])

    def build_payload(self) -> dict:
        cache = self.build_cache()
        return self._payload_for_cache(
            cache,
            provider_sources=[provider.source_name for provider in [*self.providers, *self.override_providers]],
        )

    def build_snapshot(self, path: Path) -> SymbolUniverseBuildResult:
        cache = self.build_cache()
        provider_sources = [
            provider.source_name for provider in [*self.providers, *self.override_providers]
        ]
        self.save_cache_snapshot(cache, path, provider_sources=provider_sources)
        market_count = _market_count(cache.records)
        return SymbolUniverseBuildResult(
            path=path,
            record_count=len(cache.records),
            market_count=market_count,
            provider_sources=provider_sources,
        )

    @staticmethod
    def save_cache_snapshot(
        cache: SymbolUniverseCache,
        path: Path,
        *,
        provider_sources: list[str],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = SymbolUniverseBuilder._payload_for_cache(
            cache,
            provider_sources=provider_sources,
        )
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _payload_for_cache(cache: SymbolUniverseCache, *, provider_sources: list[str]) -> dict:
        return {
            "metadata": {
                "schema_version": 1,
                "source": "symbol_universe_builder",
                "generated_at": _utc_now(),
                "provider_sources": provider_sources,
                "market_count": _market_count(cache.records),
                "record_count": len(cache.records),
            },
            "records": [_symbol_record_to_mapping(record) for record in cache.records],
        }


def _merge_records(existing: SymbolRecord, incoming: SymbolRecord) -> SymbolRecord:
    aliases = list(dict.fromkeys([*(existing.aliases or []), *(incoming.aliases or [])]))
    if existing.provider_source == "curated_seed":
        preferred = existing
        fallback = incoming
    elif incoming.provider_source == "curated_seed":
        preferred = incoming
        fallback = existing
    else:
        preferred = existing
        fallback = incoming
    return SymbolRecord(
        canonical_symbol=preferred.canonical_symbol,
        raw_symbol=preferred.raw_symbol,
        market=preferred.market,
        exchange=preferred.exchange or fallback.exchange,
        instrument_type=preferred.instrument_type or fallback.instrument_type,
        name=preferred.name or fallback.name,
        aliases=aliases,
        provider_source=preferred.provider_source,
        is_active=preferred.is_active,
        last_updated=preferred.last_updated or fallback.last_updated,
    )


class SymbolResolver:
    """Deterministic Route B symbol resolver."""

    def __init__(self, cache: SymbolUniverseCache) -> None:
        self.cache = cache

    def search(self, query: str, limit: int = 8) -> list[SymbolCandidate]:
        normalized = _normalize_explicit_symbol_query(query)
        if not normalized:
            return []
        exact_candidates = _dedupe_candidates(self.cache.exact_matches(normalized))
        if exact_candidates:
            return _sort_candidates(exact_candidates)[:limit]

        if re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z]{1,3})?", normalized) or _norm_key(normalized).isdigit():
            return []

        q = _norm_key(normalized)
        prefix: dict[str, SymbolCandidate] = {}
        contains: dict[str, SymbolCandidate] = {}
        for record, label, key, field_type in self.cache.search_terms():
            if key.startswith(q):
                score = 0.82 if field_type in {"symbol", "name"} else 0.80
                _keep_best_candidate(
                    prefix,
                    SymbolCandidate(record, score, "prefix", label),
                )
                continue
            if q in key:
                score = 0.68 if field_type in {"symbol", "name"} else 0.66
                _keep_best_candidate(
                    contains,
                    SymbolCandidate(record, score, "contains", label),
                )

        candidates = [*prefix.values(), *contains.values()]
        return _sort_candidates(candidates)[:limit]

    def resolve(self, query: str, limit: int = 8) -> SymbolResolveResult:
        candidates = self.search(query, limit=limit)
        if not candidates:
            return SymbolResolveResult(
                query=query,
                status="not_found",
                selected=None,
                candidates=[],
                message="找不到支援的台股 / 美股標的",
            )
        top = candidates[0]
        if top.confidence >= AUTO_SELECT_CONFIDENCE and top.match_reason in AUTO_SELECT_REASONS:
            return SymbolResolveResult(
                query=query,
                status="resolved",
                selected=top.record,
                candidates=candidates,
            )
        return SymbolResolveResult(
            query=query,
            status="ambiguous",
            selected=None,
            candidates=candidates,
            message="請選擇標的",
        )

    def _score_record(self, query: str, record: SymbolRecord) -> SymbolCandidate | None:
        q = _norm_key(query)
        if not q:
            return None
        raw = _norm_key(record.raw_symbol)
        canonical = _norm_key(record.canonical_symbol)
        name = _norm_key(record.name)
        alias_items = [(alias, _norm_key(alias)) for alias in record.aliases or []]

        if q == raw or q == canonical:
            return SymbolCandidate(record, 1.0, "exact_symbol", record.raw_symbol)
        for alias, alias_key in alias_items:
            if q == alias_key and record.instrument_type.lower() == "index":
                return SymbolCandidate(record, 1.0, "index_alias", alias)
        if q == name:
            return SymbolCandidate(record, 0.98, "exact_alias", record.name)
        for alias, alias_key in alias_items:
            if q == alias_key:
                return SymbolCandidate(record, 0.98, "exact_alias", alias)

        if re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z]{1,3})?", _normalize_query(query)):
            return None

        if q.isdigit():
            return None

        searchable = [(record.raw_symbol, raw), (record.name, name), *alias_items]
        prefix_matches = [
            label for label, key in searchable if key and key.startswith(q)
        ]
        if prefix_matches:
            return SymbolCandidate(record, 0.82, "prefix", prefix_matches[0])

        contains_matches = [
            label for label, key in searchable if key and q in key
        ]
        if contains_matches:
            return SymbolCandidate(record, 0.68, "contains", contains_matches[0])

        best_label = ""
        best_ratio = 0.0
        for label, key in searchable:
            if not key:
                continue
            ratio = difflib.SequenceMatcher(None, q, key).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_label = label
        if best_ratio >= 0.86:
            return SymbolCandidate(record, 0.58, "fuzzy", best_label)
        return None


@lru_cache(maxsize=1)
def get_default_symbol_universe_cache() -> SymbolUniverseCache:
    for snapshot_path in (
        DEFAULT_RUNTIME_SYMBOL_UNIVERSE_CACHE_PATH,
        DEFAULT_SYMBOL_UNIVERSE_SNAPSHOT_PATH,
    ):
        if snapshot_path.exists():
            return SymbolUniverseCache.from_json_snapshot(snapshot_path)
    return SymbolUniverseCache.from_providers(
        [
            CuratedSeedSymbolProvider(),
            StockMappingSymbolProvider(),
        ]
    )


@lru_cache(maxsize=1)
def get_default_symbol_resolver() -> SymbolResolver:
    return SymbolResolver(get_default_symbol_universe_cache())

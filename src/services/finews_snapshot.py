# -*- coding: utf-8 -*-
"""FiNews latest homepage snapshot parser/fetcher.

This module treats FiNews as a public external reference page. It fetches only
the homepage, parses visible text into a DSA-owned JSON shape, and never returns
raw remote HTML for rendering.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests
try:
    from opencc import OpenCC
except Exception:  # pragma: no cover - dependency is declared, fallback is for degraded runtimes
    OpenCC = None  # type: ignore[assignment]

from src.core.zh_tw_localization import localize_route_b_zh_tw_text

logger = logging.getLogger(__name__)

FINEWS_SOURCE_URL = "https://finews.elsetech.app/"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = REPO_ROOT / "data" / "cache" / "finews_latest_snapshot.json"
PARSER_VERSION = "finews-v2"
CONVERSION_ENGINE = "opencc-s2twp"
CONVERSION_VERSION = "2026-06-29-phase21-2r"

FinewsFetcher = Callable[[str, float], str]

SECTION_ORDER = (
    "after_market_summary",
    "major_news",
    "market_temperature",
    "major_indices",
    "major_stocks",
    "treasury_yields",
    "fx",
)

SECTION_LABELS = {
    "after_market_summary": "盤後總結",
    "major_news": "主要新聞",
    "market_temperature": "市場溫度",
    "major_indices": "主要指數",
    "major_stocks": "主要股票",
    "treasury_yields": "美債利率",
    "fx": "主要匯率",
}

SECTION_ALIASES = {
    "after_market_summary": {"盘后总结", "盤後總結"},
    "major_news": {"主要新闻", "主要新聞"},
    "market_temperature": {"市场温度", "市場溫度"},
    "major_indices": {"主要指数", "主要指數"},
    "major_stocks": {"主要股票", "主要股票"},
    "treasury_yields": {"美债利率", "美債利率"},
    "fx": {"主要汇率", "主要匯率"},
}

FINEWS_ZH_TW_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("聯儲", "聯準會"),
    ("美聯儲", "聯準會"),
    ("通脹", "通膨"),
    ("智慧手機", "智慧型手機"),
    ("特朗普", "川普"),
)

_OPENCC_CONVERTER: Any = None

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth == 0 and tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def lines(self) -> list[str]:
        text = "".join(self._parts)
        return [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if re.sub(r"\s+", " ", line).strip()
        ]


class _ExternalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active_href: Optional[str] = None
        self._active_text: list[str] = []
        self.links: list[dict[str, str]] = []
        self._seen: set[tuple[str, str]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag == "a":
            href = attr_map.get("href", "").strip()
            if _is_safe_external_url(href):
                self._active_href = href
                self._active_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._active_href:
            title = to_zh_tw(re.sub(r"\s+", " ", "".join(self._active_text)).strip())
            if title:
                key = (title, self._active_href)
                if key not in self._seen:
                    self._seen.add(key)
                    self.links.append({"title": title, "url": self._active_href})
            self._active_href = None
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)


def to_zh_tw(text: Optional[str]) -> str:
    if not text:
        return ""
    output = text
    global _OPENCC_CONVERTER
    if OpenCC is not None:
        if _OPENCC_CONVERTER is None:
            _OPENCC_CONVERTER = OpenCC("s2twp")
        output = _OPENCC_CONVERTER.convert(output)
    output = localize_route_b_zh_tw_text(output)
    for simplified, traditional in FINEWS_ZH_TW_OVERRIDES:
        output = output.replace(simplified, traditional)
    return output


def _empty_sections() -> dict[str, list[str]]:
    return {key: [] for key in SECTION_ORDER}


def _extract_visible_lines(html_text: str) -> list[str]:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    return parser.lines()


def _is_safe_external_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_external_links(html_text: str) -> list[dict[str, str]]:
    parser = _ExternalLinkParser()
    parser.feed(html_text)
    return parser.links


def _link_matches_item(title: str, url: str, item: str) -> bool:
    title_norm = title.strip().lower()
    item_norm = item.strip().lower()
    if not title_norm or not item_norm:
        return False
    if title_norm == item_norm or item_norm in title_norm or title_norm in item_norm:
        return True
    parsed = urlparse(url)
    url_text = " ".join(part for part in [parsed.path, parsed.query, parsed.fragment] if part).lower()
    token = re.escape(item_norm)
    return bool(re.search(rf"(^|[^a-z0-9^.-]){token}([^a-z0-9.-]|$)", url_text))


def _associate_section_links(
    sections: dict[str, list[str]],
    external_links: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    section_links: dict[str, list[dict[str, str]]] = {key: [] for key in SECTION_ORDER}
    item_sets = {key: {item.strip() for item in items if item.strip()} for key, items in sections.items()}

    for link in external_links:
        title = (link.get("title") or "").strip()
        url = (link.get("url") or "").strip()
        if not title or not _is_safe_external_url(url):
            continue
        for key, items in item_sets.items():
            if any(_link_matches_item(title, url, item) for item in items):
                section_links[key].append({"title": title, "url": url})
                break

    return section_links


def _extract_json_ld(html_text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    pattern = re.compile(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        raw = html.unescape(match.group(1).strip())
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
        elif isinstance(parsed, list):
            payloads.extend(item for item in parsed if isinstance(item, dict))
    return payloads


def _metadata_from_json_ld(html_text: str) -> tuple[Optional[str], Optional[str]]:
    report_date = None
    source_updated_at = None
    for payload in _extract_json_ld(html_text):
        if payload.get("@type") != "NewsArticle":
            continue
        if isinstance(payload.get("datePublished"), str):
            report_date = payload["datePublished"].strip() or None
        if isinstance(payload.get("dateModified"), str):
            source_updated_at = payload["dateModified"].strip() or None
        break
    return report_date, source_updated_at


def _metadata_from_text(lines: list[str]) -> tuple[Optional[str], Optional[str]]:
    report_date = None
    source_updated_at = None
    date_re = re.compile(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
    for index, line in enumerate(lines[:12]):
        if report_date is None:
            match = date_re.search(line)
            if match:
                report_date = match.group(0).replace("/", "-").replace(".", "-")
        if "更新" in line or "更新时间" in line or "更新時間" in line:
            candidate = lines[index + 1] if index + 1 < len(lines) else line
            source_updated_at = candidate.strip() or None
    return report_date, source_updated_at


def _section_key_for_line(line: str) -> Optional[str]:
    normalized = line.strip()
    localized = to_zh_tw(normalized)
    for key, aliases in SECTION_ALIASES.items():
        if normalized in aliases or localized in aliases or localized == SECTION_LABELS[key]:
            return key
    return None


def _is_noise_line(line: str) -> bool:
    if line in {"‹", "›", "日", "一", "二", "三", "四", "五", "六"}:
        return True
    if re.fullmatch(r"\d{1,2}", line):
        return True
    return False


def _extract_sections(lines: list[str]) -> dict[str, list[str]]:
    sections = _empty_sections()
    current_key: Optional[str] = None

    for line in lines:
        section_key = _section_key_for_line(line)
        if section_key:
            current_key = section_key
            continue
        if current_key is None or _is_noise_line(line):
            continue
        clean_line = re.sub(r"^\d{1,2}\s*(?=[\u4e00-\u9fff])", "", line)
        localized = to_zh_tw(clean_line)
        if localized:
            sections[current_key].append(localized)

    return sections


def parse_finews_homepage_html(
    html_text: str,
    *,
    fetched_at: Optional[str] = None,
) -> dict[str, Any]:
    lines = _extract_visible_lines(html_text)
    report_date, source_updated_at = _metadata_from_json_ld(html_text)
    text_report_date, text_updated_at = _metadata_from_text(lines)

    sections = _extract_sections(lines)
    external_links = _extract_external_links(html_text)

    return {
        "source": "finews",
        "source_url": FINEWS_SOURCE_URL,
        "report_date": report_date or text_report_date,
        "source_updated_at": source_updated_at or text_updated_at,
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
        "stale": False,
        "fetch_error": None,
        "language_original": "zh-CN",
        "language_rendered": "zh-TW",
        "parser_version": PARSER_VERSION,
        "conversion_engine": CONVERSION_ENGINE,
        "conversion_version": CONVERSION_VERSION,
        "external_links": external_links,
        "section_links": _associate_section_links(sections, external_links),
        "sections": sections,
    }


def _convert_cached_value(value: Any, *, key: str = "") -> Any:
    if isinstance(value, str):
        return value if key in {"url", "source_url"} else to_zh_tw(value)
    if isinstance(value, list):
        return [_convert_cached_value(item, key=key) for item in value]
    if isinstance(value, dict):
        return {item_key: _convert_cached_value(item_value, key=item_key) for item_key, item_value in value.items()}
    return value


def _normalize_cached_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _convert_cached_value(payload)
    if not isinstance(normalized, dict):
        return payload
    normalized.setdefault("source", "finews")
    normalized.setdefault("source_url", FINEWS_SOURCE_URL)
    normalized.setdefault("language_original", "zh-CN")
    normalized.setdefault("language_rendered", "zh-TW")
    normalized["parser_version"] = PARSER_VERSION
    normalized["conversion_engine"] = CONVERSION_ENGINE
    normalized["conversion_version"] = CONVERSION_VERSION
    sections = normalized.setdefault("sections", _empty_sections())
    external_links = normalized.setdefault("external_links", normalized.pop("news_links", []))
    normalized["section_links"] = _associate_section_links(sections, external_links)
    return normalized


def _default_fetcher(url: str, timeout: float) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "DSA-FiNews-Snapshot/1.0"},
    )
    response.raise_for_status()
    return response.text


def _cache_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return path
    configured = os.getenv("DSA_FINEWS_CACHE_PATH")
    return Path(configured) if configured else DEFAULT_CACHE_PATH


def _read_cache(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read FiNews snapshot cache %s: %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def _error_snapshot(fetch_error: str, fetched_at: str) -> dict[str, Any]:
    return {
        "source": "finews",
        "source_url": FINEWS_SOURCE_URL,
        "report_date": None,
        "source_updated_at": None,
        "fetched_at": fetched_at,
        "stale": False,
        "fetch_error": fetch_error,
        "language_original": "zh-CN",
        "language_rendered": "zh-TW",
        "parser_version": PARSER_VERSION,
        "conversion_engine": CONVERSION_ENGINE,
        "conversion_version": CONVERSION_VERSION,
        "external_links": [],
        "section_links": {key: [] for key in SECTION_ORDER},
        "sections": _empty_sections(),
    }


def fetch_latest_finews_snapshot(
    *,
    fetcher: Optional[FinewsFetcher] = None,
    cache_path: Optional[Path] = None,
    timeout: float = 15.0,
    fetched_at: Optional[str] = None,
) -> dict[str, Any]:
    timestamp = fetched_at or datetime.now(timezone.utc).isoformat()
    cache = _cache_path(cache_path)
    active_fetcher = fetcher or _default_fetcher

    try:
        html_text = active_fetcher(FINEWS_SOURCE_URL, timeout)
        snapshot = parse_finews_homepage_html(html_text, fetched_at=timestamp)
        _write_cache(cache, snapshot)
        return snapshot
    except Exception as exc:
        logger.warning("FiNews snapshot fetch failed: %s", exc)
        error = f"finews_fetch_failed: {type(exc).__name__}"
        cached = _read_cache(cache)
        if cached:
            normalized = _normalize_cached_snapshot(cached)
            normalized["stale"] = True
            normalized["fetch_error"] = error
            return normalized
        return _error_snapshot(error, timestamp)

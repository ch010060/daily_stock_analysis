# -*- coding: utf-8 -*-
"""Latest-only TAIFEX VIXTWN fetcher."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, List, Optional

import requests

logger = logging.getLogger(__name__)

TAIFEX_VIXTWN_DAILY_TXT_URL = (
    "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{yyyymm}new.txt"
)
TAIFEX_VIXTWN_SOURCE = "taifex"
TAIFEX_VIXTWN_SOURCE_URL_KEY = "taifex_vixtwn_daily_txt"


@dataclass(frozen=True)
class TaifexVixtwnQuote:
    value: Optional[float]
    as_of: Optional[str]
    source: str = TAIFEX_VIXTWN_SOURCE
    source_url_key: str = TAIFEX_VIXTWN_SOURCE_URL_KEY
    data_gap_reason: Optional[str] = None


def _gap(reason: str) -> TaifexVixtwnQuote:
    return TaifexVixtwnQuote(value=None, as_of=None, data_gap_reason=reason)


def _month_candidates(today: Optional[date] = None) -> List[str]:
    current = today or date.today()
    previous_year = current.year if current.month > 1 else current.year - 1
    previous_month = current.month - 1 if current.month > 1 else 12
    return [f"{current.year:04d}{current.month:02d}", f"{previous_year:04d}{previous_month:02d}"]


def parse_vixtwn_daily_txt(text: str) -> TaifexVixtwnQuote:
    """Parse TAIFEX daily txt and return the latest valid date/value row."""
    rows: List[TaifexVixtwnQuote] = []
    for line in (text or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 3 or len(parts[0]) != 8 or not parts[0].isdigit():
            continue
        try:
            value = float(parts[2])
        except (TypeError, ValueError):
            continue
        raw_date = parts[0]
        rows.append(TaifexVixtwnQuote(
            value=value,
            as_of=f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}",
        ))
    if not rows:
        return _gap("taifex_vixtwn_no_valid_rows")
    return rows[-1]


def fetch_latest_vixtwn(
    *,
    session: Any = None,
    today: Optional[date] = None,
    timeout: int = 15,
) -> TaifexVixtwnQuote:
    """Fetch latest VIXTWN daily close from TAIFEX; never raises."""
    http = session or requests
    last_gap = "taifex_vixtwn_fetch_failed"
    for yyyymm in _month_candidates(today):
        url = TAIFEX_VIXTWN_DAILY_TXT_URL.format(yyyymm=yyyymm)
        try:
            response = http.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            last_gap = "taifex_vixtwn_fetch_failed"
            logger.warning("[taifex_vixtwn] fetch failed for %s: %s", yyyymm, exc)
            continue
        if getattr(response, "status_code", None) != 200:
            last_gap = "taifex_vixtwn_fetch_failed"
            continue
        quote = parse_vixtwn_daily_txt(getattr(response, "text", "") or "")
        if quote.value is not None and quote.as_of:
            return quote
        last_gap = quote.data_gap_reason or "taifex_vixtwn_parse_failed"
    return _gap(last_gap)

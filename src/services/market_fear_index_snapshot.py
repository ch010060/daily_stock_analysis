# -*- coding: utf-8 -*-
"""Deterministic market fear-index snapshot builder."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

US_VIX_LABEL = "恐慌指數 VIX"
TW_VIXTWN_LABEL = "台灣恐慌指數 VIXTWN"


def _to_float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _snapshot(
    *,
    market: str,
    kind: str,
    label: str,
    value: Any,
    as_of: Optional[str],
    source: str,
    source_url_key: str,
    data_gap_reason: Optional[str] = None,
) -> Dict[str, Any]:
    parsed_value = _to_float(value)
    return {
        "market": market,
        "kind": kind,
        "label": label,
        "value": parsed_value,
        "as_of": as_of,
        "source": source,
        "source_url_key": source_url_key,
        "status": "unknown",
        "data_gap_reason": data_gap_reason if parsed_value is None else None,
    }


def build_us_vix_market_fear_snapshot(
    value: Any,
    *,
    as_of: Optional[str] = None,
    data_gap_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return _snapshot(
        market="us",
        kind="vix",
        label=US_VIX_LABEL,
        value=value,
        as_of=as_of or date.today().isoformat(),
        source="yfinance_yahoo_quote",
        source_url_key="yahoo_vix",
        data_gap_reason=data_gap_reason or "yfinance_vix_missing",
    )


def build_tw_vixtwn_market_fear_snapshot(quote: Any) -> Dict[str, Any]:
    return _snapshot(
        market="tw",
        kind="vixtwn",
        label=TW_VIXTWN_LABEL,
        value=getattr(quote, "value", None),
        as_of=getattr(quote, "as_of", None),
        source=getattr(quote, "source", "taifex") or "taifex",
        source_url_key=getattr(quote, "source_url_key", "taifex_vixtwn_daily_txt") or "taifex_vixtwn_daily_txt",
        data_gap_reason=getattr(quote, "data_gap_reason", None) or "taifex_vixtwn_fetch_failed",
    )


def build_tw_vixtwn_gap_snapshot(reason: str = "taifex_vixtwn_fetch_failed") -> Dict[str, Any]:
    return _snapshot(
        market="tw",
        kind="vixtwn",
        label=TW_VIXTWN_LABEL,
        value=None,
        as_of=None,
        source="taifex",
        source_url_key="taifex_vixtwn_daily_txt",
        data_gap_reason=reason,
    )

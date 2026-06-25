# -*- coding: utf-8 -*-
"""
Phase 19B.2 — deterministic valuation/fundamental snapshot builders.

These shape already-fetched raw provider fields (FinMind for TW, yfinance
`fundamental_context` for US) into the fixed `valuation_snapshot` /
`fundamental_snapshot` report-contract dicts. They never fetch data
themselves and never read anything LLM-supplied — the numeric table is
backend-deterministic by construction. Missing fields degrade to `None`
and are listed in `data_gap_fields` so the renderer can show "資料不足"
instead of guessing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

VALUATION_FIELDS = ("pe_ttm", "pe_forward", "pb", "dividend_yield", "market_cap")
FUNDAMENTAL_FIELDS = ("revenue_yoy", "earnings_yoy", "net_profit_yoy", "roe", "gross_margin")


def _build_snapshot(
    fields: tuple,
    raw: Dict[str, Any],
    *,
    source: str,
    as_of: Optional[str],
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    gaps: List[str] = []
    for field_name in fields:
        value = raw.get(field_name)
        snapshot[field_name] = value
        if value is None:
            gaps.append(field_name)
    snapshot["source"] = source
    snapshot["as_of"] = as_of or raw.get("as_of")
    snapshot["data_gap_fields"] = gaps
    return snapshot


def build_valuation_snapshot(
    raw: Dict[str, Any], *, source: str, as_of: Optional[str] = None
) -> Dict[str, Any]:
    """Build the `valuation_snapshot` contract dict from raw provider fields."""
    return _build_snapshot(VALUATION_FIELDS, raw, source=source, as_of=as_of)


def build_fundamental_snapshot(
    raw: Dict[str, Any], *, source: str, as_of: Optional[str] = None
) -> Dict[str, Any]:
    """Build the `fundamental_snapshot` contract dict from raw provider fields."""
    return _build_snapshot(FUNDAMENTAL_FIELDS, raw, source=source, as_of=as_of)

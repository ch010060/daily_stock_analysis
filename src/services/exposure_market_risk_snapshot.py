# -*- coding: utf-8 -*-
"""
Phase 19B.3 — deterministic exposure / market-risk snapshot builders.

Mirrors `src/services/valuation_fundamental_snapshot.py` (Phase 19B.2):
these shape already-fetched raw fields into the fixed `exposure_snapshot` /
`market_risk_snapshot` report-contract dicts. They never fetch data
themselves and are never LLM-populated. Missing fields degrade to `None`
and are listed in `data_gap_fields` so the renderer shows "資料不足"
instead of guessing.

`source=None` is a valid, deliberate state (TW this phase: no FinMind/
yfinance call is made at all per the Phase 19B.3 security constraint —
see `gap_reason`), distinct from "fetch attempted but field missing".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

EXPOSURE_FIELDS = ("underlying_index", "leverage_factor", "is_leveraged", "is_inverse")
MARKET_RISK_FIELDS = ("vix_level", "vix_status", "spx_change_pct", "risk_level")

TW_MARKET_RISK_GAP_REASON = "本期未對台股市場風險溫度計發起任何外部資料請求，固定顯示資料不足"


def _build_snapshot(
    fields: tuple,
    raw: Dict[str, Any],
    *,
    source: Optional[str],
    as_of: Optional[str],
    gap_reason: Optional[str] = None,
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
    if gap_reason:
        snapshot["gap_reason"] = gap_reason
    return snapshot


def build_exposure_snapshot(
    raw: Dict[str, Any],
    *,
    source: Optional[str],
    as_of: Optional[str] = None,
    gap_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the `exposure_snapshot` contract dict (ETF/index-only)."""
    return _build_snapshot(EXPOSURE_FIELDS, raw, source=source, as_of=as_of, gap_reason=gap_reason)


def build_market_risk_snapshot(
    raw: Dict[str, Any],
    *,
    source: Optional[str],
    as_of: Optional[str] = None,
    gap_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the `market_risk_snapshot` contract dict (ETF/index-only)."""
    return _build_snapshot(MARKET_RISK_FIELDS, raw, source=source, as_of=as_of, gap_reason=gap_reason)


def classify_vix_status(vix_level: Optional[float]) -> Optional[str]:
    """Deterministic VIX bucketing — fixed thresholds, no LLM, no guessing."""
    if vix_level is None:
        return None
    if vix_level >= 30:
        return "恐慌"
    if vix_level >= 20:
        return "緊張"
    return "平穩"

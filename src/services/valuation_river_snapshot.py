# -*- coding: utf-8 -*-
"""
Phase 26.1 — deterministic valuation river snapshot for TW stocks.

Builds a historical PER/PBR-derived price-band series ("valuation river")
purely from already-fetched FinMind `TaiwanStockPER` (daily PER/PBR/dividend
yield) joined with `TaiwanStockPrice` (daily OHLCV) by date. Every number is
backend-deterministic arithmetic:

    implied_eps(t)  = close(t) / per(t)
    implied_bvps(t) = close(t) / pbr(t)
    band(t, multiple) = implied_eps(t) * multiple

The LLM never sees or produces any of this — this module has no prompt
awareness and is never imported by `analysis_context_builder.py`. Band
multiples are fixed constants (not configurable per-request, not LLM
output), and are explicitly documented as visual reference multiples, not
fair value / target price / a recommendation.

Non-goals (see docs/worklogs and Phase 26.0 report): no US historical
EPS/BVPS extraction, no full valuation engine, no sector-relative or peer
comparison, no forward EPS, no LLM-generated commentary, no trading signal.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Fixed, deterministic PER multiples — visual reference bands only.
# Chosen in Phase 26.0's PoC to bracket the ~19.7x-34.9x PER range observed
# for 2330 over a ~13-month window with headroom on both sides.
PER_BAND_MULTIPLES: tuple = (14, 18, 22, 26, 30, 34, 38)
NEUTRAL_MULTIPLE = 26

METHODOLOGY_NOTE = (
    "倍數帶為固定視覺參考基準（非估值結論、目標價或買賣建議），"
    "由 close(t)/PER(t) 反推的隱含 EPS 乘上固定倍數計算而得。"
)

MIN_JOINED_ROWS = 20  # below this, "partial"; below GAP_JOINED_ROWS, "gap"
GAP_JOINED_ROWS = 5


def _band_key(multiple: int) -> str:
    return f"per_{multiple}"


def _zone_for_multiple(current_multiple: Optional[float]) -> str:
    if current_multiple is None:
        return "unknown"
    if current_multiple < NEUTRAL_MULTIPLE:
        return "undervalued"
    if current_multiple > NEUTRAL_MULTIPLE:
        return "overvalued"
    return "neutral"


def _unavailable(
    *, market: str, symbol: str, reason: str, warnings: Optional[List[str]] = None
) -> Dict[str, Any]:
    return {
        "enabled": False,
        "market": market,
        "symbol": symbol,
        "currency": "TWD" if market == "tw" else ("USD" if market == "us" else None),
        "source": "unavailable",
        "method": "unavailable",
        "basis": "unavailable",
        "as_of": None,
        "range": {"start_date": None, "end_date": None, "trading_days": 0},
        "points": [],
        "current": {
            "close": None, "per": None, "pbr": None,
            "implied_eps": None, "implied_bvps": None, "zone": "unknown",
        },
        "quality": {
            "status": "unsupported",
            "warnings": warnings or [reason],
            "data_gap_fields": [],
            "methodology_note": METHODOLOGY_NOTE,
        },
    }


def build_valuation_river_snapshot_unsupported(market: str, symbol: str, reason: str) -> Dict[str, Any]:
    """Public helper for non-TW / non-stock callers: always returns a well-formed
    unavailable snapshot so the frontend adapter never has to special-case a
    missing key vs. an explicit "not applicable" state."""
    return _unavailable(market=market, symbol=symbol, reason=reason)


def build_tw_valuation_river_snapshot(
    symbol: str,
    per_rows: List[Dict[str, Any]],
    price_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the TW valuation river snapshot from already-fetched FinMind rows.

    Args:
        symbol: bare TW stock_id (e.g. "2330").
        per_rows: rows from `TaiwanStockPER` fetch (date/PER/PBR/dividend_yield).
        price_rows: rows from `TaiwanStockPrice` fetch (date/close/...).

    Returns:
        The full `valuation_river_snapshot` contract dict. Never raises —
        insufficient/malformed input degrades to `quality.status` in
        {"partial", "gap"} with `enabled=True` but an empty/short `points`
        list, never to a crash.
    """
    warnings: List[str] = []

    if not per_rows:
        return _unavailable(market="tw", symbol=symbol, reason="TaiwanStockPER 無資料")
    if not price_rows:
        return _unavailable(market="tw", symbol=symbol, reason="TaiwanStockPrice 無資料")

    per_by_date = {r.get("date"): r for r in per_rows if r.get("date")}
    price_by_date = {r.get("date"): r for r in price_rows if r.get("date")}
    joined_dates = sorted(set(per_by_date) & set(price_by_date))

    if not joined_dates:
        return _unavailable(
            market="tw", symbol=symbol,
            reason="TaiwanStockPER 與 TaiwanStockPrice 日期無交集",
        )

    points: List[Dict[str, Any]] = []
    per_gap_count = 0
    pbr_gap_count = 0

    for d in joined_dates:
        per_row = per_by_date[d]
        price_row = price_by_date[d]
        close = price_row.get("close")
        per = per_row.get("PER")
        pbr = per_row.get("PBR")

        implied_eps = None
        implied_bvps = None
        bands: Dict[str, float] = {}

        if close is None:
            continue  # no price on this date is a hard skip; can't derive anything

        if per is None or per == 0:
            per_gap_count += 1
        else:
            implied_eps = round(close / per, 4)
            bands = {_band_key(m): round(implied_eps * m, 4) for m in PER_BAND_MULTIPLES}

        if pbr is None or pbr == 0:
            pbr_gap_count += 1
        else:
            implied_bvps = round(close / pbr, 4)

        point: Dict[str, Any] = {
            "date": d,
            "close": close,
            "per": per,
            "pbr": pbr,
            "implied_eps": implied_eps,
            "implied_bvps": implied_bvps,
        }
        if bands:
            point["bands"] = bands
        points.append(point)

    if not points:
        return _unavailable(
            market="tw", symbol=symbol,
            reason="聯集日期後無可用收盤價資料",
        )

    if len(points) < GAP_JOINED_ROWS:
        return _unavailable(
            market="tw", symbol=symbol,
            reason=f"聯集資料筆數過少（僅 {len(points)} 個交易日，低於 {GAP_JOINED_ROWS} 天下限），暫不提供河流圖",
        )

    if per_gap_count:
        warnings.append(f"{per_gap_count} 個交易日缺少 PER，該日無倍數帶")
    if pbr_gap_count:
        warnings.append(f"{pbr_gap_count} 個交易日缺少 PBR，implied_bvps 為 null")

    last = points[-1]
    current_zone = _zone_for_multiple(last.get("per"))

    status = "ok"
    if len(points) < MIN_JOINED_ROWS:
        status = "partial"
        warnings.append(f"僅 {len(points)} 個交易日聯集資料，低於建議下限 {MIN_JOINED_ROWS} 天")

    return {
        "enabled": True,
        "market": "tw",
        "symbol": symbol,
        "currency": "TWD",
        "source": "finmind",
        "method": "per_implied_eps_river",
        "basis": "implied_eps",
        "band_multiples": list(PER_BAND_MULTIPLES),
        "neutral_multiple": NEUTRAL_MULTIPLE,
        "as_of": last["date"],
        "range": {
            "start_date": points[0]["date"],
            "end_date": last["date"],
            "trading_days": len(points),
        },
        "points": points,
        "current": {
            "close": last["close"],
            "per": last.get("per"),
            "pbr": last.get("pbr"),
            "implied_eps": last.get("implied_eps"),
            "implied_bvps": last.get("implied_bvps"),
            "zone": current_zone,
        },
        "quality": {
            "status": status,
            "warnings": warnings,
            "data_gap_fields": (["per"] if per_gap_count else []) + (["pbr"] if pbr_gap_count else []),
            "methodology_note": METHODOLOGY_NOTE,
        },
    }

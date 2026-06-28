# -*- coding: utf-8 -*-
"""
Phase 19B.4 — deterministic multi-period trend snapshot builder.

Mirrors `src/services/exposure_market_risk_snapshot.py` (Phase 19B.3): pure
shaping functions only, no fetching, never LLM-populated. Given a list of
OHLC rows (already fetched by the pipeline via
`src/services/history_loader.py::load_history_df`), computes fixed-period
(5D/20D/60D/120D/252D) return/drawdown/MA-position/trend-status rows.
Periods without enough rows degrade to `insufficient_data` /
`data_gap_fields` instead of guessing — never a hallucinated number.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# (period_key, label, required_points)
PERIOD_DEFS = (
    ("5D", "1週", 5),
    ("20D", "1月", 20),
    ("60D", "1季", 60),
    ("120D", "半年", 120),
    ("252D", "52週", 252),
)


def normalize_ohlc_rows(raw_rows: Any) -> List[Dict[str, Any]]:
    """Normalize a DataFrame/list-of-dict/None into ascending-by-date dict rows.

    Accepts a pandas DataFrame (as returned by `load_history_df`) or a list
    of dicts. Drops rows missing `close`. Never raises — malformed input
    returns an empty list.
    """
    rows: List[Dict[str, Any]] = []
    try:
        if raw_rows is None:
            return []
        if hasattr(raw_rows, "to_dict") and hasattr(raw_rows, "columns"):
            # pandas DataFrame
            rows = raw_rows.to_dict("records")
        elif isinstance(raw_rows, (list, tuple)):
            rows = [dict(r) for r in raw_rows if isinstance(r, dict)]
        else:
            return []
    except Exception:
        return []

    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        close = row.get("close")
        if close is None:
            continue
        date_val = row.get("date")
        cleaned.append({
            "date": date_val,
            "high": row.get("high", close),
            "low": row.get("low", close),
            "close": close,
        })

    def _sort_key(row: Dict[str, Any]):
        d = row.get("date")
        return str(d) if d is not None else ""

    cleaned.sort(key=_sort_key)
    return cleaned


def format_pct(value: Optional[float]) -> Optional[float]:
    """Round a fractional/percent change to 2 decimals; pass through None."""
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def classify_period_trend(
    change_pct: Optional[float],
    price_vs_ma_pct: Optional[float],
) -> str:
    """Deterministic trend bucket — fixed thresholds, no LLM, no guessing."""
    if change_pct is None or price_vs_ma_pct is None:
        return "insufficient_data"
    if change_pct >= 5 and price_vs_ma_pct >= 0:
        return "uptrend"
    if change_pct <= -5 and price_vs_ma_pct < 0:
        return "downtrend"
    return "neutral"


def _build_period_row(period_key: str, label: str, required: int, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    available = min(len(rows), required)
    window = rows[-required:] if len(rows) >= required else rows
    row: Dict[str, Any] = {
        "period": period_key,
        "label": label,
        "required_points": required,
        "available_points": available,
        "start_close": None,
        "end_close": None,
        "change_pct": None,
        "period_high": None,
        "period_low": None,
        "drawdown_from_high_pct": None,
        "ma": None,
        "price_vs_ma_pct": None,
        "trend_status": "insufficient_data",
        "data_gap_fields": [],
    }

    if len(rows) < required or not window:
        row["data_gap_fields"] = [
            "start_close", "end_close", "change_pct", "period_high", "period_low",
            "drawdown_from_high_pct", "ma", "price_vs_ma_pct",
        ]
        return row

    try:
        closes = [float(r["close"]) for r in window]
        highs = [float(r.get("high", r["close"])) for r in window]
        lows = [float(r.get("low", r["close"])) for r in window]

        start_close = closes[0]
        end_close = closes[-1]
        period_high = max(highs)
        period_low = min(lows)
        ma = sum(closes) / len(closes)

        change_pct = ((end_close - start_close) / start_close * 100) if start_close else None
        drawdown_from_high_pct = (
            ((end_close - period_high) / period_high * 100) if period_high else None
        )
        price_vs_ma_pct = ((end_close - ma) / ma * 100) if ma else None

        row.update({
            "start_close": start_close,
            "end_close": end_close,
            "change_pct": format_pct(change_pct),
            "period_high": period_high,
            "period_low": period_low,
            "drawdown_from_high_pct": format_pct(drawdown_from_high_pct),
            "ma": round(ma, 4) if ma is not None else None,
            "price_vs_ma_pct": format_pct(price_vs_ma_pct),
        })
        row["trend_status"] = classify_period_trend(row["change_pct"], row["price_vs_ma_pct"])
    except (TypeError, ValueError, KeyError):
        row["data_gap_fields"] = [
            "start_close", "end_close", "change_pct", "period_high", "period_low",
            "drawdown_from_high_pct", "ma", "price_vs_ma_pct",
        ]
        row["trend_status"] = "insufficient_data"

    return row


def build_multi_period_trend_snapshot(
    raw_rows: Any,
    *,
    source: Optional[str],
    as_of: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build the `multi_period_trend_snapshot` contract dict.

    Returns `None` when there are no usable rows at all (e.g. fetch failed
    upstream). Otherwise always returns a dict with all 5 period rows —
    periods lacking enough data are marked `insufficient_data` with their
    `data_gap_fields` populated rather than omitted.
    """
    rows = normalize_ohlc_rows(raw_rows)
    if not rows:
        return None

    periods = [_build_period_row(key, label, required, rows) for key, label, required in PERIOD_DEFS]
    top_level_gaps = [p["period"] for p in periods if p["data_gap_fields"]]
    latest_close = rows[-1].get("close")
    latest_date = rows[-1].get("date")

    return {
        "market": None,
        "source": source,
        "as_of": as_of or (str(latest_date) if latest_date is not None else None),
        "latest_close": float(latest_close) if latest_close is not None else None,
        "periods": periods,
        "data_gap_fields": top_level_gaps,
        "notes": [],
    }

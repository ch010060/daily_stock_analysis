# -*- coding: utf-8 -*-
"""DB-first K-line snapshot builder for report drawers."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.market_context import detect_market


KLINE_RANGE_ROWS: Dict[str, int] = {
    # 1W is still daily-candle based. Ten rows gives the drawer enough
    # visual context without pretending to be intraday data.
    "1w": 10,
    "1m": 20,
    "3m": 60,
    "1y": 252,
}


class KlineHistoryNotFound(Exception):
    """Raised when the requested history record cannot be resolved."""


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return date.min
    if hasattr(value, "date"):
        try:
            coerced = value.date()
            return coerced if isinstance(coerced, date) else date.min
        except Exception:
            return date.min
    return date.min


def _read_raw_result(record: Any) -> Dict[str, Any]:
    raw = getattr(record, "raw_result", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _history_candidates(code: str) -> List[str]:
    raw = str(code or "").strip()
    normalized = canonical_stock_code(normalize_stock_code(raw))
    candidates: List[str] = []
    for candidate in (canonical_stock_code(raw), normalized):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _resolve_history(db_manager: Any, record_id: str) -> Any:
    record = None
    try:
        record = db_manager.get_analysis_history_by_id(int(record_id))
    except (TypeError, ValueError):
        pass
    if record is None and hasattr(db_manager, "get_latest_analysis_by_query_id"):
        record = db_manager.get_latest_analysis_by_query_id(str(record_id))
    if record is None:
        raise KlineHistoryNotFound(str(record_id))
    return record


def _record_end_date(record: Any) -> date:
    created_at = getattr(record, "created_at", None)
    parsed = _date_value(created_at)
    return parsed if parsed != date.min else date.today()


def _bar_to_row(bar: Any) -> Optional[Dict[str, Any]]:
    row_date = _date_value(getattr(bar, "date", None))
    open_ = _finite(getattr(bar, "open", None))
    high = _finite(getattr(bar, "high", None))
    low = _finite(getattr(bar, "low", None))
    close = _finite(getattr(bar, "close", None))
    if row_date == date.min or None in (open_, high, low, close):
        return None
    return {
        "date": row_date.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": _finite(getattr(bar, "volume", None)),
        "source": str(getattr(bar, "data_source", "") or ""),
    }


def _with_moving_averages(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    closes = [row["close"] for row in rows]
    output: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        enriched = dict(row)
        for period in (20, 60, 120, 252):
            key = f"ma{period}"
            if index + 1 < period:
                enriched[key] = None
                continue
            window = closes[index + 1 - period:index + 1]
            enriched[key] = sum(window) / period
        output.append(enriched)
    return output


def _market_for_code(code: str) -> str:
    market = detect_market(code)
    return market if market in {"tw", "us"} else "unknown"


def _expected_source(market: str) -> str:
    if market == "tw":
        return "TaiwanFinMindFetcher"
    if market == "us":
        return "YfinanceFetcher"
    return "unknown"


def _first_number(raw: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = _finite(raw.get(key))
        if value is not None:
            return value
    return None


def build_history_kline(db_manager: Any, record_id: str, range_value: str = "3m") -> Dict[str, Any]:
    """Build an additive K-line API payload from local OHLC cache."""
    if range_value not in KLINE_RANGE_ROWS:
        range_value = "3m"

    record = _resolve_history(db_manager, record_id)
    raw = _read_raw_result(record)
    symbol = canonical_stock_code(str(getattr(record, "code", "") or ""))
    market = _market_for_code(symbol)
    instrument_type = str(
        raw.get("instrument_type") or raw.get("instrumentType") or "unknown"
    ).lower()
    end_date = _record_end_date(record)
    start_date = end_date - timedelta(days=540)

    bars: List[Any] = []
    resolved_symbol = symbol
    for candidate in _history_candidates(symbol):
        candidate_bars = list(db_manager.get_data_range(candidate, start_date, end_date) or [])
        if candidate_bars:
            bars = candidate_bars
            resolved_symbol = candidate
            break

    if not bars:
        return {
            "history_id": getattr(record, "id", None),
            "symbol": symbol,
            "market": market,
            "instrument_type": instrument_type,
            "range": range_value,
            "source": _expected_source(market),
            "source_type": "data_gap",
            "as_of": None,
            "rows": [],
            "current_price": _first_number(raw, "current_price", "currentPrice"),
            "support_level": _first_number(raw, "support_level", "supportLevel"),
            "resistance_level": _first_number(raw, "resistance_level", "resistanceLevel"),
            "data_gap_reason": "no_cached_ohlc",
        }

    rows = [_bar_to_row(bar) for bar in bars]
    valid_rows = sorted((row for row in rows if row), key=lambda row: row["date"])
    enriched_rows = _with_moving_averages(valid_rows)
    requested = KLINE_RANGE_ROWS[range_value]
    display_rows = enriched_rows[-requested:]
    source = next((row.get("source") for row in reversed(enriched_rows) if row.get("source")), None)
    data_gap_reason = "insufficient_rows_for_range" if 0 < len(display_rows) < requested else None

    return {
        "history_id": getattr(record, "id", None),
        "symbol": resolved_symbol,
        "market": market,
        "instrument_type": instrument_type,
        "range": range_value,
        "source": source or _expected_source(market),
        "source_type": "db_cache",
        "as_of": display_rows[-1]["date"] if display_rows else None,
        "rows": display_rows,
        "current_price": _first_number(raw, "current_price", "currentPrice") or (
            display_rows[-1]["close"] if display_rows else None
        ),
        "support_level": _first_number(raw, "support_level", "supportLevel"),
        "resistance_level": _first_number(raw, "resistance_level", "resistanceLevel"),
        "data_gap_reason": data_gap_reason,
    }

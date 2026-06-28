# -*- coding: utf-8 -*-
"""DB-first K-line snapshot builder for report drawers."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

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

INTRADAY_RANGE_CONFIG: Dict[str, Tuple[str, str]] = {
    "1d": ("1d", "5m"),
    "5d": ("5d", "15m"),
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


def _timezone_for_market(market: str) -> Optional[str]:
    if market == "tw":
        return "Asia/Taipei"
    if market == "us":
        return "America/New_York"
    return None


def _currency_for_market(market: str) -> Optional[str]:
    if market == "tw":
        return "TWD"
    if market == "us":
        return "USD"
    return None


def _yfinance_intraday_symbol(symbol: str, market: str) -> str:
    normalized = canonical_stock_code(normalize_stock_code(symbol))
    if market == "tw" and not normalized.endswith(".TW"):
        return f"{normalized}.TW"
    return normalized.removesuffix(".US")


def _classify_intraday_error(exc: Exception) -> str:
    text = f"{type(exc).__name__} {str(exc)}".lower()
    if "rate" in text or "too many" in text or "429" in text:
        return "provider_rate_limited_or_blocked"
    if "timeout" in text or "connection" in text or "network" in text or "ssl" in text:
        return "provider_network_error"
    if "timezone" in text or "tz" in text:
        return "timezone_or_index_error"
    if "not found" in text or "delisted" in text or "no data" in text:
        return "unsupported_symbol_or_no_data"
    return "unknown_error"


def _normalize_intraday_columns(frame: Any) -> Any:
    columns = getattr(frame, "columns", None)
    if columns is None:
        return frame
    if hasattr(columns, "nlevels") and columns.nlevels > 1:
        frame = frame.copy()
        frame.columns = [str(column[0]).lower().replace(" ", "_") for column in frame.columns]
        return frame
    frame = frame.copy()
    frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]
    return frame


def _fetch_yfinance_intraday_frame(symbol: str, period: str, interval: str) -> Tuple[Any, Optional[str]]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    frame = ticker.history(
        period=period,
        interval=interval,
        auto_adjust=False,
        actions=False,
        prepost=False,
    )
    currency = None
    try:
        fast_info = ticker.fast_info
        currency = getattr(fast_info, "currency", None)
        if currency is None and hasattr(fast_info, "get"):
            currency = fast_info.get("currency")
    except Exception:
        currency = None
    return frame, str(currency) if currency else None


def _intraday_gap_payload(
    record: Any,
    symbol: str,
    market: str,
    instrument_type: str,
    range_value: str,
    interval: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "history_id": getattr(record, "id", None),
        "symbol": symbol,
        "market": market,
        "instrument_type": instrument_type,
        "range": range_value,
        "granularity": "intraday",
        "interval": interval,
        "currency": _currency_for_market(market),
        "timezone": _timezone_for_market(market),
        "source": "yfinance",
        "source_type": "data_gap",
        "source_chain": ["yfinance"],
        "as_of": None,
        "is_cached": False,
        "rows": [],
        "candles": [],
        "current_price": None,
        "support_level": None,
        "resistance_level": None,
        "data_gap_reason": reason,
    }


def _build_intraday_kline(
    record: Any,
    raw: Dict[str, Any],
    symbol: str,
    market: str,
    instrument_type: str,
    range_value: str,
) -> Dict[str, Any]:
    period, interval = INTRADAY_RANGE_CONFIG[range_value]
    yf_symbol = _yfinance_intraday_symbol(symbol, market)
    try:
        frame, currency = _fetch_yfinance_intraday_frame(yf_symbol, period, interval)
    except Exception as exc:
        return _intraday_gap_payload(
            record, yf_symbol, market, instrument_type, range_value, interval,
            _classify_intraday_error(exc),
        )

    if frame is None or getattr(frame, "empty", True):
        return _intraday_gap_payload(
            record, yf_symbol, market, instrument_type, range_value, interval,
            "provider_empty_response",
        )

    frame = _normalize_intraday_columns(frame)
    timezone_name = str(getattr(getattr(frame, "index", None), "tz", None) or _timezone_for_market(market) or "")
    candles: List[Dict[str, Any]] = []
    seen = set()
    for timestamp, row in frame.iterrows():
        open_ = _finite(row.get("open"))
        high = _finite(row.get("high"))
        low = _finite(row.get("low"))
        close = _finite(row.get("close"))
        volume = _finite(row.get("volume"))
        if None in (open_, high, low, close, volume):
            continue
        ts = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
        # ponytail: keep the last duplicate timestamp; add exchange sequence handling only if yfinance returns real duplicates.
        if ts in seen:
            candles = [candle for candle in candles if candle["timestamp"] != ts]
        seen.add(ts)
        candles.append({
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })

    if not candles:
        return _intraday_gap_payload(
            record, yf_symbol, market, instrument_type, range_value, interval,
            "provider_partial_ohlcv",
        )

    candles.sort(key=lambda candle: candle["timestamp"])
    return {
        "history_id": getattr(record, "id", None),
        "symbol": yf_symbol,
        "market": market,
        "instrument_type": instrument_type,
        "range": range_value,
        "granularity": "intraday",
        "interval": interval,
        "currency": currency or _currency_for_market(market),
        "timezone": timezone_name or _timezone_for_market(market),
        "source": "yfinance",
        "source_type": "provider",
        "source_chain": ["yfinance"],
        "as_of": candles[-1]["timestamp"],
        "is_cached": False,
        "rows": [],
        "candles": candles,
        "current_price": _first_number(raw, "current_price", "currentPrice") or candles[-1]["close"],
        "support_level": _first_number(raw, "support_level", "supportLevel"),
        "resistance_level": _first_number(raw, "resistance_level", "resistanceLevel"),
        "data_gap_reason": None,
    }


def _snapshot_missing_intraday_payload(
    record: Any,
    symbol: str,
    market: str,
    instrument_type: str,
    range_value: str,
) -> Dict[str, Any]:
    _period, interval = INTRADAY_RANGE_CONFIG[range_value]
    payload = _intraday_gap_payload(
        record,
        _yfinance_intraday_symbol(symbol, market),
        market,
        instrument_type,
        range_value,
        interval,
        "report_kline_snapshot_missing",
    )
    payload["source_chain"] = ["analysis_kline_snapshot"]
    return payload


def _history_parts(db_manager: Any, record_id: str) -> Tuple[Any, Dict[str, Any], str, str, str]:
    record = _resolve_history(db_manager, record_id)
    raw = _read_raw_result(record)
    symbol = canonical_stock_code(str(getattr(record, "code", "") or ""))
    market = _market_for_code(symbol)
    instrument_type = str(
        raw.get("instrument_type") or raw.get("instrumentType") or "unknown"
    ).lower()
    return record, raw, symbol, market, instrument_type


def _build_daily_kline(
    db_manager: Any,
    record: Any,
    raw: Dict[str, Any],
    symbol: str,
    market: str,
    instrument_type: str,
    range_value: str,
    *,
    legacy_fallback: bool = False,
) -> Dict[str, Any]:
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

    source_chain_prefix = (
        ["report_snapshot_missing", "stock_daily_legacy_db_fallback"]
        if legacy_fallback else []
    )

    if not bars:
        return {
            "history_id": getattr(record, "id", None),
            "symbol": symbol,
            "market": market,
            "instrument_type": instrument_type,
            "range": range_value,
            "granularity": "daily",
            "interval": "1d",
            "currency": _currency_for_market(market),
            "timezone": _timezone_for_market(market),
            "source": _expected_source(market),
            "source_type": "data_gap",
            "source_chain": [*source_chain_prefix, _expected_source(market)],
            "as_of": None,
            "is_cached": True,
            "rows": [],
            "candles": [],
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
        "granularity": "daily",
        "interval": "1d",
        "currency": _currency_for_market(market),
        "timezone": _timezone_for_market(market),
        "source": source or _expected_source(market),
        "source_type": "db_cache",
        "source_chain": [*source_chain_prefix, source or _expected_source(market)],
        "as_of": display_rows[-1]["date"] if display_rows else None,
        "is_cached": True,
        "rows": display_rows,
        "candles": [
            {
                "timestamp": row["date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume"),
            }
            for row in display_rows
        ],
        "current_price": _first_number(raw, "current_price", "currentPrice") or (
            display_rows[-1]["close"] if display_rows else None
        ),
        "support_level": _first_number(raw, "support_level", "supportLevel"),
        "resistance_level": _first_number(raw, "resistance_level", "resistanceLevel"),
        "data_gap_reason": data_gap_reason,
    }


def build_report_kline_snapshot_payload(
    db_manager: Any,
    record_id: str,
    range_value: str,
) -> Dict[str, Any]:
    """Build a report-bound K-line snapshot, allowing analysis-time providers."""
    if range_value not in KLINE_RANGE_ROWS and range_value not in INTRADAY_RANGE_CONFIG:
        range_value = "3m"
    record, raw, symbol, market, instrument_type = _history_parts(db_manager, record_id)
    if range_value in INTRADAY_RANGE_CONFIG:
        return _build_intraday_kline(record, raw, symbol, market, instrument_type, range_value)
    return _build_daily_kline(db_manager, record, raw, symbol, market, instrument_type, range_value)


def persist_report_kline_snapshots(
    db_manager: Any,
    history_id: int,
    ranges: Optional[List[str]] = None,
) -> int:
    """Persist K-line snapshots for one history record after analysis save."""
    saved = 0
    for range_value in (ranges or ["1d", "5d", "1w", "1m", "3m", "1y"]):
        try:
            payload = build_report_kline_snapshot_payload(db_manager, str(history_id), range_value)
        except Exception:
            try:
                record, _raw, symbol, market, instrument_type = _history_parts(db_manager, str(history_id))
                if range_value in INTRADAY_RANGE_CONFIG:
                    payload = _snapshot_missing_intraday_payload(
                        record, symbol, market, instrument_type, range_value
                    )
                else:
                    payload = {
                        "history_id": history_id,
                        "symbol": symbol,
                        "market": market,
                        "instrument_type": instrument_type,
                        "range": range_value,
                        "granularity": "daily",
                        "interval": "1d",
                        "currency": _currency_for_market(market),
                        "timezone": _timezone_for_market(market),
                        "source": _expected_source(market),
                        "source_type": "data_gap",
                        "source_chain": [_expected_source(market)],
                        "as_of": None,
                        "is_cached": True,
                        "rows": [],
                        "candles": [],
                        "current_price": None,
                        "support_level": None,
                        "resistance_level": None,
                        "data_gap_reason": "snapshot_build_exception",
                    }
                payload["data_gap_reason"] = payload.get("data_gap_reason") or "snapshot_build_exception"
            except Exception:
                continue
        saved += int(db_manager.upsert_analysis_kline_snapshot(payload) or 0)
    return saved


def build_history_kline(db_manager: Any, record_id: str, range_value: str = "3m") -> Dict[str, Any]:
    """Build a read-only K-line API payload from persisted report snapshots."""
    if range_value not in KLINE_RANGE_ROWS and range_value not in INTRADAY_RANGE_CONFIG:
        range_value = "3m"

    record, raw, symbol, market, instrument_type = _history_parts(db_manager, record_id)
    snapshot_loader = getattr(db_manager, "get_analysis_kline_snapshot", None)
    if callable(snapshot_loader):
        snapshot = snapshot_loader(getattr(record, "id", None), range_value)
        if isinstance(snapshot, dict):
            return snapshot

    if range_value in INTRADAY_RANGE_CONFIG:
        return _snapshot_missing_intraday_payload(record, symbol, market, instrument_type, range_value)

    return _build_daily_kline(
        db_manager,
        record,
        raw,
        symbol,
        market,
        instrument_type,
        range_value,
        legacy_fallback=True,
    )

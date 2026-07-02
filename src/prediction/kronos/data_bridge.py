# -*- coding: utf-8 -*-
"""Bridge backend OHLCV data into the Kronos data contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from src.core.trading_calendar import MARKET_EXCHANGE, MARKET_TIMEZONE
from src.prediction.kronos.data_contract import (
    MarketKlineRow,
    MarketKlineSeries,
    normalize_market,
)


HistoryLoader = Callable[..., tuple[pd.DataFrame, str]]


@dataclass(frozen=True)
class FutureTimestampResult:
    timestamps: list[pd.Timestamp]
    calendar_source: str
    fallback_used: bool = False


def load_market_kline_series(
    *,
    symbol: str,
    market: str,
    lookback: int,
    pred_len: int = 0,
    interval: str = "1d",
    max_context: int = 512,
    loader: Optional[HistoryLoader] = None,
    target_date: Optional[date] = None,
) -> MarketKlineSeries:
    normalized_market = normalize_market(market)
    required_rows = lookback + max(pred_len, 0)
    data_loader = loader or _default_history_loader
    df, source = data_loader(symbol, days=required_rows, target_date=target_date)
    if df is None or df.empty:
        raise ValueError("no backend OHLCV rows available")

    df = df.tail(required_rows).copy()
    rows = [_row_from_record(record) for record in df.to_dict("records")]
    timezone = MARKET_TIMEZONE[normalized_market]
    series = MarketKlineSeries(
        symbol=symbol,
        market=normalized_market,
        interval=interval,
        timezone=timezone,
        adjusted=_is_adjusted(normalized_market, source),
        source=source,
        currency="USD" if normalized_market == "us" else "TWD",
        rows=rows,
    )
    return series.validate(lookback=lookback, max_context=max_context)


def generate_future_daily_timestamps(
    last_timestamp: datetime | date,
    market: str,
    pred_len: int,
) -> list[pd.Timestamp]:
    return generate_future_daily_timestamp_info(last_timestamp, market, pred_len).timestamps


def generate_future_daily_timestamp_info(
    last_timestamp: datetime | date,
    market: str,
    pred_len: int,
) -> FutureTimestampResult:
    normalized_market = normalize_market(market)
    if pred_len <= 0:
        return FutureTimestampResult([], "none")

    try:
        import exchange_calendars as xcals

        exchange = MARKET_EXCHANGE[normalized_market]
        calendar = xcals.get_calendar(exchange)
        return FutureTimestampResult(
            _calendar_future_days(calendar, last_timestamp, normalized_market, pred_len),
            f"exchange-calendars:{exchange}",
            False,
        )
    except Exception:
        return FutureTimestampResult(
            _weekday_future_days(last_timestamp, normalized_market, pred_len),
            "weekday_fallback",
            True,
        )


def _default_history_loader(symbol: str, days: int, target_date: Optional[date] = None):
    from src.services.history_loader import load_history_df

    return load_history_df(symbol, days=days, target_date=target_date)


def _row_from_record(record: dict) -> MarketKlineRow:
    timestamp = record.get("timestamp", record.get("date"))
    return MarketKlineRow(
        timestamp=timestamp,
        open=record["open"],
        high=record["high"],
        low=record["low"],
        close=record["close"],
        volume=record.get("volume"),
        amount=record.get("amount"),
    )


def _is_adjusted(market: str, source: str) -> bool:
    source_name = (source or "").lower()
    if "yfinance" in source_name:
        return True
    if "finmind" in source_name:
        return False
    return market == "us"


def _calendar_future_days(calendar, last_timestamp: datetime | date, market: str, pred_len: int) -> list[pd.Timestamp]:
    result: list[pd.Timestamp] = []
    cursor = pd.Timestamp(last_timestamp).date() + timedelta(days=1)
    while len(result) < pred_len:
        if calendar.is_session(pd.Timestamp(cursor)):
            result.append(_market_timestamp(cursor, market))
        cursor += timedelta(days=1)
    return result


def _weekday_future_days(last_timestamp: datetime | date, market: str, pred_len: int) -> list[pd.Timestamp]:
    result: list[pd.Timestamp] = []
    cursor = pd.Timestamp(last_timestamp).date() + timedelta(days=1)
    while len(result) < pred_len:
        if cursor.weekday() < 5:
            result.append(_market_timestamp(cursor, market))
        cursor += timedelta(days=1)
    return result


def _market_timestamp(day: date, market: str) -> pd.Timestamp:
    tz = ZoneInfo(MARKET_TIMEZONE[market])
    return pd.Timestamp(datetime.combine(day, time.min, tzinfo=tz))

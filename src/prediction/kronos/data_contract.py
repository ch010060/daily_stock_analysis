# -*- coding: utf-8 -*-
"""Market K-line data contract for Kronos input."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# Absolute tolerance for the OHLC invariant check. Adjusted-price sources
# (e.g. yfinance auto_adjust) compute open/high/low/close as independent
# floating-point multiplications by a cumulative adjustment factor, which
# occasionally leaves a mathematically-equal pair (e.g. high == close) off
# by ~1e-13. This is ~1e7x larger than that observed noise floor while
# staying far below any real invariant violation (at least cent-scale).
_OHLC_EPSILON = 1e-6


def normalize_market(market: str) -> str:
    value = (market or "").strip().lower()
    if value in {"us", "usa", "nyse", "nasdaq"}:
        return "us"
    if value in {"tw", "taiwan", "tpe", "xtai"}:
        return "tw"
    raise ValueError(f"unsupported market: {market}")


@dataclass
class MarketKlineRow:
    timestamp: object
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    amount: Optional[float] = None


@dataclass
class MarketKlineSeries:
    symbol: str
    market: str
    interval: str
    timezone: str
    adjusted: bool
    source: str
    rows: list[MarketKlineRow]
    currency: Optional[str] = None

    def validate(
        self,
        *,
        lookback: int,
        max_context: int,
        pred_len: int = 0,
        holdout: bool = False,
    ) -> "MarketKlineSeries":
        if self.interval != "1d":
            raise ValueError("Phase 24.1 supports daily interval only")
        if lookback <= 0 or pred_len < 0:
            raise ValueError("lookback must be positive and pred_len cannot be negative")
        if lookback > max_context:
            raise ValueError("lookback exceeds max_context")

        self.market = normalize_market(self.market)
        normalized: list[MarketKlineRow] = []
        for row in self.rows:
            normalized.append(_normalize_row(row))

        normalized.sort(key=lambda row: pd.Timestamp(row.timestamp))
        deduped_by_time: dict[pd.Timestamp, MarketKlineRow] = {}
        for row in normalized:
            deduped_by_time[pd.Timestamp(row.timestamp)] = row
        self.rows = [deduped_by_time[key] for key in sorted(deduped_by_time)]

        required = lookback + pred_len if holdout else lookback
        if len(self.rows) < required:
            raise ValueError("insufficient OHLCV rows")
        return self

    def to_kronos_dataframe(self, *, input_mode: str = "ohlcva") -> pd.DataFrame:
        if input_mode not in {"ohlc_only", "ohlcv", "ohlcva"}:
            raise ValueError(f"unsupported input_mode: {input_mode}")
        records = []
        include_volume = input_mode in {"ohlcv", "ohlcva"} and any(row.volume is not None for row in self.rows)
        include_amount = input_mode == "ohlcva" and any(row.amount is not None for row in self.rows)
        for row in self.rows:
            record = {
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
            }
            if include_volume:
                record["volume"] = 0.0 if row.volume is None else row.volume
            if include_amount:
                record["amount"] = 0.0 if row.amount is None else row.amount
            records.append(record)
        return pd.DataFrame.from_records(records)


def _normalize_row(row: MarketKlineRow) -> MarketKlineRow:
    timestamp = pd.Timestamp(row.timestamp)
    open_value = _positive_float(row.open, "open")
    high_value = _positive_float(row.high, "high")
    low_value = _positive_float(row.low, "low")
    close_value = _positive_float(row.close, "close")
    volume = _non_negative_optional_float(row.volume, "volume")
    amount = _non_negative_optional_float(row.amount, "amount")

    if high_value < max(open_value, close_value, low_value) - _OHLC_EPSILON:
        raise ValueError("invalid OHLC invariant: high")
    if low_value > min(open_value, close_value, high_value) + _OHLC_EPSILON:
        raise ValueError("invalid OHLC invariant: low")

    return MarketKlineRow(
        timestamp=timestamp,
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=volume,
        amount=amount,
    )


def _positive_float(value: object, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _non_negative_optional_float(value: object, name: str) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result

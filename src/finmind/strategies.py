# -*- coding: utf-8 -*-
"""
FinMind backtesting strategies — Phase 8E.

Each strategy is a pure function that receives historical data and a config,
and returns a list of signal dicts.

Signal shape: {signal_date: str, action: 'buy' | 'sell'}

Execution rules (enforced by BacktestEngine, not here):
  - Signal on date T is executed on T+1 (next trading date).
  - Strategies must NOT use any data from dates after the signal_date.
  - No short selling, no leverage.
  - Missing data means hold current position (no crash).

Available strategies:
  buy_and_hold                — single buy at first date; hold to end
  sma_crossover               — fast/slow SMA crossover; T+1 execution
  monthly_revenue_momentum    — YoY revenue >= threshold → in market
  institutional_flow          — rolling foreign net buy → in market (optional v1)
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────

_STRATEGY_REGISTRY: Dict[str, Any] = {}


def register_strategy(name: str):
    def decorator(fn):
        _STRATEGY_REGISTRY[name] = fn
        return fn
    return decorator


def get_strategy_fn(name: str):
    """Return strategy function by name, or None if not found."""
    return _STRATEGY_REGISTRY.get(name)


def list_strategies() -> List[str]:
    """Return names of all registered strategies."""
    return list(_STRATEGY_REGISTRY.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Helper: SMA
# ──────────────────────────────────────────────────────────────────────────────

def _sma(values: List[float], period: int) -> Optional[float]:
    """Compute simple moving average of last `period` values."""
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / len(window)


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 1: Buy and Hold
# ──────────────────────────────────────────────────────────────────────────────

@register_strategy("buy_and_hold")
def strategy_buy_and_hold(
    price_rows: List[Dict],
    trading_dates: List[str],
    config: Any,
    **kwargs,
) -> List[Dict[str, str]]:
    """
    Buy on the first available trading date. Hold to end.

    Used as benchmark sanity strategy.
    Generates exactly one 'buy' signal.
    """
    if not trading_dates:
        return []
    return [{"signal_date": trading_dates[0], "action": "buy"}]


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 2: SMA Crossover
# ──────────────────────────────────────────────────────────────────────────────

@register_strategy("sma_crossover")
def strategy_sma_crossover(
    price_rows: List[Dict],
    trading_dates: List[str],
    config: Any,
    **kwargs,
) -> List[Dict[str, str]]:
    """
    Fast SMA > Slow SMA on date T → buy signal; execute on T+1.
    Fast SMA <= Slow SMA on date T → sell signal; execute on T+1.

    Signal is only emitted when the direction changes (not every day).
    Requires at least slow_period rows of price data before first signal.
    """
    fast_period = getattr(config, "sma_fast", 5)
    slow_period = getattr(config, "sma_slow", 20)

    if not trading_dates or not price_rows:
        return []

    close_by_date = {r["date"]: r.get("close") for r in price_rows if r.get("close")}
    closes: List[float] = []
    prev_signal: Optional[str] = None
    signals: List[Dict[str, str]] = []

    for date in trading_dates:
        close = close_by_date.get(date)
        if close is None:
            continue

        closes.append(close)

        fast_avg = _sma(closes, fast_period)
        slow_avg = _sma(closes, slow_period)

        if fast_avg is None or slow_avg is None:
            continue  # not enough history yet

        current = "buy" if fast_avg > slow_avg else "sell"

        if current != prev_signal:
            signals.append({"signal_date": date, "action": current})
            prev_signal = current

    return signals


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 3: Monthly Revenue Momentum
# ──────────────────────────────────────────────────────────────────────────────

def _compute_revenue_yoy_at(
    revenue_rows: List[Dict],
    as_of_date: str,
) -> Optional[float]:
    """
    Compute YoY revenue growth using only data available on or before as_of_date.

    Revenue rows must be sorted by date ascending.
    YoY = (current - prev_year_same_month) / prev_year_same_month * 100
    Requires at least 13 months of data.
    """
    available = [r for r in revenue_rows if r.get("date", "") <= as_of_date]
    if len(available) < 13:
        return None

    current = available[-1]
    prev_year = available[-13]

    c_rev = current.get("revenue")
    p_rev = prev_year.get("revenue")

    if c_rev is None or p_rev is None or p_rev == 0:
        return None

    try:
        return round((float(c_rev) - float(p_rev)) / float(p_rev) * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


@register_strategy("monthly_revenue_momentum")
def strategy_monthly_revenue_momentum(
    price_rows: List[Dict],
    trading_dates: List[str],
    config: Any,
    revenue_rows: Optional[List[Dict]] = None,
    **kwargs,
) -> List[Dict[str, str]]:
    """
    In market when YoY revenue >= threshold. Out otherwise.

    Uses only revenue data available before signal date (no lookahead).
    If revenue data is insufficient → hold (no signal change).
    """
    threshold = getattr(config, "revenue_yoy_threshold_pct", 10.0)

    if not trading_dates or not revenue_rows:
        return []

    prev_signal: Optional[str] = None
    signals: List[Dict[str, str]] = []

    for date in trading_dates:
        yoy = _compute_revenue_yoy_at(revenue_rows, date)

        if yoy is None:
            # Insufficient data: hold current position, no new signal
            continue

        current = "buy" if yoy >= threshold else "sell"

        if current != prev_signal:
            signals.append({"signal_date": date, "action": current})
            prev_signal = current

    return signals


# ──────────────────────────────────────────────────────────────────────────────
# Strategy 4: Institutional Flow (optional v1)
# ──────────────────────────────────────────────────────────────────────────────

def _rolling_foreign_net(
    institutional_rows: List[Dict],
    as_of_date: str,
    rolling_days: int,
) -> Optional[float]:
    """
    Compute rolling N-day total foreign investor net buy/sell,
    using only data available on or before as_of_date.
    """
    available = [
        r for r in institutional_rows
        if r.get("date", "") <= as_of_date
        and r.get("name") == "Foreign_Investor"
    ]
    if not available:
        return None

    window = available[-rolling_days:]
    total_net = 0.0
    for r in window:
        try:
            net = float(r.get("buy", 0) or 0) - float(r.get("sell", 0) or 0)
            total_net += net
        except (TypeError, ValueError):
            continue

    return total_net


@register_strategy("institutional_flow")
def strategy_institutional_flow(
    price_rows: List[Dict],
    trading_dates: List[str],
    config: Any,
    institutional_rows: Optional[List[Dict]] = None,
    **kwargs,
) -> List[Dict[str, str]]:
    """
    In market when rolling N-day foreign investor net buy > 0. Out otherwise.

    Uses only institutional data available before signal date (no lookahead).
    If data unavailable → hold (no signal change).
    """
    rolling_days = getattr(config, "institutional_rolling_days", 5)

    if not trading_dates or not institutional_rows:
        return []

    prev_signal: Optional[str] = None
    signals: List[Dict[str, str]] = []

    for date in trading_dates:
        net = _rolling_foreign_net(institutional_rows, date, rolling_days)

        if net is None:
            continue  # insufficient data, hold

        current = "buy" if net > 0 else "sell"

        if current != prev_signal:
            signals.append({"signal_date": date, "action": current})
            prev_signal = current

    return signals

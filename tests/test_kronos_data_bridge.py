# -*- coding: utf-8 -*-

from datetime import date, timedelta
import inspect

import pandas as pd

from src.prediction.kronos import data_bridge
from src.prediction.kronos.data_bridge import (
    generate_future_daily_timestamps,
    load_market_kline_series,
)


def _df(count: int) -> pd.DataFrame:
    start = date(2026, 1, 5)
    return pd.DataFrame(
        {
            "date": [start + timedelta(days=i) for i in range(count)],
            "open": [100.0 + i for i in range(count)],
            "high": [102.0 + i for i in range(count)],
            "low": [99.0 + i for i in range(count)],
            "close": [101.0 + i for i in range(count)],
            "volume": [1000 + i for i in range(count)],
            "amount": [100000 + i for i in range(count)],
        }
    )


def test_bridge_builds_series_and_requests_enough_rows() -> None:
    calls: list[int] = []

    def loader(symbol: str, days: int, target_date=None):
        calls.append(days)
        return _df(days), "YfinanceFetcher"

    series = load_market_kline_series(
        symbol="AAPL",
        market="us",
        lookback=4,
        pred_len=2,
        loader=loader,
    )

    assert calls == [6]
    assert series.symbol == "AAPL"
    assert series.market == "us"
    assert series.adjusted is True
    assert series.source == "YfinanceFetcher"
    assert series.currency == "USD"
    assert series.rows[-1].amount == 100005


def test_bridge_does_not_use_report_display_snapshots() -> None:
    source = inspect.getsource(data_bridge)

    assert "kline_snapshot" not in source
    assert "analysis_kline_snapshots" not in source
    assert "build_history_kline" not in source


def test_future_timestamps_skip_weekends_for_us_and_tw() -> None:
    for market in ("us", "tw"):
        stamps = generate_future_daily_timestamps(date(2026, 7, 10), market, pred_len=3)

        assert len(stamps) == 3
        assert [stamp.date().weekday() for stamp in stamps] == [0, 1, 2]
        assert stamps == sorted(stamps)


def test_is_adjusted_resolves_by_source_not_hardcoded_market() -> None:
    from src.prediction.kronos.data_bridge import _is_adjusted

    assert _is_adjusted("tw", "TaiwanFinMindFetcher") is False
    assert _is_adjusted("tw", "yfinance_tw_adjusted") is True
    assert _is_adjusted("us", "YfinanceFetcher") is True
    assert _is_adjusted("tw", "some_other_source") is False

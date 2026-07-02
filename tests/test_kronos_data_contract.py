# -*- coding: utf-8 -*-

from datetime import date, timedelta

import pytest

from src.prediction.kronos.data_contract import MarketKlineRow, MarketKlineSeries


def _rows(count: int, start: date = date(2026, 1, 5)) -> list[MarketKlineRow]:
    return [
        MarketKlineRow(
            timestamp=start + timedelta(days=i),
            open=100.0 + i,
            high=102.0 + i,
            low=99.0 + i,
            close=101.0 + i,
            volume=1000 + i,
            amount=100000 + i,
        )
        for i in range(count)
    ]


def test_valid_us_series_converts_to_kronos_dataframe() -> None:
    series = MarketKlineSeries(
        symbol="AAPL",
        market="US",
        interval="1d",
        timezone="America/New_York",
        adjusted=True,
        source="YfinanceFetcher",
        currency="USD",
        rows=_rows(5),
    ).validate(lookback=5, max_context=512)

    df = series.to_kronos_dataframe()

    assert series.market == "us"
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "amount"]
    assert len(df) == 5


def test_valid_tw_series_converts_to_kronos_dataframe() -> None:
    series = MarketKlineSeries(
        symbol="2330",
        market="tw",
        interval="1d",
        timezone="Asia/Taipei",
        adjusted=False,
        source="TaiwanFinMindFetcher",
        currency="TWD",
        rows=_rows(3),
    ).validate(lookback=3, max_context=512)

    assert series.market == "tw"
    assert series.to_kronos_dataframe()["close"].tolist() == [101.0, 102.0, 103.0]


def test_duplicate_timestamps_keep_last_row_deterministically() -> None:
    rows = _rows(3)
    rows.append(MarketKlineRow(timestamp=rows[1].timestamp, open=50, high=55, low=49, close=54))

    series = MarketKlineSeries(
        symbol="AAPL",
        market="us",
        interval="1d",
        timezone="America/New_York",
        adjusted=True,
        source="fixture",
        rows=rows,
    ).validate(lookback=3, max_context=512)

    assert [row.close for row in series.rows] == [101.0, 54.0, 103.0]


@pytest.mark.parametrize(
    "row_update",
    [
        {"high": 99.0},
        {"low": 102.0},
        {"volume": -1.0},
        {"amount": -1.0},
    ],
)
def test_invalid_rows_fail_validation(row_update: dict[str, float]) -> None:
    rows = _rows(3)
    rows[1] = MarketKlineRow(**{**rows[1].__dict__, **row_update})

    with pytest.raises(ValueError):
        MarketKlineSeries(
            symbol="AAPL",
            market="us",
            interval="1d",
            timezone="America/New_York",
            adjusted=True,
            source="fixture",
            rows=rows,
        ).validate(lookback=3, max_context=512)


def test_floating_point_noise_within_epsilon_does_not_fail_validation() -> None:
    rows = _rows(3)
    noisy_high = rows[1].close - 5e-14
    rows[1] = MarketKlineRow(**{**rows[1].__dict__, "high": noisy_high})

    series = MarketKlineSeries(
        symbol="AAPL",
        market="us",
        interval="1d",
        timezone="America/New_York",
        adjusted=True,
        source="fixture",
        rows=rows,
    ).validate(lookback=3, max_context=512)

    assert len(series.rows) == 3


def test_insufficient_rows_lookback_and_interval_fail() -> None:
    base = dict(
        symbol="AAPL",
        market="us",
        timezone="America/New_York",
        adjusted=True,
        source="fixture",
        rows=_rows(2),
    )

    with pytest.raises(ValueError):
        MarketKlineSeries(interval="1d", **base).validate(lookback=3, max_context=512)
    with pytest.raises(ValueError):
        MarketKlineSeries(interval="1d", **base).validate(lookback=513, max_context=512)
    with pytest.raises(ValueError):
        MarketKlineSeries(interval="1h", **base).validate(lookback=2, max_context=512)

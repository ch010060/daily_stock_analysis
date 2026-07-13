from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from src.services.market_structure_levels import calculate_market_structure_levels


def _frame(*, broken: bool = False) -> pd.DataFrame:
    start = date(2025, 1, 2)
    rows = []
    for index in range(36):
        close = 100.0
        low = 98.0
        high = 102.0
        if index == 8:
            low, close = 90.0, 94.0
        if index == 16:
            low, close = 90.3, 94.5
        if index == 11:
            high, close = 110.0, 106.0
        if index == 22:
            high, close = 110.4, 106.5
        if broken and index >= 32:
            low, high, close = 87.0, 89.0, 88.0
        rows.append({
            "date": start + timedelta(days=index),
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1_000_000 + index,
        })
    return pd.DataFrame(rows)


def test_confirmed_double_bottom_and_top_are_clustered_after_confirmation() -> None:
    frame = _frame()
    before_second_confirmation = calculate_market_structure_levels(frame, as_of=frame.iloc[18]["date"])
    after_confirmation = calculate_market_structure_levels(frame, as_of=frame.iloc[29]["date"])

    assert not any(level["touch_count"] == 2 for level in before_second_confirmation["support_levels"])
    support = next(level for level in after_confirmation["support_levels"] if level["touch_count"] == 2)
    resistance = next(level for level in after_confirmation["resistance_levels"] if level["touch_count"] == 2)
    assert support["price"] < frame.iloc[29]["close"]
    assert resistance["price"] > frame.iloc[29]["close"]
    assert support["confirmed_at"] == frame.iloc[19]["date"].isoformat()
    assert resistance["confirmed_at"] == frame.iloc[25]["date"].isoformat()


def test_future_rows_cannot_change_same_as_of_payload() -> None:
    frame = _frame()
    as_of = frame.iloc[29]["date"]
    prefix = calculate_market_structure_levels(frame.iloc[:30], as_of=as_of)
    longer = calculate_market_structure_levels(frame, as_of=as_of)

    assert json.dumps(prefix, sort_keys=True) == json.dumps(longer, sort_keys=True)


def test_confirmed_broken_support_is_diagnostic_not_active() -> None:
    result = calculate_market_structure_levels(_frame(broken=True))
    double_bottom = next(level for level in result["support_levels"] if level["touch_count"] == 2)

    assert double_bottom["status"] == "broken"


def test_sparse_history_emits_no_fabricated_levels() -> None:
    result = calculate_market_structure_levels(_frame().iloc[:20])

    assert result["support_levels"] == []
    assert result["resistance_levels"] == []


def test_old_untouched_level_becomes_stale() -> None:
    frame = _frame()
    tail = []
    last_date = frame.iloc[-1]["date"]
    for index in range(70):
        tail.append({
            "date": last_date + timedelta(days=index + 1),
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 2_000_000 + index,
        })
    result = calculate_market_structure_levels(pd.concat([frame, pd.DataFrame(tail)]))

    double_bottom = next(level for level in result["support_levels"] if level["touch_count"] == 2)
    assert double_bottom["status"] == "stale"


def test_repeated_calculation_is_byte_deterministic() -> None:
    first = calculate_market_structure_levels(_frame())
    second = calculate_market_structure_levels(_frame())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

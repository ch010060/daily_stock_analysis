"""Pure causal market-structure levels from an as-of-limited OHLCV prefix."""

from __future__ import annotations

from datetime import date
from statistics import median
from typing import Any

import pandas as pd


MIN_HISTORY = 30
SOURCE_WINDOW = 120
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
ATR_PERIOD = 14
MIN_PROMINENCE_ATR = 0.75
CLUSTER_TOLERANCE_MIN = 0.005
CLUSTER_TOLERANCE_MAX = 0.02
CLUSTER_ATR_MULTIPLIER = 0.5
STALE_AFTER = 60
BREAK_BUFFER = 0.01
BREAK_CONFIRMATIONS = 2
SIDE_TOLERANCE = 0.005
MAX_ACTIVE_LEVELS = 3


def _iso(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def calculate_market_structure_levels(
    frame: pd.DataFrame,
    *,
    as_of: date | str | None = None,
) -> dict[str, Any]:
    """Return JSON-safe confirmed pivot clusters using no rows after ``as_of``."""
    if frame is None or frame.empty:
        return _empty()
    data = frame.loc[:, ["date", "high", "low", "close"]].copy()
    data["date"] = pd.to_datetime(data["date"])
    if as_of is not None:
        data = data[data["date"] <= pd.Timestamp(as_of)]
    data = data.sort_values("date").reset_index(drop=True)
    if data["date"].duplicated().any():
        raise ValueError("market-structure dates must be unique")
    if len(data) < MIN_HISTORY:
        return _empty()
    data = data.iloc[-SOURCE_WINDOW:].reset_index(drop=True)
    if data[["high", "low", "close"]].isna().any().any():
        raise ValueError("market-structure OHLC must be complete")

    true_ranges = []
    for index, row in data.iterrows():
        previous_close = data.iloc[index - 1]["close"] if index else row["close"]
        true_ranges.append(max(
            float(row["high"] - row["low"]),
            abs(float(row["high"] - previous_close)),
            abs(float(row["low"] - previous_close)),
        ))

    pivots = []
    for index in range(PIVOT_LEFT, len(data) - PIVOT_RIGHT):
        confirmation = index + PIVOT_RIGHT
        atr_start = max(0, confirmation - ATR_PERIOD + 1)
        atr = sum(true_ranges[atr_start:confirmation + 1]) / (confirmation - atr_start + 1)
        if atr <= 0:
            continue
        window = data.iloc[index - PIVOT_LEFT:index + PIVOT_RIGHT + 1]
        lows = [float(value) for value in window["low"]]
        highs = [float(value) for value in window["high"]]
        low = float(data.iloc[index]["low"])
        high = float(data.iloc[index]["high"])
        if low == min(lows) and lows.index(low) == PIVOT_LEFT:
            shoulder = min(max(lows[:PIVOT_LEFT]) - low, max(lows[PIVOT_LEFT + 1:]) - low)
            prominence = shoulder / atr
            if prominence >= MIN_PROMINENCE_ATR:
                pivots.append(_pivot(data, index, confirmation, "support", low, atr, prominence))
        if high == max(highs) and highs.index(high) == PIVOT_LEFT:
            shoulder = min(high - min(highs[:PIVOT_LEFT]), high - min(highs[PIVOT_LEFT + 1:]))
            prominence = shoulder / atr
            if prominence >= MIN_PROMINENCE_ATR:
                pivots.append(_pivot(data, index, confirmation, "resistance", high, atr, prominence))

    pivots.sort(key=lambda item: (item["confirmation_index"], item["kind"], item["price"]))
    clusters: list[dict[str, Any]] = []
    for pivot in pivots:
        tolerance = min(
            CLUSTER_TOLERANCE_MAX,
            max(CLUSTER_TOLERANCE_MIN, CLUSTER_ATR_MULTIPLIER * pivot["atr"] / pivot["price"]),
        )
        eligible = []
        for cluster_index, cluster in enumerate(clusters):
            if cluster["kind"] != pivot["kind"]:
                continue
            representative = median(member["price"] for member in cluster["members"])
            distance = abs(pivot["price"] - representative) / representative
            if distance <= tolerance:
                eligible.append((distance, cluster_index))
        if eligible:
            _, chosen = min(eligible)
            clusters[chosen]["members"].append(pivot)
        else:
            clusters.append({"kind": pivot["kind"], "members": [pivot]})

    current_close = float(data.iloc[-1]["close"])
    levels = [_serialize_cluster(cluster, data, current_close) for cluster in clusters]
    supports = sorted(
        (level for level in levels if level["kind"] == "support"),
        key=lambda level: _rank(level, current_close, support=True),
    )
    resistances = sorted(
        (level for level in levels if level["kind"] == "resistance"),
        key=lambda level: _rank(level, current_close, support=False),
    )
    return {
        "algorithm": "causal_swing_cluster_v1",
        "parameters": _parameters(),
        "support_levels": supports,
        "resistance_levels": resistances,
    }


def _pivot(
    data: pd.DataFrame,
    index: int,
    confirmation: int,
    kind: str,
    price: float,
    atr: float,
    prominence: float,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "price": price,
        "pivot_index": index,
        "confirmation_index": confirmation,
        "pivot_date": _iso(data.iloc[index]["date"]),
        "confirmed_at": _iso(data.iloc[confirmation]["date"]),
        "atr": atr,
        "prominence": prominence,
    }


def _serialize_cluster(cluster: dict[str, Any], data: pd.DataFrame, close: float) -> dict[str, Any]:
    members = cluster["members"]
    price = float(median(member["price"] for member in members))
    latest = max(member["confirmation_index"] for member in members)
    status = "active"
    if len(data) - 1 - latest > STALE_AFTER:
        status = "stale"
    else:
        closes = [float(value) for value in data.iloc[latest + 1:]["close"]]
        if cluster["kind"] == "support":
            broken = _has_consecutive(closes, lambda value: value < price * (1 - BREAK_BUFFER))
            wrong_side = price > close * (1 + SIDE_TOLERANCE)
        else:
            broken = _has_consecutive(closes, lambda value: value > price * (1 + BREAK_BUFFER))
            wrong_side = price < close * (1 - SIDE_TOLERANCE)
        if broken:
            status = "broken"
        elif wrong_side:
            status = "out_of_side"
    return {
        "price": round(price, 4),
        "kind": cluster["kind"],
        "confirmed_at": max(member["confirmed_at"] for member in members),
        "first_seen_at": min(member["pivot_date"] for member in members),
        "last_seen_at": max(member["pivot_date"] for member in members),
        "touch_count": len({member["pivot_date"] for member in members}),
        "prominence": round(max(member["prominence"] for member in members), 6),
        "source_window": SOURCE_WINDOW,
        "status": status,
    }


def _has_consecutive(values: list[float], predicate) -> bool:
    count = 0
    for value in values:
        count = count + 1 if predicate(value) else 0
        if count >= BREAK_CONFIRMATIONS:
            return True
    return False


def _rank(level: dict[str, Any], close: float, *, support: bool) -> tuple:
    return (
        -level["touch_count"],
        -date.fromisoformat(level["confirmed_at"]).toordinal(),
        -level["prominence"],
        abs(level["price"] - close),
        -level["price"] if support else level["price"],
    )


def _parameters() -> dict[str, Any]:
    return {
        "min_history": MIN_HISTORY,
        "source_window": SOURCE_WINDOW,
        "pivot_left": PIVOT_LEFT,
        "pivot_right": PIVOT_RIGHT,
        "atr_period": ATR_PERIOD,
        "min_prominence_atr": MIN_PROMINENCE_ATR,
        "cluster_tolerance_min": CLUSTER_TOLERANCE_MIN,
        "cluster_tolerance_max": CLUSTER_TOLERANCE_MAX,
        "cluster_atr_multiplier": CLUSTER_ATR_MULTIPLIER,
        "stale_after": STALE_AFTER,
        "break_buffer": BREAK_BUFFER,
        "break_confirmations": BREAK_CONFIRMATIONS,
        "side_tolerance": SIDE_TOLERANCE,
        "max_active_levels": MAX_ACTIVE_LEVELS,
    }


def _empty() -> dict[str, Any]:
    return {
        "algorithm": "causal_swing_cluster_v1",
        "parameters": _parameters(),
        "support_levels": [],
        "resistance_levels": [],
    }

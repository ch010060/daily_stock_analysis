"""Pure deterministic Taiwan daily technical-analysis snapshot builder."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo


ALGORITHM_VERSION = "tw_market_technical_v1"


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _market_state(raw: str) -> str:
    try:
        now = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"

    # Weekday/session-window arithmetic alone cannot distinguish a weekend or
    # exchange holiday (no new session to report on) from a trading day that
    # has simply closed for the day. Consult the trading calendar first;
    # fall through to the original window check only once a genuine trading
    # day is confirmed, so trading-day behavior is unchanged.
    try:
        from src.core.trading_calendar import MarketPhase, infer_market_phase

        phase = infer_market_phase("tw", current_time=now)
    except Exception:
        phase = None

    if phase is None or phase == MarketPhase.UNKNOWN:
        return "calendar_unavailable"
    if phase == MarketPhase.NON_TRADING:
        return "outside_session"

    minutes = now.hour * 60 + now.minute
    return "open_incomplete" if 540 <= minutes < 810 else "closed"


def _bars(rows: Iterable[Dict[str, Any]], cutoff: str) -> tuple[List[Dict[str, Any]], List[str]]:
    normalized: List[Dict[str, Any]] = []
    warnings: List[str] = []
    seen = set()
    for raw in rows:
        row_date = str(raw.get("date") or "")
        if row_date > cutoff:
            if "future_rows_dropped" not in warnings:
                warnings.append("future_rows_dropped")
            continue
        values = {key: _finite(raw.get(key)) for key in ("open", "high", "low", "close")}
        if not row_date or None in values.values() or min(values.values()) <= 0:
            continue
        if row_date in seen:
            warnings.append("duplicate_session")
            continue
        if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
            continue
        seen.add(row_date)
        normalized.append({"date": row_date, **values})
    normalized.sort(key=lambda row: row["date"])
    return normalized, warnings


def _values(rows: Iterable[Dict[str, Any]], cutoff: str) -> tuple[List[Dict[str, Any]], List[str]]:
    output = []
    warnings = []
    seen = set()
    for raw in rows:
        row_date = str(raw.get("date") or "")
        if row_date > cutoff:
            if "future_rows_dropped" not in warnings:
                warnings.append("future_rows_dropped")
            continue
        value = _finite(raw.get("value"))
        if not row_date or value is None or value < 0 or row_date in seen:
            continue
        seen.add(row_date)
        output.append({"date": row_date, "value": value})
    output.sort(key=lambda row: row["date"])
    return output, warnings


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)


def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _wilder(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 1 / period
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _rsi(closes: List[float], period: int = 14) -> List[float]:
    if len(closes) < 2:
        return [50.0] * len(closes)
    deltas = [0.0] + [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = _wilder([max(delta, 0.0) for delta in deltas], period)
    losses = _wilder([max(-delta, 0.0) for delta in deltas], period)
    output = []
    for gain, loss in zip(gains, losses):
        if loss == 0:
            output.append(100.0 if gain > 0 else 50.0)
        else:
            output.append(100 - 100 / (1 + gain / loss))
    return output


def _atr(rows: List[Dict[str, Any]], period: int = 14) -> List[float]:
    ranges = []
    for index, row in enumerate(rows):
        previous_close = rows[index - 1]["close"] if index else row["close"]
        ranges.append(max(
            row["high"] - row["low"],
            abs(row["high"] - previous_close),
            abs(row["low"] - previous_close),
        ))
    return _wilder(ranges, period)


def _moving_averages(closes: List[float]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    close = closes[-1]
    for period in (5, 10, 20, 60, 120):
        current = _mean(closes[-period:])
        previous = _mean(closes[-period - 1:-1]) if len(closes) > period else current
        distance = close - current
        output[f"ma{period}"] = {
            "value": current,
            "distance": distance,
            "distance_pct": distance / current * 100,
            "slope": current - previous,
            "direction": "up" if current > previous else "down" if current < previous else "flat",
            "position": "above" if close > current else "below" if close < current else "at",
        }
    short = [output[key]["value"] for key in ("ma5", "ma10", "ma20")]
    if short[0] > short[1] > short[2]:
        alignment = "bullish"
    elif short[0] < short[1] < short[2]:
        alignment = "bearish"
    else:
        alignment = "mixed"
    output["alignment"] = alignment  # type: ignore[assignment]
    return output


def _candle(rows: List[Dict[str, Any]], atr: float) -> Dict[str, Any]:
    row, previous = rows[-1], rows[-2]
    body = abs(row["close"] - row["open"])
    full_range = row["high"] - row["low"]
    upper = row["high"] - max(row["open"], row["close"])
    lower = min(row["open"], row["close"]) - row["low"]
    body_floor = max(body, full_range * 0.05, 1e-12)
    gap = "up" if row["low"] > previous["high"] else "down" if row["high"] < previous["low"] else "none"
    return {
        "body": body,
        "range": full_range,
        "upper_shadow": upper,
        "lower_shadow": lower,
        "doji": body <= full_range * 0.1,
        "long_lower_shadow": lower >= body_floor * 2 and lower >= full_range * 0.45,
        "long_upper_shadow": upper >= body_floor * 2 and upper >= full_range * 0.45,
        "gap": gap,
        "inside_bar": row["high"] < previous["high"] and row["low"] > previous["low"],
        "outside_bar": row["high"] > previous["high"] and row["low"] < previous["low"],
        "bullish_engulfing": previous["close"] < previous["open"] < row["close"] and row["open"] <= previous["close"],
        "bearish_engulfing": previous["close"] > previous["open"] > row["close"] and row["open"] >= previous["close"],
        "completed_close_reclaim": row["low"] < previous["low"] and row["close"] > previous["low"],
        "completed_close_breakdown": row["close"] < min(item["low"] for item in rows[-21:-1]),
        "atr_multiple": full_range / atr if atr else None,
    }


def _zones(rows: List[Dict[str, Any]], atr: float) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    close = rows[-1]["close"]
    pivots = []
    for index in range(3, len(rows) - 3):
        window = rows[index - 3:index + 4]
        if rows[index]["low"] == min(row["low"] for row in window):
            pivots.append(("support", rows[index]["low"], rows[index]["date"]))
        if rows[index]["high"] == max(row["high"] for row in window):
            pivots.append(("resistance", rows[index]["high"], rows[index]["date"]))
    pivots.extend([
        ("support", min(row["low"] for row in rows[-20:]), rows[-1]["date"]),
        ("resistance", max(row["high"] for row in rows[-20:]), rows[-1]["date"]),
    ])
    tolerance = max(atr * 0.25, close * 0.0025)

    def build(kind: str) -> List[Dict[str, Any]]:
        candidates = [pivot for pivot in pivots if pivot[0] == kind and ((pivot[1] <= close) if kind == "support" else (pivot[1] >= close))]
        candidates.sort(key=lambda pivot: abs(pivot[1] - close))
        output = []
        for _, level, as_of in candidates:
            if any(abs(level - item["level"]) <= tolerance for item in output):
                continue
            output.append({
                "lower": level - tolerance,
                "upper": level + tolerance,
                "level": level,
                "source": "delayed_pivot_or_rolling20",
                "as_of": as_of,
                "confirmation_state": "confirmed_close_history",
                "confidence": "medium",
                "invalidation_rule": "two_closes_beyond_zone",
            })
            if len(output) == 3:
                break
        return output

    return build("support"), build("resistance")


def _volume(rows: List[Dict[str, Any]], data_date: str) -> Dict[str, Any]:
    if len(rows) < 20 or not rows or rows[-1]["date"] != data_date:
        return {"state": "unavailable", "suppression_reason": "exact_date_or_20_sessions_missing"}
    latest = rows[-1]["value"]
    ma5, ma20 = _mean([row["value"] for row in rows[-5:]]), _mean([row["value"] for row in rows[-20:]])
    ratio = latest / ma20 if ma20 else None
    return {
        "state": "available",
        "value": latest,
        "ma5": ma5,
        "ma20": ma20,
        "ratio_to_ma20": ratio,
        "direction": "expansion" if ratio is not None and ratio >= 1.1 else "contraction" if ratio is not None and ratio <= 0.9 else "normal",
        "metric_kind": "traded_value",
        "unit": "TWD",
    }


def _source_status(
    key: str,
    metadata: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
    data_date: str,
    warnings: List[str],
    *,
    required: bool,
) -> Dict[str, Any]:
    item = dict(metadata.get(key) or {})
    exact = bool(rows and rows[-1]["date"] == data_date)
    item.update({
        "first_date": rows[0]["date"] if rows else None,
        "latest_date": rows[-1]["date"] if rows else None,
        "row_count": len(rows),
        "data_date": data_date,
        "as_of": rows[-1]["date"] if rows else None,
        "lag_sessions": 0 if exact else None,
        "status": "available" if exact else "unavailable" if required else "suppressed",
        "suppression_reason": None if exact else "exact_data_date_missing",
        "warnings": warnings,
        "terms_access_risk": item.get("terms_access_risk", "medium"),
    })
    return item


def _supporting_rows(
    rows: List[Dict[str, Any]],
    sessions: List[str],
    data_date: str,
) -> Dict[str, Any]:
    usable = [row for row in rows if str(row.get("date") or "") <= data_date]
    if not usable:
        return {"status": "suppressed", "lag_sessions": None, "rows": []}
    latest_date = max(str(row.get("date") or "") for row in usable)
    latest = [dict(row) for row in usable if str(row.get("date") or "") == latest_date]
    lag = (
        sessions.index(data_date) - sessions.index(latest_date)
        if data_date in sessions and latest_date in sessions
        else None
    )
    if lag is None or lag > 1:
        return {"status": "suppressed", "lag_sessions": lag, "as_of": latest_date, "rows": []}
    return {"status": "available" if lag == 0 else "lagged", "lag_sessions": lag, "as_of": latest_date, "rows": latest}


def _supporting_source_status(
    key: str,
    metadata: Dict[str, Dict[str, Any]],
    raw_rows: List[Dict[str, Any]],
    evidence: Dict[str, Any],
    data_date: str,
) -> Dict[str, Any]:
    usable = [row for row in raw_rows if str(row.get("date") or "") <= data_date]
    dates = sorted({str(row.get("date") or "") for row in usable if row.get("date")})
    item = dict(metadata.get(key) or {})
    item.update({
        "first_date": dates[0] if dates else None,
        "latest_date": dates[-1] if dates else None,
        "row_count": len(usable),
        "data_date": data_date,
        "as_of": evidence.get("as_of"),
        "lag_sessions": evidence.get("lag_sessions"),
        "status": evidence.get("status", "suppressed"),
        "suppression_reason": None if evidence.get("status") in {"available", "lagged"} else "older_than_one_session_or_missing",
        "terms_access_risk": item.get("terms_access_risk", "medium"),
    })
    return item


def _index_analysis(rows: List[Dict[str, Any]], value_rows: List[Dict[str, Any]], data_date: str) -> Dict[str, Any]:
    closes = [row["close"] for row in rows]
    mas = _moving_averages(closes)
    alignment = mas.pop("alignment")
    rsi = _rsi(closes)
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26)]
    signal = _ema(dif, 9)
    histogram = [left - right for left, right in zip(dif, signal)]
    atr = _atr(rows)
    support, resistance = _zones(rows, atr[-1])
    # _zones() only emits support candidates with level <= close and re-anchors
    # its rolling-20 pivot to today's own low every session, so a zone
    # recalculated INCLUDING today can never be broken by today's own close
    # (level <= close implies zone.lower = level - tolerance < close, always).
    # prior_support_levels is computed from data BEFORE today, so a genuine
    # breakdown of an already-confirmed support can actually be detected.
    prior_rows = rows[:-1]
    prior_atr = _atr(prior_rows)
    prior_support, prior_resistance = _zones(prior_rows, prior_atr[-1])
    previous = rows[-2]
    latest = rows[-1]
    return {
        "latest_bar": latest,
        "previous_close": previous["close"],
        "change": latest["close"] - previous["close"],
        "change_pct": (latest["close"] - previous["close"]) / previous["close"] * 100,
        "moving_averages": mas,
        "ma_alignment": alignment,
        "momentum": {
            "rsi14": {"value": rsi[-1], "previous": rsi[-2], "direction": "improving" if rsi[-1] > rsi[-2] else "deteriorating" if rsi[-1] < rsi[-2] else "flat"},
            "macd": {
                "dif": dif[-1], "signal": signal[-1], "histogram": histogram[-1],
                "previous_histogram": histogram[-2],
                "direction": "improving" if histogram[-1] > histogram[-2] else "deteriorating" if histogram[-1] < histogram[-2] else "flat",
                "state": "bullish" if dif[-1] > signal[-1] else "bearish",
            },
        },
        "atr14": atr[-1],
        "candlestick": _candle(rows, atr[-1]),
        "support_levels": support,
        "resistance_levels": resistance,
        "prior_support_levels": prior_support,
        "prior_resistance_levels": prior_resistance,
        "volume_analysis": _volume(value_rows, data_date),
        "input_last_date": rows[-1]["date"],
    }


def _judgement(analysis: Dict[str, Any]) -> Dict[str, Any]:
    latest = analysis["latest_bar"]
    mas = analysis["moving_averages"]
    alignment = analysis["ma_alignment"]
    tested_support = _tested_support(analysis)
    invalidation = _support_zone_state(latest["close"], tested_support) == "broken_zone"
    confirmed = latest["close"] > mas["ma20"]["value"] and alignment == "bullish" and mas["ma20"]["slope"] > 0
    rebound = analysis["change"] > 0 and latest["close"] < mas["ma20"]["value"]
    if invalidation:
        category, rule_id, headline = "invalidation", "PRICE_SUPPORT_BREAKDOWN", "支撐失守，短線結構轉弱"
    elif confirmed:
        category, rule_id, headline = "confirmed_trend", "TREND_BULLISH_CONFIRMED", "多頭延續但仍需觀察動能"
    elif rebound:
        category, rule_id, headline = "unconfirmed_rebound", "TECHNICAL_REBOUND_UNCONFIRMED", "反彈中但未確認翻多"
    else:
        category, rule_id, headline = "contextual", "TREND_MIXED_CONTEXT", "短線整理，方向仍待確認"
    resistance = analysis["resistance_levels"][:1]
    confirmation_conditions = [
        {"rule_id": "CONFIRM_CLOSE_ABOVE_MA20", "text": "收盤站上 MA20 且短期均線轉為多頭排列。", "met": confirmed},
    ]
    invalidation_conditions = [
        {"rule_id": "INVALIDATE_SUPPORT_BREAK", "text": "收盤跌破最近確認支撐區。", "met": invalidation, "zone": tested_support},
    ]
    return {
        "category": category,
        "rule_id": rule_id,
        "headline": headline,
        "short_term_trend": "bullish" if alignment == "bullish" else "bearish" if alignment == "bearish" else "mixed",
        "medium_term_trend": "bullish" if latest["close"] > mas["ma60"]["value"] and latest["close"] > mas["ma120"]["value"] else "bearish",
        "rebound_status": "confirmed" if confirmed else "unconfirmed" if rebound else "none",
        "risk_level": "high" if invalidation else "medium",
        "evidence": [{"rule_id": rule_id, "facts": [f"close={latest['close']:.2f}", f"ma20={mas['ma20']['value']:.2f}"]}],
        "confirmation_conditions": confirmation_conditions,
        "invalidation_conditions": invalidation_conditions,
        "primary_resistance": resistance[0] if resistance else None,
    }


def _zone_text(zone: Dict[str, Any]) -> str:
    return f"{zone['lower']:,.0f}～{zone['upper']:,.0f} 點"


def _support_zone_state(close: float, zone: Optional[Dict[str, Any]]) -> str:
    """Three-state support-zone classification, evaluated against the zone's
    own lower/upper boundary rather than a proxy signal (e.g. a new trailing
    N-session closing low) that can diverge from the zone actually shown in
    the narrative. Boundaries are inclusive of the zone (state B)."""
    if not zone:
        return "unavailable"
    if close > zone["upper"]:
        return "above_zone"
    if close < zone["lower"]:
        return "broken_zone"
    return "testing_zone"


def _support_interaction_state(*, low: float, close: float, zone: Optional[Dict[str, Any]]) -> str:
    """Whether today's session actually entered the prior support zone,
    distinct from _support_zone_state()'s close-only read. A close above the
    zone's upper boundary does not by itself mean the zone was tested: the
    day's own low must also have reached it, otherwise the zone was simply
    never approached. Boundaries are inclusive of the zone (touched at
    low == upper; still inside at close == upper or close == lower)."""
    if not zone:
        return "unavailable"
    if close < zone["lower"]:
        return "broken_zone"
    if close <= zone["upper"]:
        return "closing_inside_zone"
    if low <= zone["upper"]:
        return "intraday_test_reclaimed"
    return "not_reached"


def _close_location_state(high: float, low: float, close: float) -> str:
    """Normalized intraday close-location classification, independent of the
    support-zone axis: whether a close near a support zone reflects buying
    support (close far from the low) or continued selling pressure (close at
    or near the low) cannot be inferred from the zone state alone."""
    daily_range = high - low
    if daily_range <= 1e-9:
        return "flat_range"
    location = min(1.0, max(0.0, (close - low) / daily_range))
    if location <= 0.15:
        return "near_low"
    if location < 0.60:
        return "partial_recovery"
    return "strong_recovery"


def _tested_support(analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select the nearest support zone confirmed BEFORE today's session.
    Falls back to support_levels only for snapshots persisted before
    prior_support_levels existed (legacy records); using the recalculated
    zone as the primary source would make a genuine breakdown of an
    already-confirmed support undetectable (see _index_analysis)."""
    zones = analysis.get("prior_support_levels")
    if zones is None:
        zones = analysis.get("support_levels") or []
    if not zones:
        return None
    low = analysis["latest_bar"]["low"]
    return min(zones, key=lambda zone: 0 if zone["lower"] <= low <= zone["upper"] else abs(zone["level"] - low))


def _market_context(snapshot: Dict[str, Any]) -> str:
    generated = str(snapshot.get("generated_at") or "")
    try:
        timestamp = datetime.fromisoformat(generated.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Taipei"))
        formatted = f"{timestamp.year} 年 {timestamp.month} 月 {timestamp.day} 日 {timestamp:%H:%M}"
    except ValueError:
        formatted = str(snapshot.get("data_date") or "資料時間未提供")
    state = {
        "open_incomplete": "台股交易中；分析僅採前一完整交易日",
        "closed": "台股已收盤",
        "outside_session": "非交易日；分析採最近完整交易日",
        "calendar_unavailable": "分析採最近完整交易日",
    }.get(str(snapshot.get("market_state") or ""), "市場狀態未確認")
    return f"資料時間：{formatted}（{state}）"


def _core_judgement(
    snapshot: Dict[str, Any],
    analysis: Dict[str, Any],
    support_state: str,
    support_text: str,
) -> Dict[str, Any]:
    mas = analysis["moving_averages"]
    candle = analysis["candlestick"]
    rsi = analysis["momentum"]["rsi14"]
    macd = analysis["momentum"]["macd"]
    short = (
        "bullish" if analysis["ma_alignment"] == "bullish" and all(mas[key]["position"] == "above" for key in ("ma5", "ma10"))
        else "bearish" if all(mas[key]["position"] == "below" for key in ("ma5", "ma10", "ma20"))
        else "mixed"
    )
    medium = (
        "bullish" if all(mas[key]["position"] == "above" for key in ("ma60", "ma120"))
        else "bearish" if all(mas[key]["position"] == "below" for key in ("ma60", "ma120"))
        else "mixed"
    )
    label = {
        ("bullish", "bullish"): "短多中多",
        ("bullish", "mixed"): "短多中性",
        ("bullish", "bearish"): "短多中空",
        ("bearish", "bullish"): "短空中多",
        ("bearish", "mixed"): "短空中性",
        ("bearish", "bearish"): "短空中空",
        ("mixed", "bullish"): "短線修復、中期偏多",
        ("mixed", "mixed"): "短中期結構分歧",
        ("mixed", "bearish"): "短線修復、中期偏空",
    }[(short, medium)]
    invalidated = support_state == "broken_zone" or snapshot.get("market_judgement", {}).get("category") == "invalidation"
    confirmed = (
        short == "bullish"
        and mas["ma5"]["slope"] > 0
        and rsi["value"] > 50
        and macd["direction"] == "improving"
    )
    rebound = analysis["change"] > 0 and mas["ma5"]["position"] == "below"
    lower_recovery = candle.get("range", 0) > 0 and candle.get("lower_shadow", 0) / candle["range"] >= 0.35
    if invalidated:
        summary = "原支撐失效，修正風險提高。"
    elif confirmed:
        summary = "短線反彈確認度提高，但仍需觀察後續量價延續。"
    elif rebound:
        summary = "出現技術性反彈，但短期均線與動能尚未確認止跌。"
    elif lower_recovery and short == "bearish":
        summary = "低檔出現承接，但尚未確認止跌。"
    elif short == "bearish" and support_state == "testing_zone":
        summary = f"短線持續下探，指數已進入 {support_text}支撐區並正接受測試，若跌破區間下緣，修正風險將進一步提高。"
    elif short == "bearish":
        summary = "短線仍在修正，中期結構是否延續取決於支撐能否守住。"
    else:
        summary = "短線結構改善，但趨勢延續仍需收盤與動能共同確認。"
    return {
        "label": label,
        "summary": summary,
        "short_term": short,
        "medium_term": medium,
        "evidence_rule_ids": [str(snapshot.get("market_judgement", {}).get("rule_id") or "TREND_STRUCTURE_COMPOSITE")],
    }


def _supporting_context(snapshot: Dict[str, Any]) -> List[str]:
    evidence = snapshot.get("supporting_evidence") or {}
    output: List[str] = []
    institutional = evidence.get("institutional") or {}
    if institutional.get("status") in {"available", "lagged"}:
        rows = {str(row.get("name")): row for row in institutional.get("rows") or []}
        net = lambda name: _finite(rows.get(name, {}).get("buy")) - _finite(rows.get(name, {}).get("sell")) if _finite(rows.get(name, {}).get("buy")) is not None and _finite(rows.get(name, {}).get("sell")) is not None else None
        foreign, trust, total = net("Foreign_Investor"), net("Investment_Trust"), net("total")
        directions = []
        if foreign is not None:
            directions.append(f"外資偏{'買' if foreign > 0 else '賣'}")
        if trust is not None:
            directions.append(f"投信偏{'買' if trust > 0 else '賣'}")
        lag = "法人資料落後一個交易日；" if institutional.get("status") == "lagged" else ""
        if directions:
            split = foreign is not None and trust is not None and foreign * trust < 0
            conclusion = "法人方向分歧" if split else "法人方向一致"
            bias = "整體仍偏賣" if total is not None and total < 0 else "整體仍偏買" if total is not None and total > 0 else "整體方向有限"
            output.append(f"{lag}{'、'.join(directions)}，{conclusion}且{bias}，資金面僅作佐證，尚不足以改變技術面判斷。")
    margin = evidence.get("margin") or {}
    if margin.get("status") in {"available", "lagged"}:
        row = next((item for item in margin.get("rows") or [] if item.get("name") == "MarginPurchaseMoney"), None)
        if row:
            current, previous = _finite(row.get("TodayBalance")), _finite(row.get("YesBalance"))
            if current is not None and previous is not None:
                direction = "下降，代表槓桿部位有所收斂" if current < previous else "上升，代表槓桿部位增加"
                output.append(f"融資餘額{direction}，但不能單獨解讀為趨勢反轉訊號。")
    return output


def compose_tw_market_analysis_article(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Compose deterministic zh-TW analysis prose from a completed snapshot."""
    if not snapshot.get("analysis_ready") or not (snapshot.get("indices") or {}).get("TAIEX"):
        return {
            "status": "unavailable",
            "headline": "台股加權指數最新技術分析",
            "market_context": _market_context(snapshot),
            "session_summary": "TAIEX 完整日線資料不足，暫不產生市場分析文章。",
            "core_judgement": {},
            "trend_paragraphs": [],
            "price_action_paragraphs": [],
            "confirmation_paragraph": "",
            "supporting_context": [],
        }
    analysis = snapshot["indices"]["TAIEX"]
    bar = analysis["latest_bar"]
    mas = analysis["moving_averages"]
    rsi = analysis["momentum"]["rsi14"]
    macd = analysis["momentum"]["macd"]
    candle = analysis["candlestick"]
    volume = analysis.get("volume_analysis") or {"state": "unavailable"}
    support = _tested_support(analysis)
    support_text = _zone_text(support) if support else "最近確認支撐區"
    support_state = _support_zone_state(bar["close"], support)
    interaction_state = _support_interaction_state(low=bar["low"], close=bar["close"], zone=support)
    core = _core_judgement(snapshot, analysis, support_state, support_text)

    value_summary = ""
    if volume.get("state") == "available":
        value_summary = f"，TWSE 股票成交金額約 {volume['value'] / 1_000_000_000_000:.2f} 兆元"
    session_summary = (
        f"最新完整交易日為 {bar['date']}，加權指數收在 {bar['close']:,.2f} 點，"
        f"{'上漲' if analysis['change'] >= 0 else '下跌'} {abs(analysis['change']):,.2f} 點、"
        f"{'漲幅' if analysis['change_pct'] >= 0 else '跌幅'} {abs(analysis['change_pct']):.2f}%；"
        f"盤中最高 {bar['high']:,.2f} 點、最低 {bar['low']:,.2f} 點{value_summary}。"
    )

    short_text = {
        "bullish": "MA5、MA10 與 MA20 呈短期多頭結構",
        "bearish": "指數收盤仍低於 MA5、MA10 與 MA20，短期均線維持偏空結構",
        "mixed": "短期均線彼此交錯，價格尚未形成一致方向",
    }[core["short_term"]]
    medium_text = {
        "bullish": "指數仍高於 MA60 與 MA120，顯示這波走弱較接近中期多頭趨勢中的修正，而非長期空頭反轉",
        "bearish": "指數也低於 MA60 與 MA120，中期結構同步轉弱",
        "mixed": "指數在 MA60 與 MA120 之間，中期結構仍有分歧",
    }[core["medium_term"]]
    trend_structure = f"{short_text}；不過{medium_text}。" if core["short_term"] == "bearish" and core["medium_term"] == "bullish" else f"{short_text}；{medium_text}。"
    rsi_state = "超賣" if rsi["value"] < 30 else "中性偏弱" if rsi["value"] < 50 else "中性偏強" if rsi["value"] < 70 else "偏熱"
    rsi_move = "回升" if rsi["direction"] == "improving" else "下滑" if rsi["direction"] == "deteriorating" else "持平"
    macd_text = (
        "MACD 已轉為多方結構，柱狀體同步改善" if macd["state"] == "bullish" and macd["direction"] == "improving"
        else "MACD 仍處空方結構，但柱狀體正在收斂" if macd["state"] == "bearish" and macd["direction"] == "improving"
        else "MACD 仍處空方結構，柱狀體動能繼續轉弱" if macd["state"] == "bearish"
        else "MACD 位於多方結構，但柱狀體動能轉弱"
    )
    momentum = f"RSI14 為 {rsi['value']:.1f}，位於{rsi_state}區並較前一日{rsi_move}；{macd_text}，因此短線動能{'尚未完成翻多確認' if core['short_term'] != 'bullish' else '已有改善，但仍需後續價格確認'}。"

    recovered = bar["close"] - bar["low"]
    location_state = _close_location_state(bar["high"], bar["low"], bar["close"])
    if interaction_state == "broken_zone":
        recovery_text = f"收盤跌破 {support['lower']:,.0f} 點，原支撐區正式失效，修正風險進一步提高"
    elif interaction_state == "closing_inside_zone":
        if location_state == "near_low":
            recovery_text = (
                f"指數已進入 {support_text}支撐區，支撐正在接受測試；"
                "收盤貼近當日最低點，顯示賣壓持續至收盤。"
                "目前尚未跌破區間下緣，但承接力偏弱，尚未出現明確止跌訊號"
            )
        elif location_state == "flat_range":
            recovery_text = (
                f"指數已進入 {support_text}支撐區，支撐正在接受測試；"
                "目前尚未跌破區間下緣，承接力仍待確認"
            )
        elif location_state == "strong_recovery":
            recovery_text = (
                f"指數已進入 {support_text}支撐區，支撐正在接受測試；"
                f"收盤距盤中低點回升 {recovered:,.0f} 點，日 K 留下明顯下影線，顯示支撐附近已有承接，"
                "目前尚未跌破區間下緣，承接力仍待確認"
            )
        else:  # partial_recovery
            recovery_text = (
                f"指數已進入 {support_text}支撐區，支撐正在接受測試；"
                f"收盤自低點收回部分跌幅（約 {recovered:,.0f} 點），但回升幅度有限，"
                "支撐區內已有初步反應，尚不足以確認止跌"
            )
    elif interaction_state == "intraday_test_reclaimed":
        # The prior support zone was genuinely entered by today's own low and
        # the close reclaimed above it — unlike "not_reached" below, crediting
        # the zone for the recovery is factually supported here.
        if location_state == "near_low":
            recovery_text = f"指數盤中測試 {support_text}後回升，但收盤貼近當日最低點，追價力道保守，尚未形成明確止跌訊號"
        elif location_state == "flat_range":
            recovery_text = f"指數盤中測試 {support_text}"
        elif location_state == "strong_recovery":
            recovery_text = f"盤中下探 {support_text}後，收盤自低點回升 {recovered:,.0f} 點，日 K 留下明顯下影線，顯示支撐附近已有承接"
        else:  # partial_recovery
            recovery_text = f"指數盤中測試 {support_text}，收盤自低點收回部分跌幅（約 {recovered:,.0f} 點），但回升幅度有限"
    elif interaction_state == "not_reached":
        # The day's own low never entered the prior support zone (support
        # exists, but close > zone.upper AND low > zone.upper) — the article
        # must not claim the zone was tested; describe candle behavior on its
        # own terms instead.
        if location_state == "near_low":
            recovery_text = f"指數盤中最低來到 {bar['low']:,.2f} 點，尚未觸及 {support_text}；收盤貼近當日最低點，顯示賣壓持續至收盤，尚未形成明確止跌訊號"
        elif location_state == "flat_range":
            recovery_text = f"指數盤中維持在 {bar['low']:,.2f} 點附近整理，尚未觸及 {support_text}"
        elif location_state == "strong_recovery":
            recovery_text = f"指數盤中最低來到 {bar['low']:,.2f} 點，尚未觸及 {support_text}；收盤自低點回升 {recovered:,.0f} 點，日 K 留下明顯下影線，顯示賣壓於低點附近趨緩"
        else:  # partial_recovery
            recovery_text = f"指數盤中最低來到 {bar['low']:,.2f} 點，尚未觸及 {support_text}；收盤自低點收回部分跌幅（約 {recovered:,.0f} 點），但回升幅度有限"
    else:  # "unavailable" — no prior support zone to reference at all
        if location_state == "near_low":
            recovery_text = f"指數盤中最低來到 {bar['low']:,.2f} 點；收盤貼近當日最低點，顯示賣壓持續至收盤，尚未形成明確止跌訊號"
        elif location_state == "flat_range":
            recovery_text = f"指數盤中維持在 {bar['low']:,.2f} 點附近整理"
        elif location_state == "strong_recovery":
            recovery_text = f"指數盤中最低來到 {bar['low']:,.2f} 點；收盤自低點回升 {recovered:,.0f} 點，日 K 留下明顯下影線"
        else:  # partial_recovery
            recovery_text = f"指數盤中最低來到 {bar['low']:,.2f} 點；收盤自低點收回部分跌幅（約 {recovered:,.0f} 點），但回升幅度有限"
    volume_text = ""
    if volume.get("state") == "available":
        if volume.get("direction") == "expansion":
            volume_text = "；成交金額高於近 20 日均值，" + ("放量下跌顯示賣壓仍重" if analysis["change"] < 0 else "量價同步回升提高反彈可信度")
        elif volume.get("direction") == "contraction":
            volume_text = "；成交金額低於近 20 日均值，" + ("縮量反彈的確認度仍不足" if analysis["change"] > 0 else "賣壓雖收斂但尚未形成反轉訊號")
        else:
            volume_text = "；成交金額接近近 20 日均值，量能尚未提供額外止跌確認"
    price_action = f"{recovery_text}{volume_text}。"
    if mas["ma5"]["position"] == "below" and support_state != "broken_zone" and location_state not in {"near_low", "flat_range"}:
        price_action += "但收盤仍未站回短期均線，因此現階段只能視為低檔承接，不能直接判定修正結束。"

    resistance_band = f"MA10 至 MA20 約 {min(mas['ma10']['value'], mas['ma20']['value']):,.0f}～{max(mas['ma10']['value'], mas['ma20']['value']):,.0f} 點"
    rebound_confirmation = (
        f"接下來若收盤先站回 MA5（約 {mas['ma5']['value']:,.0f} 點），再收復 {resistance_band}；"
        f"若成交金額沒有明顯萎縮且動能同步改善，反彈確認度才會提高。"
    )
    if interaction_state == "broken_zone":
        # Current state already reports the break; the follow-up condition must
        # be a reclaim/next-support watch, not a repeat of the same break as if
        # it were still pending (that would contradict the price-action prose).
        confirmation = (
            f"跌破支撐區後，反彈確認須先重新站回 {support_text}；"
            "若持續無法收復，修正風險將維持在偏高水準。"
        )
    elif interaction_state == "closing_inside_zone":
        confirmation = (
            f"{rebound_confirmation}若後續收盤有效跌破 {support['lower']:,.0f} 點，才代表該支撐區正式失效。"
        )
    elif interaction_state == "intraday_test_reclaimed":
        # The zone was genuinely tested and reclaimed intraday, so framing a
        # further close below it as a failed catch is factually supported.
        confirmation = (
            f"{rebound_confirmation}若收盤跌破 {support_text}，代表本次低檔承接失敗，修正風險將進一步升高。"
        )
    elif interaction_state == "not_reached":
        # The zone exists but was never engaged today — the follow-up
        # condition is forward-looking (whether a future retest finds
        # buyers), not a restatement of a catch that has not happened yet.
        confirmation = (
            f"{rebound_confirmation}後續觀察指數回測 {support_text}時能否出現承接；"
            f"若收盤有效跌破 {support['lower']:,.0f} 點，才代表該支撐區正式失效。"
        )
    else:  # "unavailable" — no prior support zone to reference
        confirmation = rebound_confirmation
    result = {
        "status": "available",
        "headline": "台股加權指數最新技術分析",
        "market_context": _market_context(snapshot),
        "session_summary": session_summary,
        "core_judgement": core,
        "trend_paragraphs": [trend_structure, momentum],
        "price_action_paragraphs": [price_action],
        "confirmation_paragraph": confirmation,
        "supporting_context": _supporting_context(snapshot),
    }
    tpex = (snapshot.get("indices") or {}).get("TPEx")
    if tpex:
        relative = "弱於" if tpex["change_pct"] < analysis["change_pct"] else "強於"
        result["tpex_context"] = (
            f"櫃買指數當日{'上漲' if tpex['change_pct'] >= 0 else '下跌'} {abs(tpex['change_pct']):.2f}%，"
            f"表現{relative}加權指數，顯示中小型股{'承壓較重，市場廣度尚未確認止穩' if relative == '弱於' else '相對有撐，可作為反彈的輔助確認'}。"
        )
    return result


def _narrative(article: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility projection for persisted readers predating article support."""
    result = {
        "title": article["headline"],
        "opening_summary": article["session_summary"],
        "core_judgement": [article["core_judgement"]["label"], article["core_judgement"]["summary"]],
        "moving_average_analysis": article["trend_paragraphs"],
        "momentum_analysis": [],
        "price_action_analysis": article["price_action_paragraphs"],
        "volume_analysis": [],
        "support_resistance_analysis": [],
        "confirmation_conditions": [article["confirmation_paragraph"]],
        "invalidation_conditions": [],
        "supporting_context": article["supporting_context"],
    }
    if article.get("tpex_context"):
        result["tpex_breadth"] = [article["tpex_context"]]
    return result


def build_tw_market_analysis_snapshot(
    *,
    taiex_rows: List[Dict[str, Any]],
    tpex_rows: Optional[List[Dict[str, Any]]] = None,
    twse_traded_value_rows: Optional[List[Dict[str, Any]]] = None,
    tpex_traded_value_rows: Optional[List[Dict[str, Any]]] = None,
    institutional_rows: Optional[List[Dict[str, Any]]] = None,
    margin_rows: Optional[List[Dict[str, Any]]] = None,
    representatives: Optional[List[Dict[str, Any]]] = None,
    source_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    primary_data_date: str,
    generated_at: str,
    market_now: str,
) -> Dict[str, Any]:
    metadata = source_metadata or {}
    taiex, taiex_warnings = _bars(taiex_rows, primary_data_date)
    tpex, tpex_warnings = _bars(tpex_rows or [], primary_data_date)
    twse_value, twse_warnings = _values(twse_traded_value_rows or [], primary_data_date)
    tpex_value, tpex_value_warnings = _values(tpex_traded_value_rows or [], primary_data_date)
    state = _market_state(market_now)
    partial_date = market_now[:10] if state == "open_incomplete" else None
    taiex_exact = bool(taiex and taiex[-1]["date"] == primary_data_date and len(taiex) >= 120 and primary_data_date != partial_date)
    tpex_exact = bool(tpex and tpex[-1]["date"] == primary_data_date and len(tpex) >= 120 and primary_data_date != partial_date)
    source_status = {
        "TAIEX": _source_status("TAIEX", metadata, taiex, primary_data_date, taiex_warnings, required=True),
        "TPEx": _source_status("TPEx", metadata, tpex, primary_data_date, tpex_warnings, required=False),
        "twse_traded_value": _source_status("twse_traded_value", metadata, twse_value, primary_data_date, twse_warnings, required=False),
        "tpex_traded_value": _source_status("tpex_traded_value", metadata, tpex_value, primary_data_date, tpex_value_warnings, required=False),
    }
    sessions = [row["date"] for row in taiex]
    institutional_evidence = _supporting_rows(institutional_rows or [], sessions, primary_data_date)
    margin_evidence = _supporting_rows(margin_rows or [], sessions, primary_data_date)
    source_status["institutional"] = _supporting_source_status(
        "institutional", metadata, institutional_rows or [], institutional_evidence, primary_data_date
    )
    source_status["margin"] = _supporting_source_status(
        "margin", metadata, margin_rows or [], margin_evidence, primary_data_date
    )
    if not taiex_exact:
        source_status["TAIEX"]["status"] = "unavailable"
        source_status["TAIEX"]["suppression_reason"] = "current_partial_or_exact_120_session_history_missing"
    if not tpex_exact:
        source_status["TPEx"]["status"] = "suppressed"
        source_status["TPEx"]["suppression_reason"] = "current_partial_or_exact_120_session_history_missing"

    base = {
        "kind": "tw_market_analysis_snapshot",
        "schema_version": 1,
        "algorithm_version": ALGORITHM_VERSION,
        "data_date": primary_data_date,
        "generated_at": generated_at,
        "market_state": state,
        "analysis_ready": taiex_exact,
        "source_status": source_status,
        "suppression_reasons": {},
        "indices": {},
        "market_judgement": {},
        "narrative": {},
        "supporting_evidence": {},
    }
    if not taiex_exact:
        base["suppression_reasons"]["TAIEX"] = source_status["TAIEX"]["suppression_reason"]
        base["market_judgement"] = {
            "category": "data_failure",
            "rule_id": "DATA_TAIEX_UNAVAILABLE",
            "headline": "TAIEX 完整日線資料不足，技術分析暫停。",
            "confirmation_conditions": [],
            "invalidation_conditions": [],
        }
        return base

    taiex_analysis = _index_analysis(taiex, twse_value, primary_data_date)
    base["indices"]["TAIEX"] = taiex_analysis
    if tpex_exact:
        base["indices"]["TPEx"] = _index_analysis(tpex, tpex_value, primary_data_date)
    else:
        base["suppression_reasons"]["TPEx"] = source_status["TPEx"]["suppression_reason"]
    judgement = _judgement(taiex_analysis)
    base["market_judgement"] = judgement
    base["supporting_evidence"] = {
        "institutional": institutional_evidence,
        "margin": margin_evidence,
        "representatives": [
            dict(row) for row in (representatives or [])
            if str(row.get("data_date") or row.get("date") or "") <= primary_data_date
        ],
    }
    base["analysis_article"] = compose_tw_market_analysis_article(base)
    base["narrative"] = _narrative(base["analysis_article"])
    return base

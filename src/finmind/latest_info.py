# -*- coding: utf-8 -*-
"""
FinMind Latest Info / News Intelligence — Phase 8C.

Provides LatestInfoCollector which gathers structured events from FinMind
TW-market datasets and generates LLM-safe follow-up prompt recommendations.

Design principles:
  - FinMind datasets are the source of truth for numeric/event data.
  - SearXNG / Tavily may be accepted as secondary augmentation but are not
    called in Phase 8C v1 (search augmentation deferred to Phase 8G).
  - No LLM calls in this module.
  - No investment recommendations (no buy/sell instructions).
  - All guards are evaluated per-call via FinMindDatasetFetcher.
  - TaiwanStockNews tier is unknown; if unavailable, a data_unavailable event
    is emitted and collection continues without crash.
  - No CN / A-share datasets are called.

Event types:
  stock_news          — per-stock news headline from TaiwanStockNews
  market_news         — market-wide news (no specific symbol)
  monthly_revenue     — monthly revenue announcement from TaiwanStockMonthRevenue
  dividend            — dividend declaration from TaiwanStockDividend
  dividend_result     — ex-dividend result from TaiwanStockDividendResult
  price_volume_move   — abnormal price or volume from TaiwanStockPrice
  institutional_flow  — institutional buy/sell from TaiwanStockInstitutionalInvestorsBuySell
  margin_change       — margin/short-sale change from TaiwanStockMarginPurchaseShortSale
  data_unavailable    — dataset could not be fetched (tier / network / fixture)
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.finmind.fetcher import FinMindDatasetFetcher

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_REVENUE_HIGH_THRESHOLD = 20.0   # abs(YoY%) >= 20 → high severity
_REVENUE_MEDIUM_THRESHOLD = 10.0  # abs(YoY%) >= 10 → medium

_PRICE_HIGH_PCT = 0.05    # abs(spread/prev_close) >= 5% → high
_PRICE_MEDIUM_PCT = 0.03  # abs(spread/prev_close) >= 3% → medium

_VOLUME_SPIKE_MULTIPLIER = 2.0   # volume >= 2x N-day avg → high

_INSTITUTIONAL_HIGH = 1_000_000_000   # 1B TWD total net abs → high
_INSTITUTIONAL_MEDIUM = 100_000_000   # 100M TWD → medium

_CN_TERMS = frozenset({
    "A股", "上證", "上证", "深證", "深证", "創業板", "创业板",
    "科創50", "科创50", "A-share", "AShare",
})
_BUYSELL_TERMS = frozenset({
    "買進", "賣出", "買入", "卖出", "强烈推薦", "强力推荐",
})

_PROMPT_TEMPLATES = [
    "請只根據本次 FinMind 事件資料（截止 {end_date}），整理 {symbol_display} 最重要的三個變化，勿引用外部資料。",
    "請根據本次提供的法人買賣超與融資餘額資料，描述籌碼面動向，不得推薦買賣。",
    "請列出本次最新資訊中，哪些數據因資料視窗限制無法確認，需等待下一個交易日。",
    "請指出這份最新資訊有哪些資料源缺口（{missing_display}），不能作為強結論依據。",
    "本次資料來源為 FinMind，資料截止 {end_date}，請不要引用任何本次資料以外的即時或外部資訊。",
]


# ──────────────────────────────────────────────────────────────────────────────
# Event model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LatestInfoEvent:
    """A single structured event extracted from a FinMind dataset."""

    event_id: str
    event_type: str
    symbol: Optional[str]
    title: str
    summary: str
    event_date: Optional[str]
    source: str
    dataset: str
    data_id: Optional[str]
    severity: str            # high / medium / low / unknown
    confidence: str          # confirmed / estimated / unavailable
    source_url: Optional[str] = None
    raw_ref: Dict[str, Any] = field(default_factory=dict)
    data_freshness: Dict[str, Any] = field(default_factory=dict)
    follow_up_prompts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "title": self.title,
            "summary": self.summary,
            "event_date": self.event_date,
            "source": self.source,
            "dataset": self.dataset,
            "data_id": self.data_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "source_url": self.source_url,
            "raw_ref": self.raw_ref,
            "data_freshness": self.data_freshness,
            "follow_up_prompts": self.follow_up_prompts,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _event_id(dataset: str, symbol: Optional[str], date: Optional[str], index: int = 0) -> str:
    key = f"{dataset}:{symbol or '_'}:{date or '_'}:{index}"
    return "evt_" + hashlib.md5(key.encode()).hexdigest()[:12]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _contains_cn_terms(text: str) -> bool:
    return any(t in text for t in _CN_TERMS)


def _contains_buysell(text: str) -> bool:
    return any(t in text for t in _BUYSELL_TERMS)


# ──────────────────────────────────────────────────────────────────────────────
# Event extractors (pure functions — testable without collector)
# ──────────────────────────────────────────────────────────────────────────────

def extract_news_events(rows: List[Dict[str, Any]], symbol: Optional[str] = None) -> List[LatestInfoEvent]:
    """Extract stock_news / market_news events from TaiwanStockNews rows."""
    events = []
    for i, row in enumerate(rows):
        sid = row.get("stock_id") or symbol
        date = row.get("date")
        title = str(row.get("title", ""))
        summary = str(row.get("summary", ""))
        link = row.get("link")
        event_type = "stock_news" if sid else "market_news"
        events.append(LatestInfoEvent(
            event_id=_event_id("TaiwanStockNews", sid, date, i),
            event_type=event_type,
            symbol=sid,
            title=title,
            summary=summary[:300] if summary else title[:300],
            event_date=date,
            source="finmind",
            dataset="TaiwanStockNews",
            data_id=sid,
            severity="low",
            confidence="confirmed",
            source_url=str(link) if link else None,
            raw_ref={"title": title, "source": row.get("source")},
        ))
    return events


def extract_revenue_events(rows: List[Dict[str, Any]], symbol: str) -> List[LatestInfoEvent]:
    """Extract monthly_revenue events from TaiwanStockMonthRevenue rows.

    Attempts YoY comparison if prior-year row is available in rows.
    Severity: high >= 20% | medium >= 10% | low otherwise.
    """
    if not rows:
        return []

    # Sort descending by (revenue_year, revenue_month)
    def _sort_key(r: Dict[str, Any]):
        return (_safe_float(r.get("revenue_year")), _safe_float(r.get("revenue_month")))

    sorted_rows = sorted(rows, key=_sort_key, reverse=True)
    # Build lookup: (year, month) → revenue
    revenue_map: Dict[tuple, float] = {}
    for r in rows:
        yr = int(_safe_float(r.get("revenue_year")))
        mo = int(_safe_float(r.get("revenue_month")))
        rev = _safe_float(r.get("revenue"))
        revenue_map[(yr, mo)] = rev

    events = []
    # Only emit event for the most recent row
    latest = sorted_rows[0]
    yr = int(_safe_float(latest.get("revenue_year")))
    mo = int(_safe_float(latest.get("revenue_month")))
    revenue = _safe_float(latest.get("revenue"))
    date = latest.get("date")

    prev_revenue = revenue_map.get((yr - 1, mo))
    if prev_revenue and prev_revenue > 0:
        yoy_pct = (revenue - prev_revenue) / prev_revenue * 100.0
        if abs(yoy_pct) >= _REVENUE_HIGH_THRESHOLD:
            severity = "high"
        elif abs(yoy_pct) >= _REVENUE_MEDIUM_THRESHOLD:
            severity = "medium"
        else:
            severity = "low"
        confidence = "confirmed"
        yoy_str = f"{yoy_pct:+.1f}%"
        summary = (
            f"{symbol} {yr}年{mo}月營收 {revenue/1e8:.1f}億元，"
            f"YoY {yoy_str}。"
        )
    else:
        severity = "low"
        confidence = "estimated"
        yoy_str = "N/A (無前期對照)"
        summary = (
            f"{symbol} {yr}年{mo}月營收 {revenue/1e8:.1f}億元，"
            f"YoY {yoy_str}。"
        )

    events.append(LatestInfoEvent(
        event_id=_event_id("TaiwanStockMonthRevenue", symbol, date),
        event_type="monthly_revenue",
        symbol=symbol,
        title=f"{symbol} {yr}/{mo:02d} 月營收 {revenue/1e8:.1f}億 (YoY {yoy_str})",
        summary=summary,
        event_date=date,
        source="finmind",
        dataset="TaiwanStockMonthRevenue",
        data_id=symbol,
        severity=severity,
        confidence=confidence,
        raw_ref={"revenue": revenue, "revenue_year": yr, "revenue_month": mo, "yoy_pct": yoy_str},
    ))
    return events


def extract_dividend_events(rows: List[Dict[str, Any]], symbol: str, dataset: str = "TaiwanStockDividend") -> List[LatestInfoEvent]:
    """Extract dividend events from TaiwanStockDividend or TaiwanStockDividendResult rows."""
    events = []
    for i, row in enumerate(rows):
        date = row.get("date")
        cash = _safe_float(row.get("CashEarningsDistribution", 0))
        stock = _safe_float(row.get("StockEarningsDistribution", 0))
        pay_date = row.get("CashDividendPaymentDate", "")

        if dataset == "TaiwanStockDividendResult":
            before = _safe_float(row.get("before_price", 0))
            after = _safe_float(row.get("after_price", 0))
            amount = _safe_float(row.get("stock_and_cache_dividend", 0))
            title = f"{symbol} 除權息結果 前/後: {before:.1f}/{after:.1f} 元"
            summary = f"{symbol} 除權息日 {date}，前收 {before:.1f} 元，參考價 {after:.1f} 元，配息 {amount:.2f} 元。"
        else:
            parts = []
            if cash > 0:
                parts.append(f"現金股利 {cash:.2f} 元")
            if stock > 0:
                parts.append(f"股票股利 {stock:.2f} 元")
            desc = "、".join(parts) if parts else "配息資訊"
            title = f"{symbol} 配息公告：{desc}"
            pay_info = f"，發放日 {pay_date}" if pay_date else ""
            summary = f"{symbol} {date} 配息公告：{desc}{pay_info}。"

        events.append(LatestInfoEvent(
            event_id=_event_id(dataset, symbol, date, i),
            event_type="dividend",
            symbol=symbol,
            title=title,
            summary=summary,
            event_date=date,
            source="finmind",
            dataset=dataset,
            data_id=symbol,
            severity="medium",
            confidence="confirmed",
            raw_ref=dict(row),
        ))
    return events


def extract_price_events(rows: List[Dict[str, Any]], symbol: str) -> List[LatestInfoEvent]:
    """Extract price_volume_move events from TaiwanStockPrice rows.

    Uses spread field (= close - prev_close) for pct change.
    Volume spike: latest row volume vs average of prior rows.
    """
    if not rows:
        return []

    events = []
    sorted_rows = sorted(rows, key=lambda r: r.get("date", ""))
    latest = sorted_rows[-1]
    prior = sorted_rows[:-1]

    date = latest.get("date")
    close = _safe_float(latest.get("close"))
    spread = _safe_float(latest.get("spread"))
    volume = _safe_float(latest.get("Trading_Volume"))

    # Price change severity
    prev_close = close - spread if close != spread else close
    if prev_close > 0:
        pct = abs(spread) / prev_close
    else:
        pct = 0.0

    # Volume spike
    if prior:
        avg_vol = sum(_safe_float(r.get("Trading_Volume")) for r in prior) / len(prior)
        vol_spike = volume >= _VOLUME_SPIKE_MULTIPLIER * avg_vol if avg_vol > 0 else False
    else:
        avg_vol = 0.0
        vol_spike = False

    if pct >= _PRICE_HIGH_PCT or vol_spike:
        severity = "high"
    elif pct >= _PRICE_MEDIUM_PCT:
        severity = "medium"
    else:
        severity = "low"

    vol_note = f"，成交量 {volume/1e4:.0f}萬股" + (" (異常大量)" if vol_spike else "")
    spread_sign = "+" if spread >= 0 else ""
    title = f"{symbol} 量價動態 {date}：{spread_sign}{spread:.1f} ({spread_sign}{pct*100:.1f}%){vol_note}"
    summary = (
        f"{symbol} {date} 收盤 {close:.1f} 元，"
        f"漲跌 {spread_sign}{spread:.1f} 元 ({spread_sign}{pct*100:.1f}%){vol_note}。"
        f"資料來源：FinMind TaiwanStockPrice。"
    )

    events.append(LatestInfoEvent(
        event_id=_event_id("TaiwanStockPrice", symbol, date),
        event_type="price_volume_move",
        symbol=symbol,
        title=title,
        summary=summary,
        event_date=date,
        source="finmind",
        dataset="TaiwanStockPrice",
        data_id=symbol,
        severity=severity,
        confidence="confirmed",
        raw_ref={
            "close": close,
            "spread": spread,
            "pct_change": pct,
            "Trading_Volume": volume,
            "avg_prior_volume": avg_vol,
            "volume_spike": vol_spike,
        },
    ))
    return events


def extract_institutional_events(rows: List[Dict[str, Any]], symbol: str) -> List[LatestInfoEvent]:
    """Extract institutional_flow events from TaiwanStockInstitutionalInvestorsBuySell rows.

    Groups by date and aggregates net buy-sell per institution type.
    """
    if not rows:
        return []

    # Group by date, aggregate net per name
    by_date: Dict[str, Dict[str, float]] = {}
    for row in rows:
        date = row.get("date", "")
        name = row.get("name", "")
        net = _safe_float(row.get("buy")) - _safe_float(row.get("sell"))
        if date not in by_date:
            by_date[date] = {}
        by_date[date][name] = by_date[date].get(name, 0.0) + net

    events = []
    for date in sorted(by_date.keys(), reverse=True)[:1]:  # only latest date
        nets = by_date[date]
        total_net = sum(nets.values())
        if abs(total_net) >= _INSTITUTIONAL_HIGH:
            severity = "high"
        elif abs(total_net) >= _INSTITUTIONAL_MEDIUM:
            severity = "medium"
        else:
            severity = "low"

        direction = "買超" if total_net > 0 else "賣超"
        net_billions = total_net / 1e8
        detail_parts = [
            f"{k.replace('_', ' ')}: {v/1e8:+.1f}億"
            for k, v in sorted(nets.items())
        ]
        detail = "；".join(detail_parts)

        title = f"{symbol} 三大法人 {date}：合計{direction} {abs(net_billions):.1f}億元"
        summary = f"{symbol} {date} 法人動向：{detail}。合計{direction} {abs(net_billions):.1f}億元。"

        events.append(LatestInfoEvent(
            event_id=_event_id("TaiwanStockInstitutionalInvestorsBuySell", symbol, date),
            event_type="institutional_flow",
            symbol=symbol,
            title=title,
            summary=summary,
            event_date=date,
            source="finmind",
            dataset="TaiwanStockInstitutionalInvestorsBuySell",
            data_id=symbol,
            severity=severity,
            confidence="confirmed",
            raw_ref={"total_net": total_net, "by_name": nets},
        ))
    return events


def extract_margin_events(rows: List[Dict[str, Any]], symbol: str) -> List[LatestInfoEvent]:
    """Extract margin_change events from TaiwanStockMarginPurchaseShortSale rows."""
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda r: r.get("date", ""))
    latest = sorted_rows[-1]
    date = latest.get("date")

    margin_today = _safe_float(latest.get("MarginPurchaseTodayBalance"))
    margin_yest = _safe_float(latest.get("MarginPurchaseYesterdayBalance"))
    short_today = _safe_float(latest.get("ShortSaleTodayBalance"))
    short_yest = _safe_float(latest.get("ShortSaleYesterdayBalance"))

    margin_delta = margin_today - margin_yest
    short_delta = short_today - short_yest

    margin_sign = "+" if margin_delta >= 0 else ""
    short_sign = "+" if short_delta >= 0 else ""

    title = (
        f"{symbol} 融資融券 {date}："
        f"融資餘額 {margin_today:,.0f} ({margin_sign}{margin_delta:,.0f})，"
        f"融券餘額 {short_today:,.0f} ({short_sign}{short_delta:,.0f})"
    )
    summary = (
        f"{symbol} {date} 融資餘額 {margin_today:,.0f} 張，"
        f"較前日 {margin_sign}{margin_delta:,.0f} 張。"
        f"融券餘額 {short_today:,.0f} 張，較前日 {short_sign}{short_delta:,.0f} 張。"
    )

    return [LatestInfoEvent(
        event_id=_event_id("TaiwanStockMarginPurchaseShortSale", symbol, date),
        event_type="margin_change",
        symbol=symbol,
        title=title,
        summary=summary,
        event_date=date,
        source="finmind",
        dataset="TaiwanStockMarginPurchaseShortSale",
        data_id=symbol,
        severity="low",
        confidence="confirmed",
        raw_ref={
            "MarginPurchaseTodayBalance": margin_today,
            "MarginPurchaseDelta": margin_delta,
            "ShortSaleTodayBalance": short_today,
            "ShortSaleDelta": short_delta,
        },
    )]


def extract_data_unavailable_event(
    dataset: str,
    symbol: Optional[str],
    reason: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> LatestInfoEvent:
    """Emit a data_unavailable event when a dataset could not be fetched."""
    return LatestInfoEvent(
        event_id=_event_id(dataset, symbol, end_date),
        event_type="data_unavailable",
        symbol=symbol,
        title=f"{dataset} 資料不可用",
        summary=f"資料集 {dataset} 無法取得（{reason or 'unavailable'}）。本次分析結論不包含此資料。",
        event_date=end_date,
        source="finmind",
        dataset=dataset,
        data_id=symbol,
        severity="unknown",
        confidence="unavailable",
        raw_ref={"unavailable_reason": reason, "start_date": start_date, "end_date": end_date},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Prompt generation (deterministic, no LLM)
# ──────────────────────────────────────────────────────────────────────────────

def generate_follow_up_prompts(
    symbols: List[str],
    end_date: str,
    missing: List[str],
    events: List[LatestInfoEvent],
) -> List[str]:
    """Generate LLM-safe follow-up prompts bound to the current snapshot.

    Rules:
    - All prompts include 'FinMind' or '本次' to anchor to provided data.
    - All prompts include end_date freshness caveat.
    - No buy/sell instruction in any prompt.
    - No prompt instructs LLM to fetch external or live data.
    """
    symbol_display = "、".join(symbols) if symbols else "目標股票"
    missing_display = "、".join(missing) if missing else "無"

    prompts = []
    for tmpl in _PROMPT_TEMPLATES:
        try:
            prompts.append(tmpl.format(
                end_date=end_date,
                symbol_display=symbol_display,
                missing_display=missing_display,
            ))
        except KeyError:
            prompts.append(tmpl)

    # Extra context-aware prompts based on events present
    event_types = {e.event_type for e in events}
    if "institutional_flow" in event_types and "margin_change" in event_types:
        prompts.append(
            f"請根據本次提供的法人買賣超與融資融券資料（截止 {end_date}），"
            f"說明兩者方向是否一致，不得推薦買賣方向。"
        )
    if "monthly_revenue" in event_types:
        prompts.append(
            f"請只根據本次 FinMind 月營收事件資料（截止 {end_date}），"
            f"說明 {symbol_display} 的月營收趨勢，並指明資料視窗限制。"
        )
    if "data_unavailable" in event_types:
        prompts.append(
            f"本次部分資料缺口（{missing_display}）無法提供，"
            f"請勿對這些缺口資料做任何假設或推斷。"
        )

    # Safety check: no prompt should contain buy/sell terms
    return [p for p in prompts if not _contains_buysell(p)]


# ──────────────────────────────────────────────────────────────────────────────
# Main collector
# ──────────────────────────────────────────────────────────────────────────────

class LatestInfoCollector:
    """
    Collect structured latest-info events for TW stocks from FinMind datasets.

    All numeric source of truth comes from FinMind via FinMindDatasetFetcher.
    search_service is accepted for future secondary augmentation (Phase 8G)
    but is not called in Phase 8C v1.

    No LLM calls.
    No buy/sell instructions.
    No CN/A-share datasets.
    """

    _STOCK_DATASETS = [
        "TaiwanStockNews",
        "TaiwanStockMonthRevenue",
        "TaiwanStockDividend",
        "TaiwanStockDividendResult",
        "TaiwanStockPrice",
        "TaiwanStockInstitutionalInvestorsBuySell",
        "TaiwanStockMarginPurchaseShortSale",
    ]
    _MARKET_DATASETS = [
        "TaiwanStockTradingDate",
    ]

    def __init__(
        self,
        fetcher: Optional[FinMindDatasetFetcher] = None,
        search_service: Any = None,
    ) -> None:
        self._fetcher = fetcher or FinMindDatasetFetcher()
        self._search_service = search_service  # secondary only; not used in Phase 8C v1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_market_latest(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Collect market-wide latest info (trading calendar, total institutional, total margin)."""
        events: List[LatestInfoEvent] = []
        datasets_ok: List[str] = []
        datasets_missing: List[str] = []

        # Trading date (freshness anchor)
        r = self._fetcher.fetch("TaiwanStockTradingDate", start_date=start_date, end_date=end_date)
        if r.get("ok"):
            datasets_ok.append("TaiwanStockTradingDate")
            logger.debug("[LatestInfoCollector] TaiwanStockTradingDate ok rows=%d", r.get("row_count", 0))
        else:
            datasets_missing.append("TaiwanStockTradingDate")
            events.append(extract_data_unavailable_event(
                "TaiwanStockTradingDate", None, r.get("unavailable_reason"), start_date, end_date,
            ))

        return {
            "ok": len(datasets_missing) == 0,
            "source": "finmind",
            "start_date": start_date,
            "end_date": end_date,
            "events": [e.to_dict() for e in events],
            "event_count": len(events),
            "data_quality": {
                "datasets_ok": datasets_ok,
                "datasets_missing": datasets_missing,
            },
        }

    def collect_stock_latest(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Collect per-stock latest info for a list of symbols."""
        all_events: List[LatestInfoEvent] = []
        datasets_ok: List[str] = []
        datasets_missing: List[str] = []

        for symbol in symbols:
            evts, ok_ds, miss_ds = self._collect_single_stock(symbol, start_date, end_date)
            all_events.extend(evts)
            for d in ok_ds:
                if d not in datasets_ok:
                    datasets_ok.append(d)
            for d in miss_ds:
                if d not in datasets_missing:
                    datasets_missing.append(d)

        return {
            "ok": len(all_events) > 0,
            "source": "finmind",
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "events": [e.to_dict() for e in all_events],
            "event_count": len(all_events),
            "missing": datasets_missing,
            "data_quality": {
                "datasets_ok": datasets_ok,
                "datasets_missing": datasets_missing,
            },
        }

    def collect_latest_info_snapshot(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Full snapshot: market-wide + per-stock events + data quality + follow-up prompts.

        Returns:
            {ok, source, symbols, start_date, end_date, events, event_count,
             missing, data_quality, recommended_prompts}
        """
        all_events: List[LatestInfoEvent] = []
        datasets_ok: List[str] = []
        datasets_missing: List[str] = []

        # Market-wide
        market = self.collect_market_latest(start_date, end_date)
        for d in market["data_quality"]["datasets_ok"]:
            if d not in datasets_ok:
                datasets_ok.append(d)
        for d in market["data_quality"]["datasets_missing"]:
            if d not in datasets_missing:
                datasets_missing.append(d)
        all_events.extend([
            _dict_to_event(e) for e in market.get("events", [])
        ])

        # Per-stock
        for symbol in symbols:
            evts, ok_ds, miss_ds = self._collect_single_stock(symbol, start_date, end_date)
            all_events.extend(evts)
            for d in ok_ds:
                if d not in datasets_ok:
                    datasets_ok.append(d)
            for d in miss_ds:
                if d not in datasets_missing:
                    datasets_missing.append(d)

        required_ok = len(datasets_missing) == 0 or (
            # Allow TaiwanStockNews unavailable (tier unknown)
            set(datasets_missing) - {"TaiwanStockNews"} == set()
        )

        # Generate follow-up prompts
        prompts = generate_follow_up_prompts(
            symbols=symbols,
            end_date=end_date,
            missing=datasets_missing,
            events=all_events,
        )

        return {
            "ok": len(all_events) > 0 or len(datasets_ok) > 0,
            "source": "finmind",
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "events": [e.to_dict() for e in all_events],
            "event_count": len(all_events),
            "missing": datasets_missing,
            "data_quality": {
                "required_ok": required_ok,
                "partial": len(datasets_missing) > 0,
                "freshness": {
                    "datasets_ok": datasets_ok,
                    "datasets_missing": datasets_missing,
                    "datasets_unavailable": datasets_missing,
                },
                "sources": ["finmind"],
            },
            "recommended_prompts": prompts,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_single_stock(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ):
        """Fetch all per-stock datasets and extract events. Returns (events, ok_datasets, missing_datasets)."""
        events: List[LatestInfoEvent] = []
        ok_ds: List[str] = []
        miss_ds: List[str] = []

        def _fetch(dataset: str, force_live: bool = False) -> Dict[str, Any]:
            return self._fetcher.fetch(
                dataset,
                data_id=symbol,
                start_date=start_date,
                end_date=end_date,
                force_live=force_live,
            )

        # TaiwanStockNews — tier unknown; force_live=True to attempt call
        r = _fetch("TaiwanStockNews", force_live=True)
        if r.get("ok"):
            ok_ds.append("TaiwanStockNews")
            events.extend(extract_news_events(r.get("rows", []), symbol))
        else:
            miss_ds.append("TaiwanStockNews")
            events.append(extract_data_unavailable_event(
                "TaiwanStockNews", symbol, r.get("unavailable_reason"), start_date, end_date,
            ))

        # TaiwanStockMonthRevenue
        r = _fetch("TaiwanStockMonthRevenue")
        if r.get("ok"):
            ok_ds.append("TaiwanStockMonthRevenue")
            evts = extract_revenue_events(r.get("rows", []), symbol)
            events.extend(evts)
        else:
            miss_ds.append("TaiwanStockMonthRevenue")

        # TaiwanStockDividend
        r = _fetch("TaiwanStockDividend")
        if r.get("ok"):
            ok_ds.append("TaiwanStockDividend")
            evts = extract_dividend_events(r.get("rows", []), symbol, "TaiwanStockDividend")
            events.extend(evts)
        else:
            miss_ds.append("TaiwanStockDividend")

        # TaiwanStockDividendResult
        r = _fetch("TaiwanStockDividendResult")
        if r.get("ok"):
            ok_ds.append("TaiwanStockDividendResult")
            evts = extract_dividend_events(r.get("rows", []), symbol, "TaiwanStockDividendResult")
            events.extend(evts)
        else:
            miss_ds.append("TaiwanStockDividendResult")

        # TaiwanStockPrice
        r = _fetch("TaiwanStockPrice")
        if r.get("ok"):
            ok_ds.append("TaiwanStockPrice")
            evts = extract_price_events(r.get("rows", []), symbol)
            events.extend(evts)
        else:
            miss_ds.append("TaiwanStockPrice")

        # TaiwanStockInstitutionalInvestorsBuySell
        r = _fetch("TaiwanStockInstitutionalInvestorsBuySell")
        if r.get("ok"):
            ok_ds.append("TaiwanStockInstitutionalInvestorsBuySell")
            evts = extract_institutional_events(r.get("rows", []), symbol)
            events.extend(evts)
        else:
            miss_ds.append("TaiwanStockInstitutionalInvestorsBuySell")

        # TaiwanStockMarginPurchaseShortSale
        r = _fetch("TaiwanStockMarginPurchaseShortSale")
        if r.get("ok"):
            ok_ds.append("TaiwanStockMarginPurchaseShortSale")
            evts = extract_margin_events(r.get("rows", []), symbol)
            events.extend(evts)
        else:
            miss_ds.append("TaiwanStockMarginPurchaseShortSale")

        return events, ok_ds, miss_ds


def _dict_to_event(d: Dict[str, Any]) -> LatestInfoEvent:
    """Re-hydrate a to_dict() result back into a LatestInfoEvent (for internal use)."""
    return LatestInfoEvent(
        event_id=d.get("event_id", ""),
        event_type=d.get("event_type", ""),
        symbol=d.get("symbol"),
        title=d.get("title", ""),
        summary=d.get("summary", ""),
        event_date=d.get("event_date"),
        source=d.get("source", "finmind"),
        dataset=d.get("dataset", ""),
        data_id=d.get("data_id"),
        severity=d.get("severity", "unknown"),
        confidence=d.get("confidence", "unknown"),
        source_url=d.get("source_url"),
        raw_ref=d.get("raw_ref", {}),
        data_freshness=d.get("data_freshness", {}),
        follow_up_prompts=d.get("follow_up_prompts", []),
    )

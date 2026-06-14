# -*- coding: utf-8 -*-
"""
FinMind-backed TW Stock Analysis v2 — Phase 8D.

Provides TWStockAnalysisCollector which assembles a multi-section structured
snapshot for a single Taiwan stock symbol using FinMind TW-market datasets.

Design principles:
  - TW-only; rejects CN/A-share symbols, US-only tickers.
  - No LLM calls. No buy/sell recommendations.
  - All guards evaluated per-call via FinMindDatasetFetcher.
  - Section failures are captured as warnings; collection continues.
  - LatestInfoCollector is reused for the latest_info section.
  - Result shape is deterministic and LLM-context-safe.

Snapshot sections:
  price_volume        — OHLCV from TaiwanStockPrice
  valuation           — PER / PBR / dividend_yield from TaiwanStockPER
  market_cap          — market_value from TaiwanStockMarketValue (optional)
  monthly_revenue     — revenue + YoY from TaiwanStockMonthRevenue
  fundamentals        — income statement from TaiwanStockFinancialStatements
  balance_sheet       — balance sheet from TaiwanStockBalanceSheet
  cash_flow           — cash flow from TaiwanStockCashFlowsStatement
  dividend            — declared dividends from TaiwanStockDividend
  dividend_result     — ex-dividend results from TaiwanStockDividendResult
  institutional_flow  — three-party from TaiwanStockInstitutionalInvestorsBuySell
  margin              — margin/short-sale from TaiwanStockMarginPurchaseShortSale
  latest_info         — LatestInfoCollector snapshot (events + prompts)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.finmind.fetcher import FinMindDatasetFetcher
from src.finmind.latest_info import LatestInfoCollector

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Symbol normalization
# ──────────────────────────────────────────────────────────────────────────────

_CN_6DIGIT_RE = re.compile(r"^\d{6}$")
_PURE_ALPHA_RE = re.compile(r"^[A-Za-z]+$")
_TW_STOCK_ID_RE = re.compile(r"^\d[\dA-Za-z]{1,5}$")  # starts with digit; 2-6 chars total


def normalize_tw_symbol(symbol: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize a symbol string to a bare TW stock_id.

    Returns (stock_id, error). On success error is None.
    On rejection stock_id is None and error describes the reason.

    Accepted forms:
      TW:2330  → 2330
      2330.TW  → 2330
      2330     → 2330
      00631L   → 00631L  (TW levered ETF)
      0050     → 0050    (TW ETF)

    Rejected:
      US:AAPL  → error (non-TW market prefix)
      HK:0700  → error (non-TW market prefix)
      AAPL     → error (pure alpha, likely US ticker)
      600519   → error (6-digit numeric = CN A-share)
      (empty)  → error
    """
    if not symbol or not isinstance(symbol, str):
        return None, "symbol must be a non-empty string"

    s = symbol.strip()

    # Handle market prefixes
    if ":" in s:
        prefix, _, rest = s.partition(":")
        if prefix.upper() != "TW":
            return None, f"non-TW market prefix '{prefix}': only TW-market symbols accepted"
        s = rest.strip()

    # Strip .TW suffix
    if s.upper().endswith(".TW"):
        s = s[:-3]

    if not s:
        return None, "symbol is empty after stripping prefix/suffix"

    # Reject 6-digit numeric (CN A-share)
    if _CN_6DIGIT_RE.match(s):
        return None, f"6-digit numeric '{s}' is a CN A-share symbol; only TW-market accepted"

    # Reject pure alpha (US ticker)
    if _PURE_ALPHA_RE.match(s):
        return None, f"pure-alpha '{s}' is likely a US ticker; only TW-market symbols accepted"

    # Validate TW stock ID pattern
    if not _TW_STOCK_ID_RE.match(s):
        return None, f"'{s}' does not match TW stock ID pattern (must start with digit, 2-6 chars)"

    return s, None


# ──────────────────────────────────────────────────────────────────────────────
# Snapshot model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TWStockAnalysisSnapshot:
    """Structured snapshot for a single TW stock.

    Fields:
      ok              — True if at least required sections partially succeeded
      symbol          — original input symbol
      stock_id        — normalized TW stock_id (e.g. '2330')
      start_date      — query window start (YYYY-MM-DD)
      end_date        — query window end (YYYY-MM-DD)
      sections        — per-section data dicts keyed by section name
      data_quality    — aggregated quality metadata
      sources         — list of data sources used
      missing         — list of section names that returned no data
      warnings        — list of warning messages from section fetches
      recommended_prompts — deterministic LLM-context prompts
    """
    ok: bool
    symbol: str
    stock_id: Optional[str]
    start_date: str
    end_date: str
    sections: Dict[str, Any] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommended_prompts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "symbol": self.symbol,
            "stock_id": self.stock_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "sections": self.sections,
            "data_quality": self.data_quality,
            "sources": self.sources,
            "missing": self.missing,
            "warnings": self.warnings,
            "recommended_prompts": self.recommended_prompts,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Section extraction helpers
# ──────────────────────────────────────────────────────────────────────────────

def _extract_price_volume(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract latest price/volume summary from TaiwanStockPrice fetch result."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": []}

    latest = rows[-1] if rows else {}
    return {
        "available": True,
        "latest_date": latest.get("date"),
        "open": latest.get("open"),
        "high": latest.get("max"),
        "low": latest.get("min"),
        "close": latest.get("close"),
        "spread": latest.get("spread"),
        "volume": latest.get("Trading_Volume"),
        "turnover": latest.get("Trading_money"),
        "row_count": len(rows),
        "rows": rows,
    }


def _extract_valuation(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract latest valuation from TaiwanStockPER fetch result."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": []}

    latest = rows[-1] if rows else {}
    return {
        "available": True,
        "latest_date": latest.get("date"),
        "PER": latest.get("PER"),
        "PBR": latest.get("PBR"),
        "dividend_yield": latest.get("dividend_yield"),
        "row_count": len(rows),
        "rows": rows,
    }


def _extract_market_cap(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract latest market cap from TaiwanStockMarketValue fetch result."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": []}

    latest = rows[-1] if rows else {}
    return {
        "available": True,
        "latest_date": latest.get("date"),
        "market_value": latest.get("market_value"),
        "row_count": len(rows),
        "rows": rows,
    }


def _compute_revenue_yoy(rows: List[Dict[str, Any]]) -> Optional[float]:
    """Compute YoY revenue growth from monthly revenue rows (sorted by date asc)."""
    if len(rows) < 13:
        return None
    current = rows[-1].get("revenue")
    prev_year = rows[-13].get("revenue") if len(rows) >= 13 else None
    if current is None or prev_year is None or prev_year == 0:
        return None
    try:
        return round((float(current) - float(prev_year)) / float(prev_year) * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _extract_monthly_revenue(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract revenue summary + YoY from TaiwanStockMonthRevenue fetch result."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": []}

    latest = rows[-1] if rows else {}
    yoy = _compute_revenue_yoy(rows)
    return {
        "available": True,
        "latest_date": latest.get("date"),
        "revenue": latest.get("revenue"),
        "revenue_month": latest.get("revenue_month"),
        "revenue_year": latest.get("revenue_year"),
        "yoy_pct": yoy,
        "yoy_available": yoy is not None,
        "row_count": len(rows),
        "rows": rows,
    }


def _extract_kv_statements(result: Dict[str, Any], section_name: str) -> Dict[str, Any]:
    """Extract key-value financial statement rows (type/value/origin_name schema)."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": [], "section": section_name}

    # Group by date, take most recent
    dates = sorted({r.get("date") for r in rows if r.get("date")}, reverse=True)
    latest_date = dates[0] if dates else None
    latest_rows = [r for r in rows if r.get("date") == latest_date]

    # Build flat dict of type→value for quick LLM consumption
    kv = {}
    for r in latest_rows:
        t = r.get("type")
        v = r.get("value")
        if t:
            kv[t] = v

    return {
        "available": True,
        "section": section_name,
        "latest_date": latest_date,
        "kv": kv,
        "all_dates": dates[:4],  # last 4 quarters
        "row_count": len(rows),
        "rows": rows,
    }


def _extract_dividend(result_declared: Dict[str, Any], result_ex: Dict[str, Any]) -> Dict[str, Any]:
    """Merge TaiwanStockDividend + TaiwanStockDividendResult into dividend section."""
    declared_rows = result_declared.get("rows", [])
    ex_rows = result_ex.get("rows", [])
    latest_declared = declared_rows[-1] if declared_rows else {}
    latest_ex = ex_rows[-1] if ex_rows else {}

    return {
        "available": bool(declared_rows or ex_rows),
        "declared": {
            "available": bool(declared_rows),
            "latest_date": latest_declared.get("date"),
            "cash_dividend": latest_declared.get("CashEarningsDistribution"),
            "stock_dividend": latest_declared.get("StockEarningsDistribution"),
            "cash_payment_date": latest_declared.get("CashDividendPaymentDate"),
            "row_count": len(declared_rows),
            "rows": declared_rows,
        },
        "ex_dividend": {
            "available": bool(ex_rows),
            "latest_date": latest_ex.get("date"),
            "row_count": len(ex_rows),
            "rows": ex_rows,
        },
    }


def _extract_institutional_flow(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract institutional buy/sell summary from TaiwanStockInstitutionalInvestorsBuySell."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": []}

    # Latest date
    dates = sorted({r.get("date") for r in rows if r.get("date")}, reverse=True)
    latest_date = dates[0] if dates else None
    latest_rows = [r for r in rows if r.get("date") == latest_date]

    # Aggregate by institution name
    by_name: Dict[str, Dict] = {}
    for r in latest_rows:
        name = r.get("name", "unknown")
        by_name[name] = {
            "buy": r.get("buy"),
            "sell": r.get("sell"),
        }

    # Compute total net (Foreign_Investor only for simplicity)
    foreign = by_name.get("Foreign_Investor", {})
    foreign_net = None
    if foreign.get("buy") is not None and foreign.get("sell") is not None:
        try:
            foreign_net = int(foreign["buy"]) - int(foreign["sell"])
        except (TypeError, ValueError):
            foreign_net = None

    return {
        "available": True,
        "latest_date": latest_date,
        "by_institution": by_name,
        "foreign_net": foreign_net,
        "row_count": len(rows),
        "rows": rows,
    }


def _extract_margin(result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract margin/short-sale summary from TaiwanStockMarginPurchaseShortSale."""
    rows = result.get("rows", [])
    if not rows:
        return {"available": False, "rows": []}

    latest = rows[-1] if rows else {}
    return {
        "available": True,
        "latest_date": latest.get("date"),
        "margin_balance": latest.get("MarginPurchaseTodayBalance"),
        "margin_prev": latest.get("MarginPurchaseYesterdayBalance"),
        "short_balance": latest.get("ShortSaleTodayBalance"),
        "short_prev": latest.get("ShortSaleYesterdayBalance"),
        "row_count": len(rows),
        "rows": rows,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Prompt generation
# ──────────────────────────----------------------------------------------------------------

def _generate_analysis_prompts(
    stock_id: str,
    end_date: str,
    sections: Dict[str, Any],
    missing: List[str],
) -> List[str]:
    """
    Generate deterministic, LLM-context-safe analysis prompts.

    Anchored to:
      - 只根據本 snapshot 的資料（不參考外部知識）
      - end_date: explicit date anchor
      - No buy/sell, no price target, no investment advice.
    """
    prompts = []

    # Price + valuation
    pv = sections.get("price_volume", {})
    val = sections.get("valuation", {})
    if pv.get("available") or val.get("available"):
        prompts.append(
            f"只根據本 snapshot 的資料（截至 {end_date}），"
            f"分析 {stock_id} 的最新收盤價、本益比和股價淨值比，"
            "並說明近期趨勢（勿作投資建議）。"
        )

    # Revenue
    rev = sections.get("monthly_revenue", {})
    if rev.get("available"):
        yoy_str = (
            f"（YoY {rev['yoy_pct']:+.1f}%）" if rev.get("yoy_pct") is not None else ""
        )
        prompts.append(
            f"只根據本 snapshot 的資料（截至 {end_date}），"
            f"說明 {stock_id} 最新月營收{yoy_str}的變化方向與潛在原因。"
        )

    # Fundamentals
    if sections.get("fundamentals", {}).get("available"):
        prompts.append(
            f"只根據本 snapshot 的資料（截至 {end_date}），"
            f"摘要 {stock_id} 最近一期的損益狀況，"
            "包含營收、毛利率、營業利益。"
        )

    # Institutional
    inst = sections.get("institutional_flow", {})
    if inst.get("available"):
        prompts.append(
            f"只根據本 snapshot 的資料（截至 {end_date}），"
            f"說明 {stock_id} 三大法人的買賣超方向與外資淨額，"
            "並分析對籌碼面的意義（勿作投資建議）。"
        )

    # Missing data note
    if missing:
        prompts.append(
            f"本 snapshot 中以下資料區段因資料源限制未取得：{', '.join(missing)}。"
            "分析時請注意此資料缺口，避免基於缺失資料做出推斷。"
        )

    return prompts


# ──────────────────────────────────────────────────────────────────────────────
# Main collector
# ──────────────────────────────────────────────────────────────────────────────

class TWStockAnalysisCollector:
    """
    Assemble a multi-section TW stock analysis snapshot via FinMind datasets.

    Usage:
        collector = TWStockAnalysisCollector()
        snapshot = collector.collect_stock_analysis_snapshot(
            symbol="TW:2330",
            start_date="2025-09-01",
            end_date="2026-06-14",
        )
        result = snapshot.to_dict()
    """

    # Datasets needed per section and their long-window requirements
    _LONG_WINDOW_DATASETS = {
        "TaiwanStockMonthRevenue",
        "TaiwanStockFinancialStatements",
        "TaiwanStockBalanceSheet",
        "TaiwanStockCashFlowsStatement",
        "TaiwanStockDividend",
        "TaiwanStockDividendResult",
    }

    def __init__(
        self,
        fetcher: Optional[FinMindDatasetFetcher] = None,
        latest_info_collector: Optional[LatestInfoCollector] = None,
    ):
        self._fetcher = fetcher or FinMindDatasetFetcher()
        self._latest_info = latest_info_collector or LatestInfoCollector(
            fetcher=self._fetcher
        )

    # ── internal fetch helpers ────────────────────────────────────────────────

    def _fetch(
        self,
        dataset: str,
        stock_id: str,
        start_date: str,
        end_date: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        try:
            return self._fetcher.fetch(
                dataset,
                data_id=stock_id,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            msg = f"fetch {dataset}/{stock_id} raised {type(exc).__name__}: {exc}"
            logger.warning(msg)
            warnings.append(msg)
            return {"ok": False, "rows": [], "columns": [], "row_count": 0}

    # ── public API ────────────────────────────────────────────────────────────

    def collect_stock_analysis_snapshot(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> TWStockAnalysisSnapshot:
        """
        Collect a full multi-section TW stock analysis snapshot.

        Args:
            symbol:     TW stock symbol in any accepted form (TW:2330, 2330.TW, 2330)
            start_date: Query window start (YYYY-MM-DD); recommend 90+ days
            end_date:   Query window end (YYYY-MM-DD)

        Returns:
            TWStockAnalysisSnapshot with sections, quality metadata, prompts.
        """
        stock_id, err = normalize_tw_symbol(symbol)
        if err:
            return TWStockAnalysisSnapshot(
                ok=False,
                symbol=symbol,
                stock_id=None,
                start_date=start_date,
                end_date=end_date,
                warnings=[f"symbol normalization failed: {err}"],
                data_quality={"valid_symbol": False},
            )

        warnings: List[str] = []
        sections: Dict[str, Any] = {}
        missing: List[str] = []

        # ── 1. price_volume ──────────────────────────────────────────────────
        r_pv = self._fetch("TaiwanStockPrice", stock_id, start_date, end_date, warnings)
        sections["price_volume"] = _extract_price_volume(r_pv)
        if not sections["price_volume"]["available"]:
            missing.append("price_volume")

        # ── 2. valuation ─────────────────────────────────────────────────────
        r_val = self._fetch("TaiwanStockPER", stock_id, start_date, end_date, warnings)
        sections["valuation"] = _extract_valuation(r_val)
        if not sections["valuation"]["available"]:
            missing.append("valuation")

        # ── 3. market_cap (optional — tier unknown) ──────────────────────────
        r_mc = self._fetch("TaiwanStockMarketValue", stock_id, start_date, end_date, warnings)
        sections["market_cap"] = _extract_market_cap(r_mc)
        if not sections["market_cap"]["available"]:
            missing.append("market_cap")

        # ── 4. monthly_revenue (long window preferred for YoY) ────────────────
        r_rev = self._fetch("TaiwanStockMonthRevenue", stock_id, start_date, end_date, warnings)
        sections["monthly_revenue"] = _extract_monthly_revenue(r_rev)
        if not sections["monthly_revenue"]["available"]:
            missing.append("monthly_revenue")

        # ── 5. fundamentals ───────────────────────────────────────────────────
        r_fs = self._fetch("TaiwanStockFinancialStatements", stock_id, start_date, end_date, warnings)
        sections["fundamentals"] = _extract_kv_statements(r_fs, "fundamentals")
        if not sections["fundamentals"]["available"]:
            missing.append("fundamentals")

        # ── 6. balance_sheet ──────────────────────────────────────────────────
        r_bs = self._fetch("TaiwanStockBalanceSheet", stock_id, start_date, end_date, warnings)
        sections["balance_sheet"] = _extract_kv_statements(r_bs, "balance_sheet")
        if not sections["balance_sheet"]["available"]:
            missing.append("balance_sheet")

        # ── 7. cash_flow ──────────────────────────────────────────────────────
        r_cf = self._fetch("TaiwanStockCashFlowsStatement", stock_id, start_date, end_date, warnings)
        sections["cash_flow"] = _extract_kv_statements(r_cf, "cash_flow")
        if not sections["cash_flow"]["available"]:
            missing.append("cash_flow")

        # ── 8. dividend (declared + ex-dividend result) ───────────────────────
        r_div = self._fetch("TaiwanStockDividend", stock_id, start_date, end_date, warnings)
        r_divr = self._fetch("TaiwanStockDividendResult", stock_id, start_date, end_date, warnings)
        sections["dividend"] = _extract_dividend(r_div, r_divr)
        if not sections["dividend"]["available"]:
            missing.append("dividend")

        # ── 9. institutional_flow ─────────────────────────────────────────────
        r_inst = self._fetch(
            "TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date, end_date, warnings
        )
        sections["institutional_flow"] = _extract_institutional_flow(r_inst)
        if not sections["institutional_flow"]["available"]:
            missing.append("institutional_flow")

        # ── 10. margin ────────────────────────────────────────────────────────
        r_mg = self._fetch(
            "TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date, warnings
        )
        sections["margin"] = _extract_margin(r_mg)
        if not sections["margin"]["available"]:
            missing.append("margin")

        # ── 11. latest_info (via LatestInfoCollector) ─────────────────────────
        try:
            li_snap = self._latest_info.collect_stock_latest(
                symbols=[stock_id],
                start_date=start_date,
                end_date=end_date,
            )
            sections["latest_info"] = li_snap
        except Exception as exc:
            msg = f"LatestInfoCollector raised {type(exc).__name__}: {exc}"
            logger.warning(msg)
            warnings.append(msg)
            sections["latest_info"] = {"available": False, "error": msg}
            missing.append("latest_info")

        # ── quality metadata ──────────────────────────────────────────────────
        required_sections = {
            "price_volume", "valuation", "monthly_revenue",
            "fundamentals", "institutional_flow",
        }
        required_ok = not required_sections.intersection(missing)
        optional_sections = {
            "market_cap", "balance_sheet", "cash_flow",
            "dividend", "margin", "latest_info",
        }
        optional_missing = optional_sections.intersection(missing)

        data_quality = {
            "valid_symbol": True,
            "required_ok": required_ok,
            "partial": bool(missing),
            "sections_ok": [s for s in sections if sections[s].get("available")],
            "sections_missing": list(missing),
            "optional_missing": list(optional_missing),
            "sources": ["finmind"],
        }

        # ── recommended prompts ───────────────────────────────────────────────
        prompts = _generate_analysis_prompts(stock_id, end_date, sections, missing)

        return TWStockAnalysisSnapshot(
            ok=not required_sections.intersection(missing),
            symbol=symbol,
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date,
            sections=sections,
            data_quality=data_quality,
            sources=["finmind"],
            missing=list(missing),
            warnings=warnings,
            recommended_prompts=prompts,
        )

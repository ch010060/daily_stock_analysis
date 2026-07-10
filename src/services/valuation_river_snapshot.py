# -*- coding: utf-8 -*-
"""
Phase 26.1/26.2 — deterministic valuation river snapshot for TW + US stocks.

TW: builds a historical PER/PBR-derived price-band series ("valuation
river") purely from already-fetched FinMind `TaiwanStockPER` (daily
PER/PBR/dividend yield) joined with `TaiwanStockPrice` (daily OHLCV) by
date:

    implied_eps(t)  = close(t) / per(t)
    implied_bvps(t) = close(t) / pbr(t)
    band(t, multiple) = implied_eps(t) * multiple

US (Phase 26.2): yfinance exposes no historical daily PE/PB ratio series
and only ~5 quarters of quarterly statements (too thin for more than one
rolling TTM point), so the TW method above cannot be replicated. Instead,
annual `income_stmt`/`balance_sheet` calls expose 4-5 real fiscal-year
EPS/book-value points — genuinely time-varying reported data, not a
current ratio reused across the whole range:

    band(t, multiple) = annual_eps_anchor(t) * multiple   (forward-filled
                                                             between fiscal
                                                             year ends)

Both paths also surface point-in-time `eps_actual` (reported/TTM) and
`eps_forward` (analyst/forward estimate) as separate reference stats,
distinct from whichever basis the plotted bands use — an "implied" or
"reported-annual" EPS must never be presented to the user as "actual EPS"
if it isn't.

The LLM never sees or produces any of this — this module has no prompt
awareness and is never imported by `analysis_context_builder.py`. Band
multiples are fixed constants (not configurable per-request, not LLM
output), and are explicitly documented as visual reference multiples, not
fair value / target price / a recommendation.

Non-goals (see docs/worklogs and Phase 26.0/26.1 reports): no full
valuation engine, no sector-relative or peer comparison, no LLM-generated
commentary, no trading signal, no fabricated historical PE/PB series from
a single current ratio.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Fixed, deterministic PER multiples — visual reference bands only. Reused
# for both TW and US so the chart's visual language stays identical across
# markets; chosen in Phase 26.0's PoC to bracket the ~19.7x-34.9x PER range
# observed for 2330 over a ~13-month window with headroom on both sides
# (US large caps in this band multiple set have historically sat in a
# comparable ~25x-40x range, e.g. AAPL trailingPE ~38x at time of writing).
PER_BAND_MULTIPLES: tuple = (14, 18, 22, 26, 30, 34, 38)
NEUTRAL_MULTIPLE = 26

METHODOLOGY_NOTE_TW = (
    "倍數帶為固定視覺參考基準（非估值結論、目標價或買賣建議），"
    "由 close(t)/PER(t) 反推的隱含 EPS 乘上固定倍數計算而得。"
)
METHODOLOGY_NOTE_US = (
    "倍數帶為固定視覺參考基準（非估值結論、目標價或買賣建議），"
    "由財報年度實際 EPS（非反推）乘上固定倍數計算而得，於財報年度間以階梯狀延伸；"
    "圖中 PER 為「現價 / 最近財報年度 EPS」，與其他區塊採用之 TTM PE 基準不同，兩者不可直接比較。"
)
# Backwards-compat alias — Phase 26.1 tests import this name directly.
METHODOLOGY_NOTE = METHODOLOGY_NOTE_TW

MIN_JOINED_ROWS = 20  # below this, "partial"; below GAP_JOINED_ROWS, "gap"
GAP_JOINED_ROWS = 5

MIN_US_ANNUAL_ANCHORS = 2  # need >=2 real fiscal-year EPS points to forward-fill a river
US_STALE_FINANCIALS_DAYS = 450  # ~15 months: one missed annual report cycle


def _band_key(multiple: int) -> str:
    return f"per_{multiple}"


def _zone_for_multiple(current_multiple: Optional[float]) -> str:
    if current_multiple is None:
        return "unknown"
    if current_multiple < NEUTRAL_MULTIPLE:
        return "undervalued"
    if current_multiple > NEUTRAL_MULTIPLE:
        return "overvalued"
    return "neutral"


def _eps_stat(value: Optional[float], *, period: str, source: str) -> Optional[Dict[str, Any]]:
    """Build a labeled point-in-time EPS stat, or None when the value is missing.

    Kept as its own small object (not a bare number) so the frontend never has
    to guess whether a number is actual/reported vs. forward/estimated vs.
    implied — the `period`/`source` travel with the value.
    """
    if value is None:
        return None
    return {"value": value, "period": period, "source": source}


def _unavailable(
    *,
    market: str,
    symbol: str,
    reason: str,
    warnings: Optional[List[str]] = None,
    codes: Optional[List[str]] = None,
    eps_actual: Optional[Dict[str, Any]] = None,
    eps_forward: Optional[Dict[str, Any]] = None,
    methodology_note: str = METHODOLOGY_NOTE_TW,
) -> Dict[str, Any]:
    return {
        "enabled": False,
        "market": market,
        "symbol": symbol,
        "currency": "TWD" if market == "tw" else ("USD" if market == "us" else None),
        "source": "unavailable",
        "method": "unavailable",
        "basis": "unavailable",
        "eps_kind": "unavailable" if eps_actual is None else "reported",
        "eps_source": "unavailable" if eps_actual is None else eps_actual["source"],
        "eps_period": "unavailable" if eps_actual is None else eps_actual["period"],
        "as_of": None,
        "range": {"start_date": None, "end_date": None, "trading_days": 0},
        "points": [],
        "current": {
            "close": None, "per": None, "pbr": None,
            "implied_eps": None, "implied_bvps": None, "zone": "unknown",
            "eps_actual": eps_actual, "eps_forward": eps_forward,
        },
        "quality": {
            "status": "unsupported",
            "warnings": warnings or [reason],
            "codes": codes or [],
            "data_gap_fields": [],
            "methodology_note": methodology_note,
        },
    }


def build_valuation_river_snapshot_unsupported(
    market: str,
    symbol: str,
    reason: str,
    *,
    eps_actual: Optional[Dict[str, Any]] = None,
    eps_forward: Optional[Dict[str, Any]] = None,
    codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Public helper for non-TW-river / non-stock callers: always returns a
    well-formed unavailable snapshot so the frontend adapter never has to
    special-case a missing key vs. an explicit "not applicable" state.

    `eps_actual`/`eps_forward` let a caller surface a real point-in-time EPS
    stat (see `_eps_stat`) even when the historical river itself could not be
    built — e.g. a US stock with a working `trailingEps`/`forwardEps` call
    but too few annual fiscal-year anchors to forward-fill a river.
    """
    return _unavailable(
        market=market, symbol=symbol, reason=reason,
        codes=codes, eps_actual=eps_actual, eps_forward=eps_forward,
    )


def build_tw_valuation_river_snapshot(
    symbol: str,
    per_rows: List[Dict[str, Any]],
    price_rows: List[Dict[str, Any]],
    *,
    actual_eps_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the TW valuation river snapshot from already-fetched FinMind rows.

    Args:
        symbol: bare TW stock_id (e.g. "2330").
        per_rows: rows from `TaiwanStockPER` fetch (date/PER/PBR/dividend_yield).
        price_rows: rows from `TaiwanStockPrice` fetch (date/close/...).
        actual_eps_row: optional `{"date": ..., "eps": ...}` from
            `fetch_tw_actual_eps_row` (latest reported quarterly EPS from
            `TaiwanStockFinancialStatements`). Surfaced as `current.eps_actual`
            — genuinely reported, distinct from this function's own
            PER-implied EPS. TW has no forward/analyst-estimate EPS source in
            this repo's current data paths, so `eps_forward` is always None.

    Returns:
        The full `valuation_river_snapshot` contract dict. Never raises —
        insufficient/malformed input degrades to `quality.status` in
        {"partial", "gap"} with `enabled=True` but an empty/short `points`
        list, never to a crash.
    """
    warnings: List[str] = []
    codes: List[str] = []
    eps_actual = (
        _eps_stat(actual_eps_row.get("eps"), period="quarterly", source="finmind")
        if actual_eps_row
        else None
    )
    if eps_actual is None:
        codes.append("missing_eps")

    if not per_rows:
        return _unavailable(
            market="tw", symbol=symbol, reason="TaiwanStockPER 無資料",
            eps_actual=eps_actual,
        )
    if not price_rows:
        return _unavailable(
            market="tw", symbol=symbol, reason="TaiwanStockPrice 無資料",
            eps_actual=eps_actual,
        )

    per_by_date = {r.get("date"): r for r in per_rows if r.get("date")}
    price_by_date = {r.get("date"): r for r in price_rows if r.get("date")}
    joined_dates = sorted(set(per_by_date) & set(price_by_date))

    if not joined_dates:
        return _unavailable(
            market="tw", symbol=symbol,
            reason="TaiwanStockPER 與 TaiwanStockPrice 日期無交集",
            eps_actual=eps_actual,
        )

    points: List[Dict[str, Any]] = []
    per_gap_count = 0
    pbr_gap_count = 0

    for d in joined_dates:
        per_row = per_by_date[d]
        price_row = price_by_date[d]
        close = price_row.get("close")
        per = per_row.get("PER")
        pbr = per_row.get("PBR")

        implied_eps = None
        implied_bvps = None
        bands: Dict[str, float] = {}

        if close is None:
            continue  # no price on this date is a hard skip; can't derive anything

        if per is None or per == 0:
            per_gap_count += 1
        else:
            implied_eps = round(close / per, 4)
            bands = {_band_key(m): round(implied_eps * m, 4) for m in PER_BAND_MULTIPLES}

        if pbr is None or pbr == 0:
            pbr_gap_count += 1
        else:
            implied_bvps = round(close / pbr, 4)

        point: Dict[str, Any] = {
            "date": d,
            "close": close,
            "per": per,
            "pbr": pbr,
            "implied_eps": implied_eps,
            "implied_bvps": implied_bvps,
        }
        if bands:
            point["bands"] = bands
        points.append(point)

    if not points:
        return _unavailable(
            market="tw", symbol=symbol,
            reason="聯集日期後無可用收盤價資料",
            eps_actual=eps_actual,
        )

    if len(points) < GAP_JOINED_ROWS:
        return _unavailable(
            market="tw", symbol=symbol,
            reason=f"聯集資料筆數過少（僅 {len(points)} 個交易日，低於 {GAP_JOINED_ROWS} 天下限），暫不提供河流圖",
            codes=["insufficient_history"],
            eps_actual=eps_actual,
        )

    if per_gap_count:
        warnings.append(f"{per_gap_count} 個交易日缺少 PER，該日無倍數帶")
    if pbr_gap_count:
        warnings.append(f"{pbr_gap_count} 個交易日缺少 PBR，implied_bvps 為 null")

    last = points[-1]
    current_zone = _zone_for_multiple(last.get("per"))

    status = "ok"
    if len(points) < MIN_JOINED_ROWS:
        status = "partial"
        warnings.append(f"僅 {len(points)} 個交易日聯集資料，低於建議下限 {MIN_JOINED_ROWS} 天")

    return {
        "enabled": True,
        "market": "tw",
        "symbol": symbol,
        "currency": "TWD",
        "source": "finmind",
        "method": "per_implied_eps_river",
        "basis": "implied_eps",
        "eps_kind": "implied",
        "eps_source": "finmind",
        "eps_period": "point_in_time",
        "band_multiples": list(PER_BAND_MULTIPLES),
        "neutral_multiple": NEUTRAL_MULTIPLE,
        "as_of": last["date"],
        "range": {
            "start_date": points[0]["date"],
            "end_date": last["date"],
            "trading_days": len(points),
        },
        "points": points,
        "current": {
            "close": last["close"],
            "per": last.get("per"),
            "pbr": last.get("pbr"),
            "implied_eps": last.get("implied_eps"),
            "implied_bvps": last.get("implied_bvps"),
            "zone": current_zone,
            "eps_actual": eps_actual,
            "eps_forward": None,
        },
        "quality": {
            "status": status,
            "warnings": warnings,
            "codes": codes,
            "data_gap_fields": (["per"] if per_gap_count else []) + (["pbr"] if pbr_gap_count else []),
            "methodology_note": METHODOLOGY_NOTE_TW,
        },
    }


def build_us_valuation_river_snapshot(
    symbol: str,
    annual_eps_rows: List[Dict[str, Any]],
    annual_bvps_rows: List[Dict[str, Any]],
    price_rows: List[Dict[str, Any]],
    *,
    eps_actual_ttm: Optional[float] = None,
    eps_forward: Optional[float] = None,
    currency: Optional[str] = "USD",
) -> Dict[str, Any]:
    """Build the US valuation river snapshot (Phase 26.2) from already-fetched
    yfinance annual financial-statement rows + daily price.

    yfinance exposes no historical daily PE/PB ratio series, so the TW method
    (implied EPS from a daily PER series) cannot be replicated. Instead this
    forward-fills real annual reported EPS (Diluted/Basic EPS from
    `income_stmt`, ~4-5 genuine fiscal-year points) onto daily close price,
    producing a step-function history built from time-varying reported
    financials — never a single current ratio reused across the whole range.

    Args:
        symbol: US ticker (e.g. "AAPL").
        annual_eps_rows: `[{"date": "YYYY-MM-DD", "eps": float}, ...]`, one row
            per fiscal year-end (from `fetch_us_valuation_river_series`).
        annual_bvps_rows: same shape with `"bvps"` — informational only, not
            banded (mirrors how TW's `implied_bvps` is per-point info without
            its own band set).
        price_rows: `[{"date": "YYYY-MM-DD", "close": float}, ...]` daily.
        eps_actual_ttm: point-in-time `trailingEps` from yfinance `.info` —
            distinct from the annual EPS the bands are built from (TTM as of
            the latest quarter vs. EPS as of the latest fiscal year-end).
        eps_forward: point-in-time `forwardEps` (analyst/forward estimate).
        currency: trading currency, default USD.

    Returns:
        Full `valuation_river_snapshot` contract dict. Never raises;
        insufficient/malformed input degrades to an unavailable snapshot
        (still carrying `eps_actual`/`eps_forward` when those point-in-time
        values were obtained, via `build_valuation_river_snapshot_unsupported`).
    """
    eps_actual = _eps_stat(eps_actual_ttm, period="ttm", source="yfinance")
    eps_forward_stat = _eps_stat(eps_forward, period="point_in_time", source="yfinance")

    usable_eps_anchors = sorted(
        (r for r in annual_eps_rows if r.get("date") and r.get("eps") is not None),
        key=lambda r: r["date"],
    )

    if not usable_eps_anchors:
        return build_valuation_river_snapshot_unsupported(
            "us", symbol, "yfinance 年度財報無可用 EPS 資料",
            eps_actual=eps_actual, eps_forward=eps_forward_stat, codes=["missing_eps"],
        )

    if len(usable_eps_anchors) < MIN_US_ANNUAL_ANCHORS:
        codes = ["insufficient_history"]
        if eps_actual is not None or eps_forward_stat is not None:
            codes.append("point_in_time_only")
        reason = (
            f"yfinance 年度財報 EPS 資料點過少（僅 {len(usable_eps_anchors)} 個財報年度，"
            f"低於 {MIN_US_ANNUAL_ANCHORS} 個下限），無法建構歷史河流圖"
        )
        return build_valuation_river_snapshot_unsupported(
            "us", symbol, reason, eps_actual=eps_actual, eps_forward=eps_forward_stat, codes=codes,
        )

    price_by_date = sorted(
        ((r["date"], r["close"]) for r in price_rows if r.get("date") and r.get("close") is not None),
        key=lambda item: item[0],
    )
    if not price_by_date:
        return build_valuation_river_snapshot_unsupported(
            "us", symbol, "yfinance 每日收盤價無可用資料",
            eps_actual=eps_actual, eps_forward=eps_forward_stat,
        )

    usable_bvps_anchors = sorted(
        (r for r in annual_bvps_rows if r.get("date") and r.get("bvps") is not None),
        key=lambda r: r["date"],
    )

    first_anchor_date = usable_eps_anchors[0]["date"]
    points: List[Dict[str, Any]] = []
    for price_date, close in price_by_date:
        if price_date < first_anchor_date:
            continue  # no reported EPS anchor exists yet this far back — don't guess

        anchor = None
        for candidate in usable_eps_anchors:
            if candidate["date"] <= price_date:
                anchor = candidate
            else:
                break
        if anchor is None:
            continue

        bvps_anchor = None
        for candidate in usable_bvps_anchors:
            if candidate["date"] <= price_date:
                bvps_anchor = candidate
            else:
                break

        eps_value = anchor["eps"]
        bands = {_band_key(m): round(eps_value * m, 4) for m in PER_BAND_MULTIPLES} if eps_value else {}
        points.append({
            "date": price_date,
            "close": close,
            "per": round(close / eps_value, 4) if eps_value else None,
            "pbr": (
                round(close / bvps_anchor["bvps"], 4)
                if bvps_anchor and bvps_anchor.get("bvps")
                else None
            ),
            "implied_eps": eps_value,
            "implied_bvps": bvps_anchor["bvps"] if bvps_anchor else None,
            "bands": bands,
            "eps_anchor_date": anchor["date"],
        })

    if not points:
        return build_valuation_river_snapshot_unsupported(
            "us", symbol, "每日收盤價早於最早財報年度錨點，無法建構河流圖",
            eps_actual=eps_actual, eps_forward=eps_forward_stat, codes=["insufficient_history"],
        )

    last = points[-1]
    current_zone = _zone_for_multiple(last.get("per"))

    codes: List[str] = []
    warnings: List[str] = []
    if not usable_bvps_anchors:
        codes.append("missing_bvps")
        warnings.append("缺少年度資產負債表資料，implied_bvps 為 null")

    try:
        from datetime import date as _date
        latest_anchor_date = usable_eps_anchors[-1]["date"]
        days_stale = (_date.fromisoformat(last["date"]) - _date.fromisoformat(latest_anchor_date)).days
        if days_stale > US_STALE_FINANCIALS_DAYS:
            codes.append("stale_financials")
            warnings.append(f"最新財報年度錨點已超過 {US_STALE_FINANCIALS_DAYS} 天未更新")
    except Exception:
        pass

    status = "ok"
    if len(usable_eps_anchors) < 4:
        status = "partial"
        warnings.append(f"僅 {len(usable_eps_anchors)} 個財報年度 EPS 錨點，河流圖以階梯狀延伸而非連續每日數列")

    return {
        "enabled": True,
        "market": "us",
        "symbol": symbol,
        "currency": currency or "USD",
        "source": "yfinance",
        "method": "us_reported_eps_annual_river",
        "basis": "reported_eps",
        "eps_kind": "reported",
        "eps_source": "yfinance",
        "eps_period": "annual",
        "band_multiples": list(PER_BAND_MULTIPLES),
        "neutral_multiple": NEUTRAL_MULTIPLE,
        "as_of": last["date"],
        "range": {
            "start_date": points[0]["date"],
            "end_date": last["date"],
            "trading_days": len(points),
        },
        "points": points,
        "current": {
            "close": last["close"],
            "per": last.get("per"),
            "pbr": last.get("pbr"),
            "implied_eps": last.get("implied_eps"),
            "implied_bvps": last.get("implied_bvps"),
            "zone": current_zone,
            "eps_actual": eps_actual,
            "eps_forward": eps_forward_stat,
        },
        "quality": {
            "status": status,
            "warnings": warnings,
            "codes": codes,
            "data_gap_fields": (["bvps"] if not usable_bvps_anchors else []),
            "methodology_note": METHODOLOGY_NOTE_US,
        },
    }

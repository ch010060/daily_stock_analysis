# -*- coding: utf-8 -*-
"""
TW market review formatter — convert TaiwanMarketDataFetcher snapshot to zh_TW markdown.

No LLM calls. No live provider calls. Pure data formatting.
Input:  dict from TaiwanMarketDataFetcher.get_tw_market_snapshot()
Output: zh_TW markdown string.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

_INSTITUTIONAL_NAME_MAP: List[tuple] = [
    ("Foreign_Investor", "外資"),
    ("Investment_Trust", "投信"),
    ("Dealer_self", "自營商"),
    ("Dealer_Hedging", "自營商（避險）"),
    ("total", "合計"),
]

_MARGIN_NAME_MAP: List[tuple] = [
    ("MarginPurchaseMoney", "融資"),
    ("ShortSaleMoney", "融券"),
    ("ShortSaleVolume", "融券（張數）"),
]


def build_tw_market_review_context(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured context dict from TaiwanMarketDataFetcher snapshot."""
    taiex = snapshot.get("taiex") or {}
    tpex = snapshot.get("tpex") or {}
    institutional = snapshot.get("institutional_total") or {}
    margin = snapshot.get("margin_total") or {}
    ref_0050 = snapshot.get("ref_0050") or {}
    ref_2330 = snapshot.get("ref_2330") or {}
    availability = snapshot.get("availability") or {}

    taiex_rows = taiex.get("rows") or []
    tpex_rows = tpex.get("rows") or []
    institutional_rows = institutional.get("rows") or []
    margin_rows = margin.get("rows") or []
    rows_0050 = ref_0050.get("rows") or []
    rows_2330 = ref_2330.get("rows") or []

    taiex_last = taiex_rows[-1] if taiex_rows else {}
    taiex_prev = taiex_rows[-2] if len(taiex_rows) >= 2 else {}
    tpex_last = tpex_rows[-1] if tpex_rows else {}
    tpex_prev = tpex_rows[-2] if len(tpex_rows) >= 2 else {}

    institutional_latest: Dict[str, Any] = {}
    if institutional_rows:
        latest_date = max(r.get("date", "") for r in institutional_rows)
        for row in institutional_rows:
            if row.get("date") == latest_date:
                institutional_latest[row.get("name", "")] = row

    margin_latest: Dict[str, Any] = {}
    if margin_rows:
        latest_date = max(r.get("date", "") for r in margin_rows)
        for row in margin_rows:
            if row.get("date") == latest_date:
                margin_latest[row.get("name", "")] = row

    return {
        "taiex_ok": bool(taiex.get("ok")),
        "taiex_last": taiex_last,
        "taiex_prev": taiex_prev,
        "taiex_source": taiex.get("source", ""),
        "tpex_ok": bool(tpex.get("ok")),
        "tpex_last": tpex_last,
        "tpex_prev": tpex_prev,
        "tpex_unavailable": bool(tpex.get("unavailable_reason")),
        "institutional_ok": bool(institutional.get("ok")),
        "institutional_latest": institutional_latest,
        "margin_ok": bool(margin.get("ok")),
        "margin_latest": margin_latest,
        "ref_0050_ok": bool(ref_0050.get("ok")),
        "last_0050": rows_0050[-1] if rows_0050 else {},
        "ref_2330_ok": bool(ref_2330.get("ok")),
        "last_2330": rows_2330[-1] if rows_2330 else {},
        "availability": availability,
        "required_ok": bool(availability.get("required_ok")),
        "as_of": availability.get("as_of", ""),
    }


def render_tw_market_review_text(
    snapshot: Dict[str, Any],
    profile: Optional[Any] = None,
) -> str:
    """
    Render zh_TW market review markdown from a TaiwanMarketDataFetcher snapshot.

    No LLM call. No live provider call. Pure data formatting.
    """
    ctx = build_tw_market_review_context(snapshot)
    availability = ctx["availability"]
    as_of = ctx["as_of"] or datetime.now().strftime("%Y-%m-%d")

    sections: List[str] = []

    # Title
    sections.append(f"# 台股大盤回顧\n\n> 資料日期：{as_of}")

    # 今日盤勢摘要
    if ctx["required_ok"]:
        summary = "今日所有必要指標資料完整，可進行完整分析。"
    else:
        missing = availability.get("missing_required") or []
        summary = f"部分必要資料缺失（{', '.join(missing)}），分析資料不完整。"
    sections.append(f"## 今日盤勢摘要\n\n{summary}")

    # 指數表現
    index_lines: List[str] = []
    if ctx["taiex_ok"] and ctx["taiex_last"]:
        price = ctx["taiex_last"].get("price")
        prev_price = ctx["taiex_prev"].get("price") if ctx["taiex_prev"] else None
        if price is not None and prev_price is not None:
            change = float(price) - float(prev_price)
            pct = change / float(prev_price) * 100 if float(prev_price) != 0 else 0.0
            arrow = "🟢" if change >= 0 else "🔴"
            index_lines.append(
                f"- 加權報酬指數（TAIEX）：{float(price):,.2f} 點 {arrow} {change:+.2f}（{pct:+.2f}%）"
            )
        else:
            index_lines.append(f"- 加權報酬指數（TAIEX）：{price} 點")
    else:
        index_lines.append("- 加權報酬指數（TAIEX）：資料暫不可用")

    if ctx["tpex_ok"] and ctx["tpex_last"]:
        price = ctx["tpex_last"].get("price")
        prev_price = ctx["tpex_prev"].get("price") if ctx["tpex_prev"] else None
        if price is not None and prev_price is not None:
            change = float(price) - float(prev_price)
            pct = change / float(prev_price) * 100 if float(prev_price) != 0 else 0.0
            arrow = "🟢" if change >= 0 else "🔴"
            index_lines.append(
                f"- 櫃買報酬指數（TPEx）：{float(price):,.2f} 點 {arrow} {change:+.2f}（{pct:+.2f}%）"
            )
        else:
            index_lines.append(f"- 櫃買報酬指數（TPEx）：{price} 點")
    elif ctx["tpex_unavailable"]:
        index_lines.append(
            "- 櫃買報酬指數（TPEx）：資料暫不可用，本段略過，未 fallback 至其他市場"
        )
    else:
        index_lines.append("- 櫃買報酬指數（TPEx）：資料暫不可用")

    sections.append("## 指數表現\n\n" + "\n".join(index_lines))

    # 法人與資金面
    inst_lines: List[str] = []
    if ctx["institutional_ok"] and ctx["institutional_latest"]:
        for name_key, zh_label in _INSTITUTIONAL_NAME_MAP:
            row = ctx["institutional_latest"].get(name_key)
            if row:
                buy = float(row.get("buy") or 0) / 1e8
                sell = float(row.get("sell") or 0) / 1e8
                net = buy - sell
                arrow = "▲" if net >= 0 else "▼"
                inst_lines.append(
                    f"- {zh_label}：買 {buy:,.1f} 億，賣 {sell:,.1f} 億，淨 {arrow} {abs(net):,.1f} 億"
                )
    else:
        inst_lines.append("- 三大法人資料暫不可用，本段略過，未 fallback 至其他市場")

    sections.append("## 法人與資金面\n\n" + "\n".join(inst_lines))

    # 融資融券觀察
    margin_lines: List[str] = []
    if ctx["margin_ok"] and ctx["margin_latest"]:
        for name_key, zh_label in _MARGIN_NAME_MAP:
            row = ctx["margin_latest"].get(name_key)
            if row:
                today_raw = float(row.get("TodayBalance") or 0)
                yes_raw = float(row.get("YesBalance") or 0)
                change_raw = today_raw - yes_raw
                arrow = "▲" if change_raw >= 0 else "▼"
                if name_key == "ShortSaleVolume":
                    margin_lines.append(
                        f"- {zh_label}：今日 {today_raw:,.0f} 張，較昨日 {arrow} {abs(change_raw):,.0f} 張"
                    )
                else:
                    today = today_raw / 1e8
                    change = change_raw / 1e8
                    margin_lines.append(
                        f"- {zh_label}：今日 {today:,.1f} 億，較昨日 {arrow} {abs(change):,.1f} 億"
                    )
    else:
        margin_lines.append("- 融資融券資料暫不可用，本段略過，未 fallback 至其他市場")

    sections.append("## 融資融券觀察\n\n" + "\n".join(margin_lines))

    # 0050 / 臺積電參考
    ref_lines: List[str] = []
    if ctx["ref_0050_ok"] and ctx["last_0050"]:
        close = ctx["last_0050"].get("close", "N/A")
        date = ctx["last_0050"].get("date", "")
        ref_lines.append(f"- 元大台灣50（0050）：收盤 {close}（{date}）")
    else:
        ref_lines.append("- 元大台灣50（0050）：資料暫不可用")

    if ctx["ref_2330_ok"] and ctx["last_2330"]:
        close = ctx["last_2330"].get("close", "N/A")
        date = ctx["last_2330"].get("date", "")
        ref_lines.append(f"- 臺積電（2330）：收盤 {close}（{date}）")
    else:
        ref_lines.append("- 臺積電（2330）：資料暫不可用")

    sections.append("## 0050 / 臺積電參考\n\n" + "\n".join(ref_lines))

    # 風險與注意事項
    sections.append(
        "## 風險與注意事項\n\n"
        "- 市場有風險，投資需謹慎。以上資料僅供參考，不構成投資建議。"
    )

    # 資料可用性說明
    avail_lines: List[str] = []
    sources = availability.get("sources") or []
    missing_req = availability.get("missing_required") or []
    missing_opt = availability.get("missing_optional") or []

    if sources:
        avail_lines.append(f"- 資料來源：{', '.join(sources)}")
    if missing_req:
        avail_lines.append(f"- 缺少必要資料：{', '.join(missing_req)}")
    if missing_opt:
        avail_lines.append(f"- 缺少選擇性資料：{', '.join(missing_opt)}")
    if not missing_req and not missing_opt:
        avail_lines.append("- 全部資料段均可用。")

    sections.append("## 資料可用性說明\n\n" + "\n".join(avail_lines))

    return "\n\n".join(sections)

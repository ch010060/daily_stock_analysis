# -*- coding: utf-8 -*-
"""Route B zh_TW localization: convert known simplified Chinese terms to Traditional Chinese.

Apply at report output boundaries only (file save, notification send).
Do not apply to internal raw data, JSON snapshots, or log messages.
"""

from __future__ import annotations

import re
from typing import Optional

# Ordered pairs (simplified → traditional).
# Longer / more-specific strings first to avoid partial-match collisions.
_ZH_TW_TERM_MAP: tuple[tuple[str, str], ...] = (
    # Multi-character phrases first (longest match takes priority)
    ("決策儀表盤", "決策儀錶板"),
    ("大盤覆盤", "大盤回顧"),
    ("大盤復盤", "大盤回顧"),
    ("資產負債表", "資產負債表"),
    ("現金流量表", "現金流量表"),
    ("機構投資者", "法人投資人"),
    ("三大法人", "三大法人"),
    ("融資融券", "融資融券"),
    ("成交額", "成交金額"),
    ("漲跌幅", "漲跌幅"),
    ("市盈率", "本益比"),
    ("市淨率", "股價淨值比"),
    ("股息率", "殖利率"),
    ("主力資金", "主力資金"),
    ("淨利潤", "淨利潤"),
    ("毛利率", "毛利率"),
    ("換手率", "換手率"),
    ("量比", "量比"),
    ("振幅", "振幅"),
    ("復權", "還權"),
    ("除權息", "除權息"),
    ("均線排列", "均線排列"),
    ("多頭排列", "多頭排列"),
    ("空頭排列", "空頭排列"),
    ("乖離率", "乖離率"),
    ("歷史記錄", "歷史記錄"),
    ("操作建議", "操作建議"),
    ("持股建議", "持股建議"),
    ("建倉策略", "建倉策略"),
    ("風控策略", "風控策略"),
    ("止損位", "停損位"),
    ("止盈目標", "停利目標"),
    ("目標位", "目標位"),
    ("部位建議", "部位建議"),
    # 2-character / shorter terms
    ("大盤", "大盤"),
    ("覆盤", "回顧"),
    ("決策", "決策"),
    ("儀表盤", "儀錶板"),
    ("觀望", "觀望"),
    ("評分", "評分"),
    ("風險", "風險"),
    ("建議", "建議"),
    ("標普", "標普"),
    ("指數", "指數"),
    ("市場", "市場"),
    ("報告", "報告"),
    ("資料", "資料"),
    ("無法", "無法"),
    ("萬股", "萬股"),
    ("億元", "億元"),
    ("專業", "專業"),
    ("預測", "預測"),
    ("資金", "資金"),
    ("買進", "買進"),
    ("賣出", "賣出"),
    ("上漲", "上漲"),
    ("下跌", "下跌"),
    ("趨勢", "趨勢"),
    ("壓力", "壓力"),
    ("支撐", "支撐"),
    ("漲幅", "漲幅"),
    ("跌幅", "跌幅"),
    ("財報", "財報"),
    ("營收", "營收"),
    ("淨利", "淨利"),
    ("現金流", "現金流"),
    ("股息", "股利"),
    ("分紅", "配息"),
    ("減倉", "減碼"),
    ("加倉", "加碼"),
    ("空倉", "空倉"),
    ("持股", "持股"),
    ("歷史", "歷史"),
    ("診斷", "診斷"),
    ("設定", "設定"),
    ("設定", "設定"),
    ("記錄", "記錄"),
    ("來源", "來源"),
    ("型別", "型別"),
    ("時間", "時間"),
    ("檢查", "檢查"),
    ("清單", "清單"),
    ("階段", "階段"),
    ("計劃", "計畫"),
    ("訊號", "訊號"),
    ("情緒", "情緒"),
    ("催化", "催化"),
    ("摘要", "摘要"),
    ("機率", "機率"),
    ("分析", "分析"),
)

# Protect code spans, fenced blocks, URLs, and stock symbols from substitution.
_PROTECT_RE = re.compile(
    r"(```[\s\S]*?```"              # fenced code block
    r"|`[^`\n]*`"                   # inline code
    r"|https?://\S+"                # URLs
    r"|(?:TW|US|HK|CN|SZ|SH):[A-Z0-9.\-]+"  # stock symbols
    r")",
    re.MULTILINE,
)


def localize_route_b_zh_tw_text(text: Optional[str]) -> str:
    """Convert simplified Chinese financial terms to Traditional Chinese equivalents.

    Preserves fenced code blocks, inline code, URLs, and stock symbol tokens.
    Returns an empty string for None or empty input.
    """
    if not text:
        return ""

    # Split on protected spans; even indices = plain text, odd = protected.
    parts = _PROTECT_RE.split(text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            for simplified, traditional in _ZH_TW_TERM_MAP:
                part = part.replace(simplified, traditional)
        out.append(part)
    return "".join(out)


def is_route_b_zh_tw_active() -> bool:
    """Return True when Route B market-scope enforcement is enabled."""
    try:
        from src.config import get_config
        config = get_config()
        return bool(getattr(config, "route_b_enforce_market_scope", False))
    except Exception:
        return False


def localize_if_route_b(text: Optional[str]) -> str:
    """Apply zh_TW localization only when Route B is active; otherwise return text as-is."""
    if not is_route_b_zh_tw_active():
        return text or ""
    return localize_route_b_zh_tw_text(text)

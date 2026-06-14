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
    # Multi-character phrases first
    ("决策仪表盘", "決策儀表板"),
    ("大盘复盘", "大盤回顧"),
    ("大盤復盤", "大盤回顧"),
    # 2-character terms
    ("大盘", "大盤"),
    ("复盘", "回顧"),
    ("决策", "決策"),
    ("仪表盘", "儀表板"),
    ("观望", "觀望"),
    ("评分", "評分"),
    ("风险", "風險"),
    ("建议", "建議"),
    ("标普", "標普"),
    ("指数", "指數"),
    ("市场", "市場"),
    ("报告", "報告"),
    ("数据", "資料"),
    ("无法", "無法"),
    ("万股", "萬股"),
    ("亿元", "億元"),
    ("专业", "專業"),
    ("预测", "預測"),
    ("资金", "資金"),
    ("买入", "買入"),
    ("卖出", "賣出"),
    ("上涨", "上漲"),
    ("下跌", "下跌"),
    ("趋势", "趨勢"),
    ("压力", "壓力"),
    ("支撑", "支撐"),
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

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
    ("决策仪表盘", "決策儀表板"),
    ("大盘复盘", "大盤回顧"),
    ("大盤復盤", "大盤回顧"),
    ("资产负债表", "資產負債表"),
    ("现金流量表", "現金流量表"),
    ("机构投资者", "法人投資人"),
    ("三大法人", "三大法人"),
    ("融资融券", "融資融券"),
    ("成交额", "成交金額"),
    ("涨跌幅", "漲跌幅"),
    ("市盈率", "本益比"),
    ("市净率", "股價淨值比"),
    ("股息率", "殖利率"),
    ("主力资金", "主力資金"),
    ("净利润", "淨利潤"),
    ("毛利率", "毛利率"),
    ("换手率", "換手率"),
    ("量比", "量比"),
    ("振幅", "振幅"),
    ("复权", "還權"),
    ("除权息", "除權息"),
    ("均线排列", "均線排列"),
    ("多头排列", "多頭排列"),
    ("空头排列", "空頭排列"),
    ("乖离率", "乖離率"),
    ("历史记录", "歷史記錄"),
    ("操作建议", "操作建議"),
    ("持仓建议", "持倉建議"),
    ("建仓策略", "建倉策略"),
    ("风控策略", "風控策略"),
    ("止损位", "停損位"),
    ("止盈目标", "停利目標"),
    ("目标位", "目標位"),
    ("仓位建议", "倉位建議"),
    # 2-character / shorter terms
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
    ("涨幅", "漲幅"),
    ("跌幅", "跌幅"),
    ("财报", "財報"),
    ("营收", "營收"),
    ("净利", "淨利"),
    ("现金流", "現金流"),
    ("股息", "股利"),
    ("分红", "配息"),
    ("减仓", "減碼"),
    ("加仓", "加碼"),
    ("空仓", "空倉"),
    ("持仓", "持倉"),
    ("历史", "歷史"),
    ("诊断", "診斷"),
    ("设置", "設定"),
    ("设定", "設定"),
    ("记录", "記錄"),
    ("来源", "來源"),
    ("类型", "類型"),
    ("时间", "時間"),
    ("检查", "檢查"),
    ("清单", "清單"),
    ("阶段", "階段"),
    ("计划", "計畫"),
    ("信号", "訊號"),
    ("情绪", "情緒"),
    ("催化", "催化"),
    ("摘要", "摘要"),
    ("概率", "機率"),
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

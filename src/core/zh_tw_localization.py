# -*- coding: utf-8 -*-
"""Route B zh_TW localization: convert known simplified Chinese financial terms to Traditional Chinese.

Apply at report output boundaries only (file save, notification send).
Do not apply to internal raw data, JSON snapshots, or log messages.

Terminology follows Taiwan financial conventions:
- \u4e70\u5165 (buy) \u2192 \u8cb7\u9032
- \u638c\u63e1 (watch) \u2192 \u89c0\u671b
- \u5e02\u76c8\u7387 (P/E) \u2192 \u672c\u76ca\u6bd4
"""

from __future__ import annotations

import re
from typing import Optional

# Ordered pairs (simplified \u2192 traditional).
# Use unicode escapes for Simplified characters to keep source audit-clean.
# Longer / more-specific strings first to avoid partial-match collisions.
_ZH_TW_TERM_MAP: tuple[tuple[str, str], ...] = (
    ("\u51b3\u7b56\u4eea\u8868\u76d8", "\u6c7a\u7b56\u5100\u9336\u677f"),
    ("\u5927\u76e4\u590d\u76d8", "\u5927\u76e4\u56de\u9867"),
    ("\u5927\u76e4\u8986\u76d8", "\u5927\u76e4\u56de\u9867"),
    ("\u8d44\u4ea7\u8d1f\u503a\u8868", "\u8cc7\u7522\u8ca0\u50b5\u8868"),
    ("\u73b0\u91d1\u6d41\u91cf\u8868", "\u73fe\u91d1\u6d41\u91cf\u8868"),
    ("\u673a\u6784\u6295\u8d44\u8005", "\u6cd5\u4eba\u6295\u8cc7\u4eba"),
    ("\u4e09\u5927\u6cd5\u4eba", "\u4e09\u5927\u6cd5\u4eba"),
    ("\u878d\u8d44\u878d\u5238", "\u878d\u8cc7\u878d\u5238"),
    ("\u6210\u4ea4\u989d", "\u6210\u4ea4\u91d1\u984d"),
    ("\u6da8\u8dcc\u5e45", "\u6f32\u8dcc\u5e45"),
    ("\u5e02\u76c8\u7387", "\u672c\u76ca\u6bd4"),
    ("\u5e02\u51c0\u7387", "\u80a1\u50f9\u6de8\u503c\u6bd4"),
    ("\u80a1\u606f\u7387", "\u6b96\u5229\u7387"),
    ("\u4e3b\u529b\u8d44\u91d1", "\u4e3b\u529b\u8cc7\u91d1"),
    ("\u51c0\u5229\u6da6", "\u6de8\u5229"),
    ("\u6bdb\u5229\u7387", "\u6bdb\u5229\u7387"),
    ("\u6362\u624b\u7387", "\u63db\u624b\u7387"),
    ("\u91cf\u6bd4", "\u91cf\u6bd4"),
    ("\u632f\u5e45", "\u632f\u5e45"),
    ("\u590d\u6743", "\u9084\u6b0a"),
    ("\u9664\u6743\u606f", "\u9664\u6b0a\u606f"),
    ("\u5747\u7ebf\u6392\u5217", "\u5747\u7dda\u6392\u5217"),
    ("\u591a\u5934\u6392\u5217", "\u591a\u982d\u6392\u5217"),
    ("\u7a7a\u5934\u6392\u5217", "\u7a7a\u982d\u6392\u5217"),
    ("\u4e56\u79bb\u7387", "\u4e56\u96e2\u7387"),
    ("\u5386\u53f2\u8bb0\u5f55", "\u6b77\u53f2\u8a18\u9304"),
    ("\u64cd\u4f5c\u5efa\u8bae", "\u64cd\u4f5c\u5efa\u8b70"),
    ("\u6301\u80a1\u5efa\u8bae", "\u6301\u80a1\u5efa\u8b70"),
    ("\u5efa\u4ed3\u7b56\u7565", "\u5efa\u5009\u7b56\u7565"),
    ("\u98ce\u63a7\u7b56\u7565", "\u98a8\u63a7\u7b56\u7565"),
    ("\u6b62\u635f\u4f4d", "\u505c\u640d\u4f4d"),
    ("\u6b62\u76c8\u76ee\u6807", "\u505c\u5229\u76ee\u6a19"),
    ("\u76ee\u6807\u4f4d", "\u76ee\u6a19\u4f4d"),
    ("\u90e8\u4f4d\u5efa\u8bae", "\u90e8\u4f4d\u5efa\u8b70"),
    # 2-char / shorter terms
    ("\u5927\u76d8", "\u5927\u76e4"),
    ("\u590d\u76d8", "\u56de\u9867"),
    ("\u51b3\u7b56", "\u6c7a\u7b56"),
    ("\u4eea\u8868\u76d8", "\u5100\u9336\u677f"),
    ("\u89c2\u671b", "\u89c0\u671b"),
    ("\u8bc4\u5206", "\u8a55\u5206"),
    ("\u98ce\u9669", "\u98a8\u96aa"),
    ("\u5efa\u8bae", "\u5efa\u8b70"),
    ("\u6807\u666e", "\u6a19\u666e"),
    ("\u6307\u6570", "\u6307\u6578"),
    ("\u5e02\u573a", "\u5e02\u5834"),
    ("\u62a5\u544a", "\u5831\u544a"),
    ("\u8d44\u6599", "\u8cc7\u6599"),
    ("\u65e0\u6cd5", "\u7121\u6cd5"),
    ("\u4e07\u80a1", "\u842c\u80a1"),
    ("\u4ebf\u5143", "\u5104\u5143"),
    ("\u4e13\u4e1a", "\u5c08\u696d"),
    ("\u9884\u6d4b", "\u9810\u6e2c"),
    ("\u8d44\u91d1", "\u8cc7\u91d1"),
    ("\u4e70\u5165", "\u8cb7\u9032"),
    ("\u5356\u51fa", "\u8ce3\u51fa"),
    ("\u4e0a\u6da8", "\u4e0a\u6f32"),
    ("\u4e0b\u8dcc", "\u4e0b\u8dcc"),
    ("\u8d8b\u52bf", "\u8da8\u52e2"),
    ("\u538b\u529b", "\u58d3\u529b"),
    ("\u652f\u6491", "\u652f\u6490"),
    ("\u6da8\u5e45", "\u6f32\u5e45"),
    ("\u8dcc\u5e45", "\u8dcc\u5e45"),
    ("\u8d22\u62a5", "\u8ca1\u5831"),
    ("\u8425\u6536", "\u71df\u6536"),
    ("\u51c0\u5229", "\u6de8\u5229"),
    ("\u73b0\u91d1\u6d41", "\u73fe\u91d1\u6d41"),
    ("\u80a1\u606f", "\u80a1\u5229"),
    ("\u5206\u7ea2", "\u914d\u606f"),
    ("\u51cf\u4ed3", "\u6e1b\u78bc"),
    ("\u52a0\u4ed3", "\u52a0\u78bc"),
    ("\u7a7a\u4ed3", "\u7a7a\u5009"),
    ("\u6301\u4ed3", "\u6301\u80a1"),
    ("\u5386\u53f2", "\u6b77\u53f2"),
    ("\u8bca\u65ad", "\u8a3a\u65b7"),
    ("\u8bbe\u7f6e", "\u8a2d\u5b9a"),
    ("\u8bbe\u5b9a", "\u8a2d\u5b9a"),
    ("\u8bb0\u5f55", "\u8a18\u9304"),
    ("\u6765\u6e90", "\u4f86\u6e90"),
    ("\u7c7b\u578b", "\u985e\u578b"),
    ("\u65f6\u95f4", "\u6642\u9593"),
    ("\u68c0\u67e5", "\u6aa2\u67e5"),
    ("\u6e05\u5355", "\u6e05\u55ae"),
    ("\u9636\u6bb5", "\u968e\u6bb5"),
    ("\u8ba1\u5212", "\u8a08\u756b"),
    ("\u4fe1\u53f7", "\u8a0a\u865f"),
    ("\u60c5\u7eea", "\u60c5\u7dd2"),
    ("\u50ac\u5316", "\u50ac\u5316"),
    ("\u6458\u8981", "\u6458\u8981"),
    ("\u673a\u7387", "\u6a5f\u7387"),
    ("\u5206\u6790", "\u5206\u6790"),
    ("\u9707\u8361", "\u9707\u76ea"),
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

# -*- coding: utf-8 -*-
"""
Market context detection for LLM prompts.

Detects the Route B market (TW/US) from a stock code and returns
market-specific role descriptions so prompts are not hardcoded to a
single market.

Fixes: https://github.com/ZhuLinsen/daily_stock_analysis/issues/644
"""

import re
from typing import Optional


def detect_market(stock_code: Optional[str]) -> str:
    """Detect market from stock code.

    Returns:
        One of 'tw', 'us', or 'route_b' as fallback.
    """
    if not stock_code:
        return "route_b"

    code = stock_code.strip().upper()

    if code.startswith("TW:"):
        return "tw"
    if code.startswith("US:"):
        return "us"
    if code.endswith(".TW"):
        return "tw"
    if code.endswith(".US"):
        return "us"

    if re.match(r"^\d{4,6}[A-Z]?$", code):
        return "tw"

    # US stocks: 1-5 uppercase letters (AAPL, TSLA, GOOGL)
    # Also handles suffixed forms like BRK.B
    if re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', code):
        return "us"

    return "route_b"


# -- Market-specific role descriptions --

_MARKET_ROLES = {
    "route_b": {
        "zh": "台股 / 美股",
        "en": "Taiwan and US stock",
    },
    "tw": {
        "zh": "台股",
        "en": "Taiwan stock",
    },
    "us": {
        "zh": "美股",
        "en": "US stock",
    },
}

_MARKET_GUIDELINES = {
    "route_b": {
        "zh": (
            "- 本次問答支援 **TW/US** 標的，請先使用系統提供的本地解析上下文確認標的。\n"
            "- 可依資料可用性分析台灣與美國市場標的；資料缺漏時說明降級來源，但仍需回答使用者問題。"
        ),
        "en": (
            "- This chat supports **TW/US** symbols. Use the provided local-resolution context to confirm the target.\n"
            "- Analyze Taiwan and US listings when data is available; disclose degraded data sources without refusing the question."
        ),
    },
    "tw": {
        "zh": (
            "- 本次分析物件為 **TW 台股** 標的。\n"
            "- 請關注台灣市場交易制度、法人籌碼、產業鏈位置、匯率與國際科技循環對標的的影響。"
        ),
        "en": (
            "- This analysis covers a **TW Taiwan stock**.\n"
            "- Consider Taiwan market structure, institutional flows, supply-chain exposure, FX, and global tech-cycle impact."
        ),
    },
    "us": {
        "zh": (
            "- 本次分析物件為 **美股**（美國交易所上市股票）。\n"
            "- 美股無漲跌停限制（但有熔斷機制），支援 T+0 交易和盤前盤後交易，需關注美元匯率、美聯儲政策及 SEC 監管動態。"
        ),
        "en": (
            "- This analysis covers a **US stock** (listed on NYSE/NASDAQ).\n"
            "- US stocks have no daily price limits (but have circuit breakers), allow T+0 and pre/after-market trading. Consider USD FX, Fed policy, and SEC regulations."
        ),
    },
}


def get_market_role(stock_code: Optional[str], lang: str = "zh") -> str:
    """Return market-specific role description for LLM prompt.

    Args:
        stock_code: The stock code being analyzed.
        lang: 'zh' or 'en'.

    Returns:
        Role string like '台股投資分析' or 'US stock investment analysis'.
    """
    market = detect_market(stock_code)
    lang_key = "en" if lang == "en" else "zh"
    return _MARKET_ROLES.get(market, _MARKET_ROLES["route_b"])[lang_key]


def get_market_guidelines(stock_code: Optional[str], lang: str = "zh") -> str:
    """Return market-specific analysis guidelines for LLM prompt.

    Args:
        stock_code: The stock code being analyzed.
        lang: 'zh' or 'en'.

    Returns:
        Multi-line string with market-specific guidelines.
    """
    market = detect_market(stock_code)
    lang_key = "en" if lang == "en" else "zh"
    return _MARKET_GUIDELINES.get(market, _MARKET_GUIDELINES["route_b"])[lang_key]

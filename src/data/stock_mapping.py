# -*- coding: utf-8 -*-
from __future__ import annotations

"""
===================================
股票代號與名稱對映
===================================

Shared stock code -> name mapping, used by analyzer, data_provider, and name_to_code_resolver.
"""

# Stock code -> name mapping (common stocks)
STOCK_NAME_MAP = {
    # === TW stocks ===
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "3008": "大立光",
    "8299": "群聯",
    # === US stocks ===
    "AAPL": "Apple",
    "TSLA": "Tesla",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet Class A",
    "GOOG": "Alphabet Class C",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "META": "Meta Platforms",
    "SPY": "SPDR S&P 500 ETF",
    "SPX": "標普500指數",
    "AMD": "AMD",
    "INTC": "Intel",
    "COIN": "Coinbase",
    "MSTR": "MicroStrategy",
}


def is_meaningful_stock_name(name: str | None, stock_code: str) -> bool:
    """Return whether a stock name is useful for display or caching."""
    if not name:
        return False

    normalized_name = str(name).strip()
    if not normalized_name:
        return False

    normalized_code = (stock_code or "").strip().upper()
    if normalized_name.upper() == normalized_code:
        return False

    if normalized_name.startswith("股票"):
        return False

    placeholder_values = {
        "N/A",
        "NA",
        "NONE",
        "NULL",
        "--",
        "-",
        "UNKNOWN",
        "TICKER",
    }
    if normalized_name.upper() in placeholder_values:
        return False

    return True

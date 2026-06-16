# -*- coding: utf-8 -*-
"""Route B runtime scope gate: TW/US market enforcement.

Classifies stock symbols by market, filters non-TW/US symbols under Route B
enforce mode, and raises a descriptive error when the accepted watchlist is empty.
Provider-name helpers allow callers to skip CN-only data providers without
calling into them.
"""

import logging
import os
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Providers that exclusively serve CN/A-share markets
_CN_PROVIDERS = frozenset({"EfinanceFetcher", "AkshareFetcher", "BaostockFetcher", "PytdxFetcher"})

# Symbol classification patterns
_US_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z])?$")
_CN_6DIGIT_RE = re.compile(r"^\d{6}$")
_TW_4DIGIT_RE = re.compile(r"^\d{4}$")
_HK_PREFIX_RE = re.compile(r"^HK\d{4,5}$")
_HK_SUFFIX_RE = re.compile(r"^\d{4,5}\.HK$", re.IGNORECASE)


class RouteBScopeError(ValueError):
    """Raised when Route B scope validation fails (empty TW/US watchlist)."""


def is_route_b_enforced(config=None) -> bool:
    """Return True when ROUTE_B_ENFORCE_MARKET_SCOPE is active."""
    if config is not None:
        return bool(getattr(config, "route_b_enforce_market_scope", False))
    raw = os.getenv("ROUTE_B_ENFORCE_MARKET_SCOPE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_route_b_markets(config=None) -> frozenset:
    """Return the set of allowed markets under Route B (uppercase, e.g. {'TW', 'US'})."""
    if config is not None:
        markets = getattr(config, "route_b_markets", None)
        if markets:
            return frozenset(m.strip().upper() for m in markets if m.strip())
    raw = os.getenv("ROUTE_B_MARKETS", "TW,US")
    return frozenset(m.strip().upper() for m in raw.split(",") if m.strip())


def classify_symbol(code: str) -> str:
    """Classify a stock symbol as 'TW', 'US', 'HK', 'CN', or 'UNKNOWN'.

    Detection order (first match wins):
    - Explicit TW: prefix or .TW suffix → TW
    - Explicit US: prefix → US
    - HK prefix (HK01810) or .HK suffix (1810.HK) → HK
    - Pure alphabetic 1-5 char ticker (AAPL, BRK.B) → US
    - 6 pure digits (600519) → CN
    - Anything else → UNKNOWN
    """
    upper = (code or "").strip().upper()
    if not upper:
        return "UNKNOWN"
    if upper.startswith("TW:"):
        return "TW"
    if upper.endswith(".TW"):
        return "TW"
    if upper.startswith("US:"):
        return "US"
    if _HK_PREFIX_RE.fullmatch(upper):
        return "HK"
    if _HK_SUFFIX_RE.fullmatch(upper):
        return "HK"
    if _TW_4DIGIT_RE.fullmatch(upper):
        return "TW"
    if _US_TICKER_RE.fullmatch(upper):
        return "US"
    if _CN_6DIGIT_RE.fullmatch(upper):
        return "CN"
    return "UNKNOWN"


def filter_stocks_for_route_b(
    stock_codes: List[str],
    config=None,
) -> Tuple[List[str], List[str]]:
    """Filter stock codes under Route B enforcement.

    Returns:
        (accepted, rejected) where accepted contains TW/US symbols and rejected
        contains all others (CN, HK, UNKNOWN).
    """
    allowed_markets = get_route_b_markets(config)
    accepted: List[str] = []
    rejected: List[str] = []
    for code in stock_codes:
        market = classify_symbol(code)
        if market in allowed_markets:
            accepted.append(code)
        else:
            rejected.append(code)
            logger.warning(
                "[Route B] Rejected symbol %r (market=%s). "
                "Only %s are allowed under Route B enforce mode.",
                code,
                market,
                "/".join(sorted(allowed_markets)),
            )
    return accepted, rejected


def validate_route_b_watchlist(
    stock_codes: List[str],
    config=None,
) -> List[str]:
    """Validate and filter stocks under Route B; raise RouteBScopeError when empty.

    Returns accepted TW/US stock codes.
    Raises:
        RouteBScopeError: when no TW/US symbols remain after filtering.
    """
    accepted, _rejected = filter_stocks_for_route_b(stock_codes, config)
    if not accepted:
        allowed_markets = get_route_b_markets(config)
        label = "/".join(sorted(allowed_markets))
        raise RouteBScopeError(
            f"No {label} watchlist configured. "
            f"Set --stocks or STOCK_LIST with {label} symbols."
        )
    return accepted


def is_cn_provider(provider_name: str) -> bool:
    """Return True if the named fetcher exclusively serves CN/A-share markets."""
    return provider_name in _CN_PROVIDERS

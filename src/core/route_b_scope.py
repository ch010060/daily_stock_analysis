# -*- coding: utf-8 -*-
"""Route B runtime scope gate: TW/US market enforcement."""

import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Providers that are outside the active TW/US route.
_NON_ROUTE_B_PROVIDERS = frozenset({"EfinanceFetcher", "AkshareFetcher", "BaostockFetcher", "PytdxFetcher"})


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
    """Classify a stock symbol using the local TW/US symbol universe."""
    text = (code or "").strip()
    if not text:
        return "UNKNOWN"
    try:
        from src.services.symbol_universe import get_default_symbol_resolver

        result = get_default_symbol_resolver().resolve(text)
    except Exception:
        return "UNKNOWN"
    if result.status == "resolved" and result.selected is not None:
        return result.selected.market
    return "UNKNOWN"


def filter_stocks_for_route_b(
    stock_codes: List[str],
    config=None,
) -> Tuple[List[str], List[str]]:
    """Filter stock codes under Route B enforcement.

    Returns:
        (accepted, rejected) where accepted contains TW/US symbols and rejected
        contains all other unsupported inputs.
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


def is_non_route_b_provider(provider_name: str) -> bool:
    """Return True if the named fetcher is outside the active TW/US route."""
    return provider_name in _NON_ROUTE_B_PROVIDERS

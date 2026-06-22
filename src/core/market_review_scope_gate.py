# -*- coding: utf-8 -*-
"""Market review region scope gate for Route B TW/US enforcement.

Resolves which market review regions are allowed to run under Route B enforce mode.
CN/HK regions are always blocked; US and TW are accepted when supported.
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Internal region codes that have a working market review implementation
_IMPLEMENTED_REGIONS = frozenset({"us", "tw"})
# Internal region codes that are recognised but not yet implemented
_DEFERRED_REGIONS = frozenset()
# Internal region codes that are blocked under Route B
_CN_REGIONS = frozenset({"cn", "hk"})

# Mapping from Route B market name (uppercase) to internal region code (lowercase)
_MARKET_TO_REGION = {
    "US": "us",
    "TW": "tw",
}

# Mapping from MARKET_REVIEW_REGIONS entry (case-insensitive) to internal region
_REGIONS_ENV_MAP = {
    "us": "us",
    "tw": "tw",
    "cn": "cn",
    "hk": "hk",
}


def parse_market_review_regions_env(raw: Optional[str]) -> List[str]:
    """Parse MARKET_REVIEW_REGIONS env value into a list of internal region codes.

    Accepted input formats (case-insensitive, comma-separated):
      "TW,US"  → ['tw', 'us']
      "us,cn"  → ['us', 'cn'] (cn will be blocked by the scope gate)
      ""       → []
    Unknown tokens are logged and dropped.
    """
    if not raw or not raw.strip():
        return []
    regions: List[str] = []
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        mapped = _REGIONS_ENV_MAP.get(item)
        if mapped:
            regions.append(mapped)
        else:
            logger.warning(
                "[MarketReviewScopeGate] Unknown region %r in MARKET_REVIEW_REGIONS; skipping.",
                item,
            )
    return regions


def get_default_route_b_regions(config=None) -> List[str]:
    """Derive candidate market review regions from ROUTE_B_MARKETS.

    TW maps to internal 'tw', US maps to internal 'us'.
    Returns an ordered list (US before TW by default).
    """
    from src.core.route_b_scope import get_route_b_markets

    allowed_markets = get_route_b_markets(config)
    # Stable order: US first, then TW
    order = ["US", "TW"]
    regions: List[str] = []
    for market in order:
        if market in allowed_markets:
            region = _MARKET_TO_REGION.get(market)
            if region:
                regions.append(region)
    return regions


def filter_regions_for_route_b(
    regions: List[str],
    config=None,
) -> Tuple[List[str], List[str], List[str]]:
    """Filter a list of internal region codes under Route B scope.

    Returns:
        (run_regions, skipped_cn, deferred_tw):
        - run_regions:  regions that will actually run
        - skipped_cn:   CN regions blocked under Route B
        - deferred_tw:  regions skipped because implementation is not yet available (empty for now)
    """
    run_regions: List[str] = []
    skipped_cn: List[str] = []
    deferred_tw: List[str] = []

    for region in regions:
        if region in _CN_REGIONS:
            skipped_cn.append(region)
            logger.warning(
                "[Route B] CN/HK market review is disabled under Route B TW/US scope. "
                "Skipping region: %r",
                region,
            )
        elif region in _DEFERRED_REGIONS:
            deferred_tw.append(region)
            logger.info(
                "[Route B] Region %r is deferred; skipped under Route B scope.", region
            )
        elif region in _IMPLEMENTED_REGIONS:
            run_regions.append(region)
        else:
            logger.warning("[Route B] Unknown region %r; skipping.", region)

    if not run_regions:
        logger.info(
            "[Route B] No supported market review regions after scope filtering "
            "(CN blocked=%r, deferred=%r).",
            skipped_cn,
            deferred_tw,
        )

    return run_regions, skipped_cn, deferred_tw


def get_effective_regions_for_route_b(
    config=None,
    explicit_regions: Optional[List[str]] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """Resolve effective market review regions under Route B enforce mode.

    Priority:
    1. explicit_regions (e.g. parsed from MARKET_REVIEW_REGIONS env var)
    2. Derived from ROUTE_B_MARKETS defaults

    Returns:
        (run_regions, skipped_cn, deferred_tw)
    """
    candidates = explicit_regions if explicit_regions else get_default_route_b_regions(config)
    return filter_regions_for_route_b(candidates, config)

# -*- coding: utf-8 -*-
"""
Market tools — wraps DataFetcherManager market-level methods as agent tools.

Tools:
- get_market_indices: major market index data
"""

import logging

from src.agent.tools.registry import ToolParameter, ToolDefinition

logger = logging.getLogger(__name__)


def _get_fetcher_manager():
    """Lazy import to avoid circular deps."""
    from data_provider import DataFetcherManager
    return DataFetcherManager()


# ============================================================
# get_market_indices
# ============================================================

def _handle_get_market_indices(region: str = "cn") -> dict:
    """Get major market indices."""
    manager = _get_fetcher_manager()
    indices = manager.get_main_indices(region=region)

    if not indices:
        return {"error": f"No market index data available for region '{region}'"}

    return {
        "region": region,
        "indices_count": len(indices),
        "indices": indices,
    }


get_market_indices_tool = ToolDefinition(
    name="get_market_indices",
    description="Get major market indices (e.g., Shanghai Composite, Shenzhen Component, "
                "CSI 300 for China; S&P 500, Nasdaq, Dow for US). Provides market overview.",
    parameters=[
        ToolParameter(
            name="region",
            type="string",
            description="Market region: 'cn' for China A-shares, 'hk' for Hong Kong, 'us' for US stocks (default: 'cn')",
            required=False,
            default="cn",
            enum=["cn", "hk", "us"],
        ),
    ],
    handler=_handle_get_market_indices,
    category="market",
)


ALL_MARKET_TOOLS = [
    get_market_indices_tool,
]

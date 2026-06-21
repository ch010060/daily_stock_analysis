# -*- coding: utf-8 -*-
"""Schemas for manual diagnostics endpoints."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NewsProviderProbeRequest(BaseModel):
    """Manual opt-in related-info/news provider probe request."""

    symbol: str = Field(..., min_length=1, max_length=24, description="股票代號 / ticker")
    market: Literal["tw", "us"] = Field(..., description="市場：tw 或 us")
    limit: int = Field(4, ge=1, le=8, description="返回樣本數")
    provider_mode: Literal["runtime", "searxng", "tavily"] = Field(
        "runtime",
        description="手動測試模式：runtime / searxng / tavily",
    )

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized


class NewsProviderProbeItem(BaseModel):
    """Sanitized sample result from a live provider probe."""

    title: str
    source: str = ""
    url: str
    published_at: Optional[str] = None


class NewsProviderProbeResponse(BaseModel):
    """Manual opt-in related-info/news provider probe response."""

    symbol: str
    market: Literal["tw", "us"]
    provider_mode: Literal["runtime", "searxng", "tavily"] = "runtime"
    status: str
    providers_attempted: List[str] = Field(default_factory=list)
    query_variants: List[str] = Field(default_factory=list)
    attempt_count: int = 0
    result_count: int = 0
    fallback_used: bool = False
    latency_ms: int = 0
    items: List[NewsProviderProbeItem] = Field(default_factory=list)
    error_message: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "symbol": "2330",
            "market": "tw",
            "provider_mode": "runtime",
            "status": "available",
            "providers_attempted": ["SearXNG"],
            "query_variants": ["2330 台積電 新聞", "台積電 最新消息"],
            "attempt_count": 2,
            "result_count": 4,
            "fallback_used": False,
            "latency_ms": 1234,
            "items": [
                {
                    "title": "台積電最新消息",
                    "source": "example",
                    "url": "https://example.com/news/1",
                    "published_at": "2026-06-20",
                }
            ],
        }
    })

# -*- coding: utf-8 -*-
"""Manual diagnostics endpoints."""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import APIRouter, Depends

from api.v1.schemas.diagnostics import (
    NewsProviderProbeRequest,
    NewsProviderProbeResponse,
)
from src.search_service import get_search_service
from src.services.run_diagnostics import (
    build_news_provider_probe_search_service,
    run_news_provider_probe,
    sanitize_diagnostic_text,
)

logger = logging.getLogger(__name__)

router = APIRouter()

NewsProviderProbeServiceResolver = Callable[[str], Any]


def get_news_provider_probe_service_resolver() -> NewsProviderProbeServiceResolver:
    """Return the service resolver used by the manual news-provider probe."""

    def resolve(provider_mode: str) -> Any:
        return (
            get_search_service()
            if provider_mode == "runtime"
            else build_news_provider_probe_search_service(provider_mode)
        )

    return resolve


@router.post(
    "/news-provider-probe",
    response_model=NewsProviderProbeResponse,
    summary="手動測試新聞搜尋來源",
    description=(
        "Operator opt-in live probe for related-info/news providers. "
        "This endpoint performs only a news search provider call; it does not run full analysis or LLM."
    ),
)
def probe_news_provider(
    request: NewsProviderProbeRequest,
    resolve_search_service: NewsProviderProbeServiceResolver = Depends(
        get_news_provider_probe_service_resolver
    ),
) -> NewsProviderProbeResponse:
    provider_mode = request.provider_mode
    try:
        service = resolve_search_service(provider_mode)
    except Exception as exc:
        return NewsProviderProbeResponse.model_validate({
            "symbol": request.symbol,
            "market": request.market,
            "provider_mode": provider_mode,
            "status": "failed",
            "providers_attempted": [],
            "query_variants": [],
            "attempt_count": 0,
            "result_count": 0,
            "fallback_used": False,
            "latency_ms": 0,
            "items": [],
            "error_message": sanitize_diagnostic_text(exc, max_length=220) or "provider unavailable",
        })
    payload = run_news_provider_probe(
        symbol=request.symbol,
        market=request.market,
        limit=request.limit,
        search_service=service,
        provider_mode=provider_mode,
    )
    return NewsProviderProbeResponse.model_validate(payload)

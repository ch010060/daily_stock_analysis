# -*- coding: utf-8 -*-
"""FiNews external snapshot endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.services.finews_snapshot import fetch_latest_finews_snapshot

router = APIRouter()


@router.get(
    "/latest",
    summary="取得 FiNews 美股日報最新快照",
    description=(
        "Fetches the public FiNews homepage and returns a sanitized structured "
        "snapshot for the local DSA reader page. This is not a market data provider."
    ),
)
def get_latest_finews_snapshot() -> dict[str, Any]:
    return fetch_latest_finews_snapshot()

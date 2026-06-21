# -*- coding: utf-8 -*-
"""
===================================
API v1 路由聚合
===================================

職責：
1. 聚合 v1 版本的所有 endpoint 路由
2. 統一新增 /api/v1 字首
"""

import os
from importlib import import_module

from fastapi import APIRouter

from api.v1.endpoints import alerts
from api.v1.endpoints import analysis
from api.v1.endpoints import auth
from api.v1.endpoints import history
from api.v1.endpoints import stocks
from api.v1.endpoints import backtest
from api.v1.endpoints import system_config
from api.v1.endpoints import agent
from api.v1.endpoints import usage
from api.v1.endpoints import portfolio
from api.v1.endpoints import health
from api.v1.endpoints import diagnostics


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _alphasift_route_enabled() -> bool:
    return _env_bool("ALPHASIFT_ROUTE_ENABLED", default=False)

# 建立 v1 版本主路由
router = APIRouter(prefix="/api/v1")

router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"]
)

router.include_router(
    agent.router,
    prefix="/agent",
    tags=["Agent"]
)

router.include_router(
    analysis.router,
    prefix="/analysis",
    tags=["Analysis"]
)

router.include_router(
    history.router,
    prefix="/history",
    tags=["History"]
)

router.include_router(
    stocks.router,
    prefix="/stocks",
    tags=["Stocks"]
)

router.include_router(
    backtest.router,
    prefix="/backtest",
    tags=["Backtest"]
)

router.include_router(
    system_config.router,
    prefix="/system",
    tags=["SystemConfig"]
)

router.include_router(
    usage.router,
    prefix="/usage",
    tags=["Usage"]
)

router.include_router(
    portfolio.router,
    prefix="/portfolio",
    tags=["Portfolio"]
)

router.include_router(
    alerts.router,
    prefix="/alerts",
    tags=["Alerts"]
)

router.include_router(
    diagnostics.router,
    prefix="/diagnostics",
    tags=["Diagnostics"]
)

if _alphasift_route_enabled():
    alphasift = import_module("api.v1.endpoints.alphasift")
    router.include_router(
        alphasift.router,
        prefix="/alphasift",
        tags=["AlphaSift"]
    )

router.include_router(
    health.router,
    tags=["Health"]
)

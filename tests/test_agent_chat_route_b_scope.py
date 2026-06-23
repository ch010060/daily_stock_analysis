# -*- coding: utf-8 -*-
"""Route B local-first context tests for Agent Ask / chat API."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.v1.endpoints import agent as agent_endpoint


class _AvailableAgentConfig:
    def is_agent_available(self) -> bool:
        return True


class _CapturingExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, *, message: str, session_id: str, context: dict | None = None):
        self.calls.append({
            "message": message,
            "session_id": session_id,
            "context": dict(context or {}),
        })
        return SimpleNamespace(success=True, content="route b answer", error=None)


def test_agent_chat_pre_resolves_tw_name_and_code_before_llm(monkeypatch) -> None:
    executor = _CapturingExecutor()
    monkeypatch.setattr(agent_endpoint, "get_config", lambda: _AvailableAgentConfig())
    monkeypatch.setattr(agent_endpoint, "_build_executor", lambda config, skills: executor)

    response = asyncio.run(
        agent_endpoint.agent_chat(
            agent_endpoint.ChatRequest(
                message="請分析瑞昱 2379 近期股價與基本面，適合長期持有嗎？",
                session_id="route-b-tw",
            )
        )
    )

    assert response.success is True
    assert executor.calls
    context = executor.calls[0]["context"]
    assert context["stock_code"] == "2379"
    assert context["stock_name"] == "瑞昱"
    assert context["market"] == "TW"
    assert context["selection_source"] == "local_symbol_universe"


def test_agent_chat_pre_resolves_us_ticker_and_name_before_llm(monkeypatch) -> None:
    executor = _CapturingExecutor()
    monkeypatch.setattr(agent_endpoint, "get_config", lambda: _AvailableAgentConfig())
    monkeypatch.setattr(agent_endpoint, "_build_executor", lambda config, skills: executor)

    response = asyncio.run(
        agent_endpoint.agent_chat(
            agent_endpoint.ChatRequest(
                message="請分析 INTC / Intel 目前是否適合長期持有？",
                session_id="route-b-us",
            )
        )
    )

    assert response.success is True
    assert executor.calls
    context = executor.calls[0]["context"]
    assert context["stock_code"] == "INTC"
    assert context["stock_name"] == "Intel"
    assert context["market"] == "US"
    assert context["selection_source"] == "local_symbol_universe"

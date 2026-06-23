# -*- coding: utf-8 -*-
"""Route B TW/US market context prompt tests."""

from __future__ import annotations

from src.market_context import detect_market, get_market_guidelines, get_market_role


def test_detect_market_treats_four_digit_route_b_symbols_as_tw() -> None:
    assert detect_market("2379") == "tw"
    assert "台股" in get_market_role("2379", "zh")
    assert "TW" in get_market_guidelines("2379", "zh")


def test_default_chat_market_context_is_tw_us_not_a_share_only() -> None:
    role = get_market_role("", "zh")
    guidelines = get_market_guidelines("", "zh")

    assert "台股" in role
    assert "美股" in role
    assert "TW/US" in guidelines


def test_detect_market_keeps_us_symbols_as_us() -> None:
    assert detect_market("INTC") == "us"
    assert "美股" in get_market_role("INTC", "zh")

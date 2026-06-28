# -*- coding: utf-8 -*-
"""YFinance provider symbol conversion tests."""

from data_provider.yfinance_fetcher import YfinanceFetcher


def test_yfinance_converts_us_class_share_dot_to_yahoo_hyphen():
    fetcher = YfinanceFetcher()

    for raw, provider in {
        "BRK.B": "BRK-B",
        "BRK.A": "BRK-A",
        "BF.B": "BF-B",
        "HEI.A": "HEI-A",
        "LEN.B": "LEN-B",
    }.items():
        assert fetcher._convert_stock_code(raw) == provider
        assert fetcher._convert_stock_code(f"US:{raw}") == provider
        assert fetcher._convert_stock_code(provider) == provider


def test_yfinance_keeps_regular_us_ticker_unchanged():
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("AAPL") == "AAPL"

# -*- coding: utf-8 -*-
"""YFinance provider symbol conversion tests."""

import sys
from types import SimpleNamespace

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


def test_yfinance_realtime_quote_preserves_exchange_metadata(monkeypatch):
    fetcher = YfinanceFetcher()

    fast_info = SimpleNamespace(
        lastPrice=170.0,
        previousClose=168.0,
        open=169.0,
        dayHigh=171.0,
        dayLow=167.0,
        lastVolume=123456,
        marketCap=1000000000,
    )
    ticker = SimpleNamespace(
        fast_info=fast_info,
        info={
            "shortName": "QUALCOMM Incorporated",
            "exchange": "NMS",
            "fullExchangeName": "NasdaqGS",
        },
    )
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: ticker))

    quote = fetcher.get_realtime_quote("QCOM")

    assert quote is not None
    assert quote.exchange == "NMS"
    assert quote.full_exchange_name == "NasdaqGS"
    assert quote.exchange_source == "yfinance"
    assert quote.to_dict()["exchange"] == "NMS"
    assert quote.to_dict()["full_exchange_name"] == "NasdaqGS"
    assert quote.to_dict()["exchange_source"] == "yfinance"

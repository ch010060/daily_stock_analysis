from src.services.google_finance_reference import (
    build_google_finance_reference_metadata,
    normalize_google_finance_exchange,
)


def test_tw_symbols_use_static_tpe_google_exchange() -> None:
    assert build_google_finance_reference_metadata(
        symbol="2330",
        market="TW",
        exchange="TWSE",
        instrument_type="stock",
    ) == {
        "market": "TW",
        "exchange": "TWSE",
        "instrument_type": "stock",
        "google_finance_exchange": "TPE",
        "exchange_source": "static_tpe",
    }
    assert build_google_finance_reference_metadata(
        symbol="0050",
        market="TW",
        exchange="TWSE",
        instrument_type="etf",
    )["google_finance_exchange"] == "TPE"


def test_us_symbols_resolve_from_exchange_metadata_not_ticker_mapping() -> None:
    assert build_google_finance_reference_metadata(
        symbol="MU",
        market="US",
        exchange="NASDAQ",
        instrument_type="stock",
    )["google_finance_exchange"] == "NASDAQ"
    assert build_google_finance_reference_metadata(
        symbol="SPY",
        market="US",
        exchange="NYSE Arca",
        instrument_type="etf",
    )["google_finance_exchange"] == "NYSEARCA"
    assert build_google_finance_reference_metadata(
        symbol="QQQ",
        market="US",
        exchange="NASDAQ",
        instrument_type="etf",
    )["google_finance_exchange"] == "NASDAQ"
    assert build_google_finance_reference_metadata(
        symbol="NOW",
        market="US",
        exchange="NYSE",
        instrument_type="stock",
    )["google_finance_exchange"] == "NYSE"


def test_unknown_us_exchange_and_non_tw_us_remain_unresolved() -> None:
    assert build_google_finance_reference_metadata(
        symbol="ABC",
        market="US",
        exchange=None,
        instrument_type="stock",
    )["google_finance_exchange"] is None
    assert build_google_finance_reference_metadata(
        symbol="0700",
        market="HK",
        exchange="HKEX",
        instrument_type="stock",
    ) is None


def test_exchange_namespace_normalization_is_exchange_level_only() -> None:
    assert normalize_google_finance_exchange("NasdaqGS") == "NASDAQ"
    assert normalize_google_finance_exchange("NYSE Arca") == "NYSEARCA"
    assert normalize_google_finance_exchange("PCX") == "NYSEARCA"
    assert normalize_google_finance_exchange("NYSE American") == "NYSEAMERICAN"
    assert normalize_google_finance_exchange("Cboe") is None

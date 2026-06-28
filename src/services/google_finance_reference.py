"""Google Finance external-reference metadata helpers.

This module only normalizes already-known listing exchange metadata for
external links. It does not fetch, scrape, or call Google Finance.
"""

from __future__ import annotations


_GOOGLE_FINANCE_EXCHANGE_ALIASES = {
    "NASDAQ": "NASDAQ",
    "NASDAQGS": "NASDAQ",
    "NASDAQGM": "NASDAQ",
    "NASDAQCM": "NASDAQ",
    "NASDAQGLOBALSELECT": "NASDAQ",
    "NASDAQGLOBALMARKET": "NASDAQ",
    "NASDAQCAPITALMARKET": "NASDAQ",
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYSE": "NYSE",
    "NYQ": "NYSE",
    "NEWYORKSTOCKEXCHANGE": "NYSE",
    "NYSEARCA": "NYSEARCA",
    "ARCA": "NYSEARCA",
    "PCX": "NYSEARCA",
    "NYSEAMERICAN": "NYSEAMERICAN",
    "NYSEMKT": "NYSEAMERICAN",
    "AMEX": "NYSEAMERICAN",
    "ASE": "NYSEAMERICAN",
    "ASEMKT": "NYSEAMERICAN",
}


def _exchange_key(exchange: str | None) -> str:
    return "".join(ch for ch in str(exchange or "").upper() if ch.isalnum())


def normalize_google_finance_exchange(exchange: str | None) -> str | None:
    """Normalize trusted exchange metadata into Google Finance exchange codes."""

    key = _exchange_key(exchange)
    if not key:
        return None
    return _GOOGLE_FINANCE_EXCHANGE_ALIASES.get(key)


def build_google_finance_reference_metadata(
    *,
    symbol: str,
    market: str | None,
    exchange: str | None,
    instrument_type: str | None,
    exchange_source: str = "symbol_universe",
) -> dict[str, str | None] | None:
    """Build safe external-reference metadata for supported TW/US symbols."""

    normalized_market = str(market or "").strip().upper()
    if normalized_market == "TW":
        return {
            "market": "TW",
            "exchange": exchange,
            "instrument_type": instrument_type,
            "google_finance_exchange": "TPE",
            "exchange_source": "static_tpe",
        }
    if normalized_market != "US":
        return None

    google_exchange = normalize_google_finance_exchange(exchange)
    return {
        "market": "US",
        "exchange": exchange,
        "instrument_type": instrument_type,
        "google_finance_exchange": google_exchange,
        "exchange_source": exchange_source if google_exchange else "unknown",
    }

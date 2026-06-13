# -*- coding: utf-8 -*-
"""TW/US symbol normalization helpers for Route B fixtures."""

from dataclasses import dataclass
import re
from typing import Optional


class SymbolNormalizationError(ValueError):
    """Raised when a symbol cannot be normalized without guessing a market."""


@dataclass(frozen=True)
class NormalizedSymbol:
    market: str
    canonical: str
    provider_symbol: str


_TW_CODE_RE = re.compile(r"^\d{4,6}[A-Z]?$")
_US_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")


def normalize_symbol(symbol: str, market: Optional[str] = None) -> NormalizedSymbol:
    """Normalize explicit TW/US symbols without guessing ambiguous bare codes."""
    raw = (symbol or "").strip()
    if not raw:
        raise SymbolNormalizationError("symbol is required")

    market_hint = (market or "").strip().upper() or None
    upper = raw.upper()

    if upper.startswith("TW:"):
        return _normalize_tw(upper[3:])
    if upper.endswith(".TW"):
        return _normalize_tw(upper[:-3])
    if upper.startswith("US:"):
        return _normalize_us(upper[3:])

    if market_hint == "TW":
        return _normalize_tw(upper)
    if market_hint == "US":
        return _normalize_us(upper)
    if market_hint:
        raise SymbolNormalizationError(f"unsupported market: {market_hint}")

    raise SymbolNormalizationError(f"market is required for ambiguous symbol: {raw}")


def _normalize_tw(code: str) -> NormalizedSymbol:
    provider_symbol = code.strip().upper()
    if not _TW_CODE_RE.fullmatch(provider_symbol):
        raise SymbolNormalizationError(f"invalid TW symbol: {code}")
    return NormalizedSymbol(
        market="TW",
        canonical=f"TW:{provider_symbol}",
        provider_symbol=provider_symbol,
    )


def _normalize_us(code: str) -> NormalizedSymbol:
    provider_symbol = code.strip().upper()
    if not _US_SYMBOL_RE.fullmatch(provider_symbol):
        raise SymbolNormalizationError(f"invalid US symbol: {code}")
    return NormalizedSymbol(
        market="US",
        canonical=f"US:{provider_symbol}",
        provider_symbol=provider_symbol,
    )

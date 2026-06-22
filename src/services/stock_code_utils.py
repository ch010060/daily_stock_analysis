# -*- coding: utf-8 -*-
"""
Shared stock code utilities.
"""

from __future__ import annotations

import re


_TW_SYMBOL_RE = re.compile(r"^(?:\d{4,6}|\d{4,5}[A-Z])$")


def is_code_like(value: str) -> bool:
    """Check if string looks like a supported TW/US stock code."""
    text = value.strip().upper()
    if not text:
        return False
    if text.startswith("TW:"):
        base = text[3:]
        if _TW_SYMBOL_RE.fullmatch(base):
            return True
    if text.endswith(".TW"):
        base = text[:-3]
        if _TW_SYMBOL_RE.fullmatch(base):
            return True
    if text.startswith("US:"):
        return bool(re.match(r"^US:[A-Z]{1,5}(?:[.-][A-Z])?$", text))
    if _TW_SYMBOL_RE.fullmatch(text):
        return True
    if re.match(r"^[A-Z]{1,5}(?:[.-][A-Z])?(?:\.US)?$", text):
        return True
    return False


def normalize_code(raw: str) -> Optional[str]:
    """Normalize and validate a single stock code.

    Supports TW 4-digit codes and US tickers only.
    """
    text = raw.strip().upper()
    if not text:
        return None
    if text.startswith("TW:") and _TW_SYMBOL_RE.fullmatch(text[3:]):
        return text[3:]
    if text.endswith(".TW") and _TW_SYMBOL_RE.fullmatch(text[:-3]):
        return text[:-3]
    if text.startswith("US:"):
        candidate = text[3:]
        return candidate if re.match(r"^[A-Z]{1,5}(?:[.-][A-Z])?$", candidate) else None
    if _TW_SYMBOL_RE.fullmatch(text):
        return text
    if text.endswith(".US"):
        candidate = text[:-3]
        return candidate if re.match(r"^[A-Z]{1,5}(?:[.-][A-Z])?$", candidate) else None
    if re.match(r"^[A-Z]{1,5}(?:[.-][A-Z])?$", text):
        return text
    return None

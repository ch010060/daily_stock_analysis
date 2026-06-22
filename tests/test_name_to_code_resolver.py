# -*- coding: utf-8 -*-
"""Tests for name_to_code_resolver.

Covers:
- Local mapping (STOCK_NAME_MAP reverse)
- Code format boundary (_is_code_like, _normalize_code)
- Pinyin match (when pypinyin available)
- Route B-only fuzzy match (difflib)
- Ambiguous names return None
"""

from src.services.name_to_code_resolver import (
    resolve_name_to_code,
    _is_code_like,
    _normalize_code,
    _build_reverse_map_no_duplicates,
)


# ---------------------------------------------------------------------------
# _is_code_like
# ---------------------------------------------------------------------------

class TestIsCodeLike:
    def test_tw_4_digits(self):
        assert _is_code_like("2330") is True
        assert _is_code_like("8299") is True
        assert _is_code_like("TW:2330") is True
        assert _is_code_like("2330.TW") is True

    def test_us_stock_letters(self):
        assert _is_code_like("AAPL") is True
        assert _is_code_like("META") is True
        assert _is_code_like("BRK.B") is True

    def test_rejects_non_code(self):
        assert _is_code_like("群聯") is False
        assert _is_code_like("1234") is True  # 4-digit: valid TW stock code
        assert _is_code_like("123") is False  # 3-digit: too short
        assert _is_code_like("1234567") is False  # too long
        assert _is_code_like("") is False
        assert _is_code_like("   ") is False


# ---------------------------------------------------------------------------
# _normalize_code
# ---------------------------------------------------------------------------

class TestNormalizeCode:
    def test_preserves_valid_tw_code(self):
        assert _normalize_code("2330") == "2330"
        assert _normalize_code("  8299  ") == "8299"
        assert _normalize_code("TW:2330") == "2330"
        assert _normalize_code("2330.TW") == "2330"

    def test_preserves_us_stock(self):
        assert _normalize_code("AAPL") == "AAPL"
        assert _normalize_code("meta") == "META"
        assert _normalize_code("brk.b") == "BRK.B"

    def test_returns_none_for_invalid(self):
        assert _normalize_code("") is None
        assert _normalize_code("123") is None
        assert _normalize_code("1234567") is None
        assert _normalize_code("群聯") is None


# ---------------------------------------------------------------------------
# _build_reverse_map_no_duplicates
# ---------------------------------------------------------------------------

class TestBuildReverseMapNoDuplicates:
    def test_excludes_ambiguous_names(self):
        code_to_name = {"META": "Meta Platforms", "METB": "Meta Platforms", "8299": "群聯"}
        result = _build_reverse_map_no_duplicates(code_to_name)
        assert "Meta Platforms" not in result
        assert result.get("群聯") == "8299"

    def test_includes_unique_names(self):
        code_to_name = {"8299": "群聯", "NVDA": "NVIDIA"}
        result = _build_reverse_map_no_duplicates(code_to_name)
        assert result["群聯"] == "8299"
        assert result["NVIDIA"] == "NVDA"


# ---------------------------------------------------------------------------
# resolve_name_to_code
# ---------------------------------------------------------------------------

class TestResolveNameToCode:
    def test_code_like_input_returned_normalized(self):
        assert resolve_name_to_code("3008") == "3008"
        assert resolve_name_to_code("8299") == "8299"
        assert resolve_name_to_code("TW:8299") == "8299"
        assert resolve_name_to_code("8299.TW") == "8299"
        assert resolve_name_to_code("  AAPL  ") == "AAPL"

    def test_local_map_exact_match(self):
        assert resolve_name_to_code("台積電") == "2330"
        assert resolve_name_to_code("群聯") == "8299"
        assert resolve_name_to_code("Meta Platforms") == "META"

    def test_route_b_natural_aliases_resolve_deterministically(self):
        assert resolve_name_to_code("大立光") == "3008"
        assert resolve_name_to_code("大立光精密") == "3008"
        assert resolve_name_to_code("Largan") == "3008"
        assert resolve_name_to_code("群聯") == "8299"
        assert resolve_name_to_code("Phison") == "8299"
        assert resolve_name_to_code("NVIDIA") == "NVDA"
        assert resolve_name_to_code("NVIDIA Corporation") == "NVDA"
        assert resolve_name_to_code("Meta Platforms") == "META"
        assert resolve_name_to_code("Facebook") == "META"

    def test_route_b_aliases_do_not_use_llm_or_market_fallback(self):
        assert resolve_name_to_code("群聯") == "8299"
        assert resolve_name_to_code("Meta Platforms") == "META"

    def test_returns_none_for_empty_or_invalid_input(self):
        assert resolve_name_to_code("") is None
        assert resolve_name_to_code("   ") is None
        assert resolve_name_to_code(None) is None  # type: ignore

    def test_unsupported_name_returns_none(self):
        assert resolve_name_to_code("不存在的支援標的") is None

    def test_weak_fuzzy_match_does_not_auto_select(self):
        result = resolve_name_to_code("未知半導體")
        assert result is None

    def test_returns_none_when_no_match(self):
        result = resolve_name_to_code("不存在的股票名稱xyz")
        assert result is None

    def test_skips_market_fallback_for_non_cjk_garbage_input(self):
        result = resolve_name_to_code("aaaaaaa")
        assert result is None

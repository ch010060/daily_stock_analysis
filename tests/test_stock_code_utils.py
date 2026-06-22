# -*- coding: utf-8 -*-
"""
Tests for src/services/stock_code_utils.py.

The active Route B stock lookup surface is TW/US-only. Legacy SH/SZ/BJ/HK
exchange forms must not be accepted by the active stock code utility.
"""

from src.services.stock_code_utils import is_code_like, normalize_code


class TestIsCodeLike:
    def test_tw_numeric_code(self):
        assert is_code_like("2330") is True

    def test_tw_etf_code_with_letter_suffix(self):
        assert is_code_like("00981A") is True

    def test_tw_explicit_prefix(self):
        assert is_code_like("TW:2330") is True

    def test_tw_suffix(self):
        assert is_code_like("2330.TW") is True

    def test_us_ticker(self):
        assert is_code_like("AAPL") is True

    def test_us_explicit_prefix(self):
        assert is_code_like("US:NVDA") is True

    def test_us_suffix(self):
        assert is_code_like("AAPL.US") is True

    def test_us_class_share_ticker(self):
        assert is_code_like("BRK.B") is True

    def test_rejects_sz_suffix(self):
        assert is_code_like("000001.SZ") is False

    def test_rejects_bj_suffix(self):
        assert is_code_like("920493.BJ") is False

    def test_rejects_sh_suffix(self):
        assert is_code_like("2330.SH") is False

    def test_rejects_hk_suffix(self):
        assert is_code_like("1810.HK") is False

    def test_rejects_exchange_prefixes(self):
        assert is_code_like("SH2330") is False
        assert is_code_like("SZ000001") is False
        assert is_code_like("BJ920493") is False
        assert is_code_like("HK700") is False

    def test_plain_text(self):
        assert is_code_like("台積電") is False

    def test_empty(self):
        assert is_code_like("") is False

    def test_mixed_invalid(self):
        assert is_code_like("abc123") is False


class TestNormalizeCode:
    def test_tw_numeric_code(self):
        assert normalize_code("2330") == "2330"

    def test_tw_etf_code_with_letter_suffix(self):
        assert normalize_code("00981A") == "00981A"

    def test_tw_explicit_prefix(self):
        assert normalize_code("TW:2330") == "2330"

    def test_tw_suffix(self):
        assert normalize_code("2330.TW") == "2330"

    def test_us_ticker(self):
        assert normalize_code("AAPL") == "AAPL"

    def test_us_explicit_prefix(self):
        assert normalize_code("US:NVDA") == "NVDA"

    def test_us_suffix(self):
        assert normalize_code("AAPL.US") == "AAPL"

    def test_us_class_share_ticker(self):
        assert normalize_code("BRK.B") == "BRK.B"

    def test_whitespace_stripped(self):
        assert normalize_code("  2330  ") == "2330"

    def test_rejects_sz_suffix(self):
        assert normalize_code("000001.SZ") is None

    def test_rejects_bj_suffix(self):
        assert normalize_code("920493.BJ") is None

    def test_rejects_ss_suffix(self):
        assert normalize_code("600000.SS") is None

    def test_rejects_hk_suffix(self):
        assert normalize_code("1810.HK") is None

    def test_rejects_exchange_prefixes(self):
        assert normalize_code("SH2330") is None
        assert normalize_code("SZ000001") is None
        assert normalize_code("BJ920493") is None
        assert normalize_code("HK700") is None

    def test_empty_returns_none(self):
        assert normalize_code("") is None

    def test_plain_text_returns_none(self):
        assert normalize_code("台積電") is None

    def test_partial_prefix_no_digits_returns_none(self):
        assert normalize_code("SH6005") is None

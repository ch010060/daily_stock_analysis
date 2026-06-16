# -*- coding: utf-8 -*-

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.symbol_normalizer import SymbolNormalizationError, normalize_symbol
from data_provider.base import normalize_stock_code


class TestSymbolNormalization(unittest.TestCase):
    def test_tw_prefixed_symbol(self):
        result = normalize_symbol("TW:2330")

        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:2330")
        self.assertEqual(result.provider_symbol, "2330")

    def test_tw_dot_suffix_symbol(self):
        result = normalize_symbol("2330.TW")

        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:2330")
        self.assertEqual(result.provider_symbol, "2330")

    def test_tw_bare_symbol_requires_explicit_market(self):
        result = normalize_symbol("2330", market="TW")

        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:2330")
        self.assertEqual(result.provider_symbol, "2330")

    def test_us_prefixed_symbol(self):
        result = normalize_symbol("US:AAPL")

        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:AAPL")
        self.assertEqual(result.provider_symbol, "AAPL")

    def test_us_bare_symbol_requires_explicit_market(self):
        result = normalize_symbol("AAPL", market="US")

        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:AAPL")
        self.assertEqual(result.provider_symbol, "AAPL")

    def test_a_share_without_market_fails_fast(self):
        """Bare 5-digit CN codes still fail normalization.
        4-digit codes are now accepted as TW stock codes (Phase 9C)."""
        with self.assertRaises(SymbolNormalizationError):
            normalize_symbol("600519")

    def test_tw_like_bare_symbol_without_market_fails_fast(self):
        """4-digit codes are now accepted as TW stock codes (Phase 9C).
        The Route B scope gate handles CN filtering at a higher layer."""
        result = normalize_symbol("2330")
        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:2330")

    def test_tw_4digit_etf_symbol(self):
        result = normalize_symbol("TW:0050")
        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:0050")
        self.assertEqual(result.provider_symbol, "0050")

    def test_tw_5digit_etf_symbol(self):
        result = normalize_symbol("TW:00878")
        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:00878")
        self.assertEqual(result.provider_symbol, "00878")

    def test_tw_6digit_etf_symbol(self):
        result = normalize_symbol("TW:006208")
        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:006208")
        self.assertEqual(result.provider_symbol, "006208")

    def test_tw_etf_with_uppercase_suffix(self):
        result = normalize_symbol("TW:00981A")
        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:00981A")
        self.assertEqual(result.provider_symbol, "00981A")

    def test_existing_a_h_code_path_helpers_are_unchanged(self):
        self.assertEqual(normalize_stock_code("SH600519"), "600519")
        self.assertEqual(normalize_stock_code("SZ000001"), "000001")
        self.assertEqual(normalize_stock_code("1810.HK"), "HK01810")
        self.assertEqual(normalize_stock_code("HK700"), "HK00700")

    def test_us_multiclass_dot_suffix(self):
        result = normalize_symbol("US:BRK.B")
        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:BRK.B")
        self.assertEqual(result.provider_symbol, "BRK.B")

    def test_us_multiclass_hyphen_suffix(self):
        result = normalize_symbol("US:BRK-B")
        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:BRK-B")
        self.assertEqual(result.provider_symbol, "BRK-B")

    def test_us_bf_b_dot_suffix(self):
        result = normalize_symbol("US:BF.B")
        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:BF.B")
        self.assertEqual(result.provider_symbol, "BF.B")

    def test_us_multiclass_bare_market_hint(self):
        result = normalize_symbol("BRK.B", market="US")
        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:BRK.B")

    def test_us_multiclass_too_long_suffix_rejected(self):
        with self.assertRaises(SymbolNormalizationError):
            normalize_symbol("US:BRK.BCX")

    def test_us_lowercase_multiclass_normalizes_to_upper(self):
        result = normalize_symbol("US:brk.b")
        self.assertEqual(result.market, "US")
        self.assertEqual(result.canonical, "US:BRK.B")

    def test_tw_code_dot_suffix_not_confused_with_us(self):
        result = normalize_symbol("2330.TW")
        self.assertEqual(result.market, "TW")


if __name__ == "__main__":
    unittest.main()

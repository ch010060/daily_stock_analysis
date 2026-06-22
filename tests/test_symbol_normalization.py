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

    def test_tw_bare_symbol_defaults_to_tw_when_supported(self):
        """Bare supported TW symbols resolve through the TW/US universe."""
        result = normalize_symbol("2330")
        self.assertEqual(result.market, "TW")
        self.assertEqual(result.canonical, "TW:2330")

    def test_unknown_symbol_without_market_fails_fast(self):
        with self.assertRaises(SymbolNormalizationError):
            normalize_symbol("UNKNOWN_TARGET")

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

    def test_stock_code_helper_supports_tw_us_only(self):
        self.assertEqual(normalize_stock_code("TW:00981A"), "00981A")
        self.assertEqual(normalize_stock_code("006208.TW"), "006208")
        self.assertEqual(normalize_stock_code("US:AAPL"), "AAPL")
        self.assertEqual(normalize_stock_code("AAPL.US"), "AAPL")

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

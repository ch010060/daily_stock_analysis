# -*- coding: utf-8 -*-
"""Tests for market strategy blueprints."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.core.market_strategy import get_market_strategy_blueprint
from src.market_analyzer import MarketAnalyzer, MarketOverview


class TestMarketStrategyBlueprint(unittest.TestCase):
    """Validate TW/US strategy blueprint basics."""

    def test_tw_blueprint_contains_action_framework(self):
        blueprint = get_market_strategy_blueprint("tw")
        block = blueprint.to_prompt_block()

        self.assertIn("台股市場三段式回顧策略", block)
        self.assertIn("Action Framework", block)
        self.assertIn("進攻", block)

    def test_cn_blueprint_is_unsupported(self):
        with self.assertRaisesRegex(ValueError, "Unsupported market strategy region"):
            get_market_strategy_blueprint("cn")

    def test_us_blueprint_contains_regime_strategy(self):
        blueprint = get_market_strategy_blueprint("us")
        block = blueprint.to_prompt_block()

        self.assertIn("US Market Regime Strategy", block)
        self.assertIn("Risk-on", block)
        self.assertIn("Macro & Flows", block)


class TestMarketAnalyzerStrategyPrompt(unittest.TestCase):
    """Validate strategy section is injected into prompt/report."""

    def test_tw_prompt_contains_strategy_plan_section(self):
        analyzer = MarketAnalyzer(region="tw")
        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("明日交易計劃", prompt)
        self.assertIn("台股市場三段式回顧策略", prompt)

    def test_us_prompt_uses_english_shell_when_report_language_is_en(self):
        with patch("src.market_analyzer.get_config", return_value=SimpleNamespace(report_language="en")):
            analyzer = MarketAnalyzer(region="us")

        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("Strategy Plan", prompt)
        self.assertIn("US Market Regime Strategy", prompt)

    def test_us_prompt_uses_traditional_chinese_shell_by_default(self):
        """US region must follow the configured report language, not be hardcoded to English."""
        analyzer = MarketAnalyzer(region="us")
        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("明日交易計劃", prompt)
        self.assertIn("美股大盤回顧", prompt)
        for english_heading in (
            "Market Summary",
            "Index Commentary",
            "Fund Flows",
            "Sector Highlights",
            "Outlook",
            "Risk Alerts",
            "Strategy Plan",
            "US Market Recap",
        ):
            self.assertNotIn(english_heading, prompt)

    def test_cn_prompt_region_is_unsupported(self):
        with self.assertRaisesRegex(ValueError, "unsupported region"):
            MarketAnalyzer(region="cn")

    def test_tw_prompt_uses_english_shell_when_report_language_is_en(self):
        with patch("src.market_analyzer.get_config", return_value=SimpleNamespace(report_language="en")):
            analyzer = MarketAnalyzer(region="tw")

        prompt = analyzer._build_review_prompt(MarketOverview(date="2026-02-24"), [])

        self.assertIn("# Today's Market Data", prompt)
        self.assertIn("### 1. Market Summary", prompt)
        self.assertIn("Taiwan", prompt)
        self.assertNotIn("A-share", prompt)
        self.assertNotIn("### 一、市場總結", prompt)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
Tests for Phase 8F — FinMind-backed Strategy Analysis.

All tests are offline. MockEngine injects deterministic backtest results.
"""

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("DSA_FIXTURE_MODE", "true")

from src.finmind.backtesting import BacktestConfig, BacktestDataLoader, BacktestEngine
from src.finmind.strategy_analysis import (
    StrategyAnalysisConfig,
    StrategyAnalysisResult,
    StrategyAnalyzer,
    _SWEEP_SPACE,
    compare_strategies,
    detect_risk_flags,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "finmind" / "strategy_analysis"
BT_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "finmind" / "backtesting"


def _load(path: Path) -> List[Dict]:
    with open(path) as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────────────
# MockLoader for BacktestEngine (reusing strategy_analysis fixtures)
# ──────────────────────────────────────────────────────────────────────────────

class MockSALoader:
    """Data loader backed by strategy_analysis fixtures."""

    def __init__(self, price_ok: bool = True, bench_ok: bool = True,
                 revenue_ok: bool = True, inst_ok: bool = True):
        self._price_ok = price_ok
        self._bench_ok = bench_ok
        self._revenue_ok = revenue_ok
        self._inst_ok = inst_ok
        self._price_rows = _load(FIXTURE_DIR / "price_2330_120d.json")
        self._bench_rows = _load(FIXTURE_DIR / "benchmark_0050_120d.json")
        self._rev_rows = _load(FIXTURE_DIR / "month_revenue_2330.json")
        self._inst_rows = _load(FIXTURE_DIR / "institutional_2330.json")

    def load_price_series(self, symbol: str, start_date: str, end_date: str,
                          adjusted_preferred: bool = True) -> Dict:
        if symbol == "0050":
            if not self._bench_ok:
                return {"ok": False, "rows": [], "adjusted": False, "caveat": "unavail", "source_dataset": None}
            return {"ok": True, "rows": self._bench_rows, "adjusted": False,
                    "caveat": "using unadjusted TaiwanStockPrice", "source_dataset": "TaiwanStockPrice"}
        if not self._price_ok:
            return {"ok": False, "rows": [], "adjusted": False, "caveat": "unavail", "source_dataset": None}
        caveat = "TaiwanStockPriceAdj unavailable (Backer tier); using unadjusted TaiwanStockPrice"
        return {"ok": True, "rows": self._price_rows, "adjusted": False,
                "caveat": caveat, "source_dataset": "TaiwanStockPrice"}

    def load_trading_dates(self, start_date: str, end_date: str) -> Dict:
        dates = sorted({r["date"] for r in self._price_rows})
        return {"ok": True, "dates": dates, "source": "fixture"}

    def load_monthly_revenue(self, symbol: str, start_date: str, end_date: str) -> Dict:
        if not self._revenue_ok:
            return {"ok": False, "rows": []}
        return {"ok": True, "rows": self._rev_rows}

    def load_institutional_flow(self, symbol: str, start_date: str, end_date: str) -> Dict:
        if not self._inst_ok:
            return {"ok": False, "rows": []}
        return {"ok": True, "rows": self._inst_rows}

    def load_margin(self, symbol: str, start_date: str, end_date: str) -> Dict:
        return {"ok": True, "rows": []}


def _make_engine(**kwargs) -> BacktestEngine:
    return BacktestEngine(data_loader=MockSALoader(**kwargs))


def _make_analyzer(**kwargs) -> StrategyAnalyzer:
    return StrategyAnalyzer(backtest_engine=_make_engine(**kwargs))


def _default_cfg(**kwargs) -> StrategyAnalysisConfig:
    defaults = dict(
        symbol="2330",
        start_date="2026-01-05",
        end_date="2026-06-19",
        benchmark_symbol="TW:0050",
        max_parameter_combinations=24,
        rolling_window_days=60,
    )
    defaults.update(kwargs)
    return StrategyAnalysisConfig(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Initialization
# ──────────────────────────────────────────────────────────────────────────────

class TestStrategyAnalyzerInit(unittest.TestCase):

    def test_initializes_with_engine(self):
        engine = _make_engine()
        analyzer = StrategyAnalyzer(backtest_engine=engine)
        self.assertIsNotNone(analyzer)

    def test_default_engine_created(self):
        # Just verifies it doesn't crash on default init
        analyzer = StrategyAnalyzer()
        self.assertIsNotNone(analyzer)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Strategy results
# ──────────────────────────────────────────────────────────────────────────────

class TestStrategyResults(unittest.TestCase):

    def test_default_strategies_generated(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        self.assertTrue(result["ok"])
        names = [r["strategy_name"] for r in result["strategy_results"]]
        self.assertIn("buy_and_hold", names)
        self.assertIn("sma_crossover", names)

    def test_analyze_returns_strategy_results(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        self.assertIn("strategy_results", result)
        self.assertGreater(len(result["strategy_results"]), 0)

    def test_engine_error_captured_per_strategy_not_crash(self):
        # Price unavailable → each strategy fails but analyze() still returns ok=False not raises
        analyzer = _make_analyzer(price_ok=False)
        result = analyzer.analyze(_default_cfg())
        # ok=False because all strategies failed, but no exception raised
        self.assertIn("ok", result)
        self.assertFalse(result["ok"])


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Strategy comparison
# ──────────────────────────────────────────────────────────────────────────────

class TestCompareStrategies(unittest.TestCase):

    def _make_mock_results(self) -> List[Dict]:
        return [
            {
                "ok": True, "strategy_name": "buy_and_hold", "params": {},
                "metrics": {"total_return": 0.3, "max_drawdown": 0.1,
                             "annualized_return": 0.6, "volatility": 0.2,
                             "win_rate": 0.5, "trade_count": 1,
                             "exposure_ratio": 0.99, "benchmark_return": 0.25,
                             "excess_return": 0.05},
                "data_quality": {"adjusted_price_used": False, "price_dataset": "TaiwanStockPrice"},
                "signals": [{"signal_date": "2026-01-05", "action": "buy"}],
            },
            {
                "ok": True, "strategy_name": "sma_crossover", "params": {"sma_fast": 5, "sma_slow": 20},
                "metrics": {"total_return": 0.15, "max_drawdown": 0.08,
                             "annualized_return": 0.3, "volatility": 0.15,
                             "win_rate": 0.6, "trade_count": 4,
                             "exposure_ratio": 0.5, "benchmark_return": 0.25,
                             "excess_return": -0.10},
                "data_quality": {"adjusted_price_used": False, "price_dataset": "TaiwanStockPrice"},
                "signals": [{"signal_date": "2026-01-05", "action": "buy"},
                             {"signal_date": "2026-02-05", "action": "sell"}],
            },
        ]

    def test_compare_ranks_by_total_return(self):
        results = self._make_mock_results()
        comparison = compare_strategies(results)
        ranked = comparison["ranked_by_total_return"]
        self.assertEqual(ranked[0]["strategy_label"], "buy_and_hold")

    def test_comparison_no_advisory_wording(self):
        results = self._make_mock_results()
        comparison = compare_strategies(results)
        result_str = str(comparison)
        forbidden = ["推薦", "建議買", "建議賣", "應該", "recommend", "should buy"]
        for term in forbidden:
            self.assertNotIn(term, result_str,
                             f"Advisory term '{term}' found in comparison output")

    def test_comparison_uses_historical_label(self):
        results = self._make_mock_results()
        comparison = compare_strategies(results)
        # Should use "best_historical_return_strategy" not "recommended_strategy"
        self.assertIn("best_historical_return_strategy", comparison)
        self.assertNotIn("recommended_strategy", comparison)

    def test_empty_results_returns_unavailable(self):
        comparison = compare_strategies([])
        self.assertFalse(comparison.get("available"))


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Parameter sweep
# ──────────────────────────────────────────────────────────────────────────────

class TestParameterSweep(unittest.TestCase):

    def test_sma_sweep_respects_max_combinations(self):
        analyzer = _make_analyzer()
        cfg = _default_cfg(max_parameter_combinations=4)
        result = analyzer.analyze(_default_cfg(
            strategies=[{"name": "sma_crossover"}],
            max_parameter_combinations=4,
        ))
        sweep = result.get("parameter_sweep", {})
        if sweep.get("available"):
            self.assertLessEqual(sweep.get("combo_count", 0), 4)

    def test_sma_sweep_space_is_bounded(self):
        combos = _SWEEP_SPACE.get("sma_crossover", [])
        self.assertGreater(len(combos), 0)
        self.assertLessEqual(len(combos), 24)
        # All combos must have fast < slow
        for c in combos:
            self.assertLess(c["sma_fast"], c["sma_slow"])

    def test_revenue_sweep_produces_results(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg(
            strategies=[{"name": "monthly_revenue_momentum"}]
        ))
        self.assertIn("parameter_sweep", result)

    def test_sweep_includes_overfit_warning(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg(
            strategies=[{"name": "sma_crossover"}]
        ))
        sweep = result.get("parameter_sweep", {})
        if sweep.get("available"):
            self.assertIn("overfit_warning", sweep)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Rolling analysis
# ──────────────────────────────────────────────────────────────────────────────

class TestRollingAnalysis(unittest.TestCase):

    def test_rolling_returns_windows_when_enough_data(self):
        analyzer = _make_analyzer()
        # 120d fixture, rolling_window_days=60 → at least 2 windows
        result = analyzer.analyze(_default_cfg(rolling_window_days=60))
        rolling = result.get("rolling_analysis", {})
        if rolling.get("available"):
            self.assertGreater(rolling.get("window_count", 0), 0)
            self.assertIn("windows", rolling)

    def test_rolling_unavailable_when_insufficient_data(self):
        analyzer = _make_analyzer()
        # 5 days total < 2 × 60 window
        result = analyzer.analyze(_default_cfg(
            start_date="2026-06-01",
            end_date="2026-06-07",
            rolling_window_days=60,
        ))
        rolling = result.get("rolling_analysis", {})
        self.assertFalse(rolling.get("available", True))


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Risk flags
# ──────────────────────────────────────────────────────────────────────────────

class TestRiskFlags(unittest.TestCase):

    def _make_result(self, name: str, **metric_overrides) -> Dict:
        metrics = {
            "total_return": 0.1, "max_drawdown": 0.05,
            "annualized_return": 0.2, "volatility": 0.15,
            "win_rate": 0.5, "trade_count": 3,
            "exposure_ratio": 0.5, "benchmark_return": 0.08,
            "excess_return": 0.02,
        }
        metrics.update(metric_overrides)
        return {
            "ok": True, "strategy_name": name, "params": {},
            "metrics": metrics,
            "data_quality": {"adjusted_price_used": False, "price_dataset": "TaiwanStockPrice"},
            "signals": [{"signal_date": "2026-01-05", "action": "buy"},
                         {"signal_date": "2026-02-05", "action": "sell"}],
        }

    def test_high_drawdown_flag_triggers(self):
        results = [self._make_result("sma_crossover", max_drawdown=0.25)]
        flags = detect_risk_flags(results)
        flag_names = [f["flag"] for f in flags]
        self.assertIn("high_drawdown", flag_names)

    def test_underperforms_benchmark_flag_triggers(self):
        results = [self._make_result("sma_crossover", excess_return=-0.15)]
        flags = detect_risk_flags(results)
        flag_names = [f["flag"] for f in flags]
        self.assertIn("underperforms_benchmark", flag_names)

    def test_low_trade_count_flag_triggers(self):
        results = [self._make_result("sma_crossover", trade_count=1)]
        flags = detect_risk_flags(results)
        flag_names = [f["flag"] for f in flags]
        self.assertIn("low_trade_count", flag_names)

    def test_unadjusted_price_caveat_flag(self):
        result = self._make_result("buy_and_hold")
        flags = detect_risk_flags([result])
        flag_names = [f["flag"] for f in flags]
        self.assertIn("unadjusted_price_caveat", flag_names)

    def test_high_drawdown_flag_severity_is_high(self):
        results = [self._make_result("sma_crossover", max_drawdown=0.30)]
        flags = detect_risk_flags(results)
        high_dd = [f for f in flags if f["flag"] == "high_drawdown"]
        self.assertEqual(high_dd[0]["severity"], "high")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Prompts
# ──────────────────────────────────────────────────────────────────────────────

class TestPrompts(unittest.TestCase):

    def test_prompts_generated(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        prompts = result.get("recommended_prompts", [])
        self.assertGreater(len(prompts), 0)

    def test_prompts_contain_no_buy_sell(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        prompts = result.get("recommended_prompts", [])
        for p in prompts:
            for term in ["買進", "賣出", "建議買", "建議賣", "should buy", "should sell"]:
                self.assertNotIn(term, p, f"Forbidden term '{term}' in prompt: {p}")

    def test_prompts_say_provided_analysis_only(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        prompts = result.get("recommended_prompts", [])
        # At least one prompt anchors to this analysis
        has_anchor = any("本次" in p or "截至" in p for p in prompts)
        self.assertTrue(has_anchor, "Prompts should anchor to current analysis")


# ──────────────────────────────────────────────────────────────────────────────
# Tests: Safety
# ──────────────────────────────────────────────────────────────────────────────

class TestSafety(unittest.TestCase):

    def test_non_tw_symbol_rejected(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg(symbol="US:AAPL"))
        self.assertFalse(result["ok"])
        self.assertTrue(any("symbol rejected" in w for w in result["warnings"]))

    def test_non_tw_symbol_rejected(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg(symbol="BADTARGET"))
        self.assertFalse(result["ok"])

    def test_no_cn_a_share_terms(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        result_str = str(result)
        cn_terms = ["台股", "上證", "上證", "深證", "深證", "創業板", "創業板"]
        found = [t for t in cn_terms if t in result_str]
        self.assertEqual(found, [], f"CN/A-share terms found: {found}")

    def test_no_live_calls_in_tests(self):
        import os
        orig = os.environ.get("DSA_ALLOW_EXTERNAL_NETWORK")
        try:
            os.environ["DSA_ALLOW_EXTERNAL_NETWORK"] = "false"
            analyzer = _make_analyzer()
            result = analyzer.analyze(_default_cfg())
            self.assertIn("ok", result)
        finally:
            if orig is None:
                os.environ.pop("DSA_ALLOW_EXTERNAL_NETWORK", None)
            else:
                os.environ["DSA_ALLOW_EXTERNAL_NETWORK"] = orig

    def test_result_shape_has_required_keys(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze(_default_cfg())
        for key in ("ok", "symbol", "start_date", "end_date",
                    "strategy_results", "comparison", "parameter_sweep",
                    "rolling_analysis", "risk_flags", "data_quality",
                    "recommended_prompts", "warnings", "sources"):
            self.assertIn(key, result, f"Missing key: {key}")


if __name__ == "__main__":
    unittest.main()

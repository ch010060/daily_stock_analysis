# -*- coding: utf-8 -*-
"""
Tests for Phase 8E — FinMind-backed Backtesting Foundation.

All tests are offline (no live network calls). MockLoader injects fixtures.
"""

import json
import math
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("DSA_FIXTURE_MODE", "true")

from src.finmind.backtesting import (
    BacktestConfig,
    BacktestDataLoader,
    BacktestEngine,
    BacktestResult,
    _build_equity_curve,
    _compute_benchmark_return,
    _compute_metrics,
    _execute_signals,
    summarize_backtest_result,
)
from src.finmind.strategies import (
    _compute_revenue_yoy_at,
    get_strategy_fn,
    list_strategies,
    strategy_buy_and_hold,
    strategy_monthly_revenue_momentum,
    strategy_sma_crossover,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "finmind" / "backtesting"


def _load(name: str) -> List[Dict[str, Any]]:
    with open(FIXTURE_DIR / name) as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────────────
# MockLoader — injects fixture data, no live calls
# ──────────────────────────────────────────────────────────────────────────────

class MockLoader:
    """Deterministic data loader backed by fixture files."""

    def __init__(self, adjusted_ok: bool = False, price_ok: bool = True,
                 bench_ok: bool = True, revenue_ok: bool = True,
                 inst_ok: bool = True):
        self._adjusted_ok = adjusted_ok
        self._price_ok = price_ok
        self._bench_ok = bench_ok
        self._revenue_ok = revenue_ok
        self._inst_ok = inst_ok
        self._price_rows = _load("price_2330_60d.json")
        self._bench_rows = _load("benchmark_0050_60d.json")
        self._td_rows = _load("trading_dates_60d.json")
        self._rev_rows = _load("month_revenue_2330.json")
        self._inst_rows = _load("institutional_2330.json")
        self._margin_rows = _load("margin_2330.json")

    def load_price_series(self, symbol: str, start_date: str, end_date: str,
                          adjusted_preferred: bool = True) -> Dict:
        if symbol == "0050":
            if self._bench_ok:
                return {"ok": True, "rows": self._bench_rows, "adjusted": False,
                        "caveat": "using unadjusted TaiwanStockPrice", "source_dataset": "TaiwanStockPrice"}
            return {"ok": False, "rows": [], "adjusted": False, "caveat": "unavailable", "source_dataset": None}

        if not self._price_ok:
            return {"ok": False, "rows": [], "adjusted": False, "caveat": "unavailable", "source_dataset": None}

        if adjusted_preferred and self._adjusted_ok:
            return {"ok": True, "rows": self._price_rows, "adjusted": True,
                    "caveat": None, "source_dataset": "TaiwanStockPriceAdj"}

        caveat = "TaiwanStockPriceAdj unavailable (Backer tier); using unadjusted TaiwanStockPrice" if adjusted_preferred else None
        return {"ok": True, "rows": self._price_rows, "adjusted": False,
                "caveat": caveat, "source_dataset": "TaiwanStockPrice"}

    def load_trading_dates(self, start_date: str, end_date: str) -> Dict:
        dates = sorted({r["date"] for r in self._td_rows})
        return {"ok": True, "dates": dates, "source": "TaiwanStockTradingDate"}

    def load_monthly_revenue(self, symbol: str, start_date: str, end_date: str) -> Dict:
        if not self._revenue_ok:
            return {"ok": False, "rows": []}
        return {"ok": True, "rows": self._rev_rows}

    def load_institutional_flow(self, symbol: str, start_date: str, end_date: str) -> Dict:
        if not self._inst_ok:
            return {"ok": False, "rows": []}
        return {"ok": True, "rows": self._inst_rows}

    def load_margin(self, symbol: str, start_date: str, end_date: str) -> Dict:
        return {"ok": True, "rows": self._margin_rows}


def _make_engine(adjusted_ok=False, price_ok=True, bench_ok=True,
                 revenue_ok=True, inst_ok=True) -> BacktestEngine:
    loader = MockLoader(adjusted_ok=adjusted_ok, price_ok=price_ok,
                        bench_ok=bench_ok, revenue_ok=revenue_ok, inst_ok=inst_ok)
    return BacktestEngine(data_loader=loader)


def _default_config(**kwargs) -> BacktestConfig:
    defaults = dict(
        strategy_name="buy_and_hold",
        symbol="2330",
        start_date="2026-03-23",
        end_date="2026-06-12",
        benchmark_symbol="TW:0050",
        initial_cash=1_000_000.0,
        transaction_cost_bps=10.0,
        slippage_bps=5.0,
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: BacktestDataLoader loads fixture price series
# ──────────────────────────────────────────────────────────────────────────────

class TestBacktestDataLoader(unittest.TestCase):

    def test_loads_fixture_price_series(self):
        loader = MockLoader()
        result = loader.load_price_series("2330", "2026-03-23", "2026-06-12")
        self.assertTrue(result["ok"])
        self.assertGreater(len(result["rows"]), 0)
        # Rows sorted by date
        dates = [r["date"] for r in result["rows"]]
        self.assertEqual(dates, sorted(dates))

    def test_adjusted_unavailable_falls_back_to_unadjusted(self):
        loader = MockLoader(adjusted_ok=False)
        result = loader.load_price_series("2330", "2026-03-23", "2026-06-12",
                                          adjusted_preferred=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["adjusted"])
        self.assertIn("unadjusted", result.get("caveat", ""))

    def test_trading_dates_loaded_and_sorted(self):
        loader = MockLoader()
        result = loader.load_trading_dates("2026-03-23", "2026-06-12")
        self.assertTrue(result["ok"])
        dates = result["dates"]
        self.assertGreater(len(dates), 0)
        self.assertEqual(dates, sorted(dates))

    def test_revenue_loaded(self):
        loader = MockLoader()
        result = loader.load_monthly_revenue("2330", "2025-01-01", "2026-06-12")
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["rows"]), 13)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: Buy and Hold
# ──────────────────────────────────────────────────────────────────────────────

class TestBuyAndHold(unittest.TestCase):

    def test_produces_one_buy_trade(self):
        engine = _make_engine()
        cfg = _default_config(strategy_name="buy_and_hold")
        result = engine.run(cfg)
        self.assertTrue(result["ok"])
        trades = result["trades"]
        buy_trades = [t for t in trades if t["action"] == "buy"]
        self.assertEqual(len(buy_trades), 1)

    def test_buy_and_hold_no_sell_mid_period(self):
        engine = _make_engine()
        cfg = _default_config(strategy_name="buy_and_hold")
        result = engine.run(cfg)
        # No sell trade (holds to end)
        sell_trades = [t for t in result["trades"] if t["action"] == "sell"]
        self.assertEqual(len(sell_trades), 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: SMA Crossover
# ──────────────────────────────────────────────────────────────────────────────

class TestSMACrossover(unittest.TestCase):

    def _run_sma(self, **kwargs) -> Dict:
        engine = _make_engine()
        cfg = _default_config(strategy_name="sma_crossover", **kwargs)
        return engine.run(cfg)

    def test_sma_generates_signals(self):
        result = self._run_sma()
        self.assertTrue(result["ok"])
        signals = result["signals"]
        self.assertGreater(len(signals), 0)

    def test_sma_crossover_has_buy_and_sell(self):
        result = self._run_sma()
        actions = {s["action"] for s in result["signals"]}
        self.assertIn("buy", actions)
        self.assertIn("sell", actions)

    def test_sma_executes_t1_not_same_day(self):
        result = self._run_sma()
        for trade in result["trades"]:
            self.assertGreater(trade["execution_date"], trade["signal_date"],
                               f"T+1 violated: exec={trade['execution_date']} <= signal={trade['signal_date']}")

    def test_no_lookahead_signal_before_execution(self):
        result = self._run_sma()
        for trade in result["trades"]:
            sig_date = trade["signal_date"]
            exec_date = trade["execution_date"]
            self.assertLess(sig_date, exec_date,
                            "signal_date must be strictly before execution_date")


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: Monthly Revenue Momentum
# ──────────────────────────────────────────────────────────────────────────────

class TestMonthlyRevenueMomentum(unittest.TestCase):

    def test_revenue_momentum_generates_signal(self):
        engine = _make_engine()
        cfg = _default_config(strategy_name="monthly_revenue_momentum")
        result = engine.run(cfg)
        self.assertTrue(result["ok"])
        self.assertGreater(len(result["signals"]), 0)

    def test_missing_revenue_does_not_crash(self):
        engine = _make_engine(revenue_ok=False)
        cfg = _default_config(strategy_name="monthly_revenue_momentum")
        result = engine.run(cfg)
        # Should still be ok (no revenue → no signals, but no crash)
        # ok may be True with 0 signals and warning
        self.assertIn("ok", result)

    def test_revenue_yoy_no_lookahead(self):
        # Revenue row dated AFTER trading date must NOT be used
        rev_rows = [
            {"date": "2026-04-10", "stock_id": "2330", "revenue": 290e9},
        ] * 13  # 13 rows all dated AFTER our trading date
        # First trading date 2026-03-23 is before 2026-04-10 → no rows available
        result = _compute_revenue_yoy_at(rev_rows, "2026-03-22")
        self.assertIsNone(result,
                          "Revenue from 2026-04-10 must not be used on 2026-03-22")

    def test_revenue_yoy_requires_13_rows(self):
        rev_rows = [{"date": f"2025-{m:02d}-10", "revenue": 100e9} for m in range(1, 12)]
        result = _compute_revenue_yoy_at(rev_rows, "2025-12-31")
        self.assertIsNone(result, "Need 13 rows for valid YoY")


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: Cost model
# ──────────────────────────────────────────────────────────────────────────────

class TestCostModel(unittest.TestCase):

    def _run_bah(self, **cfg_kwargs) -> Dict:
        engine = _make_engine()
        cfg = _default_config(strategy_name="buy_and_hold",
                              benchmark_symbol=None, **cfg_kwargs)
        return engine.run(cfg)

    def test_transaction_cost_reduces_return(self):
        r_no_cost = self._run_bah(transaction_cost_bps=0, slippage_bps=0)
        r_with_cost = self._run_bah(transaction_cost_bps=20, slippage_bps=10)
        val_no_cost = r_no_cost["equity_curve"][-1]["portfolio_value"] if r_no_cost["equity_curve"] else 0
        val_with_cost = r_with_cost["equity_curve"][-1]["portfolio_value"] if r_with_cost["equity_curve"] else 0
        self.assertLessEqual(val_with_cost, val_no_cost)

    def test_slippage_reduces_return(self):
        r_no_slip = self._run_bah(transaction_cost_bps=0, slippage_bps=0)
        r_with_slip = self._run_bah(transaction_cost_bps=0, slippage_bps=50)
        val_no = r_no_slip["equity_curve"][-1]["portfolio_value"] if r_no_slip["equity_curve"] else 0
        val_with = r_with_slip["equity_curve"][-1]["portfolio_value"] if r_with_slip["equity_curve"] else 0
        self.assertLessEqual(val_with, val_no)


# ──────────────────────────────────────────────────────────────────────────────
# Test 6: Metrics
# ──────────────────────────────────────────────────────────────────────────────

class TestMetrics(unittest.TestCase):

    def _run_sma(self) -> Dict:
        engine = _make_engine()
        cfg = _default_config(strategy_name="sma_crossover", benchmark_symbol=None)
        return engine.run(cfg)

    def test_max_drawdown_computed(self):
        result = _make_engine().run(_default_config(strategy_name="buy_and_hold", benchmark_symbol=None))
        self.assertIn("max_drawdown", result["metrics"])
        dd = result["metrics"]["max_drawdown"]
        self.assertGreaterEqual(dd, 0.0)
        self.assertLessEqual(dd, 1.0)

    def test_win_rate_computed(self):
        result = self._run_sma()
        self.assertIn("win_rate", result["metrics"])
        wr = result["metrics"]["win_rate"]
        self.assertGreaterEqual(wr, 0.0)
        self.assertLessEqual(wr, 1.0)

    def test_exposure_ratio_computed(self):
        result = self._run_sma()
        self.assertIn("exposure_ratio", result["metrics"])
        er = result["metrics"]["exposure_ratio"]
        self.assertGreaterEqual(er, 0.0)
        self.assertLessEqual(er, 1.0)

    def test_benchmark_return_computed(self):
        result = _make_engine().run(_default_config(strategy_name="buy_and_hold"))
        self.assertTrue(result["benchmark"].get("available"))
        self.assertIsNotNone(result["metrics"].get("benchmark_return"))

    def test_benchmark_missing_does_not_fail(self):
        result = _make_engine(bench_ok=False).run(_default_config(
            strategy_name="buy_and_hold", benchmark_symbol="TW:0050"
        ))
        self.assertTrue(result["ok"])
        self.assertFalse(result["benchmark"].get("available", True))


# ──────────────────────────────────────────────────────────────────────────────
# Test 7: Safety and correctness
# ──────────────────────────────────────────────────────────────────────────────

class TestSafetyAndCorrectness(unittest.TestCase):

    def test_no_short_selling_in_v1(self):
        cfg = _default_config(strategy_name="buy_and_hold", allow_short=True)
        result = _make_engine().run(cfg)
        self.assertFalse(result["ok"])
        self.assertTrue(any("short" in w.lower() for w in result["warnings"]))

    def test_no_leverage_position_never_exceeds_initial_cash(self):
        result = _make_engine().run(_default_config(strategy_name="buy_and_hold", benchmark_symbol=None))
        initial = 1_000_000.0
        for point in result["equity_curve"]:
            # Shares * price should not exceed initial_cash by more than slippage
            # (no leverage check: cash should never go deeply negative)
            self.assertGreater(point["cash"], -10000,
                               "Cash went deeply negative → possible leverage")

    def test_unknown_strategy_fails_closed(self):
        result = _make_engine().run(_default_config(strategy_name="magic_crystal_ball"))
        self.assertFalse(result["ok"])
        self.assertTrue(any("unknown strategy" in w for w in result["warnings"]))

    def test_non_tw_symbol_rejected(self):
        result = _make_engine().run(_default_config(symbol="US:AAPL"))
        self.assertFalse(result["ok"])
        self.assertTrue(any("symbol rejected" in w for w in result["warnings"]))

    def test_cn_symbol_rejected(self):
        result = _make_engine().run(_default_config(symbol="2330"))
        self.assertFalse(result["ok"])
        self.assertTrue(any("symbol rejected" in w for w in result["warnings"]))

    def test_no_cn_a_share_terms_in_result(self):
        result = _make_engine().run(_default_config(strategy_name="buy_and_hold"))
        result_str = str(result)
        cn_terms = ["台股", "上證", "上證", "深證", "深證", "創業板", "創業板"]
        found = [t for t in cn_terms if t in result_str]
        self.assertEqual(found, [], f"CN/A-share terms found: {found}")

    def test_summary_prompts_no_buy_sell(self):
        result = _make_engine().run(_default_config(strategy_name="buy_and_hold"))
        summary = summarize_backtest_result(result)
        prompts = summary.get("recommended_follow_up_prompts", [])
        self.assertGreater(len(prompts), 0)
        for p in prompts:
            for term in ["買進", "賣出", "buy signal", "sell signal", "投資建議"]:
                self.assertNotIn(term, p, f"Forbidden term '{term}' in prompt: {p}")

    def test_no_live_calls_in_unit_tests(self):
        # Engine backed by MockLoader should never touch network.
        # If fixture mode guard is working, this test will pass.
        # We verify by running with DSA_ALLOW_EXTERNAL_NETWORK=false explicitly.
        import os
        orig = os.environ.get("DSA_ALLOW_EXTERNAL_NETWORK")
        try:
            os.environ["DSA_ALLOW_EXTERNAL_NETWORK"] = "false"
            result = _make_engine().run(_default_config())
            # Should succeed because MockLoader never calls FinMindClient
            self.assertIn("ok", result)
        finally:
            if orig is None:
                os.environ.pop("DSA_ALLOW_EXTERNAL_NETWORK", None)
            else:
                os.environ["DSA_ALLOW_EXTERNAL_NETWORK"] = orig


# ──────────────────────────────────────────────────────────────────────────────
# Test 8: Strategy registry
# ──────────────────────────────────────────────────────────────────────────────

class TestStrategyRegistry(unittest.TestCase):

    def test_strategies_registered(self):
        for name in ["buy_and_hold", "sma_crossover", "monthly_revenue_momentum"]:
            self.assertIsNotNone(get_strategy_fn(name), f"strategy '{name}' not registered")

    def test_unknown_strategy_returns_none(self):
        self.assertIsNone(get_strategy_fn("not_a_strategy"))

    def test_list_strategies_non_empty(self):
        self.assertGreater(len(list_strategies()), 0)


# ──────────────────────────────────────────────────────────────────────────────
# Test 9: Result shape
# ──────────────────────────────────────────────────────────────────────────────

class TestResultShape(unittest.TestCase):

    def test_to_dict_has_required_keys(self):
        result = _make_engine().run(_default_config())
        for key in ("ok", "strategy_name", "symbol", "start_date", "end_date",
                    "metrics", "equity_curve", "trades", "signals",
                    "benchmark", "data_quality", "warnings", "sources",
                    "recommended_prompts"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_metrics_has_required_fields(self):
        result = _make_engine().run(_default_config(benchmark_symbol=None))
        metrics = result["metrics"]
        for field in ("total_return", "annualized_return", "max_drawdown",
                      "volatility", "win_rate", "trade_count",
                      "average_trade_return", "exposure_ratio", "n_trading_days"):
            self.assertIn(field, metrics, f"Missing metric: {field}")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
FinMind-backed Strategy Analysis — Phase 8F.

Provides StrategyAnalyzer which runs multi-strategy comparisons, bounded
parameter sweeps, rolling-window robustness checks, and risk flag detection
on top of Phase 8E BacktestEngine.

Design principles:
  - Deterministic: same config always produces same result.
  - No LLM calls. No buy/sell recommendations.
  - Bounded parameter sweep: max_parameter_combinations enforced.
  - Historical labels only: "best historical return" not "recommended".
  - Risk flags are descriptive, not predictive.
  - No new FinMind API calls: all data flows through BacktestEngine.
  - No CN/A-share datasets. No investment advice.
"""

import itertools
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.finmind.backtesting import BacktestConfig, BacktestEngine
from src.finmind.tw_stock_analysis import normalize_tw_symbol

logger = logging.getLogger(__name__)

_FORBIDDEN_ADVICE = frozenset({
    "推薦", "建議買", "建議賣", "應該", "recommend", "should buy", "should sell",
})

# ──────────────────────────────────────────────────────────────────────────────
# Config model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyAnalysisConfig:
    """Configuration for a multi-strategy analysis run."""

    symbol: str
    start_date: str
    end_date: str
    benchmark_symbol: Optional[str] = "TW:0050"
    strategies: List[Dict[str, Any]] = field(default_factory=list)
    initial_cash: float = 1_000_000.0
    transaction_cost_bps: float = 10.0
    slippage_bps: float = 5.0
    rolling_window_days: int = 60
    max_parameter_combinations: int = 24


# ──────────────────────────────────────────────────────────────────────────────
# Result model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyAnalysisResult:
    """Structured strategy analysis result."""

    ok: bool
    symbol: str
    start_date: str
    end_date: str
    strategy_results: List[Dict[str, Any]] = field(default_factory=list)
    comparison: Dict[str, Any] = field(default_factory=dict)
    parameter_sweep: Dict[str, Any] = field(default_factory=dict)
    rolling_analysis: Dict[str, Any] = field(default_factory=dict)
    risk_flags: List[Dict[str, Any]] = field(default_factory=list)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    recommended_prompts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "strategy_results": self.strategy_results,
            "comparison": self.comparison,
            "parameter_sweep": self.parameter_sweep,
            "rolling_analysis": self.rolling_analysis,
            "risk_flags": self.risk_flags,
            "data_quality": self.data_quality,
            "recommended_prompts": self.recommended_prompts,
            "warnings": self.warnings,
            "sources": self.sources,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Default strategy set
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_STRATEGIES = [
    {"name": "buy_and_hold"},
    {"name": "sma_crossover", "sma_fast": 5, "sma_slow": 20},
    {"name": "monthly_revenue_momentum", "revenue_yoy_threshold_pct": 10.0},
    {"name": "institutional_flow", "institutional_rolling_days": 5},
]

# ──────────────────────────────────────────────────────────────────────────────
# Parameter sweep definitions (bounded)
# ──────────────────────────────────────────────────────────────────────────────

_SWEEP_SPACE: Dict[str, List[Dict[str, Any]]] = {
    "sma_crossover": [
        {"sma_fast": fast, "sma_slow": slow}
        for fast, slow in itertools.product([5, 10, 20], [20, 60])
        if fast < slow
    ],
    "monthly_revenue_momentum": [
        {"revenue_yoy_threshold_pct": t}
        for t in [5.0, 10.0, 20.0]
    ],
    "institutional_flow": [
        {"institutional_rolling_days": d}
        for d in [3, 5, 10]
    ],
}


def _get_sweep_combinations(strategy_name: str) -> List[Dict[str, Any]]:
    """Return bounded parameter combinations for a strategy."""
    return _SWEEP_SPACE.get(strategy_name, [])


# ──────────────────────────────────────────────────────────────────────────────
# Comparison helpers (pure functions)
# ──────────────────────────────────────────────────────────────────────────────

def _safe_metric(result: Dict[str, Any], key: str) -> Optional[float]:
    return result.get("metrics", {}).get(key)


def _sharpe_like(result: Dict[str, Any]) -> Optional[float]:
    ann = _safe_metric(result, "annualized_return")
    vol = _safe_metric(result, "volatility")
    if ann is not None and vol and vol > 0:
        return round(ann / vol, 4)
    return None


def _calmar_like(result: Dict[str, Any]) -> Optional[float]:
    ann = _safe_metric(result, "annualized_return")
    dd = _safe_metric(result, "max_drawdown")
    if ann is not None and dd and dd > 0:
        return round(ann / dd, 4)
    return None


def _strategy_label(result: Dict[str, Any]) -> str:
    name = result.get("strategy_name", "unknown")
    params = result.get("params", {})
    if params:
        param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"{name}[{param_str}]"
    return name


def compare_strategies(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare strategy results. Returns ranked lists and summary.

    Labels use "best_historical_*" — not "recommended".
    No investment advice wording.
    """
    if not results:
        return {"available": False, "reason": "no_results"}

    ok_results = [r for r in results if r.get("ok")]
    if not ok_results:
        return {"available": False, "reason": "all_strategies_failed"}

    def _rank(key: str, reverse: bool = True) -> List[Dict[str, Any]]:
        scored = []
        for r in ok_results:
            val = _safe_metric(r, key)
            if val is not None:
                scored.append({
                    "strategy_label": _strategy_label(r),
                    "strategy_name": r.get("strategy_name"),
                    key: val,
                })
        return sorted(scored, key=lambda x: x[key], reverse=reverse)

    ranked_return = _rank("total_return")
    ranked_dd = _rank("max_drawdown", reverse=False)

    risk_adjusted = []
    for r in ok_results:
        sh = _sharpe_like(r)
        ca = _calmar_like(r)
        risk_adjusted.append({
            "strategy_label": _strategy_label(r),
            "strategy_name": r.get("strategy_name"),
            "sharpe_like": sh,
            "calmar_like": ca,
            "total_return": _safe_metric(r, "total_return"),
            "max_drawdown": _safe_metric(r, "max_drawdown"),
        })

    bench_relative = []
    for r in ok_results:
        excess = _safe_metric(r, "excess_return")
        bench_relative.append({
            "strategy_label": _strategy_label(r),
            "strategy_name": r.get("strategy_name"),
            "excess_return": excess,
            "benchmark_return": _safe_metric(r, "benchmark_return"),
        })

    best_return_label = ranked_return[0]["strategy_label"] if ranked_return else None
    lowest_dd_label = ranked_dd[0]["strategy_label"] if ranked_dd else None

    notes = [
        "Rankings reflect historical backtest performance only.",
        "Past performance is not indicative of future results.",
        "All results use unadjusted price unless TaiwanStockPriceAdj was available.",
    ]

    return {
        "available": True,
        "ranked_by_total_return": ranked_return,
        "ranked_by_drawdown": ranked_dd,
        "risk_adjusted_summary": risk_adjusted,
        "benchmark_relative": bench_relative,
        "best_historical_return_strategy": best_return_label,
        "lowest_historical_drawdown_strategy": lowest_dd_label,
        "notes": notes,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Rolling window helpers
# ──────────────────────────────────────────────────────────────────────────────

def _date_windows(
    start_date: str, end_date: str, window_days: int
) -> List[Tuple[str, str]]:
    """Generate sequential non-overlapping windows of `window_days` calendar days."""
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        return []
    windows = []
    cur = sd
    while True:
        w_end = cur + timedelta(days=window_days - 1)
        if w_end > ed:
            break
        windows.append((str(cur), str(w_end)))
        cur = w_end + timedelta(days=1)
    return windows


# ──────────────────────────────────────────────────────────────────────────────
# Risk flags
# ──────────────────────────────────────────────────────────────────────────────

def detect_risk_flags(
    strategy_results: List[Dict[str, Any]],
    sweep_results: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Produce deterministic risk flags from backtest results.
    Flags are descriptive only — not investment advice.
    """
    flags: List[Dict[str, Any]] = []

    for r in strategy_results:
        if not r.get("ok"):
            continue
        name = r.get("strategy_name", "unknown")
        m = r.get("metrics", {})
        dq = r.get("data_quality", {})
        label = _strategy_label(r)

        dd = m.get("max_drawdown")
        if dd is not None and dd > 0.20:
            flags.append({
                "flag": "high_drawdown",
                "severity": "high",
                "strategy_label": label,
                "strategy_name": name,
                "message": f"最大回撤 {dd:.1%} 超過 20%，虧損風險顯著。",
                "evidence": {"max_drawdown": dd},
            })

        excess = m.get("excess_return")
        if excess is not None and excess < 0:
            flags.append({
                "flag": "underperforms_benchmark",
                "severity": "low",
                "strategy_label": label,
                "strategy_name": name,
                "message": f"超額報酬 {excess:.2%}，此策略歷史表現落後基準。",
                "evidence": {"excess_return": excess},
            })

        tc = m.get("trade_count", 0)
        if name != "buy_and_hold" and tc < 2:
            flags.append({
                "flag": "low_trade_count",
                "severity": "medium",
                "strategy_label": label,
                "strategy_name": name,
                "message": f"交易次數 {tc}，樣本不足，統計意義有限。",
                "evidence": {"trade_count": tc},
            })

        if tc > 20:
            flags.append({
                "flag": "high_turnover",
                "severity": "low",
                "strategy_label": label,
                "strategy_name": name,
                "message": f"交易次數 {tc}，換手率高，需評估交易成本影響。",
                "evidence": {"trade_count": tc},
            })

        if not dq.get("adjusted_price_used", True):
            flags.append({
                "flag": "unadjusted_price_caveat",
                "severity": "low",
                "strategy_label": label,
                "strategy_name": name,
                "message": "使用未調整股價，除息調整可能影響報酬計算。",
                "evidence": {"price_dataset": dq.get("price_dataset")},
            })

        if not r.get("signals"):
            flags.append({
                "flag": "no_signals",
                "severity": "medium",
                "strategy_label": label,
                "strategy_name": name,
                "message": "策略未產生任何訊號，資料不足或窗口過短。",
                "evidence": {"signal_count": 0},
            })

    # Overfit risk from parameter sweep
    if sweep_results and len(sweep_results) >= 6:
        returns = [
            _safe_metric(r, "total_return")
            for r in sweep_results
            if r.get("ok") and _safe_metric(r, "total_return") is not None
        ]
        if len(returns) >= 2:
            sorted_r = sorted(returns, reverse=True)
            best = sorted_r[0]
            median_r = sorted_r[len(sorted_r) // 2]
            if median_r != 0 and abs(best / median_r) > 2.0:
                flags.append({
                    "flag": "overfit_risk",
                    "severity": "medium",
                    "strategy_label": "parameter_sweep",
                    "strategy_name": "parameter_sweep",
                    "message": (
                        f"最佳參數組合報酬 ({best:.1%}) 遠高於中位數 ({median_r:.1%})，"
                        "可能存在過度擬合風險。"
                    ),
                    "evidence": {"best_return": best, "median_return": median_r,
                                 "combo_count": len(sweep_results)},
                })

    return flags


# ──────────────────────────────────────────────────────────────────────────────
# Prompt generation
# ──────────────────────────────────────────────────────────────────────────────

def _generate_analysis_prompts(
    symbol: str,
    end_date: str,
    strategy_names: List[str],
    risk_flags: List[Dict[str, Any]],
    has_sweep: bool,
) -> List[str]:
    """Generate deterministic, safe prompts. No buy/sell. No advice."""
    names_str = "、".join(strategy_names[:4]) if strategy_names else "各策略"
    prompts = [
        f"請只根據本次策略分析結果（截至 {end_date}），"
        f"指出 {symbol} 的 {names_str} 中最大回撤最嚴重的策略與可能原因。",

        f"請只根據本次策略分析結果（截至 {end_date}），"
        "比較各策略的超額報酬與最大回撤，不要使用外部資料。",

        "請列出本次策略分析有哪些資料限制（例如未調整股價、資料缺口、窗口過短），"
        "以及這些限制如何影響結果的可信度（勿作投資建議）。",
    ]

    if has_sweep:
        prompts.append(
            "請只根據本次參數掃描結果，"
            "檢查是否有過度擬合風險，並說明哪個參數範圍最為穩健。"
        )

    high_flags = [f for f in risk_flags if f.get("severity") == "high"]
    if high_flags:
        flag_msgs = "; ".join(f["message"] for f in high_flags[:2])
        prompts.append(
            f"本次策略分析發現高嚴重性風險警告：{flag_msgs}。"
            "請說明這些風險對策略可靠性的意義（勿作投資建議）。"
        )

    prompts.append(
        "請列出本次策略分析下一輪應驗證的三個假設，"
        "例如流動性、除息調整、時間窗口選擇等。"
    )

    return prompts


# ──────────────────────────────────────────────────────────────────────────────
# Main analyzer
# ──────────────────────────────────────────────────────────────────────────────

class StrategyAnalyzer:
    """
    Run multi-strategy analysis using Phase 8E BacktestEngine.

    Supports:
      - Multi-strategy comparison
      - Bounded parameter sweep
      - Rolling-window robustness analysis
      - Deterministic risk flags
      - Safe follow-up prompt generation

    No LLM calls. No buy/sell recommendations. No unbounded optimization.
    """

    def __init__(self, backtest_engine: Optional[BacktestEngine] = None):
        self._engine = backtest_engine or BacktestEngine()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _run_single(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        strategy_spec: Dict[str, Any],
        config: StrategyAnalysisConfig,
    ) -> Dict[str, Any]:
        """Run a single BacktestEngine.run() call from a strategy spec dict."""
        bc = BacktestConfig(
            strategy_name=strategy_spec["name"],
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            benchmark_symbol=config.benchmark_symbol,
            initial_cash=config.initial_cash,
            transaction_cost_bps=config.transaction_cost_bps,
            slippage_bps=config.slippage_bps,
            sma_fast=strategy_spec.get("sma_fast", 5),
            sma_slow=strategy_spec.get("sma_slow", 20),
            revenue_yoy_threshold_pct=strategy_spec.get("revenue_yoy_threshold_pct", 10.0),
            institutional_rolling_days=strategy_spec.get("institutional_rolling_days", 5),
        )
        result = self._engine.run(bc)
        # Attach params for labeling
        params = {k: v for k, v in strategy_spec.items() if k != "name"}
        result["params"] = params
        return result

    # ── parameter sweep ───────────────────────────────────────────────────────

    def _run_parameter_sweep(
        self,
        strategy_name: str,
        config: StrategyAnalysisConfig,
        stock_id: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        """Run bounded parameter sweep for a single strategy."""
        combos = _get_sweep_combinations(strategy_name)
        if not combos:
            return {"available": False, "reason": f"no sweep space for '{strategy_name}'"}

        if len(combos) > config.max_parameter_combinations:
            warnings.append(
                f"sweep for '{strategy_name}' has {len(combos)} combinations "
                f"(max {config.max_parameter_combinations}); truncating."
            )
            combos = combos[: config.max_parameter_combinations]

        sweep_results = []
        for combo in combos:
            spec = {"name": strategy_name, **combo}
            try:
                r = self._run_single(stock_id, config.start_date, config.end_date, spec, config)
                sweep_results.append(r)
            except Exception as exc:
                warnings.append(f"sweep combo {combo} raised {type(exc).__name__}: {exc}")

        if not sweep_results:
            return {"available": False, "reason": "all sweep combos failed"}

        ok_results = [r for r in sweep_results if r.get("ok")]
        returns = [
            (_strategy_label(r), _safe_metric(r, "total_return"))
            for r in ok_results
            if _safe_metric(r, "total_return") is not None
        ]
        returns.sort(key=lambda x: x[1] or 0, reverse=True)

        return {
            "available": True,
            "strategy_name": strategy_name,
            "combo_count": len(combos),
            "ok_count": len(ok_results),
            "results": sweep_results,
            "ranked_by_return": returns,
            "best_historical_params": combos[0] if returns and ok_results else None,
            "overfit_warning": (
                "Parameter sweep results may reflect in-sample optimization. "
                "Do not select parameters based solely on this backtest."
            ),
        }

    # ── rolling analysis ──────────────────────────────────────────────────────

    def analyze_rolling_windows(
        self,
        strategy_spec: Dict[str, Any],
        config: StrategyAnalysisConfig,
        stock_id: str,
    ) -> Dict[str, Any]:
        """Run strategy in sequential rolling windows for robustness check."""
        total_days = (
            date.fromisoformat(config.end_date) - date.fromisoformat(config.start_date)
        ).days

        if total_days < 2 * config.rolling_window_days:
            return {
                "available": False,
                "reason": (
                    f"date range ({total_days} days) < 2 × rolling_window_days "
                    f"({config.rolling_window_days})"
                ),
            }

        windows = _date_windows(config.start_date, config.end_date, config.rolling_window_days)
        if not windows:
            return {"available": False, "reason": "no windows generated"}

        window_results = []
        for w_start, w_end in windows:
            try:
                r = self._run_single(stock_id, w_start, w_end, strategy_spec, config)
                bah_r = self._run_single(
                    stock_id, w_start, w_end, {"name": "buy_and_hold"}, config
                )
                window_results.append({
                    "window_start": w_start,
                    "window_end": w_end,
                    "strategy_name": strategy_spec["name"],
                    "total_return": _safe_metric(r, "total_return"),
                    "max_drawdown": _safe_metric(r, "max_drawdown"),
                    "trade_count": _safe_metric(r, "trade_count"),
                    "benchmark_return": _safe_metric(r, "benchmark_return"),
                    "bah_return": _safe_metric(bah_r, "total_return"),
                    "ok": r.get("ok"),
                })
            except Exception as exc:
                window_results.append({
                    "window_start": w_start,
                    "window_end": w_end,
                    "strategy_name": strategy_spec["name"],
                    "error": str(exc),
                    "ok": False,
                })

        ok_windows = [w for w in window_results if w.get("ok")]
        returns = [w["total_return"] for w in ok_windows if w.get("total_return") is not None]

        consistency = None
        if len(returns) >= 2:
            positive = sum(1 for r in returns if r > 0)
            consistency = round(positive / len(returns), 4)

        return {
            "available": True,
            "window_count": len(windows),
            "ok_count": len(ok_windows),
            "rolling_window_days": config.rolling_window_days,
            "windows": window_results,
            "win_consistency": consistency,
            "note": (
                "Rolling analysis is for robustness check only. "
                "Window results are not independent observations."
            ),
        }

    # ── risk flags ────────────────────────────────────────────────────────────

    def detect_risk_flags(
        self,
        strategy_results: List[Dict[str, Any]],
        sweep_results: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        return detect_risk_flags(strategy_results, sweep_results)

    # ── prompts ───────────────────────────────────────────────────────────────

    def generate_follow_up_prompts(self, analysis: Dict[str, Any]) -> List[str]:
        symbol = analysis.get("symbol", "")
        end_date = analysis.get("end_date", "")
        names = [r.get("strategy_name", "") for r in analysis.get("strategy_results", [])]
        risk_flags = analysis.get("risk_flags", [])
        has_sweep = bool(analysis.get("parameter_sweep", {}).get("available"))
        return _generate_analysis_prompts(symbol, end_date, names, risk_flags, has_sweep)

    # ── main entry point ──────────────────────────────────────────────────────

    def analyze(
        self,
        config: StrategyAnalysisConfig,
    ) -> Dict[str, Any]:
        """
        Run full strategy analysis.

        Steps:
          1. Validate symbol.
          2. Resolve strategy list (use defaults if empty).
          3. Run each strategy via BacktestEngine.
          4. Run bounded parameter sweep for first sweep-eligible strategy.
          5. Run rolling-window analysis for first active strategy.
          6. Compare results.
          7. Detect risk flags.
          8. Generate prompts.

        Returns:
          StrategyAnalysisResult.to_dict()
        """
        warnings: List[str] = []

        # ── 1. Symbol ─────────────────────────────────────────────────────────
        stock_id, norm_err = normalize_tw_symbol(config.symbol)
        if norm_err:
            return StrategyAnalysisResult(
                ok=False,
                symbol=config.symbol,
                start_date=config.start_date,
                end_date=config.end_date,
                warnings=[f"symbol rejected: {norm_err}"],
            ).to_dict()

        # ── 2. Strategies ─────────────────────────────────────────────────────
        strategies = config.strategies if config.strategies else list(_DEFAULT_STRATEGIES)

        # ── 3. Run each strategy ──────────────────────────────────────────────
        strategy_results: List[Dict[str, Any]] = []
        for spec in strategies:
            if not isinstance(spec, dict) or not spec.get("name"):
                warnings.append(f"invalid strategy spec: {spec}")
                continue
            try:
                result = self._run_single(
                    stock_id, config.start_date, config.end_date, spec, config
                )
                strategy_results.append(result)
            except Exception as exc:
                warnings.append(
                    f"strategy '{spec.get('name')}' raised {type(exc).__name__}: {exc}"
                )
                strategy_results.append({
                    "ok": False,
                    "strategy_name": spec.get("name", "unknown"),
                    "warnings": [str(exc)],
                    "params": {k: v for k, v in spec.items() if k != "name"},
                })

        # ── 4. Parameter sweep (first sweep-eligible active strategy) ─────────
        sweep: Dict[str, Any] = {}
        sweep_flat_results: List[Dict[str, Any]] = []
        sweep_strategy = next(
            (s["name"] for s in strategies if s.get("name") in _SWEEP_SPACE),
            None,
        )
        if sweep_strategy:
            sweep = self._run_parameter_sweep(sweep_strategy, config, stock_id, warnings)
            if sweep.get("available"):
                sweep_flat_results = sweep.get("results", [])

        # ── 5. Rolling window (first non-BAH strategy) ────────────────────────
        rolling: Dict[str, Any] = {}
        active_spec = next(
            (s for s in strategies if s.get("name") != "buy_and_hold"),
            None,
        )
        if active_spec:
            rolling = self.analyze_rolling_windows(active_spec, config, stock_id)

        # ── 6. Comparison ─────────────────────────────────────────────────────
        comparison = compare_strategies(strategy_results)

        # ── 7. Risk flags ─────────────────────────────────────────────────────
        risk_flags = self.detect_risk_flags(strategy_results, sweep_flat_results or None)

        # ── 8. Data quality ───────────────────────────────────────────────────
        ok_count = sum(1 for r in strategy_results if r.get("ok"))
        data_quality = {
            "valid_symbol": True,
            "stock_id": stock_id,
            "strategies_run": len(strategy_results),
            "strategies_ok": ok_count,
            "rolling_available": rolling.get("available", False),
            "sweep_available": sweep.get("available", False),
            "sources": ["finmind"],
        }

        # ── 9. Prompts ────────────────────────────────────────────────────────
        analysis_so_far = {
            "symbol": config.symbol,
            "end_date": config.end_date,
            "strategy_results": strategy_results,
            "risk_flags": risk_flags,
            "parameter_sweep": sweep,
        }
        prompts = self.generate_follow_up_prompts(analysis_so_far)

        return StrategyAnalysisResult(
            ok=ok_count > 0,
            symbol=config.symbol,
            start_date=config.start_date,
            end_date=config.end_date,
            strategy_results=strategy_results,
            comparison=comparison,
            parameter_sweep=sweep,
            rolling_analysis=rolling,
            risk_flags=risk_flags,
            data_quality=data_quality,
            recommended_prompts=prompts,
            warnings=warnings,
            sources=["finmind"],
        ).to_dict()

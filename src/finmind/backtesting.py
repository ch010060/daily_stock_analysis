# -*- coding: utf-8 -*-
"""
FinMind-backed TW Stock Backtesting Foundation — Phase 8E.

Provides:
  BacktestConfig     — configuration for a single backtest run
  BacktestResult     — structured result including metrics, equity curve, trades
  BacktestDataLoader — loads historical data via FinMind DAL
  BacktestEngine     — orchestrates strategy execution with T+1 rule

Design principles:
  - TW-only; rejects CN/A-share and non-TW symbols.
  - No LLM calls. No buy/sell recommendations in output.
  - Strict no-lookahead: signals on date T execute on T+1.
  - No short selling. No leverage. Long-only v1.
  - Single-symbol per run. Position: 0% or 100%.
  - Transaction cost + slippage modeled on execution.
  - Adjusted price (TaiwanStockPriceAdj, Backer tier) preferred but falls back
    to unadjusted (TaiwanStockPrice) with explicit caveat.
  - No CN/A-share datasets. No yfinance calls.
  - Guards evaluated per-call via FinMindDatasetFetcher.
  - All unit tests must be offline (MockLoader).
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.finmind.fetcher import FinMindDatasetFetcher
from src.finmind.tw_stock_analysis import normalize_tw_symbol

logger = logging.getLogger(__name__)

_CN_BUYSELL_TERMS = frozenset({
    "A股", "上證", "上证", "深證", "深证", "創業板", "创业板",
    "科創50", "科创50", "買進", "賣出", "買入", "卖出",
})


# ──────────────────────────────────────────────────────────────────────────────
# Config model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""

    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    benchmark_symbol: Optional[str] = None
    initial_cash: float = 1_000_000.0
    transaction_cost_bps: float = 10.0   # applied on buy AND sell
    slippage_bps: float = 5.0            # applied on buy entry only
    execution_lag_days: int = 1          # T+1 execution
    allow_short: bool = False            # must remain False in v1
    # SMA crossover params
    sma_fast: int = 5
    sma_slow: int = 20
    # Revenue momentum params
    revenue_yoy_threshold_pct: float = 10.0
    # Institutional flow params
    institutional_rolling_days: int = 5

    def validate(self) -> Optional[str]:
        if self.allow_short:
            return "allow_short=True: short selling not supported in v1"
        if self.execution_lag_days < 1:
            return "execution_lag_days must be >= 1 (T+1 minimum)"
        if self.initial_cash <= 0:
            return "initial_cash must be positive"
        if self.sma_fast >= self.sma_slow:
            return f"sma_fast ({self.sma_fast}) must be < sma_slow ({self.sma_slow})"
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Result model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    """Structured backtest result."""

    ok: bool
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    benchmark: Dict[str, Any] = field(default_factory=dict)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    recommended_prompts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "metrics": self.metrics,
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "signals": self.signals,
            "benchmark": self.benchmark,
            "data_quality": self.data_quality,
            "warnings": self.warnings,
            "sources": self.sources,
            "recommended_prompts": self.recommended_prompts,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Metrics computation (pure functions)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_metrics(
    equity_curve: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    initial_cash: float,
) -> Dict[str, Any]:
    """Compute portfolio metrics from equity curve and trades."""
    if not equity_curve:
        return {"error": "no_equity_curve", "total_return": None}

    values = [e["portfolio_value"] for e in equity_curve]
    n = len(values)
    initial = initial_cash
    final = values[-1]
    total_return = (final - initial) / initial if initial > 0 else 0.0
    annualized = (1 + total_return) ** (252.0 / n) - 1 if n > 1 else 0.0

    # Daily returns
    daily_returns = [
        (values[i] - values[i - 1]) / values[i - 1]
        for i in range(1, n)
        if values[i - 1] > 0
    ]
    volatility = 0.0
    if daily_returns:
        mean_r = sum(daily_returns) / len(daily_returns)
        var = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
        volatility = math.sqrt(var) * math.sqrt(252)

    # Max drawdown
    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    # Trade-level analysis (paired buy→sell)
    buy_trades = [t for t in trades if t.get("action") == "buy"]
    sell_trades = [t for t in trades if t.get("action") == "sell"]
    pairs = min(len(buy_trades), len(sell_trades))
    trade_returns = []
    for i in range(pairs):
        b = buy_trades[i]
        s = sell_trades[i]
        buy_val = b.get("price", 0) * b.get("shares", 0)
        sell_val = s.get("price", 0) * s.get("shares", 0)
        if buy_val > 0:
            trade_returns.append((sell_val - buy_val) / buy_val)

    win_rate = (
        sum(1 for r in trade_returns if r > 0) / len(trade_returns)
        if trade_returns else 0.0
    )
    avg_trade_return = sum(trade_returns) / len(trade_returns) if trade_returns else 0.0

    # Exposure
    in_market_days = sum(1 for e in equity_curve if e.get("position", 0) > 0)
    exposure_ratio = in_market_days / n if n > 0 else 0.0

    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized, 6),
        "max_drawdown": round(max_dd, 6),
        "volatility": round(volatility, 6),
        "win_rate": round(win_rate, 4),
        "trade_count": len(buy_trades),
        "average_trade_return": round(avg_trade_return, 6),
        "exposure_ratio": round(exposure_ratio, 4),
        "benchmark_return": None,
        "excess_return": None,
        "initial_cash": initial,
        "final_value": round(final, 2),
        "n_trading_days": n,
    }


def _compute_benchmark_return(
    benchmark_rows: List[Dict[str, Any]],
) -> Optional[float]:
    """Compute simple buy-and-hold return for benchmark."""
    if len(benchmark_rows) < 2:
        return None
    first_close = benchmark_rows[0].get("close")
    last_close = benchmark_rows[-1].get("close")
    if first_close and last_close and first_close > 0:
        return round((last_close - first_close) / first_close, 6)
    return None


def _build_equity_curve(
    trading_dates: List[str],
    price_by_date: Dict[str, float],
    trades: List[Dict[str, Any]],
    initial_cash: float,
) -> List[Dict[str, Any]]:
    """Build daily equity curve from trading dates, prices, and trade list."""
    by_exec: Dict[str, List[Dict]] = {}
    for t in sorted(trades, key=lambda x: x["execution_date"]):
        by_exec.setdefault(t["execution_date"], []).append(t)

    position = 0
    cash = initial_cash
    curve = []

    for date in trading_dates:
        for t in by_exec.get(date, []):
            if t["action"] == "buy":
                position = t["shares"]
                cash = t["cash_after"]
            elif t["action"] == "sell":
                position = 0
                cash = t["cash_after"]

        price = price_by_date.get(date)
        if price is None:
            continue

        portfolio_value = cash + position * price
        curve.append({
            "date": date,
            "portfolio_value": round(portfolio_value, 2),
            "position": position,
            "price": price,
            "cash": round(cash, 2),
        })

    return curve


def _execute_signals(
    signals: List[Dict[str, Any]],
    trading_dates: List[str],
    price_by_date: Dict[str, float],
    config: BacktestConfig,
) -> Tuple[List[Dict[str, Any]], int, float]:
    """Convert strategy signals to executed trades with T+1 and cost model."""
    date_idx = {d: i for i, d in enumerate(trading_dates)}

    position = 0
    cash = config.initial_cash
    trades: List[Dict[str, Any]] = []

    for sig in signals:
        signal_date = sig["signal_date"]
        action = sig["action"]

        sig_i = date_idx.get(signal_date)
        if sig_i is None:
            continue
        exec_i = sig_i + config.execution_lag_days
        if exec_i >= len(trading_dates):
            continue

        exec_date = trading_dates[exec_i]
        exec_price = price_by_date.get(exec_date)
        if exec_price is None or exec_price <= 0:
            continue

        if action == "buy" and position == 0:
            slippage_factor = 1.0 + config.slippage_bps / 10_000
            effective_price = exec_price * slippage_factor
            shares = int(cash / effective_price)
            if shares <= 0:
                continue
            trade_cost = shares * effective_price * config.transaction_cost_bps / 10_000
            cash -= shares * effective_price + trade_cost
            position = shares
            trades.append({
                "signal_date": signal_date,
                "execution_date": exec_date,
                "action": "buy",
                "price": round(effective_price, 4),
                "shares": shares,
                "cost": round(trade_cost, 4),
                "cash_after": round(cash, 2),
            })

        elif action == "sell" and position > 0:
            sell_cost = position * exec_price * config.transaction_cost_bps / 10_000
            cash += position * exec_price - sell_cost
            trades.append({
                "signal_date": signal_date,
                "execution_date": exec_date,
                "action": "sell",
                "price": round(exec_price, 4),
                "shares": position,
                "cost": round(sell_cost, 4),
                "cash_after": round(cash, 2),
            })
            position = 0

    return trades, position, cash


# ──────────────────────────────────────────────────────────────────────────────
# Data loader
# ──────────────────────────────────────────────────────────────────────────────

class BacktestDataLoader:
    """
    Load historical data from FinMind for backtesting.

    Price hierarchy:
      1. TaiwanStockPriceAdj (Backer tier; may be unavailable)
      2. TaiwanStockPrice (free; fallback with caveat)

    Trading dates: TaiwanStockTradingDate (no data_id required).
    """

    def __init__(self, fetcher: Optional[FinMindDatasetFetcher] = None):
        self._fetcher = fetcher or FinMindDatasetFetcher()

    def load_price_series(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjusted_preferred: bool = True,
    ) -> Dict[str, Any]:
        """
        Load price series for symbol. Returns sorted rows + metadata.

        Returns:
            {ok, rows, adjusted, caveat, source_dataset}
        """
        adjusted_used = False
        caveat = None

        if adjusted_preferred:
            try:
                r = self._fetcher.fetch(
                    "TaiwanStockPriceAdj",
                    data_id=symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
                if r.get("ok") and r.get("rows"):
                    return {
                        "ok": True,
                        "rows": sorted(r["rows"], key=lambda x: x.get("date", "")),
                        "adjusted": True,
                        "caveat": None,
                        "source_dataset": "TaiwanStockPriceAdj",
                    }
            except Exception as exc:
                logger.debug("TaiwanStockPriceAdj unavailable for %s: %s", symbol, exc)

            caveat = "TaiwanStockPriceAdj unavailable (Backer tier); using unadjusted TaiwanStockPrice"
            adjusted_used = False

        try:
            r = self._fetcher.fetch(
                "TaiwanStockPrice",
                data_id=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if r.get("ok") and r.get("rows"):
                return {
                    "ok": True,
                    "rows": sorted(r["rows"], key=lambda x: x.get("date", "")),
                    "adjusted": False,
                    "caveat": caveat or "using unadjusted TaiwanStockPrice",
                    "source_dataset": "TaiwanStockPrice",
                }
        except Exception as exc:
            logger.warning("TaiwanStockPrice unavailable for %s: %s", symbol, exc)

        return {
            "ok": False,
            "rows": [],
            "adjusted": False,
            "caveat": "price data unavailable",
            "source_dataset": None,
        }

    def load_trading_dates(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Load TW market trading dates.

        TaiwanStockTradingDate has data_id_required=false in registry;
        fetch without data_id. If unavailable, fall back to weekday heuristic.
        """
        try:
            r = self._fetcher.fetch(
                "TaiwanStockTradingDate",
                data_id=None,
                start_date=start_date,
                end_date=end_date,
            )
            if r.get("ok") and r.get("rows"):
                dates = sorted({row.get("date") for row in r["rows"] if row.get("date")})
                return {"ok": True, "dates": dates, "source": "TaiwanStockTradingDate"}
        except Exception as exc:
            logger.warning("TaiwanStockTradingDate fetch failed: %s", exc)

        # Weekday fallback
        dates = _weekday_dates(start_date, end_date)
        return {
            "ok": True,
            "dates": dates,
            "source": "weekday_heuristic",
            "caveat": "TaiwanStockTradingDate unavailable; using weekday approximation",
        }

    def load_monthly_revenue(
        self, symbol: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        try:
            r = self._fetcher.fetch(
                "TaiwanStockMonthRevenue",
                data_id=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            rows = sorted(r.get("rows", []), key=lambda x: x.get("date", ""))
            return {"ok": r.get("ok", False), "rows": rows}
        except Exception as exc:
            logger.warning("TaiwanStockMonthRevenue failed: %s", exc)
            return {"ok": False, "rows": []}

    def load_institutional_flow(
        self, symbol: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        try:
            r = self._fetcher.fetch(
                "TaiwanStockInstitutionalInvestorsBuySell",
                data_id=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            rows = sorted(r.get("rows", []), key=lambda x: x.get("date", ""))
            return {"ok": r.get("ok", False), "rows": rows}
        except Exception as exc:
            logger.warning("TaiwanStockInstitutionalInvestorsBuySell failed: %s", exc)
            return {"ok": False, "rows": []}

    def load_margin(self, symbol: str, start_date: str, end_date: str) -> Dict[str, Any]:
        try:
            r = self._fetcher.fetch(
                "TaiwanStockMarginPurchaseShortSale",
                data_id=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            rows = sorted(r.get("rows", []), key=lambda x: x.get("date", ""))
            return {"ok": r.get("ok", False), "rows": rows}
        except Exception as exc:
            logger.warning("TaiwanStockMarginPurchaseShortSale failed: %s", exc)
            return {"ok": False, "rows": []}


def _weekday_dates(start_date: str, end_date: str) -> List[str]:
    """Generate weekday dates (Mon–Fri) as a trading calendar approximation."""
    from datetime import date, timedelta
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        return []
    dates = []
    cur = sd
    while cur <= ed:
        if cur.weekday() < 5:
            dates.append(str(cur))
        cur += timedelta(days=1)
    return dates


# ──────────────────────────────────────────────────────────────────────────────
# Summary helper
# ──────────────────────────────────────────────────────────────────────────────

def summarize_backtest_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a structured summary from a backtest result dict.

    Returns metrics, warnings, data_quality, and safe follow-up prompts.
    No buy/sell instructions. No future return implications.
    """
    metrics = result.get("metrics", {})
    warnings = list(result.get("warnings", []))
    dq = result.get("data_quality", {})

    # Deterministic follow-up prompts (safe, no buy/sell)
    prompts = [
        "請只根據本次回測結果（不參考外部資料），指出最大回撤最大的時間區間及可能原因。",
        "請檢查這個策略是否可能因為交易成本而失效，並說明損益平衡所需的最低報酬率。",
        "請列出這個回測最需要額外驗證的三個假設（例如流動性、除息調整、資料延遲）。",
        "請指出這個策略是否有過度擬合風險，但不要假設未提供的資料或未來市場條件。",
    ]

    if metrics.get("n_trading_days") and metrics["n_trading_days"] < 60:
        warnings.append(
            f"回測區間僅 {metrics['n_trading_days']} 個交易日，統計顯著性有限，"
            "結果不應用於任何投資決策。"
        )

    return {
        "metrics": metrics,
        "warnings": warnings,
        "data_quality": dq,
        "recommended_follow_up_prompts": prompts,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Prompt generation
# ──────────────────────────────────────────────────────────────────────────────

def _generate_backtest_prompts(
    strategy_name: str,
    end_date: str,
    metrics: Dict[str, Any],
    warnings: List[str],
) -> List[str]:
    """Generate deterministic, safe analysis prompts. No buy/sell."""
    prompts = []

    dd = metrics.get("max_drawdown")
    if dd is not None:
        prompts.append(
            f"只根據本次回測資料（截至 {end_date}），"
            f"分析 {strategy_name} 策略最大回撤（{dd:.1%}）最可能發生的市場情境。"
        )

    tc = metrics.get("trade_count")
    if tc is not None:
        prompts.append(
            f"只根據本次回測資料（截至 {end_date}），"
            f"評估 {strategy_name} 策略交易次數（{tc} 次）與交易成本的合理性。"
        )

    if warnings:
        prompts.append(
            f"本次回測有以下資料品質警告：{'; '.join(warnings[:3])}。"
            "請說明這些限制對結果可靠性的影響（勿作投資建議）。"
        )

    prompts.append(
        "請列出這個回測最需要額外驗證的三個假設，"
        "例如流動性假設、無除息調整風險、資料可用時間等。"
    )

    return prompts


# ──────────────────────────────────────────────────────────────────────────────
# Main engine
# ──────────────────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    FinMind-backed TW stock backtesting engine.

    Dispatches to strategy functions in src.finmind.strategies.
    Enforces T+1 execution, cost model, no-lookahead, no short, no leverage.
    """

    def __init__(self, data_loader: Optional[BacktestDataLoader] = None):
        self._loader = data_loader or BacktestDataLoader()

    def run(self, config: BacktestConfig) -> Dict[str, Any]:
        """
        Run a single backtest.

        Args:
            config: BacktestConfig with strategy_name, symbol, dates, params.

        Returns:
            BacktestResult.to_dict() — structured result dict.
        """
        from src.finmind.strategies import get_strategy_fn  # avoid circular import

        warnings: List[str] = []
        data_quality: Dict[str, Any] = {"valid_symbol": False}

        # ── 1. Config validation ──────────────────────────────────────────────
        config_err = config.validate()
        if config_err:
            return BacktestResult(
                ok=False,
                strategy_name=config.strategy_name,
                symbol=config.symbol,
                start_date=config.start_date,
                end_date=config.end_date,
                warnings=[f"config validation failed: {config_err}"],
            ).to_dict()

        # ── 2. Symbol normalization ───────────────────────────────────────────
        stock_id, norm_err = normalize_tw_symbol(config.symbol)
        if norm_err:
            return BacktestResult(
                ok=False,
                strategy_name=config.strategy_name,
                symbol=config.symbol,
                start_date=config.start_date,
                end_date=config.end_date,
                warnings=[f"symbol rejected: {norm_err}"],
            ).to_dict()

        data_quality["valid_symbol"] = True
        data_quality["stock_id"] = stock_id

        # ── 3. Strategy lookup ────────────────────────────────────────────────
        strategy_fn = get_strategy_fn(config.strategy_name)
        if strategy_fn is None:
            return BacktestResult(
                ok=False,
                strategy_name=config.strategy_name,
                symbol=config.symbol,
                start_date=config.start_date,
                end_date=config.end_date,
                warnings=[
                    f"unknown strategy '{config.strategy_name}'; "
                    "available: buy_and_hold, sma_crossover, monthly_revenue_momentum"
                ],
            ).to_dict()

        # ── 4. Load data ──────────────────────────────────────────────────────
        price_data = self._loader.load_price_series(
            stock_id, config.start_date, config.end_date
        )
        if not price_data["ok"] or not price_data["rows"]:
            return BacktestResult(
                ok=False,
                strategy_name=config.strategy_name,
                symbol=config.symbol,
                start_date=config.start_date,
                end_date=config.end_date,
                warnings=["price data unavailable"],
                data_quality=data_quality,
            ).to_dict()

        if price_data.get("caveat"):
            warnings.append(price_data["caveat"])
        data_quality["adjusted_price_used"] = price_data.get("adjusted", False)
        data_quality["price_dataset"] = price_data.get("source_dataset")

        price_rows = price_data["rows"]
        price_by_date = {r["date"]: r.get("close") for r in price_rows if r.get("close")}

        trading_dates_data = self._loader.load_trading_dates(
            config.start_date, config.end_date
        )
        trading_dates = trading_dates_data.get("dates", [])
        if not trading_dates:
            warnings.append("trading dates unavailable; falling back to price row dates")
            trading_dates = sorted(price_by_date.keys())
        if trading_dates_data.get("caveat"):
            warnings.append(trading_dates_data["caveat"])
        data_quality["trading_calendar_source"] = trading_dates_data.get("source")

        # Filter trading dates to those with price data
        trading_dates = [d for d in trading_dates if d in price_by_date]

        revenue_data = self._loader.load_monthly_revenue(
            stock_id, config.start_date, config.end_date
        )
        inst_data = self._loader.load_institutional_flow(
            stock_id, config.start_date, config.end_date
        )

        # ── 5. Generate signals ───────────────────────────────────────────────
        signals = strategy_fn(
            price_rows=price_rows,
            trading_dates=trading_dates,
            config=config,
            revenue_rows=revenue_data.get("rows", []),
            institutional_rows=inst_data.get("rows", []),
        )

        if not signals and config.strategy_name != "buy_and_hold":
            warnings.append(
                f"strategy '{config.strategy_name}' generated 0 signals "
                "(insufficient data or no crossover in window)"
            )

        # ── 6. Execute signals ────────────────────────────────────────────────
        trades, final_position, final_cash = _execute_signals(
            signals, trading_dates, price_by_date, config
        )

        # ── 7. Equity curve ───────────────────────────────────────────────────
        equity_curve = _build_equity_curve(
            trading_dates, price_by_date, trades, config.initial_cash
        )

        # ── 8. Metrics ────────────────────────────────────────────────────────
        metrics = _compute_metrics(equity_curve, trades, config.initial_cash)

        # ── 9. Benchmark ──────────────────────────────────────────────────────
        benchmark: Dict[str, Any] = {"available": False}
        if config.benchmark_symbol:
            bench_id, bench_err = normalize_tw_symbol(config.benchmark_symbol)
            if bench_err:
                warnings.append(f"benchmark symbol rejected: {bench_err}")
            else:
                bench_price = self._loader.load_price_series(
                    bench_id, config.start_date, config.end_date
                )
                if bench_price["ok"] and bench_price["rows"]:
                    b_rows = bench_price["rows"]
                    bench_ret = _compute_benchmark_return(b_rows)
                    benchmark = {
                        "available": True,
                        "symbol": config.benchmark_symbol,
                        "benchmark_return": bench_ret,
                        "row_count": len(b_rows),
                    }
                    if bench_ret is not None:
                        metrics["benchmark_return"] = bench_ret
                        metrics["excess_return"] = round(
                            metrics["total_return"] - bench_ret, 6
                        )
                else:
                    warnings.append(
                        f"benchmark '{config.benchmark_symbol}' data unavailable"
                    )

        # ── 10. Data quality ──────────────────────────────────────────────────
        data_quality.update({
            "price_rows": len(price_rows),
            "trading_dates_used": len(trading_dates),
            "revenue_rows": len(revenue_data.get("rows", [])),
            "institutional_rows": len(inst_data.get("rows", [])),
            "short_window_warning": metrics.get("n_trading_days", 0) < 60,
        })

        # ── 11. Prompts ───────────────────────────────────────────────────────
        prompts = _generate_backtest_prompts(
            config.strategy_name, config.end_date, metrics, warnings
        )

        return BacktestResult(
            ok=True,
            strategy_name=config.strategy_name,
            symbol=config.symbol,
            start_date=config.start_date,
            end_date=config.end_date,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            signals=signals,
            benchmark=benchmark,
            data_quality=data_quality,
            warnings=warnings,
            sources=["finmind"],
            recommended_prompts=prompts,
        ).to_dict()

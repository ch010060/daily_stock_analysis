# -*- coding: utf-8 -*-
"""
FinMind Panel Bundle and LLM-safe Prompt Interaction — Phase 8G.

Assembles structured panel bundles from Phase 8C/8D/8E/8F collectors.

Design principles:
  - Deterministic: same inputs always produce same panel_id / prompt_id.
  - No LLM calls. No buy/sell recommendations.
  - Each prompt card is bound to panel_id, snapshot_id (bundle_id), allowed context,
    and data freshness. Prompts say "只根據本 X panel 的資料".
  - Collector failures create error panels; they do not crash the bundle.
  - No CN/A-share datasets. No external data fetch requests in prompts.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from src.finmind.tw_stock_analysis import normalize_tw_symbol

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_FORBIDDEN_PROMPT_TERMS = frozenset({
    "買進", "賣出", "買進", "賣出", "推薦買", "推薦賣",
    "保證", "必漲", "必跌", "請上網查", "即時搜尋",
})

PANEL_TYPES = frozenset({
    "market_overview",
    "latest_info",
    "stock_analysis",
    "backtest",
    "strategy_analysis",
    "data_quality",
})


# ──────────────────────────────────────────────────────────────────────────────
# Deterministic ID helpers
# ──────────────────────────────────────────────────────────────────────────────

def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def make_bundle_id(symbols: List[str], start_date: str, end_date: str) -> str:
    key = ",".join(sorted(symbols)) + f":{start_date}:{end_date}"
    return "bnd_" + _md5(key)


def make_panel_id(bundle_id: str, panel_type: str, symbol: Optional[str] = None) -> str:
    key = f"{bundle_id}:{panel_type}:{symbol or '_'}"
    return "pnl_" + _md5(key)


def make_prompt_id(panel_id: str, title: str) -> str:
    key = f"{panel_id}:{title}"
    return "prc_" + _md5(key)


# ──────────────────────────────────────────────────────────────────────────────
# Prompt card safety
# ──────────────────────────────────────────────────────────────────────────────

def check_prompt_safety(prompt: str) -> List[str]:
    """Return list of forbidden terms found in prompt."""
    return [t for t in _FORBIDDEN_PROMPT_TERMS if t in prompt]


def build_prompt_card(
    panel_id: str,
    snapshot_id: str,
    title: str,
    prompt: str,
    allowed_context: List[str],
    data_freshness: Dict[str, Any],
    caveats: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a LLM-safe prompt card dict."""
    violations = check_prompt_safety(prompt)
    if violations:
        logger.warning("Prompt card '%s' contains forbidden terms: %s", title, violations)
        safety_tags = ["safety_violation"]
    else:
        safety_tags = ["no_buysell", "no_external_fetch", "snapshot_bound"]

    return {
        "prompt_id": make_prompt_id(panel_id, title),
        "title": title,
        "prompt": prompt,
        "panel_id": panel_id,
        "snapshot_id": snapshot_id,
        "allowed_context": allowed_context,
        "data_freshness": data_freshness,
        "safety_tags": safety_tags,
        "caveats": caveats or [],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Panel builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_latest_info_panel(
    panel_id: str,
    bundle_id: str,
    symbol: str,
    end_date: str,
    li_result: Dict[str, Any],
) -> Dict[str, Any]:
    events = li_result.get("events", [])
    event_count = li_result.get("event_count", len(events))
    missing = li_result.get("missing", [])
    dq = li_result.get("data_quality", {})
    warnings_list: List[str] = []
    if missing:
        warnings_list.append(f"缺少資料集：{', '.join(missing)}")

    event_types = list({e.get("event_type") for e in events if e.get("event_type")})
    high_severity = [e for e in events if e.get("severity") == "high"]

    key_metrics: Dict[str, Any] = {
        "event_count": event_count,
        "event_types": event_types,
        "high_severity_events": len(high_severity),
        "datasets_ok": dq.get("freshness", {}).get("datasets_ok", []),
        "datasets_missing": missing,
    }

    missing_str = f" 缺少資料集：{', '.join(missing)}。" if missing else ""
    summary = (
        f"最新資訊 panel：{symbol} 共 {event_count} 個事件，"
        f"型別：{', '.join(event_types) or '無'}，"
        f"資料截止 {end_date}。{missing_str}"
    )

    data_freshness: Dict[str, Any] = {"as_of": end_date, "datasets_missing": missing}

    prompt_cards = [
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="最新事件摘要",
            prompt=(
                f"請只根據本 latest_info panel 的資料（資料截止 {end_date}），"
                f"整理 {symbol} 最重要的三個事件，標出資料不足處，勿引用外部資料。"
            ),
            allowed_context=["latest_info_panel"],
            data_freshness=data_freshness,
            caveats=[f"資料截止 {end_date}，部分資料集可能有延遲"] if missing else [],
        ),
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="需確認事件",
            prompt=(
                f"請只根據本 latest_info panel 的事件（截止 {end_date}），"
                f"指出哪些資訊需要下一個交易日確認，不得引用即時外部資訊。"
            ),
            allowed_context=["latest_info_panel"],
            data_freshness=data_freshness,
            caveats=["需等下一個交易日確認的事件以 confidence=estimated 標示"],
        ),
    ]
    if missing:
        prompt_cards.append(
            build_prompt_card(
                panel_id=panel_id,
                snapshot_id=bundle_id,
                title="資料缺口說明",
                prompt=(
                    f"請只根據本 latest_info panel（資料截止 {end_date}），指出因資料缺口"
                    f"（{', '.join(missing)}）無法作為強結論依據的專案，不得引用外部資訊。"
                ),
                allowed_context=["latest_info_panel"],
                data_freshness=data_freshness,
                caveats=[f"缺少資料集：{', '.join(missing)}"],
            )
        )

    return {
        "panel_id": panel_id,
        "panel_type": "latest_info",
        "title": f"最新資訊 — {symbol}",
        "symbol": symbol,
        "date_range": {"start": li_result.get("start_date", ""), "end": end_date},
        "summary": summary,
        "key_metrics": key_metrics,
        "data_quality": dq,
        "missing": missing,
        "warnings": warnings_list,
        "sources": [li_result.get("source", "finmind")],
        "prompt_cards": prompt_cards,
    }


def _build_stock_analysis_panel(
    panel_id: str,
    bundle_id: str,
    symbol: str,
    end_date: str,
    sa_result: Dict[str, Any],
) -> Dict[str, Any]:
    dq = sa_result.get("data_quality", {})
    missing = sa_result.get("missing", [])
    warnings_list = list(sa_result.get("warnings", []))
    sections = sa_result.get("sections", {})

    pv = sections.get("price_volume", {})
    latest_close = pv.get("latest_close")
    latest_date = pv.get("latest_date")

    val = sections.get("valuation", {})
    per = val.get("latest_per")
    pbr = val.get("latest_pbr")

    rev = sections.get("monthly_revenue", {})
    latest_rev = rev.get("latest_monthly_revenue")

    key_metrics: Dict[str, Any] = {
        "latest_close": latest_close,
        "latest_date": latest_date,
        "latest_per": per,
        "latest_pbr": pbr,
        "latest_monthly_revenue": latest_rev,
        "sections_ok": [s for s in sections if s not in missing],
        "sections_missing": missing,
        "adjusted_price_used": dq.get("adjusted_price_used"),
    }

    missing_str = f" 缺少區段：{', '.join(missing)}。" if missing else ""
    summary = (
        f"個股分析 panel：{symbol} 最新收盤 {latest_close}（{latest_date}），"
        f"PER={per}, PBR={pbr}，月營收={latest_rev}。{missing_str}"
    )

    data_freshness: Dict[str, Any] = {"as_of": end_date, "sections_missing": missing}

    prompt_cards = [
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="個股重要變化",
            prompt=(
                f"請只根據本 stock_analysis panel 的資料（截至 {end_date}），"
                f"整理 {symbol} 最重要的三個變化，並標出資料不足處，勿引用外部資料。"
            ),
            allowed_context=["stock_analysis_panel"],
            data_freshness=data_freshness,
            caveats=[f"以下區段資料缺失：{', '.join(missing)}"] if missing else [],
        ),
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="估值分析",
            prompt=(
                f"請只根據本 stock_analysis panel 的估值欄位（PER/PBR，截至 {end_date}），"
                f"描述 {symbol} 的估值水位，不得作出買賣判斷。"
            ),
            allowed_context=["stock_analysis_panel"],
            data_freshness=data_freshness,
            caveats=["估值資料可能有資料源延遲，以 data_quality 欄位為準"],
        ),
    ]

    return {
        "panel_id": panel_id,
        "panel_type": "stock_analysis",
        "title": f"個股分析 — {symbol}",
        "symbol": symbol,
        "date_range": {"start": sa_result.get("start_date", ""), "end": end_date},
        "summary": summary,
        "key_metrics": key_metrics,
        "data_quality": dq,
        "missing": missing,
        "warnings": warnings_list,
        "sources": list(sa_result.get("sources", [])),
        "prompt_cards": prompt_cards,
    }


def _build_backtest_panel(
    panel_id: str,
    bundle_id: str,
    symbol: str,
    end_date: str,
    bt_result: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = bt_result.get("metrics", {})
    dq = bt_result.get("data_quality", {})
    warnings_list = list(bt_result.get("warnings", []))
    strategy_name = bt_result.get("strategy_name", "unknown")
    ok = bt_result.get("ok", False)

    total_return = metrics.get("total_return")
    max_drawdown = metrics.get("max_drawdown")
    trade_count = metrics.get("trade_count")
    benchmark = bt_result.get("benchmark", {})
    bench_return = benchmark.get("benchmark_return")

    key_metrics: Dict[str, Any] = {
        "strategy_name": strategy_name,
        "ok": ok,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "trade_count": trade_count,
        "benchmark_return": bench_return,
        "adjusted_price_used": dq.get("adjusted_price_used"),
    }

    if isinstance(total_return, float) and isinstance(max_drawdown, float):
        summary = (
            f"回測 panel（{strategy_name}）：{symbol} ok={ok}，"
            f"總回報={total_return:.2%}，最大回撤={max_drawdown:.2%}，"
            f"交易次數={trade_count}。"
        )
    else:
        summary = f"回測 panel（{strategy_name}）：{symbol} ok={ok}，結果不完整。"

    data_freshness: Dict[str, Any] = {
        "as_of": end_date,
        "adjusted_price_used": dq.get("adjusted_price_used", False),
    }

    prompt_cards = [
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="回測成本分析",
            prompt=(
                f"請只根據本 backtest panel（{strategy_name}，截至 {end_date}），"
                f"檢查交易成本與滑價是否足以改變策略的回測結論，不得推論未來報酬。"
            ),
            allowed_context=["backtest_panel"],
            data_freshness=data_freshness,
            caveats=[
                "所有結果為歷史回測，不代表未來表現",
                "如 adjusted_price_used=False 則使用未還原股價",
            ],
        ),
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="回測資料品質",
            prompt=(
                f"請只根據本 backtest panel 的 data_quality 欄位（截至 {end_date}），"
                f"描述 {symbol} 回測資料的完整性限制，不得引用外部資訊。"
            ),
            allowed_context=["backtest_panel"],
            data_freshness=data_freshness,
            caveats=["回測資料品質以 data_quality 欄位為準"],
        ),
    ]

    return {
        "panel_id": panel_id,
        "panel_type": "backtest",
        "title": f"回測 — {symbol} ({strategy_name})",
        "symbol": symbol,
        "date_range": {
            "start": bt_result.get("start_date", ""),
            "end": bt_result.get("end_date", end_date),
        },
        "summary": summary,
        "key_metrics": key_metrics,
        "data_quality": dq,
        "missing": [],
        "warnings": warnings_list,
        "sources": list(bt_result.get("sources", [])),
        "prompt_cards": prompt_cards,
    }


def _build_strategy_analysis_panel(
    panel_id: str,
    bundle_id: str,
    symbol: str,
    end_date: str,
    sa_result: Dict[str, Any],
) -> Dict[str, Any]:
    comparison = sa_result.get("comparison", {})
    risk_flags = sa_result.get("risk_flags", [])
    dq = sa_result.get("data_quality", {})
    warnings_list = list(sa_result.get("warnings", []))
    strategy_results = sa_result.get("strategy_results", [])

    strategy_count = len(strategy_results)
    risk_count = len(risk_flags)
    best_historical = comparison.get("best_historical_return_strategy")
    lowest_drawdown = comparison.get("lowest_historical_drawdown_strategy")
    overfit_flags = [f for f in risk_flags if f.get("flag") == "overfit_risk"]

    key_metrics: Dict[str, Any] = {
        "strategy_count": strategy_count,
        "risk_flags_count": risk_count,
        "best_historical_return_strategy": best_historical,
        "lowest_historical_drawdown_strategy": lowest_drawdown,
        "overfit_risk_flags": len(overfit_flags),
        "risk_flag_names": [f.get("flag") for f in risk_flags],
    }

    overfit_note = f" 過度擬合風險旗標：{len(overfit_flags)} 個。" if overfit_flags else ""
    summary = (
        f"策略分析 panel：{symbol} 共 {strategy_count} 個策略，"
        f"風險旗標 {risk_count} 個，"
        f"歷史回報最高策略（僅供參考）：{best_historical or '無'}，"
        f"歷史最低迴撤：{lowest_drawdown or '無'}。{overfit_note}"
    )

    data_freshness: Dict[str, Any] = {"as_of": end_date}

    prompt_cards = [
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="過度擬合風險",
            prompt=(
                f"請只根據本 strategy_analysis panel（截至 {end_date}），"
                f"指出 {symbol} 最明顯的過度擬合風險，不得推論未來報酬或建議買賣。"
            ),
            allowed_context=["strategy_analysis_panel"],
            data_freshness=data_freshness,
            caveats=["所有策略比較均為歷史回測，不代表未來表現"],
        ),
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="風險旗標說明",
            prompt=(
                f"請只根據本 strategy_analysis panel 的 risk_flags 欄位（截至 {end_date}），"
                f"說明 {symbol} 各策略的主要風險，不得引用外部資訊或建議投資決策。"
            ),
            allowed_context=["strategy_analysis_panel"],
            data_freshness=data_freshness,
            caveats=["risk_flags 為描述性旗標，非預測性指標"],
        ),
    ]

    return {
        "panel_id": panel_id,
        "panel_type": "strategy_analysis",
        "title": f"策略分析 — {symbol}",
        "symbol": symbol,
        "date_range": {
            "start": sa_result.get("start_date", ""),
            "end": sa_result.get("end_date", end_date),
        },
        "summary": summary,
        "key_metrics": key_metrics,
        "data_quality": dq,
        "missing": [],
        "warnings": warnings_list,
        "sources": list(sa_result.get("sources", [])),
        "prompt_cards": prompt_cards,
    }


def _build_data_quality_panel(
    panel_id: str,
    bundle_id: str,
    symbol: str,
    end_date: str,
    upstream_panels: List[Dict[str, Any]],
) -> Dict[str, Any]:
    all_missing: List[str] = []
    all_warnings: List[str] = []
    all_sources: List[str] = []
    tier_caveats: List[str] = []

    for p in upstream_panels:
        all_missing.extend(p.get("missing", []))
        all_warnings.extend(p.get("warnings", []))
        all_sources.extend(p.get("sources", []))
        pdq = p.get("data_quality", {})
        if pdq.get("adjusted_price_used") is False:
            tier_caveats.append(
                f"{p.get('panel_type')}: 使用未還原股價（TaiwanStockPriceAdj 需 Backer tier）"
            )

    unique_missing = list(dict.fromkeys(all_missing))
    unique_sources = list(dict.fromkeys(all_sources))
    unique_caveats = list(dict.fromkeys(tier_caveats))

    summary = (
        f"資料品質 panel：{symbol} 截至 {end_date}，"
        f"缺少資料集 {len(unique_missing)} 個，"
        f"tier 限制 {len(unique_caveats)} 個。"
    )

    key_metrics: Dict[str, Any] = {
        "missing_datasets": unique_missing,
        "tier_caveats": unique_caveats,
        "total_warnings": len(all_warnings),
        "data_sources": unique_sources,
    }

    data_freshness: Dict[str, Any] = {"as_of": end_date}

    prompt_cards = [
        build_prompt_card(
            panel_id=panel_id,
            snapshot_id=bundle_id,
            title="資料缺口分析",
            prompt=(
                f"請只根據本 data_quality panel（截至 {end_date}），"
                f"列出 {symbol} 不能支援強結論的資料缺口，不得引用外部資訊。"
            ),
            allowed_context=["data_quality_panel"],
            data_freshness=data_freshness,
            caveats=unique_caveats,
        ),
    ]

    return {
        "panel_id": panel_id,
        "panel_type": "data_quality",
        "title": f"資料品質 — {symbol}",
        "symbol": symbol,
        "date_range": {"start": "", "end": end_date},
        "summary": summary,
        "key_metrics": key_metrics,
        "data_quality": {
            "missing_datasets": unique_missing,
            "tier_caveats": unique_caveats,
        },
        "missing": unique_missing,
        "warnings": all_warnings[:20],
        "sources": unique_sources,
        "prompt_cards": prompt_cards,
    }


def _failure_panel(
    bundle_id: str,
    panel_type: str,
    symbol: str,
    end_date: str,
    error: str,
) -> Dict[str, Any]:
    pid = make_panel_id(bundle_id, panel_type, symbol)
    return {
        "panel_id": pid,
        "panel_type": panel_type,
        "title": f"{panel_type} — {symbol} [ERROR]",
        "symbol": symbol,
        "date_range": {"start": "", "end": end_date},
        "summary": f"Panel {panel_type} failed: {error}",
        "key_metrics": {},
        "data_quality": {"ok": False, "error": error},
        "missing": [panel_type],
        "warnings": [f"Panel {panel_type} 初始化失敗：{error}"],
        "sources": [],
        "prompt_cards": [],
        "_error": True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Panel Bundle Builder
# ──────────────────────────────────────────────────────────────────────────────

class PanelBundleBuilder:
    """
    Assembles a structured panel bundle from Phase 8C/8D/8E/8F collectors.

    No LLM calls. No live data fetching beyond the delegated collector calls.
    No buy/sell recommendations. Collector failures create error panels.
    """

    def __init__(
        self,
        latest_info_collector: Any = None,
        stock_analysis_collector: Any = None,
        backtest_engine: Any = None,
        strategy_analyzer: Any = None,
    ) -> None:
        self._li = latest_info_collector
        self._sa = stock_analysis_collector
        self._bt = backtest_engine
        self._strat = strategy_analyzer

    # ------------------------------------------------------------------
    # Lazy collector access
    # ------------------------------------------------------------------

    def _get_li(self) -> Any:
        if self._li is not None:
            return self._li
        try:
            from src.finmind.latest_info import LatestInfoCollector
            return LatestInfoCollector()
        except Exception as exc:
            logger.warning("LatestInfoCollector init failed: %s", exc)
            return None

    def _get_sa(self) -> Any:
        if self._sa is not None:
            return self._sa
        try:
            from src.finmind.tw_stock_analysis import TWStockAnalysisCollector
            return TWStockAnalysisCollector()
        except Exception as exc:
            logger.warning("TWStockAnalysisCollector init failed: %s", exc)
            return None

    def _get_bt(self) -> Any:
        if self._bt is not None:
            return self._bt
        try:
            from src.finmind.backtesting import BacktestEngine
            return BacktestEngine()
        except Exception as exc:
            logger.warning("BacktestEngine init failed: %s", exc)
            return None

    def _get_strat(self) -> Any:
        if self._strat is not None:
            return self._strat
        try:
            from src.finmind.strategy_analysis import StrategyAnalyzer
            return StrategyAnalyzer()
        except Exception as exc:
            logger.warning("StrategyAnalyzer init failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_stock_bundle(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        include_backtest: bool = True,
        include_strategy_analysis: bool = True,
    ) -> Dict[str, Any]:
        """
        Build a full panel bundle for a single TW stock symbol.
        Returns a dict serializable to JSON.
        """
        stock_id, norm_err = normalize_tw_symbol(symbol)
        if norm_err or not stock_id:
            return {
                "ok": False,
                "bundle_id": "",
                "symbols": [symbol],
                "start_date": start_date,
                "end_date": end_date,
                "panels": [],
                "data_quality": {"valid_symbol": False, "error": norm_err},
                "recommended_prompts": [],
                "sources": [],
                "warnings": [f"symbol rejected: {norm_err}"],
            }

        bnd_id = make_bundle_id([symbol], start_date, end_date)
        panels: List[Dict[str, Any]] = []
        all_warnings: List[str] = []
        all_sources: List[str] = []

        # ── Latest Info Panel ──────────────────────────────────────────
        li_obj = self._get_li()
        if li_obj is not None:
            try:
                li_result = li_obj.collect_latest_info_snapshot(
                    symbols=[symbol], start_date=start_date, end_date=end_date
                )
                pid = make_panel_id(bnd_id, "latest_info", symbol)
                panel = _build_latest_info_panel(pid, bnd_id, symbol, end_date, li_result)
                panels.append(panel)
                all_sources.extend(panel.get("sources", []))
                all_warnings.extend(panel.get("warnings", []))
            except Exception as exc:
                msg = f"latest_info panel failed: {exc}"
                logger.warning(msg)
                all_warnings.append(msg)
                panels.append(_failure_panel(bnd_id, "latest_info", symbol, end_date, str(exc)))
        else:
            msg = "LatestInfoCollector unavailable"
            all_warnings.append(msg)
            panels.append(_failure_panel(bnd_id, "latest_info", symbol, end_date, msg))

        # ── Stock Analysis Panel ───────────────────────────────────────
        sa_obj = self._get_sa()
        if sa_obj is not None:
            try:
                snap = sa_obj.collect_stock_analysis_snapshot(
                    symbol=symbol, start_date=start_date, end_date=end_date
                )
                sa_result = snap.to_dict() if hasattr(snap, "to_dict") else snap
                pid = make_panel_id(bnd_id, "stock_analysis", symbol)
                panel = _build_stock_analysis_panel(pid, bnd_id, symbol, end_date, sa_result)
                panels.append(panel)
                all_sources.extend(panel.get("sources", []))
                all_warnings.extend(panel.get("warnings", []))
            except Exception as exc:
                msg = f"stock_analysis panel failed: {exc}"
                logger.warning(msg)
                all_warnings.append(msg)
                panels.append(_failure_panel(bnd_id, "stock_analysis", symbol, end_date, str(exc)))
        else:
            msg = "TWStockAnalysisCollector unavailable"
            all_warnings.append(msg)
            panels.append(_failure_panel(bnd_id, "stock_analysis", symbol, end_date, msg))

        # ── Backtest Panel ─────────────────────────────────────────────
        if include_backtest:
            bt_obj = self._get_bt()
            if bt_obj is not None:
                try:
                    from src.finmind.backtesting import BacktestConfig
                    cfg = BacktestConfig(
                        strategy_name="buy_and_hold",
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    bt_result = bt_obj.run(cfg)
                    pid = make_panel_id(bnd_id, "backtest", symbol)
                    panel = _build_backtest_panel(pid, bnd_id, symbol, end_date, bt_result)
                    panels.append(panel)
                    all_sources.extend(panel.get("sources", []))
                    all_warnings.extend(panel.get("warnings", []))
                except Exception as exc:
                    msg = f"backtest panel failed: {exc}"
                    logger.warning(msg)
                    all_warnings.append(msg)
                    panels.append(_failure_panel(bnd_id, "backtest", symbol, end_date, str(exc)))
            else:
                msg = "BacktestEngine unavailable"
                all_warnings.append(msg)
                panels.append(_failure_panel(bnd_id, "backtest", symbol, end_date, msg))

        # ── Strategy Analysis Panel ────────────────────────────────────
        if include_strategy_analysis:
            strat_obj = self._get_strat()
            if strat_obj is not None:
                try:
                    from src.finmind.strategy_analysis import StrategyAnalysisConfig
                    scfg = StrategyAnalysisConfig(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    strat_result = strat_obj.analyze(scfg)
                    pid = make_panel_id(bnd_id, "strategy_analysis", symbol)
                    panel = _build_strategy_analysis_panel(
                        pid, bnd_id, symbol, end_date, strat_result
                    )
                    panels.append(panel)
                    all_sources.extend(panel.get("sources", []))
                    all_warnings.extend(panel.get("warnings", []))
                except Exception as exc:
                    msg = f"strategy_analysis panel failed: {exc}"
                    logger.warning(msg)
                    all_warnings.append(msg)
                    panels.append(
                        _failure_panel(bnd_id, "strategy_analysis", symbol, end_date, str(exc))
                    )
            else:
                msg = "StrategyAnalyzer unavailable"
                all_warnings.append(msg)
                panels.append(_failure_panel(bnd_id, "strategy_analysis", symbol, end_date, msg))

        # ── Data Quality Panel ─────────────────────────────────────────
        pid = make_panel_id(bnd_id, "data_quality", symbol)
        dq_panel = _build_data_quality_panel(pid, bnd_id, symbol, end_date, panels)
        panels.append(dq_panel)

        # ── Aggregate ─────────────────────────────────────────────────
        all_prompt_cards = [
            pc
            for p in panels
            for pc in p.get("prompt_cards", [])
        ]
        unique_sources = list(dict.fromkeys(all_sources))

        return {
            "ok": True,
            "bundle_id": bnd_id,
            "symbols": [symbol],
            "start_date": start_date,
            "end_date": end_date,
            "panels": panels,
            "data_quality": {
                "valid_symbol": True,
                "stock_id": stock_id,
                "panel_count": len(panels),
                "panels_with_errors": [
                    p.get("panel_type") for p in panels if p.get("_error")
                ],
            },
            "recommended_prompts": all_prompt_cards,
            "sources": unique_sources,
            "warnings": all_warnings,
        }

    def build_market_bundle(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Build a market-level bundle for multiple TW stock symbols.
        Runs latest_info and stock_analysis only (no backtest/strategy per symbol).
        """
        bnd_id = make_bundle_id(symbols, start_date, end_date)
        stock_bundles = []
        all_warnings: List[str] = []
        all_sources: List[str] = []

        for sym in symbols:
            b = self.build_stock_bundle(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                include_backtest=False,
                include_strategy_analysis=False,
            )
            stock_bundles.append(b)
            all_warnings.extend(b.get("warnings", []))
            all_sources.extend(b.get("sources", []))

        panels = [p for b in stock_bundles for p in b.get("panels", [])]

        return {
            "ok": any(b.get("ok") for b in stock_bundles),
            "bundle_id": bnd_id,
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
            "panels": panels,
            "data_quality": {
                "symbol_count": len(symbols),
                "symbols_ok": [
                    b.get("symbols", [None])[0]
                    for b in stock_bundles
                    if b.get("ok")
                ],
                "symbols_failed": [
                    b.get("symbols", [None])[0]
                    for b in stock_bundles
                    if not b.get("ok")
                ],
            },
            "recommended_prompts": [
                pc
                for b in stock_bundles
                for p in b.get("panels", [])
                for pc in p.get("prompt_cards", [])
            ],
            "sources": list(dict.fromkeys(all_sources)),
            "warnings": all_warnings,
        }

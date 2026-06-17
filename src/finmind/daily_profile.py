# -*- coding: utf-8 -*-
"""
FinMind Production Daily Profile Runner — Phase 8H.

Bundles Phase 8C/8D/8E/8F/8G collectors into a per-day, multi-symbol runner.

Design principles:
  - No LLM calls. No buy/sell recommendations. No notifications.
  - No CN/A-share datasets. TW symbols only.
  - Collector failures → failed_symbols; partial results ok if ≥1 symbol succeeds.
  - Profile ID and artifact names are deterministic from end_date + sorted symbols.
  - Artifact writing is optional; never committed.
  - Mode label is recorded in output; actual guards determined by env vars.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.finmind.tw_stock_analysis import normalize_tw_symbol

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_VALID_MODES = frozenset({"fixture", "no_network", "controlled_live", "production_live"})

_CN_TERMS = frozenset({
    "A股", "上證", "上證", "深證", "深證", "創業板", "創業板", "科創50", "科創50",
})

_BUYSELL_TERMS = frozenset({
    "買進", "賣出", "買進", "賣出", "推薦買", "推薦賣",
})


# ──────────────────────────────────────────────────────────────────────────────
# Deterministic ID
# ──────────────────────────────────────────────────────────────────────────────

def make_profile_id(symbols: List[str], start_date: str, end_date: str) -> str:
    key = ",".join(sorted(symbols)) + f":{start_date}:{end_date}"
    return "prf_" + hashlib.md5(key.encode()).hexdigest()[:12]


def _yyyymmdd(date_str: str) -> str:
    return date_str.replace("-", "")


# ──────────────────────────────────────────────────────────────────────────────
# Config model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DailyProfileConfig:
    """Configuration for a production daily profile run."""

    symbols: List[str]
    start_date: str
    end_date: str
    mode: str = "controlled_live"
    include_latest_info: bool = True
    include_stock_analysis: bool = True
    include_backtest: bool = True
    include_strategy_analysis: bool = True
    send_notification: bool = False


def _config_from_dict(d: Dict[str, Any]) -> DailyProfileConfig:
    return DailyProfileConfig(
        symbols=d.get("symbols", []),
        start_date=d.get("start_date", ""),
        end_date=d.get("end_date", ""),
        mode=d.get("mode", "controlled_live"),
        include_latest_info=d.get("include_latest_info", True),
        include_stock_analysis=d.get("include_stock_analysis", True),
        include_backtest=d.get("include_backtest", True),
        include_strategy_analysis=d.get("include_strategy_analysis", True),
        send_notification=False,  # never True in Phase 8H
    )


# ──────────────────────────────────────────────────────────────────────────────
# Data quality aggregation
# ──────────────────────────────────────────────────────────────────────────────

def build_data_quality_report(bundles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate cross-bundle data quality into a single report."""
    ok_symbols: List[str] = []
    failed_symbols: List[str] = []
    all_missing: List[str] = []
    all_warnings: List[str] = []
    all_sources: List[str] = []
    all_tier_caveats: List[str] = []

    for b in bundles:
        sym = (b.get("symbols") or [None])[0]
        if b.get("ok"):
            ok_symbols.append(sym)
        else:
            failed_symbols.append(sym)
        all_warnings.extend(b.get("warnings", []))
        all_sources.extend(b.get("sources", []))
        # Gather from panels inside the bundle
        for panel in b.get("panels", []):
            all_missing.extend(panel.get("missing", []))
            dq = panel.get("data_quality", {})
            caveats = dq.get("tier_caveats", [])
            all_tier_caveats.extend(caveats)

    unique_missing = list(dict.fromkeys(all_missing))
    unique_sources = list(dict.fromkeys(all_sources))
    unique_caveats = list(dict.fromkeys(all_tier_caveats))

    return {
        "ok": len(ok_symbols) > 0,
        "partial": len(failed_symbols) > 0 or len(unique_missing) > 0,
        "symbol_count": len(bundles),
        "ok_symbols": ok_symbols,
        "failed_symbols": failed_symbols,
        "missing": unique_missing,
        "warnings": all_warnings[:30],
        "tier_caveats": unique_caveats,
        "sources": unique_sources,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Prompt card deduplication
# ──────────────────────────────────────────────────────────────────────────────

def _collect_prompt_cards(bundles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collect and deduplicate prompt cards from all bundles by prompt_id."""
    seen_ids: set = set()
    result: List[Dict[str, Any]] = []
    for b in bundles:
        for pc in b.get("recommended_prompts", []):
            pid = pc.get("prompt_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                result.append(pc)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Artifact writing
# ──────────────────────────────────────────────────────────────────────────────

def _build_markdown_summary(result: Dict[str, Any]) -> str:
    end_date = result.get("end_date", "")
    symbols = result.get("symbols", [])
    mode = result.get("mode", "")
    dq = result.get("data_quality", {})
    warnings = result.get("warnings", [])
    prompts = result.get("recommended_prompts", [])

    lines = [
        f"# Daily Profile — {', '.join(symbols)} — {end_date}",
        "",
        "## 摘要",
        f"- ok: {result.get('ok')}",
        f"- 模式: {mode}",
        f"- 資料截止: {end_date}",
        f"- 成功 symbol: {dq.get('ok_symbols', [])}",
        f"- 失敗 symbol: {dq.get('failed_symbols', [])}",
        f"- profile_id: {result.get('profile_id')}",
        "",
        "## 資料品質",
        f"- symbol_count: {dq.get('symbol_count')}",
        f"- partial: {dq.get('partial')}",
        f"- missing: {dq.get('missing', [])}",
        f"- tier_caveats: {dq.get('tier_caveats', [])}",
        "",
        "## 警告",
    ]
    if warnings:
        for w in warnings[:10]:
            lines.append(f"- {w}")
    else:
        lines.append("- (無)")

    lines += [
        "",
        "## Prompt Cards",
        f"- 總計: {len(prompts)} 個",
    ]
    for pc in prompts[:5]:
        lines.append(f"  - [{pc.get('title')}] {pc.get('prompt', '')[:80]}...")

    lines += [
        "",
        "> 本 daily profile 為 FinMind 資料快照，不含買賣建議，不含即時資料。",
        f"> 資料截止 {end_date}，所有回測結果均為歷史績效，不代表未來表現。",
    ]
    return "\n".join(lines)


def write_artifacts(result: Dict[str, Any], output_dir: Union[str, Path]) -> Dict[str, str]:
    """Write daily profile artifacts to output_dir. Returns {name: path}."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    end_date = result.get("end_date", "20260101")
    suffix = _yyyymmdd(end_date)

    artifacts: Dict[str, str] = {}

    # Full profile JSON
    profile_path = out / f"daily_profile_{suffix}.json"
    profile_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts["daily_profile_json"] = str(profile_path)

    # Markdown summary
    md_path = out / f"daily_profile_{suffix}.md"
    md_path.write_text(_build_markdown_summary(result), encoding="utf-8")
    artifacts["daily_profile_md"] = str(md_path)

    # Data quality JSON
    dq_path = out / f"daily_data_quality_{suffix}.json"
    dq_path.write_text(
        json.dumps(result.get("data_quality", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifacts["daily_data_quality_json"] = str(dq_path)

    # Prompt cards JSON
    pc_path = out / f"daily_prompt_cards_{suffix}.json"
    pc_path.write_text(
        json.dumps(result.get("recommended_prompts", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifacts["daily_prompt_cards_json"] = str(pc_path)

    return artifacts


# ──────────────────────────────────────────────────────────────────────────────
# Daily Profile Runner
# ──────────────────────────────────────────────────────────────────────────────

class DailyProfileRunner:
    """
    Production daily profile runner for TW market.

    Runs PanelBundleBuilder for each TW symbol and assembles a unified
    daily profile result. No notifications. No LLM. No CN/A-share.
    """

    def __init__(
        self,
        panel_builder: Any = None,
        fixture_mode: Optional[bool] = None,
        allow_external_network: Optional[bool] = None,
    ) -> None:
        self._panel_builder = panel_builder
        self._fixture_mode = fixture_mode
        self._allow_external_network = allow_external_network

    def _get_builder(self) -> Any:
        if self._panel_builder is not None:
            return self._panel_builder
        try:
            from src.finmind.panels import PanelBundleBuilder
            return PanelBundleBuilder()
        except Exception as exc:
            logger.warning("PanelBundleBuilder init failed: %s", exc)
            return None

    def run(self, config: Union[DailyProfileConfig, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run daily profile for the given config.
        Returns a structured profile dict serializable to JSON.
        """
        if isinstance(config, dict):
            config = _config_from_dict(config)

        mode = config.mode if config.mode in _VALID_MODES else "controlled_live"

        # Validate and filter TW symbols
        valid_symbols: List[str] = []
        rejected_symbols: List[str] = []
        reject_warnings: List[str] = []

        for sym in config.symbols:
            stock_id, err = normalize_tw_symbol(sym)
            if err or not stock_id:
                rejected_symbols.append(sym)
                reject_warnings.append(f"symbol rejected: {sym} — {err}")
            else:
                valid_symbols.append(sym)

        profile_id = make_profile_id(config.symbols, config.start_date, config.end_date)

        if not valid_symbols:
            return {
                "ok": False,
                "profile_id": profile_id,
                "mode": mode,
                "symbols": config.symbols,
                "start_date": config.start_date,
                "end_date": config.end_date,
                "generated_at": config.end_date,
                "bundles": [],
                "data_quality": {
                    "ok": False,
                    "partial": False,
                    "symbol_count": 0,
                    "ok_symbols": [],
                    "failed_symbols": list(config.symbols),
                    "missing": [],
                    "warnings": reject_warnings,
                    "tier_caveats": [],
                    "sources": [],
                },
                "warnings": reject_warnings,
                "missing": [],
                "recommended_prompts": [],
                "sources": [],
                "artifacts": {},
            }

        builder = self._get_builder()
        bundles: List[Dict[str, Any]] = []
        all_warnings = list(reject_warnings)
        all_sources: List[str] = []

        for sym in valid_symbols:
            if builder is not None:
                try:
                    bundle = builder.build_stock_bundle(
                        symbol=sym,
                        start_date=config.start_date,
                        end_date=config.end_date,
                        include_backtest=config.include_backtest,
                        include_strategy_analysis=config.include_strategy_analysis,
                    )
                    bundles.append(bundle)
                    all_warnings.extend(bundle.get("warnings", []))
                    all_sources.extend(bundle.get("sources", []))
                except Exception as exc:
                    msg = f"bundle build failed for {sym}: {exc}"
                    logger.warning(msg)
                    all_warnings.append(msg)
                    bundles.append({
                        "ok": False,
                        "bundle_id": "",
                        "symbols": [sym],
                        "panels": [],
                        "data_quality": {"ok": False, "error": str(exc)},
                        "recommended_prompts": [],
                        "sources": [],
                        "warnings": [msg],
                    })
            else:
                msg = f"PanelBundleBuilder unavailable; cannot build bundle for {sym}"
                all_warnings.append(msg)
                bundles.append({
                    "ok": False,
                    "bundle_id": "",
                    "symbols": [sym],
                    "panels": [],
                    "data_quality": {"ok": False, "error": "builder unavailable"},
                    "recommended_prompts": [],
                    "sources": [],
                    "warnings": [msg],
                })

        dq = build_data_quality_report(bundles)
        # Include symbols rejected at validation stage in failed_symbols
        for sym in rejected_symbols:
            if sym not in dq["failed_symbols"]:
                dq["failed_symbols"].append(sym)
        dq["symbol_count"] = len(valid_symbols) + len(rejected_symbols)
        if rejected_symbols:
            dq["partial"] = True
        prompt_cards = _collect_prompt_cards(bundles)
        all_missing = list(dict.fromkeys(
            m for b in bundles for p in b.get("panels", []) for m in p.get("missing", [])
        ))
        unique_sources = list(dict.fromkeys(all_sources))

        return {
            "ok": dq["ok"],
            "profile_id": profile_id,
            "mode": mode,
            "symbols": config.symbols,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "generated_at": config.end_date,
            "bundles": bundles,
            "data_quality": dq,
            "warnings": all_warnings,
            "missing": all_missing,
            "recommended_prompts": prompt_cards,
            "sources": unique_sources,
            "artifacts": {},
        }

    def build_data_quality_report(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Re-derive data quality report from an existing profile result."""
        return build_data_quality_report(result.get("bundles", []))

    def write_artifacts(
        self,
        result: Dict[str, Any],
        output_dir: Union[str, Path],
    ) -> Dict[str, str]:
        """Write artifacts to output_dir. Returns {name: path}."""
        paths = write_artifacts(result, output_dir)
        # Update artifacts field in result (in-place for convenience)
        result["artifacts"] = paths
        return paths

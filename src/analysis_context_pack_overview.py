# -*- coding: utf-8 -*-
"""Low-sensitivity public overview for Issue #1389 AnalysisContextPack P4."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from src.analysis_context_pack_prompt import (
    SENSITIVE_MARKERS,
    analysis_context_pack_to_dict,
    get_analysis_context_pack_block_labels,
    iter_analysis_context_pack_block_keys,
)
from src.market_phase_summary import MARKET_PHASE_SUMMARY_KEY
from src.schemas.analysis_context_pack import ContextFieldStatus
from src.services.run_diagnostics import build_run_diagnostic_summary


ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY = "analysis_context_pack_overview"
_ALL_STATUSES = tuple(status.value for status in ContextFieldStatus)
_DATA_QUALITY_BLOCK_KEYS = {"quote", "daily_bars", "technical", "news", "fundamentals", "chip"}
_QUALITY_BLOCK_WEIGHTS = {
    "quote": 25,
    "daily_bars": 25,
    "technical": 25,
    "news": 10,
    "fundamentals": 10,
    "chip": 5,
}
_STATUS_SCORES = {
    "available": 100,
    "partial": 75,
    "estimated": 75,
    "not_supported": 70,
    "fallback": 65,
    "stale": 50,
    "missing": 35,
    "fetch_failed": 25,
}
logger = logging.getLogger(__name__)


def render_analysis_context_pack_overview(
    pack: Any,
    *,
    report_language: str = "zh",
) -> Optional[Dict[str, Any]]:
    """Project an AnalysisContextPack into a public, low-sensitivity overview."""
    try:
        payload = analysis_context_pack_to_dict(pack)
        subject = payload.get("subject")
        blocks = payload.get("blocks")
        if not isinstance(subject, Mapping) or not isinstance(blocks, Mapping):
            return None

        labels = get_analysis_context_pack_block_labels(report_language)
        overview_blocks: List[Dict[str, Any]] = []
        counts = {status: 0 for status in _ALL_STATUSES}

        for key in iter_analysis_context_pack_block_keys(blocks):
            block = blocks.get(key)
            if not isinstance(block, Mapping):
                continue
            status = _safe_status(block.get("status"))
            if status is None:
                continue

            counts[status] += 1
            overview_blocks.append(
                {
                    "key": _safe_text(key),
                    "label": labels.get(key, _safe_text(key)),
                    "status": status,
                    "source": _first_non_empty(
                        block.get("source"),
                        _first_item_field(block.get("items"), "source"),
                    ),
                    "warnings": _list_strings(block.get("warnings")),
                    "missing_reasons": _item_missing_reasons(block.get("items")),
                }
            )

        if not overview_blocks:
            return None

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        return {
            "pack_version": _safe_text(payload.get("pack_version")) or "1.0",
            "created_at": _safe_text(payload.get("created_at")) or None,
            "subject": {
                "code": _safe_text(subject.get("code")),
                "stock_name": _safe_text(subject.get("stock_name")) or None,
                "market": _safe_text(subject.get("market")) or None,
            },
            "blocks": overview_blocks,
            "counts": counts,
            "data_quality": _sanitize_data_quality(payload.get("data_quality")),
            "warnings": _list_strings(_nested(payload, "data_quality", "warnings")),
            "metadata": {
                "trigger_source": _safe_text(metadata.get("trigger_source")) or None,
                "news_result_count": _safe_int(metadata.get("news_result_count")),
            },
        }
    except Exception as exc:
        logger.debug("render analysis context pack overview failed: %s", exc, exc_info=True)
        return None


def extract_analysis_context_pack_overview(context_snapshot: Any) -> Optional[Dict[str, Any]]:
    """Extract the persisted public overview from a context snapshot."""
    snapshot = _as_mapping(context_snapshot)
    if not snapshot:
        return None
    overview = snapshot.get(ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY)
    if not isinstance(overview, Mapping):
        return None
    return _sanitize_persisted_overview(overview, snapshot)


def sanitize_context_snapshot_for_api(context_snapshot: Any) -> Any:
    """Return a context snapshot without separately exposed public summary fields."""
    snapshot = _as_mapping(context_snapshot)
    if snapshot is not None:
        sanitized = dict(snapshot)
        sanitized.pop(ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY, None)
        sanitized.pop(MARKET_PHASE_SUMMARY_KEY, None)
        return sanitized
    return context_snapshot


def _as_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def _sanitize_persisted_overview(
    overview: Mapping[str, Any],
    snapshot: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    subject = overview.get("subject")
    blocks = overview.get("blocks")
    if not isinstance(subject, Mapping) or not isinstance(blocks, list):
        return None

    subject_code = _safe_text(subject.get("code"))
    if not subject_code:
        return None

    overview_blocks: List[Dict[str, Any]] = []
    counts = {status: 0 for status in _ALL_STATUSES}
    for block in blocks:
        if not isinstance(block, Mapping):
            return None

        key = _safe_text(block.get("key"))
        status = _safe_status(block.get("status"))
        if not key or status is None:
            return None

        counts[status] += 1
        overview_blocks.append(
            {
                "key": key,
                "label": _safe_text(block.get("label")) or key,
                "status": status,
                "source": _safe_text(block.get("source")) or None,
                "warnings": _list_strings(block.get("warnings")),
                "missing_reasons": _list_strings(block.get("missing_reasons"), limit=3),
            }
        )

    if not overview_blocks:
        return None

    metadata = overview.get("metadata") if isinstance(overview.get("metadata"), Mapping) else {}
    sanitized = {
        "pack_version": _safe_text(overview.get("pack_version")) or "1.0",
        "created_at": _safe_text(overview.get("created_at")) or None,
        "subject": {
            "code": subject_code,
            "stock_name": _safe_text(subject.get("stock_name")) or None,
            "market": _safe_text(subject.get("market")) or None,
        },
        "blocks": overview_blocks,
        "counts": counts,
        "warnings": _list_strings(overview.get("warnings")),
        "metadata": {
            "trigger_source": _safe_text(metadata.get("trigger_source")) or None,
            "news_result_count": _safe_int(metadata.get("news_result_count")),
        },
    }
    if "data_quality" in overview:
        sanitized["data_quality"] = _sanitize_data_quality(overview.get("data_quality"))
    return _reconcile_persisted_overview(sanitized, snapshot or {})


def _reconcile_persisted_overview(
    overview: Dict[str, Any],
    snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    if not snapshot:
        return overview

    summary = build_run_diagnostic_summary(context_snapshot=snapshot, raw_result=None)
    components = summary.get("components") if isinstance(summary, Mapping) else {}
    changed = False
    quote_component = components.get("realtime_quote") if isinstance(components, Mapping) else None
    if isinstance(quote_component, Mapping):
        changed = _apply_quote_component(overview, quote_component) or changed

    news_count = _final_news_count(snapshot, components)
    if news_count and news_count > 0:
        block = _overview_block(overview, "news")
        if block is not None:
            block["status"] = "available"
            block["missing_reasons"] = []
            block["warnings"] = []
            metadata = overview.setdefault("metadata", {})
            metadata["news_result_count"] = news_count
            changed = True

    if _is_tw_us_overview(overview):
        before = len(overview.get("blocks", []))
        overview["blocks"] = [
            block for block in overview.get("blocks", [])
            if not (isinstance(block, Mapping) and block.get("key") == "chip")
        ]
        changed = changed or len(overview.get("blocks", [])) != before

    if changed:
        _refresh_quality(overview)
        _refresh_counts(overview)
    return overview


def _apply_quote_component(
    overview: Dict[str, Any],
    component: Mapping[str, Any],
) -> bool:
    block = _overview_block(overview, "quote")
    if block is None:
        return False
    status = _safe_text(component.get("status"))
    details = component.get("details") if isinstance(component.get("details"), Mapping) else {}
    source = _safe_text(details.get("source_label") or details.get("sourceLabel") or details.get("provider"))
    if status == "ok":
        block["status"] = "available"
        block["source"] = source or block.get("source")
        block["warnings"] = []
        block["missing_reasons"] = []
        return True
    elif status == "degraded":
        block["status"] = "fallback"
        block["source"] = source or "備援資料"
        block["warnings"] = []
        block["missing_reasons"] = []
        return True
    elif status == "failed":
        block["status"] = "missing"
        block["source"] = None
        block["warnings"] = []
        block["missing_reasons"] = ["realtime_quote_missing"]
        return True
    return False


def _final_news_count(
    snapshot: Mapping[str, Any],
    components: Any,
) -> Optional[int]:
    direct = _safe_int(snapshot.get("news_result_count"))
    if direct and direct > 0:
        return direct
    news_search = snapshot.get("news_search") if isinstance(snapshot.get("news_search"), Mapping) else {}
    search_count = _safe_int(news_search.get("result_count"))
    if search_count and search_count > 0:
        return search_count
    news_component = components.get("news") if isinstance(components, Mapping) else None
    details = news_component.get("details") if isinstance(news_component, Mapping) and isinstance(news_component.get("details"), Mapping) else {}
    component_count = _safe_int(details.get("result_count") or details.get("resultCount"))
    return component_count if component_count and component_count > 0 else None


def _overview_block(overview: Mapping[str, Any], key: str) -> Optional[Dict[str, Any]]:
    blocks = overview.get("blocks")
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if isinstance(block, dict) and block.get("key") == key:
            return block
    return None


def _is_tw_us_overview(overview: Mapping[str, Any]) -> bool:
    subject = overview.get("subject")
    if not isinstance(subject, Mapping):
        return False
    market = _safe_text(subject.get("market")).lower()
    if market in {"tw", "us"}:
        return True

    code = _safe_text(subject.get("code")).upper()
    if code.isdigit() and len(code) == 4:
        return True
    return code.isalpha() and 1 <= len(code) <= 6


def _refresh_counts(overview: Dict[str, Any]) -> None:
    counts = {status: 0 for status in _ALL_STATUSES}
    for block in overview.get("blocks", []):
        if not isinstance(block, Mapping):
            continue
        status = _safe_status(block.get("status"))
        if status:
            counts[status] += 1
    overview["counts"] = counts


def _refresh_quality(overview: Dict[str, Any]) -> None:
    data_quality = overview.get("data_quality")
    if not isinstance(data_quality, dict):
        return

    visible_status = {
        block.get("key"): block.get("status")
        for block in overview.get("blocks", [])
        if isinstance(block, Mapping)
    }
    block_scores = {
        key: score
        for key, score in _safe_block_scores(data_quality.get("block_scores")).items()
        if key in visible_status
    }
    for key, status in visible_status.items():
        if key in _DATA_QUALITY_BLOCK_KEYS:
            block_scores[key] = _STATUS_SCORES.get(str(status), 35)

    limitations = []
    for item in _list_strings(data_quality.get("limitations"), limit=5):
        raw_key, _, raw_status = item.partition(":")
        key = raw_key.strip()
        if key in visible_status and str(visible_status[key]) == raw_status.strip():
            limitations.append(item)

    total_weight = 0
    weighted_sum = 0
    for key, weight in _QUALITY_BLOCK_WEIGHTS.items():
        if key not in visible_status:
            continue
        total_weight += weight
        weighted_sum += block_scores.get(key, 35) * weight
    if total_weight:
        overall_score = int(round(weighted_sum / total_weight))
        data_quality["overall_score"] = overall_score
        data_quality["level"] = _quality_level(overall_score)
    data_quality["block_scores"] = block_scores
    data_quality["limitations"] = limitations


def _quality_level(score: int) -> str:
    if score >= 85:
        return "good"
    if score >= 70:
        return "usable"
    if score >= 55:
        return "limited"
    return "poor"


def _sanitize_data_quality(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    return {
        "overall_score": _safe_score(value.get("overall_score")),
        "level": _safe_quality_level(value.get("level")),
        "block_scores": _safe_block_scores(value.get("block_scores")),
        "limitations": _list_strings(value.get("limitations"), limit=5),
    }


def _safe_status(value: Any) -> Optional[str]:
    text = _safe_text(value)
    return text if text in _ALL_STATUSES else None


def _safe_quality_level(value: Any) -> Optional[str]:
    text = _safe_text(value)
    return text if text in {"good", "usable", "limited", "poor"} else None


def _safe_score(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 0 <= value <= 100:
        return value
    return None


def _safe_block_scores(value: Any) -> Dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, int] = {}
    for key, score in value.items():
        text_key = _safe_text(key)
        safe_score = _safe_score(score)
        if text_key in _DATA_QUALITY_BLOCK_KEYS and safe_score is not None:
            result[text_key] = safe_score
    return result


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    lowered = text.lower()
    if any(marker in lowered for marker in SENSITIVE_MARKERS):
        return "[REDACTED]"
    return text


def _list_strings(value: Any, *, limit: int = 5) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _safe_text(item)
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return None


def _first_item_field(items: Any, field: str) -> Optional[str]:
    if not isinstance(items, Mapping):
        return None
    for item in items.values():
        if not isinstance(item, Mapping):
            continue
        value = _safe_text(item.get(field))
        if value:
            return value
    return None


def _item_missing_reasons(items: Any) -> List[str]:
    if not isinstance(items, Mapping):
        return []
    reasons: List[str] = []
    for item in items.values():
        if not isinstance(item, Mapping):
            continue
        reason = _safe_text(item.get("missing_reason"))
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons[:3]


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None

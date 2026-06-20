# -*- coding: utf-8 -*-
"""Lightweight run diagnostic context for one analysis trace.

This module intentionally keeps Phase 1 diagnostics in memory and fail-open.
Persistence can reuse existing analysis context snapshots until a dedicated
diagnostic store is introduced.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CURRENT_CONTEXT: ContextVar[Optional["RunDiagnosticContext"]] = ContextVar(
    "run_diagnostic_context",
    default=None,
)

_SECRET_REDACTIONS = (
    (
        re.compile(r"(?i)\b(authorization)\s*[:=]\s*(?:(?:Bearer|Basic|Token)\s+)?[^\s,&;]+"),
        lambda match: f"{match.group(1)}=<redacted>",
    ),
    (
        re.compile(r"(https?://)([^/\s:@]+):([^@\s/]+)@"),
        r"\1<redacted>:<redacted>@",
    ),
    (
        re.compile(r"https?://[^\s]+?(?:token|key|secret|webhook)[^\s]*", re.IGNORECASE),
        "<redacted-url>",
    ),
    (
        re.compile(
            r"(?i)([\"']?)"
            r"([A-Z0-9_]*?(?:api[_-]?key|access[_-]?token|token|secret|password|passwd|cookie))"
            r"\1\s*:\s*([\"'])([^\"']+)\3"
        ),
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(1)}: {match.group(3)}<redacted>{match.group(3)}",
    ),
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*?(?:api[_-]?key|access[_-]?token|token|secret|password|passwd|cookie))"
            r"\s*=\s*([^\s,&;]+)"
        ),
        lambda match: f"{match.group(1)}=<redacted>",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|passwd|cookie)"
            r"\s*:\s*([^\s,&;]+)"
        ),
        lambda match: f"{match.group(1)}=<redacted>",
    ),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
        "Bearer <redacted>",
    ),
)


def build_trace_id() -> str:
    """Build a compact trace id suitable for logs, API responses, and SSE."""
    return uuid.uuid4().hex


def sanitize_diagnostic_text(value: Any, *, max_length: int = 300) -> Optional[str]:
    """Return a short diagnostic string with obvious credentials redacted."""
    if value is None:
        return None

    text = " ".join(str(value).split())
    if not text:
        return None

    for pattern, replacement in _SECRET_REDACTIONS:
        text = pattern.sub(replacement, text)

    if len(text) > max_length:
        return f"{text[:max_length].rstrip()}..."
    return text


@dataclass
class ProviderRun:
    """One provider attempt in a trace."""

    trace_id: str
    data_type: str
    provider: str
    operation: str
    success: bool
    latency_ms: Optional[int] = None
    error_type: Optional[str] = None
    error_message_sanitized: Optional[str] = None
    fallback_from: Optional[str] = None
    fallback_to: Optional[str] = None
    cache_hit: Optional[bool] = None
    stale_seconds: Optional[int] = None
    record_count: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "data_type": self.data_type,
            "provider": self.provider,
            "operation": self.operation,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "error_message_sanitized": self.error_message_sanitized,
            "fallback_from": self.fallback_from,
            "fallback_to": self.fallback_to,
            "cache_hit": self.cache_hit,
            "stale_seconds": self.stale_seconds,
            "record_count": self.record_count,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class LLMRun:
    """One LLM call result in a trace."""

    trace_id: str
    provider: Optional[str] = None
    model: Optional[str] = None
    call_type: str = "analysis"
    success: bool = True
    tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    fallback_model: Optional[str] = None
    error_type: Optional[str] = None
    error_message_sanitized: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "provider": self.provider,
            "model": self.model,
            "call_type": self.call_type,
            "success": self.success,
            "tokens": self.tokens,
            "duration_ms": self.duration_ms,
            "fallback_model": self.fallback_model,
            "error_type": self.error_type,
            "error_message_sanitized": self.error_message_sanitized,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class NotificationRun:
    """Notification dispatch result in a trace."""

    trace_id: str
    channel: str
    status: str
    success: bool
    attempts: int = 1
    error_message_sanitized: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "channel": self.channel,
            "status": self.status,
            "success": self.success,
            "attempts": self.attempts,
            "error_message_sanitized": self.error_message_sanitized,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class HistoryRun:
    """History persistence result in a trace."""

    trace_id: str
    report_saved: bool
    metadata_saved: Optional[bool] = None
    analysis_history_id: Optional[int] = None
    error_message_sanitized: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "report_saved": self.report_saved,
            "metadata_saved": self.metadata_saved,
            "analysis_history_id": self.analysis_history_id,
            "error_message_sanitized": self.error_message_sanitized,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class RunDiagnosticComponent:
    """User-facing status for one diagnostic component."""

    key: str
    label: str
    status: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }
        return {key: value for key, value in payload.items() if value not in (None, {}, [])}


@dataclass
class RunDiagnosticSummary:
    """User-facing diagnostic summary for one analysis run."""

    status: str
    status_label: str
    reason: str
    trace_id: Optional[str] = None
    task_id: Optional[str] = None
    query_id: Optional[str] = None
    stock_code: Optional[str] = None
    trigger_source: Optional[str] = None
    components: Dict[str, RunDiagnosticComponent] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "query_id": self.query_id,
            "stock_code": self.stock_code,
            "trigger_source": self.trigger_source,
            "status": self.status,
            "status_label": self.status_label,
            "reason": self.reason,
            "components": {
                key: component.to_dict()
                for key, component in self.components.items()
            },
        }
        payload["copy_text"] = format_copyable_diagnostics(payload)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class RunDiagnosticContext:
    """Diagnostic state for one analysis run."""

    trace_id: str
    task_id: Optional[str] = None
    query_id: Optional[str] = None
    stock_code: Optional[str] = None
    trigger_source: Optional[str] = None
    provider_runs: List[ProviderRun] = field(default_factory=list)
    llm_runs: List[LLMRun] = field(default_factory=list)
    notification_runs: List[NotificationRun] = field(default_factory=list)
    history_runs: List[HistoryRun] = field(default_factory=list)

    def record_provider_run(self, provider_run: ProviderRun) -> None:
        self.provider_runs.append(provider_run)

    def record_llm_run(self, llm_run: LLMRun) -> None:
        self.llm_runs.append(llm_run)

    def record_notification_run(self, notification_run: NotificationRun) -> None:
        self.notification_runs.append(notification_run)

    def record_history_run(self, history_run: HistoryRun) -> None:
        self.history_runs.append(history_run)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "query_id": self.query_id,
            "stock_code": self.stock_code,
            "trigger_source": self.trigger_source,
            "provider_runs": [run.to_dict() for run in self.provider_runs],
            "llm_runs": [run.to_dict() for run in self.llm_runs],
            "notification_runs": [run.to_dict() for run in self.notification_runs],
            "history_runs": [run.to_dict() for run in self.history_runs],
        }


def get_current_diagnostic_context() -> Optional[RunDiagnosticContext]:
    return _CURRENT_CONTEXT.get()


def activate_run_diagnostic_context(
    *,
    trace_id: Optional[str] = None,
    task_id: Optional[str] = None,
    query_id: Optional[str] = None,
    stock_code: Optional[str] = None,
    trigger_source: Optional[str] = None,
) -> Token:
    """Activate a diagnostic context and return its reset token."""
    context = RunDiagnosticContext(
        trace_id=trace_id or query_id or task_id or build_trace_id(),
        task_id=task_id,
        query_id=query_id,
        stock_code=stock_code,
        trigger_source=trigger_source,
    )
    return _CURRENT_CONTEXT.set(context)


def reset_run_diagnostic_context(token: Optional[Token]) -> None:
    if token is None:
        return
    try:
        _CURRENT_CONTEXT.reset(token)
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        logger.warning("run diagnostic context reset failed: %s", exc)


def current_diagnostic_snapshot() -> Optional[Dict[str, Any]]:
    context = get_current_diagnostic_context()
    if context is None:
        return None
    try:
        return context.snapshot()
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        logger.warning("run diagnostic snapshot failed: %s", exc)
        return None


def record_provider_run(
    *,
    data_type: str,
    provider: str,
    operation: str,
    success: bool,
    latency_ms: Optional[int] = None,
    error_type: Optional[str] = None,
    error_message: Optional[Any] = None,
    fallback_from: Optional[str] = None,
    fallback_to: Optional[str] = None,
    cache_hit: Optional[bool] = None,
    stale_seconds: Optional[int] = None,
    record_count: Optional[int] = None,
) -> None:
    """Append a provider attempt to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_provider_run(
            ProviderRun(
                trace_id=context.trace_id,
                data_type=data_type,
                provider=provider,
                operation=operation,
                success=success,
                latency_ms=latency_ms,
                error_type=error_type,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
                fallback_from=fallback_from,
                fallback_to=fallback_to,
                cache_hit=cache_hit,
                stale_seconds=stale_seconds,
                record_count=record_count,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        logger.warning("provider diagnostic record failed: %s", exc)


def record_llm_run(
    *,
    success: bool,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    call_type: str = "analysis",
    tokens: Optional[int] = None,
    duration_ms: Optional[int] = None,
    fallback_model: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[Any] = None,
) -> None:
    """Append an LLM call result to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_llm_run(
            LLMRun(
                trace_id=context.trace_id,
                provider=provider,
                model=model,
                call_type=call_type,
                success=success,
                tokens=tokens,
                duration_ms=duration_ms,
                fallback_model=fallback_model,
                error_type=error_type,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        logger.warning("llm diagnostic record failed: %s", exc)


def record_notification_run(
    *,
    channel: str,
    status: str,
    success: bool,
    attempts: int = 1,
    error_message: Optional[Any] = None,
) -> None:
    """Append a notification result to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_notification_run(
            NotificationRun(
                trace_id=context.trace_id,
                channel=channel,
                status=status,
                success=success,
                attempts=attempts,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        logger.warning("notification diagnostic record failed: %s", exc)


def record_history_run(
    *,
    report_saved: bool,
    metadata_saved: Optional[bool] = None,
    analysis_history_id: Optional[int] = None,
    error_message: Optional[Any] = None,
) -> None:
    """Append a history persistence result to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_history_run(
            HistoryRun(
                trace_id=context.trace_id,
                report_saved=report_saved,
                metadata_saved=metadata_saved,
                analysis_history_id=analysis_history_id,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        logger.warning("history diagnostic record failed: %s", exc)


_SUMMARY_STATUS_LABELS = {
    "normal": "正常",
    "degraded": "部分降級",
    "failed": "失敗",
    "unknown": "未知",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _component(
    key: str,
    label: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> RunDiagnosticComponent:
    clean_details = {
        key: value
        for key, value in (details or {}).items()
        if value is not None
    }
    return RunDiagnosticComponent(
        key=key,
        label=label,
        status=status,
        message=message,
        details=clean_details,
    )


def _sanitize_string_list(
    values: Any,
    *,
    max_items: int = 12,
    max_length: int = 160,
) -> List[str]:
    cleaned: List[str] = []
    for value in _as_list(values)[:max_items]:
        text = sanitize_diagnostic_text(value, max_length=max_length)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _sanitize_news_search_details(context_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    raw = _as_dict(context_snapshot.get("news_search"))
    if not raw:
        diagnostics = _as_dict(context_snapshot.get("diagnostics"))
        raw = _as_dict(diagnostics.get("news_search"))
    if not raw:
        return {}

    details: Dict[str, Any] = {
        "enabled": bool(raw.get("enabled")),
        "providers_attempted": _sanitize_string_list(
            raw.get("providers_attempted"),
            max_items=8,
            max_length=80,
        ),
        "query_variants": _sanitize_string_list(
            raw.get("query_variants"),
            max_items=12,
            max_length=180,
        ),
        "fallback_used": bool(raw.get("fallback_used")),
    }
    for key in ("attempt_count", "result_count"):
        value = raw.get(key)
        if isinstance(value, int):
            details[key] = max(0, value)
    final_status = sanitize_diagnostic_text(raw.get("final_status"), max_length=40)
    if final_status:
        details["final_status"] = final_status
    error_types = _sanitize_string_list(raw.get("error_types"), max_items=6, max_length=40)
    if error_types:
        details["error_types"] = error_types
    return {key: value for key, value in details.items() if value not in (None, [], {})}


def _provider_component(
    *,
    key: str,
    label: str,
    data_type: str,
    provider_runs: List[Dict[str, Any]],
) -> RunDiagnosticComponent:
    runs = [
        run for run in provider_runs
        if isinstance(run, dict) and run.get("data_type") == data_type
    ]
    if not runs:
        return _component(key, label, "unknown", f"{label}未記錄診斷資訊")

    successes = [run for run in runs if run.get("success") is True]
    failures = [run for run in runs if run.get("success") is False]
    last_run = runs[-1]
    if successes:
        success_run = successes[-1]
        provider = success_run.get("provider") or "unknown"
        record_count = success_run.get("record_count")
        details = {
            "provider": provider,
            "attempts": len(runs),
            "record_count": record_count,
            "fallback_to": next(
                (run.get("fallback_to") for run in failures if run.get("fallback_to")),
                None,
            ),
        }
        details = {key: value for key, value in details.items() if value is not None}
        if failures:
            return _component(
                key,
                label,
                "degraded",
                f"{label}{provider} 成功，前置資料來源失敗後已繼續",
                details,
            )
        return _component(
            key,
            label,
            "ok",
            f"{label}{provider} 成功",
            details,
        )

    message = (
        last_run.get("error_message_sanitized")
        or last_run.get("error_type")
        or "所有資料來源嘗試失敗"
    )
    return _component(
        key,
        label,
        "failed",
        f"{label}失敗：{message}",
        {
            "attempts": len(runs),
            "provider": last_run.get("provider"),
            "error_type": last_run.get("error_type"),
        },
    )


def _news_component(context_snapshot: Dict[str, Any], raw_result: Dict[str, Any]) -> RunDiagnosticComponent:
    label = "新聞搜尋"
    search_details = _sanitize_news_search_details(context_snapshot)
    if search_details:
        result_count = search_details.get("result_count")
        final_status = str(search_details.get("final_status") or "unknown")
        if final_status == "available" and isinstance(result_count, int) and result_count > 0:
            return _component(
                "news",
                label,
                "ok",
                f"新聞搜尋取得 {result_count} 筆結果",
                search_details,
            )
        if final_status in {"failed", "provider_error", "timeout"}:
            return _component("news", label, "failed", "新聞搜尋失敗", search_details)
        if final_status == "empty" or result_count == 0:
            return _component("news", label, "degraded", "新聞搜尋無結果", search_details)
        return _component("news", label, "unknown", "新聞搜尋狀態未完整記錄", search_details)

    has_retrieval_news = "news_retrieval_content" in context_snapshot
    has_snapshot_news = has_retrieval_news or "news_content" in context_snapshot
    news_result_count = context_snapshot.get("news_result_count")
    if isinstance(news_result_count, int):
        if news_result_count > 0:
            return _component(
                "news",
                label,
                "ok",
                f"新聞檢索返回 {news_result_count} 條結果",
                {"record_count": news_result_count},
            )
        return _component("news", label, "degraded", "新聞搜尋無結果", {"record_count": 0})
    if has_snapshot_news and not has_retrieval_news:
        return _component("news", label, "unknown", "新聞檢索未記錄原始證據，可能未嘗試或未啟用")
    return _component("news", label, "unknown", "新聞搜尋未記錄診斷資訊")


def _llm_component(diagnostics: Dict[str, Any], raw_result: Dict[str, Any]) -> RunDiagnosticComponent:
    label = "LLM"
    runs = [
        run for run in _as_list(diagnostics.get("llm_runs"))
        if isinstance(run, dict)
    ]
    if runs:
        successes = [run for run in runs if run.get("success") is True]
        failures = [run for run in runs if run.get("success") is False]
        last_run = runs[-1]
        if successes:
            success_run = successes[-1]
            model = success_run.get("model") or raw_result.get("model_used") or "unknown"
            status = "degraded" if failures or success_run.get("fallback_model") else "ok"
            message = f"LLM {model} 成功"
            if status == "degraded":
                message = f"LLM {model} 成功，期間發生過失敗或模型切換"
            return _component(
                "llm",
                label,
                status,
                message,
                {
                    "model": model,
                    "tokens": success_run.get("tokens"),
                    "duration_ms": success_run.get("duration_ms"),
                    "fallback_model": success_run.get("fallback_model"),
                },
            )
        return _component(
            "llm",
            label,
            "failed",
            f"LLM 失敗：{last_run.get('error_message_sanitized') or last_run.get('error_type') or '未知錯誤'}",
            {"model": last_run.get("model"), "error_type": last_run.get("error_type")},
        )

    if raw_result:
        if raw_result.get("success") is False:
            return _component(
                "llm",
                label,
                "failed",
                f"LLM 失敗：{sanitize_diagnostic_text(raw_result.get('error_message')) or '未知錯誤'}",
            )
        model = raw_result.get("model_used")
        if model:
            return _component("llm", label, "ok", f"LLM {model} 成功", {"model": model})
        if raw_result.get("analysis_summary"):
            return _component("llm", label, "ok", "LLM 成功，模型未記錄")
    return _component("llm", label, "unknown", "LLM 未記錄診斷資訊")


def _notification_component(diagnostics: Dict[str, Any]) -> RunDiagnosticComponent:
    label = "通知"
    runs = [
        run for run in _as_list(diagnostics.get("notification_runs"))
        if isinstance(run, dict)
    ]
    if not runs:
        return _component("notification", label, "unknown", "通知結果未記錄")

    skipped = [run for run in runs if run.get("status") in {"skipped", "not_configured"}]
    successes = [run for run in runs if run.get("success") is True]
    failures = [run for run in runs if run.get("success") is False and run not in skipped]
    channels = [run.get("channel") for run in runs if run.get("channel")]
    if successes and failures:
        return _component(
            "notification",
            label,
            "degraded",
            "部分通知通道失敗，其餘通道已傳送",
            {"channels": channels, "failed": [run.get("channel") for run in failures]},
        )
    if successes:
        return _component(
            "notification",
            label,
            "ok",
            "通知傳送成功",
            {"channels": channels},
        )
    if skipped and not failures:
        status = "not_configured" if any(run.get("status") == "not_configured" for run in skipped) else "skipped"
        return _component(
            "notification",
            label,
            status,
            "通知未配置或本次跳過",
            {"channels": channels},
        )
    last_failure = failures[-1] if failures else runs[-1]
    return _component(
        "notification",
        label,
        "failed",
        f"通知失敗：{last_failure.get('error_message_sanitized') or last_failure.get('status') or '未知錯誤'}",
        {"channels": channels},
    )


def _history_component(
    diagnostics: Dict[str, Any],
    report_saved: Optional[bool],
) -> RunDiagnosticComponent:
    label = "歷史儲存"
    runs = [
        run for run in _as_list(diagnostics.get("history_runs"))
        if isinstance(run, dict)
    ]
    if runs:
        last_run = runs[-1]
        if last_run.get("report_saved") is True:
            return _component(
                "history",
                label,
                "ok",
                "報告歷史已儲存",
                {"analysis_history_id": last_run.get("analysis_history_id")},
            )
        return _component(
            "history",
            label,
            "failed",
            f"報告歷史儲存失敗：{last_run.get('error_message_sanitized') or '未知錯誤'}",
        )
    if report_saved is True:
        return _component("history", label, "ok", "報告歷史已儲存")
    if report_saved is False:
        return _component("history", label, "failed", "報告歷史儲存失敗")
    return _component("history", label, "unknown", "歷史儲存未記錄診斷資訊")


def build_run_diagnostic_summary(
    *,
    context_snapshot: Optional[Any] = None,
    raw_result: Optional[Any] = None,
    report_saved: Optional[bool] = None,
    query_id: Optional[str] = None,
    stock_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a user-facing diagnostic summary from persisted or in-memory evidence."""
    snapshot = _as_dict(context_snapshot)
    raw = _as_dict(raw_result)
    diagnostics = _as_dict(snapshot.get("diagnostics"))
    provider_runs = [
        run for run in _as_list(diagnostics.get("provider_runs"))
        if isinstance(run, dict)
    ]
    llm_runs = [
        run for run in _as_list(diagnostics.get("llm_runs"))
        if isinstance(run, dict)
    ]

    components = {
        "realtime_quote": _provider_component(
            key="realtime_quote",
            label="實時行情",
            data_type="realtime_quote",
            provider_runs=provider_runs,
        ),
        "daily_data": _provider_component(
            key="daily_data",
            label="日線資料",
            data_type="daily_data",
            provider_runs=provider_runs,
        ),
        "news": _news_component(snapshot, raw),
        "llm": _llm_component(diagnostics, raw),
        "notification": _notification_component(diagnostics),
        "history": _history_component(diagnostics, report_saved),
    }

    has_evidence = bool(snapshot or raw or diagnostics or report_saved is not None)
    has_core_diagnostic_runs = bool(provider_runs or llm_runs)
    if not has_evidence or not diagnostics:
        status = "unknown"
    elif components["llm"].status == "failed" or components["history"].status == "failed":
        status = "failed"
    elif any(component.status in {"failed", "degraded"} for component in components.values()):
        status = "degraded"
    elif all(component.status == "unknown" for component in components.values()):
        status = "unknown"
    elif not has_core_diagnostic_runs:
        status = "unknown"
    else:
        status = "normal"

    if status == "unknown":
        reason = "舊報告或診斷證據不足，無法判斷本次執行狀態"
    else:
        reason = next(
            (
                component.message
                for component in components.values()
                if component.status == "failed"
            ),
            next(
                (
                    component.message
                    for component in components.values()
                    if component.status == "degraded"
                ),
                _SUMMARY_STATUS_LABELS[status],
            ),
        )

    trace_id = diagnostics.get("trace_id") or snapshot.get("trace_id") or raw.get("trace_id")
    resolved_query_id = query_id or diagnostics.get("query_id") or snapshot.get("query_id") or raw.get("query_id")
    resolved_stock_code = (
        stock_code
        or diagnostics.get("stock_code")
        or snapshot.get("stock_code")
        or raw.get("code")
        or raw.get("stock_code")
    )

    return RunDiagnosticSummary(
        trace_id=trace_id,
        task_id=diagnostics.get("task_id"),
        query_id=resolved_query_id,
        stock_code=resolved_stock_code,
        trigger_source=diagnostics.get("trigger_source") or snapshot.get("trigger_source"),
        status=status,
        status_label=_SUMMARY_STATUS_LABELS[status],
        reason=reason,
        components=components,
    ).to_dict()


def format_copyable_diagnostics(summary: Dict[str, Any]) -> str:
    """Format a sanitized plain-text diagnostic payload for issue reports."""
    components = _as_dict(summary.get("components"))

    def _component_line(key: str) -> str:
        component = _as_dict(components.get(key))
        message = sanitize_diagnostic_text(component.get("message"), max_length=160) or "unknown"
        return f"{key}: {component.get('status', 'unknown')} - {message}"

    def _news_search_lines() -> List[str]:
        news_component = _as_dict(components.get("news"))
        details = _as_dict(news_component.get("details"))
        if not details.get("final_status") and "attempt_count" not in details:
            return []
        providers = ",".join(
            _sanitize_string_list(details.get("providers_attempted"), max_items=8, max_length=80)
        )
        queries = _sanitize_string_list(details.get("query_variants"), max_items=12, max_length=180)
        status = sanitize_diagnostic_text(details.get("final_status"), max_length=40) or "unknown"
        attempts = details.get("attempt_count", "unknown")
        results = details.get("result_count", "unknown")
        fallback_used = "true" if details.get("fallback_used") else "false"
        lines = [
            (
                "news_search: "
                f"status={status}; providers={providers or 'unknown'}; "
                f"attempts={attempts}; results={results}; fallback_used={fallback_used}"
            )
        ]
        if queries:
            lines.append(f"news_queries: {' | '.join(queries)}")
        return lines

    lines = [
        f"trace_id: {summary.get('trace_id') or 'unknown'}",
        f"query_id: {summary.get('query_id') or 'unknown'}",
        f"stock_code: {summary.get('stock_code') or 'unknown'}",
        f"trigger_source: {summary.get('trigger_source') or 'unknown'}",
        f"data_status: {summary.get('status', 'unknown')}",
        _component_line("realtime_quote"),
        _component_line("daily_data"),
        _component_line("news"),
        _component_line("llm"),
        _component_line("notification"),
        _component_line("history"),
        f"reason: {sanitize_diagnostic_text(summary.get('reason'), max_length=160) or 'unknown'}",
    ]
    news_line_index = 8
    for offset, line in enumerate(_news_search_lines()):
        lines.insert(news_line_index + offset, line)
    return "\n".join(lines)

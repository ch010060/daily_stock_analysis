# -*- coding: utf-8 -*-
"""
===================================
Chat Job Manager — 對話分析 Job 生命週期管理
===================================

職責：
1. 將分析 Job 的執行生命週期與 SSE HTTP 連接生命週期分離
2. 支援多個 SSE 觀察者連接到同一個執行中的 Job
3. 提供 Job 狀態查詢，讓前端可在斷線後重新連線

設計原則：
- 純記憶體管理（Job 結果透過 conversation_manager 持久化到 DB）
- 執行緒安全
- TTL 清理避免記憶體洩漏
- 不引入外部 Worker/Queue 基礎設施
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio import Queue as AsyncQueue

logger = logging.getLogger(__name__)


class ChatJobStatus(str, Enum):
    """Chat job status enumeration."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ChatJobInfo:
    """Public job information returned to API consumers."""
    session_id: str
    status: ChatJobStatus
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    step_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "step_count": self.step_count,
        }


@dataclass
class _ChatJob:
    """Internal job tracking state."""
    session_id: str
    status: ChatJobStatus = ChatJobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    step_count: int = 0

    # Observer queues — each attached SSE connection gets its own asyncio.Queue
    observer_queues: List[Any] = field(default_factory=list)

    def to_info(self) -> ChatJobInfo:
        return ChatJobInfo(
            session_id=self.session_id,
            status=self.status,
            created_at=datetime.fromtimestamp(self.created_at).isoformat(),
            started_at=datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            finished_at=datetime.fromtimestamp(self.finished_at).isoformat() if self.finished_at else None,
            error=self.error,
            step_count=self.step_count,
        )


class ChatJobManager:
    """
    對話分析 Job 管理器（單例）

    追蹤每個 session 的分析 Job 生命週期：
    - 一個 session 同一時間最多一個 active job（防止重複執行）
    - 多個 SSE 觀察者可以連接到同一個 running job
    - TTL 清理超過 30 分鐘未更新的 completed/failed job
    """

    _instance: Optional['ChatJobManager'] = None
    _instance_lock = threading.Lock()

    _TTL_SECONDS = 1800  # 30 minutes

    def __new__(cls) -> 'ChatJobManager':
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._jobs: Dict[str, _ChatJob] = {}
        self._lock = threading.RLock()
        self._initialized = True
        logger.info("[ChatJobManager] 初始化完成")

    # ========== Job 建立與查詢 ==========

    def create_job(self, session_id: str) -> _ChatJob:
        """
        為指定 session 建立一個新 Job。

        如果已有 active job，返回現有 job。
        如果已有 completed/failed job，建立新 job（覆蓋舊的）。
        """
        with self._lock:
            self._evict_expired_locked()

            existing = self._jobs.get(session_id)
            if existing and existing.status in (ChatJobStatus.RUNNING, ChatJobStatus.QUEUED):
                return existing

            job = _ChatJob(session_id=session_id)
            self._jobs[session_id] = job
            logger.debug("[ChatJobManager] 建立 Job: session=%s", session_id)
            return job

    def get_job(self, session_id: str) -> Optional[_ChatJob]:
        """獲取指定 session 的 job，如果已過期則返回 None。"""
        with self._lock:
            self._evict_expired_locked()
            return self._jobs.get(session_id)

    def get_job_info(self, session_id: str) -> Optional[ChatJobInfo]:
        """獲取指定 session 的 job 公開資訊。"""
        job = self.get_job(session_id)
        return job.to_info() if job else None

    def start_job(self, session_id: str) -> bool:
        """
        將 job 標記為 running。
        Returns True 如果 job 存在且狀態為 QUEUED。
        """
        with self._lock:
            job = self._jobs.get(session_id)
            if not job or job.status != ChatJobStatus.QUEUED:
                return False
            job.status = ChatJobStatus.RUNNING
            job.started_at = time.time()
            logger.debug("[ChatJobManager] Job 開始: session=%s", session_id)
            return True

    def complete_job(self, session_id: str, step_count: int = 0) -> bool:
        """將 job 標記為 completed。"""
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return False
            job.status = ChatJobStatus.COMPLETED
            job.finished_at = time.time()
            job.step_count = step_count
            logger.debug("[ChatJobManager] Job 完成: session=%s", session_id)
            return True

    def fail_job(self, session_id: str, error: str) -> bool:
        """將 job 標記為 failed。"""
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return False
            job.status = ChatJobStatus.FAILED
            job.finished_at = time.time()
            job.error = error
            logger.debug("[ChatJobManager] Job 失敗: session=%s error=%s", session_id, error[:80])
            return True

    # ========== 觀察者管理 ==========

    def attach_observer(self, session_id: str, queue: Any) -> bool:
        """
        將 asyncio.Queue 附加為指定 session 的 observer。

        Returns:
            True if an existing QUEUED or RUNNING job was found and this
            observer is attached to it.  The caller should NOT start a new
            job.
            False if no active job exists (the job is COMPLETED, FAILED, or
            does not exist at all).  The caller SHOULD create and start a
            new job.
        """
        with self._lock:
            self._evict_expired_locked()
            job = self._jobs.get(session_id)
            if not job:
                # No job exists — caller must create one.
                return False
            if job.status in (ChatJobStatus.COMPLETED, ChatJobStatus.FAILED):
                return False
            # Existing QUEUED or RUNNING job — attach as observer.
            if queue not in job.observer_queues:
                job.observer_queues.append(queue)
                logger.debug(
                    "[ChatJobManager] 附加觀察者: session=%s queues=%d",
                    session_id,
                    len(job.observer_queues),
                )
            return True

    def detach_observer(self, session_id: str, queue: Any) -> None:
        """移除指定 session 的 observer queue。"""
        with self._lock:
            job = self._jobs.get(session_id)
            if job and queue in job.observer_queues:
                job.observer_queues.remove(queue)
                logger.debug(
                    "[ChatJobManager] 移除觀察者: session=%s queues=%d",
                    session_id,
                    len(job.observer_queues),
                )

    def set_main_loop(self, loop: Any) -> None:
        """Set the main event loop reference for thread-safe broadcasting."""
        self._main_loop = loop

    def _get_main_loop(self) -> Optional[Any]:
        """Get the main event loop, defaulting to any detectable loop."""
        if getattr(self, '_main_loop', None) is not None:
            return self._main_loop
        try:
            import asyncio
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def broadcast_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        向指定 session 的所有觀察者廣播事件。

        使用 call_soon_threadsafe 確保跨執行緒安全。
        需要在執行緒池中被呼叫（由 executor thread 觸發）。
        """
        with self._lock:
            job = self._jobs.get(session_id)
            if not job:
                return
            queues = list(job.observer_queues)

        if not queues:
            return

        loop = self._get_main_loop()
        if loop is None:
            return

        for q in queues:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except (RuntimeError, Exception) as exc:
                logger.debug("[ChatJobManager] 廣播失敗: %s", exc)

    # ========== 清理 ==========

    def _evict_expired_locked(self) -> None:
        """刪除超過 TTL 的 completed/failed job。"""
        now = time.time()
        expired = [
            sid for sid, job in list(self._jobs.items())
            if job.status in (ChatJobStatus.COMPLETED, ChatJobStatus.FAILED)
            and job.finished_at
            and (now - job.finished_at) > self._TTL_SECONDS
        ]
        for sid in expired:
            del self._jobs[sid]
        if expired:
            logger.debug("[ChatJobManager] 清理過期 Job: %d", len(expired))

    def clear_session(self, session_id: str) -> None:
        """清除指定 session 的 job。"""
        with self._lock:
            self._jobs.pop(session_id, None)

    def clear_all(self) -> None:
        """清除所有 jobs（主要用於測試）。"""
        with self._lock:
            self._jobs.clear()


# ========== 便捷函式 ==========

def get_chat_job_manager() -> ChatJobManager:
    """獲取 ChatJobManager 單例。"""
    return ChatJobManager()

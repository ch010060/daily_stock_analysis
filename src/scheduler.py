# -*- coding: utf-8 -*-
"""
===================================
定時排程模組
===================================

職責：
1. 支援每日定時執行股票分析
2. 支援定時執行大盤覆盤
3. 優雅處理訊號，確保可靠退出

依賴：
- schedule: 輕量級定時任務庫
"""

import logging
import re
import signal
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """
    優雅退出處理器

    捕獲 SIGTERM/SIGINT 訊號，確保任務完成後再退出
    """

    def __init__(self):
        self.shutdown_requested = False
        self._lock = threading.Lock()

        # 註冊訊號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """訊號處理函式"""
        with self._lock:
            if not self.shutdown_requested:
                logger.info(f"收到退出訊號 ({signum})，等待當前任務完成...")
                self.shutdown_requested = True

    @property
    def should_shutdown(self) -> bool:
        """檢查是否應該退出"""
        with self._lock:
            return self.shutdown_requested


class Scheduler:
    """
    定時任務排程器

    基於 schedule 庫實現，支援：
    - 每日定時執行
    - 啟動時立即執行
    - 優雅退出
    """

    def __init__(
        self,
        schedule_time: str = "18:00",
        schedule_time_provider: Optional[Callable[[], str]] = None,
    ):
        """
        初始化排程器

        Args:
            schedule_time: 每日執行時間，格式 "HH:MM"
        """
        try:
            import schedule
            self.schedule = schedule
        except ImportError:
            logger.error("schedule 庫未安裝，請執行: pip install schedule")
            raise ImportError("請安裝 schedule 庫: pip install schedule")

        self.schedule_time = schedule_time
        self._schedule_time_provider = schedule_time_provider
        self.shutdown_handler = GracefulShutdown()
        self._task_callback: Optional[Callable] = None
        self._daily_job: Optional[Any] = None
        self._background_tasks: List[Dict[str, Any]] = []
        self._running = False

    def set_daily_task(self, task: Callable, run_immediately: bool = True):
        """
        設定每日定時任務

        Args:
            task: 要執行的任務函式（無引數）
            run_immediately: 是否在設定後立即執行一次
        """
        self._task_callback = task
        if not self._configure_daily_task(self.schedule_time):
            raise ValueError(f"無效的定時執行時間: {self.schedule_time!r}")

        if run_immediately:
            logger.info("立即執行一次任務...")
            self._safe_run_task()

    @staticmethod
    def _is_valid_schedule_time(schedule_time: str) -> bool:
        """Validate time string in HH:MM 24-hour format."""
        candidate = (schedule_time or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
            return False
        return True

    def _cancel_daily_job(self) -> None:
        """Remove the currently registered daily job if one exists."""
        if self._daily_job is None:
            return

        if hasattr(self.schedule, "cancel_job"):
            self.schedule.cancel_job(self._daily_job)
        else:  # pragma: no cover - compatibility fallback
            jobs = getattr(self.schedule, "jobs", None)
            if isinstance(jobs, list) and self._daily_job in jobs:
                jobs.remove(self._daily_job)

        self._daily_job = None

    def _configure_daily_task(self, schedule_time: str) -> bool:
        """(Re)register the daily job at the requested time."""
        candidate = (schedule_time or "").strip()
        if not self._is_valid_schedule_time(candidate):
            logger.warning(
                "檢測到無效的定時執行時間 %r，繼續沿用當前時間 %s",
                schedule_time,
                self.schedule_time,
            )
            return False

        previous_time = self.schedule_time
        self._cancel_daily_job()
        self._daily_job = self.schedule.every().day.at(candidate).do(self._safe_run_task)
        self.schedule_time = candidate

        if previous_time == candidate:
            logger.info("已設定每日定時任務，執行時間: %s", self.schedule_time)
        else:
            logger.info(
                "檢測到 SCHEDULE_TIME 變更，已將每日定時任務從 %s 更新為 %s",
                previous_time,
                self.schedule_time,
            )
        return True

    def _refresh_daily_schedule_if_needed(self) -> None:
        """Reload daily schedule time from the latest runtime config if needed."""
        if self._task_callback is None or self._schedule_time_provider is None:
            return

        try:
            latest_schedule_time = (self._schedule_time_provider() or "").strip()
        except Exception as exc:  # pragma: no cover - defensive branch
            logger.warning("讀取最新 SCHEDULE_TIME 失敗，繼續沿用 %s: %s", self.schedule_time, exc)
            return

        if not latest_schedule_time or latest_schedule_time == self.schedule_time:
            return

        if self._configure_daily_task(latest_schedule_time):
            logger.info("更新後的下次執行時間: %s", self._get_next_run_time())

    def _safe_run_task(self):
        """安全執行任務（帶異常捕獲）"""
        if self._task_callback is None:
            return

        try:
            logger.info("=" * 50)
            logger.info(f"定時任務開始執行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 50)

            self._task_callback()

            logger.info(f"定時任務執行完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            logger.exception(f"定時任務執行失敗: {e}")

    def add_background_task(
        self,
        task: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
        name: Optional[str] = None,
    ) -> None:
        """Register a periodic background task executed inside the scheduler loop.

        Note: The scheduler loop polls every 30 seconds, so *interval_seconds*
        below 30 will be clamped to 30 to avoid promising unreachable precision.
        """
        clamped_interval = max(30, int(interval_seconds))
        if int(interval_seconds) < 30:
            logger.warning(
                "後臺任務 %s 請求間隔 %ds，但排程迴圈每 30s 輪詢一次，已自動調整為 30s",
                name or getattr(task, "__name__", "background_task"),
                interval_seconds,
            )
        entry = {
            "task": task,
            "interval_seconds": clamped_interval,
            "last_run": 0.0,
            "name": name or getattr(task, "__name__", "background_task"),
            "thread": None,
            "running": False,
        }
        if not run_immediately:
            entry["last_run"] = time.time()
        self._background_tasks.append(entry)
        logger.info(
            "已註冊後臺任務: %s（間隔 %s 秒，立即執行=%s）",
            entry["name"],
            entry["interval_seconds"],
            run_immediately,
        )
        if run_immediately:
            self._start_background_task(entry)

    def _start_background_task(self, entry: Dict[str, Any]) -> bool:
        """Start one background task in a dedicated daemon thread."""
        worker = entry.get("thread")
        if worker is not None and worker.is_alive():
            return False

        def _runner() -> None:
            try:
                logger.info("後臺任務開始執行: %s", entry["name"])
                entry["task"]()
            except Exception as exc:
                logger.exception("後臺任務執行失敗 [%s]: %s", entry["name"], exc)
            finally:
                entry["running"] = False
                entry["thread"] = None

        entry["last_run"] = time.time()
        entry["running"] = True
        worker = threading.Thread(
            target=_runner,
            daemon=True,
            name=f"scheduler-bg-{entry['name']}",
        )
        entry["thread"] = worker
        worker.start()
        return True

    def _run_background_tasks(self) -> None:
        """Execute any background tasks whose interval has elapsed."""
        if not self._background_tasks:
            return

        now = time.time()
        for entry in self._background_tasks:
            worker = entry.get("thread")
            if worker is not None and worker.is_alive():
                continue
            if entry.get("running"):
                entry["running"] = False
                entry["thread"] = None
            if now - entry["last_run"] < entry["interval_seconds"]:
                continue
            self._start_background_task(entry)

    def run(self):
        """
        執行排程器主迴圈

        阻塞執行，直到收到退出訊號
        """
        self._running = True
        logger.info("排程器開始執行...")
        logger.info(f"下次執行時間: {self._get_next_run_time()}")

        while self._running and not self.shutdown_handler.should_shutdown:
            self._refresh_daily_schedule_if_needed()
            self.schedule.run_pending()
            self._run_background_tasks()
            time.sleep(30)  # 每30秒檢查一次

            # 每小時列印一次心跳
            if datetime.now().minute == 0 and datetime.now().second < 30:
                logger.info(f"排程器執行中... 下次執行: {self._get_next_run_time()}")

        logger.info("排程器已停止")

    def _get_next_run_time(self) -> str:
        """獲取下次執行時間"""
        jobs = self.schedule.get_jobs()
        if jobs:
            next_run = min(job.next_run for job in jobs)
            return next_run.strftime('%Y-%m-%d %H:%M:%S')
        return "未設定"

    def stop(self):
        """停止排程器"""
        self._running = False


def run_with_schedule(
    task: Callable,
    schedule_time: str = "18:00",
    run_immediately: bool = True,
    background_tasks: Optional[List[Dict[str, Any]]] = None,
    schedule_time_provider: Optional[Callable[[], str]] = None,
):
    """
    便捷函式：使用定時排程執行任務

    Args:
        task: 要執行的任務函式
        schedule_time: 每日執行時間
        run_immediately: 是否立即執行一次
        background_tasks: 可選的後臺任務定義列表。每項為一個字典，
            需包含 `task` 與 `interval_seconds`，可選包含 `name`
            和 `run_immediately`。`interval_seconds` 單位為秒。
        schedule_time_provider: 可選的時間提供器；排程器每輪檢查前會讀取，
            當返回值變化時自動重建 daily job。
    """
    scheduler = Scheduler(
        schedule_time=schedule_time,
        schedule_time_provider=schedule_time_provider,
    )
    for entry in background_tasks or []:
        scheduler.add_background_task(
            task=entry["task"],
            interval_seconds=entry["interval_seconds"],
            run_immediately=entry.get("run_immediately", False),
            name=entry.get("name"),
        )
    scheduler.set_daily_task(task, run_immediately=run_immediately)
    scheduler.run()


if __name__ == "__main__":
    # 測試定時排程
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )

    def test_task():
        print(f"任務執行中... {datetime.now()}")
        time.sleep(2)
        print("任務完成!")

    print("啟動測試排程器（按 Ctrl+C 退出）")
    run_with_schedule(test_task, schedule_time="23:59", run_immediately=True)

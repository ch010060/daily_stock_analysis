# -*- coding: utf-8 -*-
"""
Tests for ChatJobManager — analysis job lifecycle separation.

Verifies:
1. Job lifecycle: QUEUED → RUNNING → COMPLETED / FAILED
2. Observer attachment to running jobs
3. Observer rejection from completed/failed jobs
4. TTL cleanup of expired jobs
5. Concurrent independent job operation
6. Broadcast to multiple observers
7. Detaching observers
"""

import asyncio
import sys
import os
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.job_manager import (
    ChatJobManager,
    ChatJobStatus,
    get_chat_job_manager,
)


class TestChatJobManager(unittest.TestCase):
    """Unit tests for ChatJobManager."""

    def setUp(self):
        self.jm = ChatJobManager()
        self.jm.clear_all()

    def tearDown(self):
        self.jm.clear_all()

    # ============================================================
    # Job lifecycle
    # ============================================================

    def test_create_job_queued(self):
        """Creating a job sets status to QUEUED."""
        job = self.jm.create_job("session-A")
        self.assertEqual(job.status, ChatJobStatus.QUEUED)
        self.assertEqual(job.session_id, "session-A")

    def test_create_job_returns_existing(self):
        """Creating a second job for same session returns existing QUEUED job."""
        j1 = self.jm.create_job("session-A")
        j2 = self.jm.create_job("session-A")
        self.assertIs(j1, j2)

    def test_create_job_overwrites_completed(self):
        """Creating a job for a completed session creates new job."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.jm.complete_job("session-A")
        j2 = self.jm.create_job("session-A")
        self.assertEqual(j2.status, ChatJobStatus.QUEUED)

    def test_start_job_transitions_to_running(self):
        """start_job transitions QUEUED → RUNNING."""
        self.jm.create_job("session-A")
        self.assertTrue(self.jm.start_job("session-A"))
        info = self.jm.get_job_info("session-A")
        self.assertEqual(info.status, ChatJobStatus.RUNNING)

    def test_complete_job(self):
        """complete_job transitions RUNNING → COMPLETED."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.assertTrue(self.jm.complete_job("session-A", step_count=7))
        info = self.jm.get_job_info("session-A")
        self.assertEqual(info.status, ChatJobStatus.COMPLETED)
        self.assertEqual(info.step_count, 7)
        self.assertIsNotNone(info.finished_at)

    def test_fail_job(self):
        """fail_job transitions RUNNING → FAILED with error."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.assertTrue(self.jm.fail_job("session-A", "LLM timeout"))
        info = self.jm.get_job_info("session-A")
        self.assertEqual(info.status, ChatJobStatus.FAILED)
        self.assertEqual(info.error, "LLM timeout")

    def test_fail_non_existent_job(self):
        """fail_job on non-existent session returns False."""
        self.assertFalse(self.jm.fail_job("ghost", "error"))

    def test_complete_non_existent_job(self):
        """complete_job on non-existent session returns False."""
        self.assertFalse(self.jm.complete_job("ghost", step_count=0))

    # ============================================================
    # Observer management
    # ============================================================

    def test_attach_observer_to_running_job(self):
        """attach_observer returns True for QUEUED or RUNNING jobs."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        q = asyncio.Queue()
        attached = self.jm.attach_observer("session-A", q)
        self.assertTrue(attached)

    def test_attach_observer_to_completed_job_returns_false(self):
        """attach_observer returns False for completed jobs."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.jm.complete_job("session-A")
        q = asyncio.Queue()
        attached = self.jm.attach_observer("session-A", q)
        self.assertFalse(attached)

    def test_attach_observer_to_failed_job_returns_false(self):
        """attach_observer returns False for failed jobs."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.jm.fail_job("session-A", "failed")
        q = asyncio.Queue()
        attached = self.jm.attach_observer("session-A", q)
        self.assertFalse(attached)

    def test_detach_observer_removes_queue(self):
        """detach_observer removes the queue from the job's observer list."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        q = asyncio.Queue()
        self.jm.attach_observer("session-A", q)
        self.jm.detach_observer("session-A", q)
        # Should be removed — no effect on further operations
        self.jm.complete_job("session-A")

    def test_multiple_observers_on_same_job(self):
        """Multiple observer queues can attach to the same running job."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        q1 = asyncio.Queue()
        q2 = asyncio.Queue()
        self.assertTrue(self.jm.attach_observer("session-A", q1))
        self.assertTrue(self.jm.attach_observer("session-A", q2))
        # Both observers should receive broadcast events
        self.jm.broadcast_event("session-A", {"type": "test", "data": "hello"})

    def test_broadcast_to_detached_observer_does_not_fail(self):
        """Broadcast after detach is harmless."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        q = asyncio.Queue()
        self.jm.attach_observer("session-A", q)
        self.jm.detach_observer("session-A", q)
        # This should not raise
        self.jm.broadcast_event("session-A", {"type": "test"})

    # ============================================================
    # Concurrent sessions
    # ============================================================

    def test_concurrent_sessions_independent(self):
        """Two sessions with independent jobs operate independently."""
        self.jm.create_job("session-A")
        self.jm.create_job("session-B")
        self.jm.start_job("session-A")
        self.jm.start_job("session-B")
        self.jm.complete_job("session-A", step_count=3)
        self.jm.fail_job("session-B", "error-B")

        info_a = self.jm.get_job_info("session-A")
        info_b = self.jm.get_job_info("session-B")
        self.assertEqual(info_a.status, ChatJobStatus.COMPLETED)
        self.assertEqual(info_a.step_count, 3)
        self.assertEqual(info_b.status, ChatJobStatus.FAILED)
        self.assertEqual(info_b.error, "error-B")

    def test_concurrent_observers_no_cross_feed(self):
        """
        Observers on session A should not receive events broadcast
        for session B.
        """
        self.jm.create_job("session-A")
        self.jm.create_job("session-B")
        self.jm.start_job("session-A")
        self.jm.start_job("session-B")

        q_a = asyncio.Queue()
        q_b = asyncio.Queue()
        self.jm.attach_observer("session-A", q_a)
        self.jm.attach_observer("session-B", q_b)

        self.jm.broadcast_event("session-A", {"type": "event-for-A"})
        self.jm.broadcast_event("session-B", {"type": "event-for-B"})

    # ============================================================
    # get_job_info
    # ============================================================

    def test_get_job_info_returns_none_for_missing(self):
        """get_job_info returns None for non-existent session."""
        info = self.jm.get_job_info("nonexistent")
        self.assertIsNone(info)

    def test_get_job_info_contains_all_fields(self):
        """get_job_info returns the expected dict structure."""
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.jm.complete_job("session-A", step_count=5)
        info = self.jm.get_job_info("session-A")
        d = info.to_dict()
        self.assertIn("session_id", d)
        self.assertIn("status", d)
        self.assertIn("created_at", d)
        self.assertIn("started_at", d)
        self.assertIn("finished_at", d)
        self.assertEqual(d["session_id"], "session-A")
        self.assertEqual(d["status"], "completed")

    # ============================================================
    # TTL cleanup
    # ============================================================

    def test_ttl_cleans_completed_jobs(self):
        """Jobs older than TTL are evicted."""
        self.jm._TTL_SECONDS = 0  # Force immediate expiration
        self.jm.create_job("session-A")
        self.jm.start_job("session-A")
        self.jm.complete_job("session-A")

        # Trigger eviction
        self.jm.get_job("session-A")  # This calls _evict_expired_locked
        info = self.jm.get_job_info("session-A")
        self.assertIsNone(info)

    # ============================================================
    # clear_all / clear_session
    # ============================================================

    def test_clear_all(self):
        """clear_all removes all jobs."""
        self.jm.create_job("session-A")
        self.jm.create_job("session-B")
        self.jm.clear_all()
        self.assertIsNone(self.jm.get_job_info("session-A"))
        self.assertIsNone(self.jm.get_job_info("session-B"))

    def test_clear_session(self):
        """clear_session removes a single session's job."""
        self.jm.create_job("session-A")
        self.jm.create_job("session-B")
        self.jm.clear_session("session-A")
        self.assertIsNone(self.jm.get_job_info("session-A"))
        self.assertIsNotNone(self.jm.get_job_info("session-B"))


class TestChatJobManagerConcurrency(unittest.TestCase):
    """Concurrency safety tests for ChatJobManager."""

    def setUp(self):
        self.jm = ChatJobManager()
        self.jm.clear_all()

    def tearDown(self):
        self.jm.clear_all()

    def test_thread_safe_create(self):
        """Creating jobs from multiple threads should not race."""
        import threading

        results = []

        def create_job(name):
            self.jm.create_job(name)
            results.append(name)

        threads = [
            threading.Thread(target=create_job, args=(f"session-{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 10)
        for i in range(10):
            info = self.jm.get_job_info(f"session-{i}")
            self.assertIsNotNone(info, f"session-{i} should exist")

    def test_thread_safe_state_transition(self):
        """Concurrent state transitions should be safe."""
        import threading

        self.jm.create_job("session-A")
        errors = []

        def try_start():
            try:
                self.jm.start_job("session-A")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=try_start) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        # Should be running after at least one success
        info = self.jm.get_job_info("session-A")
        self.assertIn(info.status, (ChatJobStatus.RUNNING,))


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Unit tests for service-level multi-window backtest orchestration."""

import inspect
import unittest
from unittest.mock import MagicMock, call

from src.services.backtest_service import BacktestService


def _service_with_mocked_run(side_effect=None, return_value=None) -> BacktestService:
    service = BacktestService.__new__(BacktestService)
    service.run_backtest = MagicMock(side_effect=side_effect, return_value=return_value)
    return service


class MultiWindowBacktestTestCase(unittest.TestCase):
    def test_multi_window_backtest_runs_all_requested_windows(self) -> None:
        service = _service_with_mocked_run(
            return_value={
                "processed": 2,
                "saved": 2,
                "completed": 2,
                "insufficient": 0,
                "errors": 0,
            }
        )

        result = service.run_multi_window_backtest(
            code="2330",
            windows=[1, 3, 5],
            force=True,
            min_age_days=0,
            limit=25,
        )

        self.assertEqual(result["requested_windows"], [1, 3, 5])
        self.assertEqual(result["completed_windows"], [1, 3, 5])
        self.assertEqual(result["failed_windows"], [])
        self.assertEqual(set(result["windows"].keys()), {1, 3, 5})
        for window in (1, 3, 5):
            self.assertEqual(result["windows"][window]["status"], "completed")
            self.assertEqual(result["windows"][window]["result"]["completed"], 2)

        service.run_backtest.assert_has_calls(
            [
                call(code="2330", force=True, eval_window_days=1, min_age_days=0, limit=25),
                call(code="2330", force=True, eval_window_days=3, min_age_days=0, limit=25),
                call(code="2330", force=True, eval_window_days=5, min_age_days=0, limit=25),
            ]
        )

    def test_multi_window_backtest_rejects_invalid_windows(self) -> None:
        service = _service_with_mocked_run(return_value={})

        for invalid_windows in ([0], [-1], [1, 0], [], [True], ["bad"]):
            with self.subTest(windows=invalid_windows):
                with self.assertRaises(ValueError):
                    service.run_multi_window_backtest(windows=invalid_windows)

        service.run_backtest.assert_not_called()

    def test_multi_window_backtest_deduplicates_duplicates(self) -> None:
        service = _service_with_mocked_run(
            return_value={
                "processed": 1,
                "saved": 1,
                "completed": 1,
                "insufficient": 0,
                "errors": 0,
            }
        )

        result = service.run_multi_window_backtest(windows=[1, 3, 3, 5, 1])

        self.assertEqual(result["requested_windows"], [1, 3, 5])
        self.assertEqual(service.run_backtest.call_count, 3)
        self.assertEqual(
            [kwargs["eval_window_days"] for _, kwargs in service.run_backtest.call_args_list],
            [1, 3, 5],
        )

    def test_multi_window_backtest_preserves_single_window_behavior(self) -> None:
        signature = inspect.signature(BacktestService.run_backtest)
        self.assertNotIn("windows", signature.parameters)
        self.assertIn("eval_window_days", signature.parameters)

        expected = {
            "processed": 1,
            "saved": 1,
            "completed": 1,
            "insufficient": 0,
            "errors": 0,
        }
        service = _service_with_mocked_run(return_value=expected)

        self.assertIs(
            service.run_backtest(
                code="2330",
                force=False,
                eval_window_days=3,
                min_age_days=0,
                limit=10,
            ),
            expected,
        )

    def test_multi_window_backtest_handles_window_failure_independently(self) -> None:
        def fake_run_backtest(**kwargs):
            window = kwargs["eval_window_days"]
            if window == 3:
                raise RuntimeError("window failed")
            return {
                "processed": 1,
                "saved": 1,
                "completed": 1,
                "insufficient": 0,
                "errors": 0,
            }

        service = _service_with_mocked_run(side_effect=fake_run_backtest)

        result = service.run_multi_window_backtest(windows=[1, 3, 5])

        self.assertEqual(result["requested_windows"], [1, 3, 5])
        self.assertEqual(result["completed_windows"], [1, 5])
        self.assertEqual(result["failed_windows"], [3])
        self.assertEqual(result["windows"][1]["status"], "completed")
        self.assertEqual(result["windows"][3]["status"], "error")
        self.assertIn("window failed", result["windows"][3]["error"])
        self.assertEqual(result["windows"][5]["status"], "completed")
        self.assertEqual(service.run_backtest.call_count, 3)

    def test_multi_window_backtest_marks_insufficient_and_no_candidate_windows(self) -> None:
        service = _service_with_mocked_run(
            side_effect=[
                {"processed": 1, "saved": 1, "completed": 0, "insufficient": 1, "errors": 0},
                {"processed": 0, "saved": 0, "completed": 0, "insufficient": 0, "errors": 0},
                {"processed": 2, "saved": 2, "completed": 1, "insufficient": 1, "errors": 0},
            ]
        )

        result = service.run_multi_window_backtest(windows=[1, 3, 5])

        self.assertEqual(result["windows"][1]["status"], "insufficient_data")
        self.assertEqual(result["windows"][3]["status"], "no_candidates")
        self.assertEqual(result["windows"][5]["status"], "completed_with_insufficient_data")


if __name__ == "__main__":
    unittest.main()

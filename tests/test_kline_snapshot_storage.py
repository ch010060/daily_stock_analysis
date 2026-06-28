# -*- coding: utf-8 -*-
"""Storage tests for report-bound K-line snapshots."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from src.config import Config
from src.storage import AnalysisHistory, DatabaseManager


class KlineSnapshotStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_kline_snapshot.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        self._temp_dir.cleanup()

    def _history_id(self, code: str = "MSFT") -> int:
        with self.db.get_session() as session:
            row = AnalysisHistory(code=code, name=code, report_type="full", raw_result='{"instrument_type":"stock"}')
            session.add(row)
            session.commit()
            return int(row.id)

    def _payload(self, history_id: int, range_value: str = "1d", gap: str | None = None):
        return {
            "history_id": history_id,
            "symbol": "MSFT",
            "market": "us",
            "instrument_type": "stock",
            "range": range_value,
            "granularity": "intraday" if range_value in {"1d", "5d"} else "daily",
            "interval": "5m" if range_value == "1d" else "15m" if range_value == "5d" else "1d",
            "currency": "USD",
            "timezone": "America/New_York",
            "source": "yfinance" if range_value in {"1d", "5d"} else "YfinanceFetcher",
            "source_type": "data_gap" if gap else "provider",
            "source_chain": ["yfinance"],
            "as_of": "2026-06-26T09:30:00-04:00",
            "is_cached": False,
            "rows": [],
            "candles": [] if gap else [{
                "timestamp": "2026-06-26T09:30:00-04:00",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 1000,
            }],
            "current_price": 100.5,
            "support_level": None,
            "resistance_level": None,
            "data_gap_reason": gap,
        }

    def test_save_and_load_intraday_and_daily_snapshots(self):
        history_id = self._history_id()
        for range_value in ("1d", "5d", "3m"):
            self.assertEqual(self.db.upsert_analysis_kline_snapshot(self._payload(history_id, range_value)), 1)
            loaded = self.db.get_analysis_kline_snapshot(history_id, range_value)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["history_id"], history_id)
            self.assertEqual(loaded["range"], range_value)

    def test_gap_snapshot_roundtrips(self):
        history_id = self._history_id()
        self.db.upsert_analysis_kline_snapshot(self._payload(history_id, "1d", "provider_empty_response"))
        loaded = self.db.get_analysis_kline_snapshot(history_id, "1d")
        self.assertEqual(loaded["candles"], [])
        self.assertEqual(loaded["data_gap_reason"], "provider_empty_response")

    def test_upsert_replaces_same_history_and_range(self):
        history_id = self._history_id()
        self.db.upsert_analysis_kline_snapshot(self._payload(history_id, "1d"))
        replacement = self._payload(history_id, "1d")
        replacement["candles"][0]["close"] = 222
        self.db.upsert_analysis_kline_snapshot(replacement)
        loaded = self.db.get_analysis_kline_snapshot(history_id, "1d")
        self.assertEqual(loaded["candles"][0]["close"], 222)

    def test_different_history_ids_do_not_cross_contaminate(self):
        first = self._history_id("MSFT")
        second = self._history_id("SPY")
        self.db.upsert_analysis_kline_snapshot(self._payload(first, "1d"))
        self.assertIsNone(self.db.get_analysis_kline_snapshot(second, "1d"))

    def test_save_analysis_history_calls_snapshot_persistence_and_survives_failure(self):
        class Result:
            code = "MSFT"
            name = "Microsoft"
            sentiment_score = 50
            operation_advice = "觀望"
            trend_prediction = "中性"
            analysis_summary = "summary"

            def to_dict(self):
                return {"instrument_type": "stock"}

        with patch("src.services.kline_snapshot.persist_report_kline_snapshots", return_value=6) as persist:
            self.assertEqual(self.db.save_analysis_history(Result(), "q1", "full", None), 1)
        persist.assert_called_once()

        with patch("src.services.kline_snapshot.persist_report_kline_snapshots", side_effect=RuntimeError("boom")):
            self.assertEqual(self.db.save_analysis_history(Result(), "q2", "full", None), 1)


if __name__ == "__main__":
    unittest.main()

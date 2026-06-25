# -*- coding: utf-8 -*-
"""Regression tests for effective trading date resolution."""

import json
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from src.core import trading_calendar


class _FakeCalendar:
    def __init__(
        self,
        sessions,
        close_hour: int,
        tz_name: str,
        open_time: time = time(9, 30),
        break_start: Optional[time] = None,
        break_end: Optional[time] = None,
    ):
        self._sessions = sorted(sessions)
        self._close_hour = close_hour
        self._tz_name = tz_name
        self._open_time = open_time
        self._break_start = break_start
        self._break_end = break_end

    def is_session(self, check_date: date) -> bool:
        return check_date in self._sessions

    def date_to_session(self, check_date: date, direction: str = "previous") -> pd.Timestamp:
        if direction == "previous":
            candidates = [d for d in self._sessions if d <= check_date]
        elif direction == "next":
            candidates = [d for d in self._sessions if d >= check_date]
        else:
            raise ValueError(f"unsupported direction: {direction}")

        if not candidates:
            raise ValueError(f"no session for {check_date} ({direction})")
        return pd.Timestamp(candidates[-1] if direction == "previous" else candidates[0])

    def previous_session(self, session: pd.Timestamp) -> pd.Timestamp:
        session_date = session.date()
        index = self._sessions.index(session_date)
        if index == 0:
            raise ValueError("no previous session")
        return pd.Timestamp(self._sessions[index - 1])

    def session_open(self, session: pd.Timestamp) -> pd.Timestamp:
        local_open = datetime.combine(
            session.date(),
            self._open_time,
            tzinfo=ZoneInfo(self._tz_name),
        )
        return pd.Timestamp(local_open).tz_convert("UTC")

    def session_break_start(self, session: pd.Timestamp) -> pd.Timestamp:
        if self._break_start is None:
            return pd.NaT
        local_break_start = datetime.combine(
            session.date(),
            self._break_start,
            tzinfo=ZoneInfo(self._tz_name),
        )
        return pd.Timestamp(local_break_start).tz_convert("UTC")

    def session_break_end(self, session: pd.Timestamp) -> pd.Timestamp:
        if self._break_end is None:
            return pd.NaT
        local_break_end = datetime.combine(
            session.date(),
            self._break_end,
            tzinfo=ZoneInfo(self._tz_name),
        )
        return pd.Timestamp(local_break_end).tz_convert("UTC")

    def session_has_break(self, session: pd.Timestamp) -> bool:
        return self._break_start is not None and self._break_end is not None

    def session_close(self, session: pd.Timestamp) -> pd.Timestamp:
        local_close = datetime.combine(
            session.date(),
            time(self._close_hour, 0),
            tzinfo=ZoneInfo(self._tz_name),
        )
        return pd.Timestamp(local_close).tz_convert("UTC")


def _calendar_namespace(fake_calendar: _FakeCalendar) -> SimpleNamespace:
    return SimpleNamespace(get_calendar=lambda _ex: fake_calendar)


class _InvalidOpenCalendar(_FakeCalendar):
    def session_open(self, session: pd.Timestamp):
        return object()


class _BreakProbeFailureCalendar(_FakeCalendar):
    def session_has_break(self, session: pd.Timestamp) -> bool:
        raise RuntimeError("break metadata failed")


class _NaiveTimestampCalendar(_FakeCalendar):
    def session_open(self, session: pd.Timestamp) -> pd.Timestamp:
        return pd.Timestamp(datetime.combine(session.date(), self._open_time))

    def session_close(self, session: pd.Timestamp) -> pd.Timestamp:
        return pd.Timestamp(datetime.combine(session.date(), time(self._close_hour, 0)))


class EffectiveTradingDateTestCase(unittest.TestCase):
    def test_weekend_returns_previous_session(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
        )
        current_time = datetime(2026, 3, 28, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: fake_calendar),
            create=True,
        ):
            result = trading_calendar.get_effective_trading_date("tw", current_time=current_time)

        self.assertEqual(result, date(2026, 3, 27))

    def test_holiday_returns_previous_session(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2025, 12, 31), date(2026, 1, 5)],
            close_hour=15,
            tz_name="Asia/Taipei",
        )
        current_time = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: fake_calendar),
            create=True,
        ):
            result = trading_calendar.get_effective_trading_date("tw", current_time=current_time)

        self.assertEqual(result, date(2025, 12, 31))

    def test_intraday_returns_previous_completed_session(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=16,
            tz_name="America/New_York",
        )
        current_time = datetime(
            2026,
            3,
            27,
            15,
            59,
            tzinfo=ZoneInfo("America/New_York"),
        )

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: fake_calendar),
            create=True,
        ):
            result = trading_calendar.get_effective_trading_date("us", current_time=current_time)

        self.assertEqual(result, date(2026, 3, 26))

    def test_after_close_returns_current_session(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=16,
            tz_name="America/New_York",
        )
        current_time = datetime(
            2026,
            3,
            27,
            16,
            1,
            tzinfo=ZoneInfo("America/New_York"),
        )

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: fake_calendar),
            create=True,
        ):
            result = trading_calendar.get_effective_trading_date("us", current_time=current_time)

        self.assertEqual(result, date(2026, 3, 27))

    def test_market_timezone_controls_cross_timezone_resolution(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 25), date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=16,
            tz_name="America/New_York",
        )
        current_time = datetime(2026, 3, 27, 1, 0, tzinfo=timezone.utc)

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: fake_calendar),
            create=True,
        ):
            result = trading_calendar.get_effective_trading_date("us", current_time=current_time)

        self.assertEqual(result, date(2026, 3, 26))

    def test_calendar_error_falls_back_to_market_local_date(self):
        current_time = datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc)

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: (_ for _ in ()).throw(RuntimeError("boom"))),
            create=True,
        ):
            result = trading_calendar.get_effective_trading_date("tw", current_time=current_time)

        self.assertEqual(result, date(2026, 3, 28))


class InferMarketPhaseTestCase(unittest.TestCase):
    """Tests for the Issue #1386 P0 market phase baseline."""

    def _infer_with_calendar(
        self,
        market: str,
        current_time: datetime,
        fake_calendar: _FakeCalendar,
    ) -> trading_calendar.MarketPhase:
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            _calendar_namespace(fake_calendar),
            create=True,
        ):
            return trading_calendar.infer_market_phase(market, current_time=current_time)

    def test_tw_phase_boundaries_include_lunch_and_closing_window(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
            break_start=time(11, 30),
            break_end=time(13, 0),
        )

        cases = (
            (datetime(2026, 3, 27, 9, 29, tzinfo=ZoneInfo("Asia/Taipei")), trading_calendar.MarketPhase.PREMARKET),
            (datetime(2026, 3, 27, 9, 30, tzinfo=ZoneInfo("Asia/Taipei")), trading_calendar.MarketPhase.INTRADAY),
            (datetime(2026, 3, 27, 11, 29, tzinfo=ZoneInfo("Asia/Taipei")), trading_calendar.MarketPhase.INTRADAY),
            (
                datetime(2026, 3, 27, 11, 30, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.LUNCH_BREAK,
            ),
            (
                datetime(2026, 3, 27, 12, 59, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.LUNCH_BREAK,
            ),
            (datetime(2026, 3, 27, 13, 0, tzinfo=ZoneInfo("Asia/Taipei")), trading_calendar.MarketPhase.INTRADAY),
            (datetime(2026, 3, 27, 14, 54, tzinfo=ZoneInfo("Asia/Taipei")), trading_calendar.MarketPhase.INTRADAY),
            (
                datetime(2026, 3, 27, 14, 55, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.CLOSING_AUCTION,
            ),
            (
                datetime(2026, 3, 27, 15, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.POSTMARKET,
            ),
            (
                datetime(2026, 3, 27, 15, 1, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.POSTMARKET,
            ),
        )

        for current_time, expected in cases:
            with self.subTest(current_time=current_time):
                self.assertEqual(self._infer_with_calendar("tw", current_time, fake_calendar), expected)

    def test_tw_non_trading_day_returns_non_trading(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            break_start=time(11, 30),
            break_end=time(13, 0),
        )
        current_time = datetime(2026, 3, 28, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        result = self._infer_with_calendar("tw", current_time, fake_calendar)

        self.assertEqual(result, trading_calendar.MarketPhase.NON_TRADING)

    def test_tw_phase_boundaries_with_alternate_lunch_break_and_five_minute_closing_window(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=16,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
            break_start=time(12, 0),
            break_end=time(13, 0),
        )

        cases = (
            (
                datetime(2026, 3, 27, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.LUNCH_BREAK,
            ),
            (
                datetime(2026, 3, 27, 13, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.INTRADAY,
            ),
            (
                datetime(2026, 3, 27, 15, 54, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.INTRADAY,
            ),
            (
                datetime(2026, 3, 27, 15, 55, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.CLOSING_AUCTION,
            ),
            (
                datetime(2026, 3, 27, 16, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                trading_calendar.MarketPhase.POSTMARKET,
            ),
        )

        for current_time, expected in cases:
            with self.subTest(current_time=current_time):
                self.assertEqual(self._infer_with_calendar("tw", current_time, fake_calendar), expected)

    def test_us_phase_boundaries_skip_nat_lunch_break(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=16,
            tz_name="America/New_York",
            open_time=time(9, 30),
            break_start=None,
            break_end=None,
        )

        cases = (
            (
                datetime(2026, 3, 27, 9, 29, tzinfo=ZoneInfo("America/New_York")),
                trading_calendar.MarketPhase.PREMARKET,
            ),
            (
                datetime(2026, 3, 27, 9, 30, tzinfo=ZoneInfo("America/New_York")),
                trading_calendar.MarketPhase.INTRADAY,
            ),
            (
                datetime(2026, 3, 27, 12, 0, tzinfo=ZoneInfo("America/New_York")),
                trading_calendar.MarketPhase.INTRADAY,
            ),
            (
                datetime(2026, 3, 27, 15, 54, tzinfo=ZoneInfo("America/New_York")),
                trading_calendar.MarketPhase.INTRADAY,
            ),
            (
                datetime(2026, 3, 27, 15, 55, tzinfo=ZoneInfo("America/New_York")),
                trading_calendar.MarketPhase.CLOSING_AUCTION,
            ),
            (
                datetime(2026, 3, 27, 16, 0, tzinfo=ZoneInfo("America/New_York")),
                trading_calendar.MarketPhase.POSTMARKET,
            ),
        )

        for current_time, expected in cases:
            with self.subTest(current_time=current_time):
                self.assertEqual(self._infer_with_calendar("us", current_time, fake_calendar), expected)

    def test_unknown_market_and_calendar_failures_return_unknown(self):
        current_time = datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        self.assertEqual(
            trading_calendar.infer_market_phase(None, current_time=current_time),
            trading_calendar.MarketPhase.UNKNOWN,
        )
        self.assertEqual(
            trading_calendar.infer_market_phase("", current_time=current_time),
            trading_calendar.MarketPhase.UNKNOWN,
        )
        self.assertEqual(
            trading_calendar.infer_market_phase("invalid", current_time=current_time),
            trading_calendar.MarketPhase.UNKNOWN,
        )
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", False):
            self.assertEqual(
                trading_calendar.infer_market_phase("tw", current_time=current_time),
                trading_calendar.MarketPhase.UNKNOWN,
            )
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: (_ for _ in ()).throw(RuntimeError("boom"))),
            create=True,
        ):
            self.assertEqual(
                trading_calendar.infer_market_phase("tw", current_time=current_time),
                trading_calendar.MarketPhase.UNKNOWN,
            )

    def test_invalid_session_open_returns_unknown(self):
        fake_calendar = _InvalidOpenCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
        )
        current_time = datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        result = self._infer_with_calendar("tw", current_time, fake_calendar)

        self.assertEqual(result, trading_calendar.MarketPhase.UNKNOWN)

    def test_break_probe_failure_returns_unknown(self):
        fake_calendar = _BreakProbeFailureCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            break_start=time(11, 30),
            break_end=time(13, 0),
        )
        current_time = datetime(2026, 3, 27, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        result = self._infer_with_calendar("tw", current_time, fake_calendar)

        self.assertEqual(result, trading_calendar.MarketPhase.UNKNOWN)

    def test_naive_current_time_is_interpreted_as_market_local_time(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
            break_start=time(11, 30),
            break_end=time(13, 0),
        )

        result = self._infer_with_calendar("tw", datetime(2026, 3, 27, 9, 29), fake_calendar)

        self.assertEqual(result, trading_calendar.MarketPhase.PREMARKET)

    def test_naive_calendar_timestamps_are_interpreted_as_market_local_time(self):
        fake_calendar = _NaiveTimestampCalendar(
            sessions=[date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
        )
        current_time = datetime(2026, 3, 27, 9, 30, tzinfo=ZoneInfo("Asia/Taipei"))

        result = self._infer_with_calendar("tw", current_time, fake_calendar)

        self.assertEqual(result, trading_calendar.MarketPhase.INTRADAY)


class MarketPhaseContextTestCase(unittest.TestCase):
    """Tests for the Issue #1386 P1a runtime market phase context."""

    def _build_with_calendar(
        self,
        market: str,
        current_time: datetime,
        fake_calendar: _FakeCalendar,
    ) -> trading_calendar.MarketPhaseContext:
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            _calendar_namespace(fake_calendar),
            create=True,
        ):
            return trading_calendar.build_market_phase_context(
                market=market,
                current_time=current_time,
                trigger_source="web",
                analysis_intent="auto",
            )

    def test_context_to_dict_is_json_safe_for_intraday(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
            break_start=time(11, 30),
            break_end=time(13, 0),
        )
        ctx = self._build_with_calendar(
            "tw",
            datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            fake_calendar,
        )

        payload = ctx.to_dict()
        encoded = json.loads(json.dumps(payload, ensure_ascii=False))

        self.assertEqual(encoded["market"], "tw")
        self.assertEqual(encoded["phase"], "intraday")
        self.assertEqual(encoded["market_local_time"], "2026-03-27T10:00:00+08:00")
        self.assertEqual(encoded["session_date"], "2026-03-27")
        self.assertEqual(encoded["effective_daily_bar_date"], "2026-03-26")
        self.assertEqual(encoded["is_trading_day"], True)
        self.assertEqual(encoded["is_market_open_now"], True)
        self.assertEqual(encoded["is_partial_bar"], True)
        self.assertIsNone(encoded["minutes_to_open"])
        self.assertEqual(encoded["minutes_to_close"], 300)
        self.assertEqual(encoded["trigger_source"], "web")
        self.assertEqual(encoded["analysis_intent"], "auto")
        self.assertEqual(encoded["warnings"], [])

    def test_context_derived_flags_for_regular_session_phases(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
            break_start=time(11, 30),
            break_end=time(13, 0),
        )
        cases = (
            (
                datetime(2026, 3, 27, 9, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                "premarket",
                True,
                False,
                False,
                30,
                None,
                date(2026, 3, 26),
            ),
            (
                datetime(2026, 3, 27, 11, 45, tzinfo=ZoneInfo("Asia/Taipei")),
                "lunch_break",
                True,
                False,
                True,
                None,
                195,
                date(2026, 3, 26),
            ),
            (
                datetime(2026, 3, 27, 14, 58, tzinfo=ZoneInfo("Asia/Taipei")),
                "closing_auction",
                True,
                True,
                True,
                None,
                2,
                date(2026, 3, 26),
            ),
            (
                datetime(2026, 3, 27, 15, 1, tzinfo=ZoneInfo("Asia/Taipei")),
                "postmarket",
                True,
                False,
                False,
                None,
                None,
                date(2026, 3, 27),
            ),
            (
                datetime(2026, 3, 28, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                "non_trading",
                False,
                False,
                False,
                None,
                None,
                date(2026, 3, 27),
            ),
        )

        for (
            current_time,
            phase,
            is_trading_day,
            is_market_open_now,
            is_partial_bar,
            minutes_to_open,
            minutes_to_close,
            effective_date,
        ) in cases:
            with self.subTest(phase=phase):
                ctx = self._build_with_calendar("tw", current_time, fake_calendar)
                payload = ctx.to_dict()
                self.assertEqual(payload["phase"], phase)
                self.assertEqual(payload["is_trading_day"], is_trading_day)
                self.assertEqual(payload["is_market_open_now"], is_market_open_now)
                self.assertEqual(payload["is_partial_bar"], is_partial_bar)
                self.assertEqual(payload["minutes_to_open"], minutes_to_open)
                self.assertEqual(payload["minutes_to_close"], minutes_to_close)
                self.assertEqual(
                    payload["effective_daily_bar_date"],
                    effective_date.isoformat(),
                )

    def test_manual_analysis_phase_overrides_non_trading_day_without_rewriting_calendar_fields(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
            break_start=time(11, 30),
            break_end=time(13, 0),
        )

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            _calendar_namespace(fake_calendar),
            create=True,
        ):
            ctx = trading_calendar.build_market_phase_context(
                market="tw",
                current_time=datetime(2026, 3, 28, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                trigger_source="api",
                analysis_phase="intraday",
            )

        payload = ctx.to_dict()
        self.assertEqual(payload["phase"], "intraday")
        self.assertEqual(payload["analysis_intent"], "intraday")
        self.assertEqual(payload["market_local_time"], "2026-03-28T10:00:00+08:00")
        self.assertEqual(payload["effective_daily_bar_date"], "2026-03-27")
        self.assertTrue(payload["is_trading_day"])
        self.assertTrue(payload["is_market_open_now"])
        self.assertTrue(payload["is_partial_bar"])
        self.assertIsNone(payload["minutes_to_open"])
        self.assertIsNone(payload["minutes_to_close"])

    def test_legacy_analysis_intent_alias_can_override_phase(self):
        fake_calendar = _FakeCalendar(
            sessions=[date(2026, 3, 26), date(2026, 3, 27)],
            close_hour=15,
            tz_name="Asia/Taipei",
            open_time=time(9, 30),
        )

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            _calendar_namespace(fake_calendar),
            create=True,
        ):
            ctx = trading_calendar.build_market_phase_context(
                market="tw",
                current_time=datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                analysis_intent="postmarket",
            )

        self.assertEqual(ctx.phase, trading_calendar.MarketPhase.POSTMARKET)
        self.assertEqual(ctx.analysis_intent, "postmarket")

    def test_invalid_manual_analysis_phase_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "invalid analysis_phase"):
            trading_calendar.build_market_phase_context(
                market="tw",
                current_time=datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                analysis_phase="lunch_break",
            )

    def test_unknown_market_uses_null_tristate_flags_and_warning_code(self):
        ctx = trading_calendar.build_market_phase_context(
            market=None,
            current_time=datetime(2026, 3, 27, 10, 0),
        )
        payload = json.loads(json.dumps(ctx.to_dict()))

        self.assertEqual(payload["phase"], "unknown")
        self.assertIn("unknown_market", payload["warnings"])
        self.assertIsNone(payload["is_trading_day"])
        self.assertIsNone(payload["is_market_open_now"])
        self.assertIsNone(payload["is_partial_bar"])
        self.assertIsNone(payload["minutes_to_open"])
        self.assertIsNone(payload["minutes_to_close"])

    def test_calendar_unavailable_warning_code(self):
        current_time = datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", False):
            ctx = trading_calendar.build_market_phase_context(
                market="tw",
                current_time=current_time,
            )

        self.assertEqual(ctx.phase, trading_calendar.MarketPhase.UNKNOWN)
        self.assertIn("calendar_unavailable", ctx.warnings)

    def test_calendar_error_warning_code(self):
        current_time = datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: (_ for _ in ()).throw(RuntimeError("boom"))),
            create=True,
        ):
            ctx = trading_calendar.build_market_phase_context(
                market="tw",
                current_time=current_time,
            )

        self.assertEqual(ctx.phase, trading_calendar.MarketPhase.UNKNOWN)
        self.assertIn("calendar_error", ctx.warnings)


class ComputeEffectiveRegionTestCase(unittest.TestCase):
    """Regression tests for compute_effective_region subset logic."""

    def test_both_all_open_returns_comma_joined_three(self):
        result = trading_calendar.compute_effective_region("both", {"cn", "hk", "us"})
        self.assertEqual(result, "cn,hk,us")

    def test_both_cn_us_open_returns_comma_joined_two(self):
        result = trading_calendar.compute_effective_region("both", {"cn", "us"})
        self.assertEqual(result, "cn,us")

    def test_both_cn_hk_open_returns_comma_joined_two(self):
        result = trading_calendar.compute_effective_region("both", {"cn", "hk"})
        self.assertEqual(result, "cn,hk")

    def test_both_single_market_open_returns_single(self):
        result = trading_calendar.compute_effective_region("both", {"us"})
        self.assertEqual(result, "us")

    def test_both_no_market_open_returns_empty(self):
        result = trading_calendar.compute_effective_region("both", set())
        self.assertEqual(result, "")

    def test_single_region_open(self):
        self.assertEqual(trading_calendar.compute_effective_region("hk", {"cn", "hk", "us"}), "hk")

    def test_single_region_closed(self):
        self.assertEqual(trading_calendar.compute_effective_region("hk", {"cn", "us"}), "")

    def test_invalid_region_no_longer_silently_defaults_to_cn(self):
        """Phase 15.9R: an unrecognized region must not silently masquerade as cn."""
        result = trading_calendar.compute_effective_region("invalid", {"cn"})
        self.assertEqual(result, "")

    def test_legacy_cn_region_open_still_returns_cn(self):
        """Legacy single-region cn/hk/both callers keep their exact prior behavior."""
        self.assertEqual(trading_calendar.compute_effective_region("cn", {"cn", "us"}), "cn")

    def test_legacy_cn_region_closed_still_returns_empty(self):
        self.assertEqual(trading_calendar.compute_effective_region("cn", {"hk", "us"}), "")

    def test_route_b_all_open_returns_comma_joined_tw_us(self):
        result = trading_calendar.compute_effective_region("all", {"tw", "us"})
        self.assertEqual(result, "tw,us")

    def test_route_b_all_only_tw_open_returns_tw(self):
        result = trading_calendar.compute_effective_region("all", {"tw"})
        self.assertEqual(result, "tw")

    def test_route_b_all_no_market_open_returns_empty(self):
        result = trading_calendar.compute_effective_region("all", set())
        self.assertEqual(result, "")

    def test_route_b_all_ignores_legacy_cn_hk_even_if_open(self):
        """all is Route B (tw/us) scope; cn/hk being open must not leak in."""
        result = trading_calendar.compute_effective_region("all", {"cn", "hk", "tw"})
        self.assertEqual(result, "tw")

    def test_route_b_tw_region_open(self):
        self.assertEqual(trading_calendar.compute_effective_region("tw", {"tw", "us"}), "tw")

    def test_route_b_tw_region_closed(self):
        self.assertEqual(trading_calendar.compute_effective_region("tw", {"us"}), "")


class TaiwanMarketCalendarTestCase(unittest.TestCase):
    """Phase 15.9R: tw must have its own exchange/timezone, not silently fold into cn."""

    def test_market_timezone_has_tw_entry(self):
        self.assertIn("tw", trading_calendar.MARKET_TIMEZONE)
        self.assertEqual(trading_calendar.MARKET_TIMEZONE["tw"], "Asia/Taipei")

    def test_market_exchange_has_tw_entry(self):
        self.assertIn("tw", trading_calendar.MARKET_EXCHANGE)

    def test_is_market_open_recognizes_tw_trading_day(self):
        if not trading_calendar._XCALS_AVAILABLE:
            self.skipTest("exchange-calendars not installed")
        self.assertTrue(trading_calendar.is_market_open("tw", date(2026, 6, 23)))

    def test_is_market_open_recognizes_tw_non_trading_day(self):
        if not trading_calendar._XCALS_AVAILABLE:
            self.skipTest("exchange-calendars not installed")
        self.assertFalse(trading_calendar.is_market_open("tw", date(2026, 6, 21)))


class GetMarketForStockTestCase(unittest.TestCase):
    """Phase 19B.2A: TW codes must route to 'tw'; cn/hk are no longer recognized."""

    def test_tw_bare_numeric_code_returns_tw(self):
        self.assertEqual(trading_calendar.get_market_for_stock("2330"), "tw")

    def test_tw_etf_alpha_suffix_code_returns_tw(self):
        self.assertEqual(trading_calendar.get_market_for_stock("00981A"), "tw")

    def test_tw_four_digit_etf_code_returns_tw(self):
        self.assertEqual(trading_calendar.get_market_for_stock("0050"), "tw")

    def test_us_ticker_returns_us(self):
        self.assertEqual(trading_calendar.get_market_for_stock("AAPL"), "us")

    def test_cn_six_digit_code_no_longer_recognized(self):
        # Previously classified as "cn"; now falls through to None (fail-open).
        self.assertIsNone(trading_calendar.get_market_for_stock("600519"))

    def test_cn_six_digit_codes_with_leading_zero_not_misrouted_to_tw(self):
        # '00'-leading 6-digit CN codes share digit shape with TW ETFs
        # (e.g. 006208); only a registry hit should classify as 'tw'.
        self.assertIsNone(trading_calendar.get_market_for_stock("300750"))
        self.assertIsNone(trading_calendar.get_market_for_stock("002594"))
        self.assertIsNone(trading_calendar.get_market_for_stock("000001"))

    def test_tw_six_digit_etf_code_returns_tw_via_symbol_universe(self):
        # 006208 (Fubon TW50 ETF) is a real TW symbol-universe entry; digit
        # shape alone collides with CN A-share codes, so this must resolve
        # via the registry lookup, not the regex fast path.
        self.assertEqual(trading_calendar.get_market_for_stock("006208"), "tw")

    def test_tw_six_digit_etf_code_with_tw_suffix_returns_tw(self):
        from data_provider.base import normalize_stock_code

        self.assertEqual(
            trading_calendar.get_market_for_stock(normalize_stock_code("006208.TW")),
            "tw",
        )

    def test_tw_six_digit_etf_code_with_tw_prefix_returns_tw(self):
        from data_provider.base import normalize_stock_code

        self.assertEqual(
            trading_calendar.get_market_for_stock(normalize_stock_code("TW:006208")),
            "tw",
        )

    def test_hk_prefixed_code_no_longer_recognized(self):
        self.assertIsNone(trading_calendar.get_market_for_stock("HK:0700"))
        self.assertIsNone(trading_calendar.get_market_for_stock("hk00700"))

    def test_empty_and_invalid_input_returns_none(self):
        self.assertIsNone(trading_calendar.get_market_for_stock(""))
        self.assertIsNone(trading_calendar.get_market_for_stock(None))

    def test_market_exchange_no_longer_has_cn_or_hk_entries(self):
        self.assertNotIn("cn", trading_calendar.MARKET_EXCHANGE)
        self.assertNotIn("hk", trading_calendar.MARKET_EXCHANGE)

    def test_market_timezone_no_longer_has_cn_or_hk_entries(self):
        self.assertNotIn("cn", trading_calendar.MARKET_TIMEZONE)
        self.assertNotIn("hk", trading_calendar.MARKET_TIMEZONE)

    def test_closing_auction_window_no_longer_has_cn_or_hk_entries(self):
        self.assertNotIn("cn", trading_calendar._CLOSING_AUCTION_WINDOW_MINUTES)
        self.assertNotIn("hk", trading_calendar._CLOSING_AUCTION_WINDOW_MINUTES)


if __name__ == "__main__":
    unittest.main()

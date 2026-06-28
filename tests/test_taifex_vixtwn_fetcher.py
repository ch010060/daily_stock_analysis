# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from src.services.taifex_vixtwn_fetcher import fetch_latest_vixtwn, parse_vixtwn_daily_txt


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(status, text):
    return SimpleNamespace(status_code=status, text=text)


class TestTaifexVixtwnParser(unittest.TestCase):
    def test_parses_latest_valid_row(self) -> None:
        quote = parse_vixtwn_daily_txt(
            "bad header\n"
            "20260625 13450000 40.39 40.31\n"
            "20260626 13450000 44.27 44.01\n"
        )
        self.assertEqual(quote.as_of, "2026-06-26")
        self.assertEqual(quote.value, 44.27)
        self.assertIsNone(quote.data_gap_reason)

    def test_ignores_malformed_and_non_numeric_rows(self) -> None:
        quote = parse_vixtwn_daily_txt(
            "20260624 13450000 nope\n"
            "-------- -------------------\n"
            "20260625 13450000 40.39\n"
        )
        self.assertEqual(quote.as_of, "2026-06-25")
        self.assertEqual(quote.value, 40.39)

    def test_empty_text_returns_gap(self) -> None:
        quote = parse_vixtwn_daily_txt("")
        self.assertIsNone(quote.value)
        self.assertEqual(quote.data_gap_reason, "taifex_vixtwn_no_valid_rows")


class TestFetchLatestVixtwn(unittest.TestCase):
    def test_current_month_success(self) -> None:
        session = _Session([_response(200, "20260626 13450000 44.27 44.01\n")])
        quote = fetch_latest_vixtwn(session=session, today=date(2026, 6, 28))
        self.assertEqual(quote.as_of, "2026-06-26")
        self.assertEqual(quote.value, 44.27)
        self.assertIn("202606new.txt", session.urls[0])

    def test_404_current_month_then_previous_month_success(self) -> None:
        session = _Session([
            _response(404, ""),
            _response(200, "20260529 13450000 35.12 35.01\n"),
        ])
        quote = fetch_latest_vixtwn(session=session, today=date(2026, 6, 1))
        self.assertEqual(quote.as_of, "2026-05-29")
        self.assertEqual(quote.value, 35.12)
        self.assertEqual(len(session.urls), 2)

    def test_empty_current_month_then_previous_month_success(self) -> None:
        session = _Session([
            _response(200, "header only\n"),
            _response(200, "20251231 13450000 22.5\n"),
        ])
        quote = fetch_latest_vixtwn(session=session, today=date(2026, 1, 2))
        self.assertEqual(quote.as_of, "2025-12-31")
        self.assertEqual(quote.value, 22.5)

    def test_all_attempts_fail_returns_gap(self) -> None:
        session = _Session([RuntimeError("timeout"), _response(500, "")])
        quote = fetch_latest_vixtwn(session=session, today=date(2026, 6, 28))
        self.assertIsNone(quote.value)
        self.assertEqual(quote.data_gap_reason, "taifex_vixtwn_fetch_failed")


if __name__ == "__main__":
    unittest.main()

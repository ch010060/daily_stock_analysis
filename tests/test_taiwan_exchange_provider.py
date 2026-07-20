from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from data_provider.taiwan_exchange import (
    OfficialTaiwanExchangeProvider,
    ProviderSchemaError,
    parse_tpex_ohlc,
    parse_tpex_traded_value,
    parse_twse_ohlc,
    parse_twse_traded_value,
)


TWSE_OHLC = {
    "stat": "OK",
    "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
    "data": [
        ["115/07/13", "44,000.00", "44,500.00", "43,800.00", "44,300.00"],
        ["115/07/14", "44,400.00", "45,364.40", "43,654.04", "44,737.95"],
    ],
}

TPEX_OHLC = {
    "stat": "ok",
    "tables": [{
        "fields": ["日期", "開市", "最高", "最低", "收市", "漲/跌"],
        "data": [["2026/07/14", "419.28", "420.37", "390.99", "407.41", "-11.87"]],
    }],
}

TWSE_VALUE = {
    "stat": "OK",
    "fields": ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"],
    "data": [["115/07/14", "12,000", "1,245,206,538,568", "3,000", "44,737.95", "-642.57"]],
}

TPEX_VALUE = {
    "stat": "ok",
    "tables": [{
        "fields": ["日期", "成交張數", "金額（仟元）", "筆數", "櫃買指數", "漲/跌"],
        "data": [["115/07/14", "1,000", "289,947,486", "500", "407.41", "-11.87"]],
    }],
}

TWSE_2026_07_20 = {
    "stat": "OK",
    "fields": TWSE_OHLC["fields"],
    "data": [
        ["115/07/17", "45,234.08", "45,234.08", "42,671.27", "42,671.27"],
        ["115/07/20", "42,793.15", "43,084.51", "41,967.75", "42,449.70"],
    ],
}

TWSE_VALUE_2026_07_20 = {
    "stat": "OK",
    "fields": TWSE_VALUE["fields"],
    "data": [["115/07/20", "12,566,601,514", "1,041,457,434,398", "5,674,801", "42,449.70", "-221.57"]],
}

TPEX_2026_07_20 = {
    "stat": "ok",
    "tables": [{
        "title": "櫃買指數(月查詢)",
        "fields": TPEX_OHLC["tables"][0]["fields"],
        "data": [
            ["2026/07/17", "401.65", "401.65", "378.20", "378.44", "-28.57"],
            ["2026/07/20", "378.15", "378.15", "357.22", "368.53", "-9.91"],
        ],
    }],
}


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _month_rows(month_start: date) -> dict:
    rows = []
    current = month_start
    close = 100.0
    while current.month == month_start.month:
        if current.weekday() < 5:
            rows.append([
                f"{current.year - 1911:03d}/{current.month:02d}/{current.day:02d}",
                f"{close:.2f}", f"{close + 2:.2f}", f"{close - 2:.2f}", f"{close + 1:.2f}",
            ])
            close += 1
        current += timedelta(days=1)
    return {"stat": "OK", "fields": TWSE_OHLC["fields"], "data": rows}


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, dict(params), timeout))
        raw = params["date"]
        year, month = int(raw[:4]), int(raw[4:6])
        return _Response(_month_rows(date(year, month, 1)))


class TaiwanExchangeParserTest(unittest.TestCase):
    def test_parses_the_four_approved_structured_schemas(self) -> None:
        taiex = parse_twse_ohlc(TWSE_OHLC)
        tpex = parse_tpex_ohlc(TPEX_OHLC)
        twse_value = parse_twse_traded_value(TWSE_VALUE)
        tpex_value = parse_tpex_traded_value(TPEX_VALUE)

        self.assertEqual(taiex[-1], {
            "date": "2026-07-14", "open": 44400.0, "high": 45364.4,
            "low": 43654.04, "close": 44737.95,
        })
        self.assertEqual(tpex[-1]["close"], 407.41)
        self.assertEqual(twse_value[-1]["value"], 1245206538568)
        self.assertEqual(tpex_value[-1]["value"], 289947486000)

    def test_rejects_schema_drift_duplicates_and_invalid_ohlc(self) -> None:
        with self.assertRaises(ProviderSchemaError):
            parse_twse_ohlc({"stat": "OK", "fields": ["日期", "收盤指數"], "data": []})

        duplicate = json.loads(json.dumps(TWSE_OHLC))
        duplicate["data"].append(list(duplicate["data"][-1]))
        with self.assertRaises(ProviderSchemaError):
            parse_twse_ohlc(duplicate)

        invalid = json.loads(json.dumps(TWSE_OHLC))
        invalid["data"][-1][2] = "43,000.00"
        with self.assertRaises(ProviderSchemaError):
            parse_twse_ohlc(invalid)

    def test_empty_valid_response_is_not_fabricated(self) -> None:
        payload = {"stat": "OK", "fields": TWSE_OHLC["fields"], "data": []}
        self.assertEqual(parse_twse_ohlc(payload), [])

    def test_2026_07_20_official_price_index_and_turnover_provenance(self) -> None:
        taiex = parse_twse_ohlc(TWSE_2026_07_20)
        twse_value = parse_twse_traded_value(TWSE_VALUE_2026_07_20)
        tpex = parse_tpex_ohlc(TPEX_2026_07_20)

        self.assertEqual(taiex[-1], {
            "date": "2026-07-20", "open": 42793.15, "high": 43084.51,
            "low": 41967.75, "close": 42449.70,
        })
        self.assertAlmostEqual(taiex[-1]["close"] - taiex[-2]["close"], -221.57, places=2)
        self.assertEqual(twse_value[-1], {"date": "2026-07-20", "value": 1_041_457_434_398})
        self.assertEqual(f"{twse_value[-1]['value'] / 1_000_000_000_000:.2f}", "1.04")
        self.assertEqual(tpex[-2]["close"], 378.44)
        self.assertEqual(tpex[-1]["close"], 368.53)
        self.assertAlmostEqual((tpex[-1]["close"] - tpex[-2]["close"]) / tpex[-2]["close"] * 100, -2.62, places=2)


class TaiwanExchangeBootstrapTest(unittest.TestCase):
    def test_bootstraps_120_and_260_sessions_with_bounded_month_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = _Session()
            provider = OfficialTaiwanExchangeProvider(
                session=session,
                cache_dir=Path(temp_dir),
                now=lambda: date(2026, 7, 15),
            )

            first = provider.load_series("taiex_ohlc", end_date="2026-07-14", minimum_rows=120)
            first_calls = len(session.calls)
            second = provider.load_series("taiex_ohlc", end_date="2026-07-14", minimum_rows=260)

            self.assertTrue(first["ok"])
            self.assertGreaterEqual(len(first["rows"]), 120)
            self.assertLessEqual(first_calls, 7)
            self.assertGreaterEqual(len(second["rows"]), 260)
            self.assertLessEqual(len(session.calls), 14)
            self.assertNotIn("yahoo", json.dumps(second).lower())
            self.assertNotIn("finmind", json.dumps(second).lower())

    def test_reuses_completed_month_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = _Session()
            provider = OfficialTaiwanExchangeProvider(
                session=session,
                cache_dir=Path(temp_dir),
                now=lambda: date(2026, 8, 10),
            )
            provider.load_series("taiex_ohlc", end_date="2026-07-31", minimum_rows=20)
            call_count = len(session.calls)
            provider.load_series("taiex_ohlc", end_date="2026-07-31", minimum_rows=20)

            self.assertEqual(len(session.calls), call_count)


if __name__ == "__main__":
    unittest.main()

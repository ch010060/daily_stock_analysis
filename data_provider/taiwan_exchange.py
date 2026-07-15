"""Official TWSE/TPEx completed daily market data.

This boundary only knows the four operator-approved structured JSON endpoints.
It has no Yahoo, FinMind, HTML, or intraday fallback.
"""

from __future__ import annotations

import json
import math
import os
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ProviderSchemaError(ValueError):
    """Raised when an official response no longer matches the approved schema."""


def _number(value: Any, *, integer: bool = False) -> float | int:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ProviderSchemaError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise ProviderSchemaError(f"invalid numeric value: {value!r}")
    return int(number) if integer else number


def _iso_date(value: Any) -> str:
    text = str(value or "").strip().replace("-", "/")
    if "/" in text:
        parts = text.split("/")
    elif len(text) in {7, 8} and text.isdigit():
        year_width = len(text) - 4
        parts = [text[:year_width], text[year_width:year_width + 2], text[-2:]]
    else:
        raise ProviderSchemaError(f"invalid date: {value!r}")
    if len(parts) != 3:
        raise ProviderSchemaError(f"invalid date: {value!r}")
    try:
        year = int(parts[0])
        if year < 1911:
            year += 1911
        return date(year, int(parts[1]), int(parts[2])).isoformat()
    except ValueError as exc:
        raise ProviderSchemaError(f"invalid date: {value!r}") from exc


def _table(payload: Dict[str, Any], required: List[str]) -> tuple[List[str], List[List[Any]]]:
    if not isinstance(payload, dict):
        raise ProviderSchemaError("payload must be an object")
    if "tables" in payload:
        tables = payload.get("tables")
        table = tables[0] if isinstance(tables, list) and tables else None
        if not isinstance(table, dict):
            raise ProviderSchemaError("missing response table")
        fields, rows = table.get("fields"), table.get("data")
    else:
        fields, rows = payload.get("fields"), payload.get("data")
    if not isinstance(fields, list) or not all(field in fields for field in required):
        raise ProviderSchemaError(f"schema drift: required fields {required!r}")
    if not isinstance(rows, list):
        raise ProviderSchemaError("response data must be an array")
    return [str(field) for field in fields], rows


def _unique(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dates = [row["date"] for row in rows]
    if len(dates) != len(set(dates)):
        raise ProviderSchemaError("duplicate trading session")
    return sorted(rows, key=lambda row: row["date"])


def _ohlc(payload: Dict[str, Any], labels: List[str]) -> List[Dict[str, Any]]:
    fields, raw_rows = _table(payload, labels)
    indexes = [fields.index(label) for label in labels]
    rows: List[Dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < len(fields):
            raise ProviderSchemaError("malformed response row")
        values = [_number(raw[index]) for index in indexes[1:]]
        open_, high, low, close = values
        if min(values) <= 0 or low > min(open_, close) or high < max(open_, close) or low > high:
            raise ProviderSchemaError("invalid OHLC envelope")
        rows.append({
            "date": _iso_date(raw[indexes[0]]),
            "open": open_, "high": high, "low": low, "close": close,
        })
    return _unique(rows)


def parse_twse_ohlc(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _ohlc(payload, ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"])


def parse_tpex_ohlc(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _ohlc(payload, ["日期", "開市", "最高", "最低", "收市"])


def _traded_value(payload: Dict[str, Any], label: str, multiplier: int) -> List[Dict[str, Any]]:
    fields, raw_rows = _table(payload, ["日期", label])
    date_index, value_index = fields.index("日期"), fields.index(label)
    rows = []
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < len(fields):
            raise ProviderSchemaError("malformed response row")
        value = int(_number(raw[value_index], integer=True)) * multiplier
        rows.append({"date": _iso_date(raw[date_index]), "value": value})
    return _unique(rows)


def parse_twse_traded_value(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _traded_value(payload, "成交金額", 1)


def parse_tpex_traded_value(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _traded_value(payload, "金額（仟元）", 1000)


_SERIES = {
    "taiex_ohlc": {
        "url": "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST",
        "parser": parse_twse_ohlc,
        "provider": "TWSE",
        "endpoint_family": "indicesReport/MI_5MINS_HIST",
        "metric_kind": "ohlc",
        "raw_unit": "index_points",
    },
    "tpex_ohlc": {
        "url": "https://www.tpex.org.tw/www/zh-tw/indexInfo/inx",
        "parser": parse_tpex_ohlc,
        "provider": "TPEx",
        "endpoint_family": "indexInfo/inx",
        "metric_kind": "ohlc",
        "raw_unit": "index_points",
    },
    "twse_traded_value": {
        "url": "https://www.twse.com.tw/exchangeReport/FMTQIK",
        "parser": parse_twse_traded_value,
        "provider": "TWSE",
        "endpoint_family": "exchangeReport/FMTQIK",
        "metric_kind": "traded_value",
        "raw_unit": "TWD",
    },
    "tpex_traded_value": {
        "url": "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_index/st41_result.php",
        "parser": parse_tpex_traded_value,
        "provider": "TPEx",
        "endpoint_family": "daily_trading_index/st41_result.php",
        "metric_kind": "traded_value",
        "raw_unit": "thousand_TWD",
    },
}


def _previous_month(value: date) -> date:
    return date(value.year - 1, 12, 1) if value.month == 1 else date(value.year, value.month - 1, 1)


class OfficialTaiwanExchangeProvider:
    """Bounded monthly bootstrap with immutable completed-month JSON cache."""

    def __init__(
        self,
        *,
        session=None,
        cache_dir: Optional[Path] = None,
        now: Callable[[], date] = date.today,
        allow_network: bool = True,
    ) -> None:
        self._session = session
        self._cache_dir = cache_dir or Path("data/cache/tw_market_exchange")
        self._now = now
        self._allow_network = allow_network

    def _params(self, series: str, month: date) -> Dict[str, str]:
        if series == "tpex_ohlc":
            return {"date": month.strftime("%Y/%m/01")}
        if series == "tpex_traded_value":
            return {"l": "zh-tw", "d": f"{month.year - 1911:03d}/{month.month:02d}", "o": "json"}
        return {"date": month.strftime("%Y%m01"), "response": "json"}

    def _cache_path(self, series: str, month: date) -> Path:
        return self._cache_dir / series / f"{month:%Y-%m}.json"

    def _completed_month(self, month: date) -> bool:
        today = self._now()
        return (month.year, month.month) < (today.year, today.month)

    def _write_cache(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)

    def _month_payload(self, series: str, month: date) -> Dict[str, Any]:
        path = self._cache_path(series, month)
        if self._completed_month(month) and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if not self._allow_network:
            raise RuntimeError("official_exchange_network_disabled")
        config = _SERIES[series]
        if self._session is None:
            import requests
            response = requests.get(config["url"], params=self._params(series, month), timeout=20)
        else:
            response = self._session.get(config["url"], params=self._params(series, month), timeout=20)
        if response.status_code != 200:
            raise RuntimeError(f"official_exchange_http_{response.status_code}")
        payload = response.json()
        if self._completed_month(month):
            self._write_cache(path, payload)
        return payload

    def load_series(self, series: str, *, end_date: str, minimum_rows: int) -> Dict[str, Any]:
        if series not in _SERIES:
            raise ValueError(f"unsupported official series: {series}")
        config = _SERIES[series]
        cutoff = date.fromisoformat(end_date)
        month = cutoff.replace(day=1)
        rows: List[Dict[str, Any]] = []
        requested_months: List[str] = []
        try:
            for _ in range(18):
                payload = self._month_payload(series, month)
                requested_months.append(month.strftime("%Y-%m"))
                rows.extend(config["parser"](payload))
                rows = _unique([row for row in rows if row["date"] <= end_date])
                if len(rows) >= minimum_rows:
                    break
                month = _previous_month(month)
        except (OSError, ValueError, RuntimeError, ProviderSchemaError, json.JSONDecodeError) as exc:
            return self._result(series, config, [], requested_months, end_date, False, str(exc))
        ok = len(rows) >= minimum_rows
        reason = None if ok else f"insufficient_history:{len(rows)}<{minimum_rows}"
        return self._result(series, config, rows, requested_months, end_date, ok, reason)

    @staticmethod
    def _result(
        series: str,
        config: Dict[str, Any],
        rows: List[Dict[str, Any]],
        requested_months: List[str],
        end_date: str,
        ok: bool,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "ok": ok,
            "series": series,
            "rows": rows,
            "provider": config["provider"],
            "endpoint_family": config["endpoint_family"],
            "index_kind": "price_index" if config["metric_kind"] == "ohlc" else None,
            "metric_kind": config["metric_kind"],
            "raw_unit": config["raw_unit"],
            "normalized_unit": "TWD" if config["metric_kind"] == "traded_value" else config["raw_unit"],
            "requested_months": requested_months,
            "first_date": rows[0]["date"] if rows else None,
            "latest_date": rows[-1]["date"] if rows else None,
            "row_count": len(rows),
            "data_date": end_date,
            "as_of": rows[-1]["date"] if rows else None,
            "lag_sessions": None,
            "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "status": "available" if ok else "unavailable",
            "suppression_reason": reason,
            "terms_access_risk": "medium",
        }


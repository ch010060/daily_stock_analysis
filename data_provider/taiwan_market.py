# -*- coding: utf-8 -*-
"""
TaiwanMarketDataFetcher — FinMind-first Taiwan market-level data adapter.

Provides market-level data for 台股大盤回顧 (TW market review):
  - Trading dates
  - TAIEX / TPEx total return index
  - Institutional investors total (三大法人)
  - Margin purchase / short-sale total (融資融券)
  - Reference stock daily prices / PER rows (0050, 006208, 2330)
  - Snapshot composition

Provider chain:
  1. FinMind REST (primary)  — guarded by DSA_FIXTURE_MODE + DSA_ALLOW_EXTERNAL_NETWORK
  2. yfinance (fallback)     — only when FinMind unavailable
  3. news_only (degraded)   — signalled; caller decides whether to proceed

Network guards (evaluated in order):
  DSA_FIXTURE_MODE=true          → fixture path only, no network
  DSA_ALLOW_EXTERNAL_NETWORK=false → fixture path only, no network
  token absent                   → FinMind unavailable; yfinance fallback

TPEx yfinance fallback: explicitly unavailable — no reliable cross-platform symbol.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance
    _YFINANCE_AVAILABLE = True
except ImportError:  # pragma: no cover
    yfinance = None  # type: ignore[assignment]
    _YFINANCE_AVAILABLE = False

_FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"
_YFINANCE_SYMBOLS = {
    "TAIEX": "^TWII",
    "0050": "0050.TW",
    "006208": "006208.TW",
    "2330": "2330.TW",
}

_REPRESENTATIVE_NAMES = {
    "0050": "元大台灣50",
    "006208": "富邦台50",
    "2330": "臺積電",
}

_RESULT_KEYS = (
    "ok", "source", "dataset", "data_id", "rows", "columns",
    "row_count", "start_date", "end_date", "error", "unavailable_reason",
    "cache_meta",
)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tw_direction(change: Optional[float]) -> str:
    if change is None:
        return "neutral"
    if change > 0:
        return "tw_gain"
    if change < 0:
        return "tw_loss"
    return "neutral"


def _latest_rows_on_or_before(rows: List[Dict[str, Any]], data_date: Optional[str]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    if not rows:
        return {}, {}
    if data_date:
        usable = [row for row in rows if str(row.get("date") or "") <= data_date]
    else:
        usable = list(rows)
    if not usable:
        return {}, {}
    usable.sort(key=lambda row: str(row.get("date") or ""))
    last = usable[-1]
    prev = usable[-2] if len(usable) >= 2 else {}
    return last, prev


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fixture_root() -> Path:
    return _repo_root() / "tests" / "fixtures" / "tw_market"


def _unavailable(
    dataset: str,
    data_id: Optional[str],
    start_date: str,
    end_date: str,
    reason: str,
    source: str = "finmind",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "source": source,
        "dataset": dataset,
        "data_id": data_id,
        "rows": [],
        "columns": [],
        "row_count": 0,
        "start_date": start_date,
        "end_date": end_date,
        "error": error,
        "unavailable_reason": reason,
        "cache_meta": {
            "source": source,
            "provider": "TaiwanMarketDataFetcher",
            "dataset": dataset,
            "data_id": data_id,
        },
    }


def _success(
    dataset: str,
    data_id: Optional[str],
    start_date: str,
    end_date: str,
    rows: List[Dict[str, Any]],
    source: str,
) -> Dict[str, Any]:
    cols = list(rows[0].keys()) if rows else []
    return {
        "ok": True,
        "source": source,
        "dataset": dataset,
        "data_id": data_id,
        "rows": rows,
        "columns": cols,
        "row_count": len(rows),
        "start_date": start_date,
        "end_date": end_date,
        "error": None,
        "unavailable_reason": None,
        "cache_meta": {
            "source": source,
            "provider": "TaiwanMarketDataFetcher",
            "dataset": dataset,
            "data_id": data_id,
        },
    }


class TaiwanMarketDataFetcher:
    """FinMind-first Taiwan market-level data adapter for 台股大盤回顧."""

    def __init__(
        self,
        fixture_root: Optional[Path] = None,
        session=None,
    ) -> None:
        self._fixture_root = fixture_root or _fixture_root()
        self._session = session  # optional requests.Session for testing

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _no_network(self) -> bool:
        return _env_bool("DSA_FIXTURE_MODE", False) or not _env_bool(
            "DSA_ALLOW_EXTERNAL_NETWORK", False
        )

    def _get_token(self) -> str:
        return (
            os.getenv("FINMIND_API_TOKEN", "").strip()
            or os.getenv("FINMIND_TOKEN", "").strip()
        )

    def _finmind_get(
        self,
        dataset: str,
        data_id: Optional[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Call FinMind REST. Returns raw json dict (status, data). Never raises."""
        token = self._get_token()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params: Dict[str, str] = {
            "dataset": dataset,
            "start_date": start_date,
            "end_date": end_date,
        }
        if data_id:
            params["data_id"] = data_id

        try:
            if self._session is not None:
                resp = self._session.get(_FINMIND_BASE, params=params, headers=headers, timeout=30)
            else:
                import requests
                resp = requests.get(_FINMIND_BASE, params=params, headers=headers, timeout=30)

            if resp.status_code == 402:
                return {"status": 402, "msg": "quota_exceeded", "data": []}
            if resp.status_code != 200:
                return {"status": resp.status_code, "msg": f"http_{resp.status_code}", "data": []}
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[TaiwanMarket] FinMind request failed dataset=%s data_id=%s: %s",
                dataset, data_id, exc,
            )
            return {"status": -1, "msg": str(exc), "data": []}

    def _load_fixture(self, fixture_name: str) -> Optional[Dict[str, Any]]:
        path = self._fixture_root / fixture_name
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning("[TaiwanMarket] fixture load failed %s: %s", fixture_name, exc)
            return None

    def _finmind_or_fixture(
        self,
        dataset: str,
        data_id: Optional[str],
        start_date: str,
        end_date: str,
        fixture_name: str,
    ) -> Dict[str, Any]:
        """
        Route to fixture when no-network, else call FinMind.

        Returns a raw FinMind-shaped dict: {status, msg, data}.
        """
        if self._no_network():
            fx = self._load_fixture(fixture_name)
            if fx is None:
                return {"status": -1, "msg": f"fixture_not_found:{fixture_name}", "data": []}
            fx["_source"] = "fixture"
            return fx

        raw = self._finmind_get(dataset, data_id, start_date, end_date)
        raw["_source"] = "finmind"
        return raw

    def _wrap_finmind_result(
        self,
        raw: Dict[str, Any],
        dataset: str,
        data_id: Optional[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Convert raw FinMind response into standard result dict."""
        source = raw.get("_source", "finmind")
        api_status = raw.get("status")

        if api_status != 200:
            msg = str(raw.get("msg", "unknown"))
            return _unavailable(
                dataset, data_id, start_date, end_date,
                reason=f"finmind_error:{msg}",
                source=source,
                error=msg,
            )

        rows = raw.get("data") or []
        if not rows:
            return _unavailable(
                dataset, data_id, start_date, end_date,
                reason="empty_response",
                source=source,
            )

        return _success(dataset, data_id, start_date, end_date, rows, source=source)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_trading_dates(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Return list of Taiwan stock exchange trading dates."""
        dataset = "TaiwanStockTradingDate"
        raw = self._finmind_or_fixture(
            dataset, None, start_date, end_date, "finmind_trading_date.json"
        )
        return self._wrap_finmind_result(raw, dataset, None, start_date, end_date)

    def get_total_return_index(
        self, index_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        Return TAIEX or TPEx total return index daily prices.

        index_id: "TAIEX" | "TPEx"
        columns: date, stock_id, price
        """
        dataset = "TaiwanStockTotalReturnIndex"
        fixture_map = {
            "TAIEX": "finmind_total_return_index_taiex.json",
            "TPEx": "finmind_total_return_index_tpex.json",
        }
        fixture_name = fixture_map.get(index_id, f"finmind_total_return_index_{index_id.lower()}.json")
        raw = self._finmind_or_fixture(dataset, index_id, start_date, end_date, fixture_name)
        return self._wrap_finmind_result(raw, dataset, index_id, start_date, end_date)

    def get_institutional_investors_total(
        self, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        Return total institutional investor buy/sell figures (三大法人合計).

        columns: date, name, buy, sell
        name values: Foreign_Investor, Investment_Trust, Dealer_self, Dealer_Hedging, total
        """
        dataset = "TaiwanStockTotalInstitutionalInvestors"
        raw = self._finmind_or_fixture(
            dataset, None, start_date, end_date, "finmind_institutional_total.json"
        )
        return self._wrap_finmind_result(raw, dataset, None, start_date, end_date)

    def get_margin_purchase_short_sale_total(
        self, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        Return total margin purchase / short sale figures (融資融券).

        columns: date, name, TodayBalance, YesBalance, buy, sell, Return
        name values: MarginPurchaseMoney, ShortSaleMoney, ShortSaleVolume
        """
        dataset = "TaiwanStockTotalMarginPurchaseShortSale"
        raw = self._finmind_or_fixture(
            dataset, None, start_date, end_date, "finmind_margin_total.json"
        )
        return self._wrap_finmind_result(raw, dataset, None, start_date, end_date)

    def get_reference_stock_daily(
        self, stock_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        Return daily price data for a reference TW stock (0050, 2330, etc.).

        columns: date, stock_id, open, max, min, close, spread, Trading_Volume, Trading_money
        Falls back to yfinance when FinMind unavailable.
        """
        dataset = "TaiwanStockPrice"
        fixture_map = {
            "0050": "finmind_stock_price_0050.json",
            "006208": "finmind_stock_price_006208.json",
            "2330": "finmind_stock_price_2330.json",
        }
        fixture_name = fixture_map.get(stock_id, f"finmind_stock_price_{stock_id}.json")

        raw = self._finmind_or_fixture(dataset, stock_id, start_date, end_date, fixture_name)
        result = self._wrap_finmind_result(raw, dataset, stock_id, start_date, end_date)
        if result["ok"]:
            return result

        # yfinance fallback for reference stocks
        return self._yfinance_stock_fallback(stock_id, start_date, end_date, dataset)

    def get_reference_stock_per(
        self, stock_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Return PER/PBR/dividend yield for a representative TW stock/ETF."""
        dataset = "TaiwanStockPER"
        fixture_name = f"finmind_stock_per_{stock_id}.json"
        raw = self._finmind_or_fixture(dataset, stock_id, start_date, end_date, fixture_name)
        return self._wrap_finmind_result(raw, dataset, stock_id, start_date, end_date)

    def get_tw_market_snapshot(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Compose a TW market snapshot from all required datasets.

        Required: trading_dates, TAIEX, institutional_total, margin_total
        Optional: TPEx, 0050, 2330

        Returns a dict with all section results plus availability summary.
        """
        taiex = self.get_total_return_index("TAIEX", start_date, end_date)
        tpex = self.get_total_return_index("TPEx", start_date, end_date)
        institutional = self.get_institutional_investors_total(start_date, end_date)
        margin = self.get_margin_purchase_short_sale_total(start_date, end_date)
        trading_dates = self.get_trading_dates(start_date, end_date)
        ref_0050 = self.get_reference_stock_daily("0050", start_date, end_date)
        ref_006208 = self.get_reference_stock_daily("006208", start_date, end_date)
        ref_2330 = self.get_reference_stock_daily("2330", start_date, end_date)
        per_0050 = self.get_reference_stock_per("0050", start_date, end_date)
        per_006208 = self.get_reference_stock_per("006208", start_date, end_date)
        per_2330 = self.get_reference_stock_per("2330", start_date, end_date)

        required_sections = {
            "trading_dates": trading_dates,
            "taiex": taiex,
            "institutional_total": institutional,
            "margin_total": margin,
        }
        optional_sections = {
            "tpex": tpex,
            "ref_0050": ref_0050,
            "ref_006208": ref_006208,
            "ref_2330": ref_2330,
            "per_0050": per_0050,
            "per_006208": per_006208,
            "per_2330": per_2330,
        }

        required_ok = all(s["ok"] for s in required_sections.values())
        missing_required = [k for k, v in required_sections.items() if not v["ok"]]
        missing_optional = [k for k, v in optional_sections.items() if not v["ok"]]

        sources = list({
            v["source"]
            for v in {**required_sections, **optional_sections}.values()
            if v["ok"]
        })

        last_trading_date: Optional[str] = None
        if taiex["ok"] and taiex["rows"]:
            last_trading_date = taiex["rows"][-1].get("date")

        sections = {
            **required_sections,
            **optional_sections,
            "availability": {
                "required_ok": required_ok,
                "partial": bool(missing_optional) and required_ok,
                "missing_required": missing_required,
                "missing_optional": missing_optional,
                "sources": sources,
                "as_of": last_trading_date,
            },
        }
        sections["tw_daily_snapshot"] = self._build_tw_daily_snapshot(sections)
        return sections

    def _build_tw_daily_snapshot(self, sections: Dict[str, Any]) -> Dict[str, Any]:
        """Build a persisted structured snapshot while keeping legacy raw sections."""
        availability = sections.get("availability") or {}
        data_date = availability.get("as_of")
        data_status = {
            "missing_fields": [],
            "stale_fields": [],
            "partial_failures": [
                key for key, value in sections.items()
                if isinstance(value, dict) and value.get("ok") is False
            ],
        }

        datasets = []
        for key, value in sections.items():
            if not isinstance(value, dict) or "dataset" not in value:
                continue
            rows = value.get("rows") or []
            datasets.append({
                "key": key,
                "dataset": value.get("dataset"),
                "data_id": value.get("data_id"),
                "source": value.get("source"),
                "ok": bool(value.get("ok")),
                "row_count": value.get("row_count", 0),
                "as_of": rows[-1].get("date") if rows else None,
                "unavailable_reason": value.get("unavailable_reason"),
            })

        return {
            "kind": "tw_daily_snapshot",
            "source": "finmind",
            "data_date": data_date,
            "datasets": datasets,
            "indices": self._snapshot_indices(sections),
            "institutional_flows": self._snapshot_institutional_flows(sections),
            "margin_short": self._snapshot_margin_short(sections),
            "representatives": self._snapshot_representatives(sections, data_status),
            "data_status": data_status,
        }

    def _snapshot_indices(self, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
        data_date = (sections.get("availability") or {}).get("as_of")
        names = {
            "taiex": ("TAIEX", "加權報酬指數"),
            "tpex": ("TPEx", "櫃買報酬指數"),
        }
        rows_out: List[Dict[str, Any]] = []
        for key, (symbol, name) in names.items():
            result = sections.get(key) or {}
            rows = result.get("rows") or []
            if not result.get("ok") or not rows:
                continue
            last, prev = _latest_rows_on_or_before(rows, data_date)
            if not last:
                continue
            value = _to_float(last.get("price"))
            prev_value = _to_float(prev.get("price"))
            change = value - prev_value if value is not None and prev_value is not None else None
            change_pct = (
                change / prev_value * 100
                if change is not None and prev_value not in (None, 0)
                else None
            )
            rows_out.append({
                "symbol": symbol,
                "name": name,
                "value": value,
                "previous_value": prev_value,
                "change": change,
                "change_pct": change_pct,
                "data_date": last.get("date"),
                "source_dataset": result.get("dataset"),
                "source": result.get("source"),
                "semantic_direction": _tw_direction(change),
            })
        return rows_out

    def _snapshot_institutional_flows(self, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = sections.get("institutional_total") or {}
        rows = result.get("rows") or []
        if not result.get("ok") or not rows:
            return []
        latest_date = max(row.get("date", "") for row in rows)
        out = []
        for row in rows:
            if row.get("date") != latest_date:
                continue
            buy = _to_float(row.get("buy")) or 0.0
            sell = _to_float(row.get("sell")) or 0.0
            net = buy - sell
            out.append({
                "name": row.get("name"),
                "buy": buy,
                "sell": sell,
                "net": net,
                "unit": "TWD",
                "display_divisor": 1e8,
                "data_date": row.get("date"),
                "source_dataset": result.get("dataset"),
                "source": result.get("source"),
                "semantic_direction": "net_buy" if net > 0 else ("net_sell" if net < 0 else "neutral"),
            })
        return out

    def _snapshot_margin_short(self, sections: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = sections.get("margin_total") or {}
        rows = result.get("rows") or []
        if not result.get("ok") or not rows:
            return []
        latest_date = max(row.get("date", "") for row in rows)
        out = []
        for row in rows:
            if row.get("date") != latest_date:
                continue
            today = _to_float(row.get("TodayBalance"))
            yesterday = _to_float(row.get("YesBalance"))
            change = today - yesterday if today is not None and yesterday is not None else None
            name = row.get("name")
            out.append({
                "name": name,
                "today_balance": today,
                "yesterday_balance": yesterday,
                "change": change,
                "unit": "shares" if name == "ShortSaleVolume" else "TWD",
                "display_divisor": 1 if name == "ShortSaleVolume" else 1e8,
                "data_date": row.get("date"),
                "source_dataset": result.get("dataset"),
                "source": result.get("source"),
                "semantic_type": "risk_or_leverage",
            })
        return out

    def _snapshot_representatives(
        self,
        sections: Dict[str, Any],
        data_status: Dict[str, List[str]],
    ) -> List[Dict[str, Any]]:
        data_date = (sections.get("availability") or {}).get("as_of")
        out: List[Dict[str, Any]] = []
        for symbol, name in _REPRESENTATIVE_NAMES.items():
            price_result = sections.get(f"ref_{symbol}") or {}
            price_rows = price_result.get("rows") or []
            if not price_result.get("ok") or not price_rows:
                continue
            last, prev = _latest_rows_on_or_before(price_rows, data_date)
            if not last:
                continue
            close = _to_float(last.get("close"))
            previous_close = _to_float(prev.get("close"))
            change = (
                close - previous_close
                if close is not None and previous_close is not None
                else _to_float(last.get("spread"))
            )
            change_pct = (
                change / previous_close * 100
                if change is not None and previous_close not in (None, 0)
                else None
            )

            per_result = sections.get(f"per_{symbol}") or {}
            per_rows = per_result.get("rows") or []
            per_last = {}
            if per_result.get("ok") and per_rows:
                per_last, _ = _latest_rows_on_or_before(per_rows, data_date)
            missing_fields: List[str] = []
            valuation = {}
            for field in ("PER", "PBR", "dividend_yield"):
                value = _to_float(per_last.get(field))
                valuation[field] = value
                if value is None:
                    missing_fields.append(field)
                    data_status["missing_fields"].append(f"representatives.{symbol}.{field}")

            out.append({
                "symbol": symbol,
                "name": name,
                "close": close,
                "previous_close": previous_close,
                "change": change,
                "change_pct": change_pct,
                "volume": last.get("Trading_Volume"),
                "turnover": last.get("Trading_money"),
                "trading_turnover": last.get("Trading_turnover"),
                "data_date": last.get("date"),
                "source_dataset": price_result.get("dataset"),
                "source": price_result.get("source"),
                "PER": valuation["PER"],
                "PBR": valuation["PBR"],
                "dividend_yield": valuation["dividend_yield"],
                "valuation_as_of": per_last.get("date"),
                "valuation_source_dataset": per_result.get("dataset"),
                "missing_fields": missing_fields,
                "semantic_direction": _tw_direction(change),
            })
        return out

    # ------------------------------------------------------------------
    # yfinance fallback helpers
    # ------------------------------------------------------------------

    def get_taiex_via_yfinance(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Fetch TAIEX via yfinance (^TWII) as fallback."""
        return self._yfinance_index_fallback("TAIEX", "^TWII", start_date, end_date)

    def _yfinance_index_fallback(
        self, index_id: str, yf_symbol: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        dataset = f"yfinance:{yf_symbol}"
        if self._no_network():
            return _unavailable(
                dataset, index_id, start_date, end_date,
                reason="no_network", source="yfinance",
            )
        if not _YFINANCE_AVAILABLE or yfinance is None:
            return _unavailable(
                dataset, index_id, start_date, end_date,
                reason="yfinance_not_installed", source="yfinance",
            )
        try:
            ticker = yfinance.Ticker(yf_symbol)
            df = ticker.history(start=start_date, end=end_date)
            if df is None or df.empty:
                return _unavailable(
                    dataset, index_id, start_date, end_date,
                    reason="yfinance_empty", source="yfinance",
                )
            rows = []
            for idx, row in df.iterrows():
                rows.append({
                    "date": str(idx.date()),
                    "stock_id": index_id,
                    "price": float(row["Close"]),
                })
            return _success(dataset, index_id, start_date, end_date, rows, source="yfinance")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[TaiwanMarket] yfinance fallback failed %s: %s", yf_symbol, exc)
            return _unavailable(
                dataset, index_id, start_date, end_date,
                reason="yfinance_error", source="yfinance",
                error=str(exc),
            )

    def _yfinance_stock_fallback(
        self, stock_id: str, start_date: str, end_date: str, dataset: str
    ) -> Dict[str, Any]:
        yf_symbol = _YFINANCE_SYMBOLS.get(stock_id)
        if yf_symbol is None:
            return _unavailable(
                dataset, stock_id, start_date, end_date,
                reason="yfinance_no_symbol", source="yfinance",
            )
        if self._no_network():
            return _unavailable(
                dataset, stock_id, start_date, end_date,
                reason="no_network", source="yfinance",
            )
        if not _YFINANCE_AVAILABLE or yfinance is None:
            return _unavailable(
                dataset, stock_id, start_date, end_date,
                reason="yfinance_not_installed", source="yfinance",
            )
        try:
            ticker = yfinance.Ticker(yf_symbol)
            df = ticker.history(start=start_date, end=end_date)
            if df is None or df.empty:
                return _unavailable(
                    dataset, stock_id, start_date, end_date,
                    reason="yfinance_empty", source="yfinance",
                )
            rows = []
            for idx, row in df.iterrows():
                rows.append({
                    "date": str(idx.date()),
                    "stock_id": stock_id,
                    "open": float(row.get("Open", 0)),
                    "close": float(row.get("Close", 0)),
                    "max": float(row.get("High", 0)),
                    "min": float(row.get("Low", 0)),
                    "Trading_Volume": int(row.get("Volume", 0)),
                })
            return _success(dataset, stock_id, start_date, end_date, rows, source="yfinance")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[TaiwanMarket] yfinance stock fallback failed %s: %s", yf_symbol, exc)
            return _unavailable(
                dataset, stock_id, start_date, end_date,
                reason="yfinance_error", source="yfinance",
                error=str(exc),
            )

# -*- coding: utf-8 -*-
"""
TaiwanMarketDataFetcher — FinMind-first Taiwan market-level data adapter.

Provides market-level data for 台股大盤回顧 (TW market review):
  - Trading dates
  - TAIEX / TPEx total return index
  - Institutional investors total (三大法人)
  - Margin purchase / short-sale total (融資融券)
  - Reference stock daily prices (0050, 2330)
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
    "2330": "2330.TW",
}

_RESULT_KEYS = (
    "ok", "source", "dataset", "data_id", "rows", "columns",
    "row_count", "start_date", "end_date", "error", "unavailable_reason",
    "cache_meta",
)


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
            "2330": "finmind_stock_price_2330.json",
        }
        fixture_name = fixture_map.get(stock_id, f"finmind_stock_price_{stock_id}.json")

        raw = self._finmind_or_fixture(dataset, stock_id, start_date, end_date, fixture_name)
        result = self._wrap_finmind_result(raw, dataset, stock_id, start_date, end_date)
        if result["ok"]:
            return result

        # yfinance fallback for reference stocks
        return self._yfinance_stock_fallback(stock_id, start_date, end_date, dataset)

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
        ref_2330 = self.get_reference_stock_daily("2330", start_date, end_date)

        required_sections = {
            "trading_dates": trading_dates,
            "taiex": taiex,
            "institutional_total": institutional,
            "margin_total": margin,
        }
        optional_sections = {
            "tpex": tpex,
            "ref_0050": ref_0050,
            "ref_2330": ref_2330,
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

        return {
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

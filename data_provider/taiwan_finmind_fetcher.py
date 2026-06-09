# -*- coding: utf-8 -*-
"""
TaiwanFinMindFetcher - fixture-first Taiwan market data source.

Live path is fail-closed until all four guards pass in order:
  DSA_FIXTURE_MODE → DSA_ALLOW_EXTERNAL_NETWORK → FINMIND_ENABLED → FINMIND_API_TOKEN
"""

import importlib.metadata
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


class TaiwanFinMindFetcher(BaseFetcher):
    """Fixture-first Taiwan daily bars provider following BaseFetcher."""

    name = "TaiwanFinMindFetcher"
    priority = int(os.getenv("TAIWAN_FINMIND_PRIORITY", "99"))

    def __init__(
        self,
        fixture_root: Optional[str | Path] = None,
        finmind_enabled: Optional[bool] = None,
    ) -> None:
        self._fixture_root = Path(fixture_root) if fixture_root else (
            _repo_root() / "tests" / "fixtures" / "market" / "tw"
        )
        self._finmind_enabled = (
            _env_bool("FINMIND_ENABLED", False)
            if finmind_enabled is None
            else bool(finmind_enabled)
        )

    def is_available_for_request(self, capability: str = "") -> bool:
        if capability not in {"", "daily_data"}:
            return False
        return True

    @staticmethod
    def _canonical_stock_code(stock_code: str) -> str:
        code = (stock_code or "").strip().upper()
        if code.startswith("TW:"):
            code = code[3:]
        if code.endswith(".TW"):
            code = code[:-3]
        if not (code.isdigit() and len(code) == 4):
            raise DataFetchError(f"[TaiwanFinMind] unsupported Taiwan stock code: {stock_code}")
        return code

    def _fixture_dir(self, stock_code: str) -> Path:
        return self._fixture_root / self._canonical_stock_code(stock_code)

    def _find_daily_fixture(self, stock_code: str, start_date: str, end_date: str) -> Path:
        fixture_dir = self._fixture_dir(stock_code)
        exact = fixture_dir / f"daily_bars_{start_date}_{end_date}.csv"
        if exact.exists():
            return exact
        matches = sorted(fixture_dir.glob("daily_bars_*.csv"))
        if matches:
            return matches[0]
        raise DataFetchError(f"[TaiwanFinMind] fixture not found for {stock_code}")

    def _load_fixture_csv(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Load daily bars from CSV fixture, filtered to the requested date range."""
        fixture_path = self._find_daily_fixture(stock_code, start_date, end_date)
        df = pd.read_csv(fixture_path)
        if "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce")
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            df = df.loc[(dates >= start) & (dates <= end)].copy()
        df.attrs["_cache_source"] = "fixture"
        df.attrs["_cache_start"] = start_date
        df.attrs["_cache_end"] = end_date
        return df

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        # Guard 1: fixture mode override — strongest gate, ignores all other flags
        if _env_bool("DSA_FIXTURE_MODE", False):
            return self._load_fixture_csv(stock_code, start_date, end_date)

        # Guard 2: external network kill switch
        if not _env_bool("DSA_ALLOW_EXTERNAL_NETWORK", False):
            return self._load_fixture_csv(stock_code, start_date, end_date)

        # Guard 3: FinMind live mode explicitly enabled
        if not self._finmind_enabled:
            return self._load_fixture_csv(stock_code, start_date, end_date)

        # Guard 4: API token must be present before any network call
        token = os.getenv("FINMIND_API_TOKEN", "").strip()
        if not token:
            raise DataFetchError(
                "[TaiwanFinMind] FINMIND_API_TOKEN not set. "
                "Set token or use fixture mode (DSA_FIXTURE_MODE=true)."
            )

        # Lazy import — only reached when all guards pass
        try:
            from FinMind.data import DataLoader  # noqa: PLC0415
        except ImportError as exc:
            raise DataFetchError(
                "[TaiwanFinMind] FinMind package not installed. "
                "Run: pip install FinMind"
            ) from exc

        canonical_code = self._canonical_stock_code(stock_code)
        try:
            loader = DataLoader()
            loader.login_by_token(api_token=token)
            raw = loader.taiwan_stock_daily(
                stock_id=canonical_code,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:  # noqa: BLE001 — surface as DataFetchError for fallback chain
            raise DataFetchError(
                f"[TaiwanFinMind] live fetch failed for {canonical_code}: {exc}"
            ) from exc

        df = pd.DataFrame(raw)
        df.attrs["_cache_source"] = "finmind_live"
        df.attrs["_cache_start"] = start_date
        df.attrs["_cache_end"] = end_date
        return df

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["code", *STANDARD_COLUMNS])

        cache_source = df.attrs.get("_cache_source", "fixture")
        request_start = df.attrs.get("_cache_start", "")
        request_end = df.attrs.get("_cache_end", "")

        normalized = df.copy()
        column_mapping = {
            "stock_id": "code",
            "Trading_Volume": "volume",
            "Trading_money": "amount",
            "max": "high",
            "min": "low",
            "spread": "price_spread",
        }
        normalized = normalized.rename(columns=column_mapping)

        normalized["code"] = self._canonical_stock_code(stock_code)

        if "pct_chg" not in normalized.columns and "close" in normalized.columns:
            normalized["pct_chg"] = normalized["close"].pct_change() * 100
            normalized["pct_chg"] = normalized["pct_chg"].fillna(0).round(2)

        keep = ["code", *STANDARD_COLUMNS]
        for col in keep:
            if col not in normalized.columns:
                normalized[col] = 0 if col != "date" else pd.NaT
        out = normalized[keep]

        out.attrs["cache_meta"] = {
            "source": cache_source,
            "fetched_at": (
                "N/A" if cache_source == "fixture"
                else datetime.now(timezone.utc).isoformat()
            ),
            "market": "TW",
            "symbol": f"TW:{self._canonical_stock_code(stock_code)}",
            "provider_version": (
                "fixture" if cache_source == "fixture"
                else importlib.metadata.version("FinMind")
            ),
            "request_range": f"{request_start}/{request_end}",
        }
        return out

    def _read_json_fixture(self, stock_code: str, filename: str) -> Dict[str, Any]:
        fixture_path = self._fixture_dir(stock_code) / filename
        if not fixture_path.exists():
            raise DataFetchError(f"[TaiwanFinMind] fixture not found: {filename}")
        with fixture_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
        return {"data": data}

    def get_chips(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        chips = self._read_json_fixture(stock_code, "chips.json")
        if start_date is not None:
            chips["request_start_date"] = start_date
        if end_date is not None:
            chips["request_end_date"] = end_date
        return chips

# -*- coding: utf-8 -*-
"""
FinMind Dataset Fetcher — registry-driven, guard-aware data access layer.

Wraps FinMindClient with FinMindDatasetRegistry validation:
  - Validates dataset exists in registry (market=TW, params, tier)
  - Rejects CN/A-share datasets
  - Enforces data_id_required
  - Returns deterministic unavailable for backer-tier datasets when not forced
  - Supports feature_group bulk queries
  - Supports fixture mode for offline testing

Result shape matches TaiwanMarketDataFetcher standard (ok/source/dataset/...),
enabling direct drop-in consumption by existing report/review code.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from src.finmind.client import FinMindClient, FinMindResponse, _env_bool
from src.finmind.dataset_registry import FinMindDatasetRegistry

logger = logging.getLogger(__name__)

_CN_MARKETS = frozenset({"CN", "AShare", "SH", "SZ"})


def _make_result(response: FinMindResponse, provider: str = "FinMindDatasetFetcher") -> Dict[str, Any]:
    """Convert FinMindResponse to standard result dict (TaiwanMarketDataFetcher-compatible)."""
    d = response.to_dict()
    d["cache_meta"]["provider"] = provider
    return d


def _unavailable_result(
    dataset: str,
    data_id: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    reason: str,
    error: Optional[str] = None,
    source: str = "finmind",
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
            "provider": "FinMindDatasetFetcher",
            "dataset": dataset,
            "data_id": data_id,
        },
    }


class FinMindDatasetFetcher:
    """
    Registry-driven FinMind data access layer.

    Uses FinMindDatasetRegistry to validate dataset parameters,
    and FinMindClient to execute live or guarded requests.

    Fixture mode: When DSA_FIXTURE_MODE=true, all fetch calls return
    fixture_mode_blocked unless override_fixture is provided.
    No-network mode: When DSA_ALLOW_EXTERNAL_NETWORK=false, returns no_network.
    """

    def __init__(
        self,
        registry: Optional[FinMindDatasetRegistry] = None,
        client: Optional[FinMindClient] = None,
    ) -> None:
        self._registry = registry or FinMindDatasetRegistry()
        self._client = client or FinMindClient()

    # ------------------------------------------------------------------
    # Guards (read from env at call time, not __init__)
    # ------------------------------------------------------------------

    def _fixture_mode(self) -> bool:
        return _env_bool("DSA_FIXTURE_MODE", False)

    def _no_network(self) -> bool:
        return _env_bool("DSA_FIXTURE_MODE", False) or not _env_bool(
            "DSA_ALLOW_EXTERNAL_NETWORK", False
        )

    # ------------------------------------------------------------------
    # Public fetch API
    # ------------------------------------------------------------------

    def fetch(
        self,
        dataset: str,
        *,
        data_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force_live: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch a single dataset by name.

        Args:
            dataset:    FinMind dataset name (must exist in registry).
            data_id:    Stock code or index ID (required when registry says data_id_required=True).
            start_date: ISO date string YYYY-MM-DD.
            end_date:   ISO date string YYYY-MM-DD.
            force_live: If True, attempt live call even for Backer-tier datasets with
                        live_probe disabled. Caller must supply valid Backer token.

        Returns:
            Standard result dict: {ok, source, dataset, data_id, rows, columns,
            row_count, start_date, end_date, error, unavailable_reason, cache_meta}.
        """
        entry = self._registry.get(dataset)
        if entry is None:
            return _unavailable_result(
                dataset, data_id, start_date, end_date,
                reason="unknown_dataset",
                error=f"Dataset '{dataset}' not found in registry",
            )

        # Reject CN/A-share datasets
        market = entry.get("market", "")
        if market in _CN_MARKETS or self._registry.has_cn_datasets():
            return _unavailable_result(
                dataset, data_id, start_date, end_date,
                reason="cn_market_rejected",
                error="CN/A-share datasets are not permitted under Route B",
            )

        # Enforce data_id requirement
        if entry.get("data_id_required") and not data_id:
            return _unavailable_result(
                dataset, data_id, start_date, end_date,
                reason="missing_required_data_id",
                error=f"Dataset '{dataset}' requires data_id",
            )

        # Backer-tier guard: return unavailable unless force_live or live_probe enabled
        tier = entry.get("tier", "unknown")
        probe_enabled = entry.get("live_probe", {}).get("enabled", False)
        if tier in ("backer", "sponsor") and not probe_enabled and not force_live:
            caveats = entry.get("caveats", [])
            caveat_str = "; ".join(caveats[:2]) if caveats else f"requires {tier} tier"
            return _unavailable_result(
                dataset, data_id, start_date, end_date,
                reason=f"tier_{tier}_required",
                error=caveat_str,
            )

        # Delegate to FinMindClient
        rest = entry.get("rest", {})
        endpoint = rest.get("endpoint", "/data")

        response = self._client.get_dataset(
            dataset,
            start_date=start_date,
            end_date=end_date,
            data_id=data_id,
            endpoint=endpoint,
        )
        return _make_result(response)

    def fetch_by_feature_group(
        self,
        feature_group: str,
        *,
        start_date: str,
        end_date: str,
        sample_only: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch all datasets belonging to a feature group.

        Returns dict keyed by dataset name. Datasets requiring data_id
        are skipped in bulk queries (data_id must be supplied per-dataset
        via individual fetch() calls).

        Args:
            feature_group: One of the 7 registered feature groups.
            start_date:    ISO date string YYYY-MM-DD.
            end_date:      ISO date string YYYY-MM-DD.
            sample_only:   If True, return capability description without live calls.

        Returns:
            Dict[dataset_name, result_dict]
        """
        entries = self._registry.by_feature_group(feature_group)
        if not entries:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            name = entry["dataset"]
            if sample_only:
                results[name] = self.describe_capability(name)
                continue

            # Skip datasets that require data_id in bulk mode
            if entry.get("data_id_required"):
                results[name] = _unavailable_result(
                    name, None, start_date, end_date,
                    reason="data_id_required_for_bulk",
                    error="Provide data_id via individual fetch() call",
                )
                continue

            results[name] = self.fetch(
                name,
                start_date=start_date,
                end_date=end_date,
            )
        return results

    def describe_capability(self, dataset: str) -> Dict[str, Any]:
        """
        Return registry entry info for a dataset without making any live call.

        Useful for panel prompt and capability discovery features.
        """
        entry = self._registry.get(dataset)
        if entry is None:
            return {
                "ok": False,
                "dataset": dataset,
                "unavailable_reason": "unknown_dataset",
            }
        return {
            "ok": True,
            "dataset": dataset,
            "market": entry.get("market"),
            "category": entry.get("category"),
            "feature_groups": entry.get("feature_groups", []),
            "tier": entry.get("tier"),
            "live_probe_enabled": entry.get("live_probe", {}).get("enabled", False),
            "data_id_required": entry.get("data_id_required"),
            "columns": entry.get("columns", []),
            "caveats": entry.get("caveats", []),
            "fallback": entry.get("fallback", []),
            "endpoint": entry.get("rest", {}).get("endpoint", "/data"),
            "sdk_method": entry.get("sdk", {}).get("method"),
            "bulk_download_available": entry.get("sdk", {}).get("bulk_download_available", False),
            "source": "registry",
            "row_count": None,
            "unavailable_reason": None,
        }

    def capabilities_summary(self) -> Dict[str, List[str]]:
        """Return feature_group → [dataset names] mapping from registry."""
        return self._registry.capabilities_summary()

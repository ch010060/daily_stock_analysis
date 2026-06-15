# -*- coding: utf-8 -*-
"""
FinMind Dataset Registry — query interface for data/finmind_dataset_registry.json.

Provides dataset capability lookup for Taiwan stock analysis features:
  - latest_info       — news, trading calendar
  - stock_analysis    — price, fundamental, chip
  - backtesting       — adjusted price, PER, revenue, chip
  - strategy_analysis — all of the above plus derivatives
  - market_review     — total index, institutional totals, margin totals
  - dataset_explorer  — metadata lookup
  - panel_prompt      — LLM prompt dataset capability queries
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent / "finmind_dataset_registry.json"

_VALID_FEATURE_GROUPS = frozenset({
    "latest_info",
    "stock_analysis",
    "backtesting",
    "strategy_analysis",
    "market_review",
    "dataset_explorer",
    "panel_prompt",
})

_VALID_CATEGORIES = frozenset({
    "calendar",
    "reference",
    "news",
    "technical",
    "fundamental",
    "chip",
    "market_overview",
    "derivatives",
    "tick",
})

_CN_DATASET_TERMS = frozenset({
    "AShare", "AStock", "China", "CN", "SH", "SZ", "Akshare",
})


class FinMindDatasetRegistry:
    """Load and query the FinMind dataset registry."""

    def __init__(self, registry_path: Optional[Path] = None) -> None:
        self._path = Path(registry_path) if registry_path else _REGISTRY_PATH
        self._raw: Dict[str, Any] = {}
        self._datasets: List[Dict[str, Any]] = []
        self._by_name: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with open(self._path, encoding="utf-8") as f:
            self._raw = json.load(f)
        self._datasets = self._raw.get("datasets", [])
        self._by_name = {d["dataset"]: d for d in self._datasets}
        logger.debug("FinMindDatasetRegistry loaded %d datasets from %s", len(self._datasets), self._path)

    @property
    def version(self) -> str:
        return self._raw.get("version", "unknown")

    @property
    def dataset_names(self) -> List[str]:
        return list(self._by_name.keys())

    @property
    def all_datasets(self) -> List[Dict[str, Any]]:
        return list(self._datasets)

    def get(self, dataset_name: str) -> Optional[Dict[str, Any]]:
        """Return a single dataset entry by exact name, or None."""
        return self._by_name.get(dataset_name)

    def by_feature_group(self, group: str) -> List[Dict[str, Any]]:
        """Return all datasets that belong to a given feature group."""
        return [d for d in self._datasets if group in d.get("feature_groups", [])]

    def by_category(self, category: str) -> List[Dict[str, Any]]:
        """Return all datasets in a given category."""
        return [d for d in self._datasets if d.get("category") == category]

    def by_tier(self, tier: str) -> List[Dict[str, Any]]:
        """Return all datasets matching a given tier (free/sponsor/unknown)."""
        return [d for d in self._datasets if d.get("tier") == tier]

    def probe_enabled(self) -> List[Dict[str, Any]]:
        """Return datasets where live_probe.enabled is True."""
        return [
            d for d in self._datasets
            if d.get("live_probe", {}).get("enabled", False)
        ]

    def for_panel_prompt(self) -> List[Dict[str, Any]]:
        """Return datasets available for panel recommendation / LLM prompt interaction."""
        return self.by_feature_group("panel_prompt")

    def capabilities_summary(self) -> Dict[str, List[str]]:
        """Return a mapping of feature_group → dataset names for capability discovery."""
        result: Dict[str, List[str]] = {}
        for d in self._datasets:
            for fg in d.get("feature_groups", []):
                result.setdefault(fg, []).append(d["dataset"])
        return result

    def has_cn_datasets(self) -> bool:
        """Return True if any dataset name or category contains CN/A-share terms."""
        for d in self._datasets:
            name = d.get("dataset", "")
            cat = d.get("category", "")
            market = d.get("market", "")
            for term in _CN_DATASET_TERMS:
                if term in name or term in cat:
                    return True
            if market == "CN":
                return True
        return False

    def validate(self) -> List[str]:
        """Run structural validation; return list of error strings (empty = OK)."""
        errors: List[str] = []
        seen: set = set()
        for d in self._datasets:
            name = d.get("dataset", "")
            if not name:
                errors.append("Entry missing 'dataset' field")
                continue
            if name in seen:
                errors.append(f"Duplicate dataset: {name}")
            seen.add(name)
            for field in ("market", "category", "feature_groups", "rest", "columns"):
                if field not in d:
                    errors.append(f"{name}: missing field '{field}'")
            rest = d.get("rest", {})
            if "endpoint" not in rest:
                errors.append(f"{name}: rest missing 'endpoint'")
            if "params" not in rest:
                errors.append(f"{name}: rest missing 'params'")
            if not d.get("feature_groups"):
                errors.append(f"{name}: feature_groups is empty")
        return errors

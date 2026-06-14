#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 8A — FinMind Dataset Registry Live Probe Script.

Probes selected FinMind datasets to validate availability, column shape, and row count.
Does NOT dump full payload. Writes results to .runtime-validation/ only.

Usage:
    python scripts/probe_finmind_registry.py [--datasets D1,D2] [--days N] [--dry-run]

Guards (evaluated in order):
    DSA_FIXTURE_MODE=true          → fixture mode; no live calls
    DSA_ALLOW_EXTERNAL_NETWORK=false → no live calls
    FINMIND_ENABLED=false          → no live calls
    FINMIND_API_TOKEN absent       → no live calls
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_DIR = _REPO_ROOT / ".runtime-validation"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _network_allowed() -> bool:
    if _env_bool("DSA_FIXTURE_MODE"):
        logger.info("DSA_FIXTURE_MODE=true — no live calls")
        return False
    if not _env_bool("DSA_ALLOW_EXTERNAL_NETWORK", True):
        logger.info("DSA_ALLOW_EXTERNAL_NETWORK=false — no live calls")
        return False
    if not _env_bool("FINMIND_ENABLED", True):
        logger.info("FINMIND_ENABLED=false — no live calls")
        return False
    token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_TOKEN")
    if not token:
        logger.info("FINMIND_API_TOKEN not set — no live calls")
        return False
    return True


def _get_token() -> str:
    return (os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_TOKEN") or "").strip()


def _probe_dataset(dataset: str, data_id: str | None, start_date: str, end_date: str) -> dict:
    import requests
    base = "https://api.finmindtrade.com/api/v4/data"
    token = _get_token()
    params: dict = {
        "dataset": dataset,
        "start_date": start_date,
        "end_date": end_date,
        "token": token,
    }
    if data_id:
        params["data_id"] = data_id
    try:
        resp = requests.get(base, params=params, timeout=15)
        if resp.status_code == 402:
            return {"dataset": dataset, "data_id": data_id, "status": "quota_exceeded", "row_count": 0, "columns": []}
        payload = resp.json()
        if payload.get("status") != 200:
            return {
                "dataset": dataset,
                "data_id": data_id,
                "status": "api_error",
                "msg": payload.get("msg", ""),
                "row_count": 0,
                "columns": [],
            }
        rows = payload.get("data", [])
        cols = list(rows[0].keys()) if rows else []
        return {
            "dataset": dataset,
            "data_id": data_id,
            "status": "ok",
            "row_count": len(rows),
            "columns": cols[:8],  # first 8 columns only
        }
    except Exception as exc:
        return {"dataset": dataset, "data_id": data_id, "status": "error", "error": str(exc), "row_count": 0, "columns": []}


def _load_registry() -> list:
    reg_path = _REPO_ROOT / "src" / "finmind" / "finmind_dataset_registry.json"
    with open(reg_path, encoding="utf-8") as f:
        return json.load(f)["datasets"]


def main():
    parser = argparse.ArgumentParser(description="FinMind dataset registry probe")
    parser.add_argument("--datasets", default="", help="Comma-separated dataset names to probe (default: probe-enabled ones)")
    parser.add_argument("--days", type=int, default=7, help="Date window in days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be probed without calling API")
    args = parser.parse_args()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    datasets = _load_registry()
    if args.datasets:
        wanted = set(args.datasets.split(","))
        targets = [d for d in datasets if d["dataset"] in wanted]
    else:
        targets = [d for d in datasets if d.get("live_probe", {}).get("enabled")]

    logger.info("Probe targets (%d): %s", len(targets), [d["dataset"] for d in targets])

    if args.dry_run:
        logger.info("--dry-run mode: no live calls")
        return

    if not _network_allowed():
        logger.warning("Network guards active — no live probes executed")
        sys.exit(0)

    results = []
    for entry in targets:
        name = entry["dataset"]
        data_id = entry.get("live_probe", {}).get("sample_data_id")
        logger.info("Probing %s (data_id=%s)...", name, data_id)
        result = _probe_dataset(name, data_id, start_date, end_date)
        results.append(result)
        status = result.get("status")
        row_count = result.get("row_count", 0)
        columns = result.get("columns", [])
        logger.info("  → status=%s row_count=%d columns=%s", status, row_count, columns)

    _RUNTIME_DIR.mkdir(exist_ok=True)
    out_path = _RUNTIME_DIR / f"finmind_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"probed_at": end_date, "results": results}, f, ensure_ascii=False, indent=2)
    logger.info("Probe results written to %s (not committed)", out_path)

    failed = [r for r in results if r["status"] != "ok"]
    if failed:
        logger.warning("Probe failures: %s", [r["dataset"] for r in failed])
    else:
        logger.info("All probes OK")


if __name__ == "__main__":
    main()

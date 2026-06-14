# -*- coding: utf-8 -*-
"""
FinMind REST client — generic, token-safe, guard-aware.

Provides FinMindClient for calling the FinMind API v4 /data endpoint
(and custom endpoints for special datasets).

Network guards (evaluated in order):
  DSA_FIXTURE_MODE=true           → no-network; return fixture_mode_blocked
  DSA_ALLOW_EXTERNAL_NETWORK=false → no-network; return network_blocked
  FINMIND_API_TOKEN absent        → unauthenticated; free-tier only

Token safety:
  - Token is never logged.
  - Token presence is recorded as boolean only.
  - Authorization header is set only if token is non-empty.

Error classification (unavailable_reason):
  no_network           — guard blocked request before HTTP call
  fixture_mode_blocked — DSA_FIXTURE_MODE=true
  tier_or_permission   — HTTP 402 or FinMind API msg "register"/"level"
  rate_limited         — HTTP 429 or FinMind API msg "rate"/"quota"
  provider_error       — HTTP 5xx
  http_error           — other non-200 HTTP status
  api_error            — HTTP 200 but FinMind status != 200
  json_parse_error     — HTTP 200 but response is not valid JSON
  network_exception    — requests raised an exception
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_FINMIND_BASE_URL = "https://api.finmindtrade.com/api/v4"
_DEFAULT_TIMEOUT = 30

_TIER_KEYWORDS = frozenset({"register", "level", "sponsor", "backer", "upgrade"})
_RATE_KEYWORDS = frozenset({"rate", "quota", "limit", "too many"})


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _classify_api_msg(msg: str) -> str:
    msg_lower = msg.lower()
    for kw in _TIER_KEYWORDS:
        if kw in msg_lower:
            return "tier_or_permission"
    for kw in _RATE_KEYWORDS:
        if kw in msg_lower:
            return "rate_limited"
    return "api_error"


@dataclass
class FinMindResponse:
    """Result from a single FinMind API call."""

    ok: bool
    dataset: str
    data_id: Optional[str]
    rows: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    start_date: Optional[str]
    end_date: Optional[str]
    http_status: Optional[int]
    api_status: Optional[int]
    api_msg: Optional[str]
    error: Optional[str]
    unavailable_reason: Optional[str]
    source: str = "finmind"
    token_used: bool = False
    cache_meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return result as a plain dict matching the standard result shape."""
        return {
            "ok": self.ok,
            "source": self.source,
            "dataset": self.dataset,
            "data_id": self.data_id,
            "rows": self.rows,
            "columns": self.columns,
            "row_count": self.row_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "error": self.error,
            "unavailable_reason": self.unavailable_reason,
            "cache_meta": self.cache_meta,
        }


def _make_response(
    *,
    ok: bool,
    dataset: str,
    data_id: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    rows: Optional[List[Dict[str, Any]]] = None,
    http_status: Optional[int] = None,
    api_status: Optional[int] = None,
    api_msg: Optional[str] = None,
    error: Optional[str] = None,
    unavailable_reason: Optional[str] = None,
    source: str = "finmind",
    token_used: bool = False,
) -> FinMindResponse:
    rows = rows or []
    columns = list(rows[0].keys()) if rows else []
    return FinMindResponse(
        ok=ok,
        dataset=dataset,
        data_id=data_id,
        rows=rows,
        columns=columns,
        row_count=len(rows),
        start_date=start_date,
        end_date=end_date,
        http_status=http_status,
        api_status=api_status,
        api_msg=api_msg,
        error=error,
        unavailable_reason=unavailable_reason,
        source=source,
        token_used=token_used,
        cache_meta={
            "source": source,
            "provider": "FinMindClient",
            "dataset": dataset,
            "data_id": data_id,
            "token_used": token_used,
        },
    )


class FinMindClient:
    """
    Generic, token-safe FinMind REST API client.

    Respects DSA_FIXTURE_MODE and DSA_ALLOW_EXTERNAL_NETWORK guards.
    Never logs the token value — only logs token_used boolean.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = _FINMIND_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
        session: Any = None,
    ) -> None:
        self._explicit_token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = session  # requests.Session or compatible mock

    # ------------------------------------------------------------------
    # Guards (evaluated per call, not at __init__, so env overrides work)
    # ------------------------------------------------------------------

    def _fixture_mode(self) -> bool:
        return _env_bool("DSA_FIXTURE_MODE", False)

    def _network_allowed(self) -> bool:
        return _env_bool("DSA_ALLOW_EXTERNAL_NETWORK", False)

    def _no_network(self) -> bool:
        return self._fixture_mode() or not self._network_allowed()

    def _get_token(self) -> str:
        if self._explicit_token is not None:
            return self._explicit_token
        return (
            os.getenv("FINMIND_API_TOKEN", "").strip()
            or os.getenv("FINMIND_TOKEN", "").strip()
        )

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _http_get(
        self, url: str, params: Dict[str, str], headers: Dict[str, str]
    ) -> Any:
        """Execute HTTP GET. Returns requests.Response or compatible mock."""
        if self._session is not None:
            return self._session.get(url, params=params, headers=headers, timeout=self._timeout)
        import requests
        return requests.get(url, params=params, headers=headers, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_dataset(
        self,
        dataset: str,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        data_id: Optional[str] = None,
        endpoint: str = "/data",
        extra_params: Optional[Dict[str, str]] = None,
    ) -> FinMindResponse:
        """
        Call FinMind REST API for a dataset.

        Args:
            dataset:      FinMind dataset name.
            start_date:   ISO date string (YYYY-MM-DD); omit for datasets that don't use it.
            end_date:     ISO date string (YYYY-MM-DD).
            data_id:      stock_id / index_id (None for market-wide datasets).
            endpoint:     REST endpoint path, default "/data"; override for special datasets.
            extra_params: Additional query params merged last.

        Returns:
            FinMindResponse with ok=True on success, ok=False on any error.
        """
        kw = dict(
            dataset=dataset,
            data_id=data_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Guard 1: fixture mode
        if self._fixture_mode():
            logger.debug("[FinMindClient] fixture_mode — no live call for %s", dataset)
            return _make_response(
                ok=False, unavailable_reason="fixture_mode_blocked",
                source="finmind", **kw,
            )

        # Guard 2: network flag
        if not self._network_allowed():
            logger.debug("[FinMindClient] network_blocked — no live call for %s", dataset)
            return _make_response(
                ok=False, unavailable_reason="no_network",
                source="finmind", **kw,
            )

        token = self._get_token()
        token_used = bool(token)
        headers: Dict[str, str] = {}
        if token_used:
            headers["Authorization"] = f"Bearer {token}"

        params: Dict[str, str] = {"dataset": dataset}
        if data_id is not None:
            params["data_id"] = str(data_id)
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if extra_params:
            params.update(extra_params)
        if token_used:
            params["token"] = token  # FinMind also accepts token in params

        url = self._base_url + endpoint

        try:
            resp = self._http_get(url, params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FinMindClient] network exception dataset=%s: %s", dataset, type(exc).__name__)
            return _make_response(
                ok=False,
                unavailable_reason="network_exception",
                error=type(exc).__name__,
                token_used=token_used,
                **kw,
            )

        http_status = resp.status_code

        if http_status == 402:
            logger.warning("[FinMindClient] HTTP 402 dataset=%s token_used=%s", dataset, token_used)
            return _make_response(
                ok=False,
                http_status=402,
                unavailable_reason="tier_or_permission",
                error="HTTP 402",
                token_used=token_used,
                **kw,
            )

        if http_status == 429:
            logger.warning("[FinMindClient] HTTP 429 rate_limited dataset=%s", dataset)
            return _make_response(
                ok=False,
                http_status=429,
                unavailable_reason="rate_limited",
                error="HTTP 429",
                token_used=token_used,
                **kw,
            )

        if http_status >= 500:
            logger.warning("[FinMindClient] HTTP %d provider_error dataset=%s", http_status, dataset)
            return _make_response(
                ok=False,
                http_status=http_status,
                unavailable_reason="provider_error",
                error=f"HTTP {http_status}",
                token_used=token_used,
                **kw,
            )

        if http_status != 200:
            logger.warning("[FinMindClient] HTTP %d dataset=%s", http_status, dataset)
            return _make_response(
                ok=False,
                http_status=http_status,
                unavailable_reason="http_error",
                error=f"HTTP {http_status}",
                token_used=token_used,
                **kw,
            )

        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FinMindClient] JSON parse error dataset=%s: %s", dataset, type(exc).__name__)
            return _make_response(
                ok=False,
                http_status=200,
                unavailable_reason="json_parse_error",
                error=type(exc).__name__,
                token_used=token_used,
                **kw,
            )

        api_status = payload.get("status")
        api_msg = str(payload.get("msg", ""))

        if api_status != 200:
            reason = _classify_api_msg(api_msg)
            logger.warning(
                "[FinMindClient] api_status=%s reason=%s dataset=%s msg=%s",
                api_status, reason, dataset, api_msg[:120],
            )
            return _make_response(
                ok=False,
                http_status=200,
                api_status=api_status,
                api_msg=api_msg,
                unavailable_reason=reason,
                error=api_msg[:200] if api_msg else None,
                token_used=token_used,
                **kw,
            )

        rows: List[Dict[str, Any]] = payload.get("data") or []
        logger.debug("[FinMindClient] ok dataset=%s rows=%d token_used=%s", dataset, len(rows), token_used)
        return _make_response(
            ok=True,
            http_status=200,
            api_status=200,
            api_msg=api_msg,
            rows=rows,
            token_used=token_used,
            **kw,
        )

    def probe_dataset(
        self,
        registry_entry: Dict[str, Any],
        start_date: str,
        end_date: str,
    ) -> FinMindResponse:
        """
        Probe a single dataset using its registry entry.

        Derives endpoint and params from registry_entry['rest'].
        Uses live_probe.sample_data_id if present.
        """
        dataset = registry_entry["dataset"]
        rest = registry_entry.get("rest", {})
        endpoint = rest.get("endpoint", "/data")
        data_id = registry_entry.get("live_probe", {}).get("sample_data_id")
        rest_params = rest.get("params", [])

        # For datasets using 'date' instead of start_date/end_date
        extra_params: Dict[str, str] = {}
        if "date" in rest_params and "start_date" not in rest_params:
            extra_params["date"] = end_date
            return self.get_dataset(
                dataset, data_id=data_id, endpoint=endpoint, extra_params=extra_params,
            )

        return self.get_dataset(
            dataset,
            start_date=start_date,
            end_date=end_date,
            data_id=data_id,
            endpoint=endpoint,
        )

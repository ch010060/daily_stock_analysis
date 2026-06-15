# -*- coding: utf-8 -*-
"""
Tests for FinMindClient (Phase 8B).

All tests are offline — HTTP calls are mocked via a fake session.
No live provider calls, no token printed, no full payload dumped.
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.finmind.client import FinMindClient, FinMindResponse

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "finmind"


def _load_fixture(name: str) -> dict:
    with open(_FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _mock_resp(status_code: int, body: dict) -> MagicMock:
    """Create a mock requests.Response."""
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = body
    return m


def _mock_resp_json_error(status_code: int = 200) -> MagicMock:
    """Create a mock response whose .json() raises ValueError."""
    m = MagicMock()
    m.status_code = status_code
    m.json.side_effect = ValueError("not valid JSON")
    return m


def _client_with_mock_session(response_mock, token: str = "test_token") -> FinMindClient:
    """Build FinMindClient with a fake session returning response_mock."""
    session = MagicMock()
    session.get.return_value = response_mock
    return FinMindClient(token=token, session=session)


class TestGetDatasetParams(unittest.TestCase):
    """Test 1: get_dataset sends correct /data params."""

    def _make_client(self, body):
        resp = _mock_resp(200, body)
        return _client_with_mock_session(resp)

    def test_params_include_dataset_name(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = self._make_client(body)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        call_kwargs = client._session.get.call_args
        params = call_kwargs[1]["params"]
        self.assertEqual(params["dataset"], "TaiwanStockPrice")

    def test_params_include_data_id(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = self._make_client(body)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        params = client._session.get.call_args[1]["params"]
        self.assertEqual(params["data_id"], "2330")

    def test_params_include_date_range(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = self._make_client(body)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        params = client._session.get.call_args[1]["params"]
        self.assertEqual(params["start_date"], "2026-06-01")
        self.assertEqual(params["end_date"], "2026-06-14")

    def test_endpoint_default_is_data(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = self._make_client(body)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        url = client._session.get.call_args[0][0]
        self.assertTrue(url.endswith("/data"))


class TestAuthorizationHeader(unittest.TestCase):
    """Test 2: Authorization header used when token exists; token never in result/log."""

    def test_auth_header_present_when_token_set(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = _client_with_mock_session(_mock_resp(200, body), token="secret_token")
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        headers = client._session.get.call_args[1]["headers"]
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_token_not_in_result_dict(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = _client_with_mock_session(_mock_resp(200, body), token="secret_token")
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        result_str = str(resp.to_dict())
        self.assertNotIn("secret_token", result_str)

    def test_token_not_in_response_object_except_bool(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = _client_with_mock_session(_mock_resp(200, body), token="secret_token")
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertTrue(resp.token_used)  # boolean only
        self.assertNotIn("secret_token", str(resp))


class TestNoTokenMode(unittest.TestCase):
    """Test 3: Missing token still works as unauthenticated mode."""

    def test_no_auth_header_without_token(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        session = MagicMock()
        session.get.return_value = _mock_resp(200, body)
        client = FinMindClient(token="", session=session)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false",
                                      "FINMIND_API_TOKEN": "", "FINMIND_TOKEN": ""}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        headers = session.get.call_args[1]["headers"]
        self.assertNotIn("Authorization", headers)
        self.assertFalse(resp.token_used)


class TestSuccessWithRows(unittest.TestCase):
    """Test 4: HTTP 200 + success + rows -> ok=True."""

    def test_ok_true_with_rows(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = _client_with_mock_session(_mock_resp(200, body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertTrue(resp.ok)
        self.assertEqual(resp.dataset, "TaiwanStockPrice")
        self.assertEqual(resp.row_count, 3)
        self.assertIn("close", resp.columns)
        self.assertIsNone(resp.unavailable_reason)

    def test_result_dict_shape(self):
        body = _load_fixture("client_success_taiwan_stock_price.json")
        client = _client_with_mock_session(_mock_resp(200, body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        d = resp.to_dict()
        for key in ("ok", "source", "dataset", "data_id", "rows", "columns",
                    "row_count", "start_date", "end_date", "error", "unavailable_reason", "cache_meta"):
            self.assertIn(key, d, f"Missing key: {key}")


class TestEmptySuccess(unittest.TestCase):
    """Test 5: HTTP 200 + empty rows -> ok=True but row_count=0."""

    def test_ok_true_empty_rows(self):
        body = _load_fixture("client_empty_success.json")
        client = _client_with_mock_session(_mock_resp(200, body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockMonthRevenue", start_date="2026-06-10", end_date="2026-06-14", data_id="2330")
        self.assertTrue(resp.ok)
        self.assertEqual(resp.row_count, 0)
        self.assertEqual(resp.rows, [])
        self.assertEqual(resp.columns, [])


class TestHTTP400(unittest.TestCase):
    """Test 6: HTTP 400 -> ok=False unavailable."""

    def test_http_400_returns_http_error(self):
        body = {"status": 400, "msg": "bad request", "data": []}
        client = _client_with_mock_session(_mock_resp(400, body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "http_error")


class TestHTTP402(unittest.TestCase):
    """Test 7: HTTP 402 -> ok=False tier_or_permission."""

    def test_http_402_returns_tier_or_permission(self):
        client = _client_with_mock_session(_mock_resp(402, {}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPriceAdj", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "tier_or_permission")
        self.assertEqual(resp.http_status, 402)


class TestHTTP429(unittest.TestCase):
    """Test 8: HTTP 429 -> ok=False rate_limited."""

    def test_http_429_returns_rate_limited(self):
        client = _client_with_mock_session(_mock_resp(429, {}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "rate_limited")
        self.assertEqual(resp.http_status, 429)


class TestHTTP500(unittest.TestCase):
    """Test 9: HTTP 500 -> ok=False provider_error."""

    def test_http_500_returns_provider_error(self):
        client = _client_with_mock_session(_mock_resp(500, {}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "provider_error")

    def test_http_503_returns_provider_error(self):
        client = _client_with_mock_session(_mock_resp(503, {}))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "provider_error")


class TestJSONParseError(unittest.TestCase):
    """Test 10: JSON parse error -> ok=False."""

    def test_json_error_returns_parse_error(self):
        session = MagicMock()
        session.get.return_value = _mock_resp_json_error(200)
        client = FinMindClient(token="test_token", session=session)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "json_parse_error")


class TestNetworkException(unittest.TestCase):
    """Test 11: Network exception -> ok=False."""

    def test_connection_error_returns_network_exception(self):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError("refused")
        client = FinMindClient(token="test_token", session=session)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "network_exception")

    def test_timeout_returns_network_exception(self):
        import requests
        session = MagicMock()
        session.get.side_effect = requests.exceptions.Timeout("timed out")
        client = FinMindClient(token="test_token", session=session)
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "network_exception")


class TestNoNetworkGuard(unittest.TestCase):
    """Test 12: No-network guard prevents requests.get call."""

    def test_fixture_mode_blocks_request(self):
        session = MagicMock()
        client = FinMindClient(token="test_token", session=session)
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "true", "DSA_ALLOW_EXTERNAL_NETWORK": "true"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        session.get.assert_not_called()
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "fixture_mode_blocked")

    def test_network_disabled_blocks_request(self):
        session = MagicMock()
        client = FinMindClient(token="test_token", session=session)
        with patch.dict(os.environ, {"DSA_FIXTURE_MODE": "false", "DSA_ALLOW_EXTERNAL_NETWORK": "false"}):
            resp = client.get_dataset("TaiwanStockPrice", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        session.get.assert_not_called()
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "no_network")

    def test_api_error_tier_classified_correctly(self):
        body = _load_fixture("client_error_tier.json")
        client = _client_with_mock_session(_mock_resp(200, body))
        with patch.dict(os.environ, {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"}):
            resp = client.get_dataset("TaiwanStockPriceAdj", start_date="2026-06-01", end_date="2026-06-14", data_id="2330")
        self.assertFalse(resp.ok)
        self.assertEqual(resp.unavailable_reason, "tier_or_permission")


if __name__ == "__main__":
    unittest.main()

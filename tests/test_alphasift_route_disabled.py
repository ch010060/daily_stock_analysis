"""Route-level safety tests for the optional AlphaSift API."""

import importlib
import os
import sys
import unittest
from unittest.mock import patch
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


ALPHASIFT_PREFIX = "/api/v1/alphasift"


class AlphaSiftRouteDisabledTestCase(unittest.TestCase):
    @staticmethod
    def _route_paths(routes: Any) -> set[str]:
        collected: set[str] = set()
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                collected.add(path)

            nested_prefix = path.rstrip("/") if isinstance(path, str) and path not in {"", "/"} else ""

            nested_routes = getattr(route, "routes", None)
            if isinstance(nested_routes, list):
                if nested_prefix:
                    for nested_path in AlphaSiftRouteDisabledTestCase._route_paths(nested_routes):
                        if nested_path == "/":
                            collected.add(nested_prefix)
                        elif nested_path.startswith("/"):
                            collected.add(f"{nested_prefix}{nested_path}")
                        else:
                            collected.add(f"{nested_prefix}/{nested_path}")
                else:
                    collected.update(AlphaSiftRouteDisabledTestCase._route_paths(nested_routes))

            nested_app = getattr(route, "app", None)
            nested_app_routes = getattr(nested_app, "routes", None)
            if isinstance(nested_app_routes, list):
                if nested_prefix:
                    for nested_path in AlphaSiftRouteDisabledTestCase._route_paths(nested_app_routes):
                        if nested_path == "/":
                            collected.add(nested_prefix)
                        elif nested_path.startswith("/"):
                            collected.add(f"{nested_prefix}{nested_path}")
                        else:
                            collected.add(f"{nested_prefix}/{nested_path}")
                else:
                    collected.update(AlphaSiftRouteDisabledTestCase._route_paths(nested_app_routes))

        return collected

    @staticmethod
    def _router_paths(app) -> set[str]:
        return {
            r.path for r in app.router.routes
            if hasattr(r, "path") and isinstance(r.path, str)
        }

    def tearDown(self) -> None:
        os.environ.pop("ALPHASIFT_ROUTE_ENABLED", None)
        module = sys.modules.get("api.v1.router")
        if module is not None:
            importlib.reload(module)

    def _app_with_route_flag(self, value: str | None = None) -> FastAPI:
        if value is None:
            os.environ.pop("ALPHASIFT_ROUTE_ENABLED", None)
        else:
            os.environ["ALPHASIFT_ROUTE_ENABLED"] = value

        module = importlib.import_module("api.v1.router")
        router_module = importlib.reload(module)
        app = FastAPI()
        app.include_router(router_module.router)
        return app

    def test_default_route_list_excludes_alphasift(self) -> None:
        app = self._app_with_route_flag(None)

        paths = self._router_paths(app)

        self.assertFalse(
            any(path.startswith(ALPHASIFT_PREFIX) for path in paths),
            paths,
        )

    def test_default_status_route_returns_404(self) -> None:
        client = TestClient(self._app_with_route_flag(None))

        response = client.get(f"{ALPHASIFT_PREFIX}/status")

        self.assertEqual(404, response.status_code)

    def test_default_strategies_route_returns_404(self) -> None:
        client = TestClient(self._app_with_route_flag(None))

        response = client.get(f"{ALPHASIFT_PREFIX}/strategies")

        self.assertEqual(404, response.status_code)

    def test_default_install_route_returns_404(self) -> None:
        client = TestClient(self._app_with_route_flag(None))

        response = client.post(f"{ALPHASIFT_PREFIX}/install")

        self.assertEqual(404, response.status_code)

    def test_default_screen_route_returns_404(self) -> None:
        client = TestClient(self._app_with_route_flag(None))

        response = client.post(
            f"{ALPHASIFT_PREFIX}/screen",
            json={"strategy": "dual_low", "market": "cn", "max_results": 5},
        )

        self.assertEqual(404, response.status_code)

    def test_disabled_routes_do_not_trigger_alphasift_internals(self) -> None:
        app = self._app_with_route_flag(None)
        client = TestClient(app)

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("AlphaSift internals must not run when route is disabled")

        with patch(
            "api.v1.endpoints.alphasift._import_alphasift",
            side_effect=fail_if_called,
        ) as import_alphasift, patch(
            "api.v1.endpoints.alphasift._install_alphasift",
            side_effect=fail_if_called,
        ) as install_alphasift, patch(
            "api.v1.endpoints.alphasift._call_alphasift_screen",
            side_effect=fail_if_called,
        ) as call_screen:
            responses = [
                client.get(f"{ALPHASIFT_PREFIX}/status"),
                client.get(f"{ALPHASIFT_PREFIX}/strategies"),
                client.post(f"{ALPHASIFT_PREFIX}/install"),
                client.post(
                    f"{ALPHASIFT_PREFIX}/screen",
                    json={"strategy": "dual_low", "market": "cn", "max_results": 5},
                ),
            ]

        self.assertEqual([404, 404, 404, 404], [response.status_code for response in responses])
        import_alphasift.assert_not_called()
        install_alphasift.assert_not_called()
        call_screen.assert_not_called()

    def test_explicit_route_flag_registers_alphasift_routes(self) -> None:
        app = self._app_with_route_flag("true")

        paths = self._router_paths(app)

        self.assertIn(f"{ALPHASIFT_PREFIX}/status", paths)
        self.assertIn(f"{ALPHASIFT_PREFIX}/screen", paths)


if __name__ == "__main__":
    unittest.main()

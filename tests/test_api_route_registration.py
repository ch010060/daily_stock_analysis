"""Regression test: API route registration must not raise FastAPIError on import.

Guards against empty-path route shapes that FastAPI rejects when a router
is mounted with a non-empty prefix (e.g. /history prefix + "" path).
"""

import importlib
import sys
import unittest
from typing import Any


class TestApiRouteRegistration(unittest.TestCase):
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
                    for nested_path in TestApiRouteRegistration._route_paths(nested_routes):
                        if nested_path == "/":
                            collected.add(nested_prefix)
                        elif nested_path.startswith("/"):
                            collected.add(f"{nested_prefix}{nested_path}")
                        else:
                            collected.add(f"{nested_prefix}/{nested_path}")
                else:
                    collected.update(TestApiRouteRegistration._route_paths(nested_routes))

            nested_app = getattr(route, "app", None)
            nested_app_routes = getattr(nested_app, "routes", None)
            if isinstance(nested_app_routes, list):
                if nested_prefix:
                    for nested_path in TestApiRouteRegistration._route_paths(nested_app_routes):
                        if nested_path == "/":
                            collected.add(nested_prefix)
                        elif nested_path.startswith("/"):
                            collected.add(f"{nested_prefix}{nested_path}")
                        else:
                            collected.add(f"{nested_prefix}/{nested_path}")
                else:
                    collected.update(TestApiRouteRegistration._route_paths(nested_app_routes))

        return collected

    def setUp(self):
        # Evict cached api modules so each test starts clean.
        for mod in list(sys.modules):
            if mod.startswith("api.") or mod == "api":
                sys.modules.pop(mod, None)

    def test_server_app_imports_without_fastapi_error(self):
        # This must not raise fastapi.exceptions.FastAPIError.
        from api.app import create_app
        app = create_app()
        self.assertIsNotNone(app)

    def test_history_list_route_registered_with_trailing_slash(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.router.routes if hasattr(r, "path")}
        self.assertIn("/api/v1/history/", paths,
                      "History list route /api/v1/history/ must be registered")

    def test_no_empty_path_in_registered_routes(self):
        from api.app import create_app
        app = create_app()
        empty_paths = [
            route.path for route in app.routes
            if getattr(route, "path", None) == ""
        ]
        self.assertEqual(
            empty_paths, [],
            f"No route should have an empty path string; found: {empty_paths}"
        )

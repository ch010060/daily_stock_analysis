import asyncio
import builtins
import sys
import types
import unittest

from src.services.report_pdf_service import (
    ReportPdfUnavailable,
    build_print_url,
    content_disposition_for_pdf,
    generate_pdf_from_print_route,
    playwright_cookies_from_request,
    sanitize_pdf_filename,
)


class ReportPdfServiceTest(unittest.TestCase):
    def test_sanitize_pdf_filename_keeps_tw_name_and_removes_unsafe_chars(self) -> None:
        filename = sanitize_pdf_filename(
            history_id=74,
            stock_code="006208/TW",
            stock_name="富邦台50:*?",
            created_at="2026-06-28T12:00:00",
        )

        self.assertEqual(filename, "006208_TW_富邦台50_report_2026-06-28.pdf")

    def test_content_disposition_includes_attachment_and_utf8_filename(self) -> None:
        header = content_disposition_for_pdf("006208_富邦台50_report_2026-06-28.pdf")

        self.assertIn("attachment", header)
        self.assertIn("filename=", header)
        self.assertIn("filename*=UTF-8''", header)
        self.assertIn("%E5%AF%8C%E9%82%A6", header)

    def test_build_print_url_targets_pdf_mode(self) -> None:
        self.assertEqual(
            build_print_url("http://testserver/api/v1/", 74),
            "http://testserver/api/v1/reports/74/print?pdf=1",
        )
        self.assertEqual(
            build_print_url("http://testserver/", 74),
            "http://testserver/reports/74/print?pdf=1",
        )

    def test_playwright_cookie_conversion_uses_request_origin(self) -> None:
        self.assertEqual(
            playwright_cookies_from_request("http://testserver/", {"session": "abc"}),
            [{"name": "session", "value": "abc", "url": "http://testserver"}],
        )

    def test_generate_pdf_reports_unavailable_without_playwright(self) -> None:
        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "playwright.async_api":
                raise ModuleNotFoundError(name)
            return original_import(name, *args, **kwargs)

        builtins.__import__ = blocked_import
        try:
            with self.assertRaises(ReportPdfUnavailable):
                asyncio.run(generate_pdf_from_print_route("http://testserver/reports/1/print?pdf=1"))
        finally:
            builtins.__import__ = original_import

    def test_generate_pdf_closes_browser_context_on_success(self) -> None:
        closed: list[str] = []

        class FakePage:
            def set_default_timeout(self, _timeout: int) -> None:
                pass

            async def goto(self, *_args, **_kwargs) -> None:
                pass

            async def wait_for_selector(self, *_args, **_kwargs) -> None:
                pass

            async def pdf(self, **_kwargs) -> bytes:
                return b"%PDF fake"

        class FakeContext:
            async def add_cookies(self, _cookies) -> None:
                pass

            async def new_page(self) -> FakePage:
                return FakePage()

            async def close(self) -> None:
                closed.append("context")

        class FakeBrowser:
            async def new_context(self) -> FakeContext:
                return FakeContext()

            async def close(self) -> None:
                closed.append("browser")

        class FakeChromium:
            async def launch(self) -> FakeBrowser:
                return FakeBrowser()

        class FakePlaywrightContext:
            async def __aenter__(self):
                return types.SimpleNamespace(chromium=FakeChromium())

            async def __aexit__(self, *_args) -> None:
                pass

        old_playwright = sys.modules.get("playwright")
        old_async_api = sys.modules.get("playwright.async_api")
        async_api = types.ModuleType("playwright.async_api")
        async_api.async_playwright = lambda: FakePlaywrightContext()
        sys.modules["playwright"] = types.ModuleType("playwright")
        sys.modules["playwright.async_api"] = async_api
        try:
            pdf = asyncio.run(generate_pdf_from_print_route("http://testserver/reports/1/print?pdf=1"))
        finally:
            if old_playwright is None:
                sys.modules.pop("playwright", None)
            else:
                sys.modules["playwright"] = old_playwright
            if old_async_api is None:
                sys.modules.pop("playwright.async_api", None)
            else:
                sys.modules["playwright.async_api"] = old_async_api

        self.assertEqual(pdf, b"%PDF fake")
        self.assertEqual(closed, ["context", "browser"])

    def test_generate_pdf_ignores_cleanup_error_after_success(self) -> None:
        closed: list[str] = []

        class FakePage:
            def set_default_timeout(self, _timeout: int) -> None:
                pass

            async def goto(self, *_args, **_kwargs) -> None:
                pass

            async def wait_for_selector(self, *_args, **_kwargs) -> None:
                pass

            async def pdf(self, **_kwargs) -> bytes:
                return b"%PDF fake"

        class FakeContext:
            async def add_cookies(self, _cookies) -> None:
                pass

            async def new_page(self) -> FakePage:
                return FakePage()

            async def close(self) -> None:
                closed.append("context")
                raise RuntimeError("already closed")

        class FakeBrowser:
            async def new_context(self) -> FakeContext:
                return FakeContext()

            async def close(self) -> None:
                closed.append("browser")

        class FakeChromium:
            async def launch(self) -> FakeBrowser:
                return FakeBrowser()

        class FakePlaywrightContext:
            async def __aenter__(self):
                return types.SimpleNamespace(chromium=FakeChromium())

            async def __aexit__(self, *_args) -> None:
                pass

        old_playwright = sys.modules.get("playwright")
        old_async_api = sys.modules.get("playwright.async_api")
        async_api = types.ModuleType("playwright.async_api")
        async_api.async_playwright = lambda: FakePlaywrightContext()
        sys.modules["playwright"] = types.ModuleType("playwright")
        sys.modules["playwright.async_api"] = async_api
        try:
            pdf = asyncio.run(generate_pdf_from_print_route("http://testserver/reports/1/print?pdf=1"))
        finally:
            if old_playwright is None:
                sys.modules.pop("playwright", None)
            else:
                sys.modules["playwright"] = old_playwright
            if old_async_api is None:
                sys.modules.pop("playwright.async_api", None)
            else:
                sys.modules["playwright.async_api"] = old_async_api

        self.assertEqual(pdf, b"%PDF fake")
        self.assertEqual(closed, ["context", "browser"])


if __name__ == "__main__":
    unittest.main()

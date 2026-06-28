# -*- coding: utf-8 -*-
"""Server-side PDF generation helpers for persisted analysis reports."""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
from typing import Iterable
from urllib.parse import quote, urljoin


class ReportPdfError(RuntimeError):
    """Base class for controlled report PDF generation failures."""


class ReportPdfUnavailable(ReportPdfError):
    """Raised when the browser/PDF runtime is unavailable."""


_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')
_WHITESPACE = re.compile(r"\s+")


def _safe_filename_part(value: object) -> str:
    text = str(value or "").strip()
    text = _UNSAFE_FILENAME_CHARS.sub("_", text)
    text = _WHITESPACE.sub("_", text)
    return text.strip("._- ")


def _format_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def sanitize_pdf_filename(
    *,
    history_id: int,
    stock_code: object = None,
    stock_name: object = None,
    created_at: object = None,
) -> str:
    """Build a safe, human-readable PDF filename."""

    report_date = _format_date(created_at)
    parts = [
        _safe_filename_part(stock_code),
        _safe_filename_part(stock_name),
        "report",
        _safe_filename_part(report_date),
    ]
    stem = "_".join(part for part in parts if part)
    if stem in {"", "report"}:
        stem = f"analysis_report_{history_id}"
    if len(stem) > 140:
        stem = stem[:140].rstrip("._- ")
    return f"{stem}.pdf"


def content_disposition_for_pdf(filename: str) -> str:
    """Return a standards-friendly attachment header for unicode filenames."""

    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii")
    ascii_fallback = _safe_filename_part(ascii_fallback) or "analysis_report.pdf"
    if not ascii_fallback.endswith(".pdf"):
        ascii_fallback = f"{ascii_fallback}.pdf"
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )


def build_print_url(base_url: str, history_id: int) -> str:
    """Build the SPA print route URL used as the PDF rendering target."""

    return urljoin(str(base_url).rstrip("/") + "/", f"reports/{history_id}/print?pdf=1")


def playwright_cookies_from_request(base_url: str, cookies: dict[str, str]) -> list[dict[str, str]]:
    """Convert FastAPI request cookies into Playwright cookie params."""

    root_url = str(base_url).rstrip("/") or "http://localhost"
    return [
        {"name": name, "value": value, "url": root_url}
        for name, value in cookies.items()
    ]


async def generate_pdf_from_print_route(
    print_url: str,
    *,
    cookies: Iterable[dict[str, str]] | None = None,
    page_load_timeout_ms: int = 30_000,
    pdf_timeout_seconds: int = 60,
) -> bytes:
    """Render the print route to PDF using Playwright when available."""

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime
        raise ReportPdfUnavailable("PDF 產生服務目前不可用。") from exc

    async def close_safely(resource: object | None) -> None:
        if resource is None:
            return
        try:
            await resource.close()
        except Exception:
            # Playwright can report TargetClosedError during cleanup if the
            # browser/context was already closed after PDF generation. Cleanup
            # failures must not turn a successfully rendered PDF into HTTP 500.
            return

    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context()
            cookie_list = list(cookies or [])
            if cookie_list:
                await context.add_cookies(cookie_list)
            page = await context.new_page()
            page.set_default_timeout(page_load_timeout_ms)
            await page.goto(print_url, wait_until="networkidle", timeout=page_load_timeout_ms)
            await page.wait_for_selector(
                '[data-testid="report-print-page"][data-print-ready="true"]',
                timeout=page_load_timeout_ms,
            )
            return await asyncio.wait_for(
                page.pdf(
                    format="A4",
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={
                        "top": "10mm",
                        "right": "10mm",
                        "bottom": "10mm",
                        "left": "10mm",
                    },
                ),
                timeout=pdf_timeout_seconds,
            )
    except ReportPdfError:
        raise
    except Exception as exc:  # pragma: no cover - browser runtime specific
        raise ReportPdfError("PDF 產生失敗，請稍後再試。") from exc
    finally:
        await close_safely(context)
        await close_safely(browser)

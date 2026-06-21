# -*- coding: utf-8 -*-
"""
===================================
FastAPI 應用工廠模組
===================================

職責：
1. 建立和配置 FastAPI 應用例項
2. 配置 CORS 中介軟體
3. 註冊路由和異常處理器
4. 託管前端靜態檔案（生產模式）

使用方式：
    from api.app import create_app
    app = create_app()
"""

import asyncio
import logging
import mimetypes
import os
import re
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

LOCAL_SERVER_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
STARLETTE_TEST_HOST = "testserver"
BIND_ALL_HOSTS = frozenset({"0.0.0.0", "::"})
PRIVATE_NETWORK_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|\[::1\]|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"169\.254\.\d{1,3}\.\d{1,3}|"
    r"[A-Za-z0-9-]+\.local"
    r")(:\d+)?$"
)
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

# Match src="/assets/foo.js" / href="/assets/foo.css" produced by the
# vite build. Used by the startup self-check to surface packaging
# mismatches early (see GitHub #1064 / #1065 / #1050).
_INDEX_ASSET_REF_PATTERN = re.compile(
    r"""(?:src|href)\s*=\s*["'](/assets/[^"']+)["']""",
    re.IGNORECASE,
)
_SAFE_MISSING_ASSET_MEDIA_TYPES = frozenset({"text/css", "text/javascript"})
_FRONTEND_INDEX_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


class ServerSafetyError(RuntimeError):
    """Raised when server/WebUI/API startup safety gates are not satisfied."""


def _normalize_bind_host(host: str | None) -> str:
    normalized = (host or "").strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _strip_host_port(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    hostname = parsed.hostname or candidate.split(":", 1)[0]
    return _normalize_bind_host(hostname)


def _is_lan_access_host(host: str) -> bool:
    if host in LOCAL_SERVER_HOSTS:
        return True
    try:
        parsed = ip_address(host)
    except ValueError:
        # Allow mDNS LAN names such as macmini.local, but reject public DNS
        # names and arbitrary bare Host headers by default.
        return host.endswith(".local")
    return parsed.is_private or parsed.is_loopback or parsed.is_link_local


def _configured_lan_hosts() -> List[str]:
    hosts: List[str] = []
    sources = (
        os.environ.get("DSA_PUBLIC_HOST", ""),
        os.environ.get("DSA_ALLOWED_HOSTS", ""),
        os.environ.get("WEBUI_HOST", ""),
    )
    for source in sources:
        for raw in source.split(","):
            host = _strip_host_port(raw)
            if (
                host
                and host not in BIND_ALL_HOSTS
                and _is_lan_access_host(host)
                and host not in hosts
            ):
                hosts.append(host)
    return hosts


def _external_network_enabled() -> bool:
    return _env_truthy("DSA_ALLOW_EXTERNAL_NETWORK", default=False)


class SafeHostMiddleware:
    """Reject unsafe Host headers without using wildcard TrustedHost patterns."""

    def __init__(
        self,
        app,
        *,
        allowed_hosts: List[str],
        allow_private_hosts: bool = False,
    ) -> None:
        self.app = app
        self.allowed_hosts = set(allowed_hosts)
        self.allow_private_hosts = allow_private_hosts

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        host_header = ""
        for key, value in scope.get("headers") or []:
            if key == b"host":
                host_header = value.decode("latin-1")
                break
        host = _strip_host_port(host_header)
        allowed = host in self.allowed_hosts or (
            self.allow_private_hosts and _is_lan_access_host(host)
        )
        if not allowed:
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def build_server_safe_allowed_hosts() -> List[str]:
    """Build explicit TrustedHost list without wildcard hosts."""
    hosts = ["127.0.0.1", "localhost", "::1", STARLETTE_TEST_HOST]
    if _external_network_enabled():
        for host in _configured_lan_hosts():
            if host not in hosts:
                hosts.append(host)
    return hosts


def validate_local_server_host(host: str | None) -> str:
    """Return normalized host or raise when the bind host is not allowed."""
    normalized = _normalize_bind_host(host)
    if normalized in LOCAL_SERVER_HOSTS:
        return normalized
    if _external_network_enabled():
        configured_hosts = _configured_lan_hosts()
        if normalized in configured_hosts:
            return normalized
        if normalized in BIND_ALL_HOSTS:
            return normalized
    if normalized not in LOCAL_SERVER_HOSTS:
        raise ServerSafetyError(
            "Unsafe server bind host rejected; use 127.0.0.1, localhost, or ::1, "
            "or set DSA_ALLOW_EXTERNAL_NETWORK=true with DSA_PUBLIC_HOST/DSA_ALLOWED_HOSTS."
        )
    return normalized


def _is_local_cors_origin(origin: str) -> bool:
    parsed = urlparse(origin.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    hostname = _normalize_bind_host(parsed.hostname)
    return hostname in LOCAL_SERVER_HOSTS


def build_server_safe_cors_origins(extra_origins: str | None = None) -> List[str]:
    """Build safe CORS origins; wildcard and unconfigured origins are ignored."""
    if os.environ.get("CORS_ALLOW_ALL", "").strip().lower() in {"1", "true", "yes", "on"}:
        logger.warning(
            "CORS_ALLOW_ALL is set but no longer has any effect; "
            "wildcard CORS is permanently disabled for server safety. "
            "Remove CORS_ALLOW_ALL from your .env to silence this warning."
        )
    origins = list(DEFAULT_CORS_ORIGINS)
    external_enabled = _external_network_enabled()
    allowed_hosts = set(build_server_safe_allowed_hosts())
    if external_enabled:
        port = os.environ.get("WEBUI_PORT", "8000").strip() or "8000"
        for host in allowed_hosts:
            if host == STARLETTE_TEST_HOST:
                continue
            origin = f"http://{host}:{port}" if ":" not in host else f"http://[{host}]:{port}"
            if origin not in origins:
                origins.append(origin)
    for origin in (extra_origins or "").split(","):
        candidate = origin.strip()
        parsed = urlparse(candidate)
        hostname = _normalize_bind_host(parsed.hostname)
        is_allowed_external = (
            external_enabled
            and parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and hostname in allowed_hosts
        )
        if (
            candidate
            and candidate not in origins
            and (_is_local_cors_origin(candidate) or is_allowed_external)
        ):
            origins.append(candidate)
    return origins


def build_server_safe_cors_origin_regex() -> str | None:
    """Return private-network CORS regex only for explicit external-network mode."""
    if not _external_network_enabled():
        return None
    return PRIVATE_NETWORK_CORS_ORIGIN_REGEX


def validate_admin_auth_ready() -> None:
    """Require admin auth enabled and a valid stored PBKDF2 password hash."""
    from src.auth import has_stored_password, is_auth_enabled, refresh_auth_state

    refresh_auth_state()
    if not is_auth_enabled():
        raise ServerSafetyError("Server startup requires ADMIN_AUTH_ENABLED=true.")
    if not has_stored_password():
        raise ServerSafetyError("Server startup requires a stored admin password hash.")


def validate_server_startup_safety(host: str | None) -> None:
    """Validate server/WebUI/API startup gates before uvicorn starts."""
    validate_local_server_host(host)
    validate_admin_auth_ready()


def _frontend_index_response(static_dir: Path) -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers=_FRONTEND_INDEX_NO_CACHE_HEADERS,
    )


def _check_frontend_assets_consistency(static_dir: Path) -> List[str]:
    """
    Verify that ``index.html`` only references assets that actually exist
    under ``static_dir``. Returns the list of missing references; an empty
    list means the bundle is consistent.

    Logs an actionable error when a mismatch is detected so the root cause
    is visible in ``logs/desktop.log`` instead of surfacing as a silent
    blank page.
    """
    index_html = static_dir / "index.html"
    if not index_html.is_file():
        return []
    try:
        html = index_html.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Failed to read %s for asset check: %s", index_html, exc)
        return []

    missing: List[str] = []
    for match in _INDEX_ASSET_REF_PATTERN.finditer(html):
        ref = match.group(1)
        candidate = static_dir / ref.lstrip("/")
        if not candidate.is_file() and ref not in missing:
            missing.append(ref)

    if missing:
        logger.error(
            "Frontend bundle is inconsistent: index.html references %d asset(s) "
            "that are not present on disk under %s. This will surface as a "
            "blank page in the desktop app (see GitHub #1064 / #1065). "
            "Missing: %s. Re-run the frontend build and make sure the packaging "
            "step copies the freshly generated static/ directory.",
            len(missing),
            static_dir,
            ", ".join(missing),
        )
    return missing


def _resolve_asset_path(assets_dir: Path, asset_path: str) -> Optional[Path]:
    """Resolve a requested asset path while keeping it confined to assets_dir."""
    decoded_path = unquote(asset_path)
    if not decoded_path or decoded_path.startswith(("/", "\\")):
        return None
    if "\x00" in decoded_path:
        return None
    if "\\" in decoded_path:
        return None
    if ":" in decoded_path.split("/", 1)[0]:
        return None

    assets_root = assets_dir.resolve()
    candidate = (assets_root / decoded_path).resolve()
    if not candidate.is_relative_to(assets_root):
        return None
    return candidate


def _missing_asset_media_type(asset_path: str) -> str:
    """Return a safe media type for a missing asset response."""
    content_type, _ = mimetypes.guess_type(asset_path)
    if content_type in _SAFE_MISSING_ASSET_MEDIA_TYPES:
        return content_type
    return "text/plain"

from api.v1 import api_v1_router
from api.middlewares.auth import add_auth_middleware
from api.middlewares.error_handler import add_error_handlers
from api.v1.schemas.common import HealthResponse
from src.data.stock_index_loader import find_existing_stock_index_path
from src.services.system_config_service import SystemConfigService
from src.services.stock_index_remote_service import (
    get_remote_stock_index_cache_path,
    refresh_remote_stock_index_cache,
    settings_from_config,
)


_STOCK_INDEX_FILENAME = "stocks.index.json"
_STOCK_INDEX_HEADERS = {
    "Cache-Control": "no-cache",
}


def _bundled_stock_index_path() -> Path:
    return Path(__file__).parent.parent / "apps" / "dsa-web" / "public" / _STOCK_INDEX_FILENAME


async def _refresh_stock_index_cache_in_background(reason: str) -> None:
    try:
        from src.config import get_config

        settings = settings_from_config(get_config())
        result = await run_in_threadpool(refresh_remote_stock_index_cache, settings)
        if result.refreshed:
            logger.info("[stock-index] background refresh completed (%s): %s", reason, result.cache_path)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - index refresh must stay best-effort.
        logger.warning("[stock-index] background refresh failed (%s): %s", reason, exc)


def _schedule_stock_index_background_refresh(app: FastAPI, reason: str) -> None:
    task = getattr(app.state, "stock_index_refresh_task", None)
    if task is not None and not task.done():
        return

    app.state.stock_index_refresh_task = asyncio.create_task(
        _refresh_stock_index_cache_in_background(reason)
    )


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Initialize and release shared services for the app lifecycle."""
    app.state.system_config_service = SystemConfigService()
    _schedule_stock_index_background_refresh(app, "startup")
    try:
        yield
    finally:
        refresh_task = getattr(app.state, "stock_index_refresh_task", None)
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await refresh_task
        if hasattr(app.state, "system_config_service"):
            delattr(app.state, "system_config_service")


def create_app(static_dir: Optional[Path] = None) -> FastAPI:
    """
    建立並配置 FastAPI 應用例項
    
    Args:
        static_dir: 靜態檔案目錄路徑（可選，預設為專案根目錄下的 static）
        
    Returns:
        配置完成的 FastAPI 應用例項
    """
    # 預設靜態檔案目錄
    if static_dir is None:
        static_dir = Path(__file__).parent.parent / "static"
    
    # 建立 FastAPI 例項
    app = FastAPI(
        title="Daily Stock Analysis API",
        description=(
            "A股/港股/美股自選股智慧分析系統 API\n\n"
            "## 功能模組\n"
            "- 股票分析：觸發 AI 智慧分析\n"
            "- 歷史記錄：查詢歷史分析報告\n"
            "- 股票資料：獲取行情資料\n\n"
            "## 認證方式\n"
            "支援可選的執行時認證（透過 WebUI 設定頁面啟用/關閉）"
        ),
        version="1.0.0",
        lifespan=app_lifespan,
    )
    
    # ============================================================
    # CORS 配置
    # ============================================================
    
    allowed_hosts = build_server_safe_allowed_hosts()
    allowed_origins = build_server_safe_cors_origins(os.environ.get("CORS_ORIGINS", ""))
    allowed_origin_regex = build_server_safe_cors_origin_regex()

    add_auth_middleware(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        SafeHostMiddleware,
        allowed_hosts=allowed_hosts,
        allow_private_hosts=_external_network_enabled(),
    )
    
    # ============================================================
    # 註冊路由
    # ============================================================
    
    app.include_router(api_v1_router)
    add_error_handlers(app)
    
    # ============================================================
    # 根路由和健康檢查
    # ============================================================
    
    has_frontend = static_dir.exists() and (static_dir / "index.html").exists()
    
    if has_frontend:
        # Surface bundle inconsistencies as soon as the app starts so that
        # blank-page reports (#1064 / #1065 / #1050) can be diagnosed from
        # logs/desktop.log instead of via browser devtools.
        _check_frontend_assets_consistency(static_dir)

        @app.get("/", include_in_schema=False)
        async def root():
            """根路由 - 返回前端頁面"""
            return _frontend_index_response(static_dir)
    else:
        _FRONTEND_NOT_BUILT_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DSA - Frontend Not Built</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#0a0e17;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,monospace}
  .card{max-width:580px;padding:2.5rem;border:1px solid #1e293b;border-radius:12px;background:#111827}
  h1{font-size:1.25rem;color:#38bdf8;margin-bottom:.75rem}
  p{font-size:.9rem;line-height:1.7;color:#94a3b8;margin-bottom:.5rem}
  code{background:#1e293b;padding:2px 8px;border-radius:4px;font-size:.85rem;color:#67e8f9}
  .hint{margin-top:1.25rem;padding:.75rem 1rem;border-left:3px solid #f59e0b;background:#1c1917;border-radius:0 6px 6px 0}
  .hint p{color:#fbbf24;margin:0}
  a{color:#38bdf8;text-decoration:none}
  a:hover{text-decoration:underline}
  .status{margin-top:1rem;font-size:.8rem;color:#475569}
</style></head><body><div class="card">
<h1>&#9888;&#65039; Frontend Not Built</h1>
<p>API is running, but the Web UI has not been built yet.</p>
<p>Build the frontend first:</p>
<p><code>cd apps/dsa-web &amp;&amp; npm install &amp;&amp; npm run build</code></p>
<p>Or start with auto-build:</p>
<p><code>python main.py --serve-only</code></p>
<div class="hint"><p>If you only need the API, visit <a href="/docs">/docs</a> for the interactive API documentation.</p></div>
<p class="status">API Version 1.0.0 &bull; <a href="/api/health">/api/health</a></p>
</div></body></html>"""

        @app.get("/", include_in_schema=False)
        async def root():
            """根路由 - 前端未構建時返回引導頁面"""
            return HTMLResponse(content=_FRONTEND_NOT_BUILT_HTML)
    
    @app.get(
        "/api/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="健康檢查",
        description="用於負載均衡器或監控系統檢查服務狀態"
    )
    async def health_check() -> HealthResponse:
        """健康檢查介面"""
        return HealthResponse(
            status="ok",
            timestamp=datetime.now().isoformat()
        )

    def _stock_index_candidate_paths() -> tuple[Path, ...]:
        local_candidates = (
            static_dir / _STOCK_INDEX_FILENAME,
            _bundled_stock_index_path(),
        )
        local_path = next((path for path in local_candidates if path.is_file()), None)
        if local_path is None:
            return (get_remote_stock_index_cache_path(),)
        return (
            get_remote_stock_index_cache_path(),
            local_path,
        )

    def _find_existing_stock_index_path() -> Optional[Path]:
        remote_cache_path = get_remote_stock_index_cache_path()
        return find_existing_stock_index_path(
            _stock_index_candidate_paths(),
            remote_cache_path=remote_cache_path,
        )

    @app.api_route(
        f"/{_STOCK_INDEX_FILENAME}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def serve_stock_index():
        """Serve the freshest available stock autocomplete index."""
        _schedule_stock_index_background_refresh(app, "serve-stock-index")

        index_path = _find_existing_stock_index_path()
        if index_path is None:
            return Response(
                content="stock index not found",
                status_code=404,
                media_type="text/plain",
            )
        return FileResponse(
            index_path,
            media_type="application/json",
            headers=_STOCK_INDEX_HEADERS,
        )
    
    # ============================================================
    # 靜態檔案託管（前端 SPA）
    # ============================================================
    
    if has_frontend:
        # Serve `/assets/*` explicitly so that misses return a plain-text
        # 404 with the correct Content-Type instead of the default JSON
        # error response. JSON for a JS/CSS request is what masked the
        # blank-page root cause in #1064; here we make it obvious that the
        # static file simply does not exist on disk.
        assets_dir = static_dir / "assets"

        assets_static_files = StaticFiles(directory=str(assets_dir), check_dir=False)
        assets_root = assets_dir.resolve()

        @app.api_route(
            "/assets/{asset_path:path}",
            methods=["GET", "HEAD"],
            include_in_schema=False,
        )
        async def serve_asset(request: Request, asset_path: str):
            file_path = _resolve_asset_path(assets_dir, asset_path)
            if file_path is None:
                return Response(
                    content="not found",
                    status_code=404,
                    media_type="text/plain",
                )
            if file_path.is_file():
                relative_path = file_path.relative_to(assets_root).as_posix()
                return await assets_static_files.get_response(relative_path, request.scope)
            return Response(
                content="asset not found",
                status_code=404,
                media_type=_missing_asset_media_type(asset_path),
            )

        # SPA 路由回退
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(request: Request, full_path: str):
            """SPA 路由回退 - 非 API 路由返回 index.html"""
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={"error": "not_found", "message": f"API endpoint /{full_path} not found"}
                )

            # Reuse the same containment check as /assets/* so that requests
            # like `/%2e%2e/%2e%2e/etc/passwd` cannot escape static_dir via
            # the SPA fallback. Starlette's :path converter does not collapse
            # `..` segments, so static_dir / full_path can resolve outside
            # the bundle root if served unchecked.
            file_path = _resolve_asset_path(static_dir, full_path) if full_path else None
            if file_path is not None and file_path.is_file():
                if file_path == (static_dir / "index.html").resolve():
                    return _frontend_index_response(static_dir)
                # Issue #520: Explicitly resolve MIME type to avoid
                # browsers rejecting JS modules served as text/plain.
                content_type, _ = mimetypes.guess_type(str(file_path))
                return FileResponse(file_path, media_type=content_type)

            return _frontend_index_response(static_dir)
    
    return app


# 預設應用例項（供 uvicorn 直接使用）
app = create_app()

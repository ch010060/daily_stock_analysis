# -*- coding: utf-8 -*-
"""
===================================
台股 / 美股自選股智慧分析系統 - 主排程程式
===================================

職責：
1. 協調各模組完成股票分析流程
2. 實現低併發的執行緒池排程
3. 全域性異常處理，確保單股失敗不影響整體
4. 提供命令列入口

使用方式：
    python main.py              # 正常執行
    python main.py --debug      # 除錯模式
    python main.py --dry-run    # 僅獲取資料不分析

交易理念（已融入分析）：
- 嚴進策略：不追高，乖離率 > 5% 不買進
- 趨勢交易：只做 MA5>MA10>MA20 多頭排列
- 效率優先：關注籌碼集中度好的股票
- 買點偏好：縮量回踩 MA5/MA10 支撐
"""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import dotenv_values
from src.config import setup_env

_INITIAL_PROCESS_ENV = dict(os.environ)
setup_env()

# 代理配置 - 透過 USE_PROXY 環境變數控制，預設關閉
# GitHub Actions 環境自動跳過代理配置
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    # 本地開發環境，啟用代理（可在 .env 中配置 PROXY_HOST 和 PROXY_PORT）
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

from data_provider.base import canonical_stock_code
from src.webui_frontend import prepare_webui_frontend_assets
from src.config import get_config, Config
from src.logging_config import setup_logging


logger = logging.getLogger(__name__)
_RUNTIME_ENV_FILE_KEYS = set()


def _get_active_env_path() -> Path:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return Path(env_file)
    return Path(__file__).resolve().parent / ".env"


def _read_active_env_values() -> Optional[Dict[str, str]]:
    env_path = _get_active_env_path()
    if not env_path.exists():
        return {}

    try:
        values = dotenv_values(env_path)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("讀取配置檔案 %s 失敗，繼續沿用當前環境變數: %s", env_path, exc)
        return None

    return {
        str(key): "" if value is None else str(value)
        for key, value in values.items()
        if key is not None
    }


_ACTIVE_ENV_FILE_VALUES = _read_active_env_values() or {}
_RUNTIME_ENV_FILE_KEYS = {
    key for key in _ACTIVE_ENV_FILE_VALUES
    if key not in _INITIAL_PROCESS_ENV
}

# setup_env() already ran at import time above.
_env_bootstrapped = True


def _bootstrap_environment() -> None:
    """Load .env and apply optional local proxy settings.

    Guarded to be idempotent so it can safely be called from lazy-import
    paths used by API / bot consumers.
    """
    global _env_bootstrapped
    if _env_bootstrapped:
        return

    from src.config import setup_env

    setup_env()

    if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
        proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
        proxy_port = os.getenv("PROXY_PORT", "10809")
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url

    _env_bootstrapped = True


def _setup_bootstrap_logging(debug: bool = False) -> None:
    """Initialize stderr-only logging before config is loaded.

    File handlers are deferred until ``config.log_dir`` is known (via the
    subsequent ``setup_logging()`` call) so that healthy runs never create
    log files in a hard-coded directory.
    """
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)


def _setup_runtime_logging(log_dir: str, debug: bool = False) -> bool:
    """Switch to configured logging, falling back to console on file I/O errors."""
    try:
        setup_logging(log_prefix="stock_analysis", debug=debug, log_dir=log_dir)
        return True
    except OSError as exc:
        logger.warning(
            "檔案日誌初始化失敗，已降級為控制檯日誌輸出；日誌目錄 %r 當前不可寫或不可建立: %s。"
            "官方 Docker 映象啟動入口會自動修復預設掛載目錄許可權；若仍失敗，"
            "請檢查是否使用了 --user、只讀掛載、rootless Docker 或 NFS 等限制寫入的環境。",
            log_dir,
            exc,
        )
        return False


def _get_stock_analysis_pipeline():
    """Lazily import StockAnalysisPipeline for external consumers.

    Also ensures env/proxy bootstrap has run so that API / bot consumers
    that never call ``main()`` still get ``USE_PROXY`` applied.
    """
    _bootstrap_environment()
    from src.core.pipeline import StockAnalysisPipeline as _Pipeline

    return _Pipeline


class _LazyPipelineDescriptor:
    """Descriptor that resolves StockAnalysisPipeline on first attribute access."""

    _resolved = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        if self._resolved is None:
            self._resolved = _get_stock_analysis_pipeline()
        return self._resolved


class _ModuleExports:
    StockAnalysisPipeline = _LazyPipelineDescriptor()


_exports = _ModuleExports()


def __getattr__(name: str):
    if name == "StockAnalysisPipeline":
        return _exports.StockAnalysisPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reload_env_file_values_preserving_overrides() -> None:
    """Refresh `.env`-managed env vars without clobbering process env overrides."""
    global _RUNTIME_ENV_FILE_KEYS

    latest_values = _read_active_env_values()
    if latest_values is None:
        return

    managed_keys = {
        key for key in latest_values
        if key not in _INITIAL_PROCESS_ENV
    }

    for key in _RUNTIME_ENV_FILE_KEYS - managed_keys:
        os.environ.pop(key, None)

    for key in managed_keys:
        os.environ[key] = latest_values[key]

    _RUNTIME_ENV_FILE_KEYS = managed_keys


def parse_arguments() -> argparse.Namespace:
    """解析命令列引數"""
    parser = argparse.ArgumentParser(
        description='台股 / 美股自選股智慧分析系統',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常執行
  python main.py --debug            # 除錯模式
  python main.py --dry-run          # 僅獲取資料，不進行 AI 分析
  python main.py --stocks 600519,000001  # 指定分析特定股票
  python main.py --no-notify        # 不傳送推送通知
  python main.py --check-notify     # 檢查通知配置，不傳送通知
  python main.py --single-notify    # 啟用單股推送模式（每分析完一隻立即推送）
  python main.py --schedule         # 啟用定時任務模式
  python main.py --market-review    # 僅執行大盤覆盤
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='啟用除錯模式，輸出詳細日誌'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='僅獲取資料，不進行 AI 分析'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要分析的股票代號，逗號分隔（覆蓋配置檔案）'
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不傳送推送通知'
    )

    parser.add_argument(
        '--check-notify',
        action='store_true',
        help='只讀檢查通知通道配置，不傳送通知'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='啟用單股推送模式：每分析完一隻股票立即推送，而不是彙總推送'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='併發執行緒數（預設使用配置值）'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='啟用定時任務模式，每日定時執行'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='定時任務啟動時不立即執行一次'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='僅執行大盤覆盤分析'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳過大盤覆盤分析'
    )

    parser.add_argument(
        '--force-run',
        action='store_true',
        help='跳過交易日檢查，強制執行全量分析（Issue #373）'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='啟動 Web 管理介面'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='僅啟動 Web 服務，不執行自動分析'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='啟動 FastAPI 後端服務（同時執行分析任務）'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='僅啟動 FastAPI 後端服務，不自動執行分析'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='FastAPI 服務埠（預設 8000）'
    )

    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1',
        help='FastAPI 服務監聽地址（預設 127.0.0.1；僅允許本機地址）'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='不儲存分析上下文快照'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='執行回測（對歷史分析結果進行評估）'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='僅回測指定股票代號'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='回測評估視窗（交易日數，預設使用配置）'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='強制回測（即使已有回測結果也重新計算）'
    )

    return parser.parse_args()


def _compute_trading_day_filter(
    config: Config,
    args: argparse.Namespace,
    stock_codes: List[str],
) -> Tuple[List[str], Optional[str], bool]:
    """
    Compute filtered stock list and effective market review region (Issue #373).

    Returns:
        (filtered_codes, effective_region, should_skip_all)
        - effective_region None = use config default (check disabled)
        - effective_region '' = all relevant markets closed, skip market review
        - should_skip_all: skip entire run when no stocks and no market review to run
    """
    force_run = getattr(args, 'force_run', False)
    if force_run or not getattr(config, 'trading_day_check_enabled', True):
        return (stock_codes, None, False)

    from src.core.trading_calendar import (
        get_market_for_stock,
        get_open_markets_today,
        compute_effective_region,
    )

    open_markets = get_open_markets_today()
    filtered_codes = []
    for code in stock_codes:
        mkt = get_market_for_stock(code)
        if mkt in open_markets or mkt is None:
            filtered_codes.append(code)

    if config.market_review_enabled and not getattr(args, 'no_market_review', False):
        effective_region = compute_effective_region(
            getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
        )
    else:
        effective_region = None

    should_skip_all = (not filtered_codes) and (effective_region or '') == ''
    return (filtered_codes, effective_region, should_skip_all)


def _run_market_review_with_shared_lock(
    config: Config,
    run_market_review_func: Callable[..., Optional[str]],
    **kwargs: Any,
) -> Optional[str]:
    from src.core.market_review_lock import (
        release_market_review_lock,
        try_acquire_market_review_lock,
    )

    lock_token = try_acquire_market_review_lock(config)
    if lock_token is None:
        logger.warning("大盤覆盤正在執行中，跳過本次大盤覆盤")
        return None

    try:
        return run_market_review_func(**kwargs)
    finally:
        release_market_review_lock(lock_token)


def _refresh_stock_index_cache_for_analysis(config: Config) -> None:
    """Best-effort stock-index refresh for CLI/scheduled analysis paths."""
    try:
        from src.services.stock_index_remote_service import (
            refresh_remote_stock_index_cache,
            settings_from_config,
        )

        result = refresh_remote_stock_index_cache(settings_from_config(config))
        if result.refreshed:
            logger.info("[stock-index] 分析前已重新整理股票索引快取: %s", result.cache_path)
        elif result.error:
            logger.debug("[stock-index] 分析前重新整理未完成，繼續使用本地索引: %s", result.error)
    except Exception as exc:  # noqa: BLE001 - stock index freshness must not block analysis.
        logger.warning("[stock-index] 分析前重新整理股票索引失敗，繼續執行分析: %s", exc)


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None
):
    """
    執行完整的分析流程（個股 + 大盤覆盤）

    這是定時任務呼叫的主函式
    """
    # Import pipeline modules outside the broad try/except so that import-time
    # failures propagate to the caller instead of being silently swallowed.
    from src.core.market_review import run_market_review
    from src.core.pipeline import StockAnalysisPipeline

    try:
        _refresh_stock_index_cache_for_analysis(config)

        # Issue #529: Hot-reload STOCK_LIST from .env on each scheduled run
        if stock_codes is None:
            config.refresh_stock_list()

        # Issue #373: Trading day filter (per-stock, per-market)
        effective_codes = stock_codes if stock_codes is not None else config.stock_list

        # Route B: reject non-TW/US symbols before trading-day filter
        if getattr(config, 'route_b_enforce_market_scope', False):
            from src.core.route_b_scope import RouteBScopeError, validate_route_b_watchlist
            try:
                effective_codes = validate_route_b_watchlist(effective_codes, config)
            except RouteBScopeError as exc:
                logger.error("Route B scope error: %s", exc)
                return

        filtered_codes, effective_region, should_skip = _compute_trading_day_filter(
            config, args, effective_codes
        )
        if should_skip:
            logger.info(
                "今日所有相關市場均為非交易日，跳過執行。可使用 --force-run 強制執行。"
            )
            return
        if set(filtered_codes) != set(effective_codes):
            skipped = set(effective_codes) - set(filtered_codes)
            logger.info("今日休市股票已跳過: %s", skipped)
        stock_codes = filtered_codes

        # Route B: enforce TW/US region gate for market review
        if getattr(config, 'route_b_enforce_market_scope', False) and effective_region != '':
            from src.core.market_review_scope_gate import get_effective_regions_for_route_b
            run_regions, skipped_cn, deferred_tw = get_effective_regions_for_route_b(config)
            if skipped_cn:
                logger.warning("Route B: blocking CN market review: %s", skipped_cn)
            if deferred_tw:
                logger.warning("Route B: deferring TW market review (not yet implemented): %s", deferred_tw)
            effective_region = ','.join(run_regions) if run_regions else ''

        # 命令列引數 --single-notify 覆蓋配置（#55）
        if getattr(args, 'single_notify', False):
            config.single_stock_notify = True

        # Issue #190: 個股與大盤覆盤合併推送
        merge_notification = (
            getattr(config, 'merge_email_notification', False)
            and config.market_review_enabled
            and not getattr(args, 'no_market_review', False)
            and not config.single_stock_notify
        )

        # 建立排程器
        save_context_snapshot = None
        if getattr(args, 'no_context_snapshot', False):
            save_context_snapshot = False
        query_id = uuid.uuid4().hex
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers,
            query_id=query_id,
            query_source="cli",
            save_context_snapshot=save_context_snapshot
        )

        # 1. 執行個股分析
        results = pipeline.run(
            stock_codes=stock_codes,
            dry_run=args.dry_run,
            send_notification=not args.no_notify,
            merge_notification=merge_notification
        )

        # Issue #128: 分析間隔 - 在個股分析和大盤分析之間新增延遲
        analysis_delay = getattr(config, 'analysis_delay', 0)
        if (
            analysis_delay > 0
            and config.market_review_enabled
            and not args.no_market_review
            and effective_region != ''
        ):
            logger.info(f"等待 {analysis_delay} 秒後執行大盤覆盤（避免API限流）...")
            time.sleep(analysis_delay)

        # 2. 執行大盤覆盤（如果啟用且不是僅個股模式）
        market_report = ""
        if (
            config.market_review_enabled
            and not args.no_market_review
            and effective_region != ''
        ):
            review_result = _run_market_review_with_shared_lock(
                config,
                run_market_review,
                notifier=pipeline.notifier,
                analyzer=pipeline.analyzer,
                search_service=pipeline.search_service,
                send_notification=not args.no_notify,
                merge_notification=merge_notification,
                override_region=effective_region,
            )
            # 如果有結果，賦值給 market_report 用於後續飛書文件生成
            if review_result:
                market_report = review_result

        # Issue #190: 合併推送（個股+大盤覆盤）
        if merge_notification and (results or market_report) and not args.no_notify:
            parts = []
            if market_report:
                parts.append(f"# 📈 大盤覆盤\n\n{market_report}")
            if results:
                dashboard_content = pipeline.notifier.generate_aggregate_report(
                    results,
                    getattr(config, 'report_type', 'simple'),
                )
                parts.append(f"# 🚀 個股決策儀表盤\n\n{dashboard_content}")
            if parts:
                combined_content = "\n\n---\n\n".join(parts)
                if pipeline.notifier.is_available():
                    if pipeline.notifier.send(combined_content, email_send_to_all=True, route_type="report"):
                        logger.info("已合併推送（個股+大盤覆盤）")
                    else:
                        logger.warning("合併推送失敗")

        # 輸出摘要
        if results:
            logger.info("\n===== 分析結果摘要 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"評分 {r.sentiment_score} | {r.trend_prediction}"
                )

        logger.info("\n任務執行完成")

        # === 新增：生成飛書雲文件 ===
        try:
            from src.feishu_doc import FeishuDocManager

            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("正在建立飛書雲文件...")

                # 1. 準備標題 "01-01 13:01大盤覆盤"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 大盤覆盤"

                # 2. 準備內容 (拼接個股分析和大盤覆盤)
                full_content = ""

                # 新增大盤覆盤內容（如果有）
                if market_report:
                    full_content += f"# 📈 大盤覆盤\n\n{market_report}\n\n---\n\n"

                # 新增個股決策儀表盤（使用 NotificationService 生成，按 report_type 分支）
                if results:
                    dashboard_content = pipeline.notifier.generate_aggregate_report(
                        results,
                        getattr(config, 'report_type', 'simple'),
                    )
                    full_content += f"# 🚀 個股決策儀表盤\n\n{dashboard_content}"

                # 3. 建立文件
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"飛書雲文件建立成功: {doc_url}")
                    # 可選：將文件連結也推送到群裡
                    if not args.no_notify:
                        pipeline.notifier.send(
                            f"[{now.strftime('%Y-%m-%d %H:%M')}] 覆盤文件建立成功: {doc_url}",
                            route_type="report",
                        )

        except Exception as e:
            logger.error(f"飛書文件生成失敗: {e}")

        # === Auto backtest ===
        try:
            if getattr(config, 'backtest_enabled', False):
                from src.services.backtest_service import BacktestService

                logger.info("開始自動回測...")
                service = BacktestService()
                stats = service.run_backtest(
                    force=False,
                    eval_window_days=getattr(config, 'backtest_eval_window_days', 10),
                    min_age_days=getattr(config, 'backtest_min_age_days', 14),
                    limit=200,
                )
                logger.info(
                    f"自動回測完成: processed={stats.get('processed')} saved={stats.get('saved')} "
                    f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
                )
        except Exception as e:
            logger.warning(f"自動回測失敗（已忽略）: {e}")

    except Exception as e:
        logger.exception(f"分析流程執行失敗: {e}")


def start_api_server(host: str, port: int, config: Config) -> None:
    """
    在後臺執行緒啟動 FastAPI 服務

    Args:
        host: 監聽地址
        port: 監聽埠
        config: 配置物件
    """
    import threading
    import uvicorn
    from api.app import validate_server_startup_safety

    validate_server_startup_safety(host)

    def run_server():
        level_name = (config.log_level or "INFO").lower()
        uvicorn.run(
            "api.app:app",
            host=host,
            port=port,
            log_level=level_name,
            log_config=None,
        )

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info(f"FastAPI 服務已啟動: http://{host}:{port}")


def _is_truthy_env(var_name: str, default: str = "true") -> bool:
    """Parse common truthy / falsy environment values."""
    value = os.getenv(var_name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}


def start_bot_stream_clients(config: Config) -> None:
    """Start bot stream clients when enabled in config."""
    # 啟動釘釘 Stream 客戶端
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Dingtalk Stream client: {exc}")

    # 啟動飛書 Stream 客戶端
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Feishu Stream client: {exc}")


def _resolve_scheduled_stock_codes(stock_codes: Optional[List[str]]) -> Optional[List[str]]:
    """Scheduled runs should always read the latest persisted watchlist."""
    if stock_codes is not None:
        logger.warning(
            "定時模式下檢測到 --stocks 引數；計劃執行將忽略啟動時股票快照，並在每次執行前重新讀取最新的 STOCK_LIST。"
        )
    return None


def _reload_runtime_config() -> Config:
    """Reload config from the latest persisted `.env` values for scheduled runs."""
    _reload_env_file_values_preserving_overrides()
    Config.reset_instance()
    return get_config()


def _build_schedule_time_provider(default_schedule_time: str):
    """Read the latest schedule time directly from the active config file.

    Fallback order:
    1. Process-level env override (set before launch) → honour it.
    2. Persisted config file value (written by WebUI) → use it.
    3. Documented system default ``"18:00"`` → always fall back here so
       that clearing SCHEDULE_TIME in WebUI correctly resets the schedule.
    """
    from src.core.config_manager import ConfigManager

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider() -> str:
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return os.getenv("SCHEDULE_TIME", default_schedule_time)

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip()
        if schedule_time:
            return schedule_time
        return _SYSTEM_DEFAULT_SCHEDULE_TIME

    return _provider


def main() -> int:
    """
    主入口函式

    Returns:
        退出碼（0 表示成功）
    """
    # 解析命令列引數
    args = parse_arguments()

    # 在配置載入前先初始化 bootstrap 日誌，確保早期失敗也能落盤
    try:
        _setup_bootstrap_logging(debug=args.debug)
    except Exception as exc:
        logging.basicConfig(
            level=logging.DEBUG if getattr(args, "debug", False) else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        logger.warning("Bootstrap 日誌初始化失敗，已回退到 stderr: %s", exc)

    # 載入配置（在 bootstrap logging 之後執行，確保異常有日誌）
    try:
        config = get_config()
    except Exception as exc:
        logger.exception("載入配置失敗: %s", exc)
        return 1

    # 配置日誌（輸出到控制檯和檔案）
    try:
        _setup_runtime_logging(config.log_dir, debug=args.debug)
    except Exception as exc:
        logger.exception("切換到配置日誌目錄失敗: %s", exc)
        return 1

    logger.info("=" * 60)
    logger.info("台股 / 美股自選股智慧分析系統 啟動")
    logger.info(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 驗證配置
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    if getattr(args, "check_notify", False):
        from src.services.notification_diagnostics import (
            format_notification_diagnostics,
            run_notification_diagnostics,
        )

        result = run_notification_diagnostics(config)
        print(format_notification_diagnostics(result))
        return 0 if result.ok else 1

    # 解析股票列表（統一為大寫 Issue #355）
    stock_codes = None
    if args.stocks:
        stock_codes = [canonical_stock_code(c) for c in args.stocks.split(',') if (c or "").strip()]
        logger.info(f"使用命令列指定的股票列表: {stock_codes}")

    # === 處理 --webui / --webui-only 引數，對映到 --serve / --serve-only ===
    if args.webui:
        args.serve = True
    if args.webui_only:
        args.serve_only = True

    # 相容舊版 WEBUI_ENABLED 環境變數
    if config.webui_enabled and not (args.serve or args.serve_only):
        args.serve = True

    # === 啟動 Web 服務 (如果啟用) ===
    start_serve = (args.serve or args.serve_only) and os.getenv("GITHUB_ACTIONS") != "true"

    # 相容舊版 WEBUI_HOST/WEBUI_PORT：如果使用者未透過 --host/--port 指定，則使用舊變數
    if start_serve:
        if args.host == '127.0.0.1' and os.getenv('WEBUI_HOST'):
            args.host = os.getenv('WEBUI_HOST')
        if args.port == 8000 and os.getenv('WEBUI_PORT'):
            args.port = int(os.getenv('WEBUI_PORT'))

    bot_clients_started = False
    if start_serve:
        if not prepare_webui_frontend_assets():
            logger.warning("前端靜態資源未就緒，繼續啟動 FastAPI 服務（Web 頁面可能不可用）")
        try:
            start_api_server(host=args.host, port=args.port, config=config)
            bot_clients_started = True
        except Exception as e:
            logger.error(f"啟動 FastAPI 服務失敗: {e}")

    if bot_clients_started:
        start_bot_stream_clients(config)

    # === 僅 Web 服務模式：不自動執行分析 ===
    if args.serve_only:
        logger.info("模式: 僅 Web 服務")
        logger.info(f"Web 服務執行中: http://{args.host}:{args.port}")
        logger.info("透過 /api/v1/analysis/analyze 介面觸發分析")
        logger.info(f"API 文件: http://{args.host}:{args.port}/docs")
        logger.info("按 Ctrl+C 退出...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n使用者中斷，程式退出")
        return 0

    try:
        # 模式0: 回測
        if getattr(args, 'backtest', False):
            logger.info("模式: 回測")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"回測完成: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # 模式1: 僅大盤覆盤
        if args.market_review:
            from src.core.market_review import run_market_review
            from src.core.market_review_runtime import build_market_review_runtime

            # Issue #373: Trading day check for market-review-only mode.
            # Do NOT use _compute_trading_day_filter here: that helper checks
            # config.market_review_enabled, which would wrongly block an
            # explicit --market-review invocation when the flag is disabled.
            effective_region = None
            if not getattr(args, 'force_run', False) and getattr(config, 'trading_day_check_enabled', True):
                from src.core.trading_calendar import get_open_markets_today, compute_effective_region as _compute_region
                open_markets = get_open_markets_today()
                effective_region = _compute_region(
                    getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
                )
                if effective_region == '':
                    logger.info("今日大盤覆盤相關市場均為非交易日，跳過執行。可使用 --force-run 強制執行。")
                    return 0

            logger.info("模式: 僅大盤覆盤")
            notifier, analyzer, search_service = build_market_review_runtime(config)

            _run_market_review_with_shared_lock(
                config,
                run_market_review,
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=not args.no_notify,
                override_region=effective_region,
            )
            return 0

        # 模式2: 定時任務模式
        if args.schedule or config.schedule_enabled:
            logger.info("模式: 定時任務")
            logger.info(f"每日執行時間: {config.schedule_time}")

            # Determine whether to run immediately:
            # Command line arg --no-run-immediately overrides config if present.
            # Otherwise use config (defaults to True).
            should_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                should_run_immediately = False

            logger.info(f"啟動時立即執行: {should_run_immediately}")

            from src.scheduler import run_with_schedule
            scheduled_stock_codes = _resolve_scheduled_stock_codes(stock_codes)
            schedule_time_provider = _build_schedule_time_provider(config.schedule_time)

            def scheduled_task():
                runtime_config = _reload_runtime_config()
                run_full_analysis(runtime_config, args, scheduled_stock_codes)

            background_tasks = []
            if getattr(config, 'agent_event_monitor_enabled', False):
                from src.services.alert_worker import AlertWorker

                interval_minutes = max(1, getattr(config, 'agent_event_monitor_interval_minutes', 5))
                alert_worker = AlertWorker(config_provider=_reload_runtime_config)

                def event_monitor_task():
                    stats = alert_worker.run_once()
                    triggered_count = stats.get("triggered", 0)
                    if triggered_count:
                        logger.info("[EventMonitor] 本輪觸發 %d 條提醒", triggered_count)

                background_tasks.append({
                    "task": event_monitor_task,
                    "interval_seconds": interval_minutes * 60,
                    "run_immediately": True,
                    "name": "agent_event_monitor",
                })

            run_with_schedule(
                task=scheduled_task,
                schedule_time=config.schedule_time,
                run_immediately=should_run_immediately,
                background_tasks=background_tasks,
                schedule_time_provider=schedule_time_provider,
            )
            return 0

        # 模式3: 正常單次執行
        if config.run_immediately:
            run_full_analysis(config, args, stock_codes)
        else:
            logger.info("配置為不立即執行分析 (RUN_IMMEDIATELY=false)")

        logger.info("\n程式執行完成")

        # 如果啟用了服務且是非定時任務模式，保持程式執行
        keep_running = start_serve and not (args.schedule or config.schedule_enabled)
        if keep_running:
            logger.info("API 服務執行中 (按 Ctrl+C 退出)...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        return 0

    except KeyboardInterrupt:
        logger.info("\n使用者中斷，程式退出")
        return 130

    except Exception as e:
        logger.exception(f"程式執行失敗: {e}")
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

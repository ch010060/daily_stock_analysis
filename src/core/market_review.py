# -*- coding: utf-8 -*-
"""
===================================
股票智慧分析系統 - 大盤覆盤模組（支援 A 股 / 港股 / 美股）
===================================

職責：
1. 根據 MARKET_REVIEW_REGION 配置選擇市場區域（cn / hk / us / both）
2. 執行大盤覆盤分析並生成覆盤報告
3. 儲存和傳送覆盤報告
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from src.config import get_config
from src.notification import NotificationService
from src.market_analyzer import MarketAnalyzer
from src.report_language import normalize_report_language
from src.search_service import SearchService
from src.analyzer import AnalysisResult, GeminiAnalyzer


logger = logging.getLogger(__name__)

MARKET_REVIEW_HISTORY_CODE = "MARKET"
MARKET_REVIEW_REPORT_TYPE = "market_review"
_MARKET_REVIEW_MARKETS = (
    ('cn', 'cn_title', 'A 股'),
    ('hk', 'hk_title', '港股'),
    ('us', 'us_title', '美股'),
    ('tw', 'tw_title', '台股'),
)
_MARKET_REVIEW_REGION_ORDER = tuple(market for market, _, _ in _MARKET_REVIEW_MARKETS)
_VALID_MARKET_REVIEW_REGIONS = frozenset(_MARKET_REVIEW_REGION_ORDER)


def _get_market_review_text(language: str) -> dict[str, str]:
    normalized = normalize_report_language(language)
    if normalized == "en":
        return {
            "root_title": "# 🎯 Market Review",
            "push_title": "🎯 Market Review",
            "cn_title": "# A-share Market Recap",
            "us_title": "# US Market Recap",
            "hk_title": "# HK Market Recap",
            "tw_title": "# TW Market Recap",
            "separator": "> Next market recap follows",
        }
    if normalized == "zh_TW":
        return {
            "root_title": "# 🎯 大盤回顧",
            "push_title": "🎯 大盤回顧",
            "cn_title": "# A股大盤回顧",
            "us_title": "# 美股大盤回顧",
            "hk_title": "# 港股大盤回顧",
            "tw_title": "# 台股大盤回顧",
            "separator": "> 以下為下一市場大盤回顧",
        }
    return {
        "root_title": "# 🎯 大盤覆盤",
        "push_title": "🎯 大盤覆盤",
        "cn_title": "# A股大盤覆盤",
        "us_title": "# 美股大盤覆盤",
        "hk_title": "# 港股大盤覆盤",
        "tw_title": "# 台股大盤回顧",
        "separator": "> 以下為下一市場大盤覆盤",
    }


def _resolve_market_review_regions(raw_region: Optional[str]) -> list[str]:
    """Normalize MARKET_REVIEW_REGION into an ordered, non-empty region list."""

    region = str(raw_region or 'cn').strip().lower()
    if region == 'both':
        return list(_MARKET_REVIEW_REGION_ORDER)
    if ',' in region:
        requested = {
            item.strip().lower()
            for item in region.split(',')
            if item.strip().lower() in _VALID_MARKET_REVIEW_REGIONS
        }
        return [market for market in _MARKET_REVIEW_REGION_ORDER if market in requested] or ['cn']
    if region in _VALID_MARKET_REVIEW_REGIONS:
        return [region]
    return ['cn']


def _run_tw_market_review_section():
    """Fetch TW market snapshot and render self-contained zh_TW markdown.

    Returns (report_text, light_snapshot_dict). report_text already contains
    the '# 台股大盤回顧' title — callers must NOT prepend an additional title.
    """
    from datetime import timedelta
    from data_provider.taiwan_market import TaiwanMarketDataFetcher
    from src.core.tw_market_review import render_tw_market_review_text

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    try:
        fetcher = TaiwanMarketDataFetcher()
        snapshot = fetcher.get_tw_market_snapshot(start_date, end_date)
        report = render_tw_market_review_text(snapshot)
        availability = snapshot.get("availability") or {}
        mls = {
            "source": "TaiwanMarketDataFetcher",
            "region": "tw",
            "required_ok": availability.get("required_ok", False),
            "as_of": availability.get("as_of"),
            "sources": availability.get("sources", []),
        }
        return report, mls
    except Exception as exc:
        logger.error("TW market review section failed: %s", exc)
        return None, {}


def run_market_review(
    notifier: NotificationService,
    analyzer: Optional[GeminiAnalyzer] = None,
    search_service: Optional[SearchService] = None,
    send_notification: bool = True,
    merge_notification: bool = False,
    override_region: Optional[str] = None,
    query_id: Optional[str] = None,
) -> Optional[str]:
    """
    執行大盤覆盤分析

    Args:
        notifier: 通知服務
        analyzer: AI分析器（可選）
        search_service: 搜尋服務（可選）
        send_notification: 是否傳送通知
        merge_notification: 是否合併推送（跳過本次推送，由 main 層合併個股+大盤後統一傳送，Issue #190）
        override_region: 覆蓋 config 的 market_review_region（Issue #373 交易日過濾後有效子集）
        query_id: 歷史記錄關聯 ID；API 後臺任務會傳入 task_id，CLI/Bot 為空時自動生成

    Returns:
        覆盤報告文字
    """
    logger.info("開始執行大盤覆盤分析...")
    config = get_config()
    _report_lang = getattr(config, "report_language", "zh")
    if getattr(config, "route_b_enforce_market_scope", False) and _report_lang not in ("en",):
        _report_lang = "zh_TW"
    review_text = _get_market_review_text(_report_lang)
    # Prefer market_review_regions (plural, MARKET_REVIEW_REGIONS=TW,US) when set;
    # fall back to market_review_region (singular, MARKET_REVIEW_REGION=tw).
    _plural = getattr(config, 'market_review_regions', None) or []
    raw_region = (
        override_region
        if override_region is not None
        else (
            ','.join(_plural)
            if _plural
            else (getattr(config, 'market_review_region', 'cn') or 'cn')
        )
    )
    run_markets = _resolve_market_review_regions(raw_region)
    # Under Route B enforcement, filter out CN regions via scope gate.
    if getattr(config, "route_b_enforce_market_scope", False):
        from src.core.market_review_scope_gate import (
            parse_market_review_regions_env,
            get_effective_regions_for_route_b,
        )
        explicit = parse_market_review_regions_env(','.join(run_markets))
        run_markets, skipped_cn, _ = get_effective_regions_for_route_b(config, explicit)
        if skipped_cn:
            logger.warning(
                "[Route B] Market review: blocked CN/A-share regions %r under Route B scope.",
                skipped_cn,
            )
        if not run_markets:
            logger.warning(
                "[Route B] Market review: no regions remain after Route B filtering; aborting."
            )
            return None
    persist_region = ','.join(run_markets) if len(run_markets) > 1 else run_markets[0]

    try:
        if len(run_markets) > 1:
            # 多市場順序執行，合併報告
            parts = []
            market_light_snapshots: Dict[str, Dict[str, Any]] = {}
            for mkt, title_key, label in _MARKET_REVIEW_MARKETS:
                if mkt not in run_markets:
                    continue
                logger.info("生成 %s 大盤覆盤報告...", label)
                if mkt == "tw":
                    tw_text, tw_mls = _run_tw_market_review_section()
                    market_light_snapshots["tw"] = tw_mls
                    if tw_text:
                        parts.append(tw_text)
                else:
                    mkt_analyzer = MarketAnalyzer(
                        search_service=search_service, analyzer=analyzer, region=mkt
                    )
                    review_result = mkt_analyzer.run_daily_review_with_snapshot()
                    mkt_report = review_result.report
                    market_light_snapshots[mkt] = review_result.market_light_snapshot
                    if mkt_report:
                        parts.append(f"{review_text[title_key]}\n\n{mkt_report}")
            if parts:
                review_report = f"\n\n---\n\n{review_text['separator']}\n\n".join(parts)
            else:
                review_report = None
        else:
            run_region = run_markets[0]
            if run_region == "tw":
                review_report, tw_mls = _run_tw_market_review_section()
                market_light_snapshots = {"tw": tw_mls}
            else:
                market_analyzer = MarketAnalyzer(
                    search_service=search_service,
                    analyzer=analyzer,
                    region=run_region,
                )
                review_result = market_analyzer.run_daily_review_with_snapshot()
                review_report = review_result.report
                market_light_snapshots = {run_region: review_result.market_light_snapshot}
        
        if review_report:
            from src.core.zh_tw_localization import localize_if_route_b
            review_report = localize_if_route_b(review_report)
            # 儲存報告到檔案
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"market_review_{date_str}.md"
            filepath = notifier.save_report_to_file(
                f"{review_text['root_title']}\n\n{review_report}",
                report_filename
            )
            logger.info(f"大盤覆盤報告已儲存: {filepath}")

            _persist_market_review_history(
                review_report=review_report,
                markdown_report=f"{review_text['root_title']}\n\n{review_report}",
                region=persist_region,
                config=config,
                query_id=query_id,
                market_light_snapshots=market_light_snapshots,
            )
            
            # 推送通知（合併模式下跳過，由 main 層統一傳送）
            if merge_notification and send_notification:
                logger.info("合併推送模式：跳過大盤覆盤單獨推送，將在個股+大盤覆盤後統一傳送")
            elif send_notification and notifier.is_available():
                # 新增標題
                report_content = f"{review_text['push_title']}\n\n{review_report}"

                success = notifier.send(report_content, email_send_to_all=True, route_type="report")
                if success:
                    logger.info("大盤覆盤推送成功")
                else:
                    logger.warning("大盤覆盤推送失敗")
            elif not send_notification:
                logger.info("已跳過推送通知 (--no-notify)")
            
            return review_report
        
    except Exception as e:
        logger.error(f"大盤覆盤分析失敗: {e}")
    
    return None


def _persist_market_review_history(
    *,
    review_report: str,
    markdown_report: str,
    region: str,
    config: object,
    query_id: Optional[str] = None,
    market_light_snapshots: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    """Persist market review output into the existing analysis history table."""
    try:
        from src.storage import DatabaseManager

        report_language = normalize_report_language(getattr(config, "report_language", "zh"))
        summary = _summarize_market_review(review_report, report_language)
        if report_language == "en":
            stock_name = "Market Review"
            operation_advice = "View review"
            trend_prediction = "Market review"
        else:
            stock_name = "大盤覆盤"
            operation_advice = "檢視覆盤"
            trend_prediction = "大盤覆盤"

        result = AnalysisResult(
            code=MARKET_REVIEW_HISTORY_CODE,
            name=stock_name,
            sentiment_score=50,
            trend_prediction=trend_prediction,
            operation_advice=operation_advice,
            analysis_summary=summary,
            report_language=report_language,
            news_summary=review_report,
            raw_response=markdown_report,
            data_sources="market_review",
        )

        history_query_id = query_id or f"market_review_{uuid.uuid4().hex}"
        context_snapshot = {
            "report_kind": MARKET_REVIEW_REPORT_TYPE,
            "market_review_region": region,
            "report_language": report_language,
        }
        if market_light_snapshots:
            context_snapshot["market_light_snapshots"] = market_light_snapshots

        saved = DatabaseManager.get_instance().save_analysis_history(
            result=result,
            query_id=history_query_id,
            report_type=MARKET_REVIEW_REPORT_TYPE,
            news_content=review_report,
            context_snapshot=context_snapshot,
            save_snapshot=True,
        )
        if saved:
            logger.info("大盤覆盤歷史記錄已儲存: query_id=%s", history_query_id)
        else:
            logger.warning("大盤覆盤歷史記錄儲存失敗: query_id=%s", history_query_id)
        return saved
    except Exception as exc:
        logger.warning("大盤覆盤歷史記錄儲存異常，報告檔案與推送流程繼續: %s", exc, exc_info=True)
        return 0


def _summarize_market_review(review_report: str, report_language: str) -> str:
    for line in (review_report or "").splitlines():
        text = line.strip().lstrip("#").strip()
        if text and not text.startswith("---") and not text.startswith(">"):
            return text[:200]
    if report_language == "en":
        return "Market review report generated."
    if report_language == "zh_TW":
        return "大盤回顧報告已生成。"
    return "大盤覆盤報告已生成。"

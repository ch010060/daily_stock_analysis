# -*- coding: utf-8 -*-
"""
===================================
歷史記錄介面
===================================

職責：
1. 提供 GET /api/v1/history 歷史列表查詢介面
2. 提供 GET /api/v1/history/{query_id} 歷史詳情查詢介面
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Body

from api.deps import get_database_manager
from api.v1.schemas.history import (
    HistoryListResponse,
    HistoryItem,
    DeleteHistoryRequest,
    DeleteHistoryResponse,
    NewsIntelItem,
    NewsIntelResponse,
    AnalysisReport,
    ReportMeta,
    ReportSummary,
    ReportStrategy,
    ReportDetails,
    MarkdownReportResponse,
    RunDiagnosticSummaryResponse,
    StockBarItem,
    StockBarResponse,
)
from api.v1.schemas.common import ErrorResponse
from src.storage import DatabaseManager
from src.report_language import (
    get_sentiment_label,
    get_localized_stock_name,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.services.history_service import HistoryService, MarkdownReportGenerationError
from src.services.report_renderer import sanitize_narrative_text
from src.utils.data_processing import (
    normalize_model_used,
    extract_fundamental_detail_fields,
    extract_board_detail_fields,
    extract_realtime_detail_fields,
)
from src.analysis_context_pack_overview import (
    extract_analysis_context_pack_overview,
    sanitize_context_snapshot_for_api,
)
from src.market_phase_summary import extract_market_phase_summary

logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_code_for_grouping(code: str) -> str:
    """Normalize stock code for deduplication grouping.

    Delegates to data_provider.base.normalize_stock_code which handles
    SH2330, 2330.TW, AAPL, AAPL, BJ920748, etc.
    """
    from data_provider.base import normalize_stock_code
    return normalize_stock_code(code or "")


@router.get(
    "/",
    response_model=HistoryListResponse,
    responses={
        200: {"description": "歷史記錄列表"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史分析列表",
    description="分頁獲取歷史分析記錄摘要，支援按股票代號和日期範圍篩選"
)
def get_history_list(
    stock_code: Optional[str] = Query(None, description="股票代號篩選"),
    start_date: Optional[str] = Query(None, description="開始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="頁碼（從 1 開始）"),
    limit: int = Query(20, ge=1, le=100, description="每頁數量"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> HistoryListResponse:
    """
    獲取歷史分析列表
    
    分頁獲取歷史分析記錄摘要，支援按股票代號和日期範圍篩選
    
    Args:
        stock_code: 股票代號篩選
        start_date: 開始日期
        end_date: 結束日期
        page: 頁碼
        limit: 每頁數量
        db_manager: 資料庫管理器依賴
        
    Returns:
        HistoryListResponse: 歷史記錄列表
    """
    try:
        service = HistoryService(db_manager)
        
        # 使用 def 而非 async def，FastAPI 自動線上程池中執行
        result = service.get_history_list(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit
        )
        
        # 轉換為響應模型
        items = [
            HistoryItem(
                id=item.get("id"),
                query_id=item.get("query_id", ""),
                stock_code=item.get("stock_code", ""),
                stock_name=item.get("stock_name"),
                report_type=item.get("report_type"),
                trend_prediction=item.get("trend_prediction"),
                analysis_summary=item.get("analysis_summary"),
                sentiment_score=item.get("sentiment_score"),
                operation_advice=item.get("operation_advice"),
                current_price=item.get("current_price"),
                change_pct=item.get("change_pct"),
                volume_ratio=item.get("volume_ratio"),
                turnover_rate=item.get("turnover_rate"),
                model_used=item.get("model_used"),
                created_at=item.get("created_at")
            )
            for item in result.get("items", [])
        ]
        
        return HistoryListResponse(
            total=result.get("total", 0),
            page=page,
            limit=limit,
            items=items
        )
        
    except Exception as e:
        logger.error(f"查詢歷史列表失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢歷史列表失敗: {str(e)}"
            }
        )


@router.delete(
    "/by-code/{stock_code}",
    response_model=DeleteHistoryResponse,
    responses={
        200: {"description": "刪除成功"},
        404: {"description": "未找到記錄", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="按股票代號刪除歷史分析記錄",
    description="刪除指定股票代號的所有分析歷史記錄（支援程式碼變體歸一化匹配）",
)
def delete_history_by_code(
    stock_code: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> DeleteHistoryResponse:
    try:
        candidates = HistoryService._history_code_filter_candidates(stock_code)
        records, _ = db_manager.get_analysis_history_paginated(code=candidates, limit=10000)
        record_ids = [r.id for r in records if r.id is not None]
        if not record_ids:
            return DeleteHistoryResponse(deleted=0)
        deleted = db_manager.delete_analysis_history_records(record_ids)
        return DeleteHistoryResponse(deleted=deleted)
    except Exception as e:
        logger.error(f"按股票代號刪除歷史記錄失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"刪除失敗: {str(e)}"},
        )


@router.delete(
    "/",
    response_model=DeleteHistoryResponse,
    responses={
        200: {"description": "刪除成功"},
        400: {"description": "請求引數錯誤", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="刪除歷史分析記錄",
    description="按歷史記錄主鍵 ID 批次刪除分析歷史"
)
def delete_history_records(
    request: DeleteHistoryRequest = Body(...),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> DeleteHistoryResponse:
    """
    按主鍵 ID 批次刪除歷史分析記錄。
    """
    record_ids = sorted({record_id for record_id in request.record_ids if record_id is not None})
    if not record_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_request",
                "message": "record_ids 不能為空"
            }
        )

    try:
        service = HistoryService(db_manager)
        deleted = service.delete_history_records(record_ids)
        return DeleteHistoryResponse(deleted=deleted)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除歷史記錄失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"刪除歷史記錄失敗: {str(e)}"
            }
        )


@router.get(
    "/stocks",
    response_model=StockBarResponse,
    responses={
        200: {"description": "不重複個股列表"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取不重複個股列表",
    description="返回歷史記錄中每隻股票的最新一條分析摘要，大盤覆盤（code=MARKET）始終置頂。",
)
def get_stock_bar(
    start_date: Optional[str] = Query(None, description="開始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    limit: int = Query(200, ge=1, le=500, description="最大返回數量"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> StockBarResponse:
    try:
        from datetime import date as date_type
        from src.utils.data_processing import parse_json_field

        start = date_type.fromisoformat(start_date) if start_date else None
        end = date_type.fromisoformat(end_date) if end_date else None

        # Fetch more than limit to compensate for normalization dedup shrinkage
        # (e.g. 002460 + 002460.SZ both initially counted but merged to one)
        fetch_limit = min(limit * 3, 500)
        records = db_manager.get_distinct_stocks_from_history(
            start_date=start,
            end_date=end,
            limit=fetch_limit,
        )

        # Deduplicate by normalized code, keeping the record with highest id
        seen: dict = {}
        for record in records:
            norm_code = _normalize_code_for_grouping(record.code or "")
            if norm_code not in seen or record.id > seen[norm_code].id:
                seen[norm_code] = record

        items = []
        for norm_code in seen:
            record = seen[norm_code]
            raw_result = parse_json_field(getattr(record, "raw_result", None))
            model_used = raw_result.get("model_used") if isinstance(raw_result, dict) else None

            analysis_count = db_manager.get_analysis_history_paginated(
                code=HistoryService._history_code_filter_candidates(
                    record.code or "",
                ),
                limit=1,
            )[1]
            items.append(
                StockBarItem(
                    id=record.id,
                    stock_code=record.code or "",
                    stock_name=record.name,
                    report_type=record.report_type,
                    sentiment_score=record.sentiment_score,
                    operation_advice=record.operation_advice,
                    analysis_count=analysis_count,
                    last_analysis_time=(
                        record.created_at.isoformat() if record.created_at else None
                    ),
                    model_used=normalize_model_used(model_used),
                )
            )

        items = items[:limit]
        return StockBarResponse(total=len(items), items=items)

    except Exception as e:
        logger.error(f"查詢個股欄失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢個股欄失敗: {str(e)}",
            },
        )


@router.get(
    "/{record_id}",
    response_model=AnalysisReport,
    responses={
        200: {"description": "報告詳情"},
        404: {"description": "報告不存在", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告詳情",
    description="根據分析歷史記錄 ID 或 query_id 獲取完整的歷史分析報告"
)
def get_history_detail(
    record_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> AnalysisReport:
    """
    獲取歷史報告詳情
    
    根據分析歷史記錄主鍵 ID 或 query_id 獲取完整的歷史分析報告。
    優先嚐試按主鍵 ID（整數）查詢，若引數不是合法整數則按 query_id 查詢。
    
    Args:
        record_id: 分析歷史記錄主鍵 ID（整數）或 query_id（字串）
        db_manager: 資料庫管理器依賴
        
    Returns:
        AnalysisReport: 完整分析報告
        
    Raises:
        HTTPException: 404 - 報告不存在
    """
    try:
        service = HistoryService(db_manager)
        
        # Try integer ID first, fall back to query_id string lookup
        result = service.resolve_and_get_detail(record_id)
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到 id/query_id={record_id} 的分析記錄"
                }
            )
        
        # 從 context_snapshot 中提取價格資訊
        # 注意：使用 `is None` 而非 `or`，避免把 0.0（平盤）誤判為缺失值；
        # 同時不混用 `change_60d`（60 日累計漲跌幅）作為日內 change_pct 的兜底。
        context_snapshot = result.get("context_snapshot")
        analysis_context_pack_overview = extract_analysis_context_pack_overview(context_snapshot)
        market_phase_summary = extract_market_phase_summary(context_snapshot)
        api_context_snapshot = sanitize_context_snapshot_for_api(context_snapshot)
        realtime_fields = extract_realtime_detail_fields(context_snapshot)
        current_price = realtime_fields.get("current_price")
        change_pct = realtime_fields.get("change_pct")
        
        raw_result = result.get("raw_result")
        if not isinstance(raw_result, dict):
            raw_result = {}
        report_language = normalize_report_language(
            result.get("report_language")
            or raw_result.get("report_language")
            or (
                context_snapshot.get("report_language")
                if isinstance(context_snapshot, dict)
                else None
            )
        )
        stock_name = get_localized_stock_name(
            result.get("stock_name"),
            result.get("stock_code", ""),
            report_language,
        )

        # 構建響應模型
        meta = ReportMeta(
            id=result.get("id"),
            query_id=result.get("query_id", ""),
            stock_code=result.get("stock_code", ""),
            stock_name=stock_name,
            report_type=result.get("report_type"),
            report_language=report_language,
            created_at=result.get("created_at"),
            current_price=current_price,
            change_pct=change_pct,
            model_used=normalize_model_used(result.get("model_used")),
            market_phase_summary=market_phase_summary,
        )
        
        summary = ReportSummary(
            analysis_summary=result.get("analysis_summary"),
            operation_advice=localize_operation_advice(
                result.get("operation_advice"),
                report_language,
            ),
            trend_prediction=localize_trend_prediction(
                result.get("trend_prediction"),
                report_language,
            ),
            sentiment_score=result.get("sentiment_score"),
            sentiment_label=(
                get_sentiment_label(result.get("sentiment_score"), report_language)
                if result.get("sentiment_score") is not None
                else result.get("sentiment_label")
            )
        )
        
        strategy = ReportStrategy(
            ideal_buy=result.get("ideal_buy"),
            secondary_buy=result.get("secondary_buy"),
            stop_loss=result.get("stop_loss"),
            take_profit=result.get("take_profit")
        )
        
        fallback_fundamental = db_manager.get_latest_fundamental_snapshot(
            query_id=result.get("query_id", ""),
            code=result.get("stock_code", ""),
        )
        extracted_fundamental = extract_fundamental_detail_fields(
            context_snapshot=result.get("context_snapshot"),
            fallback_fundamental_payload=fallback_fundamental,
        )
        extracted_boards = extract_board_detail_fields(
            context_snapshot=result.get("context_snapshot"),
            fallback_fundamental_payload=fallback_fundamental,
        )

        details = ReportDetails(
            news_content=result.get("news_content"),
            raw_result=result.get("raw_result"),
            context_snapshot=api_context_snapshot,
            analysis_context_pack_overview=analysis_context_pack_overview,
            financial_report=extracted_fundamental.get("financial_report"),
            dividend_metrics=extracted_fundamental.get("dividend_metrics"),
            belong_boards=extracted_boards.get("belong_boards"),
            sector_rankings=extracted_boards.get("sector_rankings"),
        )
        
        return AnalysisReport(
            meta=meta,
            summary=summary,
            strategy=strategy,
            details=details
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查詢歷史詳情失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢歷史詳情失敗: {str(e)}"
            }
        )


@router.get(
    "/{record_id}/diagnostics",
    response_model=RunDiagnosticSummaryResponse,
    responses={
        200: {"description": "執行診斷摘要"},
        404: {"description": "報告不存在", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告執行診斷摘要",
    description="根據分析歷史記錄 ID 或 query_id 獲取使用者可讀診斷摘要和脫敏複製文字。",
)
def get_history_diagnostics(
    record_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> RunDiagnosticSummaryResponse:
    """
    獲取歷史報告執行診斷摘要。
    """
    try:
        service = HistoryService(db_manager)
        summary = service.resolve_and_get_diagnostics(record_id)
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到 id/query_id={record_id} 的分析記錄",
                },
            )
        return RunDiagnosticSummaryResponse.model_validate(summary)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查詢執行診斷摘要失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢執行診斷摘要失敗: {str(e)}",
            },
        )


@router.get(
    "/{record_id}/news",
    response_model=NewsIntelResponse,
    responses={
        200: {"description": "新聞情報列表"},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告關聯新聞",
    description="根據分析歷史記錄 ID 獲取關聯的新聞情報列表（為空也返回 200）"
)
def get_history_news(
    record_id: str,
    limit: int = Query(20, ge=1, le=100, description="返回數量限制"),
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> NewsIntelResponse:
    """
    獲取歷史報告關聯新聞

    根據分析歷史記錄 ID 或 query_id 獲取關聯的新聞情報列表。
    在內部完成 record_id → query_id 的解析。

    Args:
        record_id: 分析歷史記錄主鍵 ID（整數）或 query_id（字串）
        limit: 返回數量限制
        db_manager: 資料庫管理器依賴

    Returns:
        NewsIntelResponse: 新聞情報列表
    """
    try:
        service = HistoryService(db_manager)
        items = service.resolve_and_get_news(record_id=record_id, limit=limit)

        response_items = [
            NewsIntelItem(
                title=item.get("title", ""),
                snippet=item.get("snippet"),
                url=item.get("url", "")
            )
            for item in items
        ]

        return NewsIntelResponse(
            total=len(response_items),
            items=response_items
        )

    except Exception as e:
        logger.error(f"查詢新聞情報失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"查詢新聞情報失敗: {str(e)}"
            }
        )


@router.get(
    "/{record_id}/markdown",
    response_model=MarkdownReportResponse,
    responses={
        200: {"description": "Markdown 格式報告"},
        404: {"description": "報告不存在", "model": ErrorResponse},
        500: {"description": "伺服器錯誤", "model": ErrorResponse},
    },
    summary="獲取歷史報告 Markdown 格式",
    description="根據分析歷史記錄 ID 獲取 Markdown 格式的完整分析報告"
)
def get_history_markdown(
    record_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager)
) -> MarkdownReportResponse:
    """
    獲取歷史報告的 Markdown 格式內容

    根據分析歷史記錄 ID 或 query_id 生成與推送通知格式一致的 Markdown 報告。

    Args:
        record_id: 分析歷史記錄主鍵 ID（整數）或 query_id（字串）
        db_manager: 資料庫管理器依賴

    Returns:
        MarkdownReportResponse: Markdown 格式的完整報告

    Raises:
        HTTPException: 404 - 報告不存在
        HTTPException: 500 - 報告生成失敗（伺服器內部錯誤）
    """
    service = HistoryService(db_manager)

    try:
        markdown_content = service.get_markdown_report(record_id)
    except MarkdownReportGenerationError as e:
        logger.error(f"Markdown report generation failed for {record_id}: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "generation_failed",
                "message": f"生成 Markdown 報告失敗: {e.message}"
            }
        )
    except Exception as e:
        logger.error(f"獲取 Markdown 報告失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"獲取 Markdown 報告失敗: {str(e)}"
            }
        )

    if markdown_content is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"未找到 id/query_id={record_id} 的分析記錄"
            }
        )

    return MarkdownReportResponse(content=sanitize_narrative_text(markdown_content))

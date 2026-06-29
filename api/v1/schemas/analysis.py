# -*- coding: utf-8 -*-
"""
===================================
分析相關模型
===================================

職責：
1. 定義分析請求和響應模型
2. 定義任務狀態模型
3. 定義非同步任務佇列相關模型
"""

from typing import Optional, List, Any, Literal
from enum import Enum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from src.utils.analysis_metadata import SELECTION_SOURCE_PATTERN


class TaskStatusEnum(str, Enum):
    """任務狀態列舉"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


AnalysisPhase = Literal["auto", "premarket", "intraday", "postmarket"]


class AnalyzeRequest(BaseModel):
    """Analysis request parameters"""
    
    stock_code: Optional[str] = Field(
        None, 
        description="單隻股票代號",
        json_schema_extra={"example": "2330"},
    )
    stock_codes: Optional[List[str]] = Field(
        None, 
        description="多隻股票代號（與 stock_code 二選一）",
        json_schema_extra={"example": ["2330", "2454"]},
    )
    report_type: str = Field(
        "detailed",
        description="報告型別：simple(精簡) / detailed(完整) / full(完整) / brief(簡潔)",
        pattern="^(simple|detailed|full|brief)$",
    )
    force_refresh: bool = Field(
        False,
        description="是否強制重新整理（忽略快取）"
    )
    async_mode: bool = Field(
        False,
        description="是否使用非同步模式"
    )
    analysis_phase: AnalysisPhase = Field(
        "auto",
        description="分析階段覆蓋：auto(自動推斷) / premarket(盤前) / intraday(盤中) / postmarket(盤後)",
    )
    stock_name: Optional[str] = Field(
        None,
        description="使用者選中的股票名稱（自動補全時提供）",
        json_schema_extra={"example": "台積電"},
    )
    original_query: Optional[str] = Field(
        None,
        description="使用者原始輸入（如台積電、gzmt、2330）",
        json_schema_extra={"example": "台積電"},
    )
    selection_source: Optional[str] = Field(
        None,
        description="股票選擇來源：manual(手動輸入) | autocomplete(自動補全) | import(匯入) | image(圖片識別)",
        pattern=SELECTION_SOURCE_PATTERN,
        json_schema_extra={"example": "autocomplete"},
    )
    notify: bool = Field(
        True,
        description="是否傳送推送通知（Telegram/企業微信等）"
    )
    skills: Optional[List[str]] = Field(
        None,
        validation_alias=AliasChoices("skills", "strategies"),
        description="本次分析使用的策略 skill ID 列表；相容 legacy strategies 欄位",
        json_schema_extra={"example": ["bull_trend", "growth_quality"]},
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "2330",
            "report_type": "detailed",
            "force_refresh": False,
            "async_mode": False,
            "analysis_phase": "auto",
            "stock_name": "台積電",
            "original_query": "台積電",
            "selection_source": "autocomplete",
            "notify": True,
            "skills": ["bull_trend"]
        }
    })


class MarketReviewRequest(BaseModel):
    """Market review trigger parameters."""

    send_notification: bool = Field(
        True,
        description="是否在大盤覆盤完成後傳送推送通知",
    )


class MarketReviewAccepted(BaseModel):
    """Market review background task accepted response."""

    status: str = Field("accepted", description="提交狀態")
    message: str = Field(..., description="提示資訊")
    send_notification: bool = Field(..., description="是否傳送通知")
    trace_id: Optional[str] = Field(
        None,
        description="本次後臺任務的診斷 trace ID",
    )
    task_id: Optional[str] = Field(
        None,
        description="任務 ID（僅當任務實際提交時返回）",
    )


class AnalysisResultResponse(BaseModel):
    """分析結果響應模型"""
    
    query_id: str = Field(..., description="分析記錄唯一標識")
    trace_id: Optional[str] = Field(None, description="診斷 trace ID")
    stock_code: str = Field(..., description="股票代號")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    report: Optional[Any] = Field(None, description="分析報告")
    diagnostic_summary: Optional[Any] = Field(None, description="執行診斷摘要")
    created_at: str = Field(..., description="建立時間")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query_id": "abc123def456",
            "stock_code": "2330",
            "stock_name": "台積電",
            "report": {
                "summary": {
                    "sentiment_score": 75,
                    "operation_advice": "持有"
                }
            },
            "created_at": "2024-01-01T12:00:00"
        }
    })


class TaskAccepted(BaseModel):
    """非同步任務接受響應"""
    
    task_id: str = Field(..., description="任務 ID，用於查詢狀態")
    trace_id: Optional[str] = Field(None, description="診斷 trace ID")
    status: str = Field(
        ..., 
        description="任務狀態",
        pattern="^(pending|processing)$"
    )
    message: Optional[str] = Field(None, description="提示資訊")
    analysis_phase: AnalysisPhase = Field("auto", description="請求的分析階段")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task_abc123",
            "status": "pending",
            "message": "Analysis task accepted",
            "analysis_phase": "auto"
        }
    })


class BatchTaskAcceptedItem(BaseModel):
    """批次非同步任務中的單個成功提交項。"""

    task_id: str = Field(..., description="任務 ID，用於查詢狀態")
    trace_id: Optional[str] = Field(None, description="診斷 trace ID")
    stock_code: str = Field(..., description="股票代號")
    status: str = Field(
        ...,
        description="任務狀態",
        pattern="^(pending|processing)$"
    )
    message: Optional[str] = Field(None, description="提示資訊")
    analysis_phase: AnalysisPhase = Field("auto", description="請求的分析階段")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task_abc123",
            "stock_code": "2330",
            "status": "pending",
            "message": "分析任務已加入佇列: 2330",
            "analysis_phase": "auto"
        }
    })


class BatchDuplicateTaskItem(BaseModel):
    """批次非同步任務中的重複提交項。"""

    stock_code: str = Field(..., description="股票代號")
    existing_task_id: str = Field(..., description="已存在的任務 ID")
    message: str = Field(..., description="錯誤資訊")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "2330",
            "existing_task_id": "task_existing_123",
            "message": "股票 2330 正在分析中 (task_id: task_existing_123)"
        }
    })


class BatchTaskAcceptedResponse(BaseModel):
    """批次非同步任務接受響應。"""

    accepted: List[BatchTaskAcceptedItem] = Field(default_factory=list, description="成功提交的任務列表")
    duplicates: List[BatchDuplicateTaskItem] = Field(default_factory=list, description="重複而跳過的任務列表")
    message: str = Field(..., description="彙總資訊")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "accepted": [
                {
                    "task_id": "task_abc123",
                    "stock_code": "2330",
                    "status": "pending",
                    "message": "分析任務已加入佇列: 2330",
                    "analysis_phase": "auto"
                }
            ],
            "duplicates": [
                {
                    "stock_code": "2454",
                    "existing_task_id": "task_existing_456",
                    "message": "股票 2454 正在分析中 (task_id: task_existing_456)"
                }
            ],
            "message": "已提交 1 個任務，1 個重複跳過"
        }
    })


class TaskStatus(BaseModel):
    """Task status model"""
    
    task_id: str = Field(..., description="任務 ID")
    trace_id: Optional[str] = Field(None, description="診斷 trace ID")
    status: str = Field(
        ..., 
        description="任務狀態",
        pattern="^(pending|processing|completed|failed)$"
    )
    progress: Optional[int] = Field(
        None, 
        description="進度百分比 (0-100)",
        ge=0,
        le=100
    )
    stage: Optional[str] = Field(None, description="當前分析階段")
    stage_label: Optional[str] = Field(None, description="當前階段顯示文字")
    result: Optional[AnalysisResultResponse] = Field(
        None, 
        description="分析結果（僅在 completed 時存在）"
    )
    market_review_report: Optional[str] = Field(
        None,
        description="大盤覆盤任務返回的報告文字（僅大盤覆盤任務）",
    )
    market_review_snapshot: Optional[Any] = Field(
        None,
        description="台股日報結構化快照（僅大盤覆盤任務，來源為持久化 context_snapshot）",
    )
    market_review_skip_reason: Optional[str] = Field(
        None,
        description="台股日報任務已完成但未產生可持久化報告時的跳過原因（僅大盤覆盤任務）",
    )
    error: Optional[str] = Field(
        None, 
        description="錯誤資訊（僅在 failed 時存在）"
    )
    stock_name: Optional[str] = Field(None, description="股票名稱")
    original_query: Optional[str] = Field(None, description="使用者原始輸入")
    selection_source: Optional[str] = Field(
        None,
        description="選擇來源",
        pattern=SELECTION_SOURCE_PATTERN,
    )
    analysis_phase: Optional[AnalysisPhase] = Field(
        None,
        description="請求的分析階段；無持久化欄位的歷史 DB fallback 可能為空",
    )
    skills: Optional[List[str]] = Field(None, description="本次任務使用的策略 skill ID 列表")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "task_abc123",
            "status": "completed",
            "progress": 100,
            "result": None,
            "market_review_report": None,
            "error": None,
            "stock_name": "台積電",
            "original_query": "台積電",
            "selection_source": "autocomplete",
            "analysis_phase": "auto",
            "skills": ["bull_trend"]
        }
    })


class TaskInfo(BaseModel):
    """
    Task details model

    Used for task list and SSE event delivery
    """
    
    task_id: str = Field(..., description="任務 ID")
    trace_id: Optional[str] = Field(None, description="診斷 trace ID")
    stock_code: str = Field(..., description="股票代號")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    status: TaskStatusEnum = Field(..., description="任務狀態")
    progress: int = Field(0, description="進度百分比 (0-100)", ge=0, le=100)
    message: Optional[str] = Field(None, description="狀態訊息")
    report_type: str = Field("detailed", description="報告型別")
    created_at: str = Field(..., description="建立時間")
    started_at: Optional[str] = Field(None, description="開始執行時間")
    completed_at: Optional[str] = Field(None, description="完成時間")
    error: Optional[str] = Field(None, description="錯誤資訊（僅在 failed 時存在）")
    original_query: Optional[str] = Field(None, description="使用者原始輸入")
    selection_source: Optional[str] = Field(
        None,
        description="選擇來源",
        pattern=SELECTION_SOURCE_PATTERN,
    )
    analysis_phase: AnalysisPhase = Field("auto", description="請求的分析階段")
    skills: Optional[List[str]] = Field(None, description="本次任務使用的策略 skill ID 列表")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "task_id": "abc123def456",
            "stock_code": "2330",
            "stock_name": "台積電",
            "status": "processing",
            "progress": 50,
            "message": "正在分析中...",
            "report_type": "detailed",
            "created_at": "2026-02-05T10:30:00",
            "started_at": "2026-02-05T10:30:01",
            "completed_at": None,
            "error": None,
            "original_query": "台積電",
            "selection_source": "autocomplete",
            "analysis_phase": "auto",
            "skills": ["bull_trend"]
        }
    })


class TaskListResponse(BaseModel):
    """任務列表響應模型"""
    
    total: int = Field(..., description="任務總數")
    pending: int = Field(..., description="等待中的任務數")
    processing: int = Field(..., description="處理中的任務數")
    tasks: List[TaskInfo] = Field(..., description="任務列表")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total": 3,
            "pending": 1,
            "processing": 2,
            "tasks": []
        }
    })


class DuplicateTaskErrorResponse(BaseModel):
    """重複任務錯誤響應模型"""
    
    error: str = Field("duplicate_task", description="錯誤型別")
    message: str = Field(..., description="錯誤資訊")
    stock_code: str = Field(..., description="股票代號")
    existing_task_id: str = Field(..., description="已存在的任務 ID")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "error": "duplicate_task",
            "message": "股票 2330 正在分析中",
            "stock_code": "2330",
            "existing_task_id": "abc123def456"
        }
    })

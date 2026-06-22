# -*- coding: utf-8 -*-
"""
===================================
股票資料相關模型
===================================

職責：
1. 定義股票實時行情模型
2. 定義歷史 K 線資料模型
"""

from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class StockQuote(BaseModel):
    """股票實時行情"""
    
    stock_code: str = Field(..., description="股票代號")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    current_price: float = Field(..., description="當前價格")
    change: Optional[float] = Field(None, description="漲跌額")
    change_percent: Optional[float] = Field(None, description="漲跌幅 (%)")
    open: Optional[float] = Field(None, description="開盤價")
    high: Optional[float] = Field(None, description="最高價")
    low: Optional[float] = Field(None, description="最低價")
    prev_close: Optional[float] = Field(None, description="昨收價")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交額（元）")
    update_time: Optional[str] = Field(None, description="更新時間")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "2330",
            "stock_name": "台積電",
            "current_price": 1800.00,
            "change": 15.00,
            "change_percent": 0.84,
            "open": 1785.00,
            "high": 1810.00,
            "low": 1780.00,
            "prev_close": 1785.00,
            "volume": 10000000,
            "amount": 18000000000,
            "update_time": "2024-01-01T15:00:00"
        }
    })


class KLineData(BaseModel):
    """K 線資料點"""
    
    date: str = Field(..., description="日期")
    open: float = Field(..., description="開盤價")
    high: float = Field(..., description="最高價")
    low: float = Field(..., description="最低價")
    close: float = Field(..., description="收盤價")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交額")
    change_percent: Optional[float] = Field(None, description="漲跌幅 (%)")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "2024-01-01",
            "open": 1785.00,
            "high": 1810.00,
            "low": 1780.00,
            "close": 1800.00,
            "volume": 10000000,
            "amount": 18000000000,
            "change_percent": 0.84
        }
    })


class ExtractItem(BaseModel):
    """單條提取結果（程式碼、名稱、置信度）"""

    code: Optional[str] = Field(None, description="股票代號，None 表示解析失敗")
    name: Optional[str] = Field(None, description="股票名稱（如有）")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """圖片股票代號提取響應"""

    codes: List[str] = Field(..., description="提取的股票代號（已去重，向後相容）")
    items: List[ExtractItem] = Field(default_factory=list, description="提取結果明細（程式碼+名稱+置信度）")
    raw_text: Optional[str] = Field(None, description="原始 LLM 響應（除錯用）")


class StockHistoryResponse(BaseModel):
    """股票歷史行情響應"""
    
    stock_code: str = Field(..., description="股票代號")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    period: str = Field(..., description="K 線週期")
    data: List[KLineData] = Field(default_factory=list, description="K 線資料列表")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "2330",
            "stock_name": "台積電",
            "period": "daily",
            "data": []
        }
    })


class SymbolCandidateResponse(BaseModel):
    """TW/US symbol lookup candidate."""

    canonical_symbol: str = Field(..., description="Canonical market-scoped symbol, e.g. TW:8299")
    raw_symbol: str = Field(..., description="Provider/native symbol, e.g. 8299 or META")
    symbol: str = Field(..., description="Alias of raw_symbol for frontend compatibility")
    market: str = Field(..., description="Supported market: TW or US")
    exchange: Optional[str] = Field(None, description="Exchange/source venue if known")
    instrument_type: str = Field(..., description="stock / ETF / index")
    name: str = Field(..., description="Display name")
    aliases: List[str] = Field(default_factory=list, description="Known aliases")
    provider_source: str = Field(..., description="Sanitized universe source")
    is_active: bool = Field(True, description="Whether candidate is active")
    last_updated: Optional[str] = Field(None, description="Source update timestamp")
    confidence: float = Field(..., description="Deterministic match confidence")
    match_reason: str = Field(..., description="Deterministic match reason")


class SymbolSearchResponse(BaseModel):
    """Symbol candidate search response."""

    query: str
    candidates: List[SymbolCandidateResponse] = Field(default_factory=list)


class SymbolResolveResponse(BaseModel):
    """Symbol resolve response."""

    query: str
    status: str = Field(..., description="resolved / ambiguous / not_found")
    selected: Optional[SymbolCandidateResponse] = None
    candidates: List[SymbolCandidateResponse] = Field(default_factory=list)
    message: Optional[str] = None

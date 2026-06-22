# -*- coding: utf-8 -*-
"""
===================================
A股自選股智慧分析系統 - 搜尋服務模組
===================================

職責：
1. 提供統一的新聞搜尋介面
2. 支援 Bocha、Tavily、Brave、SerpAPI、SearXNG 多種搜尋引擎
3. 多 Key 負載均衡和故障轉移
4. 搜尋結果快取和格式化
"""

import logging
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Optional, Tuple
from itertools import cycle
from urllib.parse import parse_qsl, unquote, urlparse
import requests
from newspaper import Article, Config
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from data_provider.us_index_mapping import is_us_index_code
from src.config import (
    NEWS_STRATEGY_WINDOWS,
    normalize_news_strategy_profile,
    resolve_news_window_days,
)
from src.services.run_diagnostics import sanitize_diagnostic_text

logger = logging.getLogger(__name__)

DEFAULT_NEWS_CONTEXT_MAX_TOTAL_CHARS = 8000
NEWS_CONTEXT_TRUNCATION_MARKER_TEMPLATE = "[TRUNCATED: news context capped at {max_chars} chars]"


def cap_news_context(
    text: Optional[str],
    max_chars: Optional[int] = DEFAULT_NEWS_CONTEXT_MAX_TOTAL_CHARS,
) -> Optional[str]:
    """Apply a deterministic total length cap to news context text."""
    if text is None or max_chars is None:
        return text

    safe_max_chars = max(0, max_chars)
    if len(text) <= safe_max_chars:
        return text

    marker = NEWS_CONTEXT_TRUNCATION_MARKER_TEMPLATE.format(max_chars=safe_max_chars)
    truncated = text[:safe_max_chars].rstrip()
    if not truncated:
        return marker
    return f"{truncated}\n{marker}"


# Transient network errors (retryable)
_SEARCH_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_SEARCH_TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _post_with_retry(url: str, *, headers: Dict[str, str], json: Dict[str, Any], timeout: int) -> requests.Response:
    """POST with retry on transient SSL/network errors."""
    return requests.post(url, headers=headers, json=json, timeout=timeout)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_SEARCH_TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_with_retry(
    url: str, *, headers: Dict[str, str], params: Dict[str, Any], timeout: int, verify: bool = True
) -> requests.Response:
    """GET with retry on transient SSL/network errors."""
    return requests.get(url, headers=headers, params=params, timeout=timeout, verify=verify)


def fetch_url_content(url: str, timeout: int = 5) -> str:
    """
    獲取 URL 網頁正文內容 (使用 newspaper3k)
    """
    try:
        # 配置 newspaper3k
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        config.request_timeout = timeout
        config.fetch_images = False  # 不下載圖片
        config.memoize_articles = False # 不快取

        article = Article(url, config=config, language='zh') # 預設中文，但也支援其他
        article.download()
        article.parse()

        # 獲取正文
        text = article.text.strip()

        # 簡單的後處理，去除空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        return text[:1500]  # 限制返回長度（比 bs4 稍微多一點，因為 newspaper 解析更乾淨）
    except Exception as e:
        logger.debug(f"Fetch content failed for {url}: {e}")

    return ""


@dataclass
class SearchResult:
    """搜尋結果資料類"""
    title: str
    snippet: str  # 摘要
    url: str
    source: str  # 來源網站
    published_date: Optional[str] = None
    relevance_score: Optional[int] = None
    relevance_category: Optional[str] = None
    relevance_reasons: Optional[List[str]] = None
    
    def to_text(self) -> str:
        """轉換為文字格式"""
        date_str = f" ({self.published_date})" if self.published_date else ""
        relevance_parts: List[str] = []
        if self.relevance_category:
            relevance_parts.append(self.relevance_category)
        if self.relevance_score is not None:
            relevance_parts.append(f"score={self.relevance_score}")
        if self.relevance_reasons:
            relevance_parts.append(f"依據: {'；'.join(self.relevance_reasons[:3])}")
        relevance_str = f"\n關聯度: {'; '.join(relevance_parts)}" if relevance_parts else ""
        return f"【{self.source}】{self.title}{date_str}\n{self.snippet}{relevance_str}"


@dataclass 
class SearchResponse:
    """搜尋響應"""
    query: str
    results: List[SearchResult]
    provider: str  # 使用的搜尋引擎
    success: bool = True
    error_message: Optional[str] = None
    search_time: float = 0.0  # 搜尋耗時（秒）
    diagnostics: Optional[Dict[str, Any]] = None
    
    def to_context(self, max_results: int = 5) -> str:
        """將搜尋結果轉換為可用於 AI 分析的上下文"""
        if not self.success or not self.results:
            return f"搜尋 '{self.query}' 未找到相關結果。"
        
        lines = [f"【{self.query} 搜尋結果】（來源：{self.provider}）"]
        for i, result in enumerate(self.results[:max_results], 1):
            lines.append(f"\n{i}. {result.to_text()}")
        
        return "\n".join(lines)


class BaseSearchProvider(ABC):
    """搜尋引擎基類"""
    
    def __init__(self, api_keys: List[str], name: str):
        """
        初始化搜尋引擎
        
        Args:
            api_keys: API Key 列表（支援多個 key 負載均衡）
            name: 搜尋引擎名稱
        """
        self._api_keys = api_keys
        self._name = name
        self._key_cycle = cycle(api_keys) if api_keys else None
        self._key_usage: Dict[str, int] = {key: 0 for key in api_keys}
        self._key_errors: Dict[str, int] = {key: 0 for key in api_keys}
        self._state_lock = threading.RLock()
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_available(self) -> bool:
        """檢查是否有可用的 API Key"""
        return bool(self._api_keys)
    
    def _get_next_key(self) -> Optional[str]:
        """
        獲取下一個可用的 API Key（負載均衡）
        
        策略：輪詢 + 跳過錯誤過多的 key
        """
        with self._state_lock:
            if not self._key_cycle:
                return None
            
            # 最多嘗試所有 key
            for _ in range(len(self._api_keys)):
                key = next(self._key_cycle)
                # 跳過錯誤次數過多的 key（超過 3 次）
                if self._key_errors.get(key, 0) < 3:
                    return key
            
            # 所有 key 都有問題，重置錯誤計數並返回第一個
            logger.warning(f"[{self._name}] 所有 API Key 都有錯誤記錄，重置錯誤計數")
            self._key_errors = {key: 0 for key in self._api_keys}
            return self._api_keys[0] if self._api_keys else None
    
    def _record_success(self, key: str) -> None:
        """記錄成功使用"""
        with self._state_lock:
            self._key_usage[key] = self._key_usage.get(key, 0) + 1
            # 成功後減少錯誤計數
            if key in self._key_errors and self._key_errors[key] > 0:
                self._key_errors[key] -= 1
    
    def _record_error(self, key: str) -> None:
        """記錄錯誤"""
        with self._state_lock:
            self._key_errors[key] = self._key_errors.get(key, 0) + 1
            error_count = self._key_errors[key]
        logger.warning(f"[{self._name}] API Key {key[:8]}... 錯誤計數: {error_count}")
    
    @abstractmethod
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行搜尋（子類實現）"""
        pass
    
    def _execute_search(
        self,
        query: str,
        *,
        max_results: int = 5,
        days: int = 7,
        api_key: Optional[str] = None,
        **search_kwargs: Any,
    ) -> SearchResponse:
        """Run the shared search flow with an optional preselected API key."""
        api_key = api_key or self._get_next_key()
        if not api_key:
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=f"{self._name} 未配置 API Key"
            )

        start_time = time.time()
        try:
            response = self._do_search(query, api_key, max_results, days=days, **search_kwargs)
            response.search_time = time.time() - start_time

            if response.success:
                self._record_success(api_key)
                logger.info(f"[{self._name}] 搜尋 '{query}' 成功，返回 {len(response.results)} 條結果，耗時 {response.search_time:.2f}s")
            else:
                self._record_error(api_key)

            return response

        except Exception as e:
            self._record_error(api_key)
            elapsed = time.time() - start_time
            logger.error(f"[{self._name}] 搜尋 '{query}' 失敗: {e}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=str(e),
                search_time=elapsed
            )

    def search(self, query: str, max_results: int = 5, days: int = 7) -> SearchResponse:
        """
        執行搜尋
        
        Args:
            query: 搜尋關鍵詞
            max_results: 最大返回結果數
            days: 搜尋最近幾天的時間範圍（預設7天）
            
        Returns:
            SearchResponse 物件
        """
        return self._execute_search(query, max_results=max_results, days=days)


class TavilySearchProvider(BaseSearchProvider):
    """
    Tavily 搜尋引擎
    
    特點：
    - 專為 AI/LLM 最佳化的搜尋 API
    - 免費版每月 1000 次請求
    - 返回結構化的搜尋結果
    
    文件：https://docs.tavily.com/
    """
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Tavily")
    
    def _do_search(
        self,
        query: str,
        api_key: str,
        max_results: int,
        days: int = 7,
        topic: Optional[str] = None,
    ) -> SearchResponse:
        """執行 Tavily 搜尋"""
        try:
            from tavily import TavilyClient
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="tavily-python 未安裝，請執行: pip install tavily-python"
            )
        
        try:
            client = TavilyClient(api_key=api_key)
            
            # 執行搜尋（最佳化：使用advanced深度、限制最近幾天）
            search_kwargs: Dict[str, Any] = {
                "query": query,
                "search_depth": "advanced",  # advanced 獲取更多結果
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
                "days": days,  # 搜尋最近天數的內容
            }
            if topic is not None:
                search_kwargs["topic"] = topic

            response = client.search(
                **search_kwargs,
            )
            
            # 記錄原始響應到日誌
            logger.info(f"[Tavily] 搜尋完成，query='{query}', 返回 {len(response.get('results', []))} 條結果")
            logger.debug(f"[Tavily] 原始響應: {response}")
            
            # 解析結果
            results = []
            for item in response.get('results', []):
                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=item.get('content', '')[:500],  # 擷取前500字
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=item.get('published_date') or item.get('publishedDate'),
                ))
            
            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except Exception as e:
            error_msg = str(e)
            # 檢查是否是配額問題
            if 'rate limit' in error_msg.lower() or 'quota' in error_msg.lower():
                error_msg = f"API 配額已用盡: {error_msg}"
            
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )

    def search(
        self,
        query: str,
        max_results: int = 5,
        days: int = 7,
        topic: Optional[str] = None,
    ) -> SearchResponse:
        """執行 Tavily 搜尋，可按呼叫方選擇是否啟用新聞 topic。"""
        if topic is None:
            return super().search(query, max_results=max_results, days=days)

        api_key = self._get_next_key()
        if not api_key:
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=f"{self._name} 未配置 API Key"
            )

        start_time = time.time()
        try:
            response = self._do_search(query, api_key, max_results, days=days, topic=topic)
            response.search_time = time.time() - start_time

            if response.success:
                self._record_success(api_key)
                logger.info(f"[{self._name}] 搜尋 '{query}' 成功，返回 {len(response.results)} 條結果，耗時 {response.search_time:.2f}s")
            else:
                self._record_error(api_key)

            return response

        except Exception as e:
            self._record_error(api_key)
            elapsed = time.time() - start_time
            logger.error(f"[{self._name}] 搜尋 '{query}' 失敗: {e}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=str(e),
                search_time=elapsed
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class SerpAPISearchProvider(BaseSearchProvider):
    """
    SerpAPI 搜尋引擎
    
    特點：
    - 支援 Google、Bing、百度等多種搜尋引擎
    - 免費版每月 100 次請求
    - 返回真實的搜尋結果
    
    文件：https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis
    """

    _ORGANIC_CONTENT_FETCH_LIMIT = 1
    _ORGANIC_CONTENT_FETCH_RANK_LIMIT = 2
    _ORGANIC_CONTENT_FETCH_TIMEOUT = 2
    _ORGANIC_SNIPPET_SUFFICIENT_LENGTH = 140
    _ORGANIC_FETCHED_PREVIEW_LENGTH = 320
    _SKIPPED_CONTENT_FETCH_SUFFIXES = (
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".zip",
        ".rar",
        ".7z",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".csv",
    )
    _SKIPPED_CONTENT_FETCH_QUERY_KEYS = {
        "attachment",
        "attachment_file",
        "doc",
        "document",
        "download",
        "download_file",
        "file",
        "file_name",
        "filename",
        "file_path",
        "filepath",
        "resource",
        "resource_file",
    }
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "SerpAPI")
    
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行 SerpAPI 搜尋"""
        try:
            from serpapi import GoogleSearch
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="google-search-results 未安裝，請執行: pip install google-search-results"
            )
        
        try:
            # 確定時間範圍引數 tbs
            tbs = "qdr:w"  # 預設一週
            if days <= 1:
                tbs = "qdr:d"  # 過去24小時
            elif days <= 7:
                tbs = "qdr:w"  # 過去一週
            elif days <= 30:
                tbs = "qdr:m"  # 過去一月
            else:
                tbs = "qdr:y"  # 過去一年

            # 使用 Google 搜尋 (獲取 Knowledge Graph, Answer Box 等)
            params = {
                "engine": "google",
                "q": query,
                "api_key": api_key,
                "google_domain": "google.com.hk", # 使用香港谷歌，中文支援較好
                "hl": "zh-cn",  # 中文介面
                "gl": "cn",     # 中國地區偏好
                "tbs": tbs,     # 時間範圍限制
                "num": max_results # 請求的結果數量，注意：Google API有時不嚴格遵守
            }
            
            search = GoogleSearch(params)
            response = search.get_dict()
            
            # 記錄原始響應到日誌
            logger.debug(f"[SerpAPI] 原始響應 keys: {response.keys()}")
            
            # 解析結果
            results = []
            
            # 1. 解析 Knowledge Graph (知識圖譜)
            kg = response.get('knowledge_graph', {})
            if kg:
                title = kg.get('title', '知識圖譜')
                desc = kg.get('description', '')
                
                # 提取額外屬性
                details = []
                for key in ['type', 'founded', 'headquarters', 'employees', 'ceo']:
                    val = kg.get(key)
                    if val:
                        details.append(f"{key}: {val}")
                        
                snippet = f"{desc}\n" + " | ".join(details) if details else desc
                
                results.append(SearchResult(
                    title=f"[知識圖譜] {title}",
                    snippet=snippet,
                    url=kg.get('source', {}).get('link', ''),
                    source="Google Knowledge Graph"
                ))
                
            # 2. 解析 Answer Box (精選回答/行情卡片)
            ab = response.get('answer_box', {})
            if ab:
                ab_title = ab.get('title', '精選回答')
                ab_snippet = ""
                
                # 財經類回答
                if ab.get('type') == 'finance_results':
                    stock = ab.get('stock', '')
                    price = ab.get('price', '')
                    currency = ab.get('currency', '')
                    movement = ab.get('price_movement', {})
                    mv_val = movement.get('percentage', 0)
                    mv_dir = movement.get('movement', '')
                    
                    ab_title = f"[行情卡片] {stock}"
                    ab_snippet = f"價格: {price} {currency}\n漲跌: {mv_dir} {mv_val}%"
                    
                    # 提取表格資料
                    if 'table' in ab:
                        table_data = []
                        for row in ab['table']:
                            if 'name' in row and 'value' in row:
                                table_data.append(f"{row['name']}: {row['value']}")
                        if table_data:
                            ab_snippet += "\n" + "; ".join(table_data)
                            
                # 普通文字回答
                elif 'snippet' in ab:
                    ab_snippet = ab.get('snippet', '')
                    list_items = ab.get('list', [])
                    if list_items:
                        ab_snippet += "\n" + "\n".join([f"- {item}" for item in list_items])
                
                elif 'answer' in ab:
                    ab_snippet = ab.get('answer', '')
                    
                if ab_snippet:
                    results.append(SearchResult(
                        title=f"[精選回答] {ab_title}",
                        snippet=ab_snippet,
                        url=ab.get('link', '') or ab.get('displayed_link', ''),
                        source="Google Answer Box"
                    ))

            # 3. 解析 Related Questions (相關問題)
            rqs = response.get('related_questions', [])
            for rq in rqs[:3]: # 取前3個
                question = rq.get('question', '')
                snippet = rq.get('snippet', '')
                link = rq.get('link', '')
                
                if question and snippet:
                     results.append(SearchResult(
                        title=f"[相關問題] {question}",
                        snippet=snippet,
                        url=link,
                        source="Google Related Questions"
                     ))

            # 4. 解析 Organic Results (自然搜尋結果)
            organic_results = response.get('organic_results', [])
            organic_content_fetch_attempts = 0

            for rank, item in enumerate(organic_results[:max_results]):
                link = item.get('link', '')
                rich_extensions = self._extract_rich_snippet_extensions(item)
                snippet = self._build_organic_snippet(item, rich_extensions=rich_extensions)

                if self._should_fetch_organic_content(
                    link=link,
                    snippet=snippet,
                    rank=rank,
                    fetched_count=organic_content_fetch_attempts,
                    has_structured_summary=bool(rich_extensions),
                ):
                    organic_content_fetch_attempts += 1
                    try:
                        fetched_content = fetch_url_content(
                            link,
                            timeout=self._ORGANIC_CONTENT_FETCH_TIMEOUT,
                        )
                        if fetched_content:
                            snippet = self._merge_organic_snippet_with_content(
                                snippet,
                                fetched_content,
                            )
                    except Exception as e:
                        logger.debug(f"[SerpAPI] Fetch content failed: {e}")

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=snippet[:1000], # 限制總長度
                    url=link,
                    source=item.get('source', self._extract_domain(link)),
                    published_date=item.get('date'),
                ))

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except Exception as e:
            error_msg = str(e)
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace('www.', '') or '未知來源'
        except Exception:
            return '未知來源'

    @classmethod
    def _normalize_organic_text(cls, value: Any) -> str:
        """標準化 SerpAPI organic 文字欄位。"""
        text = "" if value is None else str(value)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _extract_rich_snippet_extensions(cls, item: Dict[str, Any]) -> List[str]:
        """提取 rich_snippet 中已有的結構化摘要，優先複用 API 原始返回。"""
        rich_snippet = item.get("rich_snippet")
        if not isinstance(rich_snippet, dict):
            return []

        extensions: List[str] = []
        seen: set[str] = set()

        for section in ("top", "bottom"):
            section_data = rich_snippet.get(section)
            if not isinstance(section_data, dict):
                continue

            raw_extensions = section_data.get("extensions")
            if isinstance(raw_extensions, (list, tuple, set)):
                for raw_value in raw_extensions:
                    value = cls._normalize_organic_text(raw_value)
                    if not value or value in seen:
                        continue
                    seen.add(value)
                    extensions.append(value)

            for raw_value in cls._flatten_rich_snippet_values(
                section_data.get("detected_extensions")
            ):
                if raw_value in seen:
                    continue
                seen.add(raw_value)
                extensions.append(raw_value)

        return extensions

    @classmethod
    def _flatten_rich_snippet_values(
        cls,
        value: Any,
        *,
        label: Optional[str] = None,
        allow_unlabeled_scalar: bool = False,
    ) -> List[str]:
        """把 rich_snippet.detected_extensions 展平為可讀文字。"""
        if isinstance(value, dict):
            flattened: List[str] = []
            for key, nested_value in value.items():
                flattened.extend(
                    cls._flatten_rich_snippet_values(
                        nested_value,
                        label=cls._normalize_organic_text(str(key)).replace("_", " "),
                    )
                )
            return flattened

        if isinstance(value, (list, tuple, set)):
            flattened: List[str] = []
            for nested_value in value:
                flattened.extend(
                    cls._flatten_rich_snippet_values(
                        nested_value,
                        label=label,
                        allow_unlabeled_scalar=True,
                    )
                )
            return flattened

        text = cls._normalize_organic_text(value)
        if not text:
            return []

        if label:
            return [f"{label}: {text}"]

        if allow_unlabeled_scalar:
            return [text]

        return []

    @classmethod
    def _build_organic_snippet(
        cls,
        item: Dict[str, Any],
        *,
        rich_extensions: Optional[List[str]] = None,
    ) -> str:
        """構建 organic result 摘要，儘量先消費 SerpAPI 已返回的資訊。"""
        snippet = cls._normalize_organic_text(item.get("snippet", ""))
        if rich_extensions is None:
            rich_extensions = cls._extract_rich_snippet_extensions(item)

        if rich_extensions:
            rich_text = " | ".join(rich_extensions)
            if rich_text and rich_text not in snippet:
                snippet = f"{snippet}\n{rich_text}".strip() if snippet else rich_text

        return snippet

    @classmethod
    def _matches_skipped_content_fetch_suffix(cls, value: Any) -> bool:
        """判斷連結片段是否指向附件或其他非 HTML 資源。"""
        normalized_value = cls._normalize_organic_text(value).lower()
        if not normalized_value:
            return False

        decoded_value = unquote(normalized_value)
        if decoded_value.endswith(cls._SKIPPED_CONTENT_FETCH_SUFFIXES):
            return True

        return urlparse(decoded_value).path.lower().endswith(
            cls._SKIPPED_CONTENT_FETCH_SUFFIXES
        )

    @classmethod
    def _matches_skipped_content_fetch_query_param(
        cls, key: Any, value: Any
    ) -> bool:
        """僅對少數顯式附件引數跳過正文抓取，避免誤傷普通 HTML 頁面。"""
        normalized_key = cls._normalize_organic_text(key)
        if not normalized_key:
            return False

        snake_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized_key)
        canonical_key = re.sub(r"[^a-z0-9]+", "_", snake_key.lower()).strip("_")
        if canonical_key not in cls._SKIPPED_CONTENT_FETCH_QUERY_KEYS:
            return False

        return cls._matches_skipped_content_fetch_suffix(value)

    @classmethod
    def _should_fetch_organic_content(
        cls,
        *,
        link: Any,
        snippet: str,
        rank: int,
        fetched_count: int,
        has_structured_summary: bool,
    ) -> bool:
        """僅對極少量高位且摘要明顯不足的結果補抓正文。"""
        if fetched_count >= cls._ORGANIC_CONTENT_FETCH_LIMIT:
            return False

        if rank >= cls._ORGANIC_CONTENT_FETCH_RANK_LIMIT:
            return False

        if has_structured_summary:
            return False

        if len(snippet) >= cls._ORGANIC_SNIPPET_SUFFICIENT_LENGTH:
            return False

        if not isinstance(link, str):
            return False

        if not link or not link.startswith(("http://", "https://")):
            return False

        parsed_link = urlparse(link)
        if parsed_link.scheme not in {"http", "https"}:
            return False

        if cls._matches_skipped_content_fetch_suffix(parsed_link.path):
            return False

        for key, value in parse_qsl(parsed_link.query, keep_blank_values=True):
            if cls._matches_skipped_content_fetch_query_param(key, value):
                return False

        return True

    @classmethod
    def _merge_organic_snippet_with_content(cls, snippet: str, content: str) -> str:
        """用較短正文預覽補強 snippet，避免拉長單次搜尋耗時和返回體積。"""
        normalized = cls._normalize_organic_text(content)
        if not normalized:
            return snippet

        preview = normalized[:cls._ORGANIC_FETCHED_PREVIEW_LENGTH]
        if len(normalized) > cls._ORGANIC_FETCHED_PREVIEW_LENGTH:
            preview = f"{preview}..."

        if snippet:
            return f"{snippet}\n\n【網頁詳情】\n{preview}"

        return f"【網頁詳情】\n{preview}"


class BochaSearchProvider(BaseSearchProvider):
    """
    博查搜尋引擎
    
    特點：
    - 專為AI最佳化的中文搜尋API
    - 結果準確、摘要完整
    - 支援時間範圍過濾和AI摘要
    - 相容Bing Search API格式
    
    文件：https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK
    """
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Bocha")
    
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行博查搜尋"""
        try:
            import requests
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="requests 未安裝，請執行: pip install requests"
            )
        
        try:
            # API 端點
            url = "https://api.bocha.cn/v1/web-search"
            
            # 請求頭
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # 確定時間範圍
            freshness = "oneWeek"
            if days <= 1:
                freshness = "oneDay"
            elif days <= 7:
                freshness = "oneWeek"
            elif days <= 30:
                freshness = "oneMonth"
            else:
                freshness = "oneYear"

            # 請求引數（嚴格按照API文件）
            payload = {
                "query": query,
                "freshness": freshness,  # 動態時間範圍
                "summary": True,  # 啟用AI摘要
                "count": min(max_results, 50)  # 最大50條
            }
            
            # 執行搜尋（帶瞬時 SSL/網路錯誤重試）
            response = _post_with_retry(url, headers=headers, json=payload, timeout=10)
            
            # 檢查HTTP狀態碼
            if response.status_code != 200:
                # 嘗試解析錯誤資訊
                try:
                    if response.headers.get('content-type', '').startswith('application/json'):
                        error_data = response.json()
                        error_message = error_data.get('message', response.text)
                    else:
                        error_message = response.text
                except Exception:
                    error_message = response.text
                
                # 根據錯誤碼處理
                if response.status_code == 403:
                    error_msg = f"餘額不足: {error_message}"
                elif response.status_code == 401:
                    error_msg = f"API KEY無效: {error_message}"
                elif response.status_code == 400:
                    error_msg = f"請求引數錯誤: {error_message}"
                elif response.status_code == 429:
                    error_msg = f"請求頻率達到限制: {error_message}"
                else:
                    error_msg = f"HTTP {response.status_code}: {error_message}"
                
                logger.warning(f"[Bocha] 搜尋失敗: {error_msg}")
                
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 解析響應
            try:
                data = response.json()
            except ValueError as e:
                error_msg = f"響應JSON解析失敗: {str(e)}"
                logger.error(f"[Bocha] {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 檢查響應code
            if data.get('code') != 200:
                error_msg = data.get('msg') or f"API返回錯誤碼: {data.get('code')}"
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 記錄原始響應到日誌
            logger.info(f"[Bocha] 搜尋完成，query='{query}'")
            logger.debug(f"[Bocha] 原始響應: {data}")
            
            # 解析搜尋結果
            results = []
            web_pages = data.get('data', {}).get('webPages', {})
            value_list = web_pages.get('value', [])
            
            for item in value_list[:max_results]:
                # 優先使用summary（AI摘要），fallback到snippet
                snippet = item.get('summary') or item.get('snippet', '')
                
                # 擷取摘要長度
                if snippet:
                    snippet = snippet[:500]
                
                results.append(SearchResult(
                    title=item.get('name', ''),
                    snippet=snippet,
                    url=item.get('url', ''),
                    source=item.get('siteName') or self._extract_domain(item.get('url', '')),
                    published_date=item.get('datePublished'),  # UTC+8格式，無需轉換
                ))
            
            logger.info(f"[Bocha] 成功解析 {len(results)} 條結果")
            
            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except requests.exceptions.Timeout:
            error_msg = "請求超時"
            logger.error(f"[Bocha] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"網路請求失敗: {str(e)}"
            logger.error(f"[Bocha] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            error_msg = f"未知錯誤: {str(e)}"
            logger.error(f"[Bocha] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class AnspireSearchProvider(BaseSearchProvider):
    """
    Anspire Search 搜尋引擎
    
    特點：
    - 面向AI生態的下一代實時智慧搜尋引擎
    - 結果精準、響應快速
    - 適用於股票新聞和市場情報搜尋
    
    文件: https://open.anspire.cn/document/docs/searchApi/
    """
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Anspire")
    
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行 Anspire 搜尋"""
        try:
            import requests
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="requests 未安裝，請執行：pip install requests"
            )
        
        try:
            # API 端點
            url = "https://plugin.anspire.cn/api/ntsearch/search"
            
            # 請求頭
            headers = {
                'Authorization': f'Bearer {api_key}'
            }

            # 請求引數
            payload = {
                "query": query,
                "top_k": min(max_results,50), 
                "FromTime": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
                "ToTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 執行搜尋
            response = _get_with_retry(url, headers=headers, params=payload, timeout=10)
            
            # 檢查 HTTP 狀態碼
            if response.status_code != 200:
                # 嘗試解析錯誤資訊
                try:
                    if response.headers.get('content-type', '').startswith('application/json'):
                        error_data = response.json()
                        error_message = error_data.get('message', response.text)
                    else:
                        error_message = response.text
                except Exception:
                    error_message = response.text
                
                # 根據錯誤碼處理
                if response.status_code == 403:
                    error_msg = f"餘額不足或許可權不足：{error_message}"
                elif response.status_code == 401:
                    error_msg = f"API KEY 無效：{error_message}"
                elif response.status_code == 400:
                    error_msg = f"請求引數錯誤：{error_message}"
                else:
                    error_msg = f"HTTP {response.status_code}: {error_message}"
                
                logger.warning(f"[Anspire] 搜尋失敗：{error_msg}")
                
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 解析響應
            try:
                data = response.json()
            except ValueError as e:
                error_msg = f"響應 JSON 解析失敗：{str(e)}"
                logger.error(f"[Anspire] {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            if 'code' in data and data.get('code') != 200:
                error_msg = data.get('msg') or f"API 返回錯誤碼：{data.get('code')}"
                logger.warning(f"[Anspire] 搜尋失敗：{error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            if 'results' not in data:
                error_msg = "響應中缺少 results 欄位"
                logger.error(f"[Anspire] {error_msg}，原始響應：{data}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 記錄原始響應到日誌
            logger.info(f"[Anspire] 搜尋完成，query='{query}'")
            logger.debug(f"[Anspire] 原始響應：{data}")
            
            results = []
            value_list = data.get('results', [])
            
            for item in value_list[:max_results]:
                snippet = item.get('content')
                if snippet and isinstance(snippet, str) and len(snippet) > 500:
                    snippet = snippet[:500] + "..."
                
                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=snippet,
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=item.get('date', '')
                ))
            
            logger.info(f"[Anspire] 成功解析 {len(results)} 條結果")
            
            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except requests.exceptions.Timeout:
            error_msg = "請求超時"
            logger.error(f"[Anspire] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"網路請求失敗：{str(e)}"
            logger.error(f"[Anspire] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            error_msg = f"未知錯誤：{str(e)}"
            logger.error(f"[Anspire] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class MiniMaxSearchProvider(BaseSearchProvider):
    """
    MiniMax Web Search (Coding Plan API)

    Features:
    - Backed by MiniMax Coding Plan subscription
    - Returns structured organic results with title/link/snippet/date
    - No native time-range parameter; time filtering is done via query
      augmentation and client-side date filtering
    - Circuit-breaker protection: 3 consecutive failures -> 300s cooldown

    API endpoint: POST https://api.minimaxi.com/v1/coding_plan/search
    """

    API_ENDPOINT = "https://api.minimaxi.com/v1/coding_plan/search"

    # Circuit-breaker settings
    _CB_FAILURE_THRESHOLD = 3
    _CB_COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "MiniMax")
        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until: float = 0.0

    @property
    def is_available(self) -> bool:
        """Check availability considering circuit breaker state."""
        with self._state_lock:
            if not self._api_keys:
                return False
            if self._consecutive_failures >= self._CB_FAILURE_THRESHOLD:
                if time.time() < self._circuit_open_until:
                    return False
                # Cooldown expired -> half-open, allow one probe
            return True

    def _record_success(self, key: str) -> None:
        with self._state_lock:
            super()._record_success(key)
            # Reset circuit breaker on success
            self._consecutive_failures = 0
            self._circuit_open_until = 0.0

    def _record_error(self, key: str) -> None:
        warning_message = None
        with self._state_lock:
            super()._record_error(key)
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._CB_FAILURE_THRESHOLD:
                self._circuit_open_until = time.time() + self._CB_COOLDOWN_SECONDS
                warning_message = (
                    f"[MiniMax] Circuit breaker OPEN – "
                    f"{self._consecutive_failures} consecutive failures, "
                    f"cooldown {self._CB_COOLDOWN_SECONDS}s"
                )
        if warning_message:
            logger.warning(warning_message)

    # ------------------------------------------------------------------
    # Time-range helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _time_hint(days: int, is_chinese: bool = True) -> str:
        """Build a time-hint string to append to the search query."""
        if is_chinese:
            if days <= 1:
                return "今天"
            elif days <= 3:
                return "最近三天"
            elif days <= 7:
                return "最近一週"
            else:
                return "最近一個月"
        else:
            if days <= 1:
                return "today"
            elif days <= 3:
                return "past 3 days"
            elif days <= 7:
                return "past week"
            else:
                return "past month"

    @staticmethod
    def _is_within_days(date_str: Optional[str], days: int) -> bool:
        """Check whether *date_str* falls within the last *days* days.

        Accepts common formats: ``2025-06-01``, ``2025/06/01``,
        ``Jun 1, 2025``, ISO-8601 with timezone, etc.
        Returns True when date_str is None or unparseable (keep the result).
        """
        if not date_str:
            return True
        try:
            from dateutil import parser as dateutil_parser
            dt = dateutil_parser.parse(date_str, fuzzy=True)
            from datetime import timedelta, timezone
            now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
            return (now - dt) <= timedelta(days=days + 1)  # +1 buffer
        except Exception:
            return True  # Keep result when date is unparseable

    # ------------------------------------------------------------------

    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """Execute MiniMax web search."""
        try:
            # Detect language hint from query (simple heuristic)
            has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in query)
            time_hint = self._time_hint(days, is_chinese=has_cjk)
            augmented_query = f"{query} {time_hint}"

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'MM-API-Source': 'Minimax-MCP',
            }
            payload = {"q": augmented_query}

            response = _post_with_retry(
                self.API_ENDPOINT, headers=headers, json=payload, timeout=15
            )

            # HTTP error handling
            if response.status_code != 200:
                error_msg = self._parse_http_error(response)
                logger.warning(f"[MiniMax] Search failed: {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg,
                )

            data = response.json()

            # Check base_resp status
            base_resp = data.get('base_resp', {})
            if base_resp.get('status_code', 0) != 0:
                error_msg = base_resp.get('status_msg', 'Unknown API error')
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg,
                )

            logger.info(f"[MiniMax] Search done, query='{query}'")
            logger.debug(f"[MiniMax] Raw response keys: {list(data.keys())}")

            # Parse organic results
            results: List[SearchResult] = []
            for item in data.get('organic', []):
                date_val = item.get('date')

                # Client-side time filtering
                if not self._is_within_days(date_val, days):
                    continue

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=(item.get('snippet', '') or '')[:500],
                    url=item.get('link', ''),
                    source=self._extract_domain(item.get('link', '')),
                    published_date=date_val,
                ))

                if len(results) >= max_results:
                    break

            logger.info(f"[MiniMax] Parsed {len(results)} results (after time filter)")

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )

        except requests.exceptions.Timeout:
            error_msg = "Request timeout"
            logger.error(f"[MiniMax] {error_msg}")
            return SearchResponse(
                query=query, results=[], provider=self.name,
                success=False, error_message=error_msg,
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {e}"
            logger.error(f"[MiniMax] {error_msg}")
            return SearchResponse(
                query=query, results=[], provider=self.name,
                success=False, error_message=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"[MiniMax] {error_msg}")
            return SearchResponse(
                query=query, results=[], provider=self.name,
                success=False, error_message=error_msg,
            )

    @staticmethod
    def _parse_http_error(response) -> str:
        """Parse HTTP error response from MiniMax API."""
        try:
            ct = response.headers.get('content-type', '')
            if 'json' in ct:
                err = response.json()
                base_resp = err.get('base_resp', {})
                msg = base_resp.get('status_msg') or err.get('message') or str(err)
                return msg
            return response.text[:200]
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL as source label."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class BraveSearchProvider(BaseSearchProvider):
    """
    Brave Search 搜尋引擎

    特點：
    - 隱私優先的獨立搜尋引擎
    - 索引超過300億頁面
    - 免費層可用
    - 支援時間範圍過濾

    文件：https://brave.com/search/api/
    """

    API_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Brave")

    def _do_search(
        self,
        query: str,
        api_key: str,
        max_results: int,
        days: int = 7,
        search_lang: Optional[str] = None,
        country: Optional[str] = None,
    ) -> SearchResponse:
        """執行 Brave 搜尋"""
        try:
            # 請求頭
            headers = {
                'X-Subscription-Token': api_key,
                'Accept': 'application/json'
            }

            # 確定時間範圍（freshness 引數）
            if days <= 1:
                freshness = "pd"  # Past day (24小時)
            elif days <= 7:
                freshness = "pw"  # Past week
            elif days <= 30:
                freshness = "pm"  # Past month
            else:
                freshness = "py"  # Past year

            # 請求引數
            params = {
                "q": query,
                "count": min(max_results, 20),  # Brave 最大支援20條
                "freshness": freshness,
                "safesearch": "moderate"
            }
            if search_lang:
                params["search_lang"] = search_lang
            if country:
                params["country"] = country

            # 執行搜尋（GET 請求）
            response = requests.get(
                self.API_ENDPOINT,
                headers=headers,
                params=params,
                timeout=10
            )

            # 檢查HTTP狀態碼
            if response.status_code != 200:
                error_msg = self._parse_error(response)
                logger.warning(f"[Brave] 搜尋失敗: {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            # 解析響應
            try:
                data = response.json()
            except ValueError as e:
                error_msg = f"響應JSON解析失敗: {str(e)}"
                logger.error(f"[Brave] {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            logger.info(f"[Brave] 搜尋完成，query='{query}'")
            logger.debug(f"[Brave] 原始響應: {data}")

            # 解析搜尋結果
            results = []
            web_data = data.get('web', {})
            web_results = web_data.get('results', [])

            for item in web_results[:max_results]:
                # 解析釋出日期（ISO 8601 格式）
                published_date = None
                age = item.get('age') or item.get('page_age')
                if age:
                    try:
                        # 轉換 ISO 格式為簡單日期字串
                        dt = datetime.fromisoformat(age.replace('Z', '+00:00'))
                        published_date = dt.strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        published_date = age  # 解析失敗時使用原始值

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=item.get('description', '')[:500],  # 擷取到500字元
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=published_date
                ))

            logger.info(f"[Brave] 成功解析 {len(results)} 條結果")

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True
            )

        except requests.exceptions.Timeout:
            error_msg = "請求超時"
            logger.error(f"[Brave] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"網路請求失敗: {str(e)}"
            logger.error(f"[Brave] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            error_msg = f"未知錯誤: {str(e)}"
            logger.error(f"[Brave] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )

    def _parse_error(self, response) -> str:
        """解析錯誤響應"""
        try:
            if response.headers.get('content-type', '').startswith('application/json'):
                error_data = response.json()
                # Brave API 返回的錯誤格式
                if 'message' in error_data:
                    return error_data['message']
                if 'error' in error_data:
                    return error_data['error']
                return str(error_data)
            return response.text[:200]
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'

    def search(
        self,
        query: str,
        max_results: int = 5,
        days: int = 7,
        search_lang: Optional[str] = None,
        country: Optional[str] = None,
    ) -> SearchResponse:
        """執行 Brave 搜尋，可按呼叫方傳入區域與語言偏好。"""
        if search_lang is None and country is None:
            return super().search(query, max_results=max_results, days=days)

        return self._execute_search(
            query,
            max_results=max_results,
            days=days,
            search_lang=search_lang,
            country=country,
        )


class SearXNGSearchProvider(BaseSearchProvider):
    """
    SearXNG search engine (self-hosted, no quota).

    Self-hosted instances are used when explicitly configured. Public discovery
    is disabled by default and must be explicitly enabled by callers.
    """

    PUBLIC_INSTANCES_URL = "https://searx.space/data/instances.json"
    PUBLIC_INSTANCES_CACHE_TTL_SECONDS = 3600
    PUBLIC_INSTANCES_STALE_REFRESH_BACKOFF_SECONDS = 60
    PUBLIC_INSTANCES_POOL_LIMIT = 20
    PUBLIC_INSTANCES_MAX_ATTEMPTS = 3
    PUBLIC_INSTANCES_TIMEOUT_SECONDS = 5
    SELF_HOSTED_TIMEOUT_SECONDS = 10

    _public_instances_cache: Optional[Tuple[float, List[str]]] = None
    _public_instances_stale_retry_after: float = 0.0
    _public_instances_lock = threading.Lock()

    def __init__(self, base_urls: Optional[List[str]] = None, *, use_public_instances: bool = False):
        normalized_base_urls = []
        for url in (base_urls or []):
            if not url.strip():
                continue
            if self._is_local_base_url(url):
                normalized_base_urls.append(url.rstrip("/"))
            else:
                logger.warning(
                    "SearXNG base URL %r is not a loopback address and will be ignored; "
                    "only localhost/127.0.0.1/::1 URLs are permitted in server-safe mode.",
                    url.strip(),
                )
        super().__init__(normalized_base_urls, "SearXNG")
        self._base_urls = normalized_base_urls
        self._use_public_instances = bool(use_public_instances and not self._base_urls)
        self._cursor = 0
        self._cursor_lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        return bool(self._base_urls) or self._use_public_instances

    @staticmethod
    def _is_local_base_url(url: str) -> bool:
        parsed = urlparse((url or "").strip())
        host = (parsed.hostname or "").strip().lower()
        return parsed.scheme in {"http", "https"} and host in {"127.0.0.1", "localhost", "::1"}

    @classmethod
    def reset_public_instance_cache(cls) -> None:
        """Reset the shared searx.space cache (used by tests)."""
        with cls._public_instances_lock:
            cls._public_instances_cache = None
            cls._public_instances_stale_retry_after = 0.0

    @staticmethod
    def _parse_http_error(response) -> str:
        """Parse HTTP error details for easier diagnostics."""
        try:
            raw_content_type = response.headers.get("content-type", "")
            content_type = raw_content_type if isinstance(raw_content_type, str) else ""
            if "json" in content_type:
                error_data = response.json()
                if isinstance(error_data, dict):
                    message = error_data.get("error") or error_data.get("message")
                    if message:
                        return str(message)
                return str(error_data)
            raw_text = getattr(response, "text", "")
            body = raw_text.strip() if isinstance(raw_text, str) else ""
            return body[:200] if body else f"HTTP {response.status_code}"
        except Exception:
            raw_text = getattr(response, "text", "")
            body = raw_text if isinstance(raw_text, str) else ""
            return f"HTTP {response.status_code}: {body[:200]}"

    @staticmethod
    def _time_range(days: int) -> str:
        if days <= 1:
            return "day"
        if days <= 7:
            return "week"
        if days <= 30:
            return "month"
        return "year"

    @classmethod
    def _search_latency_seconds(cls, instance_data: Dict[str, Any]) -> float:
        timing = (instance_data.get("timing") or {}).get("search") or {}
        all_timing = timing.get("all")
        if isinstance(all_timing, dict):
            for key in ("mean", "median"):
                value = all_timing.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        return float("inf")

    @classmethod
    def _extract_public_instances(cls, payload: Any) -> List[str]:
        if not isinstance(payload, dict):
            return []

        instances = payload.get("instances")
        if not isinstance(instances, dict):
            return []

        ranked: List[Tuple[float, float, str]] = []
        for raw_url, item in instances.items():
            if not isinstance(raw_url, str) or not isinstance(item, dict):
                continue
            if item.get("network_type") != "normal":
                continue
            http_status = (item.get("http") or {}).get("status_code")
            if http_status != 200:
                continue
            timing = (item.get("timing") or {}).get("search") or {}
            uptime = timing.get("success_percentage")
            if not isinstance(uptime, (int, float)) or float(uptime) <= 0:
                continue

            ranked.append(
                (
                    float(uptime),
                    cls._search_latency_seconds(item),
                    raw_url.rstrip("/"),
                )
            )

        ranked.sort(key=lambda row: (-row[0], row[1], row[2]))
        return [url for _, _, url in ranked[: cls.PUBLIC_INSTANCES_POOL_LIMIT]]

    @classmethod
    def _get_public_instances(cls) -> List[str]:
        now = time.time()
        with cls._public_instances_lock:
            stale_urls: List[str] = []
            if cls._public_instances_cache is None and cls._public_instances_stale_retry_after > now:
                logger.debug(
                    "[SearXNG] 公共例項冷啟動重新整理退避中，剩餘 %.0fs",
                    cls._public_instances_stale_retry_after - now,
                )
                return []
            if cls._public_instances_cache is not None:
                cached_at, cached_urls = cls._public_instances_cache
                if now - cached_at < cls.PUBLIC_INSTANCES_CACHE_TTL_SECONDS:
                    return list(cached_urls)
                stale_urls = list(cached_urls)
                if cls._public_instances_stale_retry_after > now:
                    logger.debug(
                        "[SearXNG] 公共例項重新整理退避中，繼續使用過期快取，剩餘 %.0fs",
                        cls._public_instances_stale_retry_after - now,
                    )
                    return stale_urls

            try:
                response = requests.get(
                    cls.PUBLIC_INSTANCES_URL,
                    timeout=cls.PUBLIC_INSTANCES_TIMEOUT_SECONDS,
                )
                if response.status_code != 200:
                    logger.warning(
                        "[SearXNG] 拉取公共例項列表失敗: HTTP %s",
                        response.status_code,
                    )
                else:
                    urls = cls._extract_public_instances(response.json())
                    if urls:
                        cls._public_instances_cache = (now, list(urls))
                        cls._public_instances_stale_retry_after = 0.0
                        logger.info("[SearXNG] 已重新整理公共例項池，共 %s 個候選例項", len(urls))
                        return list(urls)
                    logger.warning("[SearXNG] searx.space 未返回可用公共例項，保留已有快取")
            except Exception as exc:
                logger.warning("[SearXNG] 拉取公共例項列表失敗: %s", exc)

            if stale_urls:
                cls._public_instances_stale_retry_after = (
                    now + cls.PUBLIC_INSTANCES_STALE_REFRESH_BACKOFF_SECONDS
                )
                logger.warning(
                    "[SearXNG] 公共例項重新整理失敗，繼續使用過期快取，共 %s 個候選例項；"
                    "%.0fs 內不再重新整理",
                    len(stale_urls),
                    cls.PUBLIC_INSTANCES_STALE_REFRESH_BACKOFF_SECONDS,
                )
                return stale_urls
            cls._public_instances_stale_retry_after = (
                now + cls.PUBLIC_INSTANCES_STALE_REFRESH_BACKOFF_SECONDS
            )
            logger.warning(
                "[SearXNG] 公共例項冷啟動重新整理失敗，%.0fs 內不再重新整理",
                cls.PUBLIC_INSTANCES_STALE_REFRESH_BACKOFF_SECONDS,
            )
            return []

    def _rotate_candidates(self, pool: List[str], *, max_attempts: int) -> List[str]:
        if not pool or max_attempts <= 0:
            return []
        with self._cursor_lock:
            start = self._cursor % len(pool)
            self._cursor = (self._cursor + 1) % len(pool)
        ordered = pool[start:] + pool[:start]
        return ordered[:max_attempts]

    def _do_search(  # type: ignore[override]
        self,
        query: str,
        base_url: str,
        max_results: int,
        days: int = 7,
        *,
        timeout: int,
        retry_enabled: bool,
    ) -> SearchResponse:
        """Execute one SearXNG search against a specific instance."""
        try:
            base = base_url.rstrip("/")
            search_url = base if base.endswith("/search") else base + "/search"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            params = {
                "q": query,
                "format": "json",
                "time_range": self._time_range(days),
                "pageno": 1,
            }

            request_get = _get_with_retry if retry_enabled else requests.get
            ssl_verify = not self._is_local_base_url(base_url)
            response = request_get(search_url, headers=headers, params=params, timeout=timeout, verify=ssl_verify)

            if response.status_code != 200:
                error_msg = self._parse_http_error(response)
                if response.status_code == 403:
                    error_msg = (
                        f"{error_msg}；SearXNG 例項可能未啟用 JSON 輸出（請檢查 settings.yml），"
                        "或例項/代理拒絕了本次訪問"
                    )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg,
                )

            try:
                data = response.json()
            except Exception:
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message="響應JSON解析失敗",
                )

            if not isinstance(data, dict):
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message="響應格式無效",
                )

            raw = data.get("results", [])
            if not isinstance(raw, list):
                raw = []

            results = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                url_val = item.get("url")
                if not url_val:
                    continue
                raw_published_date = item.get("publishedDate")

                snippet = (item.get("content") or item.get("description") or "")[:500]
                published_date = None
                if raw_published_date:
                    try:
                        dt = datetime.fromisoformat(raw_published_date.replace("Z", "+00:00"))
                        published_date = dt.strftime("%Y-%m-%d")
                    except (ValueError, AttributeError):
                        published_date = raw_published_date

                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        snippet=snippet,
                        url=url_val,
                        source=self._extract_domain(url_val),
                        published_date=published_date,
                    )
                )
                if len(results) >= max_results:
                    break

            return SearchResponse(query=query, results=results, provider=self.name, success=True)

        except requests.exceptions.Timeout:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="請求超時",
            )
        except requests.exceptions.RequestException as e:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=f"網路請求失敗: {e}",
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=f"未知錯誤: {e}",
            )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL as source label."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            return domain or "未知來源"
        except Exception:
            return "未知來源"

    def search(self, query: str, max_results: int = 5, days: int = 7) -> SearchResponse:
        """Execute SearXNG search with instance rotation and per-request failover."""
        start_time = time.time()
        if self._base_urls:
            candidates = self._rotate_candidates(
                self._base_urls,
                max_attempts=len(self._base_urls),
            )
            retry_enabled = True
            timeout = self.SELF_HOSTED_TIMEOUT_SECONDS
            empty_error = "SearXNG 未配置可用例項"
        elif self._use_public_instances:
            public_instances = self._get_public_instances()
            candidates = self._rotate_candidates(
                public_instances,
                max_attempts=min(len(public_instances), self.PUBLIC_INSTANCES_MAX_ATTEMPTS),
            )
            retry_enabled = False
            timeout = self.PUBLIC_INSTANCES_TIMEOUT_SECONDS
            empty_error = "未獲取到可用的公共 SearXNG 例項"
        else:
            candidates = []
            retry_enabled = False
            timeout = self.PUBLIC_INSTANCES_TIMEOUT_SECONDS
            empty_error = "SearXNG 未配置可用例項"

        if not candidates:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=empty_error,
                search_time=time.time() - start_time,
            )

        errors: List[str] = []
        for base_url in candidates:
            response = self._do_search(
                query,
                base_url,
                max_results,
                days=days,
                timeout=timeout,
                retry_enabled=retry_enabled,
            )
            response.search_time = time.time() - start_time
            if response.success:
                logger.info(
                    "[%s] 搜尋 '%s' 成功，例項=%s，返回 %s 條結果，耗時 %.2fs",
                    self.name,
                    query,
                    base_url,
                    len(response.results),
                    response.search_time,
                )
                return response

            errors.append(f"{base_url}: {response.error_message or '未知錯誤'}")
            logger.warning("[%s] 例項 %s 搜尋失敗: %s", self.name, base_url, response.error_message)

        elapsed = time.time() - start_time
        return SearchResponse(
            query=query,
            results=[],
            provider=self.name,
            success=False,
            error_message="；".join(errors[:3]) if errors else empty_error,
            search_time=elapsed,
        )


class SearchService:
    """
    搜尋服務
    
    功能：
    1. 管理多個搜尋引擎
    2. 自動故障轉移
    3. 結果聚合和格式化
    4. 資料來源失敗時的增強搜尋（股價、走勢等）
    5. 港股/美股自動使用英文搜尋關鍵詞
    """
    
    # 增強搜尋關鍵詞模板（A股 中文）
    ENHANCED_SEARCH_KEYWORDS = [
        "{name} 股票 今日 股價",
        "{name} {code} 最新 行情 走勢",
        "{name} 股票 分析 走勢圖",
        "{name} K線 技術分析",
        "{name} {code} 漲跌 成交量",
    ]

    # 增強搜尋關鍵詞模板（港股/美股 英文）
    ENHANCED_SEARCH_KEYWORDS_EN = [
        "{name} stock price today",
        "{name} {code} latest quote trend",
        "{name} stock analysis chart",
        "{name} technical analysis",
        "{name} {code} performance volume",
    ]
    NEWS_OVERSAMPLE_FACTOR = 2
    NEWS_OVERSAMPLE_MAX = 10
    FUTURE_TOLERANCE_DAYS = 1
    _CHINESE_TEXT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
    _US_STOCK_RE = re.compile(r"^[A-Za-z]{1,5}([.\-][A-Za-z])?$")
    _DIRECT_NEWS_CATEGORY = "direct_company_news"
    _SECTOR_NEWS_CATEGORY = "sector_related_news"
    _MACRO_NEWS_CATEGORY = "macro_market_news"
    _NEWS_CATEGORY_PRIORITY = {
        _DIRECT_NEWS_CATEGORY: 0,
        _SECTOR_NEWS_CATEGORY: 1,
        _MACRO_NEWS_CATEGORY: 2,
    }
    _AMBIGUOUS_EN_COMPANY_NAMES = {"apple", "meta", "square", "target", "gap"}
    _AMBIGUOUS_EN_CONFIRMING_EVENT_TERMS = (
        "earnings", "revenue", "profit", "guidance", "filing", "buyback",
        "dividend", "lawsuit", "merger", "acquisition",
    )
    _COMPANY_EVENT_TERMS = (
        "公告", "披露", "釋出", "收購", "回購", "減持", "增持", "訴訟", "處罰",
        "業績", "財報", "營收", "淨利潤", "分紅", "董事會", "股東大會", "訂單",
        "合作", "中標", "earnings", "revenue", "profit", "guidance", "filing",
        "sec", "shares", "stock", "buyback", "dividend", "lawsuit", "merger",
        "acquisition", "results", "quarterly", "annual", "announces", "launches",
    )
    _SECTOR_NEWS_TERMS = (
        "行業", "板塊", "產業鏈", "龍頭", "概念股", "賽道", "sector", "industry",
        "peers", "competitors", "supply chain", "market share",
    )
    _MACRO_NEWS_TERMS = (
        "大盤", "市場", "指數", "宏觀", "央行", "利率", "通脹", "a股", "港股",
        "美股", "納指", "標普", "market", "index", "fed", "inflation",
        "interest rate", "nasdaq", "s&p 500", "dow jones",
    )
    _OFFICIAL_SOURCE_TERMS = (
        "cninfo", "sse.com", "szse.cn", "hkexnews", "sec.gov", "nasdaq.com",
        "nyse.com", "上交所", "深交所", "港交所", "證券交易所",
    )
    _TW_NEWS_ENGLISH_ALIASES_BY_CODE = {
        "2330": ["TSMC Taiwan Semiconductor"],
        "2454": ["MediaTek"],
        "2317": ["Hon Hai Foxconn"],
        "3008": ["Largan Precision", "Largan stock"],
    }
    _TW_NEWS_IDENTITY_ALIASES_BY_CODE = {
        "2330": ["台積電", "TSMC", "Taiwan Semiconductor"],
        "2454": ["聯發科", "MediaTek"],
        "2317": ["鴻海精密", "Hon Hai", "Foxconn"],
        "3008": ["大立光", "大立光精密", "Largan", "Largan Precision"],
    }
    _US_NEWS_TOPIC_VARIANTS_BY_CODE = {
        "AAPL": ["Apple iPhone services market news"],
        "NVDA": [
            "NVIDIA earnings AI GPU stock news",
            "Nvidia latest market news",
            "NVIDIA AI chip GPU data center earnings",
        ],
    }

    def __init__(
        self,
        bocha_keys: Optional[List[str]] = None,
        tavily_keys: Optional[List[str]] = None,
        anspire_keys: Optional[List[str]] = None,
        brave_keys: Optional[List[str]] = None,
        serpapi_keys: Optional[List[str]] = None,
        minimax_keys: Optional[List[str]] = None,
        searxng_base_urls: Optional[List[str]] = None,
        searxng_public_instances_enabled: bool = False,
        news_max_age_days: int = 3,
        news_strategy_profile: str = "short",
    ):
        """
        初始化搜尋服務

        Args:
            bocha_keys: 博查搜尋 API Key 列表
            tavily_keys: Tavily API Key 列表
            anspire_keys: Anspire Search API Key 列表
            brave_keys: Brave Search API Key 列表
            serpapi_keys: SerpAPI Key 列表
            minimax_keys: MiniMax API Key 列表
            searxng_base_urls: SearXNG 例項地址列表（自建無配額兜底）
            searxng_public_instances_enabled: 未配置自建例項時，是否自動使用公共 SearXNG 例項（預設關閉）
            news_max_age_days: 新聞最大時效（天）
            news_strategy_profile: 新聞視窗策略檔位（ultra_short/short/medium/long）
        """
        self._providers: List[BaseSearchProvider] = []
        self.news_max_age_days = max(1, news_max_age_days)
        raw_profile = (news_strategy_profile or "short").strip().lower()
        self.news_strategy_profile = normalize_news_strategy_profile(news_strategy_profile)
        if raw_profile != self.news_strategy_profile:
            logger.warning(
                "NEWS_STRATEGY_PROFILE '%s' 無效，已回退為 'short'",
                news_strategy_profile,
            )
        self.news_window_days = resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )
        self.news_profile_days = NEWS_STRATEGY_WINDOWS.get(
            self.news_strategy_profile,
            NEWS_STRATEGY_WINDOWS["short"],
        )

        fixture_mode = os.getenv("DSA_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
        external_network_enabled = os.getenv("DSA_ALLOW_EXTERNAL_NETWORK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        external_providers_allowed = external_network_enabled and not fixture_mode

        # 初始化搜尋引擎（按優先順序排序）
        # 1. Bocha 優先（中文搜尋最佳化，AI摘要）
        if bocha_keys and external_providers_allowed:
            self._providers.append(BochaSearchProvider(bocha_keys))
            logger.info(f"已配置 Bocha 搜尋，共 {len(bocha_keys)} 個 API Key")

        # 2. Tavily（免費額度更多，每月 1000 次）
        if tavily_keys and external_providers_allowed:
            self._providers.append(TavilySearchProvider(tavily_keys))
            logger.info(f"已配置 Tavily 搜尋，共 {len(tavily_keys)} 個 API Key")

        # 3. Brave Search（隱私優先，全球覆蓋）
        if brave_keys and external_providers_allowed:
            self._providers.append(BraveSearchProvider(brave_keys))
            logger.info(f"已配置 Brave 搜尋，共 {len(brave_keys)} 個 API Key")

        # 4. SerpAPI 作為備選（每月 100 次）
        if serpapi_keys and external_providers_allowed:
            self._providers.append(SerpAPISearchProvider(serpapi_keys))
            logger.info(f"已配置 SerpAPI 搜尋，共 {len(serpapi_keys)} 個 API Key")

        # 5. MiniMax（Coding Plan Web Search，結構化結果）
        if minimax_keys and external_providers_allowed:
            self._providers.append(MiniMaxSearchProvider(minimax_keys))
            logger.info(f"已配置 MiniMax 搜尋，共 {len(minimax_keys)} 個 API Key")

        allow_public_searxng = bool(
            searxng_public_instances_enabled
            and not searxng_base_urls
            and not fixture_mode
            and external_network_enabled
        )

        # 6. SearXNG（本機自建例項優先；公共發現必須顯式啟用且不在 fixture/no-network 模式）
        searxng_provider = SearXNGSearchProvider(
            searxng_base_urls,
            use_public_instances=allow_public_searxng,
        )
        if searxng_provider.is_available:
            self._providers.append(searxng_provider)
            if searxng_provider._base_urls:
                logger.info("已配置 SearXNG 搜尋，共 %s 個本機自建例項", len(searxng_provider._base_urls))
            else:
                logger.info("已啟用 SearXNG 公共例項自動發現模式")

        # 7. Anspire Search（實時智慧搜尋最佳化）
        if anspire_keys and external_providers_allowed:
            self._providers.insert(0, AnspireSearchProvider(anspire_keys))
            logger.info(f"已配置 Anspire Search 搜尋，共 {len(anspire_keys)} 個 API Key")
            
        if not self._providers:
            logger.warning("未配置任何搜尋能力，新聞搜尋功能將不可用")

        # In-memory search result cache: {cache_key: (timestamp, SearchResponse)}
        self._cache: Dict[str, Tuple[float, 'SearchResponse']] = {}
        self._cache_lock = threading.RLock()
        self._cache_inflight: Dict[str, threading.Event] = {}
        # Default cache TTL in seconds (10 minutes)
        self._cache_ttl: int = 600
        logger.info(
            "新聞時效策略已啟用: profile=%s, profile_days=%s, NEWS_MAX_AGE_DAYS=%s, effective_window=%s",
            self.news_strategy_profile,
            self.news_profile_days,
            self.news_max_age_days,
            self.news_window_days,
        )
    
    @staticmethod
    def _is_foreign_stock(stock_code: str) -> bool:
        """判斷是否為港股或美股"""
        code = stock_code.strip()
        # 美股：1-5個大寫字母，可能包含點（如 BRK.B）
        if SearchService._US_STOCK_RE.match(code):
            return True
        # 港股：帶 hk 字首或 5位純數字
        lower = code.lower()
        if lower.startswith('hk'):
            return True
        if code.isdigit() and len(code) == 5:
            return True
        return False

    @classmethod
    def _contains_chinese_text(cls, value: Optional[str]) -> bool:
        """Return True when the input contains CJK characters."""
        return bool(value and cls._CHINESE_TEXT_RE.search(value))

    @classmethod
    def _is_us_stock(cls, stock_code: str) -> bool:
        """判斷是否為美股/美股指數程式碼。"""
        code = (stock_code or "").strip().upper()
        return bool(cls._US_STOCK_RE.match(code) or is_us_index_code(code))

    @classmethod
    def _should_prefer_chinese_news(
        cls,
        stock_code: str,
        stock_name: str,
        focus_keywords: Optional[List[str]] = None,
    ) -> bool:
        """A 股或中文名稱/關鍵詞場景下優先中文資訊。

        Only returns True when there is a positive Chinese signal:
        Chinese characters in keywords/stock_name, or a 6-digit A-stock code.
        Avoids false positives for non-foreign but English contexts like
        ``stock_code="market", stock_name="US market"``.
        """
        if any(cls._contains_chinese_text(keyword) for keyword in (focus_keywords or [])):
            return True
        if cls._contains_chinese_text(stock_name):
            return True
        # Positive A-stock identification: 6-digit numeric codes (e.g. 600519)
        code = (stock_code or "").strip()
        return code.isdigit() and len(code) == 6

    @classmethod
    def _is_chinese_news_result(cls, item: SearchResult) -> bool:
        """Heuristic check for Chinese-language news items."""
        return cls._contains_chinese_text(" ".join(filter(None, [item.title, item.snippet, item.source])))

    @classmethod
    def _prioritize_news_language(
        cls,
        response: SearchResponse,
        *,
        prefer_chinese: bool,
    ) -> Tuple[SearchResponse, int]:
        """Reorder results by preferred language and return preferred-result count."""
        if not prefer_chinese or not response.success or not response.results:
            return response, 0

        chinese_results: List[SearchResult] = []
        other_results: List[SearchResult] = []
        for item in response.results:
            if cls._is_chinese_news_result(item):
                chinese_results.append(item)
            else:
                other_results.append(item)

        return (
            SearchResponse(
                query=response.query,
                results=chinese_results + other_results,
                provider=response.provider,
                success=response.success,
                error_message=response.error_message,
                search_time=response.search_time,
            ),
            len(chinese_results),
        )

    @classmethod
    def _is_better_preferred_news_response(
        cls,
        candidate: SearchResponse,
        *,
        candidate_preferred_count: int,
        best_response: Optional[SearchResponse],
        best_preferred_count: int,
    ) -> bool:
        """Prefer responses with more Chinese items, then more total items."""
        if best_response is None:
            return True
        if candidate_preferred_count != best_preferred_count:
            return candidate_preferred_count > best_preferred_count
        return len(candidate.results) > len(best_response.results)

    @classmethod
    def _brave_search_locale(
        cls,
        stock_code: str,
        *,
        prefer_chinese: bool,
    ) -> Dict[str, str]:
        """Resolve Brave locale hints without forcing US bias onto non-US symbols."""
        if prefer_chinese:
            return {"search_lang": "zh-hans", "country": "CN"}
        if cls._is_us_stock(stock_code):
            return {"search_lang": "en", "country": "US"}
        return {}

    # A-share ETF code prefixes (Shanghai 51/52/56/58, Shenzhen 15/16/18)
    _A_ETF_PREFIXES = ('51', '52', '56', '58', '15', '16', '18')
    _ETF_NAME_KEYWORDS = ('ETF', 'FUND', 'TRUST', 'INDEX', 'TRACKER', 'UNIT')  # US/HK ETF name hints

    @staticmethod
    def is_index_or_etf(stock_code: str, stock_name: str) -> bool:
        """
        Judge if symbol is index-tracking ETF or market index.
        For such symbols, analysis focuses on index movement only, not issuer company risks.
        """
        code = (stock_code or '').strip().split('.')[0]
        if not code:
            return False
        # A-share ETF
        if code.isdigit() and len(code) == 6 and code.startswith(SearchService._A_ETF_PREFIXES):
            return True
        # US index (SPX, DJI, IXIC etc.)
        if is_us_index_code(code):
            return True
        # US/HK ETF: foreign symbol + name contains fund-like keywords
        if SearchService._is_foreign_stock(code):
            name_upper = (stock_name or '').upper()
            return any(kw in name_upper for kw in SearchService._ETF_NAME_KEYWORDS)
        return False

    @property
    def is_available(self) -> bool:
        """檢查是否有可用的搜尋引擎"""
        return any(p.is_available for p in self._providers)

    def _cache_key(self, query: str, max_results: int, days: int) -> str:
        """Build a cache key from query parameters."""
        return f"{query}|{max_results}|{days}"

    def _get_cached_locked(self, key: str) -> Optional['SearchResponse']:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, response = entry
        if time.time() - ts > self._cache_ttl:
            self._cache.pop(key, None)
            return None
        logger.debug(f"Search cache hit: {key[:60]}...")
        return response

    def _get_cached(self, key: str) -> Optional['SearchResponse']:
        """Return cached SearchResponse if still valid, else None."""
        with self._cache_lock:
            return self._get_cached_locked(key)

    def _get_cached_or_reserve(
        self,
        key: str,
    ) -> Tuple[Optional['SearchResponse'], bool, Optional[threading.Event]]:
        with self._cache_lock:
            cached = self._get_cached_locked(key)
            if cached is not None:
                return cached, False, None

            event = self._cache_inflight.get(key)
            if event is None:
                event = threading.Event()
                self._cache_inflight[key] = event
                return None, True, event
            return None, False, event

    def _release_cache_fill(self, key: str, event: threading.Event) -> None:
        with self._cache_lock:
            current = self._cache_inflight.get(key)
            if current is event:
                self._cache_inflight.pop(key, None)
                event.set()

    def _wait_for_cached(self, key: str, event: threading.Event) -> Optional['SearchResponse']:
        event.wait(timeout=max(1.0, min(float(self._cache_ttl), 30.0)))
        return self._get_cached(key)

    def _put_cache(self, key: str, response: 'SearchResponse') -> None:
        """Store a successful SearchResponse in cache."""
        with self._cache_lock:
            # Hard cap: evict oldest entries when cache exceeds limit
            _MAX_CACHE_SIZE = 500
            if len(self._cache) >= _MAX_CACHE_SIZE:
                now = time.time()
                # First pass: remove expired entries
                expired = [k for k, (ts, _) in self._cache.items() if now - ts > self._cache_ttl]
                for k in expired:
                    self._cache.pop(k, None)
                # Second pass: if still over limit, evict oldest entries (FIFO)
                if len(self._cache) >= _MAX_CACHE_SIZE:
                    excess = len(self._cache) - _MAX_CACHE_SIZE + 1
                    oldest = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])[:excess]
                    for k in oldest:
                        self._cache.pop(k, None)
            self._cache[key] = (time.time(), response)

    def _effective_news_window_days(self) -> int:
        """Resolve effective news window from strategy profile and global max-age."""
        return resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )

    @classmethod
    def _provider_request_size(cls, max_results: int) -> int:
        """Apply light overfetch before time filtering to avoid sparse outputs."""
        target = max(1, int(max_results))
        return max(target, min(target * cls.NEWS_OVERSAMPLE_FACTOR, cls.NEWS_OVERSAMPLE_MAX))

    @staticmethod
    def _is_tw_stock_code(stock_code: str) -> bool:
        """Return True for common Taiwan listed stock codes."""
        code = (stock_code or "").strip()
        return code.isdigit() and len(code) == 4

    @classmethod
    def _news_query_variants(
        cls,
        stock_code: str,
        stock_name: str,
        *,
        focus_keywords: Optional[List[str]] = None,
        prefer_chinese: bool = False,
    ) -> List[str]:
        """Build ordered related-info/news queries for one stock."""
        code = (stock_code or "").strip()
        name = (stock_name or "").strip()

        if focus_keywords:
            focused = " ".join(item.strip() for item in focus_keywords if item and item.strip())
            return [focused] if focused else []

        variants: List[str] = []

        if cls._is_tw_stock_code(code):
            cls._append_unique(variants, f"{code} {name} 新聞")
            cls._append_unique(variants, f"{name} 最新消息")
            cls._append_unique(variants, f"{name} 財報 法說 產業")
            for alias in cls._TW_NEWS_ENGLISH_ALIASES_BY_CODE.get(code, []):
                cls._append_unique(variants, f"{alias} news")
            return variants

        upper_code = code.upper()
        if cls._US_STOCK_RE.match(upper_code):
            cls._append_unique(variants, f"{upper_code} {name} stock news")
            cls._append_unique(variants, f"{name} earnings stock news")
            for variant in cls._US_NEWS_TOPIC_VARIANTS_BY_CODE.get(upper_code, []):
                cls._append_unique(variants, variant)
            cls._append_unique(variants, f"{name} latest market news")
            return variants

        is_foreign = cls._is_foreign_stock(code)
        if prefer_chinese:
            cls._append_unique(variants, f"{name} {code} 股票 最新訊息")
        elif is_foreign:
            cls._append_unique(variants, f"{name} {code} stock latest news")
        else:
            cls._append_unique(variants, f"{name} {code} 股票 最新訊息")
        return variants

    @staticmethod
    def _sanitize_news_search_text(value: Any, *, max_length: int = 160) -> str:
        sanitized = sanitize_diagnostic_text(value, max_length=max_length) or ""
        return sanitized.strip()

    @classmethod
    def _sanitize_news_search_list(
        cls,
        values: List[Any],
        *,
        max_items: int = 12,
        max_length: int = 160,
    ) -> List[str]:
        cleaned: List[str] = []
        for value in values[:max_items]:
            text = cls._sanitize_news_search_text(value, max_length=max_length)
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    @staticmethod
    def _append_unique_diagnostic_value(values: List[str], value: Optional[str]) -> None:
        cleaned = (value or "").strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)

    @classmethod
    def _classify_search_error(cls, error: Any) -> str:
        if isinstance(error, TimeoutError):
            return "timeout"
        text = str(error or "").lower()
        if "timeout" in text or "timed out" in text or "超時" in text:
            return "timeout"
        return "provider_error"

    @classmethod
    def _build_news_search_diagnostics(
        cls,
        *,
        query_variants: List[str],
        providers_attempted: List[str],
        attempt_count: int,
        result_count: int,
        fallback_used: bool,
        final_status: str,
        error_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "enabled": True,
            "providers_attempted": cls._sanitize_news_search_list(
                providers_attempted,
                max_items=8,
                max_length=80,
            ),
            "query_variants": cls._sanitize_news_search_list(
                query_variants,
                max_items=12,
                max_length=180,
            ),
            "attempt_count": max(0, int(attempt_count or 0)),
            "result_count": max(0, int(result_count or 0)),
            "fallback_used": bool(fallback_used),
            "final_status": cls._sanitize_news_search_text(final_status, max_length=40) or "unknown",
        }
        cleaned_error_types = cls._sanitize_news_search_list(
            error_types or [],
            max_items=6,
            max_length=40,
        )
        if cleaned_error_types:
            payload["error_types"] = cleaned_error_types
        return {"news_search": payload}

    @classmethod
    def _attach_news_search_diagnostics(
        cls,
        response: SearchResponse,
        *,
        query_variants: List[str],
        providers_attempted: List[str],
        attempt_count: int,
        fallback_used: bool,
        final_status: str,
        error_types: Optional[List[str]] = None,
    ) -> SearchResponse:
        response.diagnostics = cls._build_news_search_diagnostics(
            query_variants=query_variants,
            providers_attempted=providers_attempted,
            attempt_count=attempt_count,
            result_count=len(response.results or []),
            fallback_used=fallback_used,
            final_status=final_status,
            error_types=error_types,
        )
        return response

    @staticmethod
    def _append_unique(values: List[str], value: Optional[str]) -> None:
        cleaned = (value or "").strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)

    @classmethod
    def _stock_code_identity_terms(cls, stock_code: str) -> List[str]:
        """Return code/ticker variants that should count as strong identity hits."""
        raw = (stock_code or "").strip()
        if not raw:
            return []

        terms: List[str] = []
        upper = raw.upper()
        code_for_variants = upper
        if "." in upper:
            base, suffix = upper.rsplit(".", 1)
            if suffix == "HK" and base.isdigit() and 1 <= len(base) <= 5:
                code_for_variants = f"HK{base.zfill(5)}"
            elif suffix in {"SH", "SZ", "SS", "BJ"} and base.isdigit() and len(base) == 6:
                code_for_variants = base
            elif suffix == "US" and re.fullmatch(r"[A-Z]{1,5}", base):
                code_for_variants = base

        is_us_ticker = bool(cls._US_STOCK_RE.match(code_for_variants))
        if not is_us_ticker:
            cls._append_unique(terms, raw)
            cls._append_unique(terms, upper)
            if code_for_variants != upper:
                cls._append_unique(terms, code_for_variants)

        lower = code_for_variants.lower()
        hk_digits = ""
        if lower.startswith("hk"):
            hk_digits = re.sub(r"\D", "", code_for_variants)
        elif code_for_variants.isdigit() and len(code_for_variants) == 5:
            hk_digits = code_for_variants

        if hk_digits:
            padded = hk_digits.zfill(5)
            short = str(int(hk_digits)) if hk_digits.isdigit() else hk_digits.lstrip("0")
            cls._append_unique(terms, padded)
            cls._append_unique(terms, f"HK{padded}")
            cls._append_unique(terms, f"{padded}.HK")
            cls._append_unique(terms, f"{short}.HK")
            cls._append_unique(terms, f"HKEX:{short}")
            return terms

        if code_for_variants.isdigit() and len(code_for_variants) == 6:
            suffix = ".SH" if code_for_variants.startswith(("5", "6", "9")) else ".SZ"
            cls._append_unique(terms, f"{code_for_variants}{suffix}")
            return terms

        if cls._US_STOCK_RE.match(code_for_variants):
            cls._append_unique(terms, f"${code_for_variants}")
            cls._append_unique(terms, f"NASDAQ:{code_for_variants}")
            cls._append_unique(terms, f"NYSE:{code_for_variants}")
            if len(code_for_variants) > 1:
                cls._append_unique(terms, code_for_variants)
            return terms

        return terms

    @classmethod
    def _company_identity_terms(cls, stock_name: str) -> List[str]:
        """Return conservative company-name variants for relevance matching."""
        raw = (stock_name or "").strip()
        if not raw:
            return []

        terms: List[str] = []
        cls._append_unique(terms, raw)

        without_market_suffix = re.sub(r"[-－（(].*$", "", raw).strip()
        cls._append_unique(terms, without_market_suffix)

        if cls._contains_chinese_text(raw):
            cleaned = re.sub(
                r"(股份有限公司|有限責任公司|有限公司|控股集團|控股|集團|股份|公司)$",
                "",
                without_market_suffix,
            ).strip()
            if len(cleaned) >= 4:
                cls._append_unique(terms, cleaned)
        else:
            cleaned = re.sub(
                r"\b(incorporated|inc|corporation|corp|company|co|plc|ltd|limited|holdings?)\.?$",
                "",
                without_market_suffix,
                flags=re.IGNORECASE,
            ).strip()
            if len(cleaned) >= 3:
                cls._append_unique(terms, cleaned)

        return terms

    @classmethod
    def _news_alias_identity_terms(cls, stock_code: str) -> List[str]:
        """Return symbol-specific aliases that should count as company identity."""
        code = (stock_code or "").strip().upper()
        terms: List[str] = []
        for alias in cls._TW_NEWS_IDENTITY_ALIASES_BY_CODE.get(code, []):
            cls._append_unique(terms, alias)
        for alias in cls._TW_NEWS_ENGLISH_ALIASES_BY_CODE.get(code, []):
            cls._append_unique(terms, alias)
        return terms

    @classmethod
    def _contains_identity_term(cls, text: str, term: str) -> bool:
        if not text or not term:
            return False

        if cls._contains_chinese_text(term):
            start = 0
            while True:
                index = text.find(term, start)
                if index < 0:
                    return False
                next_char = text[index + len(term):index + len(term) + 1]
                if next_char not in {"鎮", "村", "縣"}:
                    return True
                start = index + len(term)

        lower_text = text.lower()
        lower_term = term.lower()
        if lower_term.startswith("$"):
            return lower_term in lower_text

        pattern = r"(?<![A-Za-z0-9])" + re.escape(lower_term) + r"(?![A-Za-z0-9])"
        return bool(re.search(pattern, lower_text))

    @classmethod
    def _contains_stock_code_identity_term(cls, text: str, term: str) -> bool:
        if not text or not term:
            return False

        if cls._US_STOCK_RE.match(term) and term.upper() == term and not term.startswith("$"):
            ticker_pattern = f"(?:{re.escape(term)}|{re.escape(term.lower())})"
            pattern = (
                r"(?<![A-Za-z0-9$:.])"
                + ticker_pattern
                + r"(?=$|[^A-Za-z0-9.]|\.(?:US|us|O|o|N|n|NYSE|nyse|NASDAQ|nasdaq|AMEX|amex)\b)"
            )
            return bool(re.search(pattern, text))

        return cls._contains_identity_term(text, term)

    @classmethod
    def _contains_any_news_term(cls, text: str, terms: Tuple[str, ...]) -> bool:
        lower = (text or "").lower()
        return any(term.lower() in lower for term in terms)

    @classmethod
    def _score_news_relevance(
        cls,
        item: SearchResult,
        *,
        stock_code: str,
        stock_name: str,
    ) -> SearchResult:
        """Attach conservative, explainable relevance metadata to one news item."""
        title = item.title or ""
        snippet = item.snippet or ""
        url = item.url or ""
        source = item.source or ""
        full_text = " ".join([title, snippet, url, source])

        score = 0
        direct_signal = 0
        reasons: List[str] = []
        has_stock_code_signal = False
        has_unambiguous_company_signal = False
        has_ambiguous_company_signal = False

        def add_reason(reason: str) -> None:
            if reason not in reasons and len(reasons) < 5:
                reasons.append(reason)

        for term in cls._stock_code_identity_terms(stock_code):
            if cls._contains_stock_code_identity_term(title, term):
                score += 55
                direct_signal += 55
                has_stock_code_signal = True
                add_reason(f"標題命中股票程式碼 {term}")
                break
        else:
            for term in cls._stock_code_identity_terms(stock_code):
                if cls._contains_stock_code_identity_term(snippet, term):
                    score += 34
                    direct_signal += 34
                    has_stock_code_signal = True
                    add_reason(f"摘要命中股票程式碼 {term}")
                    break
            else:
                for term in cls._stock_code_identity_terms(stock_code):
                    if cls._contains_stock_code_identity_term(url, term):
                        score += 18
                        direct_signal += 18
                        has_stock_code_signal = True
                        add_reason(f"連結命中股票程式碼 {term}")
                        break

        for term in cls._company_identity_terms(stock_name):
            ambiguous_en = (
                not cls._contains_chinese_text(term)
                and term.lower() in cls._AMBIGUOUS_EN_COMPANY_NAMES
            )
            title_score = 26 if ambiguous_en else 45
            snippet_score = 16 if ambiguous_en else 28
            if cls._contains_identity_term(title, term):
                score += title_score
                direct_signal += title_score
                if ambiguous_en:
                    has_ambiguous_company_signal = True
                else:
                    has_unambiguous_company_signal = True
                add_reason(f"標題命中公司名 {term}")
                break
            if cls._contains_identity_term(snippet, term):
                score += snippet_score
                direct_signal += snippet_score
                if ambiguous_en:
                    has_ambiguous_company_signal = True
                else:
                    has_unambiguous_company_signal = True
                add_reason(f"摘要命中公司名 {term}")
                break

        for term in cls._news_alias_identity_terms(stock_code):
            if cls._contains_identity_term(title, term):
                score += 45
                direct_signal += 45
                has_unambiguous_company_signal = True
                add_reason(f"標題命中公司別名 {term}")
                break
            if cls._contains_identity_term(snippet, term):
                score += 28
                direct_signal += 28
                has_unambiguous_company_signal = True
                add_reason(f"摘要命中公司別名 {term}")
                break

        has_company_event = cls._contains_any_news_term(full_text, cls._COMPANY_EVENT_TERMS)
        if has_company_event and direct_signal > 0:
            score += 12
            ambiguous_name_only = (
                has_ambiguous_company_signal
                and not has_stock_code_signal
                and not has_unambiguous_company_signal
            )
            has_confirming_event = cls._contains_any_news_term(
                full_text,
                cls._AMBIGUOUS_EN_CONFIRMING_EVENT_TERMS,
            )
            if not ambiguous_name_only or has_confirming_event:
                direct_signal += 12
            add_reason("命中公告/財報/交易等公司事件詞")

        if cls._contains_any_news_term(f"{source} {url}", cls._OFFICIAL_SOURCE_TERMS):
            score += 8
            add_reason("來源接近公告或交易所通道")

        has_sector_signal = cls._contains_any_news_term(full_text, cls._SECTOR_NEWS_TERMS)
        has_macro_signal = cls._contains_any_news_term(full_text, cls._MACRO_NEWS_TERMS)

        if direct_signal >= 38:
            category = cls._DIRECT_NEWS_CATEGORY
        elif has_macro_signal and not direct_signal:
            category = cls._MACRO_NEWS_CATEGORY
            score = max(0, score - 12)
            add_reason("未命中目標公司身份，歸為宏觀/市場新聞")
        else:
            category = cls._SECTOR_NEWS_CATEGORY
            if has_sector_signal:
                score += 6
                add_reason("僅命中行業或板塊背景")
            else:
                add_reason("未命中股票程式碼或公司全稱，降級為背景新聞")

        score = max(0, min(100, score))
        return SearchResult(
            title=item.title,
            snippet=item.snippet,
            url=item.url,
            source=item.source,
            published_date=item.published_date,
            relevance_score=score,
            relevance_category=category,
            relevance_reasons=reasons,
        )

    @classmethod
    def _rank_news_response(
        cls,
        response: SearchResponse,
        *,
        stock_code: str,
        stock_name: str,
        prefer_chinese: bool,
        max_results: int,
        log_scope: str,
    ) -> SearchResponse:
        """Score and sort news so direct company items are not crowded out."""
        if not response.success or not response.results:
            return response

        scored_results = [
            cls._score_news_relevance(item, stock_code=stock_code, stock_name=stock_name)
            for item in response.results
        ]

        indexed_results = list(enumerate(scored_results))

        def sort_key(entry: Tuple[int, SearchResult]) -> Tuple[int, int, int, int]:
            index, result = entry
            category = result.relevance_category or cls._SECTOR_NEWS_CATEGORY
            category_rank = cls._NEWS_CATEGORY_PRIORITY.get(category, 9)
            language_rank = 0 if prefer_chinese and cls._is_chinese_news_result(result) else 1
            if not prefer_chinese:
                language_rank = 0
            score = result.relevance_score or 0
            return (category_rank, language_rank, -score, index)

        ranked_results = [result for _, result in sorted(indexed_results, key=sort_key)]
        limited_results = ranked_results[:max_results]
        category_counts = {
            cls._DIRECT_NEWS_CATEGORY: 0,
            cls._SECTOR_NEWS_CATEGORY: 0,
            cls._MACRO_NEWS_CATEGORY: 0,
        }
        for result in limited_results:
            if result.relevance_category in category_counts:
                category_counts[result.relevance_category] += 1
        if limited_results:
            top = limited_results[0]
            logger.info(
                "[新聞相關度] %s: direct=%s, sector=%s, macro=%s, top_score=%s, top_category=%s, reasons=%s",
                log_scope,
                category_counts[cls._DIRECT_NEWS_CATEGORY],
                category_counts[cls._SECTOR_NEWS_CATEGORY],
                category_counts[cls._MACRO_NEWS_CATEGORY],
                top.relevance_score,
                top.relevance_category,
                "；".join(top.relevance_reasons or []),
            )

        return SearchResponse(
            query=response.query,
            results=limited_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
            diagnostics=response.diagnostics,
        )

    @classmethod
    def _news_relevance_stats(
        cls,
        response: SearchResponse,
        *,
        prefer_chinese: bool,
    ) -> Dict[str, int]:
        results = response.results if response and response.results else []
        return {
            "direct_count": sum(
                1 for item in results if item.relevance_category == cls._DIRECT_NEWS_CATEGORY
            ),
            "preferred_direct_count": sum(
                1
                for item in results
                if (
                    prefer_chinese
                    and item.relevance_category == cls._DIRECT_NEWS_CATEGORY
                    and cls._is_chinese_news_result(item)
                )
            ),
            "preferred_count": sum(
                1 for item in results if prefer_chinese and cls._is_chinese_news_result(item)
            ),
            "max_score": max((item.relevance_score or 0 for item in results), default=0),
            "result_count": len(results),
        }

    @classmethod
    def _is_better_ranked_news_response(
        cls,
        candidate: SearchResponse,
        *,
        candidate_stats: Dict[str, int],
        best_response: Optional[SearchResponse],
        best_stats: Optional[Dict[str, int]],
        prefer_chinese: bool,
    ) -> bool:
        if best_response is None or best_stats is None:
            return True
        if candidate_stats["direct_count"] != best_stats["direct_count"]:
            return candidate_stats["direct_count"] > best_stats["direct_count"]
        if (
            prefer_chinese
            and candidate_stats["preferred_direct_count"] != best_stats["preferred_direct_count"]
        ):
            return candidate_stats["preferred_direct_count"] > best_stats["preferred_direct_count"]
        if prefer_chinese and candidate_stats["preferred_count"] != best_stats["preferred_count"]:
            return candidate_stats["preferred_count"] > best_stats["preferred_count"]
        if candidate_stats["max_score"] != best_stats["max_score"]:
            return candidate_stats["max_score"] > best_stats["max_score"]
        return candidate_stats["result_count"] > best_stats["result_count"]

    @staticmethod
    def _parse_relative_news_date(text: str, now: datetime) -> Optional[date]:
        """Parse common Chinese/English relative-time strings."""
        raw = (text or "").strip()
        if not raw:
            return None

        lower = raw.lower()
        if raw in {"今天", "今日", "剛剛"} or lower in {"today", "just now", "now"}:
            return now.date()
        if raw == "昨天" or lower == "yesterday":
            return (now - timedelta(days=1)).date()
        if raw == "前天":
            return (now - timedelta(days=2)).date()

        zh = re.match(r"^\s*(\d+)\s*(分鐘|小時|天|周|個月|月|年)\s*前\s*$", raw)
        if zh:
            amount = int(zh.group(1))
            unit = zh.group(2)
            if unit == "分鐘":
                return (now - timedelta(minutes=amount)).date()
            if unit == "小時":
                return (now - timedelta(hours=amount)).date()
            if unit == "天":
                return (now - timedelta(days=amount)).date()
            if unit == "周":
                return (now - timedelta(weeks=amount)).date()
            if unit in {"個月", "月"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit == "年":
                return (now - timedelta(days=amount * 365)).date()

        en = re.match(
            r"^\s*(\d+)\s*(minute|minutes|min|mins|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago\s*$",
            lower,
        )
        if en:
            amount = int(en.group(1))
            unit = en.group(2)
            if unit in {"minute", "minutes", "min", "mins"}:
                return (now - timedelta(minutes=amount)).date()
            if unit in {"hour", "hours"}:
                return (now - timedelta(hours=amount)).date()
            if unit in {"day", "days"}:
                return (now - timedelta(days=amount)).date()
            if unit in {"week", "weeks"}:
                return (now - timedelta(weeks=amount)).date()
            if unit in {"month", "months"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit in {"year", "years"}:
                return (now - timedelta(days=amount * 365)).date()

        return None

    @classmethod
    def _normalize_news_publish_date(cls, value: Any) -> Optional[date]:
        """Normalize provider date value into a date object."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                local_tz = datetime.now().astimezone().tzinfo or timezone.utc
                return value.astimezone(local_tz).date()
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None
        now = datetime.now()
        local_tz = now.astimezone().tzinfo or timezone.utc

        relative_date = cls._parse_relative_news_date(text, now)
        if relative_date:
            return relative_date

        # Unix timestamp fallback
        if text.isdigit() and len(text) in (10, 13):
            try:
                ts = int(text[:10]) if len(text) == 13 else int(text)
                # Provider timestamps are typically UTC epoch seconds.
                # Normalize to local date to keep window checks aligned with local "today".
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz).date()
            except (OSError, OverflowError, ValueError):
                pass

        iso_candidate = text.replace("Z", "+00:00")
        try:
            parsed_iso = datetime.fromisoformat(iso_candidate)
            if parsed_iso.tzinfo is not None:
                return parsed_iso.astimezone(local_tz).date()
            return parsed_iso.date()
        except ValueError:
            pass

        normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)

        try:
            parsed_rfc = parsedate_to_datetime(normalized)
            if parsed_rfc:
                if parsed_rfc.tzinfo is not None:
                    return parsed_rfc.astimezone(local_tz).date()
                return parsed_rfc.date()
        except (TypeError, ValueError):
            pass

        zh_match = re.search(r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?", text)
        if zh_match:
            try:
                return date(int(zh_match.group(1)), int(zh_match.group(2)), int(zh_match.group(3)))
            except ValueError:
                pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y%m%d",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%a, %d %b %Y %H:%M:%S %z",
        ):
            try:
                parsed_dt = datetime.strptime(normalized, fmt)
                if parsed_dt.tzinfo is not None:
                    return parsed_dt.astimezone(local_tz).date()
                return parsed_dt.date()
            except ValueError:
                continue

        return None

    def _filter_news_response(
        self,
        response: SearchResponse,
        *,
        search_days: int,
        max_results: int,
        log_scope: str,
    ) -> SearchResponse:
        """Hard-filter results by published_date recency and normalize date strings."""
        if not response.success or not response.results:
            return response

        today = datetime.now().date()
        earliest = today - timedelta(days=max(0, int(search_days) - 1))
        latest = today + timedelta(days=self.FUTURE_TOLERANCE_DAYS)

        filtered: List[SearchResult] = []
        dropped_unknown = 0
        dropped_old = 0
        dropped_future = 0

        for item in response.results:
            published = self._normalize_news_publish_date(item.published_date)
            if published is None:
                dropped_unknown += 1
                continue
            if published < earliest:
                dropped_old += 1
                continue
            if published > latest:
                dropped_future += 1
                continue

            filtered.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=published.isoformat(),
                    relevance_score=item.relevance_score,
                    relevance_category=item.relevance_category,
                    relevance_reasons=item.relevance_reasons,
                )
            )
            if len(filtered) >= max_results:
                break

        if dropped_unknown or dropped_old or dropped_future:
            logger.info(
                "[新聞過濾] %s: provider=%s, total=%s, kept=%s, drop_unknown=%s, drop_old=%s, drop_future=%s, window=[%s,%s]",
                log_scope,
                response.provider,
                len(response.results),
                len(filtered),
                dropped_unknown,
                dropped_old,
                dropped_future,
                earliest.isoformat(),
                latest.isoformat(),
            )

        return SearchResponse(
            query=response.query,
            results=filtered,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
            diagnostics=response.diagnostics,
        )

    def _normalize_and_limit_response(
        self,
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Normalize parseable dates without enforcing freshness filtering."""
        if not response.success or not response.results:
            return response

        normalized_results: List[SearchResult] = []
        for item in response.results[:max_results]:
            normalized_date = self._normalize_news_publish_date(item.published_date)
            normalized_results.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=(
                        normalized_date.isoformat() if normalized_date is not None else item.published_date
                    ),
                    relevance_score=item.relevance_score,
                    relevance_category=item.relevance_category,
                    relevance_reasons=item.relevance_reasons,
                )
            )

        return SearchResponse(
            query=response.query,
            results=normalized_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
            diagnostics=response.diagnostics,
        )

    @staticmethod
    def _limit_search_response(
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Trim response results without changing the rest of the metadata."""
        if not response.success or not response.results:
            return response

        limited_results = response.results[:max_results]
        if len(limited_results) == len(response.results):
            return response

        return SearchResponse(
            query=response.query,
            results=limited_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
            diagnostics=response.diagnostics,
        )

    def _latest_news_fallback_response(
        self,
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Keep provider latest items as a last-resort fallback after recent filtering is exhausted."""
        return self._normalize_and_limit_response(response, max_results=max_results)

    def search_stock_news(
        self,
        stock_code: str,
        stock_name: str,
        max_results: int = 5,
        focus_keywords: Optional[List[str]] = None,
        tavily_news_topic_first_variant_only: bool = False,
    ) -> SearchResponse:
        """
        搜尋股票相關新聞
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            max_results: 最大返回結果數
            focus_keywords: 重點關注的關鍵詞列表
            tavily_news_topic_first_variant_only: 僅第一組 Tavily query 使用 news topic
            
        Returns:
            SearchResponse 物件
        """
        # 策略視窗優先：ultra_short/short/medium/long = 1/3/7/30 天，
        # 並統一受 NEWS_MAX_AGE_DAYS 上限約束。
        search_days = self._effective_news_window_days()
        provider_max_results = self._provider_request_size(max_results)
        prefer_chinese = self._should_prefer_chinese_news(
            stock_code,
            stock_name,
            focus_keywords=focus_keywords,
        )

        query_variants = self._news_query_variants(
            stock_code,
            stock_name,
            focus_keywords=focus_keywords,
            prefer_chinese=prefer_chinese,
        )
        query = query_variants[0] if query_variants else f"{stock_name} {stock_code} 股票 最新訊息"
        candidate_queries = query_variants or [query]

        logger.info(
            (
                "搜尋股票新聞: %s(%s), queries=%s, 時間範圍: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s, prefer_chinese=%s), 目標條數=%s, provider請求條數=%s"
            ),
            stock_name,
            stock_code,
            query_variants,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            prefer_chinese,
            max_results,
            provider_max_results,
        )

        cache_key = self._cache_key(
            (
                f"{' || '.join(query_variants)}|target={stock_code}:{stock_name}|"
                f"news_pref={'zh' if prefer_chinese else 'default'}"
            ),
            max_results,
            search_days,
        )
        cached, cache_owner, cache_event = self._get_cached_or_reserve(cache_key)
        if cached is not None:
            logger.info(f"使用快取搜尋結果: {stock_name}({stock_code})")
            return cached

        if not cache_owner and cache_event is not None:
            cached = self._wait_for_cached(cache_key, cache_event)
            if cached is not None:
                logger.info(f"使用併發填充後的快取搜尋結果: {stock_name}({stock_code})")
                return cached
            cached, cache_owner, cache_event = self._get_cached_or_reserve(cache_key)
            if cached is not None:
                logger.info(f"使用等待後命中的快取搜尋結果: {stock_name}({stock_code})")
                return cached

        try:
            # 依次嘗試 query variants 和搜尋引擎；若過濾後為空，繼續耗盡後續查詢/引擎。
            had_provider_success = False
            best_ranked_response: Optional[SearchResponse] = None
            best_ranked_stats: Optional[Dict[str, int]] = None
            best_latest_fallback_response: Optional[SearchResponse] = None
            best_latest_fallback_stats: Optional[Dict[str, int]] = None
            last_error_message: Optional[str] = None
            providers_attempted: List[str] = []
            error_types: List[str] = []
            attempt_count = 0
            fallback_used = False

            for query_index, candidate_query in enumerate(candidate_queries, 1):
                for provider in self._providers:
                    if not provider.is_available:
                        continue

                    search_kwargs: Dict[str, Any] = {}
                    if isinstance(provider, TavilySearchProvider):
                        if not tavily_news_topic_first_variant_only or query_index == 1:
                            search_kwargs["topic"] = "news"
                    elif isinstance(provider, BraveSearchProvider):
                        search_kwargs.update(
                            self._brave_search_locale(
                                stock_code,
                                prefer_chinese=prefer_chinese,
                            )
                        )

                    provider_name = self._sanitize_news_search_text(
                        getattr(provider, "name", provider.__class__.__name__),
                        max_length=80,
                    ) or "unknown"
                    self._append_unique_diagnostic_value(providers_attempted, provider_name)
                    attempt_count += 1

                    try:
                        response = provider.search(
                            candidate_query,
                            max_results=provider_max_results,
                            days=search_days,
                            **search_kwargs,
                        )
                    except Exception as exc:  # pragma: no cover - defensive provider boundary
                        error_type = self._classify_search_error(exc)
                        self._append_unique_diagnostic_value(error_types, error_type)
                        last_error_message = sanitize_diagnostic_text(exc) or type(exc).__name__
                        fallback_used = True
                        logger.warning(
                            "%s query[%s/%s] 搜尋異常: %s，繼續嘗試下一路徑",
                            provider_name,
                            query_index,
                            len(candidate_queries),
                            last_error_message,
                        )
                        continue

                    filtered_response = self._filter_news_response(
                        response,
                        search_days=search_days,
                        max_results=provider_max_results,
                        log_scope=f"{stock_code}:{provider.name}:stock_news:q{query_index}",
                    )
                    had_provider_success = had_provider_success or bool(response.success)

                    if filtered_response.success and filtered_response.results:
                        language_response, _preferred_count = self._prioritize_news_language(
                            filtered_response,
                            prefer_chinese=prefer_chinese,
                        )
                        ranked_response = self._rank_news_response(
                            language_response,
                            stock_code=stock_code,
                            stock_name=stock_name,
                            prefer_chinese=prefer_chinese,
                            max_results=provider_max_results,
                            log_scope=f"{stock_code}:{provider.name}:stock_news:q{query_index}",
                        )
                        limited_response = self._limit_search_response(
                            ranked_response,
                            max_results=max_results,
                        )
                        stats = self._news_relevance_stats(
                            limited_response,
                            prefer_chinese=prefer_chinese,
                        )
                        if self._is_better_ranked_news_response(
                            limited_response,
                            candidate_stats=stats,
                            best_response=best_ranked_response,
                            best_stats=best_ranked_stats,
                            prefer_chinese=prefer_chinese,
                        ):
                            best_ranked_response = limited_response
                            best_ranked_stats = stats

                        if stats["direct_count"] > 0 and (
                            not prefer_chinese or stats["preferred_direct_count"] > 0
                        ):
                            logger.info(
                                "%s query[%s/%s] 搜尋成功，識別到 %s 條直接個股新聞，優先返回",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                                stats["direct_count"],
                            )
                            final_response = self._attach_news_search_diagnostics(
                                limited_response,
                                query_variants=query_variants,
                                providers_attempted=providers_attempted,
                                attempt_count=attempt_count,
                                fallback_used=fallback_used,
                                final_status="available",
                                error_types=error_types,
                            )
                            self._put_cache(cache_key, final_response)
                            return final_response

                        fallback_used = True

                        if prefer_chinese and stats["direct_count"] > 0:
                            logger.info(
                                "%s query[%s/%s] 搜尋成功，識別到 %s 條直接個股新聞但缺少中文直接命中，繼續嘗試下一路徑",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                                stats["direct_count"],
                            )
                            continue

                        if prefer_chinese and stats["preferred_count"] >= max_results:
                            logger.info(
                                "%s query[%s/%s] 搜尋成功，中文結果已滿足目標條數但缺少直接個股命中，繼續嘗試下一路徑",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                            )
                            continue

                        if prefer_chinese and stats["preferred_count"] > 0:
                            logger.info(
                                "%s query[%s/%s] 搜尋成功，識別到 %s/%s 條中文新聞但缺少直接個股命中，繼續嘗試下一路徑",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                                stats["preferred_count"],
                                len(limited_response.results),
                            )
                        else:
                            logger.info(
                                "%s query[%s/%s] 搜尋成功但未識別直接個股新聞，繼續嘗試下一路徑",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                            )
                    else:
                        if response.success and response.results:
                            fallback_used = True
                            unknown_response = self._latest_news_fallback_response(
                                response,
                                max_results=provider_max_results,
                            )
                            if unknown_response.results:
                                ranked_unknown = self._rank_news_response(
                                    unknown_response,
                                    stock_code=stock_code,
                                    stock_name=stock_name,
                                    prefer_chinese=prefer_chinese,
                                    max_results=provider_max_results,
                                    log_scope=f"{stock_code}:{provider.name}:stock_news:q{query_index}:latest_fallback",
                                )
                                limited_unknown = self._limit_search_response(
                                    ranked_unknown,
                                    max_results=max_results,
                                )
                                unknown_stats = self._news_relevance_stats(
                                    limited_unknown,
                                    prefer_chinese=prefer_chinese,
                                )
                                if self._is_better_ranked_news_response(
                                    limited_unknown,
                                    candidate_stats=unknown_stats,
                                    best_response=best_latest_fallback_response,
                                    best_stats=best_latest_fallback_stats,
                                    prefer_chinese=prefer_chinese,
                                ):
                                    best_latest_fallback_response = limited_unknown
                                    best_latest_fallback_stats = unknown_stats
                        if response.success and not filtered_response.results:
                            fallback_used = True
                            logger.info(
                                "%s query[%s/%s] 搜尋成功但過濾後無有效新聞，繼續嘗試下一路徑",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                            )
                        else:
                            error_type = self._classify_search_error(response.error_message)
                            self._append_unique_diagnostic_value(error_types, error_type)
                            last_error_message = sanitize_diagnostic_text(response.error_message) or "搜尋失敗"
                            fallback_used = True
                            logger.warning(
                                "%s query[%s/%s] 搜尋失敗: %s，嘗試下一路徑",
                                provider_name,
                                query_index,
                                len(candidate_queries),
                                last_error_message,
                            )
            if best_ranked_response is not None:
                final_response = self._attach_news_search_diagnostics(
                    best_ranked_response,
                    query_variants=query_variants,
                    providers_attempted=providers_attempted,
                    attempt_count=attempt_count,
                    fallback_used=fallback_used,
                    final_status="available",
                    error_types=error_types,
                )
                self._put_cache(cache_key, final_response)
                return final_response

            if best_latest_fallback_response is not None and best_latest_fallback_response.results:
                logger.info(
                    "所有嚴格日期新聞路徑皆未返回結果，使用 provider 最新可用新聞作為最後 fallback: %s 條",
                    len(best_latest_fallback_response.results),
                )
                final_response = self._attach_news_search_diagnostics(
                    best_latest_fallback_response,
                    query_variants=query_variants,
                    providers_attempted=providers_attempted,
                    attempt_count=attempt_count,
                    fallback_used=True,
                    final_status="available",
                    error_types=error_types,
                )
                self._put_cache(cache_key, final_response)
                return final_response

            if had_provider_success:
                response = SearchResponse(
                    query=query,
                    results=[],
                    provider="Filtered",
                    success=True,
                    error_message=None,
                )
                return self._attach_news_search_diagnostics(
                    response,
                    query_variants=query_variants,
                    providers_attempted=providers_attempted,
                    attempt_count=attempt_count,
                    fallback_used=fallback_used,
                    final_status="empty",
                    error_types=error_types,
                )

            # 所有引擎都失敗
            response = SearchResponse(
                query=query,
                results=[],
                provider="None",
                success=False,
                error_message=last_error_message or "所有搜尋引擎都不可用或搜尋失敗"
            )
            return self._attach_news_search_diagnostics(
                response,
                query_variants=query_variants,
                providers_attempted=providers_attempted,
                attempt_count=attempt_count,
                fallback_used=fallback_used,
                final_status="failed",
                error_types=error_types,
            )
        finally:
            if cache_owner and cache_event is not None:
                self._release_cache_fill(cache_key, cache_event)
    
    def search_stock_events(
        self,
        stock_code: str,
        stock_name: str,
        event_types: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜尋股票特定事件（年報預告、減持等）
        
        專門針對交易決策相關的重要事件進行搜尋
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            event_types: 事件型別列表
            
        Returns:
            SearchResponse 物件
        """
        if event_types is None:
            if self._is_foreign_stock(stock_code):
                event_types = ["earnings report", "insider selling", "quarterly results"]
            else:
                event_types = ["年報預告", "減持公告", "業績快報"]
        
        # 構建針對性查詢
        event_query = " OR ".join(event_types)
        query = f"{stock_name} ({event_query})"
        
        logger.info(f"搜尋股票事件: {stock_name}({stock_code}) - {event_types}")
        
        # 依次嘗試各個搜尋引擎
        for provider in self._providers:
            if not provider.is_available:
                continue
            
            response = provider.search(query, max_results=5)
            
            if response.success:
                return response
        
        return SearchResponse(
            query=query,
            results=[],
            provider="None",
            success=False,
            error_message="事件搜尋失敗"
        )
    
    def search_comprehensive_intel(
        self,
        stock_code: str,
        stock_name: str,
        max_searches: int = 3
    ) -> Dict[str, SearchResponse]:
        """
        多維度情報搜尋（同時使用多個引擎、多個維度）
        
        搜尋維度：
        1. 最新訊息 - 近期新聞動態
        2. 風險排查 - 減持、處罰、利空
        3. 業績預期 - 年報預告、業績快報
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            max_searches: 最大搜尋次數
            
        Returns:
            {維度名稱: SearchResponse} 字典
        """
        results = {}
        search_count = 0

        is_foreign = self._is_foreign_stock(stock_code)
        is_index_etf = self.is_index_or_etf(stock_code, stock_name)

        if is_foreign:
            search_dimensions = [
                {
                    'name': 'latest_news',
                    'query': f"{stock_name} {stock_code} latest news events",
                    'desc': '最新訊息',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'market_analysis',
                    'query': f"{stock_name} analyst rating target price report",
                    'desc': '機構分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'risk_check',
                    'query': (
                        f"{stock_name} {stock_code} index performance outlook tracking error"
                        if is_index_etf else f"{stock_name} risk insider selling lawsuit litigation"
                    ),
                    'desc': '風險排查',
                    'tavily_topic': None if is_index_etf else 'news',
                    'strict_freshness': not is_index_etf,
                },
                {
                    'name': 'earnings',
                    'query': (
                        f"{stock_name} {stock_code} index performance composition outlook"
                        if is_index_etf else f"{stock_name} earnings revenue profit growth forecast"
                    ),
                    'desc': '業績預期',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'industry',
                    'query': (
                        f"{stock_name} {stock_code} index sector allocation holdings"
                        if is_index_etf else f"{stock_name} industry competitors market share outlook"
                    ),
                    'desc': '行業分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
            ]
        else:
            search_dimensions = [
                {
                    'name': 'latest_news',
                    'query': f"{stock_name} {stock_code} 最新 新聞 重大 事件",
                    'desc': '最新訊息',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'market_analysis',
                    'query': f"{stock_name} 研報 目標價 評級 深度分析",
                    'desc': '機構分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'risk_check',
                    'query': (
                        f"{stock_name} 指數走勢 跟蹤誤差 淨值 表現"
                        if is_index_etf else f"{stock_name} 減持 處罰 違規 訴訟 利空 風險"
                    ),
                    'desc': '風險排查',
                    'tavily_topic': None if is_index_etf else 'news',
                    'strict_freshness': not is_index_etf,
                },
                {
                    'name': 'announcements',
                    'query': (
                        f"{stock_name} {stock_code} 公告 指數調整 成分變化"
                        if is_index_etf else f"{stock_name} {stock_code} 公司公告 重要公告 上交所 深交所 cninfo"
                    ),
                    'desc': '公司公告',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'earnings',
                    'query': (
                        f"{stock_name} 指數成分 淨值 跟蹤表現"
                        if is_index_etf else f"{stock_name} 業績預告 財報 營收 淨利潤 同比增長"
                    ),
                    'desc': '業績預期',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'industry',
                    'query': (
                        f"{stock_name} 指數成分股 行業配置 權重"
                        if is_index_etf else f"{stock_name} 所在行業 競爭對手 市場份額 行業前景"
                    ),
                    'desc': '行業分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
            ]
        
        search_days = self._effective_news_window_days()
        target_per_dimension = 3
        provider_max_results = self._provider_request_size(target_per_dimension)

        logger.info(
            (
                "開始多維度情報搜尋: %s(%s), 時間範圍: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s), 目標條數=%s, provider請求條數=%s"
            ),
            stock_name,
            stock_code,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            target_per_dimension,
            provider_max_results,
        )
        
        # 輪流使用不同的搜尋引擎
        provider_index = 0

        if search_count < max_searches:
            latest_response = self.search_stock_news(
                stock_code,
                stock_name,
                max_results=target_per_dimension,
                tavily_news_topic_first_variant_only=True,
            )
            results["latest_news"] = latest_response
            search_count += 1
            if latest_response.success:
                logger.info(
                    "[情報搜尋] 最新訊息: 原始=%s條",
                    len(latest_response.results),
                )
            else:
                logger.warning(
                    "[情報搜尋] 最新訊息: 搜尋失敗 - %s",
                    latest_response.error_message,
                )
        
        for dim in search_dimensions:
            if dim['name'] == 'latest_news':
                continue
            if search_count >= max_searches:
                break
            
            # 選擇搜尋引擎（輪流使用）
            available_providers = [p for p in self._providers if p.is_available]
            if not available_providers:
                break
            
            provider = available_providers[provider_index % len(available_providers)]
            provider_index += 1
            
            logger.info(f"[情報搜尋] {dim['desc']}: 使用 {provider.name}")

            if isinstance(provider, TavilySearchProvider) and dim.get('tavily_topic'):
                response = provider.search(
                    dim['query'],
                    max_results=provider_max_results,
                    days=search_days,
                    topic=dim['tavily_topic'],
                )
            else:
                response = provider.search(
                    dim['query'],
                    max_results=provider_max_results,
                    days=search_days,
                )
            if dim['strict_freshness']:
                filtered_response = self._filter_news_response(
                    response,
                    search_days=search_days,
                    max_results=provider_max_results,
                    log_scope=f"{stock_code}:{provider.name}:{dim['name']}",
                )
            else:
                filtered_response = self._normalize_and_limit_response(
                    response,
                    max_results=provider_max_results,
                )
            filtered_response = self._rank_news_response(
                filtered_response,
                stock_code=stock_code,
                stock_name=stock_name,
                prefer_chinese=self._should_prefer_chinese_news(stock_code, stock_name),
                max_results=target_per_dimension,
                log_scope=f"{stock_code}:{provider.name}:{dim['name']}:rank",
            )
            results[dim['name']] = filtered_response
            search_count += 1
            
            if response.success:
                logger.info(
                    "[情報搜尋] %s: 原始=%s條, 過濾後=%s條",
                    dim['desc'],
                    len(response.results),
                    len(filtered_response.results),
                )
            else:
                logger.warning(f"[情報搜尋] {dim['desc']}: 搜尋失敗 - {response.error_message}")
            
            # 短暫延遲避免請求過快
            time.sleep(0.5)
        
        return results
    
    def format_intel_report(
        self,
        intel_results: Dict[str, SearchResponse],
        stock_name: str,
        max_total_chars: Optional[int] = DEFAULT_NEWS_CONTEXT_MAX_TOTAL_CHARS,
    ) -> str:
        """
        格式化情報搜尋結果為報告
        
        Args:
            intel_results: 多維度搜尋結果
            stock_name: 股票名稱
            max_total_chars: 最大總字元數，超出時截斷並附加標記
            
        Returns:
            格式化的情報報告文字
        """
        lines = [f"【{stock_name} 情報搜尋結果】"]
        
        # 維度展示順序
        display_order = ['latest_news', 'announcements', 'market_analysis', 'risk_check', 'earnings', 'industry']

        dim_labels = {
            'latest_news': '📰 最新訊息',
            'announcements': '📋 公司公告',
            'market_analysis': '📈 機構分析',
            'risk_check': '⚠️ 風險排查',
            'earnings': '📊 業績預期',
            'industry': '🏭 行業分析',
        }

        for dim_name in display_order:
            if dim_name not in intel_results:
                continue
                
            resp = intel_results[dim_name]
            
            # 獲取維度描述
            dim_desc = dim_labels.get(dim_name, dim_name)
            
            lines.append(f"\n{dim_desc} (來源: {resp.provider}):")
            if resp.success and resp.results:
                # 增加顯示條數
                for i, r in enumerate(resp.results[:4], 1):
                    date_str = f" [{r.published_date}]" if r.published_date else ""
                    lines.append(f"  {i}. {r.title}{date_str}")
                    # 如果摘要太短，可能資訊量不足
                    snippet = r.snippet[:150] if len(r.snippet) > 20 else r.snippet
                    lines.append(f"     {snippet}...")
                    if r.relevance_category or r.relevance_reasons:
                        relevance_parts = []
                        if r.relevance_category:
                            relevance_parts.append(r.relevance_category)
                        if r.relevance_score is not None:
                            relevance_parts.append(f"score={r.relevance_score}")
                        if r.relevance_reasons:
                            relevance_parts.append(f"依據: {'；'.join(r.relevance_reasons[:3])}")
                        lines.append(f"     關聯度: {'; '.join(relevance_parts)}")
            else:
                lines.append("  未找到相關資訊")
        
        return cap_news_context("\n".join(lines), max_chars=max_total_chars) or ""
    
    def batch_search(
        self,
        stocks: List[Dict[str, str]],
        max_results_per_stock: int = 3,
        delay_between: float = 1.0
    ) -> Dict[str, SearchResponse]:
        """
        Batch search news for multiple stocks.
        
        Args:
            stocks: List of stocks
            max_results_per_stock: Max results per stock
            delay_between: Delay between searches (seconds)
            
        Returns:
            Dict of results
        """
        results = {}
        
        for i, stock in enumerate(stocks):
            if i > 0:
                time.sleep(delay_between)
            
            code = stock.get('code', '')
            name = stock.get('name', '')
            
            response = self.search_stock_news(code, name, max_results_per_stock)
            results[code] = response
        
        return results

    def search_stock_price_fallback(
        self,
        stock_code: str,
        stock_name: str,
        max_attempts: int = 3,
        max_results: int = 5
    ) -> SearchResponse:
        """
        Enhance search when data sources fail.
        
        When all data sources (efinance, akshare, tushare, baostock, etc.) fail to get
        stock data, use search engines to find stock trends and price info as supplemental data for AI analysis.
        
        Strategy:
        1. Search using multiple keyword templates
        2. Try all available search engines for each keyword
        3. Aggregate and deduplicate results
        
        Args:
            stock_code: Stock Code
            stock_name: Stock Name
            max_attempts: Max search attempts (using different keywords)
            max_results: Max results to return
            
        Returns:
            SearchResponse object with aggregated results
        """

        if not self.is_available:
            return SearchResponse(
                query=f"{stock_name} 股價走勢",
                results=[],
                provider="None",
                success=False,
                error_message="未配置搜尋能力"
            )
        
        logger.info(f"[增強搜尋] 資料來源失敗，啟動增強搜尋: {stock_name}({stock_code})")
        
        all_results = []
        seen_urls = set()
        successful_providers = []
        
        # 使用多個關鍵詞模板搜尋
        is_foreign = self._is_foreign_stock(stock_code)
        keywords = self.ENHANCED_SEARCH_KEYWORDS_EN if is_foreign else self.ENHANCED_SEARCH_KEYWORDS
        for i, keyword_template in enumerate(keywords[:max_attempts]):
            query = keyword_template.format(name=stock_name, code=stock_code)
            
            logger.info(f"[增強搜尋] 第 {i+1}/{max_attempts} 次搜尋: {query}")
            
            # 依次嘗試各個搜尋引擎
            for provider in self._providers:
                if not provider.is_available:
                    continue
                
                try:
                    response = provider.search(query, max_results=3)
                    
                    if response.success and response.results:
                        # 去重並新增結果
                        for result in response.results:
                            if result.url not in seen_urls:
                                seen_urls.add(result.url)
                                all_results.append(result)
                                
                        if provider.name not in successful_providers:
                            successful_providers.append(provider.name)
                        
                        logger.info(f"[增強搜尋] {provider.name} 返回 {len(response.results)} 條結果")
                        break  # 成功後跳到下一個關鍵詞
                    else:
                        logger.debug(f"[增強搜尋] {provider.name} 無結果或失敗")
                        
                except Exception as e:
                    logger.warning(f"[增強搜尋] {provider.name} 搜尋異常: {e}")
                    continue
            
            # 短暫延遲避免請求過快
            if i < max_attempts - 1:
                time.sleep(0.5)
        
        # 彙總結果
        if all_results:
            # 擷取前 max_results 條
            final_results = all_results[:max_results]
            provider_str = ", ".join(successful_providers) if successful_providers else "None"
            
            logger.info(f"[增強搜尋] 完成，共獲取 {len(final_results)} 條結果（來源: {provider_str}）")
            
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股價走勢",
                results=final_results,
                provider=provider_str,
                success=True,
            )
        else:
            logger.warning(f"[增強搜尋] 所有搜尋均未返回結果")
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股價走勢",
                results=[],
                provider="None",
                success=False,
                error_message="增強搜尋未找到相關資訊"
            )

    def search_stock_with_enhanced_fallback(
        self,
        stock_code: str,
        stock_name: str,
        include_news: bool = True,
        include_price: bool = False,
        max_results: int = 5
    ) -> Dict[str, SearchResponse]:
        """
        綜合搜尋介面（支援新聞和股價資訊）
        
        當 include_price=True 時，會同時搜尋新聞和股價資訊。
        主要用於資料來源完全失敗時的兜底方案。
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            include_news: 是否搜尋新聞
            include_price: 是否搜尋股價/走勢資訊
            max_results: 每類搜尋的最大結果數
            
        Returns:
            {'news': SearchResponse, 'price': SearchResponse} 字典
        """
        results = {}
        
        if include_news:
            results['news'] = self.search_stock_news(
                stock_code, 
                stock_name, 
                max_results=max_results
            )
        
        if include_price:
            results['price'] = self.search_stock_price_fallback(
                stock_code,
                stock_name,
                max_attempts=3,
                max_results=max_results
            )
        
        return results

    def format_price_search_context(self, response: SearchResponse) -> str:
        """
        將股價搜尋結果格式化為 AI 分析上下文
        
        Args:
            response: 搜尋響應物件
            
        Returns:
            格式化的文字，可直接用於 AI 分析
        """
        if not response.success or not response.results:
            return "【股價走勢搜尋】未找到相關資訊，請以其他通道資料為準。"
        
        lines = [
            f"【股價走勢搜尋結果】（來源: {response.provider}）",
            "⚠️ 注意：以下資訊來自網路搜尋，僅供參考，可能存在延遲或不準確。",
            ""
        ]
        
        for i, result in enumerate(response.results, 1):
            date_str = f" [{result.published_date}]" if result.published_date else ""
            lines.append(f"{i}. 【{result.source}】{result.title}{date_str}")
            lines.append(f"   {result.snippet[:200]}...")
            lines.append("")
        
        return "\n".join(lines)


# === 便捷函式 ===
_search_service: Optional[SearchService] = None
_search_service_lock = threading.Lock()


def get_search_service() -> SearchService:
    """獲取搜尋服務單例"""
    global _search_service
    
    if _search_service is None:
        with _search_service_lock:
            if _search_service is None:
                from src.config import get_config
                config = get_config()
                
                _search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    anspire_keys=config.anspire_api_keys,
                    brave_keys=config.brave_api_keys,
                    serpapi_keys=config.serpapi_keys,
                    minimax_keys=config.minimax_api_keys,
                    searxng_base_urls=config.searxng_base_urls,
                    searxng_public_instances_enabled=config.searxng_public_instances_enabled,
                    news_max_age_days=config.news_max_age_days,
                    news_strategy_profile=getattr(config, "news_strategy_profile", "short"),
                )
    
    return _search_service


def reset_search_service() -> None:
    """重置搜尋服務（用於測試）"""
    global _search_service
    with _search_service_lock:
        _search_service = None


if __name__ == "__main__":
    # 測試搜尋服務
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
    )
    
    # 手動測試（需要配置 API Key）
    service = get_search_service()
    
    if service.is_available:
        print("=== 測試股票新聞搜尋 ===")
        response = service.search_stock_news("300389", "艾比森")
        print(f"搜尋狀態: {'成功' if response.success else '失敗'}")
        print(f"搜尋引擎: {response.provider}")
        print(f"結果數量: {len(response.results)}")
        print(f"耗時: {response.search_time:.2f}s")
        print("\n" + response.to_context())
    else:
        print("未配置搜尋能力，跳過測試")

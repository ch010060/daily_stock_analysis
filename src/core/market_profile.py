# -*- coding: utf-8 -*-
"""
大盤覆盤市場區域配置

定義各市場區域的指數、新聞搜尋詞、Prompt 提示等後設資料，
供 MarketAnalyzer 按 region 切換台股/美股回顧行為。
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MarketProfile:
    """大盤覆盤市場區域配置"""

    region: str  # "tw" | "us"
    # 用於判斷整體走勢的指數程式碼，tw 用 TAIEX，us 用標普 SPX
    mood_index_code: str
    # 新聞搜尋關鍵詞
    news_queries: List[str]
    # 指數點評 Prompt 提示語
    prompt_index_hint: str
    # 市場概況是否包含漲跌家數、漲停跌停
    has_market_stats: bool
    # 市場概況是否包含板塊漲跌
    has_sector_rankings: bool


CN_PROFILE = MarketProfile(
    region="tw",
    mood_index_code="TAIEX",
    news_queries=[
        "台股 大盤 今日",
        "TAIEX 台股 加權指數 半導體",
        "臺積電 台股 盤勢",
        "櫃買 指數 台股",
        "外資 投信 自營商 台股",
    ],
    prompt_index_hint="分析加權指數（TAIEX）、櫃買指數（TPEx）、0050走勢，關注半導體與科技板塊主線",
    has_market_stats=False,
    has_sector_rankings=False,
)

US_PROFILE = MarketProfile(
    region="us",
    mood_index_code="SPX",
    news_queries=[
        "美股 大盤",
        "US stock market",
        "S&P 500 NASDAQ",
    ],
    prompt_index_hint="分析標普500、納斯達克、道指等各指數走勢特點",
    has_market_stats=False,
    has_sector_rankings=False,
)

HK_PROFILE = MarketProfile(
    region="us",
    mood_index_code="SPX",
    news_queries=[
        "美股 大盤",
        "US stock market",
        "S&P 500 NASDAQ",
    ],
    prompt_index_hint="分析標普500、納斯達克、道指等各指數走勢特點",
    has_market_stats=False,
    has_sector_rankings=False,
)

TW_PROFILE = MarketProfile(
    region="tw",
    mood_index_code="TAIEX",
    news_queries=[
        "台股 大盤 今日",
        "TAIEX 台股 加權指數 半導體",
        "臺積電 台股 盤勢",
        "櫃買 指數 台股",
        "外資 投信 自營商 台股",
    ],
    prompt_index_hint="分析加權指數（TAIEX）、櫃買指數（TPEx）、0050走勢，關注半導體與科技板塊主線",
    has_market_stats=False,
    has_sector_rankings=False,
)


_PROFILE_MAP = {
    "us": US_PROFILE,
    "tw": TW_PROFILE,
}


def get_profile(region: str) -> MarketProfile:
    """Return MarketProfile for the given region.

    Raises ValueError for unrecognised regions to prevent silent CN fallback.
    """
    try:
        return _PROFILE_MAP[region]
    except KeyError:
        raise ValueError(
            f"Unsupported market review region: {region!r}. "
            f"Accepted values: {sorted(_PROFILE_MAP)}"
        )

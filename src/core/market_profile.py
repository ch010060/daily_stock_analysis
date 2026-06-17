# -*- coding: utf-8 -*-
"""
大盤覆盤市場區域配置

定義各市場區域的指數、新聞搜尋詞、Prompt 提示等後設資料，
供 MarketAnalyzer 按 region 切換 A 股/美股覆盤行為。
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MarketProfile:
    """大盤覆盤市場區域配置"""

    region: str  # "cn" | "us" | "hk" | "tw"
    # 用於判斷整體走勢的指數程式碼，cn 用上證 000001，us 用標普 SPX
    mood_index_code: str
    # 新聞搜尋關鍵詞
    news_queries: List[str]
    # 指數點評 Prompt 提示語
    prompt_index_hint: str
    # 市場概況是否包含漲跌家數、漲停跌停（A 股有，美股無）
    has_market_stats: bool
    # 市場概況是否包含板塊漲跌（A 股有，美股暫無）
    has_sector_rankings: bool


CN_PROFILE = MarketProfile(
    region="cn",
    mood_index_code="000001",
    news_queries=[
        "A股 大盤 覆盤",
        "股市 行情 分析",
        "A股 市場 熱點 板塊",
    ],
    prompt_index_hint="分析上證、深證、創業板等各指數走勢特點",
    has_market_stats=True,
    has_sector_rankings=True,
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
    region="hk",
    mood_index_code="HSI",
    news_queries=[
        "港股 大盤 覆盤",
        "Hong Kong stock market",
        "恒生指數 行情",
    ],
    prompt_index_hint="分析恒生指數、恒生科技指數、國企指數等各指數走勢特點",
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
    "cn": CN_PROFILE,
    "us": US_PROFILE,
    "hk": HK_PROFILE,
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

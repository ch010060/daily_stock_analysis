# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.finews_snapshot import (
    FINEWS_SOURCE_URL,
    fetch_latest_finews_snapshot,
    parse_finews_homepage_html,
    to_zh_tw,
)


FIXTURE_HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <title>FiNews 美股日报</title>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": "FiNews 美股日报 · 2026-06-26",
    "datePublished": "2026-06-26",
    "dateModified": "2026-06-26 21:13:18"
  }
  </script>
  <script>window.bad = "<p>不要渲染</p>"</script>
</head>
<body>
  <h1>盘后总结</h1>
  <p>01</p>
  <p>美股主要指数盘后偏弱，市场温度分化。</p>
  <p>02科技股承压。</p>
  <p>来源：Yahoo Finance</p>
  <h1>主要新闻</h1>
  <article>
    <a href="https://example.com/news-one">美股收低，科技股抛售。</a>
    <a href="javascript:alert(1)">不安全連結</a>
    <p>标普与纳斯达克承压。</p>
  </article>
  <h2>市场温度</h2>
  <p>恐慌贪婪指数</p>
  <p>25 · 极度恐慌</p>
  <h2>主要指数</h2>
  <p>标普 500</p>
  <p><a href="https://finance.yahoo.com/quote/%5EGSPC">^GSPC</a></p>
  <p>6,000.00</p>
  <h2>主要股票</h2>
  <p>VOO</p>
  <p><a href="https://finance.yahoo.com/quote/VOO">VOO</a></p>
  <p>500.00</p>
  <p>+0.10%</p>
  <p>Invesco Trust</p>
  <p><a href="https://finance.yahoo.com/quote/QQQ">QQQ</a></p>
  <p>520.00</p>
  <p>-0.20%</p>
  <p>Nvidia</p>
  <p><a href="https://finance.yahoo.com/quote/NVDA">NVDA</a></p>
  <p>190.10</p>
  <p>+1.20%</p>
  <p>Apple</p>
  <p><a href="https://finance.yahoo.com/quote/AAPL">AAPL</a></p>
  <p>210.20</p>
  <p>-0.30%</p>
  <p>美债利率</p>
  <p>美国 10 年期国债</p>
  <p>主要汇率</p>
  <p>美元 / 人民币</p>
  <p><a href="https://finance.yahoo.com/quote/BTC-USD">BTC-USD</a></p>
  <p>101000</p>
  <p>+0.50%</p>
</body>
</html>
"""

COMMON_SIMPLIFIED_RESIDUE = [
    "从",
    "成长",
    "板块",
    "转向",
    "焦点",
    "沟通",
    "官员",
    "预计",
    "债券",
    "强硬",
    "表态",
    "变量",
    "争议",
    "击",
    "霍尔木兹",
    "航运",
    "保险",
    "影响",
    "资产",
    "定价",
    "威胁",
    "对",
    "征收",
    "数字",
    "国家",
    "关税",
    "公司层面",
    "礼来",
    "表现",
    "苹果",
    "微软",
    "亚马逊",
    "英伟达",
    "行业",
    "存储",
    "消费电子",
    "资本开支",
    "节奏",
    "企业",
    "预算",
    "投资者",
    "评估",
    "温度",
    "当前",
    "过去",
    "数据",
    "来源",
    "综合",
    "动量",
    "期权",
    "避险",
    "极度",
    "贪婪",
]


def test_parser_extracts_metadata_and_required_sections() -> None:
    snapshot = parse_finews_homepage_html(
        FIXTURE_HTML,
        fetched_at="2026-06-29T00:00:00+00:00",
    )

    assert snapshot["source"] == "finews"
    assert snapshot["source_url"] == FINEWS_SOURCE_URL
    assert snapshot["report_date"] == "2026-06-26"
    assert snapshot["source_updated_at"] == "2026-06-26 21:13:18"
    assert snapshot["language_original"] == "zh-CN"
    assert snapshot["language_rendered"] == "zh-TW"
    assert snapshot["sections"]["after_market_summary"] == [
        "美股主要指數盤後偏弱，市場溫度分化。",
        "科技股承壓。",
        "來源：Yahoo Finance",
    ]
    assert "美股收低，科技股拋售。" in snapshot["sections"]["major_news"]
    assert snapshot["external_links"] == [
        {
            "title": "美股收低，科技股拋售。",
            "url": "https://example.com/news-one",
        },
        {
            "title": "^GSPC",
            "url": "https://finance.yahoo.com/quote/%5EGSPC",
        },
        {"title": "VOO", "url": "https://finance.yahoo.com/quote/VOO"},
        {"title": "QQQ", "url": "https://finance.yahoo.com/quote/QQQ"},
        {"title": "NVDA", "url": "https://finance.yahoo.com/quote/NVDA"},
        {"title": "AAPL", "url": "https://finance.yahoo.com/quote/AAPL"},
        {"title": "BTC-USD", "url": "https://finance.yahoo.com/quote/BTC-USD"},
    ]
    assert snapshot["section_links"]["major_news"] == [
        {
            "title": "美股收低，科技股拋售。",
            "url": "https://example.com/news-one",
        }
    ]
    assert snapshot["section_links"]["major_indices"] == [
        {
            "title": "^GSPC",
            "url": "https://finance.yahoo.com/quote/%5EGSPC",
        }
    ]
    assert snapshot["section_links"]["major_stocks"] == [
        {"title": "VOO", "url": "https://finance.yahoo.com/quote/VOO"},
        {"title": "QQQ", "url": "https://finance.yahoo.com/quote/QQQ"},
        {"title": "NVDA", "url": "https://finance.yahoo.com/quote/NVDA"},
        {"title": "AAPL", "url": "https://finance.yahoo.com/quote/AAPL"},
    ]
    assert snapshot["section_links"]["fx"] == [
        {"title": "BTC-USD", "url": "https://finance.yahoo.com/quote/BTC-USD"},
    ]
    assert "恐慌貪婪指數" in snapshot["sections"]["market_temperature"]
    assert "標普 500" in snapshot["sections"]["major_indices"]
    assert "美國 10 年期國債" in snapshot["sections"]["treasury_yields"]
    assert "美元 / 人民幣" in snapshot["sections"]["fx"]


def test_parser_degrades_when_optional_sections_are_missing() -> None:
    snapshot = parse_finews_homepage_html(
        "<html><body><h1>盘后总结</h1><p>市场温度回升。</p></body></html>",
        fetched_at="2026-06-29T00:00:00+00:00",
    )

    assert snapshot["sections"]["after_market_summary"] == ["市場溫度回升。"]
    assert snapshot["sections"]["major_news"] == []
    assert snapshot["sections"]["major_indices"] == []


def test_zh_cn_content_is_converted_to_zh_tw() -> None:
    simplified = (
        "美股日报：盘后总结，市场温度，主要汇率，恐慌贪婪指数，从风险资产到智能手机消费成长，"
        "沟通官员债券强硬战争战前定价扩散，实时经济数据来源，期权避险，联储预计涨跌。"
    )

    converted = to_zh_tw(simplified)

    assert "美股日報" in converted
    assert "盤後總結" in converted
    assert "恐慌貪婪指數" in converted
    assert "智慧型手機" in converted
    for residue in [
        "从",
        "成长",
        "沟通",
        "官员",
        "债券",
        "强硬",
        "战争",
        "战前",
        "风险",
        "资产",
        "定价",
        "扩散",
        "消费",
        "智能手机",
        "实时",
        "经济",
        "数据",
        "来源",
        "期权",
        "避险",
        "联储",
        "预计",
    ]:
        assert residue not in converted


def test_snapshot_visible_fields_have_no_common_simplified_residue() -> None:
    html = """
    <html><body>
      <h1>盘后总结</h1>
      <p>从成长板块转向防御，沟通官员预计债券强硬表态。</p>
      <p>霍尔木兹航运保险影响风险资产定价，投资者评估期权避险。</p>
      <h1>主要新闻</h1>
      <a href="https://example.com/focus">焦点新闻：苹果微软亚马逊英伟达消费电子资本开支。</a>
      <h2>市场温度</h2>
      <p>恐慌贪婪指数</p>
      <p>25</p>
      <p>极度恐慌</p>
      <p>当前数据来源显示综合动量偏弱。</p>
    </body></html>
    """
    snapshot = parse_finews_homepage_html(html)

    payload = json.dumps(snapshot, ensure_ascii=False)
    for residue in COMMON_SIMPLIFIED_RESIDUE:
        assert residue not in payload


def test_fetch_failure_converts_old_cache_and_rebuilds_section_links(tmp_path: Path) -> None:
    cache_path = tmp_path / "finews.json"
    cache_path.write_text(
        json.dumps(
            {
                "source": "finews",
                "source_url": FINEWS_SOURCE_URL,
                "report_date": "2026-06-26",
                "source_updated_at": None,
                "fetched_at": "2026-06-28T00:00:00+00:00",
                "stale": False,
                "fetch_error": None,
                "language_original": "zh-CN",
                "language_rendered": "zh-TW",
                "external_links": [
                    {"title": "QQQ", "url": "https://finance.yahoo.com/quote/QQQ"},
                ],
                "sections": {
                    "after_market_summary": ["从风险资产转向债券。"],
                    "major_stocks": ["Invesco Trust", "QQQ", "520.00", "-0.20%"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def failing_fetcher(url: str, timeout: float) -> str:
        raise RuntimeError("network down")

    snapshot = fetch_latest_finews_snapshot(
        fetcher=failing_fetcher,
        cache_path=cache_path,
        fetched_at="2026-06-29T00:00:00+00:00",
    )

    assert snapshot["stale"] is True
    assert snapshot["conversion_engine"] == "opencc-s2twp"
    assert snapshot["conversion_version"] == "2026-06-29-phase21-2r"
    assert snapshot["sections"]["after_market_summary"] == ["從風險資產轉向債券。"]
    assert snapshot["section_links"]["major_stocks"] == [
        {"title": "QQQ", "url": "https://finance.yahoo.com/quote/QQQ"}
    ]


def test_fetch_failure_returns_cached_snapshot(tmp_path: Path) -> None:
    cache_path = tmp_path / "finews.json"
    cache_path.write_text(
        json.dumps(
            {
                "source": "finews",
                "source_url": FINEWS_SOURCE_URL,
                "report_date": "2026-06-26",
                "source_updated_at": None,
                "fetched_at": "2026-06-28T00:00:00+00:00",
                "stale": False,
                "fetch_error": None,
                "language_original": "zh-CN",
                "language_rendered": "zh-TW",
                "parser_version": "old",
                "conversion_engine": "dictionary",
                "conversion_version": "old",
                "external_links": [],
                "section_links": {},
                "sections": {"after_market_summary": ["舊快照"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def failing_fetcher(url: str, timeout: float) -> str:
        raise RuntimeError("network down")

    snapshot = fetch_latest_finews_snapshot(
        fetcher=failing_fetcher,
        cache_path=cache_path,
        fetched_at="2026-06-29T00:00:00+00:00",
    )

    assert snapshot["stale"] is True
    assert snapshot["fetch_error"] == "finews_fetch_failed: RuntimeError"
    assert snapshot["sections"]["after_market_summary"] == ["舊快照"]


def test_fetch_failure_returns_graceful_error_without_cache(tmp_path: Path) -> None:
    def failing_fetcher(url: str, timeout: float) -> str:
        raise TimeoutError("timeout")

    snapshot = fetch_latest_finews_snapshot(
        fetcher=failing_fetcher,
        cache_path=tmp_path / "missing.json",
        fetched_at="2026-06-29T00:00:00+00:00",
    )

    assert snapshot["stale"] is False
    assert snapshot["fetch_error"] == "finews_fetch_failed: TimeoutError"
    assert snapshot["sections"]["after_market_summary"] == []


def test_successful_fetch_writes_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "finews.json"

    def fixture_fetcher(url: str, timeout: float) -> str:
        assert url == FINEWS_SOURCE_URL
        return FIXTURE_HTML

    snapshot = fetch_latest_finews_snapshot(
        fetcher=fixture_fetcher,
        cache_path=cache_path,
        fetched_at="2026-06-29T00:00:00+00:00",
    )

    assert snapshot["stale"] is False
    assert cache_path.is_file()
    assert json.loads(cache_path.read_text(encoding="utf-8"))["report_date"] == "2026-06-26"


def test_endpoint_returns_snapshot_without_cookie_dependency(monkeypatch) -> None:
    from api.v1.endpoints import finews

    monkeypatch.setattr(
        finews,
        "fetch_latest_finews_snapshot",
        lambda: {
            "source": "finews",
            "source_url": FINEWS_SOURCE_URL,
            "report_date": "2026-06-26",
            "source_updated_at": None,
            "fetched_at": "2026-06-29T00:00:00+00:00",
            "stale": False,
            "fetch_error": None,
            "language_original": "zh-CN",
            "language_rendered": "zh-TW",
            "parser_version": "finews-v2",
            "conversion_engine": "opencc-s2twp",
            "conversion_version": "2026-06-29-phase21-2r",
            "external_links": [],
            "section_links": {},
            "sections": {"after_market_summary": ["內容"]},
        },
    )
    app = FastAPI()
    app.include_router(finews.router, prefix="/finews")

    response = TestClient(app).get("/finews/latest")

    assert response.status_code == 200
    assert response.json()["source"] == "finews"


def test_endpoint_response_contains_no_common_simplified_residue(monkeypatch) -> None:
    from api.v1.endpoints import finews

    monkeypatch.setattr(
        finews,
        "fetch_latest_finews_snapshot",
        lambda: parse_finews_homepage_html(FIXTURE_HTML),
    )
    app = FastAPI()
    app.include_router(finews.router, prefix="/finews")

    response = TestClient(app).get("/finews/latest")

    assert response.status_code == 200
    payload = json.dumps(response.json(), ensure_ascii=False)
    for residue in COMMON_SIMPLIFIED_RESIDUE:
        assert residue not in payload

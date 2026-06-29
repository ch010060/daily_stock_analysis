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
    <p>标普与纳斯达克承压。</p>
  </article>
  <h2>市场温度</h2>
  <p>恐慌贪婪指数</p>
  <p>25 · 极度恐慌</p>
  <h2>主要指数</h2>
  <p>标普 500</p>
  <p>^GSPC</p>
  <p>6,000.00</p>
  <h2>主要股票</h2>
  <p>Nvidia</p>
  <p>NVDA</p>
  <p>美债利率</p>
  <p>美国 10 年期国债</p>
  <p>主要汇率</p>
  <p>美元 / 人民币</p>
</body>
</html>
"""


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
    assert {
        "title": "美股收低，科技股拋售。",
        "url": "https://example.com/news-one",
    } in snapshot["external_links"]
    assert snapshot["external_links"] == [
        {
            "title": "美股收低，科技股拋售。",
            "url": "https://example.com/news-one",
        }
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
    assert to_zh_tw("美股日报：盘后总结，市场温度，主要汇率，恐慌贪婪指数") == (
        "美股日報：盤後總結，市場溫度，主要匯率，恐慌貪婪指數"
    )


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
                "external_links": [],
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
            "external_links": [],
            "sections": {"after_market_summary": ["內容"]},
        },
    )
    app = FastAPI()
    app.include_router(finews.router, prefix="/finews")

    response = TestClient(app).get("/finews/latest")

    assert response.status_code == 200
    assert response.json()["source"] == "finews"

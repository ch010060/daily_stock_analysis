# -*- coding: utf-8 -*-
"""Route B TW/US related-info news admission policy tests."""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.search_service import SearchResponse, SearchResult, SearchService


def _result(
    title: str,
    published_date: str,
    *,
    snippet: str = "摘要",
    url: str = "https://news.example.invalid/item",
    source: str = "news.example.invalid",
) -> SearchResult:
    return SearchResult(
        title=title,
        snippet=snippet,
        url=url,
        source=source,
        published_date=published_date,
    )


def _response(results: list[SearchResult], *, query: str = "query") -> SearchResponse:
    return SearchResponse(query=query, results=results, provider="MockProvider", success=True)


class RouteBNewsRelevancePolicyTestCase(unittest.TestCase):
    classlevel_env = patch.dict(
        os.environ,
        {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"},
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.classlevel_env.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.classlevel_env.stop()

    def _service_with_response(self, response: SearchResponse) -> tuple[SearchService, MagicMock]:
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        mock_search = MagicMock(return_value=response)
        service._providers = [
            SimpleNamespace(is_available=True, name="MockProvider", search=mock_search),
        ]
        return service, mock_search

    def test_non_positive_source_items_do_not_admit_tw_or_us_related_info(self) -> None:
        fresh = datetime.now().date().isoformat()

        cases = [
            (
                "2454",
                "聯發科",
                _result(
                    "Regional exchange turnover digest",
                    fresh,
                    snippet="No supported market, company, sector, or financial evidence for the target.",
                    url="https://legacy-source.example.invalid/market",
                    source="legacy-source",
                ),
                _result(
                    "聯發科 2454 月營收優於預期",
                    fresh,
                    snippet="聯發科公告月營收，法人上修 EPS 預估。",
                    url="https://finance.example.invalid/2454-revenue",
                    source="finance.example.invalid",
                ),
            ),
            (
                "AMD",
                "Advanced Micro Devices",
                _result(
                    "Regional market observation from an unsupported source",
                    fresh,
                    snippet="Broad commentary with no supported company identity or Route B evidence.",
                    url="https://legacy-source.example.invalid/market",
                    source="legacy-source",
                ),
                _result(
                    "AMD earnings guidance lifts AI chip suppliers",
                    fresh,
                    snippet="Advanced Micro Devices raised data center GPU guidance.",
                    url="https://finance.example.invalid/amd-earnings",
                    source="finance.example.invalid",
                ),
            ),
        ]

        for code, name, weak_source_only, direct_hit in cases:
            with self.subTest(code=code):
                service, _ = self._service_with_response(_response([weak_source_only, direct_hit]))

                resp = service.search_stock_news(code, name, max_results=2)

                self.assertEqual([item.title for item in resp.results], [direct_hit.title])

    def test_unsupported_source_vocabulary_is_not_a_positive_relevance_signal(self) -> None:
        fresh = datetime.now().date().isoformat()
        service, _ = self._service_with_response(
            _response(
                [
                    _result(
                        "Unsupported regional market closing summary",
                        fresh,
                        snippet="No supported company identity, sector, market, or financial event.",
                        source="legacy-source",
                    ),
                ]
            )
        )

        resp = service.search_stock_news("AMD", "Advanced Micro Devices", max_results=2)

        self.assertEqual(resp.results, [])
        self.assertEqual(resp.diagnostics["news_search"]["final_status"], "empty")

    def test_direct_tw_us_company_news_survives_overseas_context(self) -> None:
        fresh = datetime.now().date().isoformat()
        cases = [
            (
                "2330",
                "台積電",
                _result(
                    "台積電 2330 法說會聚焦先進製程與海外需求",
                    fresh,
                    snippet="台積電說明 AI 伺服器需求、先進製程產能與全球供應鏈風險。",
                ),
            ),
            (
                "AAPL",
                "Apple",
                _result(
                    "Apple revenue guidance weighs overseas demand and SEC filing risks",
                    fresh,
                    snippet="AAPL management discussed revenue, margin, and global supply-chain exposure.",
                ),
            ),
        ]

        for code, name, item in cases:
            with self.subTest(code=code):
                service, _ = self._service_with_response(_response([item]))

                resp = service.search_stock_news(code, name, max_results=1)

                self.assertEqual([result.title for result in resp.results], [item.title])
                self.assertEqual(resp.results[0].relevance_category, SearchService._DIRECT_NEWS_CATEGORY)

    def test_positive_tw_us_sector_and_business_relevance_is_admitted(self) -> None:
        fresh = datetime.now().date().isoformat()
        cases = [
            (
                "2454",
                "聯發科",
                _result(
                    "台股半導體 IC設計 外資看好 AI伺服器拉貨",
                    fresh,
                    snippet="月營收、法說會與 EPS 預估成為市場焦點。",
                ),
            ),
            (
                "NVDA",
                "NVIDIA",
                _result(
                    "Nasdaq AI chips and data center earnings stay in focus",
                    fresh,
                    snippet="Wall Street tracks guidance, analyst ratings, Fed policy, and GPU demand.",
                ),
            ),
        ]

        for code, name, item in cases:
            with self.subTest(code=code):
                service, _ = self._service_with_response(_response([item]))

                resp = service.search_stock_news(code, name, max_results=1)

                self.assertEqual([result.title for result in resp.results], [item.title])
                self.assertGreater(resp.results[0].relevance_score or 0, 0)

    def test_app_business_metric_news_is_preserved_for_app_and_apple(self) -> None:
        fresh = datetime.now().date().isoformat()
        cases = [
            (
                "APP",
                "AppLovin",
                _result(
                    "APP AppLovin ad revenue rises as install growth accelerates",
                    fresh,
                    snippet="Downloads grew, active users improved, and app revenue beat guidance.",
                    url="https://finance.example.invalid/app/app-install-growth",
                ),
            ),
            (
                "AAPL",
                "Apple",
                _result(
                    "Apple services revenue rises with App Store active users",
                    fresh,
                    snippet="AAPL app revenue and install growth supported quarterly earnings.",
                    url="https://finance.example.invalid/apple-app-store",
                ),
            ),
        ]

        for code, name, item in cases:
            with self.subTest(code=code):
                service, _ = self._service_with_response(_response([item]))

                resp = service.search_stock_news(code, name, max_results=1)

                self.assertEqual([result.title for result in resp.results], [item.title])
                self.assertEqual(resp.results[0].relevance_category, SearchService._DIRECT_NEWS_CATEGORY)

    def test_score_zero_filler_is_pruned_when_better_candidate_exists(self) -> None:
        fresh = datetime.now().date().isoformat()
        service, _ = self._service_with_response(
            _response(
                [
                    _result(
                        "市場閒聊：午餐吃什麼",
                        fresh,
                        snippet="生活話題討論，沒有投資或產業內容。",
                    ),
                    _result(
                        "AMD Advanced Micro Devices reports data center earnings",
                        fresh,
                        snippet="AMD reported revenue, EPS, margin and guidance.",
                    ),
                ]
            )
        )

        resp = service.search_stock_news("AMD", "Advanced Micro Devices", max_results=2)

        self.assertEqual(
            [item.title for item in resp.results],
            ["AMD Advanced Micro Devices reports data center earnings"],
        )

    def test_all_unrelated_candidates_return_truthful_empty_status(self) -> None:
        fresh = datetime.now().date().isoformat()
        service, _ = self._service_with_response(
            _response(
                [
                    _result("生活新聞：週末天氣晴", fresh, snippet="無公司或金融市場內容。"),
                    _result("美食專題：新餐廳開幕", fresh, snippet="生活消費與餐飲話題。"),
                ]
            )
        )

        resp = service.search_stock_news("2454", "聯發科", max_results=2)

        self.assertEqual(resp.results, [])
        self.assertEqual(resp.diagnostics["news_search"]["final_status"], "empty")

    def test_comprehensive_intel_announcements_query_uses_tw_us_terms(self) -> None:
        fresh = datetime.now().date().isoformat()
        service, mock_search = self._service_with_response(
            _response(
                [
                    _result(
                        "聯發科 2454 法說會公告",
                        fresh,
                        snippet="聯發科發布法說會與月營收公告。",
                    )
                ]
            )
        )

        service.search_comprehensive_intel("2454", "聯發科", max_searches=4)

        queries = [call.args[0] for call in mock_search.call_args_list]
        self.assertTrue(any("法說會" in query or "月營收" in query for query in queries))

    def test_legacy_old_source_labels_still_render_in_context(self) -> None:
        context = SearchResponse(
            query="legacy",
            results=[
                SearchResult(
                    title="Legacy stored item",
                    snippet="Old persisted related-info item.",
                    url="https://legacy.example.invalid/news",
                    source="legacy-source",
                    published_date="2026-06-01",
                    relevance_score=0,
                    relevance_category=SearchService._SECTOR_NEWS_CATEGORY,
                    relevance_reasons=["legacy stored source label"],
                )
            ],
            provider="Unit",
            success=True,
        ).to_context()

        self.assertIn("Legacy stored item", context)
        self.assertIn("legacy-source", context)


if __name__ == "__main__":
    unittest.main()

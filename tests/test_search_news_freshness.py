# -*- coding: utf-8 -*-
"""
Unit tests for strict news freshness filtering and strategy window logic (Issue #697).
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from itertools import chain, repeat
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Mock newspaper before search_service import (optional dependency)
if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.search_service import SearchResponse, SearchResult, SearchService


def _result(
    title: str,
    published_date: str | None,
    *,
    snippet: str = "snippet",
    url: str | None = None,
    source: str = "example.com",
) -> SearchResult:
    return SearchResult(
        title=title,
        snippet=snippet,
        url=url or f"https://example.com/{title}",
        source=source,
        published_date=published_date,
    )


def _response(results) -> SearchResponse:
    return SearchResponse(
        query="test",
        results=results,
        provider="Mock",
        success=True,
    )


def _responses_then_empty(*responses: SearchResponse):
    return chain(responses, repeat(_response([])))


def _comprehensive_intel_responses(
    latest_response: SearchResponse,
    *dimension_responses: SearchResponse,
    latest_variant_count: int = 4,
):
    latest_variant_padding = [_response([]) for _ in range(max(0, latest_variant_count - 1))]
    return _responses_then_empty(
        latest_response,
        *latest_variant_padding,
        *dimension_responses,
    )


def _news_search_diagnostics(response: SearchResponse) -> dict:
    diagnostics = getattr(response, "diagnostics", None)
    if not isinstance(diagnostics, dict):
        return {}
    news_search = diagnostics.get("news_search")
    if not isinstance(news_search, dict):
        return {}
    return news_search


class SearchNewsFreshnessTestCase(unittest.TestCase):
    """Tests for strategy window and strict published_date filtering."""

    classlevel_env = patch.dict(
        os.environ,
        {"DSA_ALLOW_EXTERNAL_NETWORK": "true", "DSA_FIXTURE_MODE": "false"},
    )

    @classmethod
    def setUpClass(cls):
        cls.classlevel_env.start()

    @classmethod
    def tearDownClass(cls):
        cls.classlevel_env.stop()

    def _create_service_with_mock_provider(
        self,
        *,
        news_max_age_days: int = 3,
        news_strategy_profile: str = "short",
        response: SearchResponse | None = None,
    ):
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=news_max_age_days,
            news_strategy_profile=news_strategy_profile,
        )
        mock_search = MagicMock(
            return_value=response
            or _response([_result("default", datetime.now().date().isoformat())])
        )
        service._providers[0].search = mock_search
        return service, mock_search

    def test_effective_window_uses_profile_and_news_max_age(self) -> None:
        """window = min(profile_days, NEWS_MAX_AGE_DAYS)."""
        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="medium",  # 7
        )
        service.search_stock_news("2330", "台積電", max_results=5)
        kwargs = mock_search.call_args[1]
        self.assertEqual(kwargs["days"], 3)

    def test_invalid_profile_falls_back_to_short(self) -> None:
        """Invalid profile should fallback to short (3 days)."""
        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=30,
            news_strategy_profile="invalid_profile",
        )
        service.search_stock_news("2330", "台積電", max_results=5)
        kwargs = mock_search.call_args[1]
        self.assertEqual(kwargs["days"], 3)

    def test_search_stock_news_strict_filters(self) -> None:
        """Drop old/unknown/future+2, keep future+1 and within-window dates."""
        today = datetime.now().date()
        fresh = today.isoformat()
        old = (today - timedelta(days=30)).isoformat()
        future_1 = (today + timedelta(days=1)).isoformat()
        future_2 = (today + timedelta(days=2)).isoformat()

        service, _ = self._create_service_with_mock_provider(
            news_max_age_days=7,
            news_strategy_profile="medium",
            response=_response(
                [
                    _result("old", old),
                    _result("unknown", None),
                    _result("future_2", future_2),
                    _result("future_1", future_1),
                    _result("fresh", fresh),
                ]
            ),
        )

        resp = service.search_stock_news("2330", "台積電", max_results=5)
        titles = [r.title for r in resp.results]
        self.assertEqual(titles, ["future_1", "fresh"])
        for item in resp.results:
            self.assertRegex(item.published_date or "", r"^\d{4}-\d{2}-\d{2}$")

    def test_search_stock_news_overfetch_before_filter(self) -> None:
        """Provider request size should be increased before filtering."""
        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        service.search_stock_news("2330", "台積電", max_results=4)
        args, kwargs = mock_search.call_args
        requested = kwargs.get("max_results")
        if requested is None:
            requested = args[1]
        self.assertEqual(requested, 8)

    def test_search_stock_news_try_next_provider_when_filtered_empty(self) -> None:
        """If provider-A passes API call but all results are filtered, continue to provider-B."""
        today = datetime.now().date()
        old = (today - timedelta(days=90)).isoformat()
        fresh = today.isoformat()

        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="P1",
            search=MagicMock(return_value=_response([_result("too_old", old)])),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="P2",
            search=MagicMock(return_value=_response([_result("fresh", fresh)])),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("2330", "台積電", max_results=3)
        self.assertEqual([r.title for r in resp.results], ["fresh"])
        self.assertEqual(p1.search.call_count, 4)
        self.assertEqual(p2.search.call_count, 4)

    def test_search_stock_news_tries_next_provider_when_chinese_context_is_english_only(self) -> None:
        """Chinese-preferred queries should not stop on English-only provider results."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="P1",
            search=MagicMock(
                return_value=_response(
                    [
                        _result("English headline", fresh),
                        _result("Another English story", fresh),
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="P2",
            search=MagicMock(return_value=_response([_result("中文資訊", fresh)])),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("2330", "台積電", max_results=3)
        self.assertEqual([r.title for r in resp.results], ["中文資訊"])
        self.assertEqual(p1.search.call_count, 4)
        self.assertEqual(p2.search.call_count, 4)

    def test_search_stock_news_prioritizes_chinese_items_within_mixed_results(self) -> None:
        """Chinese items should be ordered ahead of English items in mixed batches."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        mixed_provider = SimpleNamespace(
            is_available=True,
            name="Mixed",
            search=MagicMock(
                return_value=_response(
                    [
                        _result("English headline", fresh),
                        _result("中文快訊", fresh),
                        _result("Second English headline", fresh),
                    ]
                )
            ),
        )
        service._providers = [mixed_provider]

        resp = service.search_stock_news("2330", "台積電", max_results=3)
        self.assertEqual(
            [r.title for r in resp.results],
            ["中文快訊", "English headline", "Second English headline"],
        )

    def test_search_stock_news_prioritizes_chinese_before_truncating_results(self) -> None:
        """Chinese candidates beyond the first raw slot should still win after reprioritization."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="P1",
            search=MagicMock(
                return_value=_response(
                    [
                        _result("English headline", fresh),
                        _result("中文快訊", fresh),
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="P2",
            search=MagicMock(return_value=_response([_result("後續中文資訊", fresh)])),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("2330", "台積電", max_results=1)
        self.assertEqual([r.title for r in resp.results], ["中文快訊"])
        self.assertEqual(p1.search.call_count, 4)
        self.assertEqual(p2.search.call_count, 4)

    def test_search_stock_news_prefers_chinese_direct_hit_before_score_truncation(self) -> None:
        """Chinese direct hits should outrank higher-scored English direct hits before limiting."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        provider = SimpleNamespace(
            is_available=True,
            name="MixedDirect",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "Kweichow Moutai 2330 announces buyback",
                            fresh,
                            snippet="The company reported an updated share repurchase plan.",
                        ),
                        _result(
                            "台積電 釋出回購公告",
                            fresh,
                            snippet="公司披露回購方案。",
                        ),
                    ]
                )
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("2330", "台積電", max_results=1)

        self.assertEqual([r.title for r in resp.results], ["台積電 釋出回購公告"])
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        provider.search.assert_called_once()

    def test_a_share_chinese_sector_provider_beats_higher_scored_english_sector(self) -> None:
        """When no direct hit exists, Chinese-preferred flows should compare language before score."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="EnglishSector",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "Baijiu industry quarterly results improve",
                            fresh,
                            snippet="Sector peers report better market share.",
                            source="sec.gov",
                        )
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="ChineseSector",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "白酒板塊資金回暖",
                            fresh,
                            snippet="消費行業反彈。",
                        )
                    ]
                )
            ),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("2330", "台積電", max_results=1)

        self.assertEqual([r.title for r in resp.results], ["白酒板塊資金回暖"])
        self.assertEqual(resp.results[0].relevance_category, "sector_related_news")
        self.assertEqual(p1.search.call_count, 4)
        self.assertEqual(p2.search.call_count, 4)

    def test_search_stock_news_keeps_english_provider_order_for_us_stock(self) -> None:
        """English stock searches should keep the first successful provider result."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="P1",
            search=MagicMock(return_value=_response([_result("Apple earnings beat", fresh)])),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="P2",
            search=MagicMock(return_value=_response([_result("蘋果資訊", fresh)])),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("AAPL", "Apple", max_results=3)
        self.assertEqual([r.title for r in resp.results], ["Apple earnings beat"])
        p1.search.assert_called_once()
        p2.search.assert_not_called()

    def test_a_share_direct_company_news_beats_sector_provider_fallback(self) -> None:
        """A-share direct company hits should beat generic sector news from earlier providers."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="P1",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "白酒行業景氣度回暖 多隻龍頭上漲",
                            fresh,
                            snippet="消費板塊獲得資金關注。",
                        )
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="P2",
            search=MagicMock(
                return_value=_response(
                    [
                        _result("滬指震盪收漲，市場情緒回暖", fresh),
                        _result(
                            "台積電 2330 釋出回購公告",
                            fresh,
                            snippet="台積電披露公司公告，董事會審議透過回購方案。",
                            source="cninfo",
                        ),
                    ]
                )
            ),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("2330", "台積電", max_results=2)

        self.assertEqual(resp.results[0].title, "台積電 2330 釋出回購公告")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        self.assertIn("股票代號", "；".join(resp.results[0].relevance_reasons or []))
        p1.search.assert_called_once()
        p2.search.assert_called_once()

    def test_a_share_chinese_direct_news_beats_english_direct_provider_fallback(self) -> None:
        """Chinese-preferred queries should keep looking past English-only direct hits."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        p1 = SimpleNamespace(
            is_available=True,
            name="EnglishDirect",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "Kweichow Moutai 2330 announces buyback",
                            fresh,
                            snippet="The company reported an updated share repurchase plan.",
                        )
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="ChineseDirect",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "台積電 2330 釋出回購公告",
                            fresh,
                            snippet="台積電披露公司回購公告。",
                        )
                    ]
                )
            ),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("2330", "台積電", max_results=1)

        self.assertEqual(resp.results[0].title, "台積電 2330 釋出回購公告")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        p1.search.assert_called_once()
        p2.search.assert_called_once()

    def test_hk_stock_relevance_avoids_similar_name_noise(self) -> None:
        """HK stock matching should prefer exact company/code over similar-name news."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="HKProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "騰訊音樂釋出新專輯合作計劃",
                            fresh,
                            snippet="騰訊音樂娛樂集團宣佈內容合作。",
                        ),
                        _result(
                            "騰訊控股 AAPL 公告：回購股份",
                            fresh,
                            snippet="騰訊控股在港交所披露股份回購公告。",
                            source="hkexnews",
                        ),
                    ]
                )
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("hkAAPL", "騰訊控股", max_results=2)

        self.assertEqual(resp.results[0].title, "騰訊控股 AAPL 公告：回購股份")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        self.assertEqual(resp.results[1].relevance_category, "sector_related_news")

    def test_hk_stock_bare_short_code_does_not_match_index_points(self) -> None:
        """Bare HK short codes should not make index-point headlines direct hits."""
        result = SearchService._score_news_relevance(
            _result(
                "恒生指數大漲700點 科技股普遍反彈",
                datetime.now().date().isoformat(),
                snippet="美股市場情緒回暖，指數走強。",
            ),
            stock_code="hkAAPL",
            stock_name="騰訊控股",
        )

        self.assertNotEqual(result.relevance_category, "direct_company_news")
        self.assertNotIn("股票代號 700", "；".join(result.relevance_reasons or []))

    def test_us_stock_ticker_relevance_beats_ambiguous_company_word(self) -> None:
        """US ticker hits should outrank ambiguous common-word company-name noise."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="USProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "Apple growers face lower fruit prices",
                            fresh,
                            snippet="Agriculture market report on orchards.",
                        ),
                        _result(
                            "AAPL Apple earnings beat analyst expectations",
                            fresh,
                            snippet="Apple shares rose after quarterly revenue guidance improved.",
                        ),
                    ]
                )
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("AAPL", "Apple", max_results=2)

        self.assertEqual(resp.results[0].title, "AAPL Apple earnings beat analyst expectations")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        self.assertEqual(resp.results[1].relevance_category, "sector_related_news")

    def test_ambiguous_company_name_with_generic_event_terms_stays_background(self) -> None:
        """Generic event words should not make ambiguous company names direct without ticker."""
        scored = SearchService._score_news_relevance(
            _result(
                "Apple stock results harvest",
                datetime.now().date().isoformat(),
                snippet="Agriculture market report on orchards.",
            ),
            stock_code="AAPL",
            stock_name="Apple",
        )

        self.assertNotEqual(scored.relevance_category, "direct_company_news")
        self.assertFalse(
            any(
                reason.startswith(("標題命中股票代號", "摘要命中股票代號", "連結命中股票代號"))
                for reason in (scored.relevance_reasons or [])
            )
        )

    def test_suffixed_stock_codes_keep_canonical_identity_terms(self) -> None:
        """Suffixed market codes should still emit canonical direct-match variants."""
        cases = (
            ("AAPL", {"AAPL", "AAPL"}),
            ("2330.TW", {"2330", "2330.TW"}),
            ("AAPL.US", {"AAPL", "NASDAQ:AAPL", "NYSE:AAPL"}),
        )
        for stock_code, expected_terms in cases:
            with self.subTest(stock_code=stock_code):
                terms = set(SearchService._stock_code_identity_terms(stock_code))
                self.assertTrue(expected_terms.issubset(terms))

    def test_suffixed_market_codes_score_canonical_code_hits_as_direct(self) -> None:
        """Canonical code hits from suffixed inputs should be direct company news."""
        fresh = datetime.now().date().isoformat()
        cases = (
            ("AAPL", "AAPL announces buyback"),
            ("2330.TW", "2330 釋出回購公告"),
            ("AAPL.US", "AAPL announces quarterly results"),
        )
        for stock_code, title in cases:
            with self.subTest(stock_code=stock_code):
                scored = SearchService._score_news_relevance(
                    _result(
                        title,
                        fresh,
                        snippet="The company reported a share buyback and quarterly results.",
                    ),
                    stock_code=stock_code,
                    stock_name="Unmatched Name",
                )
                self.assertEqual(scored.relevance_category, "direct_company_news")
                self.assertIn("股票代號", "；".join(scored.relevance_reasons or []))

    def test_us_ticker_matches_before_known_dotted_market_suffix(self) -> None:
        """Ticker boundaries should allow explicit market suffixes from news feeds."""
        self.assertTrue(
            SearchService._contains_stock_code_identity_term("AAPL.US shares rally", "AAPL")
        )
        self.assertTrue(
            SearchService._contains_stock_code_identity_term("aapl.us shares rally", "AAPL")
        )
        self.assertTrue(
            SearchService._contains_stock_code_identity_term("aapl shares rally", "AAPL")
        )
        self.assertTrue(
            SearchService._contains_stock_code_identity_term("TSLA.O gains after results", "TSLA")
        )
        self.assertTrue(
            SearchService._contains_stock_code_identity_term("tsla.o gains after results", "TSLA")
        )
        self.assertFalse(
            SearchService._contains_stock_code_identity_term("AAPL.COM launches update", "AAPL")
        )

        scored = SearchService._score_news_relevance(
            _result(
                "msft.us earnings beat expectations",
                datetime.now().date().isoformat(),
                snippet="Quarterly revenue guidance improved.",
            ),
            stock_code="MSFT",
            stock_name="Microsoft",
        )
        self.assertEqual(scored.relevance_category, "direct_company_news")
        self.assertIn("股票代號", "；".join(scored.relevance_reasons or []))

    def test_one_letter_us_ticker_does_not_match_common_article_words(self) -> None:
        """Bare one-letter US tickers should not make ordinary words direct hits."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        p1 = SimpleNamespace(
            is_available=True,
            name="GenericProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "A new investing playbook emerges",
                            fresh,
                            snippet="Markets weigh a broad macro update.",
                        )
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="CompanyProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "Agilent Technologies announces quarterly earnings",
                            fresh,
                            snippet="Agilent Technologies revenue guidance improved.",
                        )
                    ]
                )
            ),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("A", "Agilent Technologies", max_results=1)

        self.assertEqual(resp.results[0].title, "Agilent Technologies announces quarterly earnings")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        p1.search.assert_called_once()
        p2.search.assert_called_once()

    def test_common_word_us_ticker_does_not_match_title_case_words(self) -> None:
        """Bare alphabetic tickers should not turn ordinary words into direct hits."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        p1 = SimpleNamespace(
            is_available=True,
            name="GenericProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "All investors brace for inflation data",
                            fresh,
                            snippet="Market participants watch a broad macro update.",
                        )
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="CompanyProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "ALL Allstate quarterly earnings beat expectations",
                            fresh,
                            snippet="Allstate revenue guidance improved after quarterly results.",
                        )
                    ]
                )
            ),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("ALL", "Allstate", max_results=1)

        self.assertEqual(resp.results[0].title, "ALL Allstate quarterly earnings beat expectations")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        p1.search.assert_called_once()
        p2.search.assert_called_once()

    def test_ambiguous_english_name_generic_event_does_not_stop_provider_fallback(self) -> None:
        """Ambiguous title-only names plus broad event words should not count as direct hits."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            bocha_keys=["dummy_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        p1 = SimpleNamespace(
            is_available=True,
            name="AmbiguousProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "Apple stock results improve after harvest update",
                            fresh,
                            snippet="Fruit market coverage tracks inventory and crop supply.",
                        )
                    ]
                )
            ),
        )
        p2 = SimpleNamespace(
            is_available=True,
            name="TickerProvider",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "AAPL Apple earnings beat analyst expectations",
                            fresh,
                            snippet="Apple revenue guidance improved after quarterly earnings.",
                        )
                    ]
                )
            ),
        )
        service._providers = [p1, p2]

        resp = service.search_stock_news("AAPL", "Apple", max_results=1)

        self.assertEqual(resp.results[0].title, "AAPL Apple earnings beat analyst expectations")
        self.assertEqual(resp.results[0].relevance_category, "direct_company_news")
        p1.search.assert_called_once()
        p2.search.assert_called_once()

    def test_relevance_metadata_is_visible_in_news_context(self) -> None:
        result = SearchResult(
            title="台積電 2330 釋出公告",
            snippet="公司披露董事會決議。",
            url="https://example.com/news",
            source="cninfo",
            published_date=datetime.now().date().isoformat(),
            relevance_score=100,
            relevance_category="direct_company_news",
            relevance_reasons=["標題命中股票代號 2330", "標題命中公司名 台積電"],
        )
        context = SearchResponse(query="台積電", results=[result], provider="Unit").to_context()

        self.assertIn("關聯度", context)
        self.assertIn("direct_company_news", context)
        self.assertIn("標題命中股票代號 2330", context)

    def test_search_stock_news_brave_locale_matches_market_context(self) -> None:
        """Brave locale should follow Chinese-preferred vs US-stock contexts."""
        fresh_dt = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_iso = fresh_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        for stock_code, stock_name, expected_lang, expected_country, title, description in (
            ("2330", "台積電", "zh-hans", "CN", "中文資訊", "中文摘要"),
            ("AAPL", "Apple", "en", "US", "Apple earnings beat", "English summary"),
        ):
            with self.subTest(stock_code=stock_code):
                fake_response = MagicMock()
                fake_response.status_code = 200
                fake_response.json.return_value = {
                    "web": {
                        "results": [
                            {
                                "title": title,
                                "description": description,
                                "url": "https://example.com/news",
                                "age": fresh_iso,
                            }
                        ]
                    }
                }

                with patch("src.search_service.requests.get", return_value=fake_response) as mock_get:
                    service = SearchService(
                        brave_keys=["dummy_key"],
                        searxng_public_instances_enabled=False,
                        news_max_age_days=3,
                        news_strategy_profile="short",
                    )
                    resp = service.search_stock_news(stock_code, stock_name, max_results=1)

                self.assertEqual(len(resp.results), 1)
                params = mock_get.call_args.kwargs["params"]
                self.assertEqual(params["search_lang"], expected_lang)
                self.assertEqual(params["country"], expected_country)

    def test_search_comprehensive_intel_splits_strict_and_non_strict_filters(self) -> None:
        """Latest news stays strict while market analysis keeps undated results."""
        today = datetime.now().date()
        old = (today - timedelta(days=20)).isoformat()
        fresh = (today - timedelta(days=1)).isoformat()
        analysis_dt = datetime.now(timezone.utc).replace(microsecond=0)
        analysis_text = analysis_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        expected_analysis_date = analysis_dt.astimezone().date().isoformat()

        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="medium",  # min(7,3)=3
        )
        mock_search.side_effect = _comprehensive_intel_responses(
            _response([_result("old", old), _result("fresh", fresh)]),
            _response([_result("analysis_unknown", None), _result("analysis_dated", analysis_text)]),
        )
        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel(
                stock_code="2330",
                stock_name="台積電",
                max_searches=2,
            )

        self.assertGreaterEqual(mock_search.call_count, 1)
        for call in mock_search.call_args_list:
            kwargs = call[1]
            self.assertEqual(kwargs["days"], 3)
            self.assertEqual(kwargs["max_results"], 6)  # target 3 -> overfetch 6

        self.assertEqual([item.title for item in intel["latest_news"].results], ["fresh"])
        self.assertEqual(
            [item.title for item in intel["market_analysis"].results],
            ["analysis_unknown", "analysis_dated"],
        )
        self.assertIsNone(intel["market_analysis"].results[0].published_date)
        self.assertEqual(intel["market_analysis"].results[1].published_date, expected_analysis_date)

    def test_search_comprehensive_intel_etf_risk_check_keeps_unknown_dates(self) -> None:
        """ETF risk_check should avoid strict freshness filtering."""
        fresh_dt = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_text = fresh_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        expected_fresh_date = fresh_dt.astimezone().date().isoformat()

        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        mock_search.side_effect = _comprehensive_intel_responses(
            _response([_result("latest_news", fresh_text)]),
            _response([_result("market_analysis_unknown", None)]),
            _response([_result("risk_unknown", None)]),
            latest_variant_count=1,
        )

        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel(
                stock_code="510300",
                stock_name="滬深300ETF",
                max_searches=3,
            )

        self.assertEqual(intel["latest_news"].results[0].published_date, expected_fresh_date)
        self.assertEqual([item.title for item in intel["market_analysis"].results], ["market_analysis_unknown"])
        self.assertIsNone(intel["market_analysis"].results[0].published_date)
        self.assertEqual([item.title for item in intel["risk_check"].results], ["risk_unknown"])
        self.assertIsNone(intel["risk_check"].results[0].published_date)

    def test_search_comprehensive_intel_non_etf_risk_check_stays_strict(self) -> None:
        """Non-ETF risk_check should keep strict freshness filtering."""
        fresh_dt = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_text = fresh_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        expected_fresh_date = fresh_dt.astimezone().date().isoformat()

        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        mock_search.side_effect = _comprehensive_intel_responses(
            _response([_result("latest_news", fresh_text)]),
            _response([_result("market_analysis_unknown", None)]),
            _response([_result("risk_unknown", None)]),
        )

        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel(
                stock_code="2330",
                stock_name="台積電",
                max_searches=3,
            )

        self.assertEqual(intel["latest_news"].results[0].published_date, expected_fresh_date)
        self.assertEqual([item.title for item in intel["market_analysis"].results], ["market_analysis_unknown"])
        self.assertIsNone(intel["market_analysis"].results[0].published_date)
        self.assertEqual(intel["risk_check"].results, [])

    def test_announcements_dimension_included_within_max_searches_5(self) -> None:
        """announcements is now at index 3 so it is processed when max_searches>=4."""
        fresh_dt = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_text = fresh_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        mock_search.side_effect = _comprehensive_intel_responses(
            _response([_result("latest_news", fresh_text)]),
            _response([_result("market_analysis", None)]),
            _response([_result("risk_check", fresh_text)]),
            _response([_result("announcement_item", fresh_text)]),
        )

        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel(
                stock_code="2330",
                stock_name="台積電",
                max_searches=4,
            )

        self.assertIn("announcements", intel)
        self.assertEqual(
            [item.title for item in intel["announcements"].results],
            ["announcement_item"],
        )

    def test_announcements_dimension_uses_news_topic_and_strict_filter(self) -> None:
        """announcements uses tavily_topic='news' and strict_freshness=True."""
        fresh_dt = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_text = fresh_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (datetime.now().date() - timedelta(days=30)).isoformat()

        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        mock_search.side_effect = _comprehensive_intel_responses(
            _response([_result("latest_news", fresh_text)]),
            _response([_result("market_analysis", None)]),
            _response([_result("risk_check", fresh_text)]),
            _response([_result("old_announcement", old), _result("fresh_announcement", fresh_text)]),
        )

        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel(
                stock_code="2330",
                stock_name="台積電",
                max_searches=4,
            )

        self.assertIn("announcements", intel)
        # strict_freshness=True: stale result is filtered out
        titles = [item.title for item in intel["announcements"].results]
        self.assertNotIn("old_announcement", titles)
        self.assertIn("fresh_announcement", titles)

    def test_announcements_etf_is_not_strict(self) -> None:
        """For ETF, announcements dimension also uses tavily_topic='news' and strict_freshness=True."""
        fresh_dt = datetime.now(timezone.utc).replace(microsecond=0)
        fresh_text = fresh_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        service, mock_search = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        mock_search.side_effect = _responses_then_empty(
            _response([_result("latest_news", fresh_text)]),
            _response([_result("market_analysis", None)]),
            _response([_result("risk_check", None)]),
            _response([_result("announcement_item", fresh_text)]),
        )

        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel(
                stock_code="510300",
                stock_name="滬深300ETF",
                max_searches=4,
            )

        self.assertIn("announcements", intel)

    def test_effective_window_helper_has_no_side_effect(self) -> None:
        """_effective_news_window_days should not mutate stored news_window_days."""
        service, _ = self._create_service_with_mock_provider(
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        service.news_window_days = 99
        resolved = service._effective_news_window_days()
        self.assertEqual(resolved, 3)
        self.assertEqual(service.news_window_days, 99)

    def test_unix_timestamp_normalizes_to_local_date(self) -> None:
        """Unix timestamp should be converted to local date before window filtering."""
        dt_utc = datetime(2026, 3, 15, 23, 30, tzinfo=timezone.utc)
        timestamp = str(int(dt_utc.timestamp()))
        expected_local_date = dt_utc.astimezone().date()
        parsed = SearchService._normalize_news_publish_date(timestamp)
        self.assertEqual(parsed, expected_local_date)

    def test_iso_utc_string_normalizes_to_local_date(self) -> None:
        """ISO datetime with timezone should be converted to local date."""
        dt_utc = datetime(2026, 3, 15, 23, 30, tzinfo=timezone.utc)
        iso_text = "2026-03-15T23:30:00Z"
        expected_local_date = dt_utc.astimezone().date()
        parsed = SearchService._normalize_news_publish_date(iso_text)
        self.assertEqual(parsed, expected_local_date)

    def test_rfc_utc_string_normalizes_to_local_date(self) -> None:
        """RFC datetime with timezone should be converted to local date."""
        dt_utc = datetime(2026, 3, 15, 23, 30, tzinfo=timezone.utc)
        rfc_text = "Sun, 15 Mar 2026 23:30:00 +0000"
        expected_local_date = dt_utc.astimezone().date()
        parsed = SearchService._normalize_news_publish_date(rfc_text)
        self.assertEqual(parsed, expected_local_date)

    def test_tw_news_query_variants_continue_until_results(self) -> None:
        """TW related-info search should try required variants instead of stopping at the first empty query."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    _response([]),
                    _response([
                        _result(
                            "台積電 2330 財報法說重點",
                            fresh,
                            snippet="台積電法說會聚焦 AI 需求與先進製程。",
                        )
                    ]),
                ]
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("2330", "台積電", max_results=3)

        self.assertEqual([item.title for item in resp.results], ["台積電 2330 財報法說重點"])
        queries = [call.args[0] for call in provider.search.call_args_list]
        self.assertGreaterEqual(len(queries), 2)
        self.assertEqual(queries[:2], ["2330 台積電 新聞", "台積電 最新消息"])

    def test_us_news_query_variants_continue_until_results(self) -> None:
        """US related-info search should try stock/earnings/market variants."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    _response([]),
                    _response([
                        _result(
                            "Apple earnings lift AAPL stock",
                            fresh,
                            snippet="Apple earnings and services revenue supported shares.",
                        )
                    ]),
                ]
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("AAPL", "Apple", max_results=3)

        self.assertEqual([item.title for item in resp.results], ["Apple earnings lift AAPL stock"])
        queries = [call.args[0] for call in provider.search.call_args_list]
        self.assertGreaterEqual(len(queries), 2)
        self.assertEqual(queries[:2], ["AAPL Apple stock news", "Apple earnings stock news"])

    def test_news_provider_error_does_not_stop_query_variants(self) -> None:
        """Provider errors should keep trying remaining variants/providers before giving up."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    SearchResponse(
                        query="AAPL Apple stock news",
                        results=[],
                        provider="MockProvider",
                        success=False,
                        error_message="請求超時",
                    ),
                    _response([
                        _result(
                            "Apple iPhone services market news",
                            fresh,
                            snippet="Apple services growth and iPhone demand remain in focus.",
                        )
                    ]),
                ]
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("AAPL", "Apple", max_results=3)

        self.assertEqual([item.title for item in resp.results], ["Apple iPhone services market news"])
        self.assertGreaterEqual(provider.search.call_count, 2)

    def test_primary_provider_error_uses_next_provider(self) -> None:
        """A failing primary provider should fall through to the next configured provider."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        failing_provider = SimpleNamespace(
            is_available=True,
            name="PrimaryProvider",
            search=MagicMock(
                return_value=SearchResponse(
                    query="AAPL Apple stock news",
                    results=[],
                    provider="PrimaryProvider",
                    success=False,
                    error_message="請求超時",
                )
            ),
        )
        fallback_provider = SimpleNamespace(
            is_available=True,
            name="FallbackProvider",
            search=MagicMock(
                return_value=_response([
                    _result(
                        "AAPL Apple Reuters market update",
                        fresh,
                        snippet="Apple stock news returned by fallback provider.",
                    )
                ])
            ),
        )
        service._providers = [failing_provider, fallback_provider]

        resp = service.search_stock_news("AAPL", "Apple", max_results=3)

        self.assertEqual([item.title for item in resp.results], ["AAPL Apple Reuters market update"])
        failing_provider.search.assert_called_once()
        fallback_provider.search.assert_called_once()

    def test_unknown_publish_date_results_are_last_resort_news_fallback(self) -> None:
        """SearXNG-style results without publishedDate should be usable after strict-date variants are exhausted."""
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="SearXNG",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "NVIDIA AI GPU market update",
                            None,
                            snippet="NVIDIA AI GPU demand remains a key stock-market topic.",
                            source="example.com",
                        )
                    ]
                )
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("NVDA", "NVIDIA", max_results=3)

        self.assertEqual([item.title for item in resp.results], ["NVIDIA AI GPU market update"])
        self.assertIsNone(resp.results[0].published_date)
        self.assertTrue(resp.success)

    def test_stale_publish_date_results_are_latest_news_fallback(self) -> None:
        """If no recent items exist, keep latest provider results instead of silent no-news."""
        stale = (datetime.now().date() - timedelta(days=90)).isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="SearXNG",
            search=MagicMock(
                return_value=_response(
                    [
                        _result(
                            "NVIDIA older market update",
                            stale,
                            snippet="NVIDIA stock coverage is older but still a real provider result.",
                        )
                    ]
                )
            ),
        )
        service._providers = [provider]

        resp = service.search_stock_news("NVDA", "NVIDIA", max_results=3)

        self.assertEqual([item.title for item in resp.results], ["NVIDIA older market update"])
        self.assertEqual(resp.results[0].published_date, stale)
        self.assertTrue(resp.success)

    def test_comprehensive_intel_latest_news_uses_query_variants(self) -> None:
        """Report pipeline intel search should persist latest_news from the robust variant path."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    _response([]),
                    _response([
                        _result(
                            "Apple earnings lift AAPL stock",
                            fresh,
                            snippet="Apple earnings and services revenue supported shares.",
                        )
                    ]),
                ]
            ),
        )
        service._providers = [provider]

        with patch("src.search_service.time.sleep"):
            intel = service.search_comprehensive_intel("AAPL", "Apple", max_searches=1)

        self.assertIn("latest_news", intel)
        self.assertEqual(
            [item.title for item in intel["latest_news"].results],
            ["Apple earnings lift AAPL stock"],
        )
        queries = [call.args[0] for call in provider.search.call_args_list]
        self.assertEqual(queries[:2], ["AAPL Apple stock news", "Apple earnings stock news"])

    def test_search_diagnostics_include_tw_query_variants(self) -> None:
        """News diagnostics should expose sanitized TW query variants."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(return_value=_response([_result("台積電新聞", fresh)])),
        )
        service._providers = [provider]

        response = service.search_stock_news("2330", "台積電")

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(
            diagnostics["query_variants"][:3],
            ["2330 台積電 新聞", "台積電 最新消息", "台積電 財報 法說 產業"],
        )
        self.assertIn("TSMC Taiwan Semiconductor news", diagnostics["query_variants"])
        self.assertEqual(diagnostics["providers_attempted"], ["MockProvider"])
        self.assertEqual(diagnostics["attempt_count"], 1)
        self.assertEqual(diagnostics["result_count"], 1)
        self.assertEqual(diagnostics["final_status"], "available")

    def test_2317_news_query_variants_include_hon_hai_foxconn_aliases(self) -> None:
        """2317 should search 鴻海 and known English aliases, not only broad TW market terms."""
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(return_value=_response([_result("鴻海新聞", datetime.now().date().isoformat())])),
        )
        service._providers = [provider]

        response = service.search_stock_news("2317", "鴻海", max_results=3)

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(
            diagnostics["query_variants"][:3],
            ["2317 鴻海 新聞", "鴻海 最新消息", "鴻海 財報 法說 產業"],
        )
        self.assertIn("Hon Hai Foxconn news", diagnostics["query_variants"])

    def test_2317_news_prefers_later_alias_relevant_result_over_broad_unrelated_result(self) -> None:
        """A broad unrelated first result must not dominate when a later alias query returns 2317-relevant news."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    _response([
                        _result(
                            "Taiwan navy market update",
                            fresh,
                            snippet="A broad Taiwan geopolitical headline without Hon Hai or Foxconn relevance.",
                        )
                    ]),
                    _response([]),
                    _response([]),
                    _response([
                        _result(
                            "Hon Hai Foxconn AI server revenue update",
                            fresh,
                            snippet="Foxconn and Hon Hai revenue news for 2317 investors.",
                            source="example.com",
                        )
                    ]),
                ]
            ),
        )
        service._providers = [provider]

        response = service.search_stock_news("2317", "鴻海", max_results=3)

        self.assertEqual(
            [item.title for item in response.results],
            ["Hon Hai Foxconn AI server revenue update"],
        )
        self.assertGreaterEqual(provider.search.call_count, 4)
        self.assertEqual(response.results[0].relevance_category, SearchService._DIRECT_NEWS_CATEGORY)

    def test_3008_news_query_variants_include_largan_aliases(self) -> None:
        """3008 should search 大立光 and Largan aliases for related-info relevance."""
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(return_value=_response([_result("大立光新聞", datetime.now().date().isoformat())])),
        )
        service._providers = [provider]

        response = service.search_stock_news("3008", "大立光", max_results=3)

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(
            diagnostics["query_variants"][:3],
            ["3008 大立光 新聞", "大立光 最新消息", "大立光 財報 法說 產業"],
        )
        self.assertIn("Largan Precision news", diagnostics["query_variants"])
        self.assertIn("Largan stock news", diagnostics["query_variants"])

    def test_3008_news_prefers_later_largan_relevant_result_over_broad_result(self) -> None:
        """Broad optical-sector news should not dominate when Largan-specific news is available."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    _response([
                        _result(
                            "Taiwan optics sector market update",
                            fresh,
                            snippet="A broad lens supply-chain headline without direct company identity.",
                        )
                    ]),
                    _response([]),
                    _response([]),
                    _response([
                        _result(
                            "Largan Precision earnings and iPhone lens order update",
                            fresh,
                            snippet="Largan and 大立光 revenue news for 3008 investors.",
                            source="example.com",
                        )
                    ]),
                ]
            ),
        )
        service._providers = [provider]

        response = service.search_stock_news("3008", "大立光", max_results=3)

        self.assertEqual(
            [item.title for item in response.results],
            ["Largan Precision earnings and iPhone lens order update"],
        )
        self.assertGreaterEqual(provider.search.call_count, 4)
        self.assertEqual(response.results[0].relevance_category, SearchService._DIRECT_NEWS_CATEGORY)

    def test_search_diagnostics_include_us_query_variants(self) -> None:
        """News diagnostics should expose sanitized US query variants."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(return_value=_response([_result("AAPL Apple earnings stock news", fresh)])),
        )
        service._providers = [provider]

        response = service.search_stock_news("AAPL", "Apple")

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(
            diagnostics["query_variants"][:3],
            [
                "AAPL Apple stock news",
                "Apple earnings stock news",
                "Apple iPhone services market news",
            ],
        )
        self.assertEqual(diagnostics["providers_attempted"], ["MockProvider"])
        self.assertEqual(diagnostics["attempt_count"], 1)
        self.assertEqual(diagnostics["result_count"], 1)
        self.assertEqual(diagnostics["final_status"], "available")

    def test_nvda_news_query_variants_include_ai_gpu_data_center_terms(self) -> None:
        """NVDA should search direct NVIDIA and AI/GPU/data-center earnings variants."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(return_value=_response([_result("NVDA NVIDIA stock news", fresh)])),
        )
        service._providers = [provider]

        response = service.search_stock_news("NVDA", "NVIDIA")

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(
            diagnostics["query_variants"][:3],
            [
                "NVDA NVIDIA stock news",
                "NVIDIA earnings stock news",
                "NVIDIA earnings AI GPU stock news",
            ],
        )
        self.assertIn("NVIDIA AI chip GPU data center earnings", diagnostics["query_variants"])

    def test_nvda_relevant_company_news_ranks_above_broad_sector_card(self) -> None:
        """Direct NVIDIA news should rank before broad AI-sector cards."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                return_value=_response([
                    _result(
                        "AI chip sector market update",
                        fresh,
                        snippet="Broad GPU demand lifted semiconductor peers without a direct company update.",
                    ),
                    _result(
                        "NVIDIA NVDA data center earnings update",
                        fresh,
                        snippet="NVIDIA AI GPU and data center revenue remain the core NVDA stock catalyst.",
                    ),
                ])
            ),
        )
        service._providers = [provider]

        response = service.search_stock_news("NVDA", "NVIDIA", max_results=2)

        self.assertEqual(response.results[0].title, "NVIDIA NVDA data center earnings update")
        self.assertEqual(response.results[0].relevance_category, SearchService._DIRECT_NEWS_CATEGORY)

    def test_search_diagnostics_records_empty_first_query_continuation(self) -> None:
        """Diagnostics should prove an empty first query did not stop the search."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                side_effect=[
                    _response([]),
                    _response([_result("台積電最新消息", fresh)]),
                ]
            ),
        )
        service._providers = [provider]

        response = service.search_stock_news("2330", "台積電")

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(provider.search.call_count, 2)
        self.assertEqual(diagnostics["attempt_count"], 2)
        self.assertEqual(diagnostics["result_count"], 1)
        self.assertIs(diagnostics["fallback_used"], True)
        self.assertEqual(diagnostics["final_status"], "available")

    def test_search_diagnostics_records_provider_error_fallback(self) -> None:
        """Diagnostics should mark fallback when a provider error is bypassed."""
        fresh = datetime.now().date().isoformat()
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        failing_provider = SimpleNamespace(
            is_available=True,
            name="PrimaryProvider",
            search=MagicMock(
                return_value=SearchResponse(
                    query="AAPL Apple stock news",
                    results=[],
                    provider="PrimaryProvider",
                    success=False,
                    error_message="provider failed",
                )
            ),
        )
        fallback_provider = SimpleNamespace(
            is_available=True,
            name="FallbackProvider",
            search=MagicMock(return_value=_response([_result("AAPL Apple market news", fresh)])),
        )
        service._providers = [failing_provider, fallback_provider]

        response = service.search_stock_news("AAPL", "Apple")

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(diagnostics["providers_attempted"], ["PrimaryProvider", "FallbackProvider"])
        self.assertEqual(diagnostics["attempt_count"], 2)
        self.assertIs(diagnostics["fallback_used"], True)
        self.assertEqual(diagnostics["final_status"], "available")
        self.assertEqual(diagnostics["result_count"], 1)
        self.assertIn("provider_error", diagnostics["error_types"])

    def test_search_diagnostics_records_provider_timeout_fallback(self) -> None:
        """Diagnostics should record timeout fallback without exposing error text."""
        fresh = datetime.now().date().isoformat()
        sensitive_marker = "phase15-sensitive-marker"
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        timeout_provider = SimpleNamespace(
            is_available=True,
            name="TimeoutProvider",
            search=MagicMock(side_effect=TimeoutError(f"timeout while using {sensitive_marker}")),
        )
        fallback_provider = SimpleNamespace(
            is_available=True,
            name="FallbackProvider",
            search=MagicMock(return_value=_response([_result("AAPL Apple market news", fresh)])),
        )
        service._providers = [timeout_provider, fallback_provider]

        response = service.search_stock_news("AAPL", "Apple")

        diagnostics = _news_search_diagnostics(response)
        serialized = str(diagnostics)
        self.assertEqual(diagnostics["attempt_count"], 2)
        self.assertIs(diagnostics["fallback_used"], True)
        self.assertEqual(diagnostics["final_status"], "available")
        self.assertIn("timeout", diagnostics["error_types"])
        self.assertNotIn(sensitive_marker, serialized)

    def test_search_diagnostics_prevents_fake_news_items(self) -> None:
        """Diagnostics must not fabricate item titles or URLs when providers fail."""
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                return_value=SearchResponse(
                    query="2330 台積電 新聞",
                    results=[],
                    provider="MockProvider",
                    success=False,
                    error_message="failed",
                )
            ),
        )
        service._providers = [provider]

        response = service.search_stock_news("2330", "台積電")

        diagnostics = _news_search_diagnostics(response)
        self.assertEqual(response.results, [])
        self.assertEqual(diagnostics["result_count"], 0)
        self.assertNotIn("items", diagnostics)
        self.assertNotIn("titles", diagnostics)
        self.assertNotIn("urls", diagnostics)

    def test_search_diagnostics_are_sanitized(self) -> None:
        """Diagnostics must omit credential-like provider error details."""
        credential_text = "phase15-sensitive-marker"
        service = SearchService(
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short",
        )
        provider = SimpleNamespace(
            is_available=True,
            name="MockProvider",
            search=MagicMock(
                return_value=SearchResponse(
                    query="AAPL Apple stock news",
                    results=[],
                    provider="MockProvider",
                    success=False,
                    error_message=credential_text,
                )
            ),
        )
        service._providers = [provider]

        response = service.search_stock_news("AAPL", "Apple")

        diagnostics = _news_search_diagnostics(response)
        serialized = str(diagnostics)
        self.assertGreaterEqual(diagnostics["attempt_count"], 1)
        self.assertNotIn(credential_text, serialized)
        self.assertNotIn("raw_payload", diagnostics)


if __name__ == "__main__":
    unittest.main()

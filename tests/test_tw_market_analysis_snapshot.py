from __future__ import annotations

import json
import unittest
from datetime import date, timedelta

from src.services.tw_market_analysis_snapshot import (
    _judgement,
    _support_zone_state,
    build_tw_market_analysis_snapshot,
    compose_tw_market_analysis_article,
)


def _bars(count: int = 260, *, start: date = date(2025, 7, 1), slope: float = 1.0):
    rows = []
    current = start
    close = 1000.0
    while len(rows) < count:
        if current.weekday() < 5:
            open_ = close - 2
            rows.append({
                "date": current.isoformat(),
                "open": open_,
                "high": close + 5,
                "low": open_ - 4,
                "close": close,
            })
            close += slope
        current += timedelta(days=1)
    return rows


def _values(bars):
    return [{"date": row["date"], "value": 100_000_000_000 + index * 1_000_000_000} for index, row in enumerate(bars)]


def _meta(provider: str, endpoint: str, metric: str, unit: str):
    return {
        "provider": provider,
        "endpoint_family": endpoint,
        "index_kind": "price_index" if metric == "ohlc" else None,
        "metric_kind": metric,
        "raw_unit": unit,
        "normalized_unit": unit,
        "requested_months": ["2026-06", "2026-07"],
        "fetched_at": "2026-07-15T01:00:00Z",
        "terms_access_risk": "medium",
    }


def _reference_article_snapshot():
    """Sanitized 2026-07-14 production-shaped facts used for golden prose."""
    ma = {
        "ma5": {"value": 45337.32, "distance_pct": -1.32, "slope": -363.69, "direction": "down", "position": "below"},
        "ma10": {"value": 45991.27, "distance_pct": -2.73, "slope": -26.19, "direction": "down", "position": "below"},
        "ma20": {"value": 46008.71, "distance_pct": -2.76, "slope": 28.45, "direction": "up", "position": "below"},
        "ma60": {"value": 43149.14, "distance_pct": 3.68, "slope": 126.77, "direction": "up", "position": "above"},
        "ma120": {"value": 38127.01, "distance_pct": 17.34, "slope": 119.81, "direction": "up", "position": "above"},
    }
    support = [
        {"lower": 44162.73, "upper": 44745.71, "level": 44454.22, "as_of": "2026-06-26"},
        {"lower": 43362.55, "upper": 43945.53, "level": 43654.04, "as_of": "2026-07-14"},
    ]
    resistance = [{"lower": 46260.67, "upper": 46843.65, "level": 46552.16, "as_of": "2026-06-03"}]
    taiex = {
        "latest_bar": {"date": "2026-07-14", "open": 45364.40, "high": 45364.40, "low": 43654.04, "close": 44737.95},
        "previous_close": 45380.52,
        "change": -642.57,
        "change_pct": -1.41596,
        "moving_averages": ma,
        "ma_alignment": "bearish",
        "momentum": {
            "rsi14": {"value": 47.07, "previous": 50.92, "direction": "deteriorating"},
            "macd": {"dif": 404.53, "signal": 724.82, "histogram": -320.29, "previous_histogram": -274.24, "direction": "deteriorating", "state": "bearish"},
        },
        "atr14": 1165.94,
        "candlestick": {
            "body": 626.45, "range": 1710.36, "upper_shadow": 0.0, "lower_shadow": 1083.91,
            "doji": False, "long_lower_shadow": False, "long_upper_shadow": False,
            "gap": "none", "inside_bar": False, "outside_bar": False,
            "bullish_engulfing": False, "bearish_engulfing": False,
            "completed_close_reclaim": False, "completed_close_breakdown": False,
        },
        "support_levels": support,
        "resistance_levels": resistance,
        "volume_analysis": {"state": "available", "value": 1_245_206_538_568, "ma5": 1_108_467_588_827, "ma20": 1_267_727_552_728.85, "ratio_to_ma20": 0.9822, "direction": "normal", "unit": "TWD"},
    }
    return {
        "kind": "tw_market_analysis_snapshot",
        "analysis_ready": True,
        "data_date": "2026-07-14",
        "generated_at": "2026-07-14T22:30:00+00:00",
        "market_state": "closed",
        "indices": {
            "TAIEX": taiex,
            "TPEx": {"latest_bar": {"date": "2026-07-14", "close": 407.41}, "change": -12.49, "change_pct": -2.9745},
        },
        "market_judgement": {
            "category": "contextual",
            "rule_id": "TREND_MIXED_CONTEXT",
            "confirmation_conditions": [{"rule_id": "CONFIRM_CLOSE_ABOVE_MA20", "text": "收盤站上 MA20 且短期均線轉為多頭排列。", "met": False}],
            "invalidation_conditions": [{"rule_id": "INVALIDATE_SUPPORT_BREAK", "text": "收盤跌破最近確認支撐區。", "met": False, "zone": support[1]}],
        },
        "supporting_evidence": {
            "institutional": {"status": "available", "lag_sessions": 0, "as_of": "2026-07-14", "rows": [
                {"name": "Foreign_Investor", "buy": 455_458_836_889, "sell": 507_351_649_396},
                {"name": "Investment_Trust", "buy": 33_009_561_957, "sell": 22_008_000_701},
                {"name": "total", "buy": 559_645_003_085, "sell": 638_827_400_598},
            ]},
            "margin": {"status": "available", "lag_sessions": 0, "as_of": "2026-07-14", "rows": [
                {"name": "MarginPurchaseMoney", "TodayBalance": 604_034_106_000, "YesBalance": 618_300_058_000},
            ]},
            "representatives": [],
        },
    }


def _testing_zone_snapshot(close_override=None, low_override=None):
    """2026-07-16 production-shaped facts: a severe single-day decline closing
    inside (not below) the tested support zone. Regression fixture for the
    copy-scope/support-zone-semantics bugfix."""
    ma = {
        "ma5": {"value": 45700.0, "distance_pct": -6.6, "slope": -150.0, "direction": "down", "position": "below"},
        "ma10": {"value": 46000.0, "distance_pct": -7.2, "slope": -80.0, "direction": "down", "position": "below"},
        "ma20": {"value": 46200.0, "distance_pct": -7.6, "slope": 10.0, "direction": "up", "position": "below"},
        "ma60": {"value": 41000.0, "distance_pct": 4.1, "slope": 90.0, "direction": "up", "position": "above"},
        "ma120": {"value": 43000.0, "distance_pct": -0.8, "slope": 60.0, "direction": "up", "position": "below"},
    }
    support = [{
        "lower": 42353.0, "upper": 42990.0, "level": 42671.5, "as_of": "2026-07-16",
        "source": "delayed_pivot_or_rolling20", "confirmation_state": "confirmed_close_history",
        "confidence": "medium", "invalidation_rule": "two_closes_beyond_zone",
    }]
    close = 42671.27 if close_override is None else close_override
    low = 42640.00 if low_override is None else low_override
    high, open_ = 45630.0, 45620.0
    taiex = {
        "latest_bar": {"date": "2026-07-16", "open": open_, "high": high, "low": low, "close": close},
        "previous_close": 45625.70,
        "change": close - 45625.70,
        "change_pct": (close - 45625.70) / 45625.70 * 100,
        "moving_averages": ma,
        "ma_alignment": "bearish",
        "momentum": {
            "rsi14": {"value": 34.2, "previous": 41.5, "direction": "deteriorating"},
            "macd": {"dif": -300.0, "signal": -100.0, "histogram": -200.0, "previous_histogram": -150.0, "direction": "deteriorating", "state": "bearish"},
        },
        "atr14": 1450.0,
        "candlestick": {
            "body": abs(close - open_), "range": high - low,
            "upper_shadow": 0.0, "lower_shadow": min(open_, close) - low,
            "doji": False, "long_lower_shadow": False, "long_upper_shadow": False,
            "gap": "none", "inside_bar": False, "outside_bar": False,
            "bullish_engulfing": False, "bearish_engulfing": False,
            "completed_close_reclaim": False,
            # Deliberately stale/true: the legacy 20-session-low proxy this bugfix
            # removes from the support-break decision. Must not drive the verdict.
            "completed_close_breakdown": True,
        },
        "support_levels": support,
        "resistance_levels": [],
        "volume_analysis": {"state": "unavailable"},
    }
    return {
        "kind": "tw_market_analysis_snapshot",
        "analysis_ready": True,
        "data_date": "2026-07-16",
        "generated_at": "2026-07-17T03:26:00+00:00",
        "market_state": "open_incomplete",
        "indices": {
            "TAIEX": taiex,
            "TPEx": {"latest_bar": {"date": "2026-07-16", "close": 300.0}, "change": -22.6, "change_pct": -7.02},
        },
        "market_judgement": {
            "category": "contextual", "rule_id": "TREND_MIXED_CONTEXT",
            "confirmation_conditions": [], "invalidation_conditions": [],
        },
        "supporting_evidence": {
            "institutional": {"status": "suppressed"}, "margin": {"status": "suppressed"}, "representatives": [],
        },
    }


def _article_text(article):
    parts = [
        article.get("headline", ""),
        article.get("market_context", ""),
        article.get("session_summary", ""),
        article.get("core_judgement", {}).get("label", ""),
        article.get("core_judgement", {}).get("summary", ""),
        *article.get("trend_paragraphs", []),
        *article.get("price_action_paragraphs", []),
        article.get("confirmation_paragraph", ""),
        *article.get("supporting_context", []),
    ]
    return "\n".join(part for part in parts if part)


class TwMarketAnalysisSnapshotTest(unittest.TestCase):
    def _build(self, **overrides):
        taiex = _bars()
        kwargs = {
            "taiex_rows": taiex,
            "tpex_rows": [{**row, "close": row["close"] / 100, "open": row["open"] / 100,
                           "high": row["high"] / 100, "low": row["low"] / 100} for row in taiex],
            "twse_traded_value_rows": _values(taiex),
            "tpex_traded_value_rows": _values(taiex),
            "institutional_rows": [{"date": taiex[-1]["date"], "name": "Foreign_Investor", "buy": 120, "sell": 100}],
            "margin_rows": [{"date": taiex[-1]["date"], "name": "MarginPurchaseMoney", "TodayBalance": 110, "YesBalance": 100}],
            "representatives": [{"symbol": "2330", "data_date": taiex[-1]["date"], "close": 1000}],
            "primary_data_date": taiex[-1]["date"],
            "generated_at": "2026-07-15T01:00:00Z",
            "market_now": "2026-07-15T09:30:00+08:00",
            "source_metadata": {
                "TAIEX": _meta("TWSE", "indicesReport/MI_5MINS_HIST", "ohlc", "index_points"),
                "TPEx": _meta("TPEx", "indexInfo/inx", "ohlc", "index_points"),
                "twse_traded_value": _meta("TWSE", "exchangeReport/FMTQIK", "traded_value", "TWD"),
                "tpex_traded_value": _meta("TPEx", "daily_trading_index/st41_result.php", "traded_value", "TWD"),
                "institutional": _meta("FinMind", "TaiwanStockTotalInstitutionalInvestors", "flow", "TWD"),
                "margin": _meta("FinMind", "TaiwanStockTotalMarginPurchaseShortSale", "leverage", "mixed"),
            },
        }
        kwargs.update(overrides)
        return build_tw_market_analysis_snapshot(**kwargs)

    def test_builds_versioned_deterministic_analysis_and_narrative(self) -> None:
        snapshot = self._build()

        self.assertEqual(snapshot["kind"], "tw_market_analysis_snapshot")
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertTrue(snapshot["algorithm_version"])
        self.assertTrue(snapshot["analysis_ready"])
        self.assertEqual(snapshot["indices"]["TAIEX"]["latest_bar"]["date"], snapshot["data_date"])
        self.assertEqual(set(snapshot["indices"]["TAIEX"]["moving_averages"]), {"ma5", "ma10", "ma20", "ma60", "ma120"})
        self.assertIn("rsi14", snapshot["indices"]["TAIEX"]["momentum"])
        self.assertIn("macd", snapshot["indices"]["TAIEX"]["momentum"])
        self.assertIn("atr14", snapshot["indices"]["TAIEX"])
        self.assertTrue(snapshot["market_judgement"]["headline"])
        self.assertTrue(snapshot["narrative"]["moving_average_analysis"])
        narrative_text = json.dumps(snapshot["narrative"], ensure_ascii=False)
        self.assertNotIn("above", narrative_text)
        self.assertNotIn("bullish", narrative_text)
        self.assertEqual(snapshot["source_status"]["TAIEX"]["terms_access_risk"], "medium")
        self.assertEqual(snapshot["source_status"]["institutional"]["provider"], "FinMind")
        self.assertEqual(snapshot["source_status"]["institutional"]["status"], "available")
        self.assertEqual(snapshot["source_status"]["margin"]["provider"], "FinMind")
        json.dumps(snapshot, ensure_ascii=False, allow_nan=False)

    def test_future_rows_are_cut_off_and_prefix_result_is_invariant(self) -> None:
        base = _bars(200)
        cutoff = base[-1]["date"]
        future = _bars(5, start=date.fromisoformat(cutoff) + timedelta(days=1), slope=-20)

        left = self._build(taiex_rows=base, primary_data_date=cutoff)
        right = self._build(taiex_rows=base + future, primary_data_date=cutoff)

        self.assertEqual(left["indices"]["TAIEX"], right["indices"]["TAIEX"])
        self.assertIn("future_rows_dropped", right["source_status"]["TAIEX"]["warnings"])

    def test_taiex_failure_persists_structured_unavailable_snapshot(self) -> None:
        snapshot = self._build(taiex_rows=[])

        self.assertFalse(snapshot["analysis_ready"])
        self.assertEqual(snapshot["source_status"]["TAIEX"]["status"], "unavailable")
        self.assertIn("TAIEX", snapshot["suppression_reasons"])
        self.assertEqual(snapshot["market_judgement"]["rule_id"], "DATA_TAIEX_UNAVAILABLE")

    def test_tpex_and_traded_value_failures_are_local_suppressions(self) -> None:
        snapshot = self._build(tpex_rows=[], twse_traded_value_rows=[])

        self.assertTrue(snapshot["analysis_ready"])
        self.assertNotIn("TPEx", snapshot["indices"])
        self.assertEqual(snapshot["source_status"]["TPEx"]["status"], "suppressed")
        self.assertEqual(snapshot["indices"]["TAIEX"]["volume_analysis"]["state"], "unavailable")
        self.assertNotIn("tpex_breadth", snapshot["narrative"])

    def test_stale_tpex_is_suppressed_without_blocking_taiex(self) -> None:
        taiex = _bars()
        snapshot = self._build(tpex_rows=taiex[:-1])

        self.assertTrue(snapshot["analysis_ready"])
        self.assertEqual(snapshot["source_status"]["TPEx"]["status"], "suppressed")
        self.assertNotIn("TPEx", snapshot["indices"])
        self.assertNotIn("tpex_breadth", snapshot["narrative"])

    def test_current_open_session_row_is_rejected_as_partial(self) -> None:
        taiex = _bars()
        data_date = taiex[-1]["date"]
        snapshot = self._build(
            primary_data_date=data_date,
            market_now=f"{data_date}T10:00:00+08:00",
        )

        self.assertFalse(snapshot["analysis_ready"])
        self.assertEqual(snapshot["market_state"], "open_incomplete")
        self.assertEqual(snapshot["market_judgement"]["rule_id"], "DATA_TAIEX_UNAVAILABLE")

    def test_supporting_data_allows_one_session_lag_and_suppresses_older_rows(self) -> None:
        taiex = _bars()
        exact, previous, older = taiex[-1]["date"], taiex[-2]["date"], taiex[-3]["date"]
        snapshot = self._build(
            institutional_rows=[{"date": previous, "name": "Foreign_Investor", "buy": 90, "sell": 100}],
            margin_rows=[{"date": older, "name": "MarginPurchaseMoney", "TodayBalance": 100, "YesBalance": 90}],
            representatives=[
                {"symbol": "2330", "data_date": exact, "close": 1000},
                {"symbol": "0050", "data_date": "2099-01-01", "close": 9999},
            ],
        )

        self.assertEqual(snapshot["supporting_evidence"]["institutional"]["lag_sessions"], 1)
        self.assertEqual(snapshot["supporting_evidence"]["institutional"]["status"], "lagged")
        self.assertEqual(snapshot["source_status"]["institutional"]["lag_sessions"], 1)
        self.assertEqual(snapshot["supporting_evidence"]["margin"]["status"], "suppressed")
        self.assertEqual(snapshot["source_status"]["margin"]["status"], "suppressed")
        self.assertEqual([item["symbol"] for item in snapshot["supporting_evidence"]["representatives"]], ["2330"])

    def test_deep_intraday_low_with_recovery_above_zone_is_not_misclassified_as_invalidation(self) -> None:
        """Regression for the copy-scope/support-zone-semantics bugfix: a sharp
        drop that closes back above the freshly-formed support zone (an intraday
        test with recovery) must not be reported as a confirmed support break."""
        rows = _bars()
        rows[-1] = {**rows[-1], "open": rows[-2]["close"] - 5, "high": rows[-2]["close"],
                    "low": rows[-2]["low"] - 40, "close": rows[-2]["low"] - 30}
        snapshot = self._build(taiex_rows=rows, primary_data_date=rows[-1]["date"])

        self.assertNotEqual(snapshot["market_judgement"]["category"], "invalidation")
        self.assertFalse(snapshot["market_judgement"]["invalidation_conditions"][0]["met"])


class TwMarketAnalysisArticleGoldenTest(unittest.TestCase):
    def test_reference_snapshot_composes_an_analysis_article_not_a_checklist(self) -> None:
        article = compose_tw_market_analysis_article(_reference_article_snapshot())
        text = _article_text(article)

        self.assertEqual(article["core_judgement"]["label"], "短空中多")
        self.assertIn("低檔出現承接，但尚未確認止跌", article["core_judgement"]["summary"])
        self.assertIn("MA5、MA10 與 MA20", article["trend_paragraphs"][0])
        self.assertIn("MA60 與 MA120", article["trend_paragraphs"][0])
        self.assertIn("RSI14", article["trend_paragraphs"][1])
        self.assertIn("MACD", article["trend_paragraphs"][1])
        self.assertIn("43,363～43,946", article["price_action_paragraphs"][0])
        self.assertIn("成交金額", article["price_action_paragraphs"][0])
        self.assertIn("收盤先站回 MA5", article["confirmation_paragraph"])
        self.assertIn("跌破 43,363～43,946", article["confirmation_paragraph"])
        self.assertIn("法人方向分歧", text)
        self.assertIn("不足以改變技術面", text)
        self.assertNotIn("方向仍待確認", text)
        self.assertNotIn("最新 K 線未出現需要優先標記", text)
        self.assertNotIn("指數低於 MA5，距離", text)
        self.assertNotIn("TREND_MIXED_CONTEXT", text)
        self.assertNotIn("[object Object]", text)

    def test_conflict_matrix_covers_required_market_states(self) -> None:
        base = _reference_article_snapshot()

        bullish = json.loads(json.dumps(base))
        bullish["indices"]["TAIEX"]["ma_alignment"] = "bullish"
        for key in ("ma5", "ma10", "ma20", "ma60", "ma120"):
            bullish["indices"]["TAIEX"]["moving_averages"][key]["position"] = "above"
        bullish["indices"]["TAIEX"]["moving_averages"]["ma5"]["slope"] = 10
        bullish["indices"]["TAIEX"]["momentum"]["rsi14"].update(value=58, direction="improving")
        bullish["indices"]["TAIEX"]["momentum"]["macd"].update(state="bullish", direction="improving")
        self.assertEqual(compose_tw_market_analysis_article(bullish)["core_judgement"]["label"], "短多中多")

        rebound = json.loads(json.dumps(base))
        rebound["indices"]["TAIEX"].update(change=180, change_pct=0.4)
        rebound["indices"]["TAIEX"]["momentum"]["rsi14"].update(value=46, previous=42, direction="improving")
        self.assertIn("技術性反彈", compose_tw_market_analysis_article(rebound)["core_judgement"]["summary"])

        broken = json.loads(json.dumps(base))
        broken["indices"]["TAIEX"]["candlestick"]["completed_close_breakdown"] = True
        broken["market_judgement"]["category"] = "invalidation"
        self.assertIn("原支撐失效", compose_tw_market_analysis_article(broken)["core_judgement"]["summary"])

    def test_optional_sources_are_suppressed_or_labeled_in_article(self) -> None:
        without_tpex = _reference_article_snapshot()
        without_tpex["indices"].pop("TPEx")
        self.assertNotIn("tpex_context", compose_tw_market_analysis_article(without_tpex))

        without_value = _reference_article_snapshot()
        without_value["indices"]["TAIEX"]["volume_analysis"] = {"state": "unavailable"}
        value_text = "\n".join(compose_tw_market_analysis_article(without_value)["price_action_paragraphs"])
        self.assertNotIn("成交金額", value_text)

        lagged = _reference_article_snapshot()
        lagged["supporting_evidence"]["institutional"].update(status="lagged", lag_sessions=1, as_of="2026-07-13")
        supporting = "\n".join(compose_tw_market_analysis_article(lagged)["supporting_context"])
        self.assertIn("落後一個交易日", supporting)

        unavailable = _reference_article_snapshot()
        unavailable["analysis_ready"] = False
        article = compose_tw_market_analysis_article(unavailable)
        self.assertEqual(article["status"], "unavailable")
        self.assertEqual(article["trend_paragraphs"], [])


class TwSupportZoneStateTest(unittest.TestCase):
    """Pure classifier: ABOVE_ZONE / TESTING_ZONE / BROKEN_ZONE boundary semantics."""

    ZONE = {"lower": 100.0, "upper": 110.0}

    def test_close_above_zone_upper_is_above_zone(self) -> None:
        self.assertEqual(_support_zone_state(111.0, self.ZONE), "above_zone")

    def test_close_exactly_at_upper_boundary_is_testing_zone(self) -> None:
        self.assertEqual(_support_zone_state(110.0, self.ZONE), "testing_zone")

    def test_close_inside_zone_is_testing_zone(self) -> None:
        self.assertEqual(_support_zone_state(105.0, self.ZONE), "testing_zone")

    def test_close_exactly_at_lower_boundary_is_testing_zone(self) -> None:
        self.assertEqual(_support_zone_state(100.0, self.ZONE), "testing_zone")

    def test_close_below_zone_lower_is_broken_zone(self) -> None:
        self.assertEqual(_support_zone_state(99.99, self.ZONE), "broken_zone")

    def test_missing_zone_is_unavailable(self) -> None:
        self.assertEqual(_support_zone_state(105.0, None), "unavailable")


class TwJudgementSupportZonePriorityTest(unittest.TestCase):
    def test_confirmed_support_break_takes_priority_over_confirmed_trend(self) -> None:
        analysis = {
            "latest_bar": {"close": 990.0},
            "change": 5.0,
            "moving_averages": {
                "ma20": {"value": 950.0, "slope": 5.0},
                "ma60": {"value": 900.0}, "ma120": {"value": 850.0},
            },
            "ma_alignment": "bullish",
            "support_levels": [{"lower": 995.0, "upper": 1005.0, "level": 1000.0}],
            "resistance_levels": [],
        }

        judgement = _judgement(analysis)

        self.assertEqual(judgement["category"], "invalidation")
        self.assertEqual(judgement["rule_id"], "PRICE_SUPPORT_BREAKDOWN")
        self.assertTrue(judgement["invalidation_conditions"][0]["met"])

    def test_close_testing_the_zone_does_not_trigger_invalidation(self) -> None:
        analysis = {
            "latest_bar": {"close": 1002.0},
            "change": 5.0,
            "moving_averages": {
                "ma20": {"value": 950.0, "slope": 5.0},
                "ma60": {"value": 900.0}, "ma120": {"value": 850.0},
            },
            "ma_alignment": "bullish",
            "support_levels": [{"lower": 995.0, "upper": 1005.0, "level": 1000.0}],
            "resistance_levels": [],
        }

        judgement = _judgement(analysis)

        self.assertEqual(judgement["category"], "confirmed_trend")
        self.assertFalse(judgement["invalidation_conditions"][0]["met"])


class TwSupportZoneArticleTest(unittest.TestCase):
    """Golden-fixture coverage for the real 2026-07-16 report the operator flagged:
    close 42,671.27 inside support zone 42,353-42,990 must read as a support test,
    not a confirmed breakdown."""

    def test_real_fixture_close_inside_zone_reads_as_testing_not_broken(self) -> None:
        article = compose_tw_market_analysis_article(_testing_zone_snapshot())
        price_action = "\n".join(article["price_action_paragraphs"])

        self.assertNotIn("原支撐失效", price_action)
        self.assertNotIn("收盤已跌破 42,353～42,990", price_action)
        self.assertNotIn("原支撐失效", article["core_judgement"]["summary"])
        self.assertIn("支撐正在接受測試", price_action)
        self.assertIn("42,353", price_action)

    def test_testing_zone_confirmation_references_lower_boundary_as_future_condition(self) -> None:
        article = compose_tw_market_analysis_article(_testing_zone_snapshot())

        self.assertIn("42,353", article["confirmation_paragraph"])
        self.assertIn("正式失效", article["confirmation_paragraph"])
        self.assertNotIn("原支撐失效", article["confirmation_paragraph"])

    def test_broken_zone_close_below_lower_boundary_reports_current_invalidation(self) -> None:
        broken = _testing_zone_snapshot(close_override=42200.0, low_override=42150.0)

        article = compose_tw_market_analysis_article(broken)
        price_action = "\n".join(article["price_action_paragraphs"])

        self.assertIn("跌破 42,353", price_action)
        self.assertIn("原支撐區正式失效", price_action)
        self.assertIn("原支撐失效", article["core_judgement"]["summary"])

    def test_broken_zone_confirmation_does_not_repeat_break_as_untriggered_condition(self) -> None:
        broken = _testing_zone_snapshot(close_override=42200.0, low_override=42150.0)

        article = compose_tw_market_analysis_article(broken)

        self.assertNotIn("若收盤跌破 42,353～42,990 點，代表本次低檔承接失敗", article["confirmation_paragraph"])
        self.assertIn("重新站回", article["confirmation_paragraph"])

    def test_above_zone_does_not_claim_a_current_break(self) -> None:
        above = _testing_zone_snapshot(close_override=44737.95, low_override=43654.04)

        article = compose_tw_market_analysis_article(above)

        self.assertNotIn("原支撐失效", article["core_judgement"]["summary"])
        self.assertNotIn("原支撐失效", "\n".join(article["price_action_paragraphs"]))


if __name__ == "__main__":
    unittest.main()

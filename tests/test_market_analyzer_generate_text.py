# -*- coding: utf-8 -*-
"""Tests for Analyzer.generate_text() and the market_analyzer bypass fix.

Covers:
- generate_text() returns the LLM response on success
- generate_text() returns None and logs on failure (no exception propagated)
- market_analyzer calls generate_text(), not private analyzer attributes
- Any provider configuration (Gemini / Anthropic / OpenAI / LLM_CHANNELS)
  does NOT trigger AttributeError (regression guard for the old bypass bug)
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Stub heavy dependencies before project imports
for _mod in ("litellm", "google.generativeai", "google.genai", "anthropic"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from unittest.mock import PropertyMock

_OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES = [
    # Repro case 1 (Issue #1279): OpenAI-compatible provider message.content is None while text is in content_blocks.
    (
        "openai/cpa-compatible",
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "content_blocks": [
                            {"type": "text", "text": "block "},
                            {"type": "text", "text": "response"},
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        },
        "block response",
    ),
    # Repro case 2: OpenAI-compatible provider returns message.content as list-of-blocks.
    (
        "openai/list-content-provider",
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "list "},
                            {"type": "text", "text": "response"},
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        },
        "list response",
    ),
]


# ---------------------------------------------------------------------------
# Analyzer.generate_text()
# ---------------------------------------------------------------------------

class TestAnalyzerGenerateText:
    def _make_analyzer(self):
        """Return a minimally configured GeminiAnalyzer with _call_litellm mocked."""
        with patch("src.analyzer.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.litellm_model = "gemini/gemini-2.0-flash"
            cfg.litellm_fallback_models = []
            cfg.gemini_api_keys = ["sk-gemini-testkey-1234"]
            cfg.anthropic_api_keys = []
            cfg.openai_api_keys = []
            cfg.deepseek_api_keys = []
            cfg.llm_model_list = []
            cfg.openai_base_url = None
            mock_cfg.return_value = cfg
            from src.analyzer import GeminiAnalyzer
            analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
            analyzer._router = None
            return analyzer

    def test_generate_text_returns_llm_response(self):
        analyzer = self._make_analyzer()
        with patch.object(analyzer, "_call_litellm", return_value="市場分析報告") as mock_call:
            result = analyzer.generate_text("寫一份覆盤", max_tokens=1024, temperature=0.5)
            assert result == "市場分析報告"
            mock_call.assert_called_once_with(
                "寫一份覆盤",
                generation_config={"max_tokens": 1024, "temperature": 0.5},
            )

    def test_generate_text_returns_none_on_failure(self):
        analyzer = self._make_analyzer()
        with patch.object(analyzer, "_call_litellm", side_effect=Exception("LLM error")):
            result = analyzer.generate_text("prompt")
            assert result is None  # must not raise

    def test_generate_text_default_params(self):
        analyzer = self._make_analyzer()
        with patch.object(analyzer, "_call_litellm", return_value="ok") as mock_call:
            analyzer.generate_text("hello")
            _, kwargs = mock_call.call_args
            gen_cfg = kwargs["generation_config"]
            assert gen_cfg["max_tokens"] == 2048
            assert gen_cfg["temperature"] == 0.7

    def test_call_litellm_stream_aggregates_chunks_and_reports_progress(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="gemini/gemini-2.0-flash",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="abc"))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="def"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            )

        progress_updates = []

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()):
            text, model, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
                stream_progress_callback=progress_updates.append,
            )

        assert text == "abcdef"
        assert model == "gemini/gemini-2.0-flash"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
        assert progress_updates == [3, 6]

    def test_call_litellm_legacy_path_uses_legacy_model_list_for_param_recovery(self):
        with patch("src.analyzer.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.litellm_model = "openai/gpt-4o-mini"
            cfg.litellm_fallback_models = []
            cfg.gemini_api_keys = []
            cfg.anthropic_api_keys = []
            cfg.deepseek_api_keys = []
            cfg.openai_api_keys = ["sk-openai-legacy-a", "sk-openai-legacy-b"]
            cfg.openai_base_url = None
            cfg.llm_model_list = [
                {
                    "model_name": "__legacy_openai__",
                    "litellm_params": {
                        "model": "__legacy_openai__",
                        "api_key": "sk-openai-legacy-a",
                        "api_base": "https://legacy-a.example/v1",
                        "extra_headers": {"x-tenant": "legacy-a"},
                    },
                },
                {
                    "model_name": "__legacy_openai__",
                    "litellm_params": {
                        "model": "__legacy_openai__",
                        "api_key": "sk-openai-legacy-b",
                        "api_base": "https://legacy-b.example/v1",
                        "extra_headers": {"x-tenant": "legacy-b"},
                    },
                },
            ]
            cfg.llm_temperature = 0.7
            mock_cfg.return_value = cfg

            from src.analyzer import GeminiAnalyzer

            analyzer = GeminiAnalyzer()
            analyzer._config_override = cfg

        captured = {}

        def _fake_call_litellm_with_param_recovery(call, **kwargs):
            captured["model_list"] = kwargs.get("model_list")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=None,
            )

        with patch("src.analyzer.call_litellm_with_param_recovery", side_effect=_fake_call_litellm_with_param_recovery):
            text, _, _ = analyzer._call_litellm("迴歸用例", {"max_tokens": 128, "temperature": 0.7})

        assert text == "ok"
        passed_model_list = captured.get("model_list")
        assert passed_model_list is not None
        assert len(passed_model_list) == 2
        assert all(item["litellm_params"].get("model") == "openai/gpt-4o-mini" for item in passed_model_list)
        assert [item["litellm_params"]["api_base"] for item in passed_model_list] == [
            "https://legacy-a.example/v1",
            "https://legacy-b.example/v1",
        ]
        assert [item["litellm_params"]["extra_headers"] for item in passed_model_list] == [
            {"x-tenant": "legacy-a"},
            {"x-tenant": "legacy-b"},
        ]

    @patch("src.analyzer.Router")
    def test_analyzer_legacy_router_recovery_cache_is_scoped_by_api_base(self, mock_router):
        """Analyzer legacy recovery should not leak across same model different api_base."""
        from src.analyzer import call_litellm_with_param_recovery as real_call
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="analyzer ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
        strict_router = MagicMock()
        flex_router = MagicMock()
        strict_router.completion.side_effect = [
            RuntimeError("Unsupported parameter: temperature is not supported"),
            response,
        ]
        flex_router.completion.return_value = response
        mock_router.side_effect = [strict_router, flex_router]

        strict_cfg = SimpleNamespace(
            litellm_model="openai/shared-model",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-strict-key-1", "sk-strict-key-2"],
            deepseek_api_keys=[],
            openai_base_url="https://strict.example/v1",
        )
        flex_cfg = SimpleNamespace(
            litellm_model="openai/shared-model",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-flex-key-1", "sk-flex-key-2"],
            deepseek_api_keys=[],
            openai_base_url="https://flex.example/v1",
        )

        captured_model_lists = []

        def _fake_recovery(call, **kwargs):
            captured_model_lists.append(kwargs.get("model_list"))
            return real_call(call, **kwargs)

        import src.analyzer as analyzer_module
        from src.analyzer import GeminiAnalyzer

        with patch.object(analyzer_module, "call_litellm_with_param_recovery", side_effect=_fake_recovery):
            GeminiAnalyzer(config=strict_cfg)._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )
            GeminiAnalyzer(config=flex_cfg)._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert len(captured_model_lists) == 2
        strict_model_list = captured_model_lists[0]
        flex_model_list = captured_model_lists[1]
        assert strict_model_list is not None
        assert flex_model_list is not None
        assert all(
            item.get("litellm_params", {}).get("api_base") == "https://strict.example/v1"
            for item in strict_model_list
        )
        assert all(
            item.get("litellm_params", {}).get("api_base") == "https://flex.example/v1"
            for item in flex_model_list
        )
        assert strict_router.completion.call_args_list[0].kwargs["temperature"] == 0.2
        assert "temperature" not in strict_router.completion.call_args_list[1].kwargs
        assert flex_router.completion.call_args.kwargs["temperature"] == 0.2

    def test_call_litellm_stream_falls_back_to_non_stream_before_first_chunk(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="gemini/gemini-2.0-flash",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        def broken_stream():
            raise RuntimeError("stream unsupported")
            yield  # pragma: no cover

        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="full response"))],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5, total_tokens=9),
        )

        dispatch_calls = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            dispatch_calls.append(call_kwargs.copy())
            if call_kwargs.get("stream"):
                return broken_stream()
            return response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "full response"
        assert model == "gemini/gemini-2.0-flash"
        assert usage == {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}
        assert len(dispatch_calls) == 2
        assert dispatch_calls[0]["stream"] is True
        assert "stream" not in dispatch_calls[1]

    @pytest.mark.parametrize(
        "provider_model,response_payload,expected_text",
        _OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES,
        ids=["issue1279-message-content-null", "issue1279-message-content-list"],
    )
    def test_call_litellm_extracts_external_provider_text_shapes(self, provider_model, response_payload, expected_text):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model=provider_model,
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response_payload):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == expected_text
        assert model_used == provider_model
        assert usage == response_payload["usage"]

    def test_call_litellm_falls_back_to_message_content_when_blocks_empty(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/deepseek-chat",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=[],
                    message=SimpleNamespace(content="message response"),
                )
            ],
            usage=None,
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "message response"
        assert model_used == "openai/deepseek-chat"
        assert usage == {}

    def test_call_litellm_normalizes_kimi_k26_temperature(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/kimi-k2.6",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "openai/kimi-k2.6"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        call_kwargs = mock_dispatch.call_args.args[1]
        assert call_kwargs["temperature"] == 1.0

    def test_call_litellm_normalizes_kimi_k26_temperature_for_yaml_alias(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="kimi_router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "kimi_router",
                    "litellm_params": {"model": "openai/kimi-k2.6"},
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "kimi_router"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        call_kwargs = mock_dispatch.call_args.args[1]
        assert call_kwargs["temperature"] == 1.0

    def test_call_litellm_normalizes_kimi_k26_temperature_for_non_thinking_yaml_alias(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="kimi_router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "kimi_router",
                    "litellm_params": {
                        "model": "openai/kimi-k2.6",
                        "extra_body": {"thinking": {"type": "disabled"}},
                    },
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "kimi_router"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        call_kwargs = mock_dispatch.call_args.args[1]
        assert call_kwargs["temperature"] == 0.6

    def test_call_litellm_omits_temperature_for_gpt5_family(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt5.5-ferr",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "openai/gpt5.5-ferr"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        call_kwargs = mock_dispatch.call_args.args[1]
        assert "temperature" not in call_kwargs

    def test_call_litellm_recovers_from_temperature_default_error(self):
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/custom-default-temp",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        calls = []

        def _dispatch(model, call_kwargs, **_kwargs):
            calls.append(dict(call_kwargs))
            if len(calls) == 1:
                raise RuntimeError(
                    "temperature=0.2 is unsupported. Only the default (1.0) value is supported."
                )
            return response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "openai/custom-default-temp"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        assert calls[0]["temperature"] == 0.2
        assert calls[1]["temperature"] == 1.0

    def test_call_litellm_keeps_user_temperature_for_non_kimi_fallback(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/kimi-k2.6",
            litellm_fallback_models=["openai/gpt-4o-mini"],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="fallback ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        temperatures = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            temperatures.append((model, call_kwargs["temperature"]))
            if model == "openai/kimi-k2.6":
                raise RuntimeError("primary failed")
            return response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "fallback ok"
        assert model_used == "openai/gpt-4o-mini"
        assert usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        assert temperatures == [
            ("openai/kimi-k2.6", 1.0),
            ("openai/gpt-4o-mini", 0.2),
        ]

    def test_call_litellm_stream_falls_back_to_non_stream_after_partial_and_falls_back_model(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="provider/bad-model",
            litellm_fallback_models=["provider/good-model"],
            llm_model_list=[],
        )

        def partial_then_broken_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="abc"))],
                usage=None,
            )
            raise RuntimeError("stream disconnected")

        def good_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="fallback"))],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5, total_tokens=9),
            )

        fallback_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="fallback full"))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=8, total_tokens=15),
        )

        dispatch_calls = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            dispatch_calls.append((model, bool(call_kwargs.get("stream"))))
            if model == "provider/bad-model":
                if call_kwargs.get("stream"):
                    return partial_then_broken_stream()
                raise RuntimeError("non-stream model broken")
            if call_kwargs.get("stream"):
                return good_stream()
            return fallback_response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "fallback"
        assert model_used == "provider/good-model"
        assert usage == {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}
        assert dispatch_calls == [
            ("provider/bad-model", True),
            ("provider/bad-model", False),
            ("provider/good-model", True),
        ]

    def test_analyze_integrity_retry_keeps_progress_monotonic(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            gemini_request_delay=0,
            report_language="zh",
            litellm_model="gemini/gemini-2.0-flash",
            llm_temperature=0.2,
            report_integrity_enabled=True,
            report_integrity_retry=1,
        )

        from src.analyzer import AnalysisResult

        progress_updates = []
        first_result = AnalysisResult(
            code="2330",
            name="台積電",
            sentiment_score=80,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="首輪結果",
        )
        second_result = AnalysisResult(
            code="2330",
            name="台積電",
            sentiment_score=82,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="補全後結果",
        )

        with patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(
                 analyzer,
                 "_call_litellm",
                 side_effect=[
                     ("first response", "model-a", {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}),
                     ("second response", "model-a", {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}),
                 ],
             ), \
             patch.object(analyzer, "_parse_response", side_effect=[first_result, second_result]), \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch.object(
                 analyzer,
                 "_check_content_integrity",
                 side_effect=[(False, ["analysis_summary"]), (True, [])],
             ), \
             patch.object(analyzer, "_build_integrity_retry_prompt", return_value="retry prompt"), \
             patch("src.analyzer.persist_llm_usage"):
            result = analyzer.analyze(
                {"code": "2330", "stock_name": "台積電"},
                progress_callback=lambda progress, message: progress_updates.append((progress, message)),
            )

        assert result.analysis_summary == "補全後結果"
        assert [progress for progress, _ in progress_updates] == [68, 93, 94, 95]
        assert "補全重試" in progress_updates[2][1]
        assert "解析 JSON" in progress_updates[3][1]

    def test_parse_response_non_json_returns_failure(self):
        """_parse_response must return success=False when LLM output is not valid JSON."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(report_language="zh")

        from src.analyzer import GeminiAnalyzer

        result = GeminiAnalyzer._parse_response(analyzer, "這是一段純文字分析，沒有 JSON。", "2330", "台積電")
        assert result.success is False
        assert result.error_message is not None
        assert result.code == "2330"

    def test_parse_response_malformed_json_returns_failure(self):
        """_parse_response must return success=False when JSON extraction fails."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(report_language="zh")

        from src.analyzer import GeminiAnalyzer

        malformed = "Here is the analysis: {broken json content without closing"
        result = GeminiAnalyzer._parse_response(analyzer, malformed, "AAPL", "Apple")
        assert result.success is False
        assert result.error_message is not None

    def test_parse_response_valid_json_returns_success(self):
        """_parse_response must return success=True when LLM output contains valid JSON."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(report_language="zh")

        from src.analyzer import GeminiAnalyzer
        import json

        valid_response = json.dumps({
            "sentiment_score": 75,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "analysis_summary": "測試分析",
        })
        result = GeminiAnalyzer._parse_response(analyzer, valid_response, "2330", "台積電")
        assert result.success is True
        assert result.error_message is None

    def test_json_parse_failure_triggers_fallback_model(self):
        """When the primary model returns non-JSON, _call_litellm must try the fallback model."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_model_list=[],
        )

        import json as _json
        valid_json = _json.dumps({"sentiment_score": 70, "trend_prediction": "看多"})
        dispatch_calls = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            dispatch_calls.append(model)
            if "primary" in model:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="這不是 JSON 格式的響應"))],
                    usage=None,
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=valid_json))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "test prompt",
                {"max_tokens": 128, "temperature": 0.7},
                response_validator=analyzer._validate_json_response,
            )

        assert "primary" in dispatch_calls[0], "primary model should be tried first"
        assert len(dispatch_calls) == 2, "fallback model should be tried after primary JSON failure"
        assert "fallback" in model_used
        assert valid_json == text

    def test_all_models_invalid_json_raises_all_models_failed_error(self):
        """When all models return non-JSON, _AllModelsFailedError is raised with last_response_text."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_model_list=[],
        )

        from src.analyzer import _AllModelsFailedError

        def fake_dispatch(model, call_kwargs, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="這不是 JSON 格式的響應"))],
                usage=None,
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            with pytest.raises(_AllModelsFailedError) as exc_info:
                analyzer._call_litellm(
                    "test prompt",
                    {"max_tokens": 128, "temperature": 0.7},
                    response_validator=analyzer._validate_json_response,
                )

        assert exc_info.value.last_response_text == "這不是 JSON 格式的響應"

    def test_analyze_all_models_invalid_json_goes_through_post_processing(self):
        """When all models return non-JSON, analyze() must still run integrity
        checks, placeholder fill, and persist_llm_usage — no early return.

        With report_integrity_retry=1, the retry loop runs once (re-prompting
        with complement instructions); when that also yields invalid JSON the
        exhausted-retries path fires placeholder fill.
        """
        from src.analyzer import AnalysisResult, _AllModelsFailedError

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            gemini_request_delay=0,
            report_language="zh",
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_temperature=0.7,
            llm_model_list=[],
            report_integrity_enabled=True,
            report_integrity_retry=1,
        )

        # _parse_response on non-JSON text produces a text fallback result
        text_fallback_result = AnalysisResult(
            code="2330",
            name="台積電",
            sentiment_score=50,
            trend_prediction="震盪",
            operation_advice="持有",
            analysis_summary="部分文字摘要",
            success=False,
            error_message="LLM response is not valid JSON; analysis result will not be persisted",
        )

        all_models_error = _AllModelsFailedError(
            "all failed",
            last_response_text="這不是 JSON，而是純文字分析結果",
            last_model="provider/fallback-model",
            last_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        with patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(
                 analyzer,
                 "_call_litellm",
                 side_effect=all_models_error,
             ) as mock_call, \
             patch.object(analyzer, "_parse_response", return_value=text_fallback_result) as mock_parse, \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch.object(analyzer, "_check_content_integrity", return_value=(False, ["dashboard.core_conclusion.one_sentence"])), \
             patch.object(analyzer, "_build_integrity_retry_prompt", return_value="retry prompt"), \
             patch.object(analyzer, "_apply_placeholder_fill") as mock_fill, \
             patch("src.analyzer.persist_llm_usage") as mock_usage:

            result = analyzer.analyze(
                {"code": "2330", "stock_name": "台積電"},
                news_context="some news",
            )

        # _call_litellm called twice: initial + 1 retry
        assert mock_call.call_count == 2

        # _parse_response called twice (initial + retry)
        assert mock_parse.call_count == 2
        mock_parse.assert_called_with("這不是 JSON，而是純文字分析結果", "2330", "台積電")

        # Placeholder fill was applied after retry exhaustion
        mock_fill.assert_called_once()
        assert "dashboard.core_conclusion.one_sentence" in mock_fill.call_args[0][1]

        # persist_llm_usage was called with the last model and usage
        mock_usage.assert_called_once()
        usage_args = mock_usage.call_args
        assert usage_args[0][0] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        assert usage_args[0][1] == "provider/fallback-model"
        assert usage_args[1]["call_type"] == "analysis"
        assert usage_args[1]["stock_code"] == "2330"

        # Result is success=False (text fallback), but all fields exist
        assert result.success is False
        assert result.code == "2330"
        assert result.search_performed is True


# ---------------------------------------------------------------------------
# market_analyzer uses generate_text(), not private attributes
# ---------------------------------------------------------------------------

class TestMarketAnalyzerBypassFix:
    def _make_market_analyzer_with_mock_generate_text(self, return_value="覆盤報告"):
        """Return a MarketAnalyzer whose embedded Analyzer.generate_text is mocked."""
        from src.core.market_profile import TW_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint

        with patch("src.analyzer.get_config") as mock_cfg, \
             patch("src.market_analyzer.get_config") as mock_cfg2:
            cfg = MagicMock()
            cfg.litellm_model = "gemini/gemini-2.0-flash"
            cfg.litellm_fallback_models = []
            cfg.gemini_api_keys = ["sk-gemini-testkey-1234"]
            cfg.anthropic_api_keys = []
            cfg.openai_api_keys = []
            cfg.deepseek_api_keys = []
            cfg.llm_model_list = []
            cfg.openai_base_url = None
            cfg.market_review_region = "tw"
            cfg.market_review_color_scheme = "green_up"
            cfg.report_language = "zh"
            mock_cfg.return_value = cfg
            mock_cfg2.return_value = cfg

            from src.analyzer import GeminiAnalyzer
            from src.market_analyzer import MarketAnalyzer

            analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
            analyzer._router = None
            analyzer._litellm_available = True
            analyzer.generate_text = MagicMock(return_value=return_value)

            ma = MarketAnalyzer.__new__(MarketAnalyzer)
            ma.analyzer = analyzer
            ma.config = cfg
            ma.profile = TW_PROFILE
            ma.strategy = get_market_strategy_blueprint("tw")
            ma.region = "tw"
            return ma

    def test_no_access_to_private_model_attribute(self):
        """generate_text() must be called; _model must never be accessed."""
        ma = self._make_market_analyzer_with_mock_generate_text("覆盤結果")
        # Ensure _model attribute does not exist (simulates PR #494 state)
        assert not hasattr(ma.analyzer, "_model") or ma.analyzer._model is None, (
            "_model should not be set on the LiteLLM-based analyzer"
        )
        # generate_text is a MagicMock, so calling it won't crash
        result = ma.analyzer.generate_text("prompt")
        assert isinstance(result, str) and len(result) > 0
        ma.analyzer.generate_text.assert_called_once()

    def test_generate_text_none_falls_back_to_template(self):
        """generate_market_review() falls back to template when generate_text returns None."""
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上證指數",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )
        result = ma.generate_market_review(overview, [])
        assert isinstance(result, str) and len(result) > 0
        ma.analyzer.generate_text.assert_called_once()

    def test_market_review_uses_8192_max_tokens(self):
        """generate_market_review() should request a larger output budget to avoid truncation."""
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="覆盤結果")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上證指數",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )

        result = ma.generate_market_review(overview, [])

        assert isinstance(result, str) and len(result) > 0
        ma.analyzer.generate_text.assert_called_once()
        _, kwargs = ma.analyzer.generate_text.call_args
        assert kwargs["max_tokens"] == 8192
        assert kwargs["temperature"] == 0.7

    def test_generate_template_review_uses_english_shell_for_tw_when_report_language_is_en(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="TAIEX",
                    name="TAIEX",
                    current=3300.0,
                    change=12.0,
                    change_pct=0.36,
                )
            ],
            up_count=3200,
            down_count=1800,
            limit_up_count=88,
            limit_down_count=5,
            total_amount=14567.0,
            top_sectors=[{"name": "AI算力", "change_pct": 3.25}],
            bottom_sectors=[{"name": "煤炭", "change_pct": -1.12}],
        )

        result = ma.generate_market_review(overview, [])

        assert "Taiwan Market Recap" in result
        assert "### 1. Market Summary" in result
        assert "Today's Taiwan market" in result
        assert "CNY 100m" not in result
        assert "A-share" not in result
        assert "### 一、市場總結" not in result

    def test_generate_template_review_keeps_chinese_shell_for_us_when_report_language_is_default(self):
        from src.core.market_profile import US_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.region = "us"
        ma.profile = US_PROFILE
        ma.strategy = get_market_strategy_blueprint("us")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="SPX",
                    name="標普500",
                    current=5200.0,
                    change=-18.0,
                    change_pct=-0.35,
                )
            ],
        )

        result = ma.generate_market_review(overview, [])

        assert "## 2026-03-05 大盤覆盤" in result
        assert "### 一、盤面總覽" in result
        assert "今日美股市場整體呈現**小幅下跌**態勢" in result
        assert "### 1. Market Summary" not in result
        assert "US Market Recap" not in result

    def test_inject_data_into_review_matches_english_headings(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="TAIEX",
                    name="TAIEX",
                    current=3300.0,
                    change=12.0,
                    change_pct=0.36,
                    amount=145000000000.0,
                )
            ],
            up_count=3200,
            down_count=1800,
            flat_count=100,
            limit_up_count=88,
            limit_down_count=5,
            total_amount=14567.0,
            top_sectors=[{"name": "半導體", "change_pct": 3.25}],
            bottom_sectors=[{"name": "金融", "change_pct": -1.12}],
        )
        review = """## 2026-03-05 Taiwan Market Recap

### 1. Market Summary
Summary text.

### 2. Index Commentary
Index text.

### 4. Sector Highlights
Sector text.
"""

        result = ma._inject_data_into_review(review, overview)

        assert "- **Market Signal**: 51/100 (mixed, balanced)" in result
        assert "- **Breadth**: Advancers 3200 / Decliners 1800 / Flat 100;" in result
        assert "Turnover 14567 (TWD bn)" in result
        assert "| Index | Last | Change % | Open | High | Low | Amplitude | Turnover (TWD bn) |" in result
        assert "#### Leading Sectors" in result
        assert "| 1 | 半導體 | +3.25% |" in result
        assert "#### Lagging Sectors" in result
        assert "| 1 | 金融 | -1.12% |" in result

    def test_inject_data_into_review_matches_reference_style_chinese_headings(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="TAIEX",
                    name="加權指數",
                    current=3300.0,
                    change=12.0,
                    change_pct=0.36,
                    open=3288.0,
                    high=3312.0,
                    low=3276.0,
                    amount=145000000000.0,
                    amplitude=1.1,
                )
            ],
            up_count=3200,
            down_count=1800,
            flat_count=100,
            limit_up_count=88,
            limit_down_count=5,
            total_amount=14567.0,
            top_sectors=[{"name": "半導體", "change_pct": 3.25}],
            bottom_sectors=[{"name": "金融", "change_pct": -1.12}],
        )
        news = [{"title": "半導體族群走強", "snippet": "AI 供應鏈延續活躍，成交額放大"}]
        review = """## 2026-03-05 大盤覆盤

### 一、盤面總覽
總結。

### 二、指數結構
指數。

### 三、板塊主線
板塊。

### 五、訊息催化
新聞。
"""

        result = ma._inject_data_into_review(review, overview, news)

        assert "盤面訊號" in result
        assert "51/100（震盪，需觀察）" in result
        assert "綠燈（可進攻）" not in result
        assert "大盤紅綠燈" not in result
        assert "green（可進攻）" not in result
        assert "訊號依據" in result
        signal_line = next(line for line in result.splitlines() if "**盤面訊號**" in line)
        drivers_line = next(line for line in result.splitlines() if "**訊號依據**" in line)
        assert signal_line.startswith("- ")
        assert "51/100" in signal_line
        assert "█" not in result
        assert "░" not in result
        assert "盤面溫度" not in drivers_line
        assert "操作建議" in result
        assert "盤面溫度" not in result
        assert "| 上漲/下跌/平盤 | 3200 / 1800 / 100 |" in result
        assert "| 指數 | 最新 | 漲跌幅 | 開盤 | 最高 | 最低 | 振幅 | 成交額(億) |" in result
        assert "| 加權指數 | 3300.00 | 🟢 +0.36% | 3288.00 | 3312.00 | 3276.00 | 1.10% | 145.00 |" in result
        assert "#### 領漲板塊 Top 5" in result
        assert "| 1 | 半導體 | +3.25% |" in result
        assert "#### 近三日市場線索" in result
        assert "半導體族群走強" in result
        assert "供應鏈延續活躍" not in result

    def test_news_block_renders_title_source_and_link_only(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.config = SimpleNamespace(report_language="zh")
        ma.region = "tw"
        long_snippet = (
            "覆盤必讀 2026-05-06 覆盤的意義在於更清晰地把握市場脈搏，"
            "綜合描述 A 股三大指數今日集體反彈，成交額放大，科技成長方向領漲。"
        )

        result = ma._build_news_block([
            {
                "title": "台股收評：科創50指數放量反彈漲5.47% 兩市成交額重回3萬億元",
                "snippet": long_snippet,
                "source": "東方財富",
                "published_date": "2026-05-06",
                "url": "https://example.com/news/1",
            }
        ])

        assert "#### 近三日市場線索" in result
        assert "| 序號 |" not in result
        assert "摘要/線索片段" not in result
        assert "關注點" not in result
        assert "成交額放大" not in result
        assert (
            "- 1. [台股收評：科創50指數放量反彈漲5.47% 兩市成交額重回3萬億元]"
            "(https://example.com/news/1)（東方財富 / 2026-05-06）"
        ) in result

    def test_news_block_uses_dash_when_source_metadata_missing(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.config = SimpleNamespace(report_language="zh")
        ma.region = "tw"

        result = ma._build_news_block([
            {
                "title": "政策利好帶動板塊活躍",
                "snippet": "相關主題成交放大",
            }
        ])

        assert "- 1. 政策利好帶動板塊活躍" in result
        assert "相關主題成交放大" not in result
        assert "| 1 | 政策利好帶動板塊活躍 |" not in result

    def test_news_block_uses_english_metadata_punctuation(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.config = SimpleNamespace(report_language="en")
        ma.region = "us"

        result = ma._build_news_block([
            {
                "title": "Chip stocks rally as AI demand improves",
                "source": "Reuters",
                "published_date": "2026-05-06",
                "url": "https://example.com/news/2",
            }
        ])

        assert "#### News Catalysts" in result
        assert (
            "- 1. [Chip stocks rally as AI demand improves](https://example.com/news/2)"
            " (Reuters / 2026-05-06)"
        ) in result
        assert "（Reuters" not in result

    def test_review_prompt_caps_news_url_context(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        long_url = "https://example.com/redirect?" + "utm_campaign=" + ("x" * 420)

        prompt = ma._build_review_prompt(
            MarketOverview(date="2026-05-06"),
            [
                {
                    "title": "台股收評：指數放量反彈",
                    "snippet": "科技成長方向領漲",
                    "source": "測試來源",
                    "published_date": "2026-05-06",
                    "url": long_url,
                }
            ],
        )

        assert long_url not in prompt
        assert "URL: https://example.com/redirect?" in prompt
        assert ("x" * 220) not in prompt

    def test_market_light_snapshot_marks_defensive_market_red(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        overview = MarketOverview(
            date="2026-03-06",
            indices=[
                MarketIndex(code="TAIEX", name="加權指數", current=3200, change_pct=-4.8),
                MarketIndex(code="TPEx", name="櫃買指數", current=250, change_pct=-4.4),
            ],
            up_count=100,
            down_count=4900,
            limit_up_count=0,
            limit_down_count=100,
            total_amount=9800.0,
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["status"] == "red"
        assert snapshot["label"] == "偏防守"
        assert snapshot["score"] < 40
        assert snapshot["region"] == "tw"
        assert snapshot["trade_date"] == "2026-03-06"
        assert snapshot["data_quality"] == "partial"
        assert snapshot["dimensions"]["breadth"]["available"] is False
        assert snapshot["dimensions"]["index"]["available"] is True
        assert snapshot["dimensions"]["limit"]["available"] is False
        assert any("虧錢效應" in reason for reason in snapshot["reasons"])

    def test_market_light_snapshot_uses_english_labels_and_reasons(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-06",
            indices=[
                MarketIndex(code="TAIEX", name="TAIEX", current=3200, change_pct=-4.8),
                MarketIndex(code="TPEx", name="TPEx", current=250, change_pct=-4.4),
            ],
            up_count=100,
            down_count=4900,
            limit_up_count=0,
            limit_down_count=100,
            total_amount=9800.0,
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["status"] == "red"
        assert snapshot["label"] == "risk-off"
        assert snapshot["guidance"] == (
            "Risk is elevated; prioritize drawdown control and avoid chasing weak rebounds."
        )
        assert not any(reason.startswith("market temperature ") for reason in snapshot["reasons"])
        assert any(
            reason.startswith("advancers ratio ") and "downside pressure dominates" in reason
            for reason in snapshot["reasons"]
        )

    def test_market_light_snapshot_marks_us_without_breadth_as_partial(self):
        from src.core.market_profile import US_PROFILE
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.region = "us"
        ma.profile = US_PROFILE
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-06",
            indices=[MarketIndex(code="SPX", name="S&P 500", current=5000, change_pct=0.5)],
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["region"] == "us"
        assert snapshot["data_quality"] == "partial"
        assert snapshot["dimensions"]["breadth"] == {"score": 50, "available": False}
        assert snapshot["dimensions"]["index"]["available"] is True
        assert snapshot["dimensions"]["limit"] == {"score": 50, "available": False}

    def test_us_english_indices_do_not_label_turnover_as_cny(self):
        from src.core.market_profile import US_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.config.report_language = "en"
        ma.region = "us"
        ma.profile = US_PROFILE
        ma.strategy = get_market_strategy_blueprint("us")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="SPX",
                    name="S&P 500",
                    current=5200.0,
                    change=35.0,
                    change_pct=0.68,
                    amount=9876543210.0,
                )
            ],
        )

        result = ma._build_indices_block(overview)

        assert "CNY 100m" not in result
        assert "Turnover (USD bn)" in result
        assert "| S&P 500 | 5200.00 |" in result

    def test_indices_block_uses_configured_red_up_color_scheme(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.config.market_review_color_scheme = "red_up"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(code="000001", name="上證指數", current=3200.0, change_pct=0.68),
                MarketIndex(code="399001", name="深證成指", current=9800.0, change_pct=-0.42),
                MarketIndex(code="399006", name="創業板指", current=2100.0, change_pct=0.0),
            ],
        )

        result = ma._build_indices_block(overview)

        assert "| 上證指數 | 3200.00 | 🔴 +0.68% |" in result
        assert "| 深證成指 | 9800.00 | 🟢 -0.42% |" in result
        assert "| 創業板指 | 2100.00 | ⚪ +0.00% |" in result

    def test_indices_block_keeps_green_up_default_color_scheme(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(code="000001", name="上證指數", current=3200.0, change_pct=0.68),
                MarketIndex(code="399001", name="深證成指", current=9800.0, change_pct=-0.42),
            ],
        )

        result = ma._build_indices_block(overview)

        assert "| 上證指數 | 3200.00 | 🟢 +0.68% |" in result
        assert "| 深證成指 | 9800.00 | 🔴 -0.42% |" in result

    def test_no_private_attribute_access_in_market_analyzer_source(self):
        """Static guard: market_analyzer.py must not access private analyzer attrs."""
        import ast
        import pathlib

        src = pathlib.Path("src/market_analyzer.py").read_text()
        tree = ast.parse(src)
        forbidden = {
            "_model", "_router", "_use_openai", "_use_anthropic",  # historical
            "_call_litellm",      # use generate_text() instead
            "_litellm_available", # use is_available() instead
        }

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden:
                    violations.append(node.attr)

        assert violations == [], (
            f"market_analyzer.py still accesses private Analyzer attributes: {violations}"
        )

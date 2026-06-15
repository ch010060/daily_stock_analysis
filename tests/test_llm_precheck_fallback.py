# -*- coding: utf-8 -*-
"""Fixture tests for LLM pre-check & fallback mechanism.

Validates that when a local LLM server (e.g. LM Studio) is unreachable:
1. _filter_reachable_model_list removes it from the active list
2. _init_litellm stores only cloud models in _active_model_list
3. _call_litellm's models_to_try is built from _active_model_list (not config.litellm_model)
4. The Router dispatches to the cloud fallback model, not the offline local model

These tests do not depend on a running container or web task polling.
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Stub heavy optional dependencies and any src.* sub-modules that pull in
# heavy system packages (sqlalchemy, fastapi, etc.) not installed locally.
_STUB_MODS = (
    # Third-party LLM / AI libraries
    "litellm",
    "json_repair",
    "google.generativeai",
    "google.genai",
    "anthropic",
    "openai",
    "tiktoken",
    # HTTP / data libraries
    "httpx",
    "aiohttp",
    "tenacity",
    # Data-provider libraries
    "FinMind",
    "FinMind.data",
    "akshare",
    "tushare",
    "alphasift",
    "alphasift.dsa_adapter",
    # DB / ORM (sqlalchemy pulled in by src.storage)
    "sqlalchemy",
    "sqlalchemy.exc",
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    # src.* modules with heavy transitive deps
    "src.storage",
    "src.config",
    "src.report_language",
    "src.schemas",
    "src.schemas.report_schema",
    "src.schemas.market_light",
    "src.schemas.analysis_context_pack",
    "src.market_context",
    "src.market_phase_prompt",
    "src.data",
    "src.data.stock_mapping",
    "src.data.stock_index_loader",
    "src.llm",
    "src.llm.generation_params",
    "src.llm.errors",
    "src.agent",
    "src.agent.events",
    "src.agent.llm_adapter",
    "src.agent.skills",
    "src.agent.skills.defaults",
    "src.notification",
    "src.search_service",
    "strategies",
)
for _mod in _STUB_MODS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Patch specific callables that analyzer.py calls at import time or during init
sys.modules["json_repair"].repair_json = MagicMock(side_effect=lambda s, **k: s)
sys.modules["src.storage"].persist_llm_usage = MagicMock()
sys.modules["src.data.stock_mapping"].STOCK_NAME_MAP = {}
sys.modules["src.agent.skills.defaults"].CORE_TRADING_SKILL_POLICY_ZH = ""
# Provide a real get_config that returns a sensible default config object
_default_cfg = MagicMock()
_default_cfg.litellm_model = "openai/qwen/qwen3.6-35b-a3b"
_default_cfg.litellm_fallback_models = []
_default_cfg.llm_model_list = []
_default_cfg.llm_temperature = 0.7
_default_cfg.report_integrity_enabled = False
_default_cfg.report_integrity_retry = 0
sys.modules["src.config"].get_config = MagicMock(return_value=_default_cfg)
sys.modules["src.config"].AppConfig = MagicMock
# Provide stubs for functions imported at module level in analyzer.py
sys.modules["src.llm.generation_params"].apply_litellm_generation_params = MagicMock(
    side_effect=lambda kw, *a, **k: kw
)
sys.modules["src.llm.errors"].call_litellm_with_param_recovery = MagicMock(
    side_effect=lambda fn, model, call_kwargs, **k: fn(call_kwargs)
)
sys.modules["src.report_language"].get_report_language = MagicMock(return_value="zh_TW")
sys.modules["src.report_language"].localize_trend_prediction = MagicMock(side_effect=lambda x, lang=None, **k: x)
sys.modules["src.market_context"].get_market_role = MagicMock(return_value="TW")
sys.modules["src.market_context"].get_market_guidelines = MagicMock(return_value="")

import pytest
from unittest.mock import call

# ---------------------------------------------------------------------------
# Helpers to build minimal channel model_list entries
# ---------------------------------------------------------------------------

def _lmstudio_entry(model_name="openai/qwen/qwen3.6-35b-a3b"):
    return {
        "model_name": model_name,
        "litellm_params": {
            "model": model_name,
            "api_base": "http://192.168.1.9:12345/v1",
            "api_key": "lm-studio",
        },
    }


def _openai_entry(model_name="openai/gpt-4o"):
    return {
        "model_name": model_name,
        "litellm_params": {
            "model": model_name,
            "api_base": "https://api.openai.com/v1",
            "api_key": "sk-test",
        },
    }


def _openai_mini_entry(model_name="openai/gpt-4o-mini"):
    return {
        "model_name": model_name,
        "litellm_params": {
            "model": model_name,
            "api_base": "https://api.openai.com/v1",
            "api_key": "sk-test",
        },
    }


# ---------------------------------------------------------------------------
# Minimal Analyzer stub — only the pre-check methods under test
# ---------------------------------------------------------------------------

def _make_analyzer():
    """Return an Analyzer instance with heavy init bypassed."""
    from src.analyzer import GeminiAnalyzer as Analyzer  # noqa: PLC0415
    obj = object.__new__(Analyzer)
    # Enough to prevent AttributeError in the methods we call
    obj._router = None
    obj._litellm_available = False
    return obj


# ---------------------------------------------------------------------------
# Tests: _is_local_api_base
# ---------------------------------------------------------------------------

class TestIsLocalApiBase:
    def setup_method(self):
        self.analyzer = _make_analyzer()

    def test_localhost(self):
        assert self.analyzer._is_local_api_base("http://localhost:1234/v1") is True

    def test_127(self):
        assert self.analyzer._is_local_api_base("http://127.0.0.1:8080/v1") is True

    def test_private_192(self):
        assert self.analyzer._is_local_api_base("http://192.168.1.9:12345/v1") is True

    def test_private_10(self):
        assert self.analyzer._is_local_api_base("http://10.0.0.5:8080/v1") is True

    def test_public_openai(self):
        assert self.analyzer._is_local_api_base("https://api.openai.com/v1") is False

    def test_none(self):
        assert self.analyzer._is_local_api_base(None) is False

    def test_empty(self):
        assert self.analyzer._is_local_api_base("") is False


# ---------------------------------------------------------------------------
# Tests: _filter_reachable_model_list
# ---------------------------------------------------------------------------

class TestFilterReachableModelList:
    def setup_method(self):
        self.analyzer = _make_analyzer()

    def test_local_offline_removed(self):
        model_list = [_lmstudio_entry(), _openai_entry(), _openai_mini_entry()]
        with patch.object(self.analyzer, "_probe_api_base_reachable", return_value=False):
            result = self.analyzer._filter_reachable_model_list(model_list)
        names = [e["model_name"] for e in result]
        assert "openai/qwen/qwen3.6-35b-a3b" not in names
        assert "openai/gpt-4o" in names
        assert "openai/gpt-4o-mini" in names

    def test_local_online_kept(self):
        model_list = [_lmstudio_entry(), _openai_entry()]
        with patch.object(self.analyzer, "_probe_api_base_reachable", return_value=True):
            result = self.analyzer._filter_reachable_model_list(model_list)
        names = [e["model_name"] for e in result]
        assert "openai/qwen/qwen3.6-35b-a3b" in names
        assert "openai/gpt-4o" in names

    def test_only_local_all_offline_returns_empty(self):
        model_list = [_lmstudio_entry()]
        with patch.object(self.analyzer, "_probe_api_base_reachable", return_value=False):
            result = self.analyzer._filter_reachable_model_list(model_list)
        assert result == []

    def test_probe_called_once_per_unique_base(self):
        """Same base URL should only be probed once even with multiple models."""
        entry1 = _lmstudio_entry("openai/qwen/model-a")
        entry2 = _lmstudio_entry("openai/qwen/model-b")  # same api_base
        model_list = [entry1, entry2, _openai_entry()]
        with patch.object(self.analyzer, "_probe_api_base_reachable", return_value=False) as mock_probe:
            self.analyzer._filter_reachable_model_list(model_list)
        # probe should be called exactly once for the shared lmstudio base
        lmstudio_calls = [c for c in mock_probe.call_args_list
                          if "192.168.1.9" in str(c)]
        assert len(lmstudio_calls) == 1

    def test_cloud_models_never_probed(self):
        """Public URLs must never be probed (they are not local)."""
        model_list = [_openai_entry(), _openai_mini_entry()]
        with patch.object(self.analyzer, "_probe_api_base_reachable") as mock_probe:
            result = self.analyzer._filter_reachable_model_list(model_list)
        mock_probe.assert_not_called()
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests: models_to_try when channel router is active (the core dispatch fix)
# ---------------------------------------------------------------------------

class TestCallLitellmModelsToTry:
    """Verify _call_litellm uses filtered active_model_list, not config.litellm_model."""

    def setup_method(self):
        self.analyzer = _make_analyzer()

    def _make_config(self, litellm_model="openai/qwen/qwen3.6-35b-a3b", active_models=None):
        """Return a minimal config with channel setup + active_model_list override."""
        cfg = SimpleNamespace(
            litellm_model=litellm_model,
            litellm_fallback_models=[],
            llm_model_list=[_lmstudio_entry(), _openai_entry(), _openai_mini_entry()],
            llm_temperature=0.7,
            report_integrity_enabled=False,
            report_integrity_retry=0,
        )
        if active_models is not None:
            # Simulate post-pre-check state: lmstudio filtered out
            self.analyzer._active_model_list = active_models
        return cfg

    def test_channel_router_uses_active_list_not_config_model(self):
        """When channel router active, models_to_try must come from _active_model_list."""
        active = [_openai_entry(), _openai_mini_entry()]
        cfg = self._make_config(active_models=active)

        dispatched_models = []

        def fake_dispatch(model, kwargs, **kw):
            dispatched_models.append(model)
            return MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])

        with patch.object(self.analyzer, "_get_runtime_config", return_value=cfg), \
             patch.object(self.analyzer, "_has_channel_config", return_value=True), \
             patch.object(self.analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch), \
             patch.object(self.analyzer, "_router", MagicMock()), \
             patch("src.analyzer.get_configured_llm_models",
                   side_effect=lambda lst: [e["model_name"] for e in lst]), \
             patch("src.analyzer.apply_litellm_generation_params", side_effect=lambda kw, *a, **k: kw), \
             patch("src.analyzer.call_litellm_with_param_recovery",
                   side_effect=lambda fn, model, call_kwargs, **kw: fn(call_kwargs)):
            try:
                self.analyzer._call_litellm("test prompt", {"temperature": 0.7})
            except Exception:
                pass  # We only care which models were attempted

        # qwen/qwen3.6-35b-a3b must NOT be attempted
        assert "openai/qwen/qwen3.6-35b-a3b" not in dispatched_models, (
            f"Expected qwen NOT dispatched, but got: {dispatched_models}"
        )
        # At least one cloud model must be attempted
        cloud_attempted = [m for m in dispatched_models if "gpt-4o" in m]
        assert cloud_attempted, f"Expected gpt-4o attempted, got: {dispatched_models}"

    def test_no_channel_router_uses_config_model(self):
        """When channel router is NOT active, config.litellm_model is used (legacy path)."""
        cfg = self._make_config(litellm_model="openai/gpt-3.5-turbo")
        dispatched_models = []

        def fake_dispatch(model, kwargs, **kw):
            dispatched_models.append(model)
            return MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])

        with patch.object(self.analyzer, "_get_runtime_config", return_value=cfg), \
             patch.object(self.analyzer, "_has_channel_config", return_value=False), \
             patch.object(self.analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch), \
             patch("src.analyzer.get_configured_llm_models", return_value=[]), \
             patch("src.analyzer.apply_litellm_generation_params", side_effect=lambda kw, *a, **k: kw), \
             patch("src.analyzer.call_litellm_with_param_recovery",
                   side_effect=lambda fn, model, call_kwargs, **kw: fn(call_kwargs)):
            try:
                self.analyzer._call_litellm("test prompt", {"temperature": 0.7})
            except Exception:
                pass

        assert "openai/gpt-3.5-turbo" in dispatched_models

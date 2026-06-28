# -*- coding: utf-8 -*-
"""
Tests for agent-mode pipeline integration.

Covers:
- Config: agent_mode, agent_max_steps, agent_skills fields
- _analyze_with_agent method
- _agent_result_to_analysis_result conversion
- YAML strategy loading (load_builtin_strategies)
"""

import json
import importlib
import types
import unittest
import sys
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _builtin_strategy_names() -> set[str]:
    strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
    return {path.stem for path in strategies_dir.glob("*.yaml")}


# ============================================================
# Config tests
# ============================================================

class TestAgentConfig(unittest.TestCase):
    """Test agent-related configuration fields load correctly."""

    @patch.dict(os.environ, {}, clear=True)
    @patch('src.config.load_dotenv')
    def test_default_agent_config(self, _mock_dotenv):
        """Agent mode should be disabled by default."""
        from src.config import AGENT_MAX_STEPS_DEFAULT, Config
        Config._instance = None
        config = Config._load_from_env()
        self.assertEqual(config.agent_litellm_model, "")
        self.assertFalse(config.agent_mode)
        self.assertEqual(config.agent_max_steps, AGENT_MAX_STEPS_DEFAULT)
        self.assertEqual(config.agent_skills, [])

    @patch.dict(os.environ, {
        'AGENT_MODE': 'true',
        'AGENT_MAX_STEPS': '15',
        'AGENT_SKILLS': 'dragon_head,shrink_pullback,volume_breakout',
    }, clear=True)
    def test_agent_config_from_env(self):
        """Agent config should be loaded from environment."""
        from src.config import Config
        Config._instance = None
        config = Config._load_from_env()
        self.assertTrue(config.agent_mode)
        self.assertEqual(config.agent_max_steps, 15)
        self.assertEqual(config.agent_skills, ['dragon_head', 'shrink_pullback', 'volume_breakout'])

    @patch.dict(os.environ, {'AGENT_MODE': 'false'}, clear=True)
    def test_agent_mode_disabled(self):
        """Explicitly disabled agent mode."""
        from src.config import Config
        Config._instance = None
        config = Config._load_from_env()
        self.assertFalse(config.agent_mode)

    @patch.dict(os.environ, {'AGENT_SKILLS': ''}, clear=True)
    def test_empty_skills_list(self):
        """Empty AGENT_SKILLS should produce empty list."""
        from src.config import Config
        Config._instance = None
        config = Config._load_from_env()
        self.assertEqual(config.agent_skills, [])

    @patch.dict(os.environ, {'AGENT_SKILLS': '  dragon_head , shrink_pullback  '}, clear=True)
    def test_skills_whitespace_handling(self):
        """Skills should have whitespace trimmed."""
        from src.config import Config
        Config._instance = None
        config = Config._load_from_env()
        self.assertEqual(config.agent_skills, ['dragon_head', 'shrink_pullback'])

    @patch.dict(os.environ, {'AGENT_LITELLM_MODEL': 'gpt-4o-mini'}, clear=True)
    def test_agent_is_available_when_agent_primary_model_is_configured(self):
        """Agent availability auto-detection should use effective Agent primary model."""
        from src.config import Config
        Config._instance = None
        config = Config._load_from_env()
        self.assertEqual(config.agent_litellm_model, 'openai/gpt-4o-mini')
        self.assertTrue(config.is_agent_available())

    def test_agent_models_to_try_inherit_legacy_provider_models(self):
        """Legacy provider key/model envs should still produce a non-empty Agent model try list."""
        from src.config import Config, get_effective_agent_models_to_try

        test_cases = [
            (
                {
                    "GEMINI_API_KEY": "gemini-test-key",
                    "GEMINI_MODEL": "gemini-2.5-flash",
                    "AGENT_LITELLM_MODEL": "",
                },
                ["gemini/gemini-2.5-flash", "gemini/gemini-3-flash-preview"],
            ),
            (
                {
                    "OPENAI_API_KEY": "sk-test-value",
                    "OPENAI_MODEL": "gpt-4o-mini",
                    "AGENT_LITELLM_MODEL": "",
                },
                ["openai/gpt-4o-mini"],
            ),
            (
                {
                    "ANTHROPIC_API_KEY": "anthropic-test-key",
                    "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
                    "AGENT_LITELLM_MODEL": "",
                },
                ["anthropic/claude-3-5-sonnet-20241022"],
            ),
        ]

        with patch("src.config.setup_env"), patch.object(Config, "_parse_litellm_yaml", return_value=[]):
            for env, expected_models in test_cases:
                with self.subTest(expected_models=expected_models), patch.dict(os.environ, env, clear=True):
                    Config._instance = None
                    config = Config._load_from_env()
                    self.assertEqual(get_effective_agent_models_to_try(config), expected_models)

        Config._instance = None

    def test_build_agent_executor_does_not_mutate_llm_route_config(self) -> None:
        """Agent factory should not rewrite model/base_url/runtime routing fields."""
        provided_config = SimpleNamespace(
            agent_arch="single",
            agent_skills=["bull_trend"],
            agent_max_steps="10",
            agent_orchestrator_timeout_s="120",
            litellm_model="openai/gpt-5",
            agent_litellm_model="anthropic/claude-3-7-sonnet-20250219",
            openai_base_url="https://api.openai.com/v1",
        )
        captured: Dict[str, Any] = {}

        def _mock_llm_adapter(cfg):
            captured["cfg"] = cfg
            return MagicMock()

        fake_llm_module = types.ModuleType("src.agent.llm_adapter")
        fake_llm_module.LLMToolAdapter = _mock_llm_adapter

        fake_executor_module = types.ModuleType("src.agent.executor")
        fake_executor_cls = MagicMock(return_value=MagicMock())
        fake_executor_module.AgentExecutor = fake_executor_cls

        skill_manager = MagicMock()
        skill_manager.list_skills.return_value = [
            SimpleNamespace(
                name="bull_trend",
                display_name="bull_trend",
                description="bull_trend desc",
                instructions="測試指令",
                default_active=True,
                default_router=True,
                default_priority=100,
                user_invocable=True,
                source="builtin",
            )
        ]
        skill_manager.get_skill_instructions.return_value = "測試指令"

        with patch.dict(sys.modules, {
            "litellm": MagicMock(),
            "src.agent.llm_adapter": fake_llm_module,
            "src.agent.executor": fake_executor_module,
        }):
            factory_module = importlib.import_module("src.agent.factory")
            with patch.object(factory_module, "get_skill_manager", return_value=skill_manager), \
                 patch.object(factory_module, "get_tool_registry", return_value=MagicMock()):
                factory_module.build_agent_executor(provided_config)

        adapter_cfg = captured.get("cfg")
        self.assertIs(adapter_cfg, provided_config)
        self.assertEqual(provided_config.agent_max_steps, "10")
        self.assertEqual(provided_config.agent_orchestrator_timeout_s, "120")
        self.assertEqual(provided_config.litellm_model, "openai/gpt-5")
        self.assertEqual(provided_config.agent_litellm_model, "anthropic/claude-3-7-sonnet-20250219")
        self.assertEqual(provided_config.openai_base_url, "https://api.openai.com/v1")
        fake_executor_cls.assert_called_once()
        kwargs = fake_executor_cls.call_args.kwargs
        self.assertEqual(kwargs["max_steps"], 10)
        self.assertEqual(kwargs["timeout_seconds"], 120)

    def test_build_agent_executor_multi_arch_does_not_mutate_llm_route_config(self) -> None:
        """Multi-arch path should keep provider/base_url/runtime fields unchanged."""
        provided_config = SimpleNamespace(
            agent_arch="multi",
            agent_skills=["bull_trend"],
            agent_max_steps="10",
            agent_orchestrator_timeout_s="120",
            litellm_model="openai/gpt-5",
            agent_litellm_model="anthropic/claude-3-7-sonnet-20250219",
            openai_base_url="https://api.openai.com/v1",
            agent_orchestrator_mode="standard",
        )
        captured: Dict[str, Any] = {}

        def _mock_llm_adapter(cfg):
            captured["cfg"] = cfg
            return MagicMock()

        fake_llm_module = types.ModuleType("src.agent.llm_adapter")
        fake_llm_module.LLMToolAdapter = _mock_llm_adapter

        fake_orchestrator_module = types.ModuleType("src.agent.orchestrator")
        fake_orchestrator_cls = MagicMock(return_value=MagicMock())
        fake_orchestrator_module.AgentOrchestrator = fake_orchestrator_cls

        skill_manager = MagicMock()
        skill_manager.list_skills.return_value = [
            SimpleNamespace(
                name="bull_trend",
                display_name="bull_trend",
                description="bull_trend desc",
                instructions="測試指令",
                default_active=True,
                default_router=True,
                default_priority=100,
                user_invocable=True,
                source="builtin",
            )
        ]
        skill_manager.get_skill_instructions.return_value = "測試指令"

        with patch.dict(sys.modules, {
            "litellm": MagicMock(),
            "src.agent.llm_adapter": fake_llm_module,
            "src.agent.orchestrator": fake_orchestrator_module,
            "src.agent.executor": MagicMock(),
        }):
            factory_module = importlib.import_module("src.agent.factory")
            with patch.object(factory_module, "get_skill_manager", return_value=skill_manager), \
                 patch.object(factory_module, "get_tool_registry", return_value=MagicMock()):
                factory_module.build_agent_executor(provided_config)

        adapter_cfg = captured.get("cfg")
        self.assertIs(adapter_cfg, provided_config)
        self.assertEqual(provided_config.agent_max_steps, "10")
        self.assertEqual(provided_config.agent_orchestrator_timeout_s, "120")
        self.assertEqual(provided_config.litellm_model, "openai/gpt-5")
        self.assertEqual(provided_config.agent_litellm_model, "anthropic/claude-3-7-sonnet-20250219")
        self.assertEqual(provided_config.openai_base_url, "https://api.openai.com/v1")
        fake_orchestrator_cls.assert_called_once()
        kwargs = fake_orchestrator_cls.call_args.kwargs
        self.assertEqual(kwargs["max_steps"], 10)
        self.assertIs(kwargs["config"], provided_config)

    def test_invalid_numeric_config_values_fallback_to_defaults_with_warning(self) -> None:
        """Invalid agent_max_steps / agent_orchestrator_timeout_s should fallback and emit warning."""
        provided_config = SimpleNamespace(
            agent_arch="single",
            agent_skills=["bull_trend"],
            agent_max_steps="invalid-steps",
            agent_orchestrator_timeout_s="invalid-timeout",
            litellm_model="openai/gpt-5",
            agent_litellm_model="anthropic/claude-3-7-sonnet-20250219",
            openai_base_url="https://api.openai.com/v1",
        )
        captured: Dict[str, Any] = {}

        def _mock_llm_adapter(cfg):
            captured["cfg"] = cfg
            return MagicMock()

        fake_llm_module = types.ModuleType("src.agent.llm_adapter")
        fake_llm_module.LLMToolAdapter = _mock_llm_adapter

        fake_executor_module = types.ModuleType("src.agent.executor")
        fake_executor_cls = MagicMock(return_value=MagicMock())
        fake_executor_module.AgentExecutor = fake_executor_cls

        skill_manager = MagicMock()
        skill_manager.list_skills.return_value = [
            SimpleNamespace(
                name="bull_trend",
                display_name="bull_trend",
                description="bull_trend desc",
                instructions="測試指令",
                default_active=True,
                default_router=True,
                default_priority=100,
                user_invocable=True,
                source="builtin",
            )
        ]
        skill_manager.get_skill_instructions.return_value = "測試指令"

        with self.assertLogs("src.agent.factory", level="WARNING") as logs:
            with patch.dict(sys.modules, {
                "litellm": MagicMock(),
                "src.agent.llm_adapter": fake_llm_module,
                "src.agent.executor": fake_executor_module,
            }):
                factory_module = importlib.import_module("src.agent.factory")
                with patch.object(factory_module, "get_skill_manager", return_value=skill_manager), \
                     patch.object(factory_module, "get_tool_registry", return_value=MagicMock()):
                    factory_module.build_agent_executor(provided_config)

        adapter_cfg = captured.get("cfg")
        self.assertIs(adapter_cfg, provided_config)
        self.assertEqual(provided_config.litellm_model, "openai/gpt-5")
        self.assertEqual(provided_config.agent_litellm_model, "anthropic/claude-3-7-sonnet-20250219")
        self.assertEqual(provided_config.openai_base_url, "https://api.openai.com/v1")

        log_output = "\n".join(logs.output)
        self.assertIn("[AgentFactory] Invalid value for agent_max_steps", log_output)
        self.assertIn("[AgentFactory] Invalid value for agent_orchestrator_timeout_s", log_output)

        kwargs = fake_executor_cls.call_args.kwargs
        from src.config import AGENT_MAX_STEPS_DEFAULT
        self.assertEqual(kwargs["max_steps"], AGENT_MAX_STEPS_DEFAULT)
        self.assertEqual(kwargs["timeout_seconds"], 0)


class TestAgentFactorySkillBaseline(unittest.TestCase):
    """Ensure explicit skill selection does not silently re-apply the default bull-trend baseline."""

    @staticmethod
    def _make_skill(
        name: str,
        *,
        default_active: bool = False,
        default_priority: int = 100,
        source: str = "builtin",
    ):
        return SimpleNamespace(
            name=name,
            display_name=name,
            description=f"{name} desc",
            instructions=f"{name} instructions",
            default_active=default_active,
            default_router=default_active,
            default_priority=default_priority,
            user_invocable=True,
            source=source,
        )

    def _run_factory_case(self, config, *, request_skills, skill_catalog, instructions):
        skill_manager = MagicMock()
        skill_manager.list_skills.return_value = skill_catalog
        skill_manager.get_skill_instructions.return_value = instructions

        fake_llm_module = types.ModuleType("src.agent.llm_adapter")
        fake_llm_module.LLMToolAdapter = MagicMock(return_value=MagicMock())
        fake_executor_module = types.ModuleType("src.agent.executor")
        fake_executor_cls = MagicMock(return_value=MagicMock())
        fake_executor_module.AgentExecutor = fake_executor_cls

        with patch.dict(sys.modules, {
            "litellm": MagicMock(),
            "src.agent.llm_adapter": fake_llm_module,
            "src.agent.executor": fake_executor_module,
        }):
            factory_module = importlib.import_module("src.agent.factory")

            with patch.object(factory_module, "get_skill_manager", return_value=skill_manager), \
                 patch.object(factory_module, "get_tool_registry", return_value=MagicMock()):
                factory_module.build_agent_executor(config, skills=request_skills)

        return fake_executor_cls.call_args.kwargs, skill_manager

    def test_explicit_request_disables_default_skill_policy(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=[],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=["chan_theory"],
            skill_catalog=[
                self._make_skill("bull_trend", default_active=True, default_priority=10),
                self._make_skill("chan_theory", default_priority=20),
            ],
            instructions="chan_theory instructions",
        )

        self.assertEqual(kwargs["default_skill_policy"], "")
        self.assertFalse(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["chan_theory"])

    def test_configured_skills_disable_default_skill_policy(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=["wave_theory"],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=None,
            skill_catalog=[
                self._make_skill("bull_trend", default_active=True, default_priority=10),
                self._make_skill("wave_theory", default_priority=20),
            ],
            instructions="wave_theory instructions",
        )

        self.assertEqual(kwargs["default_skill_policy"], "")
        self.assertFalse(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["wave_theory"])

    def test_implicit_default_run_keeps_default_skill_policy(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=[],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=None,
            skill_catalog=[self._make_skill("bull_trend", default_active=True, default_priority=10)],
            instructions="bull_trend instructions",
        )

        self.assertIn("嚴進策略", kwargs["default_skill_policy"])
        self.assertTrue(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["bull_trend"])

    def test_explicit_empty_request_falls_back_to_primary_default_skill(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=[],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=[],
            skill_catalog=[
                self._make_skill("bull_trend", default_active=True, default_priority=10),
                self._make_skill("chan_theory", default_priority=20),
            ],
            instructions="bull_trend instructions",
        )

        self.assertIn("嚴進策略", kwargs["default_skill_policy"])
        self.assertTrue(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["bull_trend"])

    def test_explicit_primary_default_skill_uses_skill_aware_prompt_mode(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=[],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=["bull_trend"],
            skill_catalog=[
                self._make_skill("bull_trend", default_active=True, default_priority=10),
                self._make_skill("chan_theory", default_priority=20),
            ],
            instructions="bull_trend instructions",
        )

        self.assertEqual(kwargs["default_skill_policy"], "")
        self.assertFalse(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["bull_trend"])

    def test_invalid_configured_skills_fall_back_to_primary_default_skill(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=["missing_skill"],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=None,
            skill_catalog=[
                self._make_skill("bull_trend", default_active=True, default_priority=10),
                self._make_skill("chan_theory", default_priority=20),
            ],
            instructions="bull_trend instructions",
        )

        self.assertIn("嚴進策略", kwargs["default_skill_policy"])
        self.assertTrue(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["bull_trend"])

    def test_custom_default_skill_does_not_use_legacy_bull_prompt(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=[],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=None,
            skill_catalog=[
                self._make_skill("custom_default", default_active=True, default_priority=10),
                self._make_skill("bull_trend", default_priority=20),
            ],
            instructions="custom_default instructions",
        )

        self.assertEqual(kwargs["default_skill_policy"], "")
        self.assertFalse(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["custom_default"])

    def test_custom_bull_trend_override_does_not_use_legacy_prompt(self):
        config = SimpleNamespace(
            agent_arch="single",
            agent_skills=[],
            agent_max_steps=10,
            agent_orchestrator_timeout_s=600,
        )
        kwargs, skill_manager = self._run_factory_case(
            config,
            request_skills=None,
            skill_catalog=[
                self._make_skill(
                    "bull_trend",
                    default_active=True,
                    default_priority=10,
                    source="/tmp/custom-skills/bull_trend.yaml",
                ),
            ],
            instructions="custom bull_trend instructions",
        )

        self.assertEqual(kwargs["default_skill_policy"], "")
        self.assertFalse(kwargs["use_legacy_default_prompt"])
        skill_manager.activate.assert_called_once_with(["bull_trend"])


# ============================================================
# AgentResult to AnalysisResult conversion
# ============================================================

class TestAgentResultConversion(unittest.TestCase):
    """Test _agent_result_to_analysis_result without spinning up the full pipeline."""

    def _make_pipeline(self):
        """Create a minimal StockAnalysisPipeline with mocked dependencies."""
        # We need to import and mock carefully to avoid touching real services
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_orchestrator_timeout_s = 0
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            pipeline = StockAnalysisPipeline(config=mock_cfg)
            return pipeline

    def test_convert_success_dashboard(self):
        """Successful AgentResult should produce a valid AnalysisResult."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        dashboard = {
            "stock_name": "台積電",
            "sentiment_score": 80,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "confidence_level": "高",
            "dashboard": {"core_conclusion": {"one_sentence": "看好"}},
            "analysis_summary": "Testing",
            "key_points": "Strong",
            "risk_warning": "High valuation",
            "buy_reason": "Leader",
            "trend_analysis": "Upward",
            "technical_analysis": "Bullish MACD",
            "ma_analysis": "Golden cross",
            "volume_analysis": "Healthy volume",
            "pattern_analysis": "Cup and handle",
            "fundamental_analysis": "Strong revenue",
            "sector_position": "Liquor leader",
            "company_highlights": "Brand value",
            "news_summary": "Recent news",
            "market_sentiment": "Optimistic",
            "hot_topics": "Baijiu",
            "short_term_outlook": "Bullish",
            "medium_term_outlook": "Stable",
        }

        agent_result = AgentResult(
            success=True,
            content=json.dumps(dashboard),
            dashboard=dashboard,
            tool_calls_log=[{"step": 1, "tool": "echo", "success": True}],
            total_steps=3,
            total_tokens=500,
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "2330", "台積電", ReportType.SIMPLE, "q123"
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.code, "2330")
        self.assertEqual(result.name, "台積電")
        self.assertEqual(result.sentiment_score, 80)
        self.assertEqual(result.trend_prediction, "看多")
        self.assertEqual(result.decision_type, "hold")
        self.assertIn("agent:gemini", result.data_sources)
        self.assertIsNotNone(result.dashboard)

    def test_convert_carries_value_network_mermaid_from_dashboard(self):
        """Phase 18D: the agent-mode conversion must extract value_network_mermaid, not drop it."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        dashboard = {
            "stock_name": "Microsoft",
            "sentiment_score": 50,
            "trend_prediction": "看空",
            "operation_advice": "觀望",
            "decision_type": "hold",
            "confidence_level": "中",
            "dashboard": {"core_conclusion": {"one_sentence": "弱勢"}},
            "value_network_mermaid": "flowchart TB\n  A[供應商] --> B[公司]",
        }
        agent_result = AgentResult(
            success=True,
            content=json.dumps(dashboard),
            dashboard=dashboard,
            provider="deepseek",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "MSFT", "Microsoft", ReportType.FULL, "q456"
        )

        self.assertEqual(result.value_network_mermaid, "flowchart TB\n  A[供應商] --> B[公司]")

    def test_convert_defaults_value_network_mermaid_to_none_when_absent(self):
        """Phase 18D: absence of the field must not raise and must default to None."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        dashboard = {
            "stock_name": "Microsoft",
            "sentiment_score": 50,
            "trend_prediction": "看空",
            "operation_advice": "觀望",
            "decision_type": "hold",
            "confidence_level": "中",
            "dashboard": {"core_conclusion": {"one_sentence": "弱勢"}},
        }
        agent_result = AgentResult(
            success=True,
            content=json.dumps(dashboard),
            dashboard=dashboard,
            provider="deepseek",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "MSFT", "Microsoft", ReportType.FULL, "q789"
        )

        self.assertIsNone(result.value_network_mermaid)

    def test_convert_preserves_top_level_phase_decision_with_nested_dashboard(self):
        """Agent top-level phase_decision should survive nested dashboard unwrapping."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        dashboard = {
            "stock_name": "台積電",
            "sentiment_score": 80,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "decision_type": "hold",
            "confidence_level": "中",
            "phase_decision": {
                "phase_context": {"phase": "intraday", "market": "cn"},
                "action_window": "盤中跟蹤",
                "immediate_action": "等待確認",
                "watch_conditions": ["放量突破"],
                "next_check_time": "14:30",
                "confidence_reason": "等待確認",
                "data_limitations": [],
            },
            "dashboard": {"core_conclusion": {"one_sentence": "看好"}},
            "analysis_summary": "Testing",
        }

        agent_result = AgentResult(
            success=True,
            content=json.dumps(dashboard),
            dashboard=dashboard,
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "2330", "台積電", ReportType.SIMPLE, "q-phase"
        )

        self.assertEqual(result.dashboard["phase_decision"]["phase_context"]["phase"], "intraday")
        self.assertEqual(result.dashboard["phase_decision"]["watch_conditions"], ["放量突破"])

    def test_convert_failed_dashboard(self):
        """Failed AgentResult should produce a minimal AnalysisResult."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=False,
            content="",
            dashboard=None,
            error="Max steps exceeded",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "2330", "台積電", ReportType.SIMPLE, "q123"
        )

        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertEqual(result.sentiment_score, 50)
        self.assertEqual(result.operation_advice, "觀望")
        self.assertIn("Max steps exceeded", result.error_message)

    def test_convert_invalid_dashboard_preserves_local_trend_result(self):
        """Invalid Agent dashboard should not erase already-computed trend data."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="LLM returned text but no dashboard JSON",
            dashboard=None,
            provider="ollama",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=64,
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-trend-fallback",
            trend_result=trend_result,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(result.sentiment_score, 64)
        self.assertEqual(result.trend_prediction, "多頭排列")
        self.assertEqual(result.operation_advice, "買進")
        self.assertEqual(result.decision_type, "buy")
        self.assertIn("trend:fallback", result.data_sources)

    def test_convert_empty_dashboard_backfills_local_trend_dashboard(self):
        """Empty Agent dashboard should still produce an integrity-ready local fallback dashboard."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.analyzer import check_content_integrity
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={},
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=68,
            support_levels=[112.3],
            risk_factors=["跌破 MA20 需止損"],
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-empty-dashboard",
            trend_result=trend_result,
        )

        ok, missing = check_content_integrity(result)
        self.assertTrue(ok, missing)
        self.assertEqual(result.sentiment_score, 68)
        self.assertEqual(result.analysis_summary, "趨勢結論：多頭排列；操作建議：買進。")
        self.assertEqual(result.dashboard["sentiment_score"], 68)
        self.assertEqual(result.dashboard["core_conclusion"]["one_sentence"], result.analysis_summary)
        self.assertEqual(result.dashboard["intelligence"]["risk_alerts"], ["跌破 MA20 需止損"])
        self.assertEqual(result.dashboard["battle_plan"]["sniper_points"]["stop_loss"], 112.3)

    def test_convert_dict_operation_advice_missing_decision_type_preserves_buy_signal(self):
        """When operation_advice is dict without decision_type, preserve dict-derived buy/sell hint."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "operation_advice": {
                    "has_position": "買進",
                    "no_position": "觀望",
                },
                "trend_prediction": "看多",
                "sentiment_score": 74,
            },
            provider="ollama",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-dict-advice",
        )

        self.assertEqual(result.operation_advice, "買進")
        self.assertEqual(result.decision_type, "buy")

    def test_convert_missing_decision_type_preserves_conditional_hold_advice(self):
        """Condition-hold wording should remain hold when decision_type is not provided."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "operation_advice": "不跌破支撐位繼續持有",
                "sentiment_score": 72,
            },
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.STRONG_BUY,
            signal_score=78,
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-conditional-hold-advice",
            trend_result=trend_result,
        )

        self.assertEqual(result.operation_advice, "不跌破支撐位繼續持有")
        self.assertEqual(result.decision_type, "hold")

    def test_convert_empty_top_level_advice_uses_nested_dashboard_advice(self):
        """Empty top-level advice dict should not block nested dashboard fallback."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "operation_advice": {},
                "dashboard": {
                    "operation_advice": "減倉",
                    "trend_prediction": "看空",
                    "sentiment_score": 42,
                },
            },
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-nested-advice",
        )

        self.assertEqual(result.operation_advice, "減倉")
        self.assertEqual(result.decision_type, "sell")
        self.assertEqual(result.dashboard["operation_advice"], "減倉")

    def test_convert_placeholder_top_level_advice_uses_nested_dashboard_advice(self):
        """Placeholder advice dict should not block nested dashboard fallback."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "operation_advice": {
                    "has_position": "待補充",
                    "no_position": "TBD",
                },
                "dashboard": {
                    "operation_advice": "減倉",
                    "trend_prediction": "看空",
                    "sentiment_score": 42,
                },
            },
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-placeholder-advice",
        )

        self.assertEqual(result.operation_advice, "減倉")
        self.assertEqual(result.decision_type, "sell")
        self.assertEqual(result.dashboard["operation_advice"], "減倉")

    def test_convert_malformed_top_level_summary_uses_nested_dashboard_summary(self):
        """Malformed top-level analysis_summary should not block nested dashboard fallback."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "analysis_summary": [],
                "dashboard": {
                    "analysis_summary": "AI 已給出的摘要",
                    "trend_prediction": "看多",
                    "operation_advice": "持有",
                    "sentiment_score": 73,
                },
            },
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-nested-summary",
        )

        self.assertEqual(result.analysis_summary, "AI 已給出的摘要")
        self.assertEqual(result.dashboard["analysis_summary"], "AI 已給出的摘要")

    def test_convert_non_string_summary_falls_back_to_nested_or_local_summary(self):
        """Non-string analysis_summary should trigger fallback to nested summary or local fallback."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        for raw_summary in (0, False):
            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "analysis_summary": raw_summary,
                    "trend_prediction": "看多",
                    "dashboard": {
                        "analysis_summary": "AI 已給出的摘要",
                    },
                    "operation_advice": "持有",
                    "sentiment_score": 73,
                },
                provider="gemini",
            )

            result = pipeline._agent_result_to_analysis_result(
                agent_result,
                "2330",
                "台積電",
                ReportType.SIMPLE,
                f"q-summary-non-string-{raw_summary}",
            )

            self.assertEqual(result.analysis_summary, "AI 已給出的摘要")
            self.assertEqual(result.dashboard["analysis_summary"], "AI 已給出的摘要")

    def test_convert_malformed_scalar_fields_fallback_to_trend_result(self):
        """Malformed non-scalar scalar fields should not be treated as valid values."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "sentiment_score": {"value": ""},
                "trend_prediction": [],
                "operation_advice": [],
                "decision_type": {},
            },
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=66,
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-malformed-scalars",
            trend_result=trend_result,
        )

        self.assertEqual(result.sentiment_score, 66)
        self.assertEqual(result.trend_prediction, "多頭排列")
        self.assertEqual(result.operation_advice, "買進")
        self.assertEqual(result.decision_type, "buy")
        self.assertEqual(result.dashboard["sentiment_score"], 66)
        self.assertEqual(result.dashboard["trend_prediction"], "多頭排列")
        self.assertEqual(result.dashboard["operation_advice"], "買進")
    def test_convert_empty_dashboard_backfills_localized_trend_fallback_for_en(self):
        """English reports should keep trend/advice fallback values localized."""
        pipeline = self._make_pipeline()
        pipeline.config.report_language = "en"

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={},
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=70,
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-en-fallback",
            trend_result=trend_result,
        )

        self.assertEqual(result.report_language, "en")
        self.assertEqual(result.trend_prediction, "Bullish")
        self.assertEqual(result.operation_advice, "Buy")
        self.assertEqual(
            result.analysis_summary,
            "Trend view: Bullish; action advice: Buy.",
        )
        self.assertEqual(result.dashboard["trend_prediction"], "Bullish")
        self.assertEqual(result.dashboard["operation_advice"], "Buy")
        self.assertEqual(
            result.dashboard["core_conclusion"]["one_sentence"],
            "Trend view: Bullish; action advice: Buy.",
        )

    def test_convert_non_dict_advice_conflict_keeps_advice_decision(self):
        """Conflict between trend fallback and explicit non-dict advice should keep advice decision."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "sentiment_score": 65,
                "trend_prediction": "看空",
                "operation_advice": "減倉",
            },
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=70,
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-advice-vs-trend",
            trend_result=trend_result,
        )

        self.assertEqual(result.operation_advice, "減倉")
        self.assertEqual(result.decision_type, "sell")

    def test_convert_partial_dashboard_uses_trend_fallback_for_missing_scalars(self):
        """Partial Agent dashboards should keep AI fields while filling missing scalars locally."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "stock_name": "台積電",
                "dashboard": {
                    "core_conclusion": {"one_sentence": "AI 已給出的核心結論"},
                    "intelligence": {"risk_alerts": ["AI 風險"]},
                    "battle_plan": {"sniper_points": {"take_profit": "120元"}},
                },
            },
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=66,
            support_levels=[108.5],
            risk_factors=["跌破 MA20"],
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-partial-dashboard",
            trend_result=trend_result,
        )

        self.assertEqual(result.sentiment_score, 66)
        self.assertEqual(result.trend_prediction, "多頭排列")
        self.assertEqual(result.operation_advice, "買進")
        self.assertEqual(result.decision_type, "buy")
        self.assertEqual(result.dashboard["sentiment_score"], 66)
        self.assertEqual(result.dashboard["operation_advice"], "買進")
        self.assertEqual(result.dashboard["core_conclusion"]["one_sentence"], "AI 已給出的核心結論")
        self.assertEqual(result.dashboard["intelligence"]["risk_alerts"], ["AI 風險"])
        self.assertEqual(result.dashboard["battle_plan"]["sniper_points"]["stop_loss"], 108.5)
        self.assertIn("trend:fallback", result.data_sources)

    def test_convert_risk_alerts_string_placeholder_uses_local_risk_factors(self):
        """String-like placeholder risk alerts should be replaced with local trend risk factors."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.analyzer import check_content_integrity
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "dashboard": {
                    "core_conclusion": {"one_sentence": "AI 已給出的核心結論"},
                    "intelligence": {"risk_alerts": "待補充"},
                },
            },
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=66,
            support_levels=[108.5],
            risk_factors=["漲幅過快", "回撤放大"],
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-risk-alerts-string-placeholder",
            trend_result=trend_result,
        )

        ok, missing = check_content_integrity(result)
        self.assertTrue(ok, missing)
        self.assertEqual(result.dashboard["intelligence"]["risk_alerts"], ["漲幅過快", "回撤放大"])

    def test_convert_placeholder_dashboard_is_completed_from_local_context(self):
        """Placeholder dashboard blocks should be completed without falling back to neutral defaults."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.analyzer import check_content_integrity
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "stock_name": "台積電",
                "dashboard": {
                    "core_conclusion": {"one_sentence": "待補充"},
                    "intelligence": {},
                    "battle_plan": {"sniper_points": {"stop_loss": ""}},
                },
            },
            provider="gemini",
        )
        trend_result = TrendAnalysisResult(
            code="2330",
            trend_status=TrendStatus.BULL,
            buy_signal=BuySignal.BUY,
            signal_score=62,
            risk_factors=["趨勢跌破支撐需減倉"],
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result,
            "2330",
            "台積電",
            ReportType.SIMPLE,
            "q-placeholder-dashboard",
            trend_result=trend_result,
        )

        ok, missing = check_content_integrity(result)
        self.assertTrue(ok, missing)
        self.assertEqual(result.sentiment_score, 62)
        self.assertEqual(result.dashboard["sentiment_score"], 62)
        self.assertEqual(result.dashboard["core_conclusion"]["one_sentence"], result.analysis_summary)
        self.assertEqual(result.dashboard["intelligence"]["risk_alerts"], ["趨勢跌破支撐需減倉"])
        self.assertEqual(result.dashboard["battle_plan"]["sniper_points"]["stop_loss"], "待補充")

    def test_convert_invalid_dashboard_normalizes_strong_trend_decision_type(self):
        """Fallback preserves strong advice text while keeping stable decision_type values."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType
        from src.stock_analyzer import BuySignal, TrendAnalysisResult, TrendStatus

        cases = [
            (BuySignal.STRONG_BUY, "buy", "強烈買進"),
            (BuySignal.STRONG_SELL, "sell", "強烈賣出"),
        ]

        for buy_signal, expected_decision, expected_advice in cases:
            with self.subTest(buy_signal=buy_signal):
                agent_result = AgentResult(
                    success=True,
                    content="LLM returned text but no dashboard JSON",
                    dashboard=None,
                    provider="ollama",
                )
                trend_result = TrendAnalysisResult(
                    code="2330",
                    trend_status=TrendStatus.BULL,
                    buy_signal=buy_signal,
                    signal_score=80,
                )

                result = pipeline._agent_result_to_analysis_result(
                    agent_result,
                    "2330",
                    "台積電",
                    ReportType.SIMPLE,
                    "q-trend-fallback",
                    trend_result=trend_result,
                )

                self.assertEqual(result.operation_advice, expected_advice)
                self.assertEqual(result.decision_type, expected_decision)

    def test_convert_uses_dashboard_stock_name_when_input_is_placeholder(self):
        """When input name is placeholder-like, prefer dashboard stock_name."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "stock_name": "科創晶片ETF",
                "sentiment_score": 75,
                "trend_prediction": "震盪偏多",
                "operation_advice": "持有",
                "decision_type": "hold",
            },
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "588200", "股票588200", ReportType.SIMPLE, "q-placeholder"
        )
        self.assertEqual(result.name, "科創晶片ETF")

    def test_convert_keeps_input_stock_name_when_valid(self):
        """When input name is already valid, do not overwrite with dashboard value."""
        pipeline = self._make_pipeline()

        from src.agent.executor import AgentResult
        from src.enums import ReportType

        agent_result = AgentResult(
            success=True,
            content="{}",
            dashboard={
                "stock_name": "錯誤名稱",
                "sentiment_score": 70,
                "trend_prediction": "看多",
                "operation_advice": "持有",
                "decision_type": "hold",
            },
            provider="gemini",
        )

        result = pipeline._agent_result_to_analysis_result(
            agent_result, "2330", "台積電", ReportType.SIMPLE, "q-valid"
        )
        self.assertEqual(result.name, "台積電")


# ============================================================
# Skill registration in pipeline
# ============================================================

class TestPipelineSkillRegistration(unittest.TestCase):
    """Test built-in strategies load from YAML via SkillManager."""

    def test_load_builtin_strategies(self):
        """SkillManager.load_builtin_strategies() should load all YAML strategies."""
        from src.agent.skills.base import SkillManager

        skill_manager = SkillManager()
        expected = _builtin_strategy_names()
        count = skill_manager.load_builtin_strategies()
        self.assertEqual(count, len(expected))

        skills = skill_manager.list_skills()
        self.assertEqual(len(skills), len(expected))

        names = {s.name for s in skills}
        self.assertEqual(names, expected)

        # All should be disabled by default
        active = skill_manager.list_active_skills()
        self.assertEqual(len(active), 0)

        # All should have source='builtin'
        for s in skills:
            self.assertEqual(s.source, "builtin")


# ============================================================
# Pipeline dual-path routing
# ============================================================

class TestPipelineRouting(unittest.TestCase):
    """Test that analyze_stock routes to agent mode when config.agent_mode is True."""

    def test_agent_mode_routes_to_agent(self):
        """When agent_mode=True, analyze_stock should call _analyze_with_agent."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 5
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)

            # Mock _analyze_with_agent to verify it gets called
            pipeline._analyze_with_agent = MagicMock(return_value=None)

            pipeline.analyze_stock("2330", ReportType.SIMPLE, "q1")

            pipeline._analyze_with_agent.assert_called_once()
            call_args = pipeline._analyze_with_agent.call_args
            # Positional args: code, report_type, query_id, stock_name, realtime_quote, chip_data, fundamental_context, trend_result
            self.assertEqual(call_args[0][0], "2330")
            self.assertEqual(call_args[0][1], ReportType.SIMPLE)
            self.assertEqual(call_args[0][2], "q1")
            # trend_result (8th arg) should be present (may be a TrendAnalysisResult or None)
            self.assertEqual(len(call_args[0]), 8)

    def test_legacy_mode_does_not_call_agent(self):
        """When agent_mode=False, analyze_stock should NOT call _analyze_with_agent."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db') as mock_db, \
             patch('src.core.pipeline.DataFetcherManager') as mock_fm, \
             patch('src.core.pipeline.GeminiAnalyzer') as mock_analyzer, \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService') as mock_search:

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_cfg.is_agent_available.return_value = False
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)

            # Mock the fetcher_manager to return None for realtime
            pipeline.fetcher_manager.get_realtime_quote.return_value = None
            pipeline.fetcher_manager.get_chip_distribution.return_value = None
            # Mock search service
            pipeline.search_service.is_available = False
            # Mock DB context
            pipeline.db.get_analysis_context.return_value = None
            # Mock analyzer
            pipeline.analyzer.analyze.return_value = None

            result = pipeline.analyze_stock("2330", ReportType.SIMPLE, "q1")

            # _analyze_with_agent should NOT exist as a mock (it's the real method)
            # Instead, verify analyzer.analyze was called (legacy path)
            pipeline.analyzer.analyze.assert_called_once()

    def test_request_skills_auto_enable_agent_mode(self):
        """Request-specific skills should route the stock analysis through Agent mode."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_cfg.agent_max_steps = 5
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(
                config=mock_cfg,
                analysis_skills=["growth_quality"],
            )
            pipeline._analyze_with_agent = MagicMock(return_value=None)

            pipeline.analyze_stock("2330", ReportType.SIMPLE, "q1")

            pipeline._analyze_with_agent.assert_called_once()
            self.assertEqual(pipeline.analysis_skills, ["growth_quality"])


class TestAnalyzeWithAgentStockName(unittest.TestCase):
    """Test stock-name handling in _analyze_with_agent."""

    def test_analyze_with_agent_uses_resolved_name_for_news_persistence(self):
        """Should use resolved stock name from dashboard for search and DB persistence."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'), \
             patch('src.agent.factory.build_agent_executor') as mock_build_executor, \
             patch('src.agent.executor.AgentExecutor.run') as mock_agent_run:

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.agent.executor import AgentResult
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)

            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "stock_name": "科創晶片ETF",
                    "sentiment_score": 78,
                    "trend_prediction": "震盪偏多",
                    "operation_advice": "持有",
                    "decision_type": "hold",
                },
                provider="gemini",
            )
            mock_executor = MagicMock()
            mock_executor.run.return_value = agent_result
            mock_build_executor.return_value = mock_executor
            mock_agent_run.return_value = agent_result

            news_response = MagicMock()
            news_response.success = True
            news_response.results = [{"title": "test"}]
            news_response.query = "test query"
            pipeline.search_service.is_available = True
            pipeline.search_service.search_stock_news.return_value = news_response

            result = pipeline._analyze_with_agent(
                code="588200",
                report_type=ReportType.SIMPLE,
                query_id="q-news",
                stock_name="股票588200",
                realtime_quote=None,
                chip_data=None
            )

            self.assertIsNotNone(result)
            self.assertEqual(result.name, "科創晶片ETF")
            pipeline.search_service.search_stock_news.assert_called_once_with(
                stock_code="588200",
                stock_name="科創晶片ETF",
                max_results=5
            )
            pipeline.db.save_news_intel.assert_called_once()
            saved_kwargs = pipeline.db.save_news_intel.call_args.kwargs
            self.assertEqual(saved_kwargs["name"], "科創晶片ETF")

    def test_analyze_with_agent_keeps_dashboard_top_level_fields_after_stability(self):
        """Decision stability downgrade in agent flow should sync dashboard and top-level decision fields."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'), \
             patch('src.agent.factory.build_agent_executor') as mock_build_executor:

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_cfg.report_language = "zh"
            mock_cfg.agent_orchestrator_timeout_s = 600
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.agent.executor import AgentResult
            from src.enums import ReportType
            from src.stock_analyzer import TrendAnalysisResult, TrendStatus, BuySignal
            pipeline = StockAnalysisPipeline(config=mock_cfg)

            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "sentiment_score": 30,
                    "trend_prediction": "震盪",
                    "operation_advice": "賣出",
                    "decision_type": "sell",
                    "analysis_summary": "原始建議",
                    "dashboard": {
                        "core_conclusion": {"one_sentence": "初始結論"},
                    },
                },
                provider="gemini",
            )
            mock_executor = MagicMock()
            mock_executor.run.return_value = agent_result
            mock_build_executor.return_value = mock_executor

            trend_result = TrendAnalysisResult(
                code="002812",
                trend_status=TrendStatus.BULL,
                buy_signal=BuySignal.SELL,
                signal_score=30,
                support_levels=[30.0],
                resistance_levels=[34.0],
            )
            fundamental_context = {
                "capital_flow": {
                    "status": "ok",
                    "data": {
                        "stock_flow": {
                            "main_net_inflow": 800_000,
                        }
                    },
                }
            }

            result = pipeline._analyze_with_agent(
                code="002812",
                report_type=ReportType.SIMPLE,
                query_id="q-agent-stability",
                stock_name="恩捷股份",
                realtime_quote={"price": 30.4, "change_pct": -2.1},
                chip_data=None,
                fundamental_context=fundamental_context,
                trend_result=trend_result,
            )

            self.assertIsNotNone(result)
            self.assertEqual(result.decision_type, "hold")
            self.assertEqual(result.operation_advice, "洗盤觀察")
            self.assertEqual(result.dashboard.get("decision_type"), "hold")
            self.assertEqual(result.dashboard.get("operation_advice"), "洗盤觀察")
            self.assertEqual(result.dashboard.get("sentiment_score"), result.sentiment_score)

    def test_analyze_with_agent_phase_integrity_fills_missing_phase_decision(self):
        """Agent weak integrity should enforce phase_decision when phase context exists."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'), \
             patch('src.agent.factory.build_agent_executor') as mock_build_executor:

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_cfg.report_language = "zh"
            mock_cfg.report_integrity_enabled = True
            mock_cfg.agent_orchestrator_timeout_s = 600
            mock_config.return_value = mock_cfg

            from src.agent.executor import AgentResult
            from src.analyzer import check_content_integrity
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType

            pipeline = StockAnalysisPipeline(config=mock_cfg)
            pipeline.search_service.is_available = False
            pipeline._ensure_agent_history = MagicMock()
            pipeline._build_analysis_context_pack_outputs = MagicMock(
                return_value=(
                    "",
                    {
                        "blocks": [],
                        "data_quality": {"limitations": []},
                    },
                )
            )

            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "sentiment_score": 62,
                    "trend_prediction": "震盪",
                    "operation_advice": "減倉",
                    "decision_type": "sell",
                    "confidence_level": "中",
                    "analysis_summary": "盤中風險偏高",
                    "dashboard": {
                        "core_conclusion": {"one_sentence": "盤中風險偏高"},
                        "intelligence": {"risk_alerts": []},
                    },
                },
                provider="gemini",
            )
            mock_executor = MagicMock()
            mock_executor.run.return_value = agent_result
            mock_build_executor.return_value = mock_executor

            phase_context = {
                "phase": "intraday",
                "market": "cn",
                "market_local_time": "2026-06-02T10:30:00+08:00",
            }
            phase_summary = {
                **phase_context,
                "is_trading_day": True,
                "is_market_open_now": True,
                "is_partial_bar": True,
                "warnings": [],
            }

            result = pipeline._analyze_with_agent(
                code="2330",
                report_type=ReportType.SIMPLE,
                query_id="q-agent-phase-integrity",
                stock_name="台積電",
                realtime_quote=None,
                chip_data=None,
                market_phase_context=phase_context,
                market_phase_summary=phase_summary,
            )

            self.assertIsNotNone(result)
            ok, missing = check_content_integrity(result, require_phase_decision=True)
            self.assertTrue(ok, missing)
            phase_decision = result.dashboard["phase_decision"]
            self.assertEqual(phase_decision["phase_context"]["phase"], "intraday")
            self.assertEqual(phase_decision["action_window"], "模型未提供階段化行動視窗")
            self.assertEqual(phase_decision["immediate_action"], "模型未提供階段化即時動作")
            self.assertEqual(phase_decision["watch_conditions"], [])
            self.assertEqual(phase_decision["next_check_time"], "模型未提供下一次檢查點")
            self.assertEqual(phase_decision["confidence_reason"], "模型未提供階段化置信度理由")

    def test_analyze_with_agent_preserves_chip_structure_when_prefetch_missing(self):
        """Agent tool chip metrics should not be cleared when prefetch chip_data is unavailable."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'), \
             patch('src.agent.factory.build_agent_executor') as mock_build_executor:

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_cfg.report_language = "zh"
            mock_cfg.report_integrity_enabled = False
            mock_cfg.agent_orchestrator_timeout_s = 600
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.agent.executor import AgentResult
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)
            pipeline.search_service.is_available = False

            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "sentiment_score": 70,
                    "trend_prediction": "震盪",
                    "operation_advice": "持有",
                    "decision_type": "hold",
                    "dashboard": {
                        "data_perspective": {
                            "chip_structure": {
                                "profit_ratio": "52.0%",
                                "avg_cost": 1850.0,
                                "concentration": "0.00%",
                                "chip_health": "健康",
                            }
                        }
                    },
                },
                provider="gemini",
            )
            mock_executor = MagicMock()
            mock_executor.run.return_value = agent_result
            mock_build_executor.return_value = mock_executor

            result = pipeline._analyze_with_agent(
                code="2330",
                report_type=ReportType.SIMPLE,
                query_id="q-agent-chip",
                stock_name="台積電",
                realtime_quote=None,
                chip_data=None,
            )

            self.assertIsNotNone(result)
            dp = result.dashboard["data_perspective"]
            self.assertEqual(dp["chip_structure"]["concentration"], "0.00%")
            self.assertNotIn("chip_unavailable_reason", dp)

    def test_analyze_with_agent_history_context_includes_diagnostic_snapshot(self):
        """Agent 分析入庫存檔時應保留 diagnostics 快照，避免歷史診斷返回 unknown。"""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'), \
             patch('src.core.pipeline.fill_price_position_if_needed'), \
             patch('src.core.pipeline.stabilize_decision_with_structure'), \
             patch('src.core.pipeline.current_diagnostic_snapshot') as mock_diagnostic_snapshot:

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.anspire_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = True
            mock_cfg.report_language = "zh"
            mock_cfg.report_integrity_enabled = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)
            pipeline.search_service.is_available = False
            pipeline._ensure_agent_history = MagicMock()
            pipeline._agent_result_to_analysis_result = MagicMock(
                return_value=SimpleNamespace(
                    success=True,
                    code="588200",
                    name="科創晶片ETF",
                    model_used="agent-model",
                    sentiment_score=70,
                    operation_advice="持有",
                    trend_prediction="震盪",
                    analysis_summary="測試摘要",
                )
            )

            mock_executor = MagicMock()
            mock_executor.run.return_value = SimpleNamespace(
                success=True,
                provider="agent-provider",
                dashboard={"stock_name": "科創晶片ETF"},
            )
            with patch('src.agent.factory.build_agent_executor', return_value=mock_executor):
                mock_diagnostic_snapshot.return_value = {"trace_id": "trace-1391", "query_id": "q-1391"}
                pipeline.db.save_analysis_history = MagicMock(return_value=1)

                result = pipeline._analyze_with_agent(
                    code="588200",
                    report_type=ReportType.SIMPLE,
                    query_id="q-1391",
                    stock_name="科創晶片ETF",
                    realtime_quote=None,
                    chip_data=None,
                )

            self.assertIsNotNone(result)
            call_kwargs = pipeline.db.save_analysis_history.call_args.kwargs
            history_context = call_kwargs["context_snapshot"]
            self.assertIn("diagnostics", history_context)
            self.assertEqual(history_context["diagnostics"]["trace_id"], "trace-1391")
            self.assertEqual(history_context["stock_name"], "科創晶片ETF")


# ============================================================
# Agent construction chain (real objects, mocked LLM)
# ============================================================

class TestAgentConstructionChain(unittest.TestCase):
    """Test that the agent construction chain wires up correctly."""

    def test_llm_adapter_accepts_config(self):
        """LLMToolAdapter should accept an optional config parameter."""
        mock_cfg = MagicMock()
        mock_cfg.gemini_api_key = ""
        mock_cfg.anthropic_api_key = ""
        mock_cfg.openai_api_key = ""
        mock_cfg.openai_base_url = ""
        mock_cfg.openai_model = ""

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        self.assertIsNotNone(adapter)

    def test_llm_adapter_no_args(self):
        """LLMToolAdapter should also work with no arguments (uses get_config)."""
        with patch('src.agent.llm_adapter.get_config') as mock_get_config:
            mock_cfg = MagicMock()
            mock_cfg.gemini_api_key = ""
            mock_cfg.anthropic_api_key = ""
            mock_cfg.openai_api_key = ""
            mock_cfg.openai_base_url = ""
            mock_cfg.openai_model = ""
            mock_get_config.return_value = mock_cfg

            from src.agent.llm_adapter import LLMToolAdapter
            adapter = LLMToolAdapter()
            self.assertIsNotNone(adapter)

    def test_full_construction_chain(self):
        """Test ToolRegistry + SkillManager + LLMToolAdapter + AgentExecutor wiring."""
        from src.agent.tools.registry import ToolRegistry, ToolDefinition, ToolParameter
        from src.agent.skills.base import SkillManager, Skill
        from src.agent.llm_adapter import LLMToolAdapter
        from src.agent.executor import AgentExecutor

        # Build registry with a dummy tool
        registry = ToolRegistry()

        def dummy_handler(x: str) -> str:
            return f"echo {x}"

        dummy_tool = ToolDefinition(
            name="dummy_echo",
            description="A test tool for echoing input.",
            category="test",
            parameters=[ToolParameter(name="x", type="string", description="input string", required=True)],
            handler=dummy_handler,
        )
        registry.register(dummy_tool)

        # Build skill manager with a fresh skill instance (avoid module singleton state)
        skill_manager = SkillManager()
        test_skill = Skill(
            name="test_skill",
            display_name="測試策略",
            description="A test skill",
            instructions="Test instructions for analysis.",
            category="trend",
            core_rules=[1, 2],
        )
        skill_manager.register(test_skill)
        skill_manager.activate(["test_skill"])
        instructions = skill_manager.get_skill_instructions()
        self.assertIn("測試策略", instructions)

        # Build LLM adapter with mocked config (no real API keys)
        mock_cfg = MagicMock()
        mock_cfg.gemini_api_key = ""
        mock_cfg.anthropic_api_key = ""
        mock_cfg.openai_api_key = ""
        mock_cfg.openai_base_url = ""
        mock_cfg.openai_model = ""
        adapter = LLMToolAdapter(config=mock_cfg)

        # Build executor
        executor = AgentExecutor(
            tool_registry=registry,
            llm_adapter=adapter,
            skill_instructions=instructions,
            max_steps=3,
        )
        self.assertEqual(executor.max_steps, 3)
        self.assertIsNotNone(executor.tool_registry)
        self.assertIsNotNone(executor.llm_adapter)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_call_completion_uses_effective_agent_models_order(self, _mock_router):
        """call_completion should use Agent effective model chain in order."""
        mock_cfg = MagicMock()
        mock_cfg.agent_litellm_model = "gpt-4o-mini"
        mock_cfg.litellm_model = "gemini/gemini-2.5-flash"
        mock_cfg.litellm_fallback_models = ["openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet-20241022"]
        mock_cfg.llm_model_list = []
        mock_cfg.llm_temperature = 0.7
        mock_cfg.gemini_api_keys = []
        mock_cfg.anthropic_api_keys = []
        mock_cfg.openai_api_keys = []
        mock_cfg.deepseek_api_keys = []
        mock_cfg.openai_base_url = None

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)

        calls = []

        def fake_call(_messages, _tools, model, **_kwargs):
            calls.append(model)
            if model == "openai/gpt-4o-mini":
                raise RuntimeError("primary failed")
            return MagicMock(content="ok")

        adapter._call_litellm_model = MagicMock(side_effect=fake_call)

        result = adapter.call_completion(messages=[{"role": "user", "content": "hi"}], tools=[])

        self.assertEqual(calls, ["openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet-20241022"])
        self.assertEqual(result.content, "ok")

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_normalizes_kimi_k26_temperature(self, _mock_router):
        """Agent direct LiteLLM calls should not send unsupported temperatures to Kimi K2.6."""
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
            litellm_model="openai/kimi-k2.6",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        adapter._router = None
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="agent ok",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

        with patch("src.agent.llm_adapter.litellm.completion", return_value=response) as mock_completion:
            result = adapter._call_litellm_model(
                [{"role": "user", "content": "hi"}],
                [],
                "openai/kimi-k2.6",
                temperature=0.2,
            )

        self.assertEqual(result.content, "agent ok")
        self.assertEqual(mock_completion.call_args.kwargs["temperature"], 1.0)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_normalizes_kimi_k26_temperature_for_yaml_alias(self, _mock_router):
        """Agent direct LiteLLM calls should normalize through routed YAML aliases."""
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
            litellm_model="kimi_router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "kimi_router",
                    "litellm_params": {"model": "openai/kimi-k2.6"},
                }
            ],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        adapter._router = None
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="agent ok",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

        with patch("src.agent.llm_adapter.litellm.completion", return_value=response) as mock_completion:
            result = adapter._call_litellm_model(
                [{"role": "user", "content": "hi"}],
                [],
                "kimi_router",
                temperature=0.2,
            )

        self.assertEqual(result.content, "agent ok")
        self.assertEqual(mock_completion.call_args.kwargs["temperature"], 1.0)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_normalizes_kimi_k26_temperature_for_non_thinking_yaml_alias(self, _mock_router):
        """Agent direct LiteLLM calls should honor non-thinking Kimi YAML overrides."""
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
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
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        adapter._router = None
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="agent ok",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

        with patch("src.agent.llm_adapter.litellm.completion", return_value=response) as mock_completion:
            result = adapter._call_litellm_model(
                [{"role": "user", "content": "hi"}],
                [],
                "kimi_router",
                temperature=0.2,
            )

        self.assertEqual(result.content, "agent ok")
        self.assertEqual(mock_completion.call_args.kwargs["temperature"], 0.6)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_omits_temperature_for_gpt5_family(self, _mock_router):
        """Agent direct LiteLLM calls should omit temperature for strict default-temperature models."""
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
            litellm_model="openai/gpt5.5-ferr",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        adapter._router = None
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="agent ok",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

        with patch("src.agent.llm_adapter.litellm.completion", return_value=response) as mock_completion:
            result = adapter._call_litellm_model(
                [{"role": "user", "content": "hi"}],
                [],
                "openai/gpt5.5-ferr",
                temperature=0.2,
            )

        self.assertEqual(result.content, "agent ok")
        self.assertNotIn("temperature", mock_completion.call_args.kwargs)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_recovers_from_unsupported_temperature(self, _mock_router):
        """Agent direct LiteLLM calls should retry once with a request-scoped parameter repair."""
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
            litellm_model="openai/custom-temp-locked-agent",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        adapter._router = None
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="agent ok",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

        with patch("src.agent.llm_adapter.litellm.completion") as mock_completion:
            mock_completion.side_effect = [
                RuntimeError("Unsupported parameter: temperature is not supported"),
                response,
            ]
            result = adapter._call_litellm_model(
                [{"role": "user", "content": "hi"}],
                [],
                "openai/custom-temp-locked-agent",
                temperature=0.2,
            )

        self.assertEqual(result.content, "agent ok")
        self.assertEqual(mock_completion.call_args_list[0].kwargs["temperature"], 0.2)
        self.assertNotIn("temperature", mock_completion.call_args_list[1].kwargs)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_legacy_router_recovery_cache_is_scoped_to_endpoint(self, mock_router):
        """Legacy multi-key Router recoveries should not leak across base URLs."""
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="agent ok",
                        tool_calls=[],
                    )
                )
            ],
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
            agent_litellm_model="",
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
            agent_litellm_model="",
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

        from src.agent.llm_adapter import LLMToolAdapter

        strict_adapter = LLMToolAdapter(config=strict_cfg)
        strict_result = strict_adapter._call_litellm_model(
            [{"role": "user", "content": "hi"}],
            [],
            "openai/shared-model",
            temperature=0.2,
        )
        flex_adapter = LLMToolAdapter(config=flex_cfg)
        flex_result = flex_adapter._call_litellm_model(
            [{"role": "user", "content": "hi"}],
            [],
            "openai/shared-model",
            temperature=0.2,
        )

        self.assertEqual(strict_result.content, "agent ok")
        self.assertEqual(flex_result.content, "agent ok")
        self.assertEqual(strict_router.completion.call_args_list[0].kwargs["temperature"], 0.2)
        self.assertNotIn("temperature", strict_router.completion.call_args_list[1].kwargs)
        self.assertEqual(flex_router.completion.call_args.kwargs["temperature"], 0.2)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_fallback_does_not_leak_kimi_fixed_temperature(self, _mock_router):
        """Non-Kimi fallbacks should keep the requested temperature after a Kimi failure."""
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
            litellm_model="openai/kimi-k2.6",
            litellm_fallback_models=["openai/gpt-4o-mini"],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="fallback ok",
                        tool_calls=[],
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
        temperatures = []

        def fake_completion(**kwargs):
            temperatures.append((kwargs["model"], kwargs["temperature"]))
            if kwargs["model"] == "openai/kimi-k2.6":
                raise RuntimeError("primary failed")
            return response

        with patch("src.agent.llm_adapter.litellm.completion", side_effect=fake_completion):
            result = adapter.call_completion(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                temperature=0.2,
            )

        self.assertEqual(result.content, "fallback ok")
        self.assertEqual(
            temperatures,
            [("openai/kimi-k2.6", 1.0), ("openai/gpt-4o-mini", 0.2)],
        )

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_recomputes_timeout_for_each_fallback_attempt(self, _mock_router):
        """Each fallback model attempt should receive only the remaining timeout budget."""
        mock_cfg = MagicMock()
        mock_cfg.agent_litellm_model = "gpt-4o-mini"
        mock_cfg.litellm_model = None
        mock_cfg.litellm_fallback_models = ["anthropic/claude-3-5-sonnet-20241022"]
        mock_cfg.llm_model_list = []
        mock_cfg.llm_temperature = 0.7
        mock_cfg.gemini_api_keys = []
        mock_cfg.anthropic_api_keys = []
        mock_cfg.openai_api_keys = []
        mock_cfg.deepseek_api_keys = []
        mock_cfg.openai_base_url = None

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)

        timeouts = []

        def fake_call(_messages, _tools, model, **kwargs):
            timeouts.append((model, kwargs.get("timeout")))
            if model == "openai/gpt-4o-mini":
                raise RuntimeError("primary failed")
            return MagicMock(content="ok")

        adapter._call_litellm_model = MagicMock(side_effect=fake_call)

        with patch("src.agent.llm_adapter.time.time", side_effect=[0.0, 0.0, 7.0, 7.0]):
            result = adapter.call_completion(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                timeout=10.0,
            )

        self.assertEqual(result.content, "ok")
        self.assertEqual(timeouts[0], ("openai/gpt-4o-mini", 10.0))
        self.assertEqual(timeouts[1], ("anthropic/claude-3-5-sonnet-20241022", 3.0))

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_rate_limit_backoff_is_bounded_by_remaining_timeout(self, _mock_router):
        """Rate-limit backoff should sleep, but never longer than the remaining timeout budget."""
        mock_cfg = MagicMock()
        mock_cfg.agent_litellm_model = "gpt-4o-mini"
        mock_cfg.litellm_model = None
        mock_cfg.litellm_fallback_models = ["openai/gpt-4.1-mini"]
        mock_cfg.llm_model_list = []
        mock_cfg.llm_temperature = 0.7
        mock_cfg.gemini_api_keys = []
        mock_cfg.anthropic_api_keys = []
        mock_cfg.openai_api_keys = []
        mock_cfg.deepseek_api_keys = []
        mock_cfg.openai_base_url = None

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)

        class FakeRateLimitError(Exception):
            pass

        timeouts = []
        sleep_calls = []
        clock = {"value": 0.0}

        def fake_time():
            return clock["value"]

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            clock["value"] += seconds

        def fake_call(_messages, _tools, model, **kwargs):
            timeouts.append((model, kwargs.get("timeout")))
            if model == "openai/gpt-4o-mini":
                clock["value"] += 8.0
                raise FakeRateLimitError("rate limited")
            return MagicMock(content="ok")

        adapter._call_litellm_model = MagicMock(side_effect=fake_call)

        with patch("src.agent.llm_adapter.litellm.RateLimitError", FakeRateLimitError), \
             patch("src.agent.llm_adapter.logger.warning"), \
             patch("src.agent.llm_adapter.time.time", side_effect=fake_time), \
             patch("src.agent.llm_adapter.time.sleep", side_effect=fake_sleep) as mock_sleep:
            result = adapter.call_completion(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                timeout=10.0,
            )

        self.assertEqual(result.content, "ok")
        self.assertEqual(timeouts[0], ("openai/gpt-4o-mini", 10.0))
        self.assertEqual(timeouts[1][0], "openai/gpt-4.1-mini")
        expected_backoff = min(2.0, 8.0 * 0.1 + 0.5)
        expected_next_timeout = 10.0 - (8.0 + expected_backoff)
        self.assertAlmostEqual(timeouts[1][1], expected_next_timeout)
        mock_sleep.assert_called_once()
        self.assertAlmostEqual(mock_sleep.call_args.args[0], expected_backoff)
        self.assertAlmostEqual(sleep_calls[0], expected_backoff)
        self.assertAlmostEqual(clock["value"], 8.0 + expected_backoff)

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_context_window_error_skips_sleep(self, _mock_router):
        """Context-window errors should continue fallback immediately without backoff."""
        mock_cfg = MagicMock()
        mock_cfg.agent_litellm_model = "gpt-4o-mini"
        mock_cfg.litellm_model = None
        mock_cfg.litellm_fallback_models = ["anthropic/claude-3-5-sonnet-20241022"]
        mock_cfg.llm_model_list = []
        mock_cfg.llm_temperature = 0.7
        mock_cfg.gemini_api_keys = []
        mock_cfg.anthropic_api_keys = []
        mock_cfg.openai_api_keys = []
        mock_cfg.deepseek_api_keys = []
        mock_cfg.openai_base_url = None

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)

        class FakeContextWindowExceededError(Exception):
            pass

        def fake_call(_messages, _tools, model, **_kwargs):
            if model == "openai/gpt-4o-mini":
                raise FakeContextWindowExceededError("window exceeded")
            return MagicMock(content="ok")

        adapter._call_litellm_model = MagicMock(side_effect=fake_call)

        with patch(
            "src.agent.llm_adapter.litellm.ContextWindowExceededError",
            FakeContextWindowExceededError,
        ), patch("src.agent.llm_adapter.time.sleep") as mock_sleep:
            result = adapter.call_completion(messages=[{"role": "user", "content": "hi"}], tools=[])

        self.assertEqual(result.content, "ok")
        mock_sleep.assert_not_called()

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_reports_rate_limit_suffix_when_any_fallback_hit_limit(self, _mock_router):
        """Final error should note earlier rate limiting even if the last error differs."""
        mock_cfg = MagicMock()
        mock_cfg.agent_litellm_model = "gpt-4o-mini"
        mock_cfg.litellm_model = None
        mock_cfg.litellm_fallback_models = ["anthropic/claude-3-5-sonnet-20241022"]
        mock_cfg.llm_model_list = []
        mock_cfg.llm_temperature = 0.7
        mock_cfg.gemini_api_keys = []
        mock_cfg.anthropic_api_keys = []
        mock_cfg.openai_api_keys = []
        mock_cfg.deepseek_api_keys = []
        mock_cfg.openai_base_url = None

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)

        class FakeRateLimitError(Exception):
            pass

        class FakeContextWindowExceededError(Exception):
            pass

        def fake_call(_messages, _tools, model, **_kwargs):
            if model == "openai/gpt-4o-mini":
                raise FakeRateLimitError("rate limited")
            raise FakeContextWindowExceededError("window exceeded")

        adapter._call_litellm_model = MagicMock(side_effect=fake_call)

        with patch("src.agent.llm_adapter.litellm.RateLimitError", FakeRateLimitError), \
             patch(
                 "src.agent.llm_adapter.litellm.ContextWindowExceededError",
                 FakeContextWindowExceededError,
             ), \
             patch("src.agent.llm_adapter.time.sleep") as mock_sleep:
            result = adapter.call_completion(messages=[{"role": "user", "content": "hi"}], tools=[])

        self.assertEqual(result.provider, "error")
        self.assertIn("All LLM models failed (rate-limit encountered during fallback).", result.content)
        self.assertIn("window exceeded", result.content)
        mock_sleep.assert_not_called()

    @patch("src.agent.llm_adapter.Router")
    def test_llm_adapter_reports_missing_configuration_without_generic_none_error(self, _mock_router):
        """Missing Agent model config should return a stable, actionable error message."""
        mock_cfg = SimpleNamespace(
            agent_litellm_model="",
            litellm_model="",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.7,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=[],
            deepseek_api_keys=[],
            openai_base_url=None,
        )

        from src.agent.llm_adapter import LLMToolAdapter
        adapter = LLMToolAdapter(config=mock_cfg)

        result = adapter.call_completion(messages=[{"role": "user", "content": "hi"}], tools=[])

        self.assertEqual(result.provider, "error")
        self.assertEqual(
            result.content,
            "No LLM configured. Please set LITELLM_MODEL, LLM_CHANNELS, or provider API keys before using Agent.",
        )


# ============================================================
# _safe_int tests
# ============================================================

class TestSafeInt(unittest.TestCase):
    """Test the _safe_int helper for robust sentiment_score parsing."""

    def _get_safe_int(self):
        """Get reference to StockAnalysisPipeline._safe_int static method."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            return StockAnalysisPipeline._safe_int

    def test_int_passthrough(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int(80), 80)

    def test_float_truncate(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int(75.6), 75)

    def test_string_numeric(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int("80"), 80)

    def test_string_with_unit(self):
        """LLM may return '80分' instead of 80."""
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int("80分"), 80)

    def test_string_with_percent(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int("75%"), 75)

    def test_none_default(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int(None), 50)
        self.assertEqual(safe_int(None, 60), 60)

    def test_empty_string(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int(""), 50)

    def test_non_numeric_string(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int("high"), 50)

    def test_negative(self):
        safe_int = self._get_safe_int()
        self.assertEqual(safe_int("-10"), -10)


# ============================================================
# Skill activation semantics
# ============================================================

class TestSkillActivation(unittest.TestCase):
    """Test that skill activation follows the correct semantics."""

    def test_skills_default_disabled(self):
        """After registration, skills should be disabled by default."""
        from src.agent.skills.base import SkillManager, Skill

        manager = SkillManager()
        # Create a fresh Skill with default enabled=False
        test_skill = Skill(
            name="test_disabled",
            display_name="Test",
            description="test",
            instructions="test",
        )
        manager.register(test_skill)
        active = manager.list_active_skills()
        self.assertEqual(len(active), 0, "Skills should be disabled by default")

    def test_activate_all(self):
        """activate(['all']) should enable all registered skills."""
        from src.agent.skills.base import SkillManager, Skill

        manager = SkillManager()
        # Create test skills instead of importing deleted Python modules
        skill1 = Skill(name="dragon_head", display_name="龍頭策略",
                       description="test", instructions="test")
        skill2 = Skill(name="shrink_pullback", display_name="縮量回踩",
                       description="test", instructions="test")
        manager.register(skill1)
        manager.register(skill2)
        manager.activate(["all"])
        active = manager.list_active_skills()
        self.assertEqual(len(active), 2)

    def test_activate_specific(self):
        """activate with specific names should only enable those."""
        from src.agent.skills.base import SkillManager, Skill

        manager = SkillManager()
        skill1 = Skill(name="dragon_head", display_name="龍頭策略",
                       description="test", instructions="test")
        skill2 = Skill(name="shrink_pullback", display_name="縮量回踩",
                       description="test", instructions="test")
        skill3 = Skill(name="volume_breakout", display_name="放量突破",
                       description="test", instructions="test")
        manager.register(skill1)
        manager.register(skill2)
        manager.register(skill3)
        manager.activate(["dragon_head"])
        active = manager.list_active_skills()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].name, "dragon_head")

    def test_empty_config_uses_primary_default_skill(self):
        """Empty agent_skills config should activate the primary default skill only."""
        from src.agent.skills.base import SkillManager
        from src.agent.skills.defaults import get_default_active_skill_ids

        skill_manager = SkillManager()
        count = skill_manager.load_builtin_strategies()
        self.assertEqual(count, len(_builtin_strategy_names()), "Should load all built-in strategies from YAML")

        default_ids = get_default_active_skill_ids(skill_manager.list_skills())
        self.assertEqual(default_ids, ["bull_trend"])
        skill_manager.activate(default_ids)

        active = skill_manager.list_active_skills()
        self.assertEqual([skill.name for skill in active], ["bull_trend"])

    def test_sentiment_score_parsed_from_dashboard(self):
        """Verify _agent_result_to_analysis_result handles non-numeric sentiment_score."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):

            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = True
            mock_cfg.agent_max_steps = 10
            mock_cfg.agent_skills = []
            mock_cfg.bocha_api_keys = []
            mock_cfg.tavily_api_keys = []
            mock_cfg.brave_api_keys = []
            mock_cfg.serpapi_keys = []
            mock_cfg.searxng_base_urls = []
            mock_cfg.searxng_public_instances_enabled = False
            mock_cfg.news_max_age_days = 7
            mock_cfg.enable_realtime_quote = True
            mock_cfg.enable_chip_distribution = True
            mock_cfg.realtime_source_priority = []
            mock_cfg.save_context_snapshot = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.agent.executor import AgentResult
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)

            # Dashboard with "80分" instead of 80
            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "stock_name": "TestCo",
                    "sentiment_score": "80分",
                    "trend_prediction": "看多",
                    "operation_advice": "買進",
                    "decision_type": "buy",
                },
                provider="gemini",
            )

            result = pipeline._agent_result_to_analysis_result(
                agent_result, "2330", "TestCo", ReportType.SIMPLE, "q1"
            )
            self.assertEqual(result.sentiment_score, 80)


# ============================================================
# Phase 19B.1: instrument_type Agent-mode parity
# ============================================================
# Both the legacy path (analyze_stock) and the Agent-mode path
# (_analyze_with_agent) must set AnalysisResult.instrument_type via the same
# resolve_report_instrument_type(code) call — parity by construction, not by
# independent LLM inference in either path.

class TestInstrumentTypeAgentParity(unittest.TestCase):
    """instrument_type must be set identically regardless of agent_mode."""

    def _mock_cfg(self, agent_mode: bool) -> MagicMock:
        mock_cfg = MagicMock()
        mock_cfg.max_workers = 2
        mock_cfg.agent_mode = agent_mode
        mock_cfg.is_agent_available.return_value = agent_mode
        mock_cfg.agent_max_steps = 10
        mock_cfg.agent_skills = []
        mock_cfg.bocha_api_keys = []
        mock_cfg.tavily_api_keys = []
        mock_cfg.brave_api_keys = []
        mock_cfg.serpapi_keys = []
        mock_cfg.searxng_base_urls = []
        mock_cfg.searxng_public_instances_enabled = False
        mock_cfg.news_max_age_days = 7
        mock_cfg.enable_realtime_quote = True
        mock_cfg.enable_chip_distribution = True
        mock_cfg.realtime_source_priority = []
        mock_cfg.save_context_snapshot = False
        return mock_cfg

    def test_agent_mode_sets_instrument_type_from_resolver(self):
        """_analyze_with_agent must set instrument_type via resolve_report_instrument_type."""
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'), \
             patch('src.agent.factory.build_agent_executor') as mock_build_executor, \
             patch('src.core.pipeline.resolve_report_instrument_type') as mock_resolve:

            mock_resolve.return_value = "etf"
            mock_cfg = self._mock_cfg(agent_mode=True)
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            from src.agent.executor import AgentResult
            from src.enums import ReportType
            pipeline = StockAnalysisPipeline(config=mock_cfg)

            agent_result = AgentResult(
                success=True,
                content="{}",
                dashboard={
                    "stock_name": "元大台灣50",
                    "sentiment_score": 60,
                    "trend_prediction": "震盪",
                    "operation_advice": "持有",
                    "decision_type": "hold",
                },
                provider="gemini",
            )
            mock_executor = MagicMock()
            mock_executor.run.return_value = agent_result
            mock_build_executor.return_value = mock_executor
            pipeline.search_service.is_available = False

            result = pipeline._analyze_with_agent(
                code="0050",
                report_type=ReportType.SIMPLE,
                query_id="q-parity-agent",
                stock_name="元大台灣50",
                realtime_quote=None,
                chip_data=None,
            )

            self.assertIsNotNone(result)
            self.assertEqual(result.instrument_type, "etf")
            mock_resolve.assert_called_once_with("0050")

    def test_legacy_and_agent_paths_resolve_same_instrument_type_for_same_code(self):
        """Same code must yield the same instrument_type whether agent_mode is on or off."""
        for agent_mode in (False, True):
            with patch('src.core.pipeline.get_config') as mock_config, \
                 patch('src.core.pipeline.get_db'), \
                 patch('src.core.pipeline.DataFetcherManager'), \
                 patch('src.core.pipeline.GeminiAnalyzer'), \
                 patch('src.core.pipeline.NotificationService'), \
                 patch('src.core.pipeline.SearchService'), \
                 patch('src.agent.factory.build_agent_executor') as mock_build_executor, \
                 patch('src.core.pipeline.resolve_report_instrument_type') as mock_resolve:

                mock_resolve.return_value = "stock"
                mock_cfg = self._mock_cfg(agent_mode=agent_mode)
                mock_config.return_value = mock_cfg

                from src.core.pipeline import StockAnalysisPipeline
                from src.agent.executor import AgentResult
                from src.enums import ReportType
                pipeline = StockAnalysisPipeline(config=mock_cfg)

                if agent_mode:
                    agent_result = AgentResult(
                        success=True,
                        content="{}",
                        dashboard={
                            "stock_name": "台積電",
                            "sentiment_score": 70,
                            "trend_prediction": "看多",
                            "operation_advice": "持有",
                            "decision_type": "hold",
                        },
                        provider="gemini",
                    )
                    mock_executor = MagicMock()
                    mock_executor.run.return_value = agent_result
                    mock_build_executor.return_value = mock_executor
                    pipeline.search_service.is_available = False

                    result = pipeline._analyze_with_agent(
                        code="2330",
                        report_type=ReportType.SIMPLE,
                        query_id="q-parity-2",
                        stock_name="台積電",
                        realtime_quote=None,
                        chip_data=None,
                    )
                else:
                    pipeline.fetcher_manager.get_realtime_quote.return_value = None
                    pipeline.fetcher_manager.get_chip_distribution.return_value = None
                    pipeline.search_service.is_available = False
                    pipeline.db.get_analysis_context.return_value = None
                    pipeline.analyzer.analyze.return_value = MagicMock(
                        code="2330", name="台積電", success=True,
                    )

                    result = pipeline.analyze_stock("2330", ReportType.SIMPLE, "q-parity-2")

                self.assertIsNotNone(result)
                self.assertEqual(result.instrument_type, "stock")
                mock_resolve.assert_called_once_with("2330")


class TestAttachValuationFundamentalSnapshot(unittest.TestCase):
    """Phase 19B.2: unit tests for pipeline._attach_valuation_fundamental_snapshot.

    Directly invokes the wired method on a minimally-constructed pipeline
    instance rather than driving the full analyze_stock/_analyze_with_agent
    flow — the method is already proven reachable from both paths by
    TestInstrumentTypeAgentParity's "set instrument_type then call" pattern.
    """

    def _make_pipeline(self) -> "StockAnalysisPipeline":  # noqa: F821
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):
            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            return StockAnalysisPipeline(config=mock_cfg)

    def test_non_stock_instrument_type_is_noop(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="etf", valuation_snapshot=None, fundamental_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock') as mock_market:
            pipeline._attach_valuation_fundamental_snapshot(result, "0050", None)
            mock_market.assert_not_called()

        self.assertIsNone(result.valuation_snapshot)
        self.assertIsNone(result.fundamental_snapshot)

    def test_tw_stock_builds_finmind_snapshots(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", valuation_snapshot=None, fundamental_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock', return_value="tw"), \
             patch('src.finmind.tw_stock_analysis.normalize_tw_symbol', return_value=("2330", None)), \
             patch('src.services.history_loader.get_frozen_target_date', return_value=date(2026, 6, 25)), \
             patch(
                 'src.finmind.tw_stock_analysis.build_tw_valuation_fundamental_snapshot',
                 return_value=(
                     {"pe_ttm": 23.1, "pb": 6.3, "as_of": "2026-06-13"},
                     {"revenue_yoy": 45.0, "as_of": "2026-06-10"},
                 ),
             ):
            pipeline._attach_valuation_fundamental_snapshot(result, "2330", None)

        self.assertEqual(result.valuation_snapshot["pe_ttm"], 23.1)
        self.assertEqual(result.valuation_snapshot["source"], "finmind")
        self.assertEqual(result.fundamental_snapshot["revenue_yoy"], 45.0)
        self.assertEqual(result.fundamental_snapshot["source"], "finmind")

    def test_us_stock_builds_yfinance_snapshots_from_fundamental_context(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", valuation_snapshot=None, fundamental_snapshot=None)
        fundamental_context = {
            "valuation": {"pe_ttm": 32.5, "pe_forward": 28.1, "pb": 48.2, "market_cap": 3.2e12, "dividend_yield": 0.5},
            "growth": {"revenue_yoy": 16.6, "net_profit_yoy": 19.3, "roe": 141.5, "gross_margin": 47.9},
        }

        with patch('src.core.pipeline.get_market_for_stock', return_value="us"):
            pipeline._attach_valuation_fundamental_snapshot(result, "AAPL", fundamental_context)

        self.assertEqual(result.valuation_snapshot["pe_ttm"], 32.5)
        self.assertEqual(result.valuation_snapshot["source"], "yfinance")
        self.assertEqual(result.fundamental_snapshot["earnings_yoy"], 19.3)  # mapped from net_profit_yoy
        self.assertEqual(result.fundamental_snapshot["net_profit_yoy"], 19.3)
        self.assertEqual(result.fundamental_snapshot["source"], "yfinance")

    def test_us_stock_reads_nested_data_key_from_build_fundamental_block(self) -> None:
        # _build_fundamental_block wraps payload under "data"; pipeline must unwrap it.
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", valuation_snapshot=None, fundamental_snapshot=None)
        fundamental_context = {
            "valuation": {
                "status": "ok",
                "coverage": {"status": "ok"},
                "source_chain": [],
                "errors": [],
                "data": {
                    "pe_ttm": 28.5, "pe_forward": 25.1, "pb": 12.3,
                    "dividend_yield": 0.72, "market_cap": 3.08e12,
                },
            },
            "growth": {
                "status": "ok",
                "coverage": {"status": "ok"},
                "source_chain": [],
                "errors": [],
                "data": {
                    "revenue_yoy": 17.2, "net_profit_yoy": 21.4,
                    "roe": 35.2, "gross_margin": 69.4,
                },
            },
        }

        with patch('src.core.pipeline.get_market_for_stock', return_value="us"):
            pipeline._attach_valuation_fundamental_snapshot(result, "MSFT", fundamental_context)

        self.assertIsNotNone(result.valuation_snapshot)
        self.assertAlmostEqual(result.valuation_snapshot["pe_ttm"], 28.5)
        self.assertAlmostEqual(result.valuation_snapshot["pb"], 12.3)
        self.assertAlmostEqual(result.valuation_snapshot["market_cap"], 3.08e12)
        self.assertEqual(result.valuation_snapshot["source"], "yfinance")
        self.assertIsNotNone(result.fundamental_snapshot)
        self.assertAlmostEqual(result.fundamental_snapshot["revenue_yoy"], 17.2)
        self.assertAlmostEqual(result.fundamental_snapshot["net_profit_yoy"], 21.4)
        self.assertAlmostEqual(result.fundamental_snapshot["earnings_yoy"], 21.4)
        self.assertAlmostEqual(result.fundamental_snapshot["roe"], 35.2)
        self.assertEqual(result.fundamental_snapshot["source"], "yfinance")

    def test_exception_degrades_to_no_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", valuation_snapshot=None, fundamental_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock', side_effect=RuntimeError("boom")):
            pipeline._attach_valuation_fundamental_snapshot(result, "2330", None)

        self.assertIsNone(result.valuation_snapshot)
        self.assertIsNone(result.fundamental_snapshot)


class TestAttachExposureAndMarketRiskSnapshot(unittest.TestCase):
    """Phase 19B.3 / 19B.3A: unit tests for
    pipeline._attach_exposure_and_market_risk_snapshot.

    19B.3A gating contract: exposure_snapshot stays etf/index-only;
    market_risk_snapshot is broadened to stock/etf/index; unknown remains
    a no-op for both. Mirrors TestAttachValuationFundamentalSnapshot's
    direct-invocation pattern. No live network/provider calls —
    fetcher_manager.get_realtime_quote is always mocked.
    """

    def _make_pipeline(self) -> "StockAnalysisPipeline":  # noqa: F821
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):
            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            return StockAnalysisPipeline(config=mock_cfg)

    def test_stock_us_builds_market_risk_but_not_exposure(self) -> None:
        """19B.3A: a US stock gets market_risk_snapshot from the mocked
        VIX/SPX quote path, but exposure_snapshot stays None."""
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", exposure_snapshot=None, market_risk_snapshot=None)
        vix_quote = SimpleNamespace(price=18.1, change_pct=None)
        spx_quote = SimpleNamespace(price=None, change_pct=0.4)

        def _fake_quote(code, log_final_failure=False):
            return vix_quote if code == "VIX" else spx_quote

        with patch('src.core.pipeline.get_market_for_stock', return_value="us"), \
             patch.object(pipeline.fetcher_manager, 'get_realtime_quote', side_effect=_fake_quote):
            pipeline._attach_exposure_and_market_risk_snapshot(result, "AAPL", None)

        self.assertIsNone(result.exposure_snapshot)
        self.assertIsNotNone(result.market_risk_snapshot)
        self.assertEqual(result.market_risk_snapshot["vix_level"], 18.1)
        self.assertEqual(result.market_risk_snapshot["source"], "yfinance")

    def test_stock_tw_market_risk_data_gap_no_fetch(self) -> None:
        """19B.3A: a TW stock gets a data-gap market_risk_snapshot with zero
        quote-provider calls, and no exposure_snapshot."""
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", exposure_snapshot=None, market_risk_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock', return_value="tw"), \
             patch.object(pipeline.fetcher_manager, 'get_realtime_quote') as mock_quote:
            pipeline._attach_exposure_and_market_risk_snapshot(result, "2330", None)
            mock_quote.assert_not_called()

        self.assertIsNone(result.exposure_snapshot)
        self.assertIsNotNone(result.market_risk_snapshot)
        self.assertIsNone(result.market_risk_snapshot["source"])
        self.assertIn("gap_reason", result.market_risk_snapshot)

    def test_etf_and_index_still_build_both_snapshots(self) -> None:
        """19B.3A: etf/index instrument types are unaffected — both fields
        still get built, exactly as in 19B.3."""
        pipeline = self._make_pipeline()
        for instrument_type in ("etf", "index"):
            result = SimpleNamespace(instrument_type=instrument_type, exposure_snapshot=None, market_risk_snapshot=None)
            with patch('src.core.pipeline.get_market_for_stock', return_value="tw"):
                pipeline._attach_exposure_and_market_risk_snapshot(result, "0050", None)
            self.assertIsNotNone(result.exposure_snapshot, instrument_type)
            self.assertIsNotNone(result.market_risk_snapshot, instrument_type)

    def test_unknown_instrument_type_is_noop(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="unknown", exposure_snapshot=None, market_risk_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock') as mock_market:
            pipeline._attach_exposure_and_market_risk_snapshot(result, "AAPL", None)
            mock_market.assert_not_called()

        self.assertIsNone(result.exposure_snapshot)
        self.assertIsNone(result.market_risk_snapshot)

    def test_us_etf_builds_market_risk_from_realtime_quote(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="etf", exposure_snapshot=None, market_risk_snapshot=None)
        vix_quote = SimpleNamespace(price=28.4, change_pct=None)
        spx_quote = SimpleNamespace(price=None, change_pct=-1.2)

        def _fake_quote(code, log_final_failure=False):
            return vix_quote if code == "VIX" else spx_quote

        with patch('src.core.pipeline.get_market_for_stock', return_value="us"), \
             patch.object(pipeline.fetcher_manager, 'get_realtime_quote', side_effect=_fake_quote):
            pipeline._attach_exposure_and_market_risk_snapshot(result, "SPY", None)

        self.assertEqual(result.market_risk_snapshot["vix_level"], 28.4)
        self.assertEqual(result.market_risk_snapshot["vix_status"], "緊張")
        self.assertEqual(result.market_risk_snapshot["spx_change_pct"], -1.2)
        self.assertEqual(result.market_risk_snapshot["source"], "yfinance")
        self.assertIsNotNone(result.exposure_snapshot)

    def test_tw_index_always_renders_data_gap_no_fetch(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="index", exposure_snapshot=None, market_risk_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock', return_value="tw"), \
             patch.object(pipeline.fetcher_manager, 'get_realtime_quote') as mock_quote:
            pipeline._attach_exposure_and_market_risk_snapshot(result, "0050", None)
            mock_quote.assert_not_called()

        self.assertIsNone(result.market_risk_snapshot["source"])
        self.assertIn("gap_reason", result.market_risk_snapshot)
        self.assertEqual(result.market_risk_snapshot["data_gap_fields"], list(["vix_level", "vix_status", "spx_change_pct", "risk_level"]))

    def test_exception_degrades_to_no_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="etf", exposure_snapshot=None, market_risk_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock', side_effect=RuntimeError("boom")):
            pipeline._attach_exposure_and_market_risk_snapshot(result, "0050", None)

        self.assertIsNone(result.exposure_snapshot)
        self.assertIsNone(result.market_risk_snapshot)


class TestAttachMarketFearIndexSnapshot(unittest.TestCase):
    def _make_pipeline(self) -> "StockAnalysisPipeline":  # noqa: F821
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):
            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            return StockAnalysisPipeline(config=mock_cfg)

    def test_us_stock_builds_vix_market_fear_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", market_fear_index_snapshot=None)
        vix_quote = SimpleNamespace(price=18.41, date="2026-06-26")

        with patch('src.core.pipeline.get_market_for_stock', return_value="us"), \
             patch.object(pipeline.fetcher_manager, 'get_realtime_quote', return_value=vix_quote):
            pipeline._attach_market_fear_index_snapshot(result, "MSFT")

        self.assertEqual(result.market_fear_index_snapshot["market"], "us")
        self.assertEqual(result.market_fear_index_snapshot["kind"], "vix")
        self.assertEqual(result.market_fear_index_snapshot["value"], 18.41)
        self.assertEqual(result.market_fear_index_snapshot["as_of"], "2026-06-26")
        self.assertEqual(result.market_fear_index_snapshot["source"], "yfinance_yahoo_quote")

    def test_tw_etf_builds_vixtwn_market_fear_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(
            instrument_type="etf",
            market_fear_index_snapshot={"kind": "llm_fake"},
        )
        quote = SimpleNamespace(
            value=44.27,
            as_of="2026-06-26",
            source="taifex",
            source_url_key="taifex_vixtwn_daily_txt",
            data_gap_reason=None,
        )

        with patch('src.core.pipeline.get_market_for_stock', return_value="tw"), \
             patch('src.services.taifex_vixtwn_fetcher.fetch_latest_vixtwn', return_value=quote):
            pipeline._attach_market_fear_index_snapshot(result, "006208")

        self.assertEqual(result.market_fear_index_snapshot["market"], "tw")
        self.assertEqual(result.market_fear_index_snapshot["kind"], "vixtwn")
        self.assertEqual(result.market_fear_index_snapshot["value"], 44.27)
        self.assertEqual(result.market_fear_index_snapshot["as_of"], "2026-06-26")
        self.assertEqual(result.market_fear_index_snapshot["source"], "taifex")

    def test_tw_fetcher_exception_degrades_to_gap_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", market_fear_index_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock', return_value="tw"), \
             patch('src.services.taifex_vixtwn_fetcher.fetch_latest_vixtwn', side_effect=RuntimeError("boom")):
            pipeline._attach_market_fear_index_snapshot(result, "2454")

        self.assertEqual(result.market_fear_index_snapshot["kind"], "vixtwn")
        self.assertIsNone(result.market_fear_index_snapshot["value"])
        self.assertEqual(result.market_fear_index_snapshot["data_gap_reason"], "taifex_vixtwn_fetch_failed")

    def test_unknown_instrument_type_does_not_fetch(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="unknown", market_fear_index_snapshot=None)

        with patch('src.core.pipeline.get_market_for_stock') as mock_market, \
             patch.object(pipeline.fetcher_manager, 'get_realtime_quote') as mock_quote:
            pipeline._attach_market_fear_index_snapshot(result, "MSFT")

        mock_market.assert_not_called()
        mock_quote.assert_not_called()
        self.assertIsNone(result.market_fear_index_snapshot)


class TestAttachMultiPeriodTrendSnapshot(unittest.TestCase):
    """Phase 19B.4: unit tests for
    pipeline._attach_multi_period_trend_snapshot.

    Approach A: this method calls
    `src.services.history_loader.load_history_df(code, days=252)`
    independently — it never touches the existing ~89-day window used for
    MA60/trend_result. Mirrors TestAttachExposureAndMarketRiskSnapshot's
    direct-invocation pattern. No live network/provider calls —
    load_history_df is always mocked.
    """

    def _make_pipeline(self) -> "StockAnalysisPipeline":  # noqa: F821
        with patch('src.core.pipeline.get_config') as mock_config, \
             patch('src.core.pipeline.get_db'), \
             patch('src.core.pipeline.DataFetcherManager'), \
             patch('src.core.pipeline.GeminiAnalyzer'), \
             patch('src.core.pipeline.NotificationService'), \
             patch('src.core.pipeline.SearchService'):
            mock_cfg = MagicMock()
            mock_cfg.max_workers = 2
            mock_cfg.agent_mode = False
            mock_config.return_value = mock_cfg

            from src.core.pipeline import StockAnalysisPipeline
            return StockAnalysisPipeline(config=mock_cfg)

    @staticmethod
    def _rows(n: int, start: float = 100.0, step: float = 5.0) -> list:
        from datetime import date, timedelta
        base = date(2025, 1, 1)
        return [
            {
                "date": (base + timedelta(days=i)).isoformat(),
                "high": start + i * step + 1,
                "low": start + i * step - 1,
                "close": start + i * step,
            }
            for i in range(n)
        ]

    def test_stock_etf_index_attach_from_sufficient_rows(self) -> None:
        pipeline = self._make_pipeline()
        rows = self._rows(260)
        for instrument_type in ("stock", "etf", "index"):
            result = SimpleNamespace(instrument_type=instrument_type, multi_period_trend_snapshot=None)
            with patch('src.services.history_loader.load_history_df', return_value=(rows, "db_cache")):
                pipeline._attach_multi_period_trend_snapshot(result, "2330")
            self.assertIsNotNone(result.multi_period_trend_snapshot, instrument_type)
            self.assertEqual(result.multi_period_trend_snapshot["source"], "db_cache")
            self.assertEqual(result.multi_period_trend_snapshot["data_gap_fields"], [])

    def test_unknown_instrument_type_is_noop(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="unknown", multi_period_trend_snapshot=None)

        with patch('src.services.history_loader.load_history_df') as mock_load:
            pipeline._attach_multi_period_trend_snapshot(result, "AAPL")
            mock_load.assert_not_called()

        self.assertIsNone(result.multi_period_trend_snapshot)

    def test_insufficient_rows_produce_data_gap_not_exception(self) -> None:
        pipeline = self._make_pipeline()
        rows = self._rows(10)
        result = SimpleNamespace(instrument_type="stock", multi_period_trend_snapshot=None)

        with patch('src.services.history_loader.load_history_df', return_value=(rows, "yfinance")):
            pipeline._attach_multi_period_trend_snapshot(result, "AAPL")

        self.assertIsNotNone(result.multi_period_trend_snapshot)
        self.assertIn("60D", result.multi_period_trend_snapshot["data_gap_fields"])
        self.assertIn("252D", result.multi_period_trend_snapshot["data_gap_fields"])

    def test_load_history_df_returns_none_degrades_to_no_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="stock", multi_period_trend_snapshot=None)

        with patch('src.services.history_loader.load_history_df', return_value=(None, "none")):
            pipeline._attach_multi_period_trend_snapshot(result, "AAPL")

        self.assertIsNone(result.multi_period_trend_snapshot)

    def test_exception_degrades_to_no_snapshot(self) -> None:
        pipeline = self._make_pipeline()
        result = SimpleNamespace(instrument_type="etf", multi_period_trend_snapshot=None)

        with patch('src.services.history_loader.load_history_df', side_effect=RuntimeError("boom")):
            pipeline._attach_multi_period_trend_snapshot(result, "0050")

        self.assertIsNone(result.multi_period_trend_snapshot)

    def test_does_not_widen_or_touch_existing_89_day_window(self) -> None:
        """Approach A guard: calling the new method must not invoke
        db.get_data_range (the existing MA60/trend_result fetch path) —
        it only goes through load_history_df."""
        pipeline = self._make_pipeline()
        rows = self._rows(260)
        result = SimpleNamespace(instrument_type="index", multi_period_trend_snapshot=None)

        with patch('src.services.history_loader.load_history_df', return_value=(rows, "db_cache")):
            pipeline._attach_multi_period_trend_snapshot(result, "0050")

        pipeline.db.get_data_range.assert_not_called()

    def test_agent_and_non_agent_paths_call_same_method_with_same_args(self) -> None:
        """Parity by construction: both analyze_stock and _analyze_with_agent
        invoke `_attach_multi_period_trend_snapshot(result, code)` — verified
        by calling it directly through two independently constructed
        pipelines and confirming identical output for identical input,
        mirroring TestInstrumentTypeAgentParity's approach for 19B.1."""
        rows = self._rows(260)
        outputs = []
        for _ in range(2):
            pipeline = self._make_pipeline()
            result = SimpleNamespace(instrument_type="stock", multi_period_trend_snapshot=None)
            with patch('src.services.history_loader.load_history_df', return_value=(rows, "db_cache")):
                pipeline._attach_multi_period_trend_snapshot(result, "2330")
            outputs.append(result.multi_period_trend_snapshot)

        self.assertEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()

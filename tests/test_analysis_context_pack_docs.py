# -*- coding: utf-8 -*-
"""Contract checks for the AnalysisContextPack P0/P1 contract doc."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = PROJECT_ROOT / "docs" / "analysis-context-pack.md"
FULL_GUIDE_PATH = PROJECT_ROOT / "docs" / "full-guide.md"
FULL_GUIDE_EN_PATH = PROJECT_ROOT / "docs" / "full-guide_EN.md"


def _read_doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _section(doc: str, heading: str) -> str:
    marker = f"## {heading}"
    assert marker in doc
    return doc.split(marker, 1)[1].split("\n## ", 1)[0]


def test_analysis_context_pack_doc_has_required_sections() -> None:
    doc = _read_doc()

    for heading in (
        "## 術語與邊界",
        "## P0 範圍與非目標",
        "## P1 內部契約",
        "## P2 Builder 契約",
        "## P3 Runtime Consumption",
        "## P4 歷史記錄、任務狀態與 Web 可見性",
        "## P5 資料質量評分與 Prompt 資料限制",
        "## 欄位質量狀態",
        "## 現有狀態對映",
        "## 七路徑盤點",
        "## 原始碼錨點",
        "## 相容與安全邊界",
    ):
        assert heading in doc


def test_analysis_context_pack_doc_disambiguates_context_surfaces() -> None:
    section = _section(_read_doc(), "術語與邊界")

    for token in (
        "`storage.get_analysis_context()`",
        "`enhanced_context`",
        "`analysis_history.context_snapshot`",
        "Agent executor message context",
        "Agent orchestrator `AgentContext`",
        "`AGENT_ARCH=single`",
        "`AGENT_ARCH=multi`",
    ):
        assert token in section


def test_analysis_context_pack_doc_defines_p0_quality_states() -> None:
    section = _section(_read_doc(), "欄位質量狀態")

    for state in (
        "`available`",
        "`missing`",
        "`not_supported`",
        "`fallback`",
        "`stale`",
        "`estimated`",
        "`partial`",
        "`fetch_failed`",
    ):
        assert state in section
    assert "P0 先固定七詞" in section
    assert "P5 在同一 1.0 umbrella 內追加 `fetch_failed`" in section


def test_analysis_context_pack_doc_covers_seven_paths() -> None:
    section = _section(_read_doc(), "七路徑盤點")

    for heading in (
        "### 普通分析",
        "### Agent",
        "### 警告",
        "### 持股",
        "### 回測",
        "### 歷史",
        "### 通知",
    ):
        assert heading in section


def test_analysis_context_pack_doc_records_agent_context_visibility() -> None:
    section = _section(_read_doc(), "七路徑盤點")

    for token in (
        "`initial_context`",
        "`fundamental_context`",
        "不顯式注入 `fundamental_context` 或 `trend_result`",
        "pre-fetched data",
        "不預注入 `fundamental_context`",
    ):
        assert token in section


def test_analysis_context_pack_doc_records_non_goals_and_safety_boundaries() -> None:
    doc = _read_doc()

    for token in (
        "P1 已新增 `AnalysisContextPack` 內部 schema",
        "不新增 builder",
        "不接入 runtime",
        "不公開完整 pack",
        "不 pack 化 `market_review`",
        "`market_light`",
        "P5 已在同一 1.0 umbrella 內追加該狀態",
        "`analysis_history.context_snapshot.enhanced_context.date`",
        "完整 pack 不預設公開",
        "API key",
        "token",
        "cookie",
        "完整 webhook URL",
        "郵箱密碼",
    ):
        assert token in doc


def test_analysis_context_pack_doc_defines_p1_schema_contract() -> None:
    section = _section(_read_doc(), "P1 內部契約")

    for token in (
        "`src/schemas/analysis_context_pack.py`",
        "`PACK_VERSION = \"1.0\"`",
        "`ContextFieldStatus`",
        "`AnalysisSubject`",
        "`AnalysisContextItem`",
        "`AnalysisContextBlock`",
        "`DataQuality`",
        "`AnalysisContextPack`",
        "`MarketPhaseContext.to_dict()`",
    ):
        assert token in section


def test_analysis_context_pack_doc_records_p1_block_catalog() -> None:
    section = _section(_read_doc(), "P1 內部契約")

    for token in (
        "P1 Block Catalog",
        "`quote`",
        "`daily_bars`",
        "`technical`",
        "`fundamentals`",
        "`news`",
        "`portfolio`",
        "`chip` / `capital_flow`",
        "`events` / `market_context`",
        "不重複新增 `identity` block",
    ):
        assert token in section


def test_analysis_context_pack_doc_records_p1_time_and_status_semantics() -> None:
    section = _section(_read_doc(), "P1 內部契約")

    for token in (
        "`AnalysisContextPack.created_at` 使用 `datetime`",
        "`model_dump(mode=\"json\")` 輸出 ISO 8601",
        "`AnalysisContextItem.timestamp`",
        "`AnalysisContextBlock.timestamp`",
        "Optional[str]",
        "構造時校驗",
        "date-only",
        "`block.status` 表示整塊可用性",
        "`item.status` 表示欄位級質量",
        "不實現 `item.status` 到 `block.status` 的自動聚合推導",
    ):
        assert token in section


def test_analysis_context_pack_doc_records_p1_redaction_contract() -> None:
    section = _section(_read_doc(), "P1 內部契約")

    for token in (
        "`AnalysisContextPack.to_safe_dict()`",
        "`redact_sensitive_mapping()`",
        "`api_key`",
        "`access_token`",
        "`authorization_header`",
        "`webhook_url`",
        "`license_key`",
        "[REDACTED]",
        "`data_api`",
        "不掃描普通字串值",
        "不做 URL 正則脫敏",
    ):
        assert token in section


def test_analysis_context_pack_doc_keeps_later_phases_out_of_p1() -> None:
    section = _section(_read_doc(), "P1 內部契約")

    for token in (
        "不填充執行時資料",
        "不新增 fetcher",
        "不改變 Prompt",
        "不寫入 history/task/report metadata",
        "不把完整 pack 暴露到 API、Web、Bot、Desktop 或通知",
        "P2 builder",
        "P3 runtime",
    ):
        assert token in section


def test_analysis_context_pack_doc_defines_p2_builder_boundaries() -> None:
    section = _section(_read_doc(), "P2 Builder 契約")

    for token in (
        "`AnalysisContextBuilder`",
        "assembler",
        "pipeline 已 fetch",
        "zero-fetch",
        "`PipelineAnalysisArtifacts`",
        "`code`、`stock_name`、`market`",
        "`price_stale`",
        "`quote_stale`",
        "`intraday_realtime_overlay`",
        "`fetch_failed`",
        "P3 runtime",
        "不改變 Prompt",
        "不寫入 history/task/report metadata",
    ):
        assert token in section


def test_analysis_context_pack_docs_record_issue_1386_p3_quality_boundaries() -> None:
    section = _section(_read_doc(), "P2 Builder 契約")

    for token in (
        "`fetched_at`",
        "`provider_timestamp`",
        "`is_stale`",
        "`stale_seconds`",
        "`fallback_from`",
        "`STALE > FALLBACK > AVAILABLE`",
        "builder 只對映上游 artifact，不做質量評分",
        "`is_partial_bar`、`is_estimated`、`estimated_fields`",
        "`daily_bars` 不承載 partial/estimated",
    ):
        assert token in section

    full_guide = FULL_GUIDE_PATH.read_text(encoding="utf-8")
    full_guide_en = FULL_GUIDE_EN_PATH.read_text(encoding="utf-8")
    assert "盤中資料包與實時質量控制（Issue #1386 P3）" in full_guide
    assert "source` 保留實際成功的資料來源 token" in full_guide
    assert "`AnalysisContextBuilder` 只對映這些上游 artifact" in full_guide
    assert "daily_bars` block 仍表示 storage 中完整日線視窗" in full_guide
    assert "Intraday Data Packet and Realtime Quality Control (Issue #1386 P3)" in full_guide_en
    assert "source` keeps the actual successful provider token" in full_guide_en


def test_analysis_context_pack_doc_defines_p3_runtime_consumption_boundaries() -> None:
    section = _section(_read_doc(), "P3 Runtime Consumption")

    for token in (
        "`StockAnalysisPipeline` 是 summary 的唯一生產者",
        "`PipelineAnalysisArtifacts` -> `AnalysisContextBuilder.build()`",
        "`format_analysis_context_pack_prompt_section()`",
        "`analysis_context_pack_summary`",
        "基礎資訊 -> #1386 `market_phase_context` 渲染區塊 -> `analysis_context_pack_summary`",
        "`news.content`、`trend_result`、`chip`、`fundamental_context` 等原始 payload",
        "`AgentExecutor._build_user_message()`",
        "`AgentOrchestrator._build_context()`",
        "`ctx.meta[\"analysis_context_pack_summary\"]`",
        "禁止寫入 `ctx.data`",
        "`BaseAgent._build_messages()`",
        "`_inject_cached_data()`",
        "`news` block 為 `missing` 是當前 P3 的預期狀態",
        "`analysis_history.context_snapshot`",
        "`analysis_context_pack`",
        "`analysis_context_pack_summary`",
        "Agent 工具級 pack cache 複用",
        "P4 在此基礎上新增低敏 overview",
        "P5 繼續複用 summary 消費路徑",
    ):
        assert token in section

    assert "P3-min" not in section


def test_analysis_context_pack_doc_defines_p4_visibility_contract() -> None:
    section = _section(_read_doc(), "P4 歷史記錄、任務狀態與 Web 可見性")

    for token in (
        "`analysis_context_pack_overview`",
        "專用 renderer",
        "`AnalysisContextPack.to_safe_dict()`",
        "`report.details.analysis_context_pack_overview`",
        "`analysisContextPackOverview`",
        "`GET /api/v1/history/{record_id}`",
        "同步 `POST /api/v1/analysis/analyze`",
        "completed `GET /api/v1/analysis/status/{task_id}`",
        "`sanitize_context_snapshot_for_api()`",
        "`extract_analysis_context_pack_overview()`",
        "`items.value`",
        "`trend_result`",
        "`fundamental_context`",
        "`SAVE_CONTEXT_SNAPSHOT=false`",
        "`AnalysisContextSummary`",
        "位置在策略點位和資訊之後、執行診斷之前",
        "預設摺疊",
        "非零的其他狀態計數",
        "不覆蓋 pending/processing TaskPanel",
        "不改通知摘要",
        "質量分/等級",
        "`fetch_failed` 狀態",
    ):
        assert token in section

    assert "執行診斷之後、策略點位之前" not in section


def test_analysis_context_pack_doc_defines_p5_data_quality_contract() -> None:
    section = _section(_read_doc(), "P5 資料質量評分與 Prompt 資料限制")

    for token in (
        "`PACK_VERSION`",
        "`fetch_failed`",
        "`fundamental_context.status == \"failed\"`",
        "`overall_score`",
        "`level`",
        "`block_scores`",
        "`limitations`",
        "`quote=25`",
        "`fetch_failed=25`",
        "`Data Limitations`",
        "`confidence_level` 不得為 `高` / `High`",
        "`phase × degraded data`",
        "fail-open",
        "不替代 P5 的 confidence/safety 規則",
        "`analysis_context_pack_overview.data_quality`",
        "`details.context_snapshot`",
        "不新增 fetcher",
        "不改變 LLM 輸出 JSON schema",
        "`dashboard.phase_decision`",
    ):
        assert token in section


def test_analysis_context_pack_doc_maps_existing_status_terms() -> None:
    section = _section(_read_doc(), "現有狀態對映")

    for token in (
        "`degraded`",
        "`insufficient_data`",
        "`partial_failed`",
        "`data_missing`",
        "`price_stale`",
        "`data_quality=ok/partial/unavailable`",
        "不對映",
    ):
        assert token in section


def test_analysis_context_pack_doc_lists_source_anchors() -> None:
    section = _section(_read_doc(), "原始碼錨點")

    for path in (
        "src/core/pipeline.py",
        "src/storage.py",
        "src/analyzer.py",
        "src/agent/orchestrator.py",
        "src/agent/executor.py",
        "src/agent/tools/data_tools.py",
        "src/services/alert_worker.py",
        "src/services/portfolio_service.py",
        "src/services/backtest_service.py",
        "src/repositories/backtest_repo.py",
        "src/services/history_service.py",
        "api/v1/endpoints/history.py",
        "api/v1/endpoints/analysis.py",
        "api/v1/schemas/history.py",
        "api/v1/schemas/portfolio.py",
        "src/notification.py",
        "docs/alerts.md",
        "docs/notifications.md",
    ):
        assert path in section


def test_analysis_context_pack_doc_updates_indexes_and_changelog() -> None:
    index = (PROJECT_ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    index_en = (PROJECT_ROOT / "docs" / "INDEX_EN.md").read_text(encoding="utf-8")
    changelog = (PROJECT_ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "[分析上下文包契約、執行態消費與可見性](analysis-context-pack.md)" in index
    assert "P1/P2 內部契約、P3 Prompt 摘要消費、P4 歷史/API/Web 低敏可見性、P5 資料質量評分" in index
    assert (
        "[Analysis Context Pack Contract, Runtime Consumption, And Visibility](analysis-context-pack.md) "
        "<sub><sub>![P5 Badge](https://img.shields.io/badge/P5-orange?style=flat)</sub></sub> "
        "(Chinese-only)"
    ) in index_en
    assert "P1/P2 internal contracts, P3 prompt-summary consumption, P4 history/API/Web low-sensitivity visibility, P5 data-quality scoring" in index_en
    assert "新增 AnalysisContextPack P0 上下文盤點" in changelog
    assert "新增 AnalysisContextPack P1 內部契約與脫敏序列化測試" in changelog
    assert "新增 AnalysisContextPack P2 builder" in changelog
    assert "普通分析與 Agent 執行時 Prompt 接入 AnalysisContextPack 低敏摘要" in changelog
    assert "AnalysisContextPack P4 低敏 overview 接入歷史詳情" in changelog
    assert "AnalysisContextPack P5 增加資料質量評分" in changelog
    assert "#1386 P5 為個股分析報告新增 `dashboard.phase_decision`" in changelog
    assert "最佳化 Web 報告詳情頁資訊層級" in changelog


def test_full_guides_clarify_pack_summary_does_not_replace_legacy_payload_channels() -> None:
    guide = (PROJECT_ROOT / "docs" / "full-guide.md").read_text(encoding="utf-8")
    guide_en = (PROJECT_ROOT / "docs" / "full-guide_EN.md").read_text(encoding="utf-8")

    assert "在這個新增的 pack 摘要區塊中" in guide
    assert "不會透過該區塊看到完整 `news.content`" in guide
    assert "既有 `news_context`、Agent pre-fetched JSON 和 `enhanced_context` 原始資料通道保持 P3 前行為" in guide
    assert "`report.details.analysis_context_pack_overview`" in guide
    assert "completed `/api/v1/analysis/status/{task_id}`" in guide
    assert "Web 端報告頁在“策略點位”和“資訊”之後展示預設摺疊的資料塊摘要" in guide
    assert "摺疊頭部展示可用數、缺失數、非零的其他狀態計數和觸發來源" in guide
    assert "Web 報告頁在策略點位和資訊之後預設摺疊展示資料塊狀態" in guide
    assert "`details.context_snapshot` 會剝離頂層 `analysis_context_pack_overview`" in guide
    assert "AnalysisContextPack 資料質量評分與 Prompt 資料限制（Issue #1389 P5）" in guide
    assert "盤中決策護欄與質量校驗（Issue #1386 P5）" in guide
    assert "`dashboard.phase_decision`" in guide
    assert "`fetch_failed`" in guide
    assert "摺疊頭部新增質量分/等級" in guide
    assert "`report.meta.market_phase_summary`" in guide
    assert "`details.context_snapshot` 會剝離頂層 `market_phase_summary`" in guide

    assert "in this new pack-summary section" in guide_en
    assert "not full `news.content`" in guide_en
    assert "Existing `news_context`, Agent pre-fetched JSON, and `enhanced_context` raw-payload channels keep their pre-P3 behavior" in guide_en
    assert "`report.details.analysis_context_pack_overview`" in guide_en
    assert "completed `/api/v1/analysis/status/{task_id}`" in guide_en
    assert "the Web report page renders a collapsed data-block summary after Strategy and News" in guide_en
    assert "available/missing counts, non-zero other status counts, and trigger source" in guide_en
    assert "the Web report page shows the data-block summary collapsed after Strategy and News" in guide_en
    assert "API `details.context_snapshot` strips the top-level `analysis_context_pack_overview`" in guide_en
    assert "AnalysisContextPack Data Quality Scoring and Prompt Limitations (Issue #1389 P5)" in guide_en
    assert "Intraday Decision Guardrails and Quality Checks (Issue #1386 P5)" in guide_en
    assert "`dashboard.phase_decision`" in guide_en
    assert "`fetch_failed`" in guide_en
    assert "adds quality score/level to the header" in guide_en
    assert "`report.meta.market_phase_summary`" in guide_en
    assert "API `details.context_snapshot` strips the top-level `market_phase_summary`" in guide_en

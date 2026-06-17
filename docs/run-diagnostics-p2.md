# 執行診斷與資料可靠性 1.0（Phase 2）

本文件記錄 #1391 Phase 2 的後端落地範圍：基於 Phase 1 的 `trace_id` 與 provider run 記錄，生成使用者可讀的執行診斷摘要，並提供可複製的脫敏排障文字。

## 本輪範圍

- 新增 `RunDiagnosticSummary` 聚合邏輯，輸出總體狀態：
  - `normal` / 正常
  - `degraded` / 部分降級
  - `failed` / 失敗
  - `unknown` / 未知
- 摘要覆蓋以下關鍵鏈路：
  - 實時行情
  - 日線資料
  - 新聞搜尋
  - LLM
  - 通知
  - 歷史儲存
- `AnalysisService` 同步/非同步任務結果追加可選 `diagnostic_summary`。
- 新增歷史報告診斷 API：

```http
GET /api/v1/history/{record_id}/diagnostics
```

`record_id` 支援歷史記錄主鍵 ID 或 `query_id`，返回診斷摘要與 `copy_text`。

## 複製排障資訊

`copy_text` 是面向 issue/排障的純文字，包含：

- `trace_id`
- `query_id`
- `stock_code`
- `trigger_source`
- 總體 `data_status`
- 實時行情、日線、新聞、LLM、通知、歷史儲存的簡短狀態
- 首要原因

生成前會複用執行診斷脫敏規則，避免輸出 token、API key、Authorization、Cookie、webhook URL、郵箱密碼、代理憑據等敏感資訊。

## 相容性邊界

- 本輪不新增配置項，不改變資料來源優先順序，不改變 fallback 策略。
- 本輪不改變任何 LLM/provider/Base URL/配置遷移語義，僅新增歷史快照中的診斷欄位與查詢介面。
- API 只追加可選欄位和新增只讀介面；舊客戶端可忽略。
- 舊報告沒有 `context_snapshot.diagnostics` 時返回 `unknown`，不報錯。
- 通知診斷在當前任務上下文中記錄；歷史報告如果儲存時尚無通知證據，會在摘要中顯示通知結果未知。
- 診斷摘要生成失敗不得影響報告讀取或分析主流程。

### 結構化檢測警告澄清

- 自動化檢測命中的“模型/provider/base URL 相容風險”來源是：`src/agent/factory.py` 新增了 `agent_max_steps` 與 `agent_orchestrator_timeout_s` 的 **數字安全兜底**（`_coerce_config_int`），因此掃描可能將其誤識別為配置敏感路徑；該命中屬於測試與路由保護觸發，不是執行時配置或相容語義變更。
- 當數值配置存在非法值時，系統會記錄 `warning` 到 `src.agent.factory` 日誌（示例：`[AgentFactory] Invalid value for agent_max_steps...`），並回退到預設值；日誌用於定位“引數未生效”類問題，與模型/provider/base URL 相容性獨立。
- 本輪確認無靜默遷移/清空/改寫：
  - `src/core/pipeline.py` 與 `src/services/analysis_service.py` 僅新增診斷記錄，不修改 `Config` 中任何 `litellm_model`、`agent_litellm_model`、`openai_base_url` 或 channel `LLM_*` 欄位。
  - `src/agent/factory.py` 的 `_coerce_config_int` 只在構建執行引數時計算 `max_steps` 與 `timeout_seconds`，並且不寫回到 `config` 物件；`litellm_model`、`agent_litellm_model`、`openai_base_url` 原值在構造鏈路中完整透傳。
  - 本輪不觸發 `Config` 的執行時清理、持久化回寫或遷移流程，因此不存在寫回導致執行時配置被重寫的風險。
- 迴歸驗證：`tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_does_not_mutate_llm_route_config` 與 `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_multi_arch_does_not_mutate_llm_route_config` 明確斷言上述欄位在 `build_agent_executor` 後保持原值。
- 回退路徑：如需恢復到舊行為，移除本輪相關提交；或將 `diag_*` 欄位從 `context_snapshot`/`RunDiagnosticSummary` 的反序列化鏈路中移除。主鏈路與模型/provider 配置無需額外遷移或修復。

## 驗證建議

```bash
python -m pytest tests/test_run_diagnostics_p2.py tests/test_run_diagnostics_p1.py
python -m py_compile src/services/run_diagnostics.py src/services/history_service.py api/v1/endpoints/history.py api/v1/schemas/history.py
```

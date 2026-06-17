# 執行診斷與資料可靠性 1.0（Phase 1）

本文件記錄 #1391 Phase 1 的最小執行時落地範圍：統一 `trace_id`，併為首批關鍵資料鏈路記錄結構化 provider 嘗試。

## 本輪範圍

- API / Web 非同步任務建立時，`TaskInfo` 使用 `task_id` 作為預設 `trace_id`。
- 任務列表、任務狀態與 SSE 事件追加 `trace_id` 欄位；舊客戶端可忽略該欄位。
- 同步分析使用本次 `query_id` 作為預設 `trace_id`。
- pipeline 執行時建立輕量診斷上下文，貫穿日線準備與單股分析。
- `data_provider/base.py` 對以下鏈路記錄 `ProviderRun` 風格事件：
  - `daily_data`
  - `realtime_quote`
- 診斷記錄寫入記憶體上下文，隨分析 `context_snapshot.diagnostics` 儲存；舊歷史記錄缺少該欄位時保持相容。

## `ProviderRun` 欄位

首版欄位保持最小：

- `trace_id`
- `data_type`
- `provider`
- `operation`
- `success`
- `latency_ms`
- `error_type`
- `error_message_sanitized`
- `fallback_to`
- `record_count`
- `created_at`

錯誤摘要會做基礎脫敏，避免輸出 token、API key、Authorization、Cookie、包含敏感引數的 webhook URL 等內容。

## 穩定性邊界

- 診斷記錄失敗只記錄 warning，不影響主分析、資料來源 fallback 或歷史儲存。
- 本輪不新增配置項，不改變資料來源優先順序，不改變 fallback 策略。
- 本輪不新增 Web 展示元件；`trace_id` 和 provider runs 先進入 API/SSE/歷史快照，供後續 Phase 2/3 聚合與展示覆用。

## 驗證建議

```bash
python -m pytest tests/test_run_diagnostics_p1.py tests/test_analysis_api_contract.py::AnalysisApiContractTestCase::test_get_analysis_status_normalizes_completed_queue_result_contract
python -m py_compile src/services/run_diagnostics.py src/services/task_queue.py src/services/analysis_service.py src/core/pipeline.py data_provider/base.py api/v1/schemas/analysis.py api/v1/endpoints/analysis.py
```

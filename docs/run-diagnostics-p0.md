# 執行診斷與資料可靠性 1.0（Phase 0）

本文件定義 #1391 的 **Phase 0（P0）**：在不引入新頁面、不改變全域性分析策略與 fallback 核心語義前提下，收斂契約邊界並限定本輪執行時修復範圍。

## 目標

- 給後續實現提供統一術語：`trace_id`、關鍵鏈路記錄、診斷摘要、脫敏排障資訊。
- 明確第一階段範圍，避免把需求擴成“完整可觀測平臺”。
- 固化 fail-open、安全與 retention 基線，降低迴歸風險。

## 當前文件範圍（本輪）

- 本檔案為 Phase 0 合同與驗收邊界文件，當前 PR 為 docs + runtime fix，本輪同步補齊 `baostock_fetcher.py`、`pytdx_fetcher.py`、`tushare_fetcher.py` 的 A 股程式碼歸屬邊界，並配套由 `tests/test_a_share_fetcher_code_conversion.py` 做迴歸驗證。
- 歸屬邊界必須覆蓋裸碼與字首碼（如 `000001`、`000001.SZ`、`SH000001`、`SH.000001`、`SZ000001`、`SZ.000001`），避免把 SH/SZ 字首語義誤歸類。
- 若無新增 LLM 相關 provider/model/Base URL 語義遷移需求，本輪收斂 Tushare A 股歸屬範圍至：`600/601/603/605/688`、`000/001/002/003/300/301`，並同步迴歸 `605`、`001`、`003`、`301` 場景；該範圍變更不視為 provider 配置/路由策略擴充套件。

## 非目標

- 不做 OpenTelemetry / APM / Grafana 風格監控系統。
- 不在首版展示 p95、全量 Provider 呼叫明細、完整運維面板。
- 不改變現有資料來源優先順序、分析策略、通知策略。
- 不變更 LLM provider 列表、Base URL、`llm_call` 執行時引數、`REPORT_*` 配置語義與遷移路徑；本輪改動限定在 A 股程式碼歸屬解析與診斷欄位邊界。

### 驗收邊界（本輪）

- 本輪為 `fix`（docs + runtime fix），變更僅收斂 A 股程式碼歸屬語義，不改 provider 列表、Base URL、`llm_call` 執行時語義與 `REPORT_*` 配置遷移路徑。
- `data_provider/baostock_fetcher.py`、`data_provider/pytdx_fetcher.py`、`data_provider/tushare_fetcher.py` 本輪只處理：
  - 裸碼與字尾碼：`000001`、`000001.SH`、`000001.SZ`
  - 字首碼：`SH000001`、`SH.000001`、`SZ000001`、`SZ.000001`
- `SH000001`/`SH.000001`/`SZ000001`/`SZ.000001` 場景為 correctness blocker，需由 `tests/test_a_share_fetcher_code_conversion.py` 覆蓋迴歸。
- 迴歸最小口徑為 `python -m pytest tests/test_a_share_fetcher_code_conversion.py` 與 `./scripts/ci_gate.sh`，並在 PR 描述同步結果與阻塞。
- 回滾優先順序為恢復本輪三檔案變更到合併前提交；其餘範圍不應一併回退。

## 術語與契約（P0 草案）

### 1) `trace_id`

- 含義：一次分析執行鏈路的統一關聯 ID。
- 要求：
  - 每次分析任務僅有一個 `trace_id`。
  - 可由入口生成，或由已有任務 ID 對映（例如 Web 任務）。
  - 出現在日誌/結構化診斷中用於排障關聯。

### 2) `RunDiagnosticSummary`

- 含義：給使用者看的簡短執行診斷摘要。
- 建議欄位（首版保持最小）：
  - `trace_id`
  - `status`：`ok` / `degraded` / `failed`
  - `data_status`：關鍵資料路徑是否降級
  - `notify_status`：通知結果摘要
  - `error_hint`：脫敏後的簡要原因
- 說明：這是使用者可感知能力，不等於內部全量事件日誌。

### 3) 關鍵鏈路記錄（最小集合）

首版只要求記錄以下關鍵節點結果（成功/失敗/降級 + 簡短原因）：

- `realtime_quote`
- `daily_data`
- `llm_call`
- `report_persist`
- `notification_dispatch`

> 說明：`news`、`fundamental`、`capital_flow` 等放到後續擴充套件，不作為首版阻斷項。

## 安全與穩定性邊界（P0 必須遵守）

### Fail-open

- 診斷記錄失敗不應阻斷主分析流程。
- 即使診斷寫入失敗，也必須繼續產出分析結果（除非主流程本身失敗）。

### 脫敏

- 複製排障資訊中禁止包含金鑰、token、完整 webhook URL、使用者賬號標識。
- 錯誤文案輸出以摘要為主，避免洩露第三方返回的敏感原文。

### Retention

- 診斷資料保留週期應可配置或可統一清理。
- 預設策略優先保守（例如僅保留必要時間窗），避免無限增長。

### 相容性

- 新欄位應優先追加，不破壞現有 API / Web / Desktop 讀取路徑。
- 舊歷史記錄缺少新欄位時應可安全回退。

## Phase 0 交付清單

- [x] 明確目標/非目標，防止範圍失控。
- [x] 定義 `trace_id` 與 `RunDiagnosticSummary` 最小契約。
- [x] 明確首版關鍵鏈路覆蓋範圍。
- [x] 固化 fail-open、脫敏、retention、相容性基線。

## 後續階段（僅說明，不在 P0 實現）

- Phase 1：`trace_id` 貫通與關鍵鏈路最小記錄落地。
- Phase 2：生成並持久化 `RunDiagnosticSummary`，支援複製脫敏排障資訊。
- Phase 3：Web 側最小展示（預設摺疊），並補齊文件和回滾說明。

# 執行診斷與資料可靠性 1.0（Phase 3）

本文件記錄 #1391 Phase 3 的交付範圍：在不新增配置的前提下，補齊執行診斷可見性並將歷史排障資訊回填到後端上下文快照，便於自部署環境快速定位異常。

## 本輪範圍

- 歷史報告詳情新增預設摺疊的「執行診斷 / 資料可靠性」區域；#1523 後 Web 展示標題調整為「執行診斷 / 執行狀態」，歷史階段標題不變。
- 任務面板對進行中任務展示預設摺疊的 trace 資訊，便於和後端日誌、SSE、歷史報告診斷串聯。
- 歷史報告透過只讀介面拉取診斷摘要：

```http
GET /api/v1/history/{record_id}/diagnostics
```

- 同步分析響應若已經帶有 `diagnostic_summary`，前端可直接展示，不額外請求歷史介面。
- 診斷面板支援複製後端生成的脫敏 `copy_text`，用於 issue 或部署排障。
- 分析鏈路在儲存歷史後會補齊任務/Provider/LLM/通知診斷到 `context_snapshot.diagnostics`，歷史診斷介面統一聚合為使用者可讀摘要。

## 狀態文案

總體狀態：

- `normal`：正常
- `degraded`：部分降級
- `failed`：失敗
- `unknown`：未知

元件狀態：

- `ok`：正常
- `degraded`：最近失敗後已降級
- `failed`：失敗
- `unknown`：未知
- `not_configured`：未配置
- `skipped`：已跳過

## 互動邊界

- 診斷區域預設摺疊，避免擠佔報告主要內容。
- 首屏只展示總體狀態、首要原因和必要 trace 資訊。
- 元件狀態與高階 JSON 欄位放在展開區域內；高階欄位再二級摺疊，避免資訊過載。
- 舊報告、介面失敗或證據不足時顯示 `unknown`，不影響報告閱讀。

## 相容性邊界

- 本輪不新增 `.env` 配置項，不修改資料庫結構，不引入資料遷移。
- Web 只消費 Phase 1/2 已追加的可選欄位和只讀診斷介面；後端補齊 `src/core/pipeline.py`、`src/services/run_diagnostics.py`、`src/storage.py` 與 `src/services/history_service.py` 的診斷持久化與重新整理邏輯，並透過 `api/v1/endpoints/history.py` 提供可讀端點。
- 後端變更範圍包含任務編排、歷史儲存後補寫、歷史診斷查詢與通知結果診斷記錄；這些鏈路只追加 `context_snapshot.diagnostics` 診斷快照和摘要，不改變分析主流程、通知傳送成敗語義或歷史報告主體欄位。
- 複製文字由後端生成並脫敏；前端只負責展示和複製。
- Desktop 複用 Web 構建產物，未單獨改動 Electron 主程序或打包指令碼。
- 執行時配置/模型/provider/base_url 相容語義不調整：除診斷持久化鏈路外，不改 provider 優先順序、LiteLLM 路由、執行時清理與配置回退邏輯。
- 舊歷史與舊配置相容規則不變：歷史診斷查詢新增可選欄位不影響既有歷史查詢響應解析；回退方式為移除本輪展示與相關前端查詢路徑，或按現有指南恢復模型和配置。
- 回滾策略：優先回退前端展示與查詢入口；若需完全隔離新增鏈路，可回滾本輪 PR（回退後保留歷史記錄原有響應，新增診斷端點不再在 Web 中展示）。

### 結構化檢測澄清

本輪 review 的結構化檢測命中了外部模型/API 相容和執行時配置遷移風險；複核後結論如下：

- 模型名/provider/Base URL：本輪不新增、不替換、不重排任何模型名、provider、Base URL、channel 或 fallback 預設值，也不改變 `LITELLM_MODEL`、`AGENT_LITELLM_MODEL`、`VISION_MODEL`、`LITELLM_FALLBACK_MODELS`、`OPENAI_*`、`GEMINI_*`、`ANTHROPIC_*`、`DEEPSEEK_*` 的解析優先順序。
- SDK/依賴預設值：本輪不修改 `requirements.txt`、`package.json` 依賴約束或 LiteLLM/OpenAI-compatible 呼叫預設引數；外部來源仍以 `docs/llm-providers.md` 和 `docs/LLM_CONFIG_GUIDE*.md` 中已記錄的官方文件與當前鎖定依賴說明為準。
- 儲存前清理/配置遷移：本輪不觸發 `.env`、Web 設定頁 channel、桌面端使用者資料目錄、Docker 執行時配置檔案或歷史舊配置的遷移、清理、刪除、回寫策略變更。
- 本輪實際執行時改動只把既有分析 trace、provider/LLM/通知結果和脫敏錯誤摘要寫入 `context_snapshot.diagnostics`，並透過歷史只讀介面和 Web 預設摺疊面板展示；診斷記錄失敗按 fail-open 處理，不改變分析或通知的成功/失敗判定。
- 因此本次屬於結構化檢測誤報/文件澄清；無新增官方來源、舊配置遷移步驟或 provider 回退路徑需要執行。若需回退，按本節回滾策略移除診斷展示/查詢入口即可，模型與執行時配置恢復路徑不變。

## 相容性迴歸與驗證（PR 合併前關鍵證據）

- 後端迴歸覆蓋：
  - `tests/test_pipeline_market_phase_context.py`
  - `tests/test_realtime_types.py`
  - `tests/test_scheduler_background.py`
  - `tests/test_analysis_api_contract.py`（子集：診斷上下文入出參/狀態查詢契約）
  - `tests/test_analysis_history.py`（子集：歷史 API 與持久化鏈路）
- 覆蓋關係：API 合約由 `tests/test_analysis_api_contract.py` 與 `tests/test_analysis_history.py` 覆蓋；任務編排、歷史儲存和 `context_snapshot.diagnostics` 由 `tests/test_pipeline_market_phase_context.py` 覆蓋；通知路徑透過 `./scripts/ci_gate.sh` 中的既有通知迴歸與匯入檢查兜底。
- 迴歸命令（PR 合併前至少確認全部透過）：

```bash
./scripts/ci_gate.sh
python -m pytest tests/test_realtime_types.py tests/test_scheduler_background.py tests/test_pipeline_market_phase_context.py tests/test_analysis_api_contract.py tests/test_analysis_history.py
cd apps/dsa-web && npm run lint && npm run build
```

## 驗證建議

```bash
cd apps/dsa-web
npm run lint
npm run build
```

可補充執行（非阻斷）：

```bash
cd apps/dsa-web
npm test -- --run src/components/report/__tests__/ReportDiagnostics.test.tsx src/components/tasks/__tests__/TaskPanel.test.tsx src/hooks/__tests__/useTaskStream.test.tsx
```

可補充確定性指令碼校驗：

```bash
python -m py_compile api/v1/endpoints/analysis.py api/v1/endpoints/history.py api/v1/schemas/analysis.py api/v1/schemas/history.py src/core/pipeline.py src/services/run_diagnostics.py src/storage.py
```

## 回滾

最小回滾方式：revert Phase 3 PR。由於本輪為可選欄位與可讀介面增強，回滾後後端歷史快照與已落庫資料保留，Web 不再展示診斷面板與 trace 診斷入口。

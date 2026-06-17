# AlphaSift 選股整合說明

AlphaSift 作為第三方選股能力接入 DSA。DSA 預設不啟用它，也不把 AlphaSift 的策略邏輯複製進主倉庫；啟用後只透過 `alphasift.dsa_adapter` 穩定適配層呼叫 AlphaSift。

## 當前方案

- 預設關閉：`ALPHASIFT_ENABLED=false`。
- 啟用入口：設定頁或選股頁點選開啟，或在 `.env` 中配置 `ALPHASIFT_ENABLED=true`。
- 安裝來源：預設固定到已驗證的 AlphaSift 適配層 commit：`ALPHASIFT_INSTALL_SPEC=git+https://github.com/ZhuLinsen/alphasift.git@b2ca66dd47001b9a09890cfe21c2b18c7219ccf5`。該來源覆蓋 `alphasift.dsa_adapter` 契約、`screen/list_strategies/get_status` 呼叫與 `ALPHASIFT_INSTALL_SPEC` 鎖定行為。
- 自動重灌邊界：僅當適配層模組缺失（`diagnostics.reason=missing_module`）時觸發自動安裝；若適配層可匯入但 `get_status()` 報錯或返回 `available=false`，不會自動重灌 `pip`，而是返回 `424 + diagnostics`，保留故障診斷，防止隱藏真實執行時錯誤。
- 原始碼部署：桌面本地模式（`DSA_DESKTOP_MODE=true`）可直接觸發自動安裝；非桌面 Web/Docker 部署觸發自動安裝前必須啟用 `ADMIN_AUTH_ENABLED=true` 並持有有效管理員會話；自定義本地路徑或 wheel 仍需先手動安裝到 DSA 後端使用的 Python 環境。
- 策略歸屬：策略列表、策略引數、選股計算和 LLM 重排由 AlphaSift 負責，DSA 只負責開關、呼叫、展示和錯誤提示。
- LLM 環境：DSA 呼叫 AlphaSift 時會橋接 DSA 已解析的 `LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS`、`LLM_CHANNELS`、`LLM_<NAME>_*`、`LITELLM_CONFIG` 和各模型金鑰；AlphaSift 獨立執行時仍使用自己的 `.env`/環境變數。
- 快照源：DSA 不覆蓋 AlphaSift 的快照源優先順序；有 `TUSHARE_TOKEN` 時由 AlphaSift 優先走 Tushare。需要除錯或臨時切換源順序時，可顯式配置 `SNAPSHOT_SOURCE_PRIORITY`。
- 風險提示：前端設定頁和選股頁展示第三方來源與投資風險說明；不會彈窗打斷使用者。

## AlphaSift 適配層要求

AlphaSift 需要提供 `alphasift.dsa_adapter` 模組，並保持以下穩定函式：

```python
def get_status() -> dict: ...
def list_strategies() -> list[dict]: ...
def screen(strategy: str, *, market: str = "cn", max_results: int = 20, use_llm: bool = True) -> dict: ...
```

`get_status()` 建議返回：

```json
{
  "available": true,
  "contract_version": "1",
  "version": "0.2.0",
  "strategy_count": 8,
  "supported_markets": ["cn"]
}
```

`list_strategies()` 至少返回 `id`，建議同時返回 `name`、`description`、`category`、`tags`、`market_scope`。

`screen()` 返回值建議包含：

```json
{
  "run_id": "20260531-...",
  "strategy": "dual_low",
  "market": "cn",
  "snapshot_count": 100,
  "after_filter_count": 5,
  "llm_ranked": true,
  "llm_coverage": 1.0,
  "warnings": [],
  "source_errors": [],
  "candidates": []
}
```

候選項建議包含 `code`、`name`、`score`、`reason`、`risk_level`、`risk_flags`、`price`、`change_pct`、`amount`、`industry`、`factor_scores`，以及 LLM 欄位：`llm_score`、`llm_confidence`、`llm_thesis`、`llm_catalysts`、`llm_risks`、`llm_watch_items` 等。

AlphaSift 側已在 `ZhuLinsen/alphasift@b2ca66dd47001b9a09890cfe21c2b18c7219ccf5` 提供 DSA adapter contract，並支援複用 DSA 的 `LLM_TIMEOUT_SEC`。

## DSA 後端行為

- `/api/v1/alphasift/status`：返回開關、可用性、預設安裝來源標識和適配層元資訊；不會暴露完整安裝來源。
- `/api/v1/alphasift/install`：開啟流程在適配層缺失時會呼叫它；桌面模式（`DSA_DESKTOP_MODE=true`）不要求管理員會話，非桌面部署必須啟用 `ADMIN_AUTH_ENABLED=true` 並攜帶有效管理員會話，否則返回 `401/403`。介面只允許預設受信任安裝來源，並會強制重灌鎖定 commit，避免舊版 `alphasift` 包殘留。
- `/api/v1/alphasift/strategies`：讀取 AlphaSift 策略列表；如果 `ALPHASIFT_ENABLED=true` 且 `diagnostics.reason=missing_module`，會先按 `/install` 的同一鑑權要求自動安裝後再讀取；若適配層狀態異常，會返回 `424 + diagnostics`，不觸發自動安裝。
- `/api/v1/alphasift/screen`：呼叫適配層 `screen(..., use_llm=True)`，並在呼叫期間臨時注入 DSA 已解析的 LLM 執行環境，同時向支援 `context` 的適配層傳入結構化 LLM 配置；如果已開啟但 `diagnostics.reason=missing_module`，會先按 `/install` 的同一鑑權要求自動安裝後再執行；執行時異常則返回 `424 + diagnostics` 並保留原始錯誤邊界。

## 配置相容邊界（LLM / LiteLLM / Base URL）

- LLM 執行時相容邊界：AlphaSift 不改變主配置鏈路，只在呼叫期注入已解析的 `LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS`、`LLM_CHANNELS` 與 `LLM_<NAME>_*` 到程序環境；受管 provider 的 fallback 過濾行為保持現有策略，不做歷史配置的靜默遷移。`ALPHASIFT_ENABLED` 是當前場景唯一新增持久化分支。
- 注入來源與回滾原則：
  - `LITELLM_MODEL` 與 `LITELLM_FALLBACK_MODELS`優先來自 DSA 已宣告路由：`LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS`、`llm_model_list`；未宣告的自定義 provider/model 將保留使用者原始配置，不被重寫。
  - `OPENAI_BASE_URL` 優先複用主配置的 `OPENAI_BASE_URL`，只有未配置時才會回退到宣告為 openai 的 `LLM_CHANNEL` base_url；不會覆蓋主配置中的私有閘道器或別名配置。
  - `LLM_<NAME>_API_KEYS/BASE_URL/MODELS` 僅按宣告通道合併注入；未宣告通道不會新增注入欄位。
- 若已有自定義模型名、channel、Base URL 或額外頭資訊，開啟/重試 AlphaSift 不會自動覆寫 `.env`。如需回退可按原配置恢復：
  - 回退到舊模型名：直接修改 `LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS`，或清空自定義 `LLM_CHANNELS`。
  - 恢復舊通道：保留歷史 `LLM_<NAME>_API_KEYS/BASE_URL` 並重啟配置生效，不需執行額外遷移指令碼。
- 相容校驗依據（運維核驗）：
  - 官方相容語義以 LiteLLM Provider 路徑與模型別名約定為準（當前服務端依賴 `litellm` 的 provider/model 解析與頻道配置語義）；AlphaSift 層不新增模型路由對映，不做 provider 模式遷移。
  - 回退路徑為“設定頁關閉 AlphaSift 或保留 `ALPHASIFT_ENABLED=false`”，並保持原有 `LITELLM_*` 與 `LLM_*` 配置，觸發失敗時可先核對 `status`/`screen` 的 `diagnostics` 後執行服務重啟。
  - 失敗可見性：`status`/`screen` 介面返回明確錯誤碼與 `message`，前端在設定頁或選股頁會將 `403/424/400/422` 等錯誤直接提示給使用者，便於定位並回退到“關閉 AlphaSift + 保持原有 LLM 執行鏈路”。
- 狀態診斷：`/api/v1/alphasift/status` 對 AlphaSift 包或 `alphasift.dsa_adapter` 未安裝仍保持 `200` + `available=false` 的相容語義；如果匯入過程、`get_status()` 呼叫或返回結構出現非預期異常，後端會記錄 warning，並在響應中追加不含安裝來源明文的 `diagnostics` 欄位，便於從介面狀態和服務端日誌定位問題。

錯誤策略：

- 未開啟返回 `403 alphasift_disabled`。
- 受控安裝介面來源不受信任返回 `403 alphasift_install_spec_not_allowed`。
- AlphaSift 未安裝、缺少適配層或適配層不可呼叫返回 `424`。
- 市場或策略被適配層拒絕時返回 `400/422`。
- 執行失敗返回 `424 alphasift_screen_failed`。

## Web 行為

- 設定頁提供 AlphaSift 開關，開啟後寫入 `ALPHASIFT_ENABLED=true` 並檢查適配層是否可用；若缺失，會自動呼叫受控安裝介面，不要求使用者再點一次安裝。非桌面 Web/Docker 部署需要先啟用管理員認證並完成登入，否則安裝會返回 `401/403`。若配置已是開啟狀態但適配層缺失，策略列表載入也會觸發自動安裝。
- `ALPHASIFT_ENABLED` 是“開啟選股”按鈕背後的持久化狀態，不作為普通資料來源配置項重複展示。
- 選股頁未開啟時展示開啟按鈕；開啟後讀取 AlphaSift 策略列表。
- 當前只暴露 A 股 `cn` 市場。
- 預設返回數量為 3，避免一次選股過慢或結果過多。
- 選股請求使用獨立長超時，避免 LLM 重排未完成時被普通 API 超時截斷。
- 結果頁展示執行 ID、樣本數量、過濾後數量、LLM 是否重排、LLM 覆蓋率；如果 AlphaSift 返回 warning/source error/LLM parse error 或 `llm_ranked=false`，頁面會明確顯示降級原因，避免把本地因子結果誤展示成正常 LLM 判斷；重複的快照源 fallback warning/source error 會在前端合併展示為一條“資料來源降級”提示。

## 桌面端說明

原始碼執行的桌面端複用同一個 Python 後端環境，並設定 `DSA_DESKTOP_MODE=true`；透過設定頁開啟時如缺少適配層，會直接嘗試自動安裝預設受信任來源。

打包後的桌面端通常不依賴執行期 `pip install`：`scripts/build-backend.ps1` 會在構建階段安裝預設 `ALPHASIFT_INSTALL_SPEC` 並把 `alphasift.dsa_adapter` 收集進 PyInstaller 產物。釋出包預設仍關閉；使用者在 Web 設定頁開啟後會先檢查適配層，若打包產物異常缺失，再嘗試受控自動安裝。

## Docker 說明

Docker 映象與桌面釋出包保持一致：`docker/Dockerfile` 會在構建階段安裝預設 `ALPHASIFT_INSTALL_SPEC` 並校驗 `alphasift.dsa_adapter` 可匯入。容器執行時預設仍關閉 AlphaSift；使用者透過 `ALPHASIFT_ENABLED=true` 或 Web 設定頁開啟後優先使用映象內建依賴，若執行環境缺失適配層，設定頁會在滿足管理員會話要求時嘗試自動安裝預設受信任來源。

## 驗證記錄

- `python -m pytest tests/test_alphasift_api.py -q`
- `python -m py_compile api/v1/endpoints/alphasift.py tests/test_alphasift_api.py src/config.py src/core/config_registry.py`
- `cd apps/dsa-web && npm run test -- alphasift.test.ts StockScreeningPage.test.tsx SettingsPage.test.tsx --run`
- `cd apps/dsa-web && npm run lint`
- `cd apps/dsa-web && npm run build`

本地聯調已驗證：`/api/v1/alphasift/status` 可讀取適配層，`/api/v1/alphasift/screen` 在 `use_llm=True` 下返回 LLM 重排結果，選股頁可執行並展開檢視候選詳情。

## 回滾

- 關閉功能：設定頁關閉 AlphaSift，或配置 `ALPHASIFT_ENABLED=false`。
- 禁止啟用：保持 `ALPHASIFT_ENABLED=false`；如需使用預設來源之外的 AlphaSift 安裝包，先在後端 Python 環境完成手動安裝。
- 回滾程式碼：移除 AlphaSift API 註冊、Web 選股入口和相關配置項即可恢復到整合前流程；預設關閉狀態下不會影響原有股票分析、報告生成和通知流程。

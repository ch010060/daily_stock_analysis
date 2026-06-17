# LLM (大模型) 配置指南

歡迎！無論你是剛接觸 AI 的新手小白，還是精通各種 API 的高玩老手，這份指南都能幫你快速把大模型（LLM）跑起來。

本專案對外提供統一的 AI 模型接入體驗，支援主流官方 API、OpenAI 相容平臺以及本地模型。底層由 [LiteLLM](https://docs.litellm.ai/) 驅動，但大多數使用者只需要理解“選服務商、填 API Key、選主模型/通道”這條預設路徑。為了照顧不同階段的使用者，我們設計了“三層優先順序”配置，按需選擇最適合你的方式即可。

如果你正在選擇具體服務商、配置 GitHub Actions Secrets / Variables、排查 `details.reason` 錯誤或準備回滾配置，請優先檢視 [LLM 服務商配置指南](./llm-providers.md)。該文件集中維護 provider 預設、Actions 變數對照、執行時能力檢測邊界和常見錯誤處理建議。

> 本頁的 provider/model/Base URL 說明本次未新增外部相容語義，僅用於同步現網約定；實際相容判斷仍按當前倉庫鎖定依賴與執行時實現執行：
> - 依賴邊界：`litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（與 `requirements.txt` 一致）。
> - 相容驗證入口：`tests/test_system_config_service.py`、`tests/test_system_config_api.py` 以及現有前端模型配置頁迴歸用例。
> - 回退路徑：優先使用 `.env` 配置備份 + `POST /api/v1/system/config/import` 恢復；也可在重啟前手動回填舊 `LITELLM_MODEL` / `LLM_*` / `AGENT_LITELLM_MODEL` / `VISION_MODEL` / `LLM_TEMPERATURE`。

> **說明**：本頁對 provider/model/base URL 的說明同步沿用當前依賴約束與歷史約定，僅做文件補充，不引入新的執行時 provider、模型或 Base URL 行為變更。

---

## 快速導航：你應該看哪一節？

1. **【新手小白】** "我只想趕緊把系統跑起來，越簡單越好！" -> [指路【方式一：極簡單模型配置】](#方式一極簡單模型配置適合新手)
2. **【進階使用者】** "我有好幾個 Key，想配置備用模型，還要改自定義網址(Base URL)。" -> [指路【方式二：通道(Channels)模式配置】](#方式二通道channels模式配置適合進階多模型)
3. **【高玩老手】** "我要做複雜的負載均衡、請求路由、甚至多異構平臺高可用！" -> [指路【方式三：YAML 高階配置】](#方式三yaml高階配置適合老手自定義)
4. **【本地模型】** "我想用 Ollama 本地模型！" -> [指路【示例 4：使用 Ollama 本地模型】](#示例-4使用-ollama-本地模型)
5. **【視覺模型】** "我想用圖片識別股票程式碼！" -> [指路【擴充套件功能：看圖模型(Vision)配置】](#擴充套件功能看圖模型vision配置)

---

## 方式一：極簡單模型配置（適合新手）

**目標：** 只要記得填入 API Key 和對應的模型名就能立刻用。不需要折騰複雜概念。

如果你只打算用一種模型，這是最快捷的辦法。開啟專案根目錄下的 `.env` 檔案（如果沒有，複製一份 `.env.example` 並重新命名為 `.env`）。

### Anspire Open 示例：

> 💡 **推薦 [Anspire Open](https://open.anspire.cn/?share_code=QFBC0FYC)**：支援中文最佳化的聯網搜尋與 OpenAI-compatible 路徑一體化體驗，適合只准備一個 Key 的使用者。
> - 以下為配置示例，模型與閘道器可用性以賬號許可權和 Anspire 控制檯為準；文件示例不替代實際連通性驗證。
> - 建議在 Web 設定頁點選“測試連線”進行實際鑑權與模型可用性檢查，避免以文件預設值直接當作可用性承諾。

```env
# Anspire Open API Keys（支援多個，逗號分隔）
# 獲取: https://open.anspire.cn/?share_code=QFBC0FYC
# 滿足預設優先順序條件時，系統會複用該 Key 處理搜尋與 LLM（僅限示例兜底路徑）。
# 示例模型：Doubao-Seed-2.0-lite；示例閘道器：https://open-gateway.anspire.cn/v6
ANSPIRE_API_KEYS=sk-xxxxxxxxxxxxxxxx
# 可選：按控制檯可用性切換模型或閘道器
# ANSPIRE_LLM_MODEL=Doubao-Seed-2.0-pro
# ANSPIRE_LLM_BASE_URL=https://open-gateway.anspire.ai/v6
```

### 示例 1：使用通用第三方平臺（相容 OpenAI 格式，推薦）

現在市面上絕大多數第三方聚合平臺（例如矽基流動、AIHubmix、阿里百鍊、智譜等）都相容 OpenAI 的介面格式。只要平臺提供了 API Key 和 Base URL，你都可以按照以下格式無腦配置：

```env
# 填入平臺提供給你的 API Key
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
# 填入平臺的介面地址 (非常重要：結尾通常必須帶有 /v1)
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
# 填入該平臺上具體的模型名稱（非常重要：注意前面必須加上 openai/ 字首幫系統識別）
LITELLM_MODEL=openai/deepseek-ai/DeepSeek-V3 
```

### 示例 2：使用 DeepSeek 官方介面
```env
# 填入你在 DeepSeek 官方平臺申請的 API Key
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```
*相容提示：僅填這一行時，系統仍會預設使用 `deepseek/deepseek-chat` 並在日誌提示遷移。*
`deepseek-chat` / `deepseek-reasoner` 仍可用於相容舊配置，但 DeepSeek 官方已標記為 2026/07/24 後廢棄；新配置建議透過 Web 快速通道或顯式 `LITELLM_MODEL=deepseek/deepseek-v4-flash` 遷移到 `deepseek-v4-flash` / `deepseek-v4-pro`。

### 示例 3：使用 Gemini 免費 API
```env
# 填入你獲取的 Google Gemini Key
GEMINI_API_KEY=AIzac...
```

### 示例 4：使用 Ollama 本地模型
```env
# Ollama 無需 API Key，本地執行 ollama serve 後即可使用
OLLAMA_API_BASE=http://localhost:11434
LITELLM_MODEL=ollama/qwen3:8b
```

> **重要**：Ollama 必須使用 `OLLAMA_API_BASE` 配置，**不要**使用 `OPENAI_BASE_URL`，否則系統會錯誤拼接 URL（如 404、`api/generate/api/show`）。遠端 Ollama 時，將 `OLLAMA_API_BASE` 設為實際地址（如 `http://192.168.1.100:11434`）。當前依賴約束為 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（與 requirements.txt 一致）。

> **恭喜！小白讀到這裡就可以去執行程式了！**
> 想測測看通沒通？在主目錄開啟命令列輸入：`python scripts/check_env.py --llm`

---

## 方式二：通道(Channels)模式配置（適合進階/多模型）

**目標：** 我有多個不同平臺的 Key 想要混著用，如果主模型卡了/網路掛了，我希望它能自動切換到備用模型。

**網頁端可以直接配：** 你可以啟動程式後，在 **Web UI 的“系統設定 -> AI 模型 -> AI 模型接入”** 中非常直觀地進行視覺化配置！

> **新版編輯體驗補充**：對於 DeepSeek、阿里百鍊（DashScope）以及其他相容 OpenAI `/v1/models` 的通道，設定頁現在支援直接點選“獲取模型”，從 `{base_url}/models` 拉取可用模型並多選；底層仍會儲存為原來的 `LLM_{CHANNEL}_MODELS=model1,model2` 逗號格式。若通道不支援該介面、鑑權失敗或暫時不可達，仍可繼續手動填寫模型列表，不影響儲存。

### 首次啟動配置狀態

後端提供只讀狀態介面 `GET /api/v1/system/config/setup/status`，用於判斷首次啟動閉環中最基礎的幾類配置是否已經就緒：LLM 主通道、Agent 通道、自選股、通知通道和本地儲存。這個介面只讀取已儲存的 `.env` 與當前程序環境變數，不會過載執行時配置、寫入 `.env`、測試真實模型或建立資料庫檔案；前端嚮導和後續 smoke run 可以基於該介面逐步接入。

### Web 通道編輯器的相容性 / 遷移 / 回退規則

- 預設裡的 provider / Base URL / 示例模型只用於**初始化表單**；真正落盤時仍是你當前輸入的 `LLM_{CHANNEL}_PROTOCOL`、`LLM_{CHANNEL}_BASE_URL`、`LLM_{CHANNEL}_MODELS`、`LLM_{CHANNEL}_API_KEY(S)`，不會在後臺偷偷改成別的 provider 名或 URL。
- 設定頁的“獲取模型”只對 `OpenAI Compatible` / `DeepSeek` 通道呼叫 `{base_url}/models`；“測試連線”預設只對模型列表首項發起一次最小聊天請求，並在結果中展示後端規範化後的 `resolved_model`。若返回 `details.reason=model_access_denied`（例如 Issue #1208 中已觀測到的 SiliconFlow / OpenAI Compatible 經 LiteLLM 返回 `Model disabled`），請把它視為基於 provider 文案的 best-effort 模型可用性診斷，優先確認該模型是否已在當前賬號/key 下開通，必要時調整模型順序或移除不可用模型後重試；未覆蓋或語義不同的 provider 文案會繼續走兜底診斷。可選的“執行時能力檢測”必須由使用者顯式選擇後觸發，會額外發起 JSON / tools / stream / vision smoke 請求，結果僅代表當前賬號、模型和 endpoint 的一次 best-effort 檢測。上述檢測返回的 `stage / error_code / details / latency_ms / capability_results` 僅用於結構化診斷提示，**不會寫回** `.env`，也不會阻止儲存。
- 若返回 `details.reason=provider_blocked`，表示服務商或中轉閘道器明確攔截了本次請求；它區別於本地網路 / TLS 異常和 `model_access_denied`，應優先檢查賬號風控、地域或請求來源限制、模型許可權、代理商閘道器策略和內容安全策略。
- 執行時能力檢測會產生真實 LLM 請求，可能帶來 token / 影象輸入費用、RPM/TPM 限流、餘額不足或超時。檢測失敗可能來自賬號許可權、模型未開通、endpoint 區域、餘額、服務商相容層或 LiteLLM 轉換路徑，不等於該 provider 全域性不支援對應能力。P3 未對所有真實 provider 做線上 smoke；相容依據來自當前依賴約束 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0` 下的 LiteLLM `completion()` / OpenAI I/O format / streaming / exception mapping，以及 OpenAI Chat Completions 的 JSON mode、tool calling、streaming 和 vision input 形狀。
- 相關外部來源：LiteLLM Python SDK / OpenAI I/O format / streaming / exception mapping：<https://docs.litellm.ai/>；LiteLLM OpenAI-compatible 路由：<https://docs.litellm.ai/docs/providers/openai_compatible>；OpenAI Chat Completions：<https://platform.openai.com/docs/api-reference/chat/create>；JSON mode：<https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat>；tool calling：<https://platform.openai.com/docs/guides/function-calling?api-mode=chat>；streaming：<https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat>；vision input：<https://platform.openai.com/docs/guides/images-vision?api-mode=chat>。
- 儲存通道時，只會更新這次提交的 key；不會因為切換通道模式而靜默遷移整個舊配置。唯一會被**同步清理**的是執行時模型引用：如果 `LITELLM_MODEL`、`AGENT_LITELLM_MODEL`、`VISION_MODEL` 或 `LITELLM_FALLBACK_MODELS` 指向了當前已啟用通道里已經不存在的模型，設定頁會在儲存前把這些失效引用清空/移除，避免執行時繼續指向無效模型；即使當前啟用通道沒有任何可選模型，也會清理缺少 legacy Key 支撐的託管 provider 舊值。`cohere/*`、`google/*`、`xai/*` 這類直連模型僅用於說明歷史 `direct-env` 相容保留語義，不等於可用性承諾，是否可用請按各廠商官方模型/API 文件再做實際驗證。
- 後端一致性依據：配置校驗鏈路在 `SystemConfigService._validate_llm_runtime_selection`（`src/services/system_config_service.py`）中透過 `_uses_direct_env_provider`（`src/config.py`）判斷執行時來源；當前僅 `gemini`、`vertex_ai`、`anthropic`、`openai`、`deepseek` 屬於託管 key provider，`cohere`、`google`、`xai` 不在該白名單中，因此會保留為直連模型。
- 回退方式也保持最小：把對應通道模型列表改回去後重新選擇主模型 / fallback，或直接用桌面端匯出備份 / 手動 `.env` 還原之前的 `LLM_*`、`LITELLM_MODEL`、`AGENT_LITELLM_MODEL`、`VISION_MODEL`、`LLM_TEMPERATURE` 即可，不需要額外跑遷移指令碼。Web 端如需恢復配置，也可在啟用管理員鑑權（`ADMIN_AUTH_ENABLED=true`）後透過 `POST /api/v1/system/config/import` 回滾。
- 當前倉庫對此鏈路的依賴約束是 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（見 `requirements.txt`）；迴歸覆蓋包括 `tests/test_system_config_service.py`、`tests/test_system_config_api.py` 和 `apps/dsa-web/src/components/settings/__tests__/LLMChannelEditor.test.tsx`。

> **外部 provider 示例模型說明**：`cohere/*`、`google/*`、`xai/*` 等 provider 字首值僅用於說明當前儲存清理語義，**不代表該依賴約束內的逐型號可用性保證**。文件或測試中的具體模型名都是配置保留行為樣例，不是生產推薦；實際可用性請以對應官方模型文件為準，並結合倉庫依賴約束 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0` 複核。

### 回退與相容性證據

- 依賴約束與靜默清理範圍：在 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0` 下，儲存僅清理失效的 runtime 模型引用（`LITELLM_MODEL`、`AGENT_LITELLM_MODEL`、`VISION_MODEL`、`LITELLM_FALLBACK_MODELS`），`cohere/*`、`google/*`、`xai/*` 等非通道直連模型會被保留。
- 回退方式：可直接用桌面端匯出備份後透過 `POST /api/v1/system/config/import` 恢復；也可手動把 `.env` 中歷史 `LITELLM_* / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE` 回填後重啟生效。Web 端執行匯入前請先開啟管理員鑑權（`ADMIN_AUTH_ENABLED=true`）。
- 回退回歸證據：`tests/test_system_config_service.py::test_import_desktop_env_restores_runtime_models_after_cleanup` 覆蓋“清理後用桌面匯出備份恢復 runtime 引用”。
- 直連 provider 迴歸證據：`tests/test_system_config_service.py::SystemConfigServiceTestCase::test_validate_accepts_minimax_model_as_direct_env_provider`、`test_validate_accepts_cohere_model_as_direct_env_provider`、`test_validate_accepts_google_model_as_direct_env_provider`、`test_validate_accepts_xai_model_as_direct_env_provider` 覆蓋直連 provider 保留語義。
- 前端迴歸命令：`cd apps/dsa-web && npm run lint && npm run build && npm run test -- src/components/settings/__tests__/LLMChannelEditor.test.tsx`。
- 建議回退操作鏈路（含設定頁重新整理）：先匯出桌面備份，`POST /api/v1/system/config/import` 匯入後，再透過 `GET /api/v1/system/config` 重新整理頁面配置，再確認 `LITELLM_MODEL / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE` 與模型列表一致後再繼續使用。

### 常用官方文件來源（用於核對預設 provider / Base URL / 模型命名）

- OpenAI Compatible 規範（LiteLLM）：<https://docs.litellm.ai/docs/providers/openai_compatible>
- OpenAI 官方：<https://platform.openai.com/docs/api-reference/chat>
- DeepSeek 官方：<https://api-docs.deepseek.com/>
- Anspire Open：<https://open.anspire.cn/?share_code=QFBC0FYC>
- 阿里百鍊 DashScope 相容模式：<https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope>
- Moonshot / Kimi 官方：<https://platform.moonshot.ai/docs/guide/compatibility>
- Anthropic 官方：<https://docs.anthropic.com/en/api/messages>
- Gemini 官方：<https://ai.google.dev/gemini-api/docs/openai>
- Cohere 官方：<https://docs.cohere.com/>
- Cohere API 參考：<https://docs.cohere.com/reference/>
- Cohere LiteLLM Provider：<https://docs.litellm.ai/docs/providers/cohere>
- Google Gemini API 與模型：<https://ai.google.dev/gemini-api/docs/openai>、<https://ai.google.dev/gemini-api/docs/models>
- Google LiteLLM Provider：<https://docs.litellm.ai/docs/providers/gemini>
- xAI 官方：<https://docs.x.ai/docs>
- xAI LiteLLM Provider：<https://docs.litellm.ai/docs/providers/xai>
- Ollama 官方：<https://github.com/ollama/ollama/blob/main/docs/api.md>

如果不方便用網頁版，在 `.env` 檔案中配置也非常絲滑，它能讓你同時管理多個第三方平臺。規則如下：

1. **先宣告你有幾個通道**：`LLM_CHANNELS=通道名稱1,通道名稱2`
2. **給每個通道分別填寫配置**（注意全大寫）：`LLM_{通道名}_XXX`

### 示例：同時配置 DeepSeek 和某中轉平臺，並設定備用切換
```env
# 1. 開啟通道模式，宣告這裡有兩個通道：deepseek 和 aihubmix
LLM_CHANNELS=deepseek,aihubmix

# 2. 通道一：配置 DeepSeek 官方
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_DEEPSEEK_API_KEY=sk-1111111111111
LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro

# 3. 通道二：配置一個常用的聚合中轉 API
LLM_AIHUBMIX_BASE_URL=https://api.aihubmix.com/v1
LLM_AIHUBMIX_API_KEY=sk-2222222222222
LLM_AIHUBMIX_MODELS=gpt-5.5,claude-sonnet-4-6

# 4. 【關鍵】指定主模型和備用模型列表
# 平時首選用 deepseek 這款模型：
LITELLM_MODEL=deepseek/deepseek-v4-flash
# 可選：Agent 問股單獨指定主模型（留空則繼承主模型）
AGENT_LITELLM_MODEL=deepseek/deepseek-v4-pro
# 主模型崩了立刻挨個嘗試下面這倆備用模型：
LITELLM_FALLBACK_MODELS=openai/gpt-5.4-mini,anthropic/claude-sonnet-4-6
```

### 示例：Ollama 通道模式（本地模型，無需 API Key）
```env
# 1. 開啟通道模式，宣告 ollama 通道
LLM_CHANNELS=ollama

# 2. 配置 Ollama 地址（本地預設 11434 埠）
LLM_OLLAMA_BASE_URL=http://localhost:11434
LLM_OLLAMA_MODELS=qwen3:8b,llama3.2

# 3. 指定主模型
LITELLM_MODEL=ollama/qwen3:8b
```

### MiniMax 通道模型填寫說明

- 如果你透過 OpenAI Compatible 通道接 MiniMax，請在通道模型裡直接填寫 `minimax/<模型名>`，例如 `minimax/MiniMax-M1`。
- Web 設定頁裡的主模型、Agent 主模型、Fallback、Vision 下拉會保留這個值原樣展示，不會再錯誤改寫成 `openai/minimax/<模型名>`。

### 問股 Agent / LiteLLM 配置相容說明

- 問股 Agent 執行時沿用與普通分析相同的三層優先順序：`LITELLM_CONFIG`（LiteLLM YAML）> `LLM_CHANNELS` > legacy provider keys。只要上層配置有效生效，下層配置就不會再參與本次請求。
- YAML 模式下，Agent 直接複用 LiteLLM `model_list` / `model_name` 路由語義；通道模式下，優先讀取 `AGENT_LITELLM_MODEL`，留空時繼承 `LITELLM_MODEL`，再按 `LITELLM_FALLBACK_MODELS` 繼續 fallback。
- 如果你沒有啟用 YAML / Channels，且 `AGENT_LITELLM_MODEL` 也留空，但本地仍保留 legacy 環境變數，問股 Agent 依然會繼承舊配置：`GEMINI_API_KEY + GEMINI_MODEL` -> `gemini/<model>`，`OPENAI_API_KEY + OPENAI_MODEL` -> `openai/<model>`，`ANTHROPIC_API_KEY + ANTHROPIC_MODEL` -> `anthropic/<model>`。
- 該相容邏輯只增強“失敗時保留後端真實錯誤原因”和“未配置 LLM 時給出更具體診斷”，**不會**靜默刪除、清空、遷移或改寫你現有的 `GEMINI_*` / `OPENAI_*` / `ANTHROPIC_*` / `LITELLM_*` 配置。
- 如果當前環境沒有任何有效 Agent 模型鏈路，問股頁面會繼續按失敗語義返回，並直接展示後端真實配置診斷；補齊任一有效模型來源後即可恢復，無需額外執行配置遷移指令碼。
- 推薦的新配置方式仍然是顯式設定 `LITELLM_MODEL` / `AGENT_LITELLM_MODEL` 或使用 `LLM_CHANNELS`；legacy provider keys 目前保留為相容回退路徑，方便舊 `.env`、本地 macOS 開發環境和歷史部署平滑繼續執行。

### 問股可見對話上下文壓縮

預設情況下，問股仍按歷史行為只注入最近 20 條可見對話。需要長會話省 token 時，可開啟：

```env
AGENT_CONTEXT_COMPRESSION_ENABLED=true
AGENT_CONTEXT_COMPRESSION_PROFILE=balanced
# 留空則跟隨 profile preset
AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=
AGENT_CONTEXT_PROTECTED_TURNS=
```

壓縮只處理 `session_id` 下使用者可見的 `user` / `assistant` 文字歷史，不處理 provider trace、thinking blocks、tool calls 或 tool results，也不會改變同輪工具呼叫透傳。三檔 preset 分別是 `cost`（6000 tokens / 保護 2 輪）、`balanced`（12000 / 4）和 `long_context_raw_first`（24000 / 6）；trigger / protected 留空時跟隨當前 profile，顯式填寫時覆蓋 profile。

問股 single-agent 路徑會額外維護一條 provider-aware trace 分軌，用於 DeepSeek V4 thinking + tool-call 的跨輪協議回放：只有同一輪同時出現 `tool_calls` 與 `reasoning_content` 時才會按當前 `session_id + provider + model` 儲存最近 3 條最小協議材料，並在下一輪按原始時序插回對應可見 assistant 回覆之前。該 trace 只能原樣保留或整段丟棄，不參與摘要、不寫入 Web 會話訊息、不新增 `.env` 配置；model/provider 不匹配、錨點已被 summary 覆蓋或預算不足時會整段跳過。Claude extended thinking 本輪只覆蓋 adapter/storage 級 opaque `thinking` / `redacted_thinking` / `signature` blocks plumbing 與離線 fixture，不宣告生產端到端支援；multi-agent trace 注入仍是 follow-up。外部協議依據包括 DeepSeek thinking mode 文件（<https://api-docs.deepseek.com/guides/thinking_mode>）和 Anthropic Claude extended thinking 文件（<https://platform.claude.com/docs/en/docs/build-with-claude/extended-thinking>），LiteLLM 相容視窗仍以 `requirements.txt` 的 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0` 為準。

### 嚴格 temperature 模型相容說明

- Moonshot 官方說明 Kimi API 相容 OpenAI 介面，Base URL 使用 `https://api.moonshot.ai/v1`：<https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart>
- LiteLLM 官方要求 OpenAI Compatible 通道模型名使用 `openai/` 字首：<https://docs.litellm.ai/docs/providers/openai_compatible>
- Moonshot 官方相容性文件區分兩種固定值：**thinking 模式固定 `1.0`，non-thinking 模式固定 `0.6`**；傳其它值會被介面拒絕：<https://platform.moonshot.ai/docs/guide/compatibility#parameters-differences-in-request-body>
- OpenAI Chat Completions 規範中 `temperature` 是可選引數；對 GPT-5 / o 系列等只接受預設溫度的模型，本專案會在請求層省略 `temperature`，讓服務端使用預設值，而不是改寫你的 `LLM_TEMPERATURE`：<https://platform.openai.com/docs/api-reference/chat/create>
- 當前倉庫的執行時依賴約束是 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（見 `requirements.txt`）；本次相容邏輯按該約束迴歸驗證了主分析、大盤覆盤、Agent 直連 LiteLLM，以及系統設定頁的通道連通性測試。
- 因此本專案會在請求發出前按**實際請求模式**歸一化 `kimi-k2.6` 及其 `kimi-k2.6-*` 變體：預設 / thinking 路徑使用 `temperature=1.0`；如果你的 LiteLLM YAML 路由別名裡顯式寫了 `litellm_params.extra_body.thinking.type: disabled`（或等價 non-thinking 配置），則自動切到 `temperature=0.6`。你在 `.env` 或 Web 設定裡儲存的 `LLM_TEMPERATURE` 不會被改寫。
- 如果相容平臺對未收錄的新模型返回明確的引數錯誤（例如 `temperature` 不支援、只能使用預設 `1.0`、`top_p` 不支援），執行時會對**當前請求**做一次引數修正並重試；只有重試成功後才把該策略快取在當前程序內。該快取不會寫回 `.env`，服務重啟後會重新按配置與適配規則判斷。
- 對已經產生部分內容的流式響應，系統不會在半截輸出後切換引數；仍沿用原有“同模型非流式重試 / fallback 模型”的穩定路徑，避免拼接出不一致的回答。
- `SystemConfigService` 在 Web 設定儲存 / 桌面端 `.env` 匯入時只更新你提交的 key，不會因為切到嚴格 temperature 模型靜默清空、遷移或重寫已有 `LLM_TEMPERATURE`；通道測試請求裡的臨時引數策略也不會回寫到配置檔案。
- 非嚴格主模型、非嚴格 fallback 以及切回普通模型後的請求，仍繼續使用你配置的溫度；也就是說舊配置無需遷移，切換模型即可自動恢復原行為。
- 本倉庫相容性迴歸覆蓋見：`tests/test_llm_channel_config.py`、`tests/test_market_analyzer_generate_text.py`、`tests/test_agent_pipeline.py`、`tests/test_system_config_service.py`。
- 最小回滾方式：直接回退本次 LLM 引數適配相關改動，無需單獨遷移已有 `LLM_TEMPERATURE` 配置。

### 相容性與回退複核清單（按 PR 稽核口徑）

- 執行時依賴約束：`litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（與 `requirements.txt` 一致）。
- 迴歸驗證入口：
  - 通道模型發現與連線：`tests/test_llm_channel_config.py`
  - 執行時源清理與恢復（含桌面匯出備份鏈路）：`tests/test_system_config_service.py`
  - 介面校驗與問題面向欄位：`tests/test_system_config_api.py`
  - 設定頁互動與儲存後提示：`apps/dsa-web/src/components/settings/__tests__/LLMChannelEditor.test.tsx`
- 舊配置回退路徑：`桌面端匯出備份 -> /api/v1/system/config/import`，或手動恢復 `LLM_* / LITELLM_* / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE`；Web 匯入備份前同樣要求 `ADMIN_AUTH_ENABLED=true`，否則會返回 403。

> **致命避坑說明**：如果你啟用了 `LLM_CHANNELS`，那麼你直接寫在外面的 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 將**全部失效（系統一律無視）**！二者**選其一即可**，千萬不要既寫了新手模式又寫了通道模式結果產生衝突。
> **Docker 注意**：如果你在 `docker compose environment:` 或 `docker run -e` 中顯式傳入 `LITELLM_MODEL`、`LLM_CHANNELS`、`LLM_DEEPSEEK_MODELS` 等變數，容器重啟後這些環境變數會覆蓋 Web 設定頁寫入的 `.env`，需要同步修改部署配置。

### 相容依據與回退審計說明（本次 PR 適配說明）

- 官方與執行時相容依據採用兩層：第一層為官方介面語義（LiteLLM OpenAI-compatible 路由、OpenAI Chat Completions、Moonshot/Kimi 文件與官方模型說明）；第二層為本倉庫當前執行時語義（`litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`）下的實際錯誤歸類。
- 本次相容恢復只使用“本地執行時錯誤歸類 + 單請求修正重試 + 程序內快取”策略，不寫入 `.env`、不做配置遷移，僅在執行路徑上動態規避不支援引數（`temperature`、`top_p`、`presence_penalty`、`frequency_penalty`、`seed`）。若要回退，不需要額外遷移命令，恢復舊值即可。
- 迴歸與證據：`tests/test_llm_param_recovery.py`、`tests/test_system_config_service.py`、`tests/test_llm_channel_config.py`、`tests/test_system_config_api.py`、`tests/test_market_analyzer_generate_text.py`、`tests/test_agent_pipeline.py`；桌面匯入與執行時清理回退另有 `test_import_desktop_env_restores_runtime_models_after_cleanup` 直接覆蓋。

---

## 方式三：YAML 高階配置（適合老手自定義）

**目標：** 我不在乎學習門檻，我要最高控制權，我要用原生規則做企業級高可用！

這一層會直接對映到底層 LiteLLM 路由能力，支援高併發、自動重試、按 RPM/TPM 負載均衡等操作。

### 本地執行 / Docker 部署模式配置說明

1. 在 `.env` 中只保留一行指向宣告：
   ```env
   LITELLM_CONFIG=./litellm_config.yaml
   ```
2. 在專案根目錄建立一個 `litellm_config.yaml`（可以參考自帶的 `docs/examples/litellm_config.example.yaml`）。

示例 `litellm_config.yaml`：
```yaml
model_list:
  - model_name: my-smart-model
    litellm_params:
      model: deepseek/deepseek-v4-flash
      api_base: https://api.deepseek.com
      api_key: "os.environ/MY_CUSTOM_SECRET_KEY"  # 從環境變數讀取 Key，安全防洩漏

  # Ollama 本地模型（無需 api_key）
  - model_name: ollama/qwen3:8b
    litellm_params:
      model: ollama/qwen3:8b
      api_base: http://localhost:11434
```

### GitHub Actions配置說明

1. `Settings` → `Secrets and variables` → `Actions`。非敏感配置（如模型名、開關、Base URL）可以放在 `Secret` 或 `Variables`；凡是 `*_API_KEY` / `*_API_KEYS` 以及 `LLM_<NAME>_API_KEY` / `LLM_<NAME>_API_KEYS` 這類金鑰欄位，請統一放在 `Secret` 標籤頁的 `New repository secret`

2. 按下表配置，只有全部必填配置正確配置，YAML 高階配置模式才可以生效，YAML配置檔案的寫法，可以參考自帶的 `docs/examples/litellm_config.example.yaml`

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `LITELLM_CONFIG` | 高階模型路由配置檔案路徑，通常配置 `./litellm_config.yaml` | 必填 |
| `LITELLM_MODEL` | 預設主模型名稱或路由別名 | 必填 |
| `LITELLM_CONFIG_YAML` | 存放 YAML 配置檔案內容，可不在倉庫中提交實體檔案 | 可選 |
| `LITELLM_API_KEY` | 用於儲存API Key，可在配置檔案中引用（環境變數引用方式）。由於GitHub Actions必須要指定匯入的環境變數，因此你不能像本地執行模式那樣自由命名環境變數 | 可選，必須配置到repository secret中 |
| `ANTHROPIC_API_KEY` | 如果要多個API Key，這個變數名稱也能拿來用 | 可選，必須配置到repository secret中 |
| `OPENAI_API_KEY` | 同上，可以用來儲存API Key | 可選，必須配置到repository secret中 |

通道模式無需上傳 YAML 檔案。倉庫自帶 `00-daily-analysis.yml` 已顯式透傳以下常用欄位：

- 執行時選擇：`LLM_CHANNELS`、`LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS`、`AGENT_LITELLM_MODEL`、`VISION_MODEL`、`VISION_PROVIDER_PRIORITY`、`LLM_TEMPERATURE`
- 多 Key：`GEMINI_API_KEYS`、`ANTHROPIC_API_KEYS`、`OPENAI_API_KEYS`、`DEEPSEEK_API_KEYS`（當前 workflow 僅從 repository secrets 匯入，不會讀取同名 Variables）
- 常用通道名：`primary`、`secondary`、`aihubmix`、`deepseek`、`dashscope`、`zhipu`、`moonshot`、`minimax`、`volcengine`、`siliconflow`、`openrouter`、`gemini`、`anthropic`、`openai`、`ollama`

例如在 GitHub Actions 中配置 `LLM_CHANNELS=primary,deepseek` 時，需同步配置 `LLM_PRIMARY_*` / `LLM_DEEPSEEK_*`。其中 `LLM_<NAME>_API_KEY` / `LLM_<NAME>_API_KEYS` 當前也僅從 repository secrets 匯入；如果你把這些值放在 Variables，執行時不會生效。若使用自定義通道名（如 `my_proxy`），GitHub Actions 還必須在 workflow `env:` 中顯式新增對應的 `LLM_MY_PROXY_*` 對映；本地 `.env` 和 Docker 不受這個限制。


> **三層配置互斥準則**：YAML 優先順序最高！只要配置了 YAML，**通道模式** 和 **新手極簡模式** 統統被忽略。系統優先順序為：`YAML配置 > 通道模式 > 極簡單模型`。

---

## 擴充套件功能：看圖模型 (Vision) 配置

系統中有些特定功能（比如上傳股票軟體截圖，讓 AI 提取出截圖裡的股票程式碼並放入自選股池）必須用到具備“視覺能力”的模型。你需在 `.env` 單獨給它指派一個懂圖片的模型。

```env
# 指定你看圖專用的模型名
VISION_MODEL=openai/gpt-5.5
# 別忘了填寫它對應提供商的 API KEY，如果是 OpenAI 相容通道就提供 OPENAI_API_KEY：
# OPENAI_API_KEY=xxx
```

**備用看圖機制：** 為了防止偶爾罷工，系統內建了切換策略。如果主視覺模型呼叫失敗，它會按照下方的順位嘗試尋找是否有其他看圖模型的 Key：
```env
# 預設的備用順序：
VISION_PROVIDER_PRIORITY=gemini,anthropic,openai
```

---

## 檢測與排錯 (Troubleshooting)

配好了之後心驚膽戰不知道對不對？在命令列（Terminal）裡敲入下面程式碼幫你掛號問診：

- `python scripts/check_env.py --config` ：純檢測 `.env` 配置檔案裡的邏輯寫得對不對，是不是少寫了什麼。（秒出結果，不呼叫網路，純檢查本地文字拼寫）
- `python scripts/check_env.py --llm` ：系統會真的發一句問候語給大模型，讓你親眼看到他的回答。這能徹底測出你的**網路通不通、賬號有沒有欠費**。

### 常見踩坑答疑臺

| 遇到了什麼詭異報錯？ | 罪魁禍首可能是啥？ | 該怎麼收拾它？ |
|----------------------|----------------------|------------------|
| **介面提示主模型未配置** | 系統不知道你到底想用哪家的哪個模型 | 在 `.env` 中寫上一句明白話：`LITELLM_MODEL=provider/你的模型名`。比如 `openai/gpt-5.5` |
| **我寫了好幾家的Key，為什麼死活只有一個生效？修改還沒用？** | 你把 **極簡模式** 和 **通道模式** 混著寫了！ | 想好一條路走到黑——只要簡單就刪掉 `LLM_CHANNELS` 開頭的；想要豐富備用切換就要全部轉投到 `LLM_CHANNELS` 下的編制裡。 |
| **錯誤碼報 400 或 401 或 Invalid API Key** | API Key 填錯、少複製了一截、賬號充值沒到賬、或者模型名字敲錯（極度常見）。 | 1. 檢查複製的 Key 前後是否有誤填空格。<br> 2. 檢查 Base URL 最後是不是少了一個 `/v1`。<br> 3. 檢查模型名是否少寫了 `openai/` 之類的字首！ |
| **Kimi K2.6 報 `invalid temperature`（可能提示只允許 `1.0` 或 `0.6`）** | 該模型按 thinking / non-thinking 模式要求不同固定 temperature；舊配置或呼叫入口可能還在傳 `0.7`。 | 升級後系統會對 `kimi-k2.6` 預設 / thinking 請求自動使用 `temperature=1.0`；如果你在 LiteLLM YAML 路由裡顯式關閉 thinking，則自動改用 `0.6`。模型名建議寫成 `openai/kimi-k2.6` 並配合 Moonshot / 聚合平臺的 OpenAI 相容 Base URL 與 API Key。非 Kimi fallback 仍會繼續使用你配置的 `LLM_TEMPERATURE`。 |
| **GPT-5 / o 系列報 `temperature` 不支援或只允許預設值** | 這類模型只接受服務端預設取樣引數，但舊呼叫入口會顯式傳 `0.7`。 | 升級後請求層會省略 `temperature`，讓服務端使用預設值；`.env` / Web 設定中的 `LLM_TEMPERATURE` 不會被改寫，切回普通模型後仍按原值傳送。 |
| **轉圈轉不停，最後報 Timeout / ConnectionRefused 等** | 1. 在國內使用國外原版（像 Google、OpenAI），沒開代理被牆了。<br>2. 你買的雲伺服器壓根不能出境。 | 非常推薦使用**國內官方**（如DeepSeek、阿里）或者各種**相容 OpenAI 的聚合中轉介面**。因為中轉站把網路問題幫你解決好了。 |
| **Ollama 報 404、`Could not get model info` 或 `api/generate/api/show`** | 誤用 `OPENAI_BASE_URL` 配置 Ollama，系統會錯誤拼接 URL | 改用 `OLLAMA_API_BASE=http://localhost:11434` 或通道模式（`LLM_CHANNELS=ollama` + `LLM_OLLAMA_BASE_URL`） |

*進階老手的叮囑：如果你開啟了 **Agent (深度思考網路搜尋問股) 模式**，這裡有個經驗之談，推薦選用如 `deepseek-v4-pro` 這種邏輯推導能力更強的大模型。如果為了省錢用小微模型跑 Agent，它邏輯能力大機率跟不上，不僅達不到預期，還會白跑一堆空流程。*

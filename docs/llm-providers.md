# LLM 服務商配置指南

本文面向首次配置使用者，說明如何選擇 LLM 配置方式、如何把 Web 設定頁「AI 模型配置」預設對映到 `.env` / GitHub Actions，以及如何處理常見檢測錯誤。

> 本頁未引入新的外部 provider、模型名或 Base URL 相容行為，僅整理配置參考與官方來源；實際相容性仍以倉庫當前執行時依賴與測試結論為準。

> - 執行時基礎：`requirements.txt` 當前鎖定 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`，相容語義以該版本約束下實現為準。
> - 驗證閉環：系統配置鏈路迴歸見 `tests/test_system_config_service.py` 與 `tests/test_system_config_api.py`，`Web` 側配置頁互動迴歸見現有元件測試用例。
> - 回退路徑：保留舊變數不做自動遷移；可透過 Web/桌面匯出備份後 `POST /api/v1/system/config/import` 回滾，或手動恢復歷史 `LLM_*` / `LITELLM_*` / `AGENT_*` / `VISION_MODEL` 配置。

實際可用模型、額度、區域限制和價格以各服務商控制檯為準；如果模型列表拉取失敗，可在 Web 中手動填寫模型名。Web 設定頁展示的 provider 能力標籤、官方來源連結和配置注意事項來自靜態 provider template，僅用於配置參考，不代表執行時能力已驗證透過。

## 先選配置方式

| 方式 | 適合誰 | 主要變數 | 說明 |
| --- | --- | --- | --- |
| 極簡 legacy | 只想快速跑通一個模型的使用者 | `LITELLM_MODEL` + 對應 provider key | 最少變數，適合本地快速開始；不適合複雜 fallback。 |
| Channels | 需要多個 provider、多個 key 或 fallback 的使用者 | `LLM_CHANNELS` + `LLM_<CHANNEL>_*` | 推薦預設路徑；Web 設定頁儲存的也是這一層配置。 |
| YAML | 熟悉 LiteLLM 路由、負載均衡和企業閘道器的使用者 | `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML` | 優先順序最高；一旦有效生效，Channels 和 legacy 不再參與本次請求。 |

優先順序保持不變：`LITELLM_CONFIG` / `LITELLM_CONFIG_YAML` > `LLM_CHANNELS` > legacy provider keys。P4 只補文件，不遷移、不清空、不靜默改寫舊配置。

## Web 設定頁路徑

推薦優先使用 Web 設定頁完成 Channels 配置：

1. 開啟設定頁的「AI 模型配置」。
2. 在「快速新增通道」選擇服務商預設。
3. 填入 API Key，必要時點選「獲取模型」。
4. 選擇主模型、Agent 主模型、備選模型和 Vision 模型後儲存。
5. 點選「測試連線」確認鑑權、模型名、額度和響應格式正常。
6. 如需確認 JSON / tools / stream / vision 能力，手動勾選「執行時能力檢測」後再觸發；該檢測會產生真實 LLM 請求，結果只代表當前賬號、模型和 endpoint 的一次 best-effort 檢測，不會寫回 `.env`，也不會阻止儲存。

## Channels 示例

### DeepSeek 官方通道

```env
LLM_CHANNELS=deepseek
LLM_DEEPSEEK_PROTOCOL=deepseek
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_DEEPSEEK_API_KEY=sk-xxx
LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro
LITELLM_MODEL=deepseek/deepseek-v4-flash
```

### OpenAI-compatible 聚合或自定義閘道器

```env
LLM_CHANNELS=my_proxy
LLM_MY_PROXY_PROTOCOL=openai
LLM_MY_PROXY_BASE_URL=https://your-proxy.example.com/v1
LLM_MY_PROXY_API_KEY=sk-xxx
LLM_MY_PROXY_MODELS=gpt-5.5,claude-sonnet-4-6
```

OpenAI-compatible Base URL 只填到服務商相容入口，不額外拼接 `/chat/completions`。本地 `.env`、Docker 和自託管指令碼可以直接使用自定義 channel；GitHub Actions 需要 workflow 顯式透傳同名 `LLM_MY_PROXY_*` 變數。
小米 MiMo 示例同理：適用於本地 `.env`、Docker 或自託管指令碼；若在 GitHub Actions 使用 `LLM_CHANNELS=mimo`，需要在 workflow 中手動補齊 `LLM_MIMO_*` 對映後方可生效。

## 常用服務商預設

| 服務商 | 通道名 | 協議 | Base URL | 模型示例 |
| --- | --- | --- | --- | --- |
| AIHubmix | `aihubmix` | `openai` | `https://aihubmix.com/v1` | `gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview` |
| Anspire Open | `anspire` | `openai` | `https://open-gateway.anspire.cn/v6`（示例） | `Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro,qwen3.5-flash,MiniMax-M2.7`（示例） |
| OpenAI | `openai` | `openai` | `https://api.openai.com/v1` | `gpt-5.5,gpt-5.4-mini` |
| DeepSeek | `deepseek` | `deepseek` | `https://api.deepseek.com` | `deepseek-v4-flash,deepseek-v4-pro` |
| Gemini | `gemini` | `gemini` | 留空 | `gemini-3.1-pro-preview,gemini-3-flash-preview` |
| Anthropic Claude | `anthropic` | `anthropic` | 留空 | `claude-sonnet-4-6,claude-opus-4-7` |
| Kimi / Moonshot | `moonshot` | `openai` | `https://api.moonshot.cn/v1` | `kimi-k2.6,kimi-k2.5` |
| 通義千問 / DashScope | `dashscope` | `openai` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.6-plus,qwen3.6-flash` |
| 智譜 GLM | `zhipu` | `openai` | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.1,glm-4.7-flash` |
| MiniMax | `minimax` | `openai` | `https://api.minimax.io/v1` | `MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed` |
| 小米 MiMo | `mimo` | `openai` | 官方控制檯提供（Actions 預設未對映） | 官方文件/控制檯為準 |
| 火山方舟 / 豆包 | `volcengine` | `openai` | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015` |
| 矽基流動 / SiliconFlow | `siliconflow` | `openai` | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507` |
| OpenRouter | `openrouter` | `openai` | `https://openrouter.ai/api/v1` | `~anthropic/claude-sonnet-latest,~openai/gpt-latest` |
| Ollama | `ollama` | `ollama` | `http://127.0.0.1:11434` | `llama3.2,qwen2.5` |

## 官方來源與相容性

| 服務商 | 官方來源 | 相容說明 |
| --- | --- | --- |
| Anspire Open | [Anspire Open](https://open.anspire.cn/?share_code=QFBC0FYC) | `ANSPIRE_API_KEYS` 在未配置更高優先順序 OpenAI-compatible 來源時可用於大模型閘道器與搜尋；頁面與 `.env` 預設示例為 `openai/Doubao-Seed-2.0-lite` + `https://open-gateway.anspire.cn/v6`，是否可用以控制檯與模型許可權為準。 |
| OpenAI | [模型列表](https://platform.openai.com/docs/models) | 官方模型頁建議從 `gpt-5.5` 開始，低延遲/低成本場景使用 `gpt-5.4-mini` 或 `gpt-5.4-nano`。 |
| DeepSeek | [快速開始](https://api-docs.deepseek.com/) | 官方 OpenAI Base URL 為 `https://api.deepseek.com`；`deepseek-chat` / `deepseek-reasoner` 將於 2026-07-24 棄用，當前模板直接使用 `deepseek-v4-flash` / `deepseek-v4-pro`。 |
| Gemini | [模型列表](https://ai.google.dev/gemini-api/docs/models) | Gemini 3.1 Pro / Gemini 3 Flash 仍為 preview；如需生產穩定性，可在控制檯改回 2.5 穩定模型。 |
| Anthropic Claude | [模型概覽](https://docs.anthropic.com/en/docs/about-claude/models/all-models) | Claude 當前 API ID 包含 `claude-sonnet-4-6`、`claude-opus-4-7`；Sonnet 更適合作為預設價效比入口。 |
| Kimi / Moonshot | [Kimi K2.6 快速開始](https://platform.kimi.com/docs/guide/kimi-k2-6-quickstart)、[模型列表](https://platform.kimi.com/docs/models) | 官方推薦 `kimi-k2.6`；`kimi-k2` 系列將在 2026-05-25 下線，舊 `moonshot-v1-*` 僅保留為穩定舊工作負載選擇。 |
| 通義千問 / DashScope | [文字生成](https://help.aliyun.com/zh/model-studio/text-generation-model/) | 百鍊推薦 `qwen3.6-plus`，確認效果後可用 `qwen3.6-flash` 降低成本。 |
| 智譜 GLM | [模型概覽](https://docs.bigmodel.cn/cn/guide/start/model-overview)、[GLM-5.1](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1) | `glm-5.1` 是當前旗艦；`glm-4.7-flash` 作為輕量/免費模型示例。 |
| MiniMax | [OpenAI API 相容](https://platform.minimax.io/docs/api-reference/text-chat)、[獲取模型列表](https://platform.minimax.io/docs/api-reference/models/openai/list-models)、[Pricing](https://platform.minimax.io/docs/guides/pricing-paygo) | 官方 OpenAI-compatible Base URL 為 `https://api.minimax.io/v1`，並列出 `MiniMax-M3`（預設，支援圖片輸入，官方支援最多 1M 輸入上下文，pricing 區分 `<=512K` 與 `>512K` 輸入兩檔價格）、`MiniMax-M2.7`、`MiniMax-M2.7-highspeed`，以及 Legacy 模型 `MiniMax-M2.5`。本倉庫 fallback 成本估算保守按 `<=512K` 價格檔註冊 M3，並保留 M2.5 legacy 定價以相容歷史使用者配置；中國區 Coding 工具場景可能使用 `.com`/Anthropic 專用入口，以控制檯為準。 |
| 小米 MiMo | 官方文件 / 控制檯 | 當前按 OpenAI-compatible 方式接入，Base URL、模型名與許可權以 MiMo 官方文件/控制檯為準；`mimo` 通道在倉庫預設 workflow 中未顯式對映，Actions 使用請按本文“GitHub Actions 配置”補齊自定義對映。 |
| 火山方舟 / 豆包 | [線上推理（常規）](https://www.volcengine.com/docs/82379/2121998)、[模型列表](https://www.volcengine.com/docs/82379/1949118) | 官方示例使用 `https://ark.cn-beijing.volces.com/api/v3` 與 `doubao-seed-1-6-251015`；如使用 Coding Plan，請改用其專用 Base URL 和模型名，不要套用本表的線上推理模板。 |
| SiliconFlow | [模型列表](https://docs.siliconflow.cn/quickstart/models)、[獲取模型列表 API](https://docs.siliconflow.cn/cn/api-reference/models/get-model-list) | 平臺模型實時更新且 `/models` 需要 API Key；模板只給常見新模型示例，儲存前建議在 Web 設定頁點選「獲取模型」確認賬號可見性。 |
| OpenRouter | [Models API](https://openrouter.ai/docs/api/api-reference/models/get-models) | OpenRouter 支援 `~anthropic/claude-sonnet-latest`、`~openai/gpt-latest` 等 latest router alias；2026-05-03 的一次手動 live smoke 以 Claude Sonnet latest 作為預設示例透過，GPT latest 保留為可按賬號許可權切換的備選。 |
| LiteLLM | [OpenAI-Compatible Endpoints](https://docs.litellm.ai/docs/providers/openai_compatible) | OpenAI-compatible 端點需要把執行時模型寫成 `openai/<model>`，Base URL 只填到服務商相容入口，不額外拼接 `/chat/completions`。 |

本頁預設只保證配置形狀與當前依賴的 OpenAI-compatible 路由規則一致；實際連通性仍取決於服務商賬號許可權、地域、額度和模型開通狀態。當前 LiteLLM 版本約束為 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（見 `requirements.txt`），保留歷史最低版本、顯式排除 PyPI 事故版本，並避免未來大版本自動進入。

## OpenAI-compatible 與 LiteLLM 規則

- OpenAI-compatible provider 的 channel `protocol` 通常是 `openai`。
- 執行時模型名通常寫成 `openai/<model>`；例如自定義閘道器裡的 `gpt-5.5` 可以作為 `openai/gpt-5.5` 被 LiteLLM 路由。
- `Qwen/...`、`deepseek-ai/...` 這類是服務商或模型倉庫組織名字首，不等同於 LiteLLM provider prefix；不要因為它們包含斜槓就誤判為 `provider/model` 路由。
- Base URL 只填官方或閘道器給出的相容入口，通常到 `/v1`、`/api/v3` 或廠商文件指定路徑；不要手動追加 `/chat/completions`。
- 如果使用 YAML 模式，按 LiteLLM `model_list` / `litellm_params` 的原生語義配置；YAML 有效時優先順序高於 Channels。

## GitHub Actions 配置

倉庫自帶 `.github/workflows/00-daily-analysis.yml` 只會透傳 workflow 中顯式列出的環境變數。使用通道模式時，先在 Repository Variables 或 Secrets 中設定 `LLM_CHANNELS`，再按通道名補齊對應 `LLM_<CHANNEL>_*`。

| 欄位 | 建議位置 | 說明 |
| --- | --- | --- |
| `LLM_CHANNELS` | Variables 或 Secrets | 逗號分隔通道名，例如 `deepseek,minimax,volcengine`。 |
| `LLM_<CHANNEL>_PROTOCOL` | Variables 或 Secrets | 非敏感，通常為 `openai`、`deepseek`、`gemini`、`anthropic` 或 `ollama`。 |
| `LLM_<CHANNEL>_BASE_URL` | Variables 或 Secrets | 非敏感時優先放 Variables；私有閘道器地址可放 Secrets。 |
| `LLM_<CHANNEL>_MODELS` | Variables 或 Secrets | 非敏感模型列表，逗號分隔。 |
| `LLM_<CHANNEL>_ENABLED` | Variables 或 Secrets | 可選，未配置時預設啟用；設為 `false` 可跳過該通道。 |
| `LLM_<CHANNEL>_API_KEY` / `LLM_<CHANNEL>_API_KEYS` | Secrets | 金鑰欄位必須放 Repository Secrets；同名 Variables 不會被 workflow 讀取。 |
| `LLM_<CHANNEL>_EXTRA_HEADERS` | Secrets 或 Variables | JSON 字串；只要包含鑑權、租戶、組織或私有閘道器資訊，就應放 Secrets。 |
| `LITELLM_CONFIG` | Variables 或 Secrets | YAML 檔案路徑；配合 `LITELLM_CONFIG_YAML` 使用時，workflow 會寫入該路徑。 |
| `LITELLM_CONFIG_YAML` | Secrets 優先 | YAML 內容本身可能包含私有閘道器或 header，建議放 Secrets。 |

預設 workflow 已顯式對映 `primary`、`secondary`、`aihubmix`、`anspire`、`deepseek`、`dashscope`、`zhipu`、`moonshot`、`minimax`、`volcengine`、`siliconflow`、`openrouter`、`gemini`、`anthropic`、`openai`、`ollama`；`mimo` 未在預設 workflow 中對映。若使用 `mimo`（或任何未列通道名），除了在 Variables/Secrets 配置同名 `LLM_<CHANNEL>_*` 外，還需在 workflow 中同步補齊對應 env 對映；本地 `.env`、Docker 和自託管指令碼不受這個限制。

Ollama 預設 Base URL `http://127.0.0.1:11434` 主要面向本地、Docker 或能訪問該服務的 self-hosted runner。GitHub-hosted runner 通常沒有本地 Ollama 服務，直接配置 `LLM_CHANNELS=ollama` 大機率會連線失敗。

## 常見錯誤與處理建議

| `details.reason` / 現象 | 常見原因 | 建議處理 |
| --- | --- | --- |
| `missing_api_key` | API Key 為空，或 `API_KEYS` 逗號分隔後沒有任何非空片段。 | 填入至少一個有效 key；本地 Ollama 或 localhost 相容服務除外。 |
| `api_key_rejected` | 服務商返回 401 / 403，key 無效、許可權不足或專案未開通。 | 重新複製 key，檢查賬號專案、組織、區域和模型許可權。 |
| `insufficient_balance` | 餘額不足、賬單未開通或套餐額度耗盡。 | 到服務商控制檯確認餘額、賬單狀態和模型套餐。 |
| `quota_exceeded` | 賬號或組織配額耗盡。 | 檢查套餐、專案額度、組織額度和服務商賬單頁。 |
| `rate_limit` | RPM / TPM / 併發限制觸發。 | 降低併發，換輕量模型，或在控制檯提升限額。 |
| `timeout` | 請求超時，可能是網路慢、服務商響應慢或本地服務無響應。 | 檢查代理、防火牆、Base URL、模型冷啟動和 timeout 設定。 |
| `dns_error` | 域名無法解析。 | 檢查 Base URL 拼寫、DNS、代理和執行環境網路。 |
| `tls_error` | TLS 證書、代理或中間人證書異常。 | 檢查 HTTPS 證書鏈、公司代理、自簽證書和系統時間。 |
| `connection_refused` | 目標埠無服務，或本地服務未啟動。 | 檢查 Base URL、埠、防火牆；Ollama 確認本機或 runner 能訪問服務。 |
| `endpoint_not_found` | `/models` 或 chat endpoint 路徑不存在。 | 確認 Base URL 是否填到相容入口，不要多拼或少拼廠商要求的路徑。 |
| `invalid_url` | base_url 包含不受支援形態（空白/控制字元、反斜槓、`userinfo@host` 等）或解析語義不安全。 | 清理 `LLM_<CHANNEL>_BASE_URL`（建議先置空/刪除該變數），保持 provider 預設入口；如需固定閘道器請先按官方相容示例填寫。 |
| `model_access_denied` | 基於已觀測 provider 文案的 best-effort 模型可用性歸類：模型可能被禁用、未開通、賬號不可見或當前 key 無許可權訪問。 | 先檢視測試結果裡的“本次測試模型”，在服務商控制檯確認該模型已開通；必要時調整模型順序、移除不可用模型，或點選「獲取模型」核對賬號可見模型。 |
| `provider_blocked` | 服務商或中轉閘道器明確攔截了本次請求，可能來自賬號風控、地域、請求來源、模型許可權、代理商策略或內容安全策略。 | 先檢視測試結果裡的“本次測試模型”和服務商控制檯日誌；檢查賬號/專案狀態、地域或來源限制、閘道器策略和內容安全規則，而不是優先排查 Base URL、TLS 或本地網路。 |
| `provider_prefix_mismatch` | LiteLLM provider prefix 與通道協議不匹配。 | OpenAI-compatible 通道通常使用 `openai/<model>`；不要把 `Qwen/...`、`deepseek-ai/...` 誤當 provider prefix。 |
| `non_json` | 服務商返回非 JSON 或代理返回 HTML / 文字錯誤頁。 | 檢查 Base URL、閘道器路徑、代理錯誤頁和 Chat Completions 相容入口。 |
| `null_response` | LiteLLM 沒有返回可解析響應物件。 | 檢查 provider 是否相容 Chat Completions，必要時換模型或 endpoint 重試。 |
| `null_content` | Chat completion 返回成功但 `content` 為空。 | 換用相容文字輸出的模型，或檢查是否強制 tool / vision 響應。 |
| `malformed_choices` | 響應缺少相容的 `choices` 結構。 | 確認 endpoint 是 Chat Completions 相容介面，不是 Embeddings、Responses 或其它協議入口。 |
| `capability_unsupported` | JSON / tools / stream / vision smoke 引數不被當前模型或 endpoint 支援。 | 換支援該能力的模型，或把結果視為當前賬號、模型和 endpoint 的一次能力診斷，不代表 provider 全域性不支援。 |
| `unknown_error` | 服務商或客戶端丟擲未能細分的異常。 | 先檢視 `details.message` / 日誌中的原始錯誤，再按網路、鑑權、模型名和額度逐項排查。 |

完整分類邏輯以 `src/services/system_config_service.py` 中的錯誤分類實現為準。

`model_access_denied` 不是跨 provider 的官方錯誤碼對映。該分類的可複核依據包括：

- SiliconFlow 官方錯誤處理文件要求介面錯誤排查時記錄 HTTP 錯誤碼和 `message`，說明 403 表示餘額不足或許可權不夠，其他情況參考報錯 `message`，並建議換一個模型確認問題是否仍存在（中文：<https://docs.siliconflow.cn/cn/faqs/error-code>；英文：<https://docs.siliconflow.cn/en/faqs/error-code>）。
- Issue #1208 中真實脫敏樣例來自 SiliconFlow / OpenAI Compatible 通道測試，經 LiteLLM 返回 `litellm.APIError: APIError: OpenAIException - Model disabled.`。
- 線上複核記錄（2026-05-06T16:21:21Z）：在 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0` 約束下，本地驗證環境為 Python `3.13.12`、LiteLLM `1.82.3`、Base URL `https://api.siliconflow.cn/v1`、模型 `Qwen/Qwen3-235B-A22B-Thinking-2507`。直連 SiliconFlow Chat Completions 返回 HTTP `403`，響應體為 `{"code":30003,"message":"Model disabled.","data":null}`；同一模型透過 LiteLLM `completion(model="openai/Qwen/Qwen3-235B-A22B-Thinking-2507")` 返回 `APIError: OpenAIException - Model disabled.`。

因此當前執行時把該已觀測 provider `message` 作為 best-effort 模型可用性診斷，而不是把它宣告為官方跨 provider 錯誤碼。實現僅在錯誤文字同時包含 `model` 和明確許可權、禁用或不可用訊號時進入該診斷；未覆蓋或語義不同的 provider 文案會繼續走既有兜底診斷。`provider_blocked` 同樣是基於明確攔截文案的 best-effort 診斷，用於區分服務商/閘道器策略攔截與本地網路、TLS 或模型不可用問題。

## 執行時能力檢測邊界

- JSON / tools / stream / vision smoke 必須在 Web 中顯式觸發。
- 檢測會產生真實 LLM 請求，可能帶來 token / 影象輸入費用、RPM/TPM 限流、餘額不足或超時。
- 檢測結果只代表當前賬號、模型和 endpoint 的一次 best-effort 執行時結果。
- 檢測結果不會寫回 `.env`，也不會阻止儲存配置。
- 能力檢測失敗不等於 provider 全域性不支援；失敗可能來自賬號許可權、模型未開通、endpoint 區域、餘額、服務商相容層或 LiteLLM 轉換路徑。
- 當前實現未對所有真實 provider 做線上 smoke，相容依據是 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（見 `requirements.txt`）、[LiteLLM Python SDK / OpenAI I/O format](https://docs.litellm.ai/)、[LiteLLM OpenAI-compatible 路由](https://docs.litellm.ai/docs/providers/openai_compatible)，以及 OpenAI Chat Completions 的 [JSON mode](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat)、[tool calling](https://platform.openai.com/docs/guides/function-calling?api-mode=chat)、[streaming](https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat) 和 [vision input](https://platform.openai.com/docs/guides/images-vision?api-mode=chat) 請求形狀。

## 回滾方式

- Web 設定頁：刪除或禁用對應 channel，重新選擇舊的主模型 / Agent 模型 / fallback。
- `.env`：恢復備份中的 `LLM_*`、`LITELLM_MODEL`、`AGENT_LITELLM_MODEL`、`VISION_MODEL`、`LITELLM_FALLBACK_MODELS`。
- 從 Channels 回到 legacy：刪除或清空 `LLM_CHANNELS`，保留 legacy provider key 和 `LITELLM_MODEL`。
- 從 YAML 回到 Channels / legacy：移除 `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML`，重啟後下層配置重新生效。
- WebUI / 桌面端：使用系統設定中匯出的配置備份恢復。
- PR 回滾：revert 對應 docs PR；P4 不涉及配置、資料或程式碼遷移。

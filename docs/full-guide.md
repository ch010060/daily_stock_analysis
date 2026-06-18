# 📖 完整配置與部署指南

本文件包含 A股智慧分析系統的完整配置說明，適合需要高階功能或特殊部署方式的使用者。

> 💡 快速上手請參考 [README.md](../README.md)，本文件為進階配置。

## 📁 專案結構

```
daily_stock_analysis/
├── main.py              # 主程式入口
├── src/                 # 核心業務邏輯
│   ├── analyzer.py      # AI 分析器
│   ├── config.py        # 配置管理
│   ├── notification.py  # 訊息推送
│   └── ...
├── data_provider/       # 多資料來源介面卡
├── bot/                 # 機器人互動模組
├── api/                 # FastAPI 後端服務
├── apps/dsa-web/        # React 前端
├── docker/              # Docker 配置
├── docs/                # 專案文件
└── .github/workflows/   # GitHub Actions
```

## 📑 目錄

- [專案結構](#專案結構)
- [GitHub Actions 詳細配置](#github-actions-詳細配置)
- [環境變數完整列表](#環境變數完整列表)
- [Docker 部署](#docker-部署)
- [本地執行詳細配置](#本地執行詳細配置)
- [定時任務配置](#定時任務配置)
- [通知通道詳細配置](#通知通道詳細配置)
- [資料來源配置](#資料來源配置)
- [高階功能](#高階功能)
- [回測功能](#回測功能)
- [本地 WebUI 管理介面](#本地-webui-管理介面)

---

## GitHub Actions 詳細配置

### 1. Fork 本倉庫

點選右上角 `Fork` 按鈕

### 2. 配置 Secrets

進入你 Fork 的倉庫 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

<div align="center">
  <img src="assets/secret_config.png" alt="GitHub Secrets 配置示意圖" width="600">
</div>

#### AI 模型配置（至少配置一個）

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `ANSPIRE_API_KEYS` | [Anspire](https://open.anspire.cn/?share_code=QFBC0FYC) API Key，一 Key 同時啟用大模型和中文最佳化聯網搜尋，含本專案免費額度 | 推薦 |
| `AIHUBMIX_KEY` | [AIHubMix](https://aihubmix.com/?aff=CfMq) API Key，一 Key 切換使用全系模型，本專案可享 10% 優惠 | 推薦 |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) 獲取免費 Key | 可選 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | 可選 |
| `OPENAI_API_KEY` | OpenAI 相容 API Key（支援 DeepSeek、通義千問等） | 可選 |
| `OPENAI_BASE_URL` | OpenAI 相容 API 地址（如 `https://api.deepseek.com`） | 可選 |
| `OPENAI_MODEL` | 模型名稱（如 `gemini-3.1-pro-preview`、`deepseek-v4-flash`、`gpt-5.5`） | 可選 |

> *注：以上模型 Key / 通道至少配置一個；推薦優先從 Anspire 或 AIHubMix 這類一 Key 多模型服務開始。啟動時配置校驗會在缺少可用 AI 模型 Key 或模型通道時給出明確錯誤提示。

#### 通知通道配置（可同時配置多個，全部推送）

> 通知通道、minimal/advanced key 分層、Actions 對映、`--check-notify` 診斷、Web 一鍵測試和本地 / Docker / GitHub Actions / Desktop 場景說明詳見 [通知專題文件](notifications.md)。

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企業微信 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_URL` | 飛書 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_SECRET` | 飛書 Webhook 簽名金鑰（開啟“簽名校驗”時必填） | 可選 |
| `FEISHU_WEBHOOK_KEYWORD` | 飛書 Webhook 關鍵詞（開啟“關鍵詞”時必填） | 可選 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（@BotFather 獲取） | 可選 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID (用於傳送到子話題) | 可選 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL（[建立方法](https://support.discord.com/hc/en-us/articles/228383668)） | 可選 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token（與 Webhook 二選一） | 可選 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID（使用 Bot 時需要） | 可選 |
| `DISCORD_INTERACTIONS_PUBLIC_KEY` | Discord Public Key（僅入站 Interaction/Webhook 回撥驗籤時需要） | 可選 |
| `SLACK_BOT_TOKEN` | Slack Bot Token（推薦，支援圖片上傳；同時配置時優先於 Webhook） | 可選 |
| `SLACK_CHANNEL_ID` | Slack Channel ID（使用 Bot 時需要） | 可選 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL（僅文字，不支援圖片） | 可選 |
| `EMAIL_SENDER` | 發件人郵箱（如 `xxx@qq.com`） | 可選 |
| `EMAIL_PASSWORD` | 郵箱授權碼（非登入密碼） | 可選 |
| `EMAIL_RECEIVERS` | 收件人郵箱（多個用逗號分隔，留空則發給自己） | 可選 |
| `EMAIL_SENDER_NAME` | 發件人顯示名稱（預設：daily_stock_analysis股票分析助手） | 可選 |
| `PUSHPLUS_TOKEN` | PushPlus Token（[獲取地址](https://www.pushplus.plus)，國內推送服務） | 可選 |
| `SERVERCHAN3_SENDKEY` | Server醬³ Sendkey（[獲取地址](https://sc3.ft07.com/)，手機APP推送服務） | 可選 |
| `ASTRBOT_URL` | AstrBot Webhook URL | 可選 |
| `ASTRBOT_TOKEN` | AstrBot Bearer Token（可選） | 可選 |
| `NTFY_URL` | ntfy 完整 topic endpoint，必須包含 topic path，例如 `https://ntfy.sh/my-topic` | 可選 |
| `NTFY_TOKEN` | ntfy Bearer Token（可選） | 可選 |
| `GOTIFY_URL` | Gotify server base URL，不包含 `/message`；系統會自動拼接 `/message` | 可選 |
| `GOTIFY_TOKEN` | Gotify application token，透過 `X-Gotify-Key` Header 傳送 | 可選 |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（支援釘釘等，多個用逗號分隔） | 可選 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定義 Webhook 的 Bearer Token（用於需要認證的 Webhook） | 可選 |
| `CUSTOM_WEBHOOK_BODY_TEMPLATE` | 自定義 Webhook JSON body 模板，適配 AstrBot、NapCat、自建服務等特殊 payload | 可選 |
| `WEBHOOK_VERIFY_SSL` | 讀取該配置的 webhook-style HTTPS 通知請求證書校驗（預設 true）。設為 false 可支援自簽名證書。警告：關閉有嚴重安全風險（MITM），僅限可信內網 | 可選 |

> *注：至少配置一個通道，配置多個則同時推送。啟動時配置校驗會提示 Telegram / 郵件成對欄位缺失，以及常見 Webhook URL 未以 `http://` 或 `https://` 開頭的問題。
>
> 當前預設 `00-daily-analysis.yml` 只顯式對映固定 Secret / Variable 名稱，不會自動把 `STOCK_GROUP_1`、`EMAIL_GROUP_1` 這類任意編號變數匯入執行環境。所以分組郵箱功能目前不適用於倉庫自帶預設 GitHub Actions workflow；它適用於本地 `.env`、Docker，或你自行顯式擴充套件過 `env:` 對映的執行環境。Actions 已顯式對映 `CUSTOM_WEBHOOK_BODY_TEMPLATE`、`WEBHOOK_VERIFY_SSL`、`FEISHU_WEBHOOK_SECRET`、`FEISHU_WEBHOOK_KEYWORD`、`PUSHPLUS_TOPIC`、`NTFY_URL`、`NTFY_TOKEN`、`GOTIFY_URL`、`GOTIFY_TOKEN`、P3 通知路由鍵以及 P4 通知降噪鍵；`MARKDOWN_TO_IMAGE_CHANNELS` 和 `MERGE_EMAIL_NOTIFICATION` 仍作為行為開關不在預設 workflow 中自動對映。

#### 推送行為配置

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `SINGLE_STOCK_NOTIFY` | 單股推送模式：設為 `true` 則每分析完一隻股票立即推送 | 可選 |
| `REPORT_TYPE` | 報告型別：`simple`(精簡)、`full`(完整)、`brief`(3-5句概括)，Docker環境推薦設為 `full` | 可選 |
| `REPORT_LANGUAGE` | 報告輸出語言：`zh`(預設中文) / `en`(英文)；會同步影響 Prompt、模板、通知 fallback 與 Web 報告頁固定文案。倉庫自帶 `00-daily-analysis.yml` 已顯式對映該變數，直接在 Actions Secrets/Variables 中配置即可生效 | 可選 |
| `REPORT_SUMMARY_ONLY` | 僅分析結果摘要：設為 `true` 時只推送彙總，不含個股詳情；多股時適合快速瀏覽（預設 false，Issue #262） | 可選 |
| `REPORT_SHOW_LLM_MODEL` | 通知報告底部是否顯示本次分析使用的 LLM 模型名稱，預設 `true`；設為 `false` 可隱藏執行時模型資訊。該變數僅調整展示，不影響 provider/model/Base URL、LiteLLM 路由或執行時模型儲存/遷移/清理語義。 | 可選 |
| `REPORT_TEMPLATES_DIR` | Jinja2 模板目錄（相對專案根，預設 `templates`） | 可選 |
| `REPORT_RENDERER_ENABLED` | 啟用 Jinja2 模板渲染（預設 `false`，保證零迴歸） | 可選 |
| `REPORT_INTEGRITY_ENABLED` | 啟用報告完整性校驗，缺失必填欄位時重試或佔位補全（預設 `true`） | 可選 |
| `REPORT_INTEGRITY_RETRY` | 完整性校驗重試次數（預設 `1`，`0` 表示僅佔位不重試） | 可選 |
| `REPORT_HISTORY_COMPARE_N` | 歷史訊號對比條數，`0` 關閉（預設），`>0` 啟用 | 可選 |
| `ANALYSIS_DELAY` | 個股分析和大盤分析之間的延遲（秒），避免API限流，如 `10` | 可選 |
| `MERGE_EMAIL_NOTIFICATION` | 個股與大盤覆盤合併推送（預設 false），減少郵件數量、降低垃圾郵件風險；與 `SINGLE_STOCK_NOTIFY` 互斥（單股模式下合併不生效） | 可選 |
| `MARKDOWN_TO_IMAGE_CHANNELS` | 將 Markdown 轉為圖片傳送的通道（用逗號分隔）：telegram,wechat,custom,email,slack；單股推送需同時配置且安裝轉圖工具 | 可選 |
| `NOTIFICATION_REPORT_CHANNELS` | report 路由通道（單股推送、聚合日報、大盤覆盤、合併推送等）；留空表示所有已配置通道 | 可選 |
| `NOTIFICATION_ALERT_CHANNELS` | alert 路由通道（EventMonitor 警告）；留空表示所有已配置通道 | 可選 |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | system_error 預留路由通道；當前不新增自動系統錯誤生產者，留空表示所有已配置通道 | 可選 |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | 通知去重 TTL 秒數，`0` 關閉；同一穩定去重 key 在 TTL 內只傳送一次 | 可選 |
| `NOTIFICATION_COOLDOWN_SECONDS` | 通知冷卻秒數，`0` 關閉；同一冷卻 key 在視窗內限頻 | 可選 |
| `NOTIFICATION_QUIET_HOURS` | 通知靜默時段，格式 `HH:MM-HH:MM`，支援跨午夜；留空關閉 | 可選 |
| `NOTIFICATION_TIMEZONE` | 靜默時段使用的 IANA 時區，如 `Asia/Shanghai`；留空跟隨 `TZ` 或系統本地時區 | 可選 |
| `NOTIFICATION_MIN_SEVERITY` | 最低通知級別：`info`、`warning`、`error`、`critical`；留空保持現狀 | 可選 |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | 每日摘要預留開關；當前不會傳送摘要或持久化摘要內容 | 可選 |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | 超過此長度不轉圖片，避免超大圖片（預設 15000） | 可選 |
| `MD2IMG_ENGINE` | 轉圖引擎：`wkhtmltoimage`（預設，需 wkhtmltopdf）或 `markdown-to-file`（emoji 更好，需 `npm i -g markdown-to-file`） | 可選 |
| `PREFETCH_REALTIME_QUOTES` | 設為 `false` 可禁用實時行情預取，避免 efinance/akshare_em 全市場拉取（預設 true） | 可選 |

> 相容性說明：`REPORT_SHOW_LLM_MODEL` 維持預設 `true` 的原始展示語義，關閉時隻影響底部模型文案輸出。該配置不會變更 provider/model/Base URL、LiteLLM 路由、模型儲存、遷移或清理語義；回退方式為恢復或刪除該變數，並設為 `true`。

#### 其他配置

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `STOCK_LIST` | 自選股程式碼，如 `2330,2454,AAPL,NVDA` | ✅ |
| `ANSPIRE_API_KEYS` | [Anspire AI Search](https://aisearch.anspire.cn/) 針對中文內容特別最佳化；同一 Key 可用於搜尋與 Anspire 大模型閘道器的兜底示例（是否可用以控制檯與賬號許可權為準） | 推薦 |
| `SERPAPI_API_KEYS` | [SerpAPI](https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis) 搜尋引擎結果補強，適合實時金融新聞 | 推薦 |
| `TAVILY_API_KEYS` | [Tavily](https://tavily.com/) 搜尋 API（新聞搜尋） | 可選 |
| `BOCHA_API_KEYS` | [博查搜尋](https://open.bocha.cn/) Web Search API（中文搜尋最佳化，支援AI摘要，多個key用逗號分隔） | 可選 |
| `BRAVE_API_KEYS` | [Brave Search](https://brave.com/search/api/) API（隱私優先，美股最佳化，多個key用逗號分隔） | 可選 |
| `MINIMAX_API_KEYS` | [MiniMax](https://platform.minimax.io/) Coding Plan Web Search（結構化搜尋結果） | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項（無配額兜底，需在 settings.yml 啟用 format: json）；server-safe/local-only 模式僅允許 loopback 例項 | 可選 |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | 是否在 `SEARXNG_BASE_URLS` 為空時自動從 `searx.space` 獲取公共例項（預設 `false`，fail-closed） | 可選 |
| `TUSHARE_TOKEN` | [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) Token | 可選 |
| `LONGBRIDGE_OAUTH_CLIENT_ID` | [Longbridge OpenAPI](https://open.longbridge.com/) OAuth client_id；留空且無 Legacy Access Token 時會相容使用 `LONGBRIDGE_APP_KEY` | 可選 |
| `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64` | OAuth token 快取檔案的 base64 內容，供 GitHub Actions / Docker 等 headless 環境恢復 SDK token 快取 | 可選 |
| `LONGBRIDGE_APP_KEY` | Longbridge Legacy App Key；無 `LONGBRIDGE_ACCESS_TOKEN` 時也可作為 OAuth client_id 相容別名 | 可選 |
| `LONGBRIDGE_APP_SECRET` | Longbridge App Secret | 可選 |
| `LONGBRIDGE_ACCESS_TOKEN` | Longbridge Legacy Access Token（不是 OAuth access token） | 可選 |
| `LONGBRIDGE_STATIC_INFO_TTL_SECONDS` | 長橋 `static_info` 程序內快取秒數（預設 86400，0=不快取） | 可選 |
| `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` | 長橋連線關閉類異常後的冷卻秒數（預設 15；冷卻期內臨時跳過 Longbridge，避免頻繁重連） | 可選 |
| `LONGBRIDGE_HTTP_URL` | HTTP 介面地址（預設 `https://openapi.longbridge.com`） | 可選 |
| `LONGBRIDGE_QUOTE_WS_URL` | 行情 WebSocket 地址（預設 `wss://openapi-quote.longbridge.com/v2`） | 可選 |
| `LONGBRIDGE_TRADE_WS_URL` | 交易 WebSocket 地址（預設 `wss://openapi-trade.longbridge.com/v2`） | 可選 |
| `LONGBRIDGE_REGION` | 覆蓋接入點；SDK 會按網路自動選擇，預設 `hk`，若判斷不正確可設定（如 `cn`、`hk`） | 可選 |
| `LONGBRIDGE_ENABLE_OVERNIGHT` | 是否開啟夜盤行情 `true` / `false`，預設 `false` | 可選 |
| `LONGBRIDGE_PUSH_CANDLESTICK_MODE` | K 線推送模式：`realtime` 或 `confirmed`（預設 `realtime`） | 可選 |
| `LONGBRIDGE_PRINT_QUOTE_PACKAGES` | 連線時是否列印行情包（未設定時預設 `false`；設為 `1`/`true`/`yes` 開啟） | 可選 |
| `ENABLE_CHIP_DISTRIBUTION` | 啟用籌碼分佈（Actions 預設 false；需籌碼資料時在 Variables 中設為 true，介面可能不穩定） | 可選 |

> **GitHub Actions：** 倉庫自帶 `00-daily-analysis.yml` 已把上表中的 `LONGBRIDGE_*` 對映到任務環境。OAuth 方式需要一個 client_id（優先 `LONGBRIDGE_OAUTH_CLIENT_ID`；留空且無 Legacy Access Token 時使用 `LONGBRIDGE_APP_KEY` 相容），並把本機 `~/.longbridge/openapi/tokens/<client_id>` 檔案 base64 後儲存為 Secret `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64`；Legacy 方式仍可配置 `LONGBRIDGE_APP_KEY`、`LONGBRIDGE_APP_SECRET`、`LONGBRIDGE_ACCESS_TOKEN`。可選接入點變數（如 `LONGBRIDGE_REGION`）可放在 **Variables** 或 **Secrets**。

> **Longbridge 執行時行為：** 未配置憑據時不會例項化 Longbridge 這個可選 fetcher；若執行時遇到 `client is closed`、`context closed`、`connection closed` 等連線關閉類異常，會進入冷卻期（預設 15 秒，可用 `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` 調整），冷卻期內美股/港股的實時與日線請求會自動跳過 Longbridge，退回 YFinance / AkShare 等兜底鏈路。

> 補充說明
- TUSHARE_TOKEN，當此引數配置後，但不具備港股日線介面許可權時，也會出現港股資料查詢不出來或者錯誤的情況，和老版本提示不支援港股效果相同

#### ✅ 最小配置示例

如果你想快速開始，最少需要配置以下項：

1. **AI 模型**：`ANSPIRE_API_KEYS`（一 Key 同時啟用大模型和搜尋）、`AIHUBMIX_KEY`（[AIHubmix](https://aihubmix.com/?aff=CfMq)，一 Key 多模型）、`GEMINI_API_KEY` 或 `OPENAI_API_KEY`
2. **通知通道**：至少配置一個，如 `WECHAT_WEBHOOK_URL` 或 `EMAIL_SENDER` + `EMAIL_PASSWORD`
3. **股票列表**：`STOCK_LIST`（必填）
4. **搜尋 API**：`ANSPIRE_API_KEYS` 或 `SERPAPI_API_KEYS`（推薦，用於新聞與輿情搜尋）

> 💡 配置完以上 4 項即可開始使用！

### 3. 啟用 Actions

1. 進入你 Fork 的倉庫
2. 點選頂部的 `Actions` 標籤
3. 如果看到提示，點選 `I understand my workflows, go ahead and enable them`

### 4. 手動測試

1. 進入 `Actions` 標籤
2. 左側選擇 `每日股票分析` workflow
3. 點選右側的 `Run workflow` 按鈕
4. 選擇執行模式
5. 點選綠色的 `Run workflow` 確認

### 5. 完成！

預設每個工作日 **18:00（北京時間）** 自動執行。

---

## 環境變數完整列表

### AI 模型配置

> 完整說明見 [LLM 配置指南](LLM_CONFIG_GUIDE.md)（三層配置、通道模式、Vision、Agent、排錯）；常用服務商預設、Actions 變數對照和錯誤排障見 [LLM 服務商配置指南](llm-providers.md)。
> 相容性說明（Issue #1306/#1391）：本次改動只複用已有歷史寫入鏈路展示大盤覆盤結果，不修改模型名、provider、Base URL、`LiteLLM` 清理/相容語義。回退路徑為回滾本版本。相容驗證來源見 `requirements.txt`（`litellm` 版本約束）、`docs/LLM_CONFIG_GUIDE*.md`，以及迴歸用例 `tests/test_analysis_api_contract.py`、`tests/test_analysis_history.py`、`tests/test_market_review.py`；官方源參考：[LiteLLM OpenAI-compatible](https://docs.litellm.ai/docs/providers/openai_compatible)、[OpenAI Chat Completion API](https://platform.openai.com/docs/api-reference/chat)。
> #1391 Phase 2 的結構化檢測風險來自 `src/agent/factory.py` 的 `agent_max_steps` / `agent_orchestrator_timeout_s` int 安全兜底，屬於配置讀取側的型別相容增強，不會改寫 `litellm_model`、`agent_litellm_model`、`openai_base_url` 或 `LLM_*` 路由狀態；迴歸可複核 `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_does_not_mutate_llm_route_config` 與 `tests/test_agent_pipeline.py::TestAgentConfig::test_build_agent_executor_multi_arch_does_not_mutate_llm_route_config`。當配置值非法（如非數字）時，`src.agent.factory` 會記錄 warning 並回退到預設值，便於排障與避免誤判配置已生效。
> 本節僅同步模型/通道配置清單，不額外引入新的外部 provider / Base URL 相容約定；相容語義以當前倉庫 `requirements.txt` 依賴約束和相關測試為準，歷史回退路徑見上述兩份文件中“回退/恢復”說明。

| 變數名 | 說明 | 預設值 | 必填 |
|--------|------|--------|:----:|
| `LITELLM_MODEL` | 主模型，格式 `provider/model`（如 `gemini/gemini-3.1-pro-preview`），推薦優先使用 | - | 否 |
| `AGENT_LITELLM_MODEL` | Agent 主模型（可選）；留空繼承主模型，無 provider 字首按 `openai/<model>` 解析 | - | 否 |
| `AGENT_CONTEXT_COMPRESSION_ENABLED` | 問股可見對話上下文壓縮開關；預設關閉，開啟後僅壓縮 `session_id` 下 user/assistant 文字歷史 | `false` | 否 |
| `AGENT_CONTEXT_COMPRESSION_PROFILE` | 問股上下文壓縮策略：`cost` / `balanced` / `long_context_raw_first` | `balanced` | 否 |
| `AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS` | 歷史 token 估算超過該值時觸發壓縮；留空則跟隨 profile preset | - | 否 |
| `AGENT_CONTEXT_PROTECTED_TURNS` | 壓縮時最近 N 個使用者輪次及其後的回覆保留原文；留空則跟隨 profile preset | - | 否 |
| `LITELLM_FALLBACK_MODELS` | 備選模型，逗號分隔 | - | 否 |
| `LLM_CHANNELS` | 通道名稱列表（逗號分隔），配合 `LLM_{NAME}_*` 使用，詳見 [LLM 配置指南](LLM_CONFIG_GUIDE.md) | - | 否 |
| `LITELLM_CONFIG` | 高階模型路由 YAML 配置檔案路徑（高階） | - | 否 |
| `ANSPIRE_API_KEYS` | [Anspire](https://open.anspire.cn/?share_code=QFBC0FYC) API Key，一 Key 同時啟用大模型閘道器和搜尋 | - | 可選 |
| `AIHUBMIX_KEY` | [AIHubmix](https://aihubmix.com/?aff=CfMq) API Key，一 Key 切換使用全系模型，無需額外配置 Base URL | - | 可選 |
| `GEMINI_API_KEY` | Google Gemini API Key | - | 可選 |
| `GEMINI_MODEL` | 主模型名稱（legacy，`LITELLM_MODEL` 優先） | `gemini-3.1-pro-preview` | 否 |
| `GEMINI_MODEL_FALLBACK` | 備選模型（legacy） | `gemini-3-flash-preview` | 否 |
| `OPENAI_API_KEY` | OpenAI 相容 API Key | - | 可選 |
| `OPENAI_BASE_URL` | OpenAI 相容 API 地址 | - | 可選 |
| `OLLAMA_API_BASE` | Ollama 本地服務地址（如 `http://localhost:11434`），詳見 [LLM 配置指南](LLM_CONFIG_GUIDE.md) | - | 可選 |
| `OPENAI_MODEL` | OpenAI 模型名稱（legacy，AIHubmix 使用者可填如 `gemini-3.1-pro-preview`、`gpt-5.5`） | `gpt-5.5` | 可選 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | - | 可選 |
| `ANTHROPIC_MODEL` | Claude 模型名稱 | `claude-sonnet-4-6` | 可選 |
| `ANTHROPIC_TEMPERATURE` | Claude 溫度引數（0.0-1.0） | `0.7` | 可選 |
| `ANTHROPIC_MAX_TOKENS` | Claude 響應最大 token 數 | `8192` | 可選 |

> *注：`ANSPIRE_API_KEYS`、`AIHUBMIX_KEY`、`GEMINI_API_KEY`、`ANTHROPIC_API_KEY`、`OPENAI_API_KEY` 或 `OLLAMA_API_BASE` 至少配置一個。`ANSPIRE_API_KEYS` 與 `AIHUBMIX_KEY` 無需配置 `OPENAI_BASE_URL`，系統自動適配。

> 問股 single-agent 路徑會在後臺為 DeepSeek V4 thinking + tool-call 儲存最近 3 條 provider trace，並按原時序回放 `reasoning_content` / tool 結果；該能力不新增配置項，不進入 Web 歷史 API，Claude extended thinking 僅覆蓋離線 plumbing，multi-agent trace 注入留作後續增強。

### 通知通道配置

更多通知配置基線、診斷和部署場景說明見 [通知專題文件](notifications.md)。

| 變數名 | 說明 | 必填 |
|--------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企業微信機器人 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_URL` | 飛書機器人 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_SECRET` | 飛書機器人簽名金鑰（僅在機器人安全設定啟用“簽名校驗”時填寫） | 可選 |
| `FEISHU_WEBHOOK_KEYWORD` | 飛書機器人關鍵詞（僅在機器人安全設定啟用“關鍵詞”時填寫） | 可選 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 可選 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID | 可選 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | 可選 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token（與 Webhook 二選一） | 可選 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID（使用 Bot 時需要） | 可選 |
| `DISCORD_INTERACTIONS_PUBLIC_KEY` | Discord Public Key（僅入站 Interaction/Webhook 回撥驗籤時需要） | 可選 |
| `DISCORD_MAX_WORDS` | Discord 最大字數限制（預設 免費伺服器限制2000） | 可選 |
| `SLACK_BOT_TOKEN` | Slack Bot Token（推薦，支援圖片上傳；同時配置時優先於 Webhook） | 可選 |
| `SLACK_CHANNEL_ID` | Slack Channel ID（使用 Bot 時需要） | 可選 |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL（僅文字，不支援圖片） | 可選 |
| `EMAIL_SENDER` | 發件人郵箱 | 可選 |
| `EMAIL_PASSWORD` | 郵箱授權碼（非登入密碼） | 可選 |
| `EMAIL_RECEIVERS` | 收件人郵箱（逗號分隔，留空發給自己） | 可選 |
| `EMAIL_SENDER_NAME` | 發件人顯示名稱 | 可選 |
| `STOCK_GROUP_N` / `EMAIL_GROUP_N` | 郵件分組路由（Issue #268）：`STOCK_GROUP_N` 應為 `STOCK_LIST` 子集，僅影響郵件收件人，不改變分析範圍或其他通知通道 | 可選 |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（逗號分隔） | 可選 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定義 Webhook Bearer Token | 可選 |
| `WEBHOOK_VERIFY_SSL` | 讀取該配置的 webhook-style HTTPS 通知請求證書校驗（預設 true）。設為 false 可支援自簽名。警告：關閉有嚴重安全風險 | 可選 |
| `PUSHOVER_USER_KEY` | Pushover 使用者 Key | 可選 |
| `PUSHOVER_API_TOKEN` | Pushover API Token | 可選 |
| `NTFY_URL` | ntfy 完整 topic endpoint，必須包含 topic path，例如 `https://ntfy.sh/my-topic` | 可選 |
| `NTFY_TOKEN` | ntfy Bearer Token（可選） | 可選 |
| `GOTIFY_URL` | Gotify server base URL，不包含 `/message` | 可選 |
| `GOTIFY_TOKEN` | Gotify application token，透過 `X-Gotify-Key` Header 傳送 | 可選 |
| `PUSHPLUS_TOKEN` | PushPlus Token（國內推送服務） | 可選 |
| `SERVERCHAN3_SENDKEY` | Server醬³ Sendkey | 可選 |
| `ASTRBOT_URL` | AstrBot Webhook URL | 可選 |
| `ASTRBOT_TOKEN` | AstrBot Bearer Token（可選） | 可選 |
| `NOTIFICATION_REPORT_CHANNELS` | report 路由通道，逗號分隔；允許值：wechat,feishu,telegram,email,pushover,ntfy,gotify,pushplus,serverchan3,custom,discord,slack,astrbot | 可選 |
| `NOTIFICATION_ALERT_CHANNELS` | alert 路由通道，逗號分隔；留空保持全通道 | 可選 |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | system_error 預留路由通道，逗號分隔；留空保持全通道 | 可選 |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | 通知去重 TTL 秒數，`0` 關閉 | 可選 |
| `NOTIFICATION_COOLDOWN_SECONDS` | 通知冷卻秒數，`0` 關閉 | 可選 |
| `NOTIFICATION_QUIET_HOURS` | 靜默時段，格式 `HH:MM-HH:MM`，支援跨午夜 | 可選 |
| `NOTIFICATION_TIMEZONE` | 靜默時段時區，如 `Asia/Shanghai`；留空跟隨 `TZ` 或系統本地時區 | 可選 |
| `NOTIFICATION_MIN_SEVERITY` | 最低通知級別：info, warning, error, critical；留空保持現狀 | 可選 |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | 每日摘要預留開關；當前不會傳送摘要 | 可選 |

> 說明：預設 `00-daily-analysis.yml` GitHub Actions workflow 只對映固定變數名，不會自動匯入任意編號的 `STOCK_GROUP_N` / `EMAIL_GROUP_N`。因此分組郵箱目前僅在本地 `.env`、Docker 或其他已顯式注入這些環境變數的執行環境中生效；若你要在自己的 GitHub Actions 中使用，需在 workflow 的 job `env:` 中逐組顯式對映。

#### 飛書雲文件配置（可選，解決訊息截斷問題）

| 變數名 | 說明 | 必填 |
|--------|------|:----:|
| `FEISHU_APP_ID` | 飛書應用 ID | 可選 |
| `FEISHU_APP_SECRET` | 飛書應用 Secret | 可選 |
| `FEISHU_FOLDER_TOKEN` | 飛書雲盤資料夾 Token | 可選 |

> 飛書雲文件配置步驟：
> 1. 在 [飛書開發者後臺](https://open.feishu.cn/app) 建立應用
> 2. 配置 GitHub Secrets
> 3. 建立群組並新增應用機器人
> 4. 在雲盤資料夾中新增群組為協作者（可管理許可權）
>
> 說明：`FEISHU_APP_ID` / `FEISHU_APP_SECRET` 用於飛書應用、雲文件或 Stream Bot 模式，不會直接啟用群 Webhook 推送。只想收通知時，請優先配置 `FEISHU_WEBHOOK_URL`。

### 搜尋服務配置

| 變數名 | 說明 | 必填 |
|--------|------|:----:|
| `ANSPIRE_API_KEYS` | Anspire Open API Key（可用於搜尋與大模型閘道器共享場景的配置示例；是否可用取決於賬號許可權與閘道器可見性，可有效增強 A 股分析效果） | 推薦 |
| `SERPAPI_API_KEYS` | SerpAPI 搜尋引擎結果補強，適合實時金融新聞 | 推薦 |
| `TAVILY_API_KEYS` | Tavily 搜尋 API Key | 可選 |
| `BOCHA_API_KEYS` | 博查搜尋 API Key（中文最佳化） | 可選 |
| `BRAVE_API_KEYS` | Brave Search API Key（美股最佳化） | 可選 |
| `MINIMAX_API_KEYS` | MiniMax Coding Plan Web Search（結構化搜尋結果） | 可選 |
| `SOCIAL_SENTIMENT_API_KEY` | Stock Sentiment API Key（Reddit / X / Polymarket，可選） | 可選 |
| `SOCIAL_SENTIMENT_API_URL` | Stock Sentiment API 地址（預設 `https://api.adanos.org`） | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項（無配額兜底，需在 settings.yml 啟用 format: json）；server-safe/local-only 模式僅允許 loopback 例項 | 可選 |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | 是否在 `SEARXNG_BASE_URLS` 為空時自動從 `searx.space` 獲取公共例項（預設 `false`，fail-closed） | 可選 |
| `NEWS_STRATEGY_PROFILE` | 新聞策略視窗檔位：`ultra_short`(1天)/`short`(3天)/`medium`(7天)/`long`(30天)；實際視窗取與 `NEWS_MAX_AGE_DAYS` 的最小值 | 預設 `short` |
| `NEWS_MAX_AGE_DAYS` | 新聞最大時效（天），搜尋時限制結果在近期內 | 預設 `3` |
| `BIAS_THRESHOLD` | 乖離率閾值（%），超過提示不追高；強勢趨勢股自動放寬到 1.5 倍 | 預設 `5.0` |

> 行為說明：搜尋服務與社交輿情服務為可選增強鏈路。任一服務初始化失敗時，系統會記錄 warning 並降級為跳過該服務，僅影響對應環節，不會阻塞技術面主鏈路和主任務流。

### 新聞檢索可解釋排序（Issue #1356）

`search_stock_news` 對每條候選新聞會計算「可解釋相關度」並落地為 3 類標籤：

- `direct_company_news`：命中目的碼、公司名（含官方/交易所來源加權）；
- `sector_related_news`：命中行業板塊語義；
- `macro_market_news`：未命中目標主體時的宏觀/市場語境新聞。

排序策略為：先按類別優先順序（direct > sector > macro）排序，再按語言偏好（中文優先）再按分數排序，因此當同一時窗記憶體在明確標的命中的新聞時會優先展示。

除錯入口：

- 每條返回會保留 `relevance_score` / `relevance_category` / `relevance_reasons` 後設資料，最終 `to_text()` 與情報上下文會附帶對應「關聯度」說明；
- 搜尋鏈路日誌會輸出 `[新聞相關度]` 統計，便於覆盤為何該批次觸發了 direct/sector/macro 分層。

相容與回退說明：該改動不新增/修改模型、provider、Base URL、LiteLLM route、配置清理或回寫邏輯；若出現異常，只能透過回滾本次提交恢復舊排序行為，不涉及歷史配置遷移。

### 資料來源配置

| 變數名 | 說明 | 預設值 | 必填 |
|--------|------|--------|:----:|
| `TUSHARE_TOKEN` | Tushare Pro Token | - | 可選 |
| `TICKFLOW_API_KEY` | TickFlow API Key；配置後 A 股大盤覆盤指數優先嚐試 TickFlow，若套餐支援標的池查詢則市場統計也會優先嚐試 TickFlow | - | 可選 |
| `LONGBRIDGE_OAUTH_CLIENT_ID` | Longbridge OAuth client_id；留空且無 Legacy Access Token 時會相容使用 `LONGBRIDGE_APP_KEY` | - | 可選 |
| `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64` | OAuth token 快取檔案的 base64 內容，供 GitHub Actions / Docker 等 headless 環境使用 | - | 可選 |
| `LONGBRIDGE_APP_KEY` | Longbridge Legacy App Key；無 `LONGBRIDGE_ACCESS_TOKEN` 時也可作為 OAuth client_id 相容別名 | - | 可選 |
| `LONGBRIDGE_APP_SECRET` | Longbridge App Secret | - | 可選 |
| `LONGBRIDGE_ACCESS_TOKEN` | Longbridge Legacy Access Token（不是 OAuth access token） | - | 可選 |
| `LONGBRIDGE_*`（可選） | 見官方 [環境變數](https://open.longbridge.com/zh-CN/docs/getting-started#環境變數)；另有 `LONGBRIDGE_STATIC_INFO_TTL_SECONDS` 與 `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` | - | 可選 |
| `ENABLE_REALTIME_QUOTE` | 啟用實時行情（關閉後使用歷史收盤價分析） | `true` | 可選 |
| `ENABLE_REALTIME_TECHNICAL_INDICATORS` | 盤中實時技術面：啟用時用實時價計算 MA5/MA10/MA20 與多頭排列（Issue #234）；關閉則用昨日收盤 | `true` | 可選 |
| `ENABLE_CHIP_DISTRIBUTION` | 啟用籌碼分佈分析（該介面不穩定，雲端部署建議關閉）。GitHub Actions 使用者需在 Repository Variables 中設定 `ENABLE_CHIP_DISTRIBUTION=true` 方可啟用；workflow 預設關閉。 | `true` | 可選 |
| `ENABLE_EASTMONEY_PATCH` | 東財介面補丁：東財介面頻繁失敗（如 RemoteDisconnected、連線被關閉）時建議設為 `true`，注入 NID 令牌與隨機 User-Agent 以降低被限流機率 | `false` | 可選 |
| `REALTIME_SOURCE_PRIORITY` | 實時行情資料來源優先順序（逗號分隔），如 `tencent,akshare_sina,efinance,akshare_em` | 見 .env.example | 可選 |
| `ENABLE_FUNDAMENTAL_PIPELINE` | 基本面聚合總開關；關閉時僅返回 `not_supported` 塊，不改變原分析鏈路 | `true` | 可選 |
| `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` | 基本面階段總時延預算（秒） | `8.0` | 可選 |
| `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS` | 單能力源呼叫超時（秒） | `3.0` | 可選 |
| `FUNDAMENTAL_RETRY_MAX` | 基本面能力重試次數（含首次） | `1` | 可選 |
| `FUNDAMENTAL_CACHE_TTL_SECONDS` | 基本面聚合快取 TTL（秒），短快取減輕重複拉取 | `120` | 可選 |
| `FUNDAMENTAL_CACHE_MAX_ENTRIES` | 基本面快取最大條目數（TTL 內按時間淘汰） | `256` | 可選 |

> 行為說明：
> - A 股：按 `valuation/growth/earnings/institution/capital_flow/dragon_tiger/boards` 聚合能力返回；
> - ETF：返回可得項，缺失能力標記為 `not_supported`，整體不影響原流程；
> - 美股/港股：透過 yfinance 介面卡返回 `valuation/growth/earnings/belong_boards`（來源 `info.sector`/`industry`），`institution/capital_flow/dragon_tiger/boards` 暫無對應資料來源仍標記 `not_supported`；yfinance 不可用或欄位缺失時整體降級回 `not_supported`，仍走 fail-open；
> - 任何異常走 fail-open，僅記錄錯誤，不影響技術面/新聞/籌碼主鏈路。
> - 配置 `TICKFLOW_API_KEY` 後，僅 A 股大盤覆盤會額外優先嚐試 TickFlow 的主要指數行情；若當前套餐支援標的池查詢，市場漲跌統計也會優先嚐試 TickFlow。個股鏈路和實時行情優先順序不變。
> - TickFlow 能力按套餐許可權分層：有限許可權套餐仍可使用主指數查詢；支援 `CN_Equity_A` 標的池查詢的套餐才會啟用 TickFlow 市場統計。
> - 官方 quickstart 已文件化 `quotes.get(universes=["CN_Equity_A"])`，但線上 smoke test 進一步確認：`TICKFLOW_API_KEY` 不等於一定具備該許可權，且 `quotes.get(symbols=[...])` 單次存在標的數量限制。
> - TickFlow 實際返回的 `change_pct` / `amplitude` 為比例值；系統已在接入層統一轉換為百分比值，確保與現有資料來源欄位語義一致。
> - A 股大盤覆盤報告採用盤後工作臺式結構：固定包含盤面訊號、指數明細、板塊 Top 表、近三日市場線索、明日交易計劃和風險提示；盤面訊號以 `66/100（偏暖，可進攻）` 這類純文字分數表達，避免色塊進度條在不同終端顯示不一致；近三日市場線索只列標題、來源和連結，不再展示搜尋摘要片段；若部分資料來源缺失，則保留可用區塊並在對應位置降級展示。
> - 欄位契約：
>   - `fundamental_context.belong_boards` = 個股關聯板塊列表；A 股從 AkShare 板塊名單寫入，美股/港股從 yfinance `info.sector` / `info.industry` 寫入，無資料時為 `[]`；
>   - `fundamental_context.boards.data` = `sector_rankings`（板塊漲跌榜，結構 `{top, bottom}`，HK/US 當前不提供）；
>   - `fundamental_context.earnings.data.financial_report` = 財報摘要（報告期、營收、歸母淨利潤、經營現金流、ROE，及 `currency` 來源 `info.financialCurrency`，HK ADR 常見為 CNY）；
>   - `fundamental_context.earnings.data.dividend` = 分紅指標（僅現金分紅稅前口徑，含 `events`、`ttm_cash_dividend_per_share`、`ttm_dividend_yield_pct`、`currency`）。`currency` 獨立讀取自 `info.currency`，與 `financial_report.currency` 可能不同（HK ADR 財報 CNY、分紅 HKD）；TTM yield 預設按 `ttm_cash / latest_price * 100`（同幣種）即時重算，僅在 TTM cash 或 latest price 缺失時回退到 yfinance `trailingAnnualDividendYield` 或 `dividendYield`；
>   - `get_stock_info.belong_boards` = 個股所屬板塊列表；
>   - `get_stock_info.boards` 為相容別名，值與 `belong_boards` 相同（未來僅在大版本考慮移除）；
>   - `get_stock_info.sector_rankings` 與 `fundamental_context.boards.data` 保持一致。
>   - `AnalysisReport.details.belong_boards` = 結構化報告詳情中的關聯板塊列表；
>   - `AnalysisReport.details.sector_rankings` = 結構化報告詳情中的板塊漲跌榜（用於前端板塊聯動展示）。
> - 板塊漲跌榜使用資料來源順序：與全域性 priority 一致。
> - 超時控制為 `best-effort` 軟超時：階段會按預算快速降級繼續執行，但不保證硬中斷底層三方呼叫。
> - `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS=8.0` 表示新增基本面階段的目標預算，不是嚴格硬 SLA；Windows、Docker 或免費資料來源被限流時可繼續調高到 `12-15s`。
> - 若要硬 SLA，請在後續版本升級為子程序隔離執行並在超時後強制終止。

### 其他配置

| 變數名 | 說明 | 預設值 |
|--------|------|--------|
| `STOCK_LIST` | 自選股程式碼（逗號分隔） | - |
| `ADMIN_AUTH_ENABLED` | Web 登入：設為 `true` 啟用密碼保護；首次訪問在網頁設定初始密碼，可在「系統設定 > 修改密碼」修改；忘記密碼執行 `python -m src.auth reset_password`。Web 的 `.env` 備份匯入匯出僅在開啟該開關後可用（桌面端不受此限制）。 | `false` |
| `TRUST_X_FORWARDED_FOR` | 單層可信反向代理部署時設為 `true`，取 `X-Forwarded-For` 最右值作為真實客戶端 IP（用於登入限流等）；直連公網時保持 `false` 防偽造。多級代理/CDN 場景下限流 key 可能退化為邊緣代理 IP，需額外評估 | `false` |
| `MAX_WORKERS` | 併發執行緒數 | `3` |
| `MARKET_REVIEW_ENABLED` | 啟用大盤覆盤 | `true` |
| `MARKET_REVIEW_REGION` | 大盤覆盤市場區域：cn(A股)、hk(港股)、us(美股)、both(三市場)，us 適合僅關注美股的使用者 | `cn` |
| `MARKET_REVIEW_COLOR_SCHEME` | 大盤覆盤指數漲跌顏色：`green_up`=綠漲紅跌（預設），`red_up`=紅漲綠跌 | `green_up` |
| `TRADING_DAY_CHECK_ENABLED` | 交易日檢查：預設 `true`，非交易日跳過執行；設為 `false` 或使用 `--force-run` 可強制執行（Issue #373） | `true` |
| `SCHEDULE_ENABLED` | 啟用定時任務 | `false` |
| `SCHEDULE_TIME` | 定時執行時間 | `18:00` |
| `LOG_DIR` | 日誌目錄 | `./logs` |

---

## Docker 部署

Dockerfile 使用多階段構建，前端會在構建映象時自動打包並內建到 `static/`。
如需覆蓋靜態資源，可掛載本地 `static/` 到容器內 `/app/static`。
執行中的 `server` 容器預設直接複用 `/app/static` 裡的預構建產物，不要求容器內保留 `apps/dsa-web` 原始碼目錄或執行時安裝 `npm`；若 WebUI 無法開啟，請優先確認 `/app/static/index.html` 是否存在。

當前官方映象釋出地址：

- GHCR：`ghcr.io/zhulinsen/daily_stock_analysis:<tag>`
- Docker Hub：`<DOCKERHUB_USERNAME>/daily_stock_analysis:<tag>`（由釋出者的 `DOCKERHUB_USERNAME` secret 決定，官方釋出為 `zhulinsen/daily_stock_analysis`）

### 快速啟動

```bash
# 1. 克隆倉庫
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

# 2. 配置環境變數
cp .env.example .env
vim .env  # 填入 API Key 和配置

# 3. 啟動容器
docker-compose -f ./docker/docker-compose.yml up -d server     # Web 服務模式（推薦，提供 API 與 WebUI）
docker-compose -f ./docker/docker-compose.yml up -d analyzer   # 定時任務模式
docker-compose -f ./docker/docker-compose.yml up -d            # 同時啟動兩種模式

# 4. 訪問 WebUI
# http://localhost:8000

# 5. 檢視日誌
docker-compose -f ./docker/docker-compose.yml logs -f server
```

### 直接拉官方映象執行

如果你不打算在目標機器上保留原始碼，可以直接拉取官方映象：

```bash
# Web/API 模式
docker pull zhulinsen/daily_stock_analysis:latest
docker run -d \
  --name dsa-server \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/reports:/app/reports" \
  zhulinsen/daily_stock_analysis:latest \
  python main.py --serve-only --host 127.0.0.1 --port 8000

# 定時任務模式
docker run -d \
  --name dsa-analyzer \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/reports:/app/reports" \
  zhulinsen/daily_stock_analysis:latest
```

如需固定版本或便於回滾，請將 `latest` 替換為具體版本 tag，例如 `v3.13.0`。

### 執行模式說明

| 命令 | 說明 | 埠 |
|------|------|------|
| `docker-compose -f ./docker/docker-compose.yml up -d server` | Web 服務模式，提供 API 與 WebUI | 8000 |
| `docker-compose -f ./docker/docker-compose.yml up -d analyzer` | 定時任務模式，每日自動執行 | - |
| `docker-compose -f ./docker/docker-compose.yml up -d` | 同時啟動兩種模式 | 8000 |

### Docker Compose 配置

`docker-compose.yml` 使用 YAML 錨點複用配置：

```yaml
version: '3.8'

x-common: &common
  build:
    context: ..
    dockerfile: docker/Dockerfile
  restart: unless-stopped
  env_file:
    - ../.env
  environment:
    - TZ=Asia/Shanghai
  volumes:
    - ../data:/app/data
    - ../logs:/app/logs
    - ../reports:/app/reports
    - ../strategies:/app/strategies:ro

services:
  # 定時任務模式
  analyzer:
    <<: *common
    container_name: stock-analyzer

  # FastAPI 模式
  server:
    <<: *common
    container_name: stock-server
    command: ["python", "main.py", "--serve-only", "--host", "127.0.0.1", "--port", "${API_PORT:-8000}"]
    ports:
      - "${API_PORT:-8000}:${API_PORT:-8000}"
```

### `.env` 與資料目錄對映說明

無論你使用 `docker run` 還是 Compose，都需要區分啟動環境變數注入和執行時檔案寫入：

- 環境變數注入：`--env-file .env` 或 Compose 的 `env_file`
  作用：把 `.env` 中的鍵值作為容器啟動時的環境變數傳入 Python 程序。
- 執行時配置寫入：不要把宿主機 `.env` 作為單檔案 bind mount 覆蓋容器內 `.env` 路徑。Docker 會把單檔案掛載目標作為 mount point，配置儲存時的 `os.replace()` 原子更新可能失敗並報 `Device or resource busy`，回退寫入也可能受許可權限制。

預設 Compose 和 `docker run` 示例僅使用 `env_file` / `--env-file` 注入啟動配置，不再把宿主機 `.env` 單檔案掛載進容器。WebUI 中儲存的執行時配置預設寫入容器內部配置檔案，不等同於回寫宿主機 `.env`；刪除或重建容器後仍以啟動時注入的 `.env` 為準。若需要持久化執行時配置，請將寫入目標放到可寫資料卷中（例如透過 `ENV_FILE=/app/data/runtime.env` 指向 `data` volume 中的檔案），不要使用 `.env` 單檔案 bind mount。

推薦同時對映這幾個目錄：

- `./data:/app/data`：資料庫、快取和執行時資料
- `./logs:/app/logs`：日誌輸出
- `./reports:/app/reports`：生成的分析報告
- `./strategies:/app/strategies:ro`：自定義策略 YAML（只讀掛載）

官方 Docker 映象啟動時會自動建立並修復 `/app/data`、`/app/logs`、`/app/reports` 的掛載目錄許可權，然後降權為容器內非 root 使用者 `dsa`（UID/GID `1000:1000`）執行應用。普通 Docker / Compose 部署不需要手動 `chown` 或 `chmod` 宿主機目錄。

如果你透過 `--user` 或 Compose `user:` 指定了其他執行使用者，或使用只讀掛載、rootless Docker、NFS 等限制 `chown` 的儲存環境，自動修復可能無法生效。此時請確保實際執行使用者對 `data`、`logs`、`reports` 具備寫入許可權，或改用可寫卷。

如果你需要覆蓋內建靜態資源，還可以額外掛載：

- `./static:/app/static:ro`

### 常用命令

```bash
# 檢視執行狀態
docker-compose -f ./docker/docker-compose.yml ps

# 檢視日誌
docker-compose -f ./docker/docker-compose.yml logs -f server

# 停止服務
docker-compose -f ./docker/docker-compose.yml down

# 重建映象（程式碼更新後）
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d server
```

### 手動構建映象

```bash
docker build -f docker/Dockerfile -t stock-analysis .
docker run -d \
  --name dsa-server-local \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/reports:/app/reports" \
  stock-analysis \
  python main.py --serve-only --host 127.0.0.1 --port 8000
```

---

## 本地執行詳細配置

### 安裝依賴

```bash
# Python 3.10+ 推薦
pip install -r requirements.txt

# 或使用 conda
conda create -n stock python=3.10
conda activate stock
pip install -r requirements.txt
```

#### FinMind live smoke 環境

FinMind 台股 live smoke 建議使用 Python 3.11 conda 環境：

```bash
conda create -n daily-stock python=3.11 -y
conda activate daily-stock
python -m pip install -r requirements.txt
python -m pip install "FinMind>=0.6.0"
```

不建議在 Python 3.12 環境中強裝 FinMind。FinMind 當前依賴 `pandas<2.0.0`，可能觸發 pandas 1.5.x source build，並在構建依賴階段失敗。

Windows PowerShell 若仍使用系統預設內碼表，首次安裝依賴或執行環境檢查前建議先啟用 UTF-8，避免第三方工具或終端輸出在中文字元上失敗：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
python -m pip install -r requirements.txt
python scripts/check_env.py --config
```

**智慧匯入依賴**：`pypinyin`（名稱→程式碼拼音匹配）和 `openpyxl`（Excel .xlsx 解析）已包含在 `requirements.txt` 中，執行上述 `pip install -r requirements.txt` 時會自動安裝。若使用智慧匯入（圖片/CSV/Excel/剪貼簿）功能，請確保依賴已正確安裝；缺失時可能報 `ModuleNotFoundError`。

### 命令列引數

```bash
python main.py                        # 完整分析（個股 + 大盤覆盤）
python main.py --market-review        # 僅大盤覆盤
python main.py --no-market-review     # 僅個股分析
python main.py --stocks 2330,AAPL     # 指定股票
python main.py --dry-run              # 僅獲取資料，不 AI 分析
python main.py --no-notify            # 不傳送推送
python main.py --schedule             # 定時任務模式
python main.py --force-run            # 非交易日也強制執行（Issue #373）
python main.py --debug                # 除錯模式（詳細日誌）
python main.py --workers 5            # 指定併發數
```

---

## 定時任務配置

### GitHub Actions 定時

編輯 `.github/workflows/00-daily-analysis.yml`:

```yaml
schedule:
  # UTC 時間，北京時間 = UTC + 8
  - cron: '0 10 * * 1-5'   # 週一到週五 18:00（北京時間）
```

常用時間對照：

| 北京時間 | UTC cron 表示式 |
|---------|----------------|
| 09:30 | `'30 1 * * 1-5'` |
| 12:00 | `'0 4 * * 1-5'` |
| 15:00 | `'0 7 * * 1-5'` |
| 18:00 | `'0 10 * * 1-5'` |
| 21:00 | `'0 13 * * 1-5'` |

#### GitHub Actions 非交易日手動執行（Issue #461 / #466）

`00-daily-analysis.yml` 支援兩種控制方式：

- `TRADING_DAY_CHECK_ENABLED`：倉庫級配置（`Settings → Secrets and variables → Actions`），預設 `true`
- `workflow_dispatch.force_run`：手動觸發時的單次開關，預設 `false`

推薦優先順序理解：

| 配置組合 | 非交易日行為 |
|---------|-------------|
| `TRADING_DAY_CHECK_ENABLED=true` + `force_run=false` | 跳過執行（預設行為） |
| `TRADING_DAY_CHECK_ENABLED=true` + `force_run=true` | 本次強制執行 |
| `TRADING_DAY_CHECK_ENABLED=false` + `force_run=false` | 始終執行（定時和手動都不檢查交易日） |
| `TRADING_DAY_CHECK_ENABLED=false` + `force_run=true` | 始終執行 |

手動觸發步驟：

1. 開啟 `Actions → 每日股票分析 → Run workflow`
2. 選擇 `mode`（`full` / `market-only` / `stocks-only`）
3. 若當天是非交易日且希望仍執行，將 `force_run` 設為 `true`
4. 點選 `Run workflow`

### 本地定時任務

內建的定時任務排程器支援每天在指定時間（預設 18:00）執行分析。

#### 命令列方式

```bash
# 啟動定時模式（啟動時立即執行一次，隨後每天 18:00 執行）
python main.py --schedule

# 啟動定時模式（啟動時不執行，僅等待下次定時觸發）
python main.py --schedule --no-run-immediately
```

> 說明：定時模式每次觸發前都會重新讀取當前儲存的 `STOCK_LIST`。如果同時傳入 `--stocks`，該引數不會鎖定後續計劃執行的股票列表；需要臨時只跑指定股票時，請使用非定時的單次執行命令。
>
> 從 `python main.py --schedule`、`python main.py --serve --schedule` 或等價內建排程模式啟動後，WebUI 儲存新的 `SCHEDULE_TIME` 會在下一輪排程檢查內自動重綁 daily job，無需重啟程序；舊的執行時間不會繼續保留。

#### 環境變數方式

你也可以透過環境變數配置定時行為（適用於 Docker 或 .env）：

| 變數名 | 說明 | 預設值 | 示例 |
|--------|------|:-------:|:-----:|
| `SCHEDULE_ENABLED` | 是否啟用定時任務 | `false` | `true` |
| `SCHEDULE_TIME` | 每日執行時間 (HH:MM) | `18:00` | `09:30` |
| `SCHEDULE_RUN_IMMEDIATELY` | 定時模式啟動時是否立即執行一次；未顯式設定時沿用 `RUN_IMMEDIATELY` 的執行時覆蓋語義 | `true` | `false` |
| `RUN_IMMEDIATELY` | 非定時模式啟動時是否立即執行一次；同時作為未顯式設定 `SCHEDULE_RUN_IMMEDIATELY` 時的 legacy 回退 | `true` | `false` |
| `TRADING_DAY_CHECK_ENABLED` | 交易日檢查：非交易日跳過執行；設為 `false` 可強制執行 | `true` | `false` |

例如在 Docker 中配置：

```bash
# 設定啟動時不立即分析
docker run -e SCHEDULE_ENABLED=true -e SCHEDULE_RUN_IMMEDIATELY=false ...
```

> 相容說明：如果執行時顯式傳入 `RUN_IMMEDIATELY`，但沒有單獨傳 `SCHEDULE_RUN_IMMEDIATELY`，內建排程模式會繼續繼承前者，避免被 `.env` 中持久化的 `SCHEDULE_RUN_IMMEDIATELY` 舊值反向覆蓋。

#### 交易日判斷（Issue #373）

預設根據自選股市場（A 股 / 港股 / 美股）和 `MARKET_REVIEW_REGION` 判斷是否為交易日：
- 使用 `exchange-calendars` 區分 A 股 / 港股 / 美股各自的交易日曆（含節假日）
- 混合持股時，每隻股票只在其市場開市日分析，休市股票當日跳過
- 全部相關市場均為非交易日時，整體跳過執行（不啟動 pipeline、不發推送）
- 斷點續傳和 `--dry-run` 的“資料已存在”判斷共用同一套“最新可複用交易日”解析邏輯，不再直接使用伺服器自然日
- `最新可複用交易日` 會按股票所屬市場的本地時區解析：A 股使用 `Asia/Shanghai`，港股使用 `Asia/Hong_Kong`，美股使用 `America/New_York`
- 非交易日（週末 / 節假日）執行時，會回退到最近一個交易日檢查本地資料；若該交易日資料已存在，則跳過重複抓取，否則繼續補數
- 交易日盤中或收盤前執行時，會以上一個已完成交易日作為複用目標；交易日收盤後執行時，當日資料已存在則可直接跳過，不存在則繼續抓取
- 覆蓋方式：`TRADING_DAY_CHECK_ENABLED=false` 或 命令列 `--force-run`

#### 市場階段基線（Issue #1386 P0）

P0 只新增內部市場階段推斷基線，不改變現有每日收盤報告、交易日跳過、斷點續傳、API、Web、Bot、Agent 或 GitHub Actions 預設行為。階段推斷用於後續 P1+ 的上下文契約準備；未安裝 `exchange-calendars` 或日曆異常時，階段返回 `unknown`，但現有交易日判斷和最新可複用交易日邏輯仍保持原來的 fail-open 行為。

階段列舉基於 regular session 語義：

| 階段 | 含義 |
| --- | --- |
| `premarket` | 常規交易時段開盤前；不代表已經獲取盤前擴充套件時段行情 |
| `intraday` | 常規交易時段內，且不處於午休或臨近收盤視窗 |
| `lunch_break` | 市場日曆提供的午間休市視窗；無午休市場不會進入此階段 |
| `closing_auction` | 臨近收盤啟發式視窗：A 股 3 分鐘、港股 10 分鐘、美股 5 分鐘；不代表完整交易所競價制度 |
| `postmarket` | 常規交易時段收盤後；不代表已經獲取盤後擴充套件時段行情 |
| `non_trading` | 當前市場本地日期不是交易日 |
| `unknown` | 未知市場、日曆不可用或日曆異常，無法可靠推斷階段 |

當前入口現狀：

- 普通個股分析、Agent 分析、Web 手動分析、Bot `/analyze` / `/ask`、schedule、GitHub Actions 仍沿用既有分析路徑和盤後覆盤口徑，不會因為 P0 階段基線自動切換 Prompt 或輸出結構。
- 大盤覆盤仍按 `MARKET_REVIEW_REGION` 與交易日過濾執行，不消費市場階段標籤。
- 跨市場混合自選股應按每個 symbol 自身市場分別推斷階段；聚合報告展示“多市場階段不一致”留給 P1+。

已知問題基線：

- 盤中觸發時，報告仍可能把尚未收盤的日內行情寫成完整交易日覆盤。
- 輸出仍可能偏向“今日走勢覆盤 / 明日關注”，而不是“當前盤中下一步觀察”。
- 實時行情時間戳、資料來源、快取和 stale 狀態還沒有統一進入階段上下文。
- 午間休市、臨近收盤、非交易日強制執行等場景還沒有被 Prompt 和報告結構顯式表達。

P0 不做：不接入 pipeline / Agent / API / Web / Bot，不修改報告 schema，不改警告 technical indicator 的 partial bar 判斷，也不新增配置項。

#### 執行態市場階段上下文（Issue #1386 P1a）

P1a 在普通個股分析 pipeline、legacy Agent context 和 multi-agent `ctx.meta` 中構造並傳遞內部 `market_phase_context`。該上下文包含市場、階段、市場本地日期、最新可複用日線日期、交易日/開市/partial bar 三態標記、開收盤分鐘數 best-effort 估算，以及 `unknown_market`、`calendar_unavailable`、`calendar_error` 等降級 warning code。

P1a 本身不改變 Prompt 文案、API/Web/Bot 引數、報告結構、history/task status 穩定 metadata 或 quote freshness/data quality 語義；普通分析 history snapshot 和 Agent history snapshot 會剝離該執行態欄位。後續 P1b 再定義可持久化 metadata 與任務狀態展示契約。

#### 市場階段低敏 Metadata（Issue #1386 P1b）

P1b 將 P1a 的 runtime `market_phase_context` 投影為穩定、低敏、可公開的 `market_phase_summary`，並寫入 `analysis_history.context_snapshot` 頂層。歷史詳情、同步分析響應和 completed `/api/v1/analysis/status/{task_id}` 都透過 `report.meta.market_phase_summary` 返回同一份市場階段元資訊；completed 任務狀態不新增 `TaskStatus` 頂層欄位，只透過 `status.result.report.meta.market_phase_summary` 間接暴露。

`market_phase_summary` 只包含市場、階段、市場本地時間、session date、effective daily-bar date、交易日/開市/partial-bar 標記、開收盤分鐘數、觸發來源、分析意圖和 warning code。它不暴露完整 `market_phase_context`，也不加入 quote freshness、fallback、stale 或 data_quality scoring 欄位。`report.details.analysis_context_pack_overview` 仍表示 #1389 輸入資料塊質量摘要；API 返回的 `details.context_snapshot` 會剝離頂層 `market_phase_summary` 和 `analysis_context_pack_overview`，避免 raw snapshot 重複展示這些穩定公開欄位。`SAVE_CONTEXT_SNAPSHOT=false` 或舊歷史記錄缺少 summary 時欄位為空，報告仍正常返回。

P1b 不改 Prompt、不新增 `analysis_phase` 請求引數、不做 Web 階段標籤或頁面展示，也不覆蓋 pending/processing TaskPanel、SSE 進行中事件、Bot、通知、`market_review` 或 P3 盤中資料質量欄位。

#### 市場階段 Prompt 注入（Issue #1386 P2-min）

P2-min 開始在已獲得 `market_phase_context` 的分析路徑中，把執行態市場階段渲染為 LLM 可讀的 Prompt 區塊。普通分析、single Agent 和 multi-agent 會在 Prompt 中看到當前階段、市場本地時間、最新可複用完整日線日期以及最小階段約束：盤前不得描述“今日走勢已經發生”，盤中 / 午間 / 臨近收盤需說明最後一根日線可能未完成，盤後保留完整交易日覆盤語義，非交易日或未知階段保持保守表述。

P2-min 仍不新增 API/Web/Bot 引數，不寫入 history/task status/report metadata，不改變報告 JSON schema，也不引入完整 quote freshness、fallback、stale 或 data_quality 契約。Bot/API 直連 Agent 若未經過 P1a pipeline 構建 `market_phase_context`，仍保持舊行為；入口透傳和可見展示留給後續 P4+。

#### 盤中資料包與實時質量控制（Issue #1386 P3）

P3 補齊普通分析主路徑使用的實時行情質量後設資料，但仍不新增 `analysis_phase` 引數，不改 API/Web/Bot 階段入口，不改變報告 JSON schema，也不做 #1389 P5 資料質量評分或模型置信度限制。實時 quote 會帶上 `fetched_at`、`provider_timestamp`、`is_stale`、`stale_seconds`、`fallback_from`；其中 `fetched_at` 是系統獲取時間，`provider_timestamp` 只在 provider 真實提供行情時間時填寫。缺少 provider 時間時不會偽造 fresh，`stale_seconds` 和 `is_stale` 保持空值。

整源 fallback 的語義固定為：`source` 保留實際成功的資料來源 token，`fallback_from` 記錄本輪失敗的最高優先順序整源 token；首選源成功後只從後續源補欄位時不寫 `fallback_from`。`AnalysisContextBuilder` 只對映這些上游 artifact，不重新取數、不做質量評分；quote block 狀態按 `STALE > FALLBACK > AVAILABLE` 歸併。盤中實時價覆蓋 `today` 時會標記 `is_partial_bar`、`is_estimated`、`estimated_fields`、`realtime_source` 和 quote 後設資料；`daily_bars` block 仍表示 storage 中完整日線視窗，partial/estimated 只進入 technical block。freshness scoring、盤中 cache TTL 分級、Agent 工具級複用和 API/Web 展示留給後續階段。

#### 分析階段入口與任務佇列透傳（Issue #1386 P4a）

P4a 新增 `analysis_phase=auto|premarket|intraday|postmarket` 請求引數，預設 `auto`，用於讓 API 呼叫方顯式覆蓋本次分析階段。該引數目前接入 `POST /api/v1/analysis/analyze`、非同步任務佇列、`AnalysisService`、普通分析 pipeline 和市場階段上下文；Web 前端型別和 API mapper 已承接該欄位，但不新增頁面 selector，Bot、schedule、GitHub Actions 和 DB migration 也不在本階段範圍內。

`analysis_phase` 是請求覆蓋值；最終報告階段仍以 `report.meta.market_phase_summary.phase` 為準。非同步 accepted response、記憶體任務 status、任務列表和 SSE payload 會回顯請求階段；歷史 DB fallback 不新增持久化欄位，舊記錄仍可能為空。同股不同 phase 仍按同一個股票任務去重，避免併發重複分析。

內部階段上下文構造仍相容舊引數 `analysis_intent`：僅當 `analysis_phase` 保持 `auto` 時，非 `auto` 的 `analysis_intent` 會被歸一為本次請求階段；外部呼叫方應優先使用 `analysis_phase`。

`auto` 保持既有交易日曆推斷；非 `auto` 只覆蓋 phase 並重算 `is_trading_day`、`is_market_open_now`、`is_partial_bar`、`minutes_to_open` 和 `minutes_to_close`。覆蓋不會改寫真實 `market_local_time` 或 `effective_daily_bar_date`；如果當前日期不是交易日或日曆不支援對應 session，分鐘欄位可以為空。

#### Web 階段標籤展示（Issue #1386 P4b）

P4b 在 Web 端補齊階段可見性，但不新增階段覆蓋 selector。進行中的任務面板只展示 P4a 回顯的請求階段 `analysis_phase`，其中 `auto` 明確顯示為“自動階段”，不偽裝成最終推斷階段。最終報告頁以 `report.meta.market_phase_summary.phase` 展示實際市場階段標籤，並在 `is_partial_bar=true` 時提示“日線未完成”。

資料質量摘要繼續複用 `report.details.analysis_context_pack_overview.data_quality` 和現有 `AnalysisContextSummary`；Web 會在同一報告詳情頁展示階段標籤，並繼續複用低敏資料質量摘要，不暴露完整 `AnalysisContextPack`、Prompt summary、raw payload 或已剝離的 snapshot 內部欄位。歷史列表、Bot、schedule、GitHub Actions、Desktop、通知摘要和高階階段覆蓋入口仍為後續工作。

#### AnalysisContextPack Prompt 摘要（Issue #1389 P3）

P3 在普通分析和 Agent 初始上下文中接入 `AnalysisContextPack` 低敏摘要。Pipeline 會用已獲取的行情、日線、趨勢、籌碼、基本面、新聞和市場階段 artifacts 組裝 pack，再把 `analysis_context_pack_summary` 插入 Prompt；在這個新增的 pack 摘要區塊中，LLM 只看到 subject、版本、各資料塊的狀態/來源/warning/missing reason 和新聞結果數，不會透過該區塊看到完整 `news.content`、`trend_result`、籌碼或基本面原始 payload。既有 `news_context`、Agent pre-fetched JSON 和 `enhanced_context` 原始資料通道保持 P3 前行為，不由本摘要替代或脫敏。

P3 當時不新增 API/Web/Bot 引數，不寫入 history/task status/report metadata，不改變報告 JSON schema，也不把完整 pack 暴露到歷史、通知或 Web。Agent 工具級複用 pack 資料和 P5 資料質量評分留給後續階段。

#### AnalysisContextPack 低敏可見性（Issue #1389 P4）

P4 新增 `report.details.analysis_context_pack_overview`，歷史詳情、同步分析響應和 completed `/api/v1/analysis/status/{task_id}` 都會返回同一份低敏 overview；Web 端報告頁在“策略點位”和“資訊”之後展示預設摺疊的資料塊摘要，摺疊頭部展示可用數、缺失數、非零的其他狀態計數和觸發來源，展開後展示資料塊狀態、來源、warning、missing reason、狀態計數和新聞結果數。API 返回的 `details.context_snapshot` 會剝離頂層 `analysis_context_pack_overview`，避免透明度面板重複展示 raw snapshot。

該 overview 不包含完整 pack、`analysis_context_pack_summary` Prompt 字串、`items.value`、新聞正文、`trend_result`、籌碼或基本面原始 payload。`SAVE_CONTEXT_SNAPSHOT=false` 或舊歷史記錄缺少 overview 時欄位為空，報告仍正常返回。本階段不覆蓋 pending/processing TaskPanel、SSE 進行中事件、通知摘要、Bot/Desktop 專屬展示、`market_review` overview 或資料質量評分。

#### AnalysisContextPack 資料質量評分與 Prompt 資料限制（Issue #1389 P5）

P5 在不修改 `PACK_VERSION = "1.0"`、不新增資料來源和不改變報告 JSON schema 的前提下，給 `AnalysisContextPack` 增加輕量資料質量評分與模型可讀的資料限制區塊。`ContextFieldStatus` 新增 `fetch_failed`，只表示欄位或資料塊本次抓取明確失敗；首版僅把 `fundamental_context.status == "failed"` 對映為 `fetch_failed`，空新聞、未配置搜尋、無實時 quote 或 chip 缺失仍按既有 `missing` / `not_supported` 處理。

`DataQuality` 現在包含 `overall_score`、`level`、`block_scores`、`limitations`，並保留舊 `warnings` / `metadata`。評分固定覆蓋 `quote`、`daily_bars`、`technical`、`news`、`fundamentals`、`chip` 六塊，不因輔助塊缺失重歸一化；核心塊降級會在 Prompt 的“資料限制”區塊中要求模型不要輸出高置信度，輔助塊缺失只限制對應分析段落，不應被解釋為利好或利空。該 Prompt 區塊由 `format_analysis_context_pack_prompt_section()` 統一生成，普通分析、single Agent 和 multi-agent 沿用同一低敏 summary，不暴露 raw payload、新聞正文、趨勢原始值、secret、token 或 webhook。

歷史詳情、同步分析響應和 completed 任務狀態繼續只透過 `report.details.analysis_context_pack_overview` 暴露低敏欄位；P5 只在該 overview 下新增 `data_quality`，包含 score、level、block_scores 和 limitations，不重複公開 `warnings`。Web 報告頁仍預設摺疊展示資料塊摘要，摺疊頭部新增質量分/等級，展開後展示限制說明和 `fetch_failed` 狀態；`details.context_snapshot` 繼續剝離頂層 `analysis_context_pack_overview`。

#### 盤中決策護欄與質量校驗（Issue #1386 P5）

P5 在個股分析報告的 `dashboard.phase_decision` 中追加階段化決策欄位：`phase_context`、`action_window`、`immediate_action`、`watch_conditions`、`next_check_time`、`confidence_reason` 和 `data_limitations`。該欄位只作為報告 JSON 的向後相容擴充套件進入歷史 `raw_result`；不新增 `analysis_phase` API 引數、不改變 Web 階段入口、不新增配置項，也不影響每日收盤覆盤預設行為。

普通分析與 Agent 分析會在儲存歷史前複用當次 `market_phase_summary` 和 `analysis_context_pack_overview.data_quality` 執行輕量護欄：核心 quote / daily_bars / technical 資料 stale、fallback、missing、fetch_failed、partial 或 estimated 時，不允許高置信結論；盤前、非交易日或未知階段不得輸出高置信盤中買賣；盤中、午間和臨近收盤會檢查主結論裡的盤後覆盤口吻，並把明顯的“今日收盤後覆盤顯示”“明日重點關注”類措辭改為階段安全的觀察/等待表述。護欄只補低敏 `phase_context` 和資料限制，不編造觀察條件或下一次檢查時間；通知摘要、警告、持股和回測聯動留給後續 P6。

#### 使用 Crontab

如果不想使用常駐程序，也可以使用系統的 Cron：

```bash
crontab -e
# 新增：0 18 * * 1-5 cd /path/to/project && python main.py
```

---

## 通知通道詳細配置

通知通道矩陣、minimal/advanced key 分層、`--check-notify` 診斷口徑和場景化配置說明見 [通知專題文件](notifications.md)。

### 企業微信

1. 在企業微信群聊中新增"群機器人"
2. 複製 Webhook URL
3. 設定 `WECHAT_WEBHOOK_URL`

### 飛書

> ⚠️ **關鍵區分**：`FEISHU_WEBHOOK_SECRET`（Webhook 簽名金鑰）和 `FEISHU_APP_SECRET`（飛書應用 Secret）是兩個完全不同的配置，不能互換。

**最小可用配置（無安全限制）：**

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
```

**完整步驟：**

1. **在飛書群聊中建立自定義機器人**：
   - 開啟目標群聊 → 右上角「群設定」→「群機器人」→「新增機器人」→「自定義機器人」
   - 填寫機器人名稱，複製生成的 **Webhook URL**（格式：`https://open.feishu.cn/open-apis/bot/v2/hook/...`）
2. 設定 `FEISHU_WEBHOOK_URL`（即上一步複製的 URL）。
3. 檢視機器人**安全設定**，根據啟用的安全項決定是否需要補充配置：
   - **無額外安全設定**：僅填 `FEISHU_WEBHOOK_URL` 即可。
   - **開啟了「簽名校驗」**：把飛書顯示的 secret 填到 `FEISHU_WEBHOOK_SECRET`。兩端必須同時啟用或同時不填，否則飛書返回簽名校驗失敗。
   - **開啟了「關鍵詞」**：把同一個關鍵詞填到 `FEISHU_WEBHOOK_KEYWORD`；系統會自動在每條訊息前補上，無需手動修改報告模板。
   - **開啟了 IP 白名單**：確保當前執行環境的出口 IP 在白名單中（本地/Docker/GitHub Actions 出口 IP 各不相同）。
4. `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 是飛書應用 / Stream Bot / 雲文件模式專用，不會觸發群 Webhook 推送，不要用它們替代 `FEISHU_WEBHOOK_URL`。

**常見失敗原因：**
- 只填了 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`，沒有配置 `FEISHU_WEBHOOK_URL`
- 飛書機器人開啟了「簽名校驗」，但 `FEISHU_WEBHOOK_SECRET` 未配置（或誤填為 `FEISHU_APP_SECRET`）
- 飛書機器人開啟了「關鍵詞」，但本地沒有同步配置 `FEISHU_WEBHOOK_KEYWORD`
- 機器人沒有被加入目標群，或群管理員限制了機器人發言
- 飛書側額外配置了 IP 白名單，但當前執行環境 IP 不在白名單中
- 訊息內容超長：飛書單條訊息有長度限制，系統會自動分段傳送；如需在一個文件內檢視完整內容，可配置飛書雲文件功能（`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_FOLDER_TOKEN`）

更完整的圖文排查請看 [docs/bot/feishu-bot-config.md](bot/feishu-bot-config.md)。
### Telegram

1. 與 @BotFather 對話建立 Bot
2. 獲取 Bot Token
3. 獲取 Chat ID（可透過 @userinfobot）
4. 設定 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
5. (可選) 如需傳送到 Topic，設定 `TELEGRAM_MESSAGE_THREAD_ID` (從 Topic 連結末尾獲取)

### 郵件

1. 開啟郵箱的 SMTP 服務
2. 獲取授權碼（非登入密碼）
3. 設定 `EMAIL_SENDER`、`EMAIL_PASSWORD`、`EMAIL_RECEIVERS`

支援的郵箱：
- QQ 郵箱：smtp.qq.com:465
- 163 郵箱：smtp.163.com:465
- Gmail：smtp.gmail.com:587

**股票分組發往不同郵箱**（Issue #268，可選）：
配置 `STOCK_GROUP_N` 與 `EMAIL_GROUP_N` 可實現不同股票組的報告傳送到不同郵箱，例如多人共享分析時互不干擾。`STOCK_LIST` 仍決定本次實際分析的股票集合，`STOCK_GROUP_N` 應寫成 `STOCK_LIST` 的子集；它隻影響郵件收件人，不會改變 Telegram、企業微信、Webhook 等其他通道收到的完整報告。大盤覆盤會發往所有配置的郵箱。

> GitHub Actions 限制：截至 2026-03-29，倉庫自帶 `00-daily-analysis.yml` 不會自動匯入任意編號的 `STOCK_GROUP_N` / `EMAIL_GROUP_N`。因此如果你只在倉庫 Secrets / Variables 中新增這些變數，而沒有修改 workflow 顯式對映，它們不會進入執行程序，看起來就像“分組配置不生效”。

```bash
STOCK_LIST=2330,2454,AAPL,NVDA
STOCK_GROUP_1=2330,2454
EMAIL_GROUP_1=user1@example.com
STOCK_GROUP_2=AAPL,NVDA
EMAIL_GROUP_2=user2@example.com
```

### 自定義 Webhook

支援任意 POST JSON 的 Webhook，包括：
- 釘釘機器人
- Discord Webhook
- Slack Webhook
- Bark（iOS 推送）
- 自建服務

設定 `CUSTOM_WEBHOOK_URLS`，多個用逗號分隔。

如需適配 AstrBot、NapCat 或自建服務的特殊 body，可設定 `CUSTOM_WEBHOOK_BODY_TEMPLATE`。這是全域性模板，會先於 Bark、Slack、Discord 等 URL 自動識別 payload 生效；如果渲染後不是 JSON object，系統會回退預設 payload。推薦使用 `$content_json` / `$title_json` 避免換行和引號破壞 JSON：

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"msg_type":"text","content":$content_json}
```

可用佔位符：`$content_json`、`$content`、`$title_json`、`$title`。其中 `$content` / `$title` 是裸字串，不做 JSON 轉義；正文含雙引號或換行時可能觸發 fallback。

Bark 使用全域性模板時需顯式寫出 Bark body：

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"body":$content_json,"group":"stock"}
```

NapCat / OneBot 示例需按實際 endpoint、`user_id` 或 `group_id` 調整：

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"user_id":123456,"message":$content_json}
```

### ntfy / Gotify

ntfy 和 Gotify 都是一等通知通道，只傳送文字 / JSON，不參與 Markdown 轉圖片。

ntfy 使用完整 topic endpoint，最後一個 path segment 會作為 topic：

```env
NTFY_URL=https://ntfy.sh/my-topic
NTFY_TOKEN=
```

Gotify 使用 server base URL，系統會自動拼接固定 `/message` API，並透過 `X-Gotify-Key` Header 傳送 application token。`GOTIFY_URL` 可包含反向代理 path prefix，但不要包含 `/message`：

```env
GOTIFY_URL=https://gotify.example
GOTIFY_TOKEN=app-token
```

```env
# 實際請求會傳送到 https://example.com/gotify/message
GOTIFY_URL=https://example.com/gotify
GOTIFY_TOKEN=app-token
```

`NTFY_URL` 與 `GOTIFY_URL` 的語義不同是兩個服務 API 設計不同導致的刻意選擇：ntfy 由使用者 topic 構成 endpoint，Gotify 的 `/message` 是固定服務 API。

### Discord

Discord 支援兩種方式推送：

**方式一：Webhook（推薦，簡單）**

1. 在 Discord 頻道設定中建立 Webhook
2. 複製 Webhook URL
3. 配置環境變數：

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
```

**方式二：Bot API（需要更多許可權）**

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 建立應用
2. 建立 Bot 並獲取 Token
3. 邀請 Bot 到伺服器
4. 獲取頻道 ID（開發者模式下右鍵頻道複製）
5. 配置環境變數：

```bash
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_MAIN_CHANNEL_ID=your_channel_id
```

如果你要接收 Discord Slash Command / Interaction 回撥，而不僅是向 Discord 推送訊息，還需要在 Discord Developer Portal 的 `General Information -> Public Key` 複製公鑰並配置：

```bash
DISCORD_INTERACTIONS_PUBLIC_KEY=your_public_key
```

未配置該公鑰時，系統會拒絕所有 Discord 入站 webhook 請求。

### Slack

Slack 支援兩種方式推送，同時配置時優先使用 Bot API，確保文字與圖片傳送到同一頻道：

**方式一：Bot API（推薦，支援圖片上傳）**

1. 建立 Slack App：https://api.slack.com/apps → Create New App
2. 新增 Bot Token Scopes：`chat:write`、`files:write`
3. 安裝到工作區並獲取 Bot Token (xoxb-...)
4. 獲取頻道 ID：頻道詳情 → 底部複製頻道 ID
5. 配置環境變數：

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C01234567
```

**方式二：Incoming Webhook（配置簡單，僅文字）**

1. 在 Slack App 管理頁面建立 Incoming Webhook
2. 複製 Webhook URL
3. 配置環境變數：

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
```

### Pushover（iOS/Android 推送）

[Pushover](https://pushover.net/) 是一個跨平臺的推送服務，支援 iOS 和 Android。

1. 註冊 Pushover 賬號並下載 App
2. 在 [Pushover Dashboard](https://pushover.net/) 獲取 User Key
3. 建立 Application 獲取 API Token
4. 配置環境變數：

```bash
PUSHOVER_USER_KEY=your_user_key
PUSHOVER_API_TOKEN=your_api_token
```

特點：
- 支援 iOS/Android 雙平臺
- 支援通知優先順序和聲音設定
- 免費額度足夠個人使用（每月 10,000 條）
- 訊息可保留 7 天

### Markdown 轉圖片（可選）

配置 `MARKDOWN_TO_IMAGE_CHANNELS` 可將報告以圖片形式傳送至不支援 Markdown 的通道（telegram, wechat, custom, email, slack）。

**依賴安裝**：

1. **imgkit**：已包含在 `requirements.txt`，執行 `pip install -r requirements.txt` 時會自動安裝
2. **wkhtmltopdf**（預設引擎）：系統級依賴，需手動安裝：
   - **macOS**：`brew install wkhtmltopdf`
   - **Debian/Ubuntu**：`apt install wkhtmltopdf`
3. **markdown-to-file**（可選，emoji 支援更好）：`npm i -g markdown-to-file`，並設定 `MD2IMG_ENGINE=markdown-to-file`

未安裝或安裝失敗時，將自動回退為 Markdown 文字傳送。

**單股推送 + 圖片傳送**（Issue #455）：

單股推送模式（`SINGLE_STOCK_NOTIFY=true`）下，若希望 Telegram 等通道以圖片形式推送，需同時配置 `MARKDOWN_TO_IMAGE_CHANNELS=telegram` 並安裝轉圖工具（wkhtmltopdf 或 markdown-to-file）。個股日報彙總同樣支援轉圖，無需額外配置。

**故障排查**：若日誌出現「Markdown 轉圖片失敗，將回退為文字傳送」，請檢查 `MARKDOWN_TO_IMAGE_CHANNELS` 配置及轉圖工具是否已正確安裝（`which wkhtmltoimage` 或 `which m2f`）。

---

## 資料來源配置

系統預設使用 AkShare（免費），也支援其他資料來源：

### AkShare（預設）
- 免費，無需配置
- 資料來源：東方財富爬蟲

### Tushare Pro
- 需要註冊獲取 Token
- 更穩定，資料更全
- 設定 `TUSHARE_TOKEN`

### Baostock
- 免費，無需配置
- 作為備用資料來源

### YFinance
- 免費，無需配置
- 支援美股/港股資料
- 美股歷史資料與實時行情均統一使用 YFinance，以避免 akshare 美股復權異常導致的技術指標錯誤

> **升級注意（Route B / Phase 5 破壞性變更）：** YFinance 美股實時資料現在預設 fail-closed。若未在 `.env` 中顯式設定以下兩項，有 fixture 的股票將靜默使用離線 fixture 資料，無 fixture 的股票將直接 `DataFetchError`，這是預期行為：
>
> ```env
> DSA_FIXTURE_MODE=false
> DSA_ALLOW_EXTERNAL_NETWORK=true
> ```
>
> 這是 Route B 離線優先安全邊界的一部分，不是 bug。

### Taiwan FinMind（台股離線 + 實時資料來源）
- 需要 Python 3.11；參見 [FinMind live smoke 環境](#finmind-live-smoke-環境) 配置說明
- 預設僅使用離線 fixture；啟用台股實時資料需同時設定三項：
  - `FINMIND_ENABLED=true`
  - `DSA_ALLOW_EXTERNAL_NETWORK=true`（見下方說明）
  - `FINMIND_API_TOKEN=<token>`（從 https://finmindtrade.com 獲取）
- `TAIWAN_FINMIND_PRIORITY=99`：數字越小，DataFetcherManager 中的優先順序越高
- `FinMind>=0.6.0` 為可選依賴，僅台股實時模式下需要安裝

### 安全標誌（適用於所有資料來源）

| 變數 | 說明 | 預設 |
|---|---|---|
| `DSA_FIXTURE_MODE` | `true` = 強制全離線，所有資料均從本地 fixture 讀取，不呼叫任何網路介面 | `false` |
| `DSA_ALLOW_EXTERNAL_NETWORK` | `true` = 允許 FinMind/YFinance/Tavily/SearXNG 等實時呼叫；**空值、未設定或其他非 `true` 值均視為禁用（fail-closed）** | `false` |

### Longbridge（長橋）
- 美股/港股資料兜底，補充 YFinance 缺失的量比、換手率、PE 等欄位
- 新接入推薦使用 Longbridge 官方 OAuth 2.0：client_id 優先使用 `LONGBRIDGE_OAUTH_CLIENT_ID`，留空且沒有 Legacy Access Token 時相容使用 `LONGBRIDGE_APP_KEY`；先在可互動環境執行 `python scripts/generate_longbridge_oauth_token.py --client-id <client_id>` 生成 SDK token 快取
- GitHub Actions / Docker 等 headless 環境不能在分析任務裡等待瀏覽器授權；可將本機 `~/.longbridge/openapi/tokens/<client_id>` 檔案 base64 後配置為 `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64`
- OAuth 執行時依賴 SDK 提供 `OAuthBuilder` / `Config.from_oauth`；若當前 Linux/Docker 環境只能安裝舊版 SDK，日誌會明確提示並自動跳過 Longbridge，不影響 YFinance / AkShare 兜底
- Legacy API Key 仍相容：設定 `LONGBRIDGE_APP_KEY`、`LONGBRIDGE_APP_SECRET`、`LONGBRIDGE_ACCESS_TOKEN`；其中 Access Token 是舊版 API Key 憑證，不是 OAuth access token
- 可選設定 `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` 控制連線關閉類異常後的冷卻秒數（預設 15）
- 接入點可配 `LONGBRIDGE_HTTP_URL`、`LONGBRIDGE_QUOTE_WS_URL`、`LONGBRIDGE_TRADE_WS_URL`、`LONGBRIDGE_REGION`
- 其餘可選引數見官方 [環境變數說明](https://open.longbridge.com/zh-CN/docs/getting-started#環境變數)
- 僅在 YFinance（美股）或 AkShare（港股）返回資料不完整時自動觸發，不影響 A 股鏈路
- 未配置憑據時不會例項化該可選資料來源；若執行時出現連線關閉類異常，會在冷卻期內臨時跳過 Longbridge，避免請求級頻繁重連

### 東財介面頻繁失敗時的處理

若日誌出現 `RemoteDisconnected`、`push2his.eastmoney.com` 連線被關閉等，多為東財限流。建議：

1. 在 `.env` 中設定 `ENABLE_EASTMONEY_PATCH=true`
2. 將 `MAX_WORKERS=1` 降低併發
3. 若已配置 Tushare，可優先使用 Tushare 資料來源

---

## 高階功能

### 港股支援

使用 `hk` 字首指定港股程式碼：

```bash
STOCK_LIST=600519,hk00700,hk01810
```

港股日線會跳過 efinance、pytdx、baostock 等不支援港股日線的資料來源，避免把港股程式碼錯配到非港股市場；預設改由 AkShare/Tushare/YFinance/Longbridge 等港股路徑繼續兜底。

### ETF 與指數分析

針對指數跟蹤型 ETF 和美股指數（如 VOO、QQQ、SPY、510050、SPX、DJI、IXIC），分析僅關注**指數走勢、跟蹤誤差、市場流動性**，不納入基金管理人/發行方的公司層面風險（訴訟、聲譽、高管變動等）。風險警報與業績預期均基於指數成分股整體表現，避免將基金公司新聞誤判為標的本身利空。詳見 Issue #274。

### 多模型切換

配置多個模型，系統自動切換：

```bash
# Gemini（主力）
GEMINI_API_KEY=xxx
GEMINI_MODEL=gemini-3.1-pro-preview

# OpenAI 相容（備選）
OPENAI_API_KEY=xxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
# deepseek-chat / deepseek-reasoner 仍相容，但官方已標記為 2026/07/24 後廢棄
```

### 高階模型路由（底層由 LiteLLM 驅動）

詳見 [LLM 配置指南](LLM_CONFIG_GUIDE.md)。預設使用時你只需要理解主模型、備選模型和模型通道；如果進入這一節，說明你要直接使用底層 [LiteLLM](https://github.com/BerriAI/litellm) 路由能力，無需單獨啟動 Proxy 服務。

**兩層機制**：同一模型多 Key 輪換（Router）與跨模型降級（Fallback）分層獨立，互不干擾。

**多 Key + 跨模型降級配置示例**：

```env
# 主模型：3 個 Gemini Key 輪換，任一 429 時 Router 自動切換下一個 Key
GEMINI_API_KEYS=key1,key2,key3
LITELLM_MODEL=gemini/gemini-3.1-pro-preview

# 跨模型降級：主模型全部 Key 均失敗時，按序嘗試 Claude → GPT
# 需配置對應 API Key：ANTHROPIC_API_KEY、OPENAI_API_KEY
LITELLM_FALLBACK_MODELS=anthropic/claude-sonnet-4-6,openai/gpt-5.4-mini
```

**預期行為**：首次請求用 `key1`；若 429，Router 下次用 `key2`；若 3 個 Key 均不可用，則切換到 Claude，再失敗則切換到 GPT。

> ⚠️ `LITELLM_MODEL` 必須包含 provider 字首（如 `gemini/`、`anthropic/`、`openai/`），
> 否則系統無法識別應使用哪組 API Key。舊格式的 `GEMINI_MODEL`（無字首）僅用於未配置 `LITELLM_MODEL` 時的自動推斷。

**依賴說明**：`requirements.txt` 中保留 `openai>=1.0.0`，因 LiteLLM 內部依賴 OpenAI SDK 作為統一介面；顯式保留可確保版本相容性，使用者無需單獨配置。

**視覺模型（圖片提取股票程式碼）**：詳見 [LLM 配置指南 - Vision](LLM_CONFIG_GUIDE.md#41-vision-模型圖片識別股票程式碼)。

從圖片提取股票程式碼（如 `/api/v1/stocks/extract-from-image`）使用統一視覺模型接入，底層採用 LiteLLM Vision 與 OpenAI `image_url` 格式，支援 Gemini、Claude、OpenAI、DeepSeek 等 Vision-capable 模型。返回 `items`（code、name、confidence）及相容的 `codes` 陣列。

> 相容性說明：`/api/v1/stocks/extract-from-image` 響應在原 `codes` 基礎上新增 `items` 欄位。若下游客戶端使用嚴格 JSON Schema 且不接受未知欄位，請同步更新 schema。

**智慧匯入**：除圖片外，還支援 CSV/Excel 檔案及剪貼簿貼上（`/api/v1/stocks/parse-import`），自動解析程式碼/名稱列，名稱→程式碼解析支援本地對映、拼音匹配及 AkShare 線上 fallback。依賴 `pypinyin`（拼音匹配）和 `openpyxl`（Excel 解析），已包含在 `requirements.txt` 中。

- **AkShare 名稱解析快取**：名稱→程式碼解析使用 AkShare 線上 fallback 時，結果快取 1 小時（TTL），避免頻繁請求；首次呼叫或快取過期後會自動重新整理。
- **CSV/Excel 列名**：支援 `code`、`股票程式碼`、`程式碼`、`name`、`股票名稱`、`名稱` 等（不區分大小寫）；無表頭時預設第 1 列為程式碼、第 2 列為名稱。
- **常見解析失敗**：檔案過大（>2MB）、編碼非 UTF-8/GBK、Excel 工作表為空或損壞、CSV 分隔符/列數不一致時，API 會返回具體錯誤提示。

- **模型優先順序**：`VISION_MODEL` > `LITELLM_MODEL` > 根據已有 API Key 推斷（`OPENAI_VISION_MODEL` 已廢棄，請改用 `VISION_MODEL`）
- **Provider 回退**：主模型失敗時，按 `VISION_PROVIDER_PRIORITY`（預設 `gemini,anthropic,openai`）自動切換到下一個可用 provider
- **主模型不支援 Vision 時**：若主模型為 DeepSeek 等非 Vision 模型，可顯式配置 `VISION_MODEL=openai/gpt-5.5` 或 `gemini/gemini-3.1-pro-preview` 供圖片提取使用
- **配置校驗**：若配置了 `VISION_MODEL` 但未配置對應 provider 的 API Key，啟動時會輸出 warning，圖片提取功能將不可用

### 除錯模式

```bash
python main.py --debug
```

日誌檔案位置：
- 常規日誌：`logs/stock_analysis_YYYYMMDD.log`
- 除錯日誌：`logs/stock_analysis_debug_YYYYMMDD.log`

除錯日誌預設保留專案自身 DEBUG 資訊，但會將 LiteLLM 內部日誌壓低到 `WARNING`，避免流式生成時按 token 寫入大量第三方除錯日誌；如需排查 LiteLLM 內部細節，可在 `.env` 中臨時設定 `LITELLM_LOG_LEVEL=DEBUG`。

### SQLite 寫入穩態配置

預設檔案型 SQLite 會在連線建立時啟用 `WAL` 並設定 `busy_timeout`，`save_daily_data()` 也已改為按 `(code, date)` 批次原子 upsert，以降低批次更新和併發回寫時的鎖競爭。

如需調整，可在 `.env` 中設定：

| 變數 | 預設值 | 說明 |
|------|-------|------|
| `SQLITE_WAL_ENABLED` | `true` | 檔案型 SQLite 是否啟用 `journal_mode=WAL` |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite 等鎖超時（毫秒） |
| `SQLITE_WRITE_RETRY_MAX` | `3` | 遇到 `database is locked` / `database table is locked` 時的最大重試次數 |
| `SQLITE_WRITE_RETRY_BASE_DELAY` | `0.1` | 寫入重試基礎退避時間（秒，按指數退避遞增） |

---

## 分析決策可操作性

個股報告的操作建議會結合支撐位、壓力位、量能/籌碼、主力資金流向和風險事件進行校準，避免僅因單日漲跌或評分跨線在“買進/賣出”之間劇烈切換。若價格處在支撐與壓力之間且資金流不明確，報告會優先給出“持有、震盪觀望、洗盤觀察”等中性可執行建議；只有接近支撐確認、有效突破壓力且量價/資金配合時才給出買進，跌破關鍵支撐或主力資金持續流出時才給出賣出/減倉。
該項調整會影響可操作決策的執行時落盤與提示詞約束鏈路，但不變更 LLM 模型、LiteLLM 路由、Provider/Key 及其相容邊界，不影響配置儲存/清理語義。
相容性核驗結論：除配置和模型側語義外，該決策穩定性鏈路覆蓋 `src/analyzer.py`、`src/core/pipeline.py`、`src/core/backtest_engine.py`、`src/report_language.py` 及 `src/agent` 決策路徑的執行時行為，建議複核報告決策型別對映與回測入口聯動。
核驗路徑：相關邏輯在上述執行時路徑與對應測試（`tests/test_backtest_engine.py`、`tests/test_analyzer_news_prompt.py`、`tests/test_decision_stability.py`、`tests/test_agent_pipeline.py` 等）中生效；未在 `src/config.py`、`src/report.py`、儲存/持久化鏈路新增配置欄位或清理邏輯。

## 回測功能

回測模組自動對歷史 AI 分析記錄進行事後驗證，評估分析建議的準確性。

### 工作原理

1. 選取已過冷卻期（預設 14 天）的 `AnalysisHistory` 記錄
2. 獲取分析日之後的日線資料（前向 K 線）
3. 根據操作建議推斷預期方向，與實際走勢對比
4. 評估止盈/止損命中情況，模擬執行收益
5. 彙總為整體和單股兩個維度的表現指標

### 操作建議對映

| 操作建議 | 部位推斷 | 預期方向 | 勝利條件 |
|---------|---------|---------|---------|
| 買進/加倉/strong buy | long | up | 漲幅 ≥ 中性帶 |
| 賣出/減倉/strong sell | cash | down | 跌幅 ≥ 中性帶 |
| 持有/持有觀察/震盪觀望/洗盤觀察/hold/hold and watch/range-bound watch/shakeout watch | long | not_down | 未顯著下跌 |
| 觀望/等待/wait | cash | flat | 價格在中性帶內 |

### 配置

在 `.env` 中設定以下變數（均有預設值，可選）：

| 變數 | 預設值 | 說明 |
|------|-------|------|
| `BACKTEST_ENABLED` | `true` | 是否在每日分析後自動執行回測 |
| `BACKTEST_EVAL_WINDOW_DAYS` | `10` | 評估視窗（交易日數） |
| `BACKTEST_MIN_AGE_DAYS` | `14` | 僅回測 N 天前的記錄，避免資料不完整 |
| `BACKTEST_ENGINE_VERSION` | `v1` | 引擎版本號，升級邏輯時用於區分結果 |
| `BACKTEST_NEUTRAL_BAND_PCT` | `2.0` | 中性區間閾值（%），±2% 內視為震盪 |

### 自動執行

回測在每日分析流程完成後自動觸發（非阻塞，失敗不影響通知推送）。也可透過 API 手動觸發。

### 評估指標

| 指標 | 說明 |
|------|------|
| `direction_accuracy_pct` | 方向預測準確率（預期方向與實際一致） |
| `win_rate_pct` | 勝率（勝 / (勝+負)，不含中性） |
| `avg_stock_return_pct` | 平均股票收益率 |
| `avg_simulated_return_pct` | 平均模擬執行收益率（含止盈止損退出） |
| `stop_loss_trigger_rate` | 止損觸發率（僅統計配置了止損的記錄） |
| `take_profit_trigger_rate` | 止盈觸發率（僅統計配置了止盈的記錄） |

---

## 本地 WebUI 管理介面

WebUI 與 FastAPI API 服務共用同一服務程序，啟動後可在瀏覽器中完成配置管理、手動分析、任務進度檢視、歷史報告、回測、持股管理和智慧匯入等操作。認證、雲伺服器訪問和 API 呼叫細節見下方說明。

### FastAPI API 服務

FastAPI 提供 RESTful API 服務，支援配置管理和觸發分析。

### 啟動方式

| 命令 | 說明 |
|------|------|
| `python main.py --serve` | 啟動 API 服務 + 執行一次完整分析 |
| `python main.py --serve-only` | 僅啟動 API 服務，手動觸發分析 |

### 功能特性

- 📝 **配置管理** - 檢視/修改自選股列表
- 🚀 **快速分析** - 透過 API 介面觸發個股分析；首頁也提供“大盤覆盤”按鈕，可在 Docker/server 模式下後臺觸發大盤覆盤
- 🎯 **策略選擇** - 首頁支援顯式選擇分析策略 skill；不傳 `skills` 時按系統預設策略執行，便於保持與歷史行為相容
- 🧭 **首次配置提示** - 首頁會讀取只讀配置狀態，缺少 LLM 主通道、自選股等基礎項時提示缺口並引導進入系統設定
- 📊 **實時進度** - 分析任務狀態實時更新，支援多工並行；普通分析鏈路在進入 LLM 階段後會優先嚐試 LiteLLM 流式生成，並透過任務 SSE 回灌更細粒度的 `message/progress`
- 🗂️ **大盤覆盤任務可見性** - 首頁觸發大盤覆盤後會返回 `task_id` 並輪詢 `GET /api/v1/analysis/status/{task_id}`，在進行中/完成/失敗場景給出可見反饋，失敗時直接透出報錯內容
- 🧾 **市場覆盤歷史可複用** - 大盤覆盤任務會持久化到分析歷史，`report_type` 為 `market_review`，可直接透過歷史列表/詳情開啟對應 Markdown 或詳情頁，不會重新觸發分析重算
- 🧩 **輸入資料塊可見** - 普通分析報告會在歷史詳情、同步響應和 completed 任務狀態中返回低敏 `AnalysisContextPack` overview，Web 報告頁在策略點位和資訊之後預設摺疊展示資料塊狀態、來源、缺失原因和降級摘要
- 📈 **回測驗證** - 評估歷史分析準確率，查詢方向勝率與模擬收益
- 🔗 **API 文件** - 訪問 `/docs` 檢視 Swagger UI

### API 介面

| 介面 | 方法 | 說明 |
|------|------|------|
| `/api/v1/analysis/analyze` | POST | 觸發股票分析 |
| `/api/v1/analysis/market-review` | POST | 後臺觸發大盤覆盤；請求體可傳 `{"send_notification": true}`；與 `main.py --market-review` 與 `bot` 複用同一套 `GeminiAnalyzer/SearchService/NotificationService` 組裝語義 |
| `/api/v1/analysis/tasks` | GET | 查詢任務列表 |
| `/api/v1/analysis/tasks/stream` | GET (SSE) | 訂閱任務實時狀態流 |
| `/api/v1/analysis/status/{task_id}` | GET | 查詢任務狀態 |
| `/api/v1/history` | GET | 查詢分析歷史 |
| `/api/v1/history/{record_id}/diagnostics` | GET | 查詢歷史報告執行診斷摘要與脫敏複製文字 |
| `/api/v1/usage/summary?period=today|month|all` | GET | 按呼叫型別與模型維度彙總 LLM 呼叫次數和 Token 用量 |
| `/api/v1/backtest/run` | POST | 觸發回測 |
| `/api/v1/backtest/results` | GET | 查詢回測結果（分頁） |
| `/api/v1/backtest/performance` | GET | 獲取整體回測表現 |
| `/api/v1/backtest/performance/{code}` | GET | 獲取單股回測表現 |
| `/api/v1/stocks/extract-from-image` | POST | 從圖片提取股票程式碼（multipart，超時 60s） |
| `/api/v1/stocks/parse-import` | POST | 解析 CSV/Excel/剪貼簿（multipart file 或 JSON `{"text":"..."}`，檔案≤2MB，文字≤100KB） |
| `/api/health` | GET | 健康檢查 |
| `/docs` | GET | API Swagger 文件 |

> 說明：`POST /api/v1/analysis/analyze` 在 `async_mode=false` 時僅支援單隻股票；批次 `stock_codes` 需使用 `async_mode=true`。非同步 `202` 響應對單股返回 `task_id`，對批次返回 `accepted` / `duplicates` 彙總結構。
> 說明：`POST /api/v1/analysis/analyze` 支援使用 `skills` 傳入策略 skill ID 列表；若未傳則按服務端預設策略執行。為相容歷史呼叫，`strategies` 欄位仍作為相容別名保留。
> 說明：`POST /api/v1/analysis/analyze` 支援 `analysis_phase=auto|premarket|intraday|postmarket`，預設 `auto`。非 `auto` 只覆蓋本次分析階段與派生階段標記，不改寫真實交易日曆時間；accepted response、記憶體 task status、任務列表和 SSE 會回顯請求階段，最終報告階段以 `report.meta.market_phase_summary.phase` 為準。
> 說明：Web 側首頁策略下拉為顯式可選策略入口。使用者未手動選擇時不會攜帶 `skills`，與歷史客戶端行為一致；選擇策略後將透傳到該介面並在任務狀態與歷史快照中保留。
> 說明：`POST /api/v1/analysis/market-review` 採用後端與 CLI/Bot 共用的配置路徑（`GeminiAnalyzer(config=...)` 與同樣的搜尋/提示詞構造入口）。Provider 相容路由會優先識別並使用 `litellm_model`、`llm_model_list`，若未配置則回退 legacy `GEMINI_*`、`OPENAI_*`、`ANTHROPIC_*`、`DEEPSEEK_*` 鍵；不會新增/調整 provider、Base URL 或 LiteLLM 路由語義。
> 審計依據：優先順序與回退語義以 `src/config.py` 的 `Config._load_from_env()` 為準（`LITELLM_CONFIG` > `LLM_CHANNELS` > legacy）。配套迴歸見 `tests/test_llm_channel_config.py`（配置源解析）與 `tests/test_market_review_runtime.py`（共享裝配路徑）。該介面當前僅提供單程序/單機級防重複能力，若為多例項部署需透過外部任務佇列或分散式鎖補齊全域性冪等。
> 說明：`POST /api/v1/analysis/market-review` 觸發後，報告會以 `report_type=market_review` 寫入歷史庫；你可直接查詢 `/api/v1/history` 或 `/api/v1/history/{record_id}` 獲取歷史 Markdown，避免再次觸發分析重算。
> 說明：該端點若返回 `task_id`，WebUI 會輪詢 `GET /api/v1/analysis/status/{task_id}` 展示狀態。狀態為 `completed` 時給出完成提示（報告已生成並按配置推送），狀態為 `failed` 時在前端錯誤區域顯示 `error` 原因。
> 說明：`GET /api/v1/history/{record_id}/diagnostics` 支援歷史記錄主鍵 ID 或 `query_id`，返回 `normal/degraded/failed/unknown` 摘要、關鍵鏈路元件和可複製的脫敏 `copy_text`；舊報告缺少診斷快照時返回 `unknown`，不影響報告讀取。
> 說明：`GET /api/v1/history` 的列表摘要可按 `stock_code` 分頁查詢同一股票歷史，並返回趨勢判斷、分析摘要、模型名與分析時價格/漲跌幅等可選欄位；舊記錄缺少快照欄位時返回空值。Web 報告頁的“歷史趨勢”抽屜複用該介面載入同股歷史。
> 說明（Issue #1520）：列表中的模型名展示欄位僅來源於歷史快照中的 `model_used`，僅用於歷史回溯展示，不影響執行時模型模型路由（`litellm_model`、`llm_model_list`）、Provider、Base URL 與配置遷移/清理語義。回退方式為回退本次提交，現網歷史查詢/抽屜/介面鏈路相容性保持不變。
> 說明：歷史詳情、同步分析響應和 completed 任務狀態會在 `report.details.analysis_context_pack_overview` 返回低敏輸入資料塊 overview；`details.context_snapshot` 會剝離該頂層欄位，不返回完整 `AnalysisContextPack` 或 Prompt summary。

> 相容性審計證據：
> - 官方來源：LiteLLM OpenAI-compatible provider 文件 <https://docs.litellm.ai/docs/providers/openai_compatible>；OpenAI Chat API 文件 <https://platform.openai.com/docs/api-reference/chat/create>；DeepSeek API 文件 <https://api-docs.deepseek.com/>。
> - 依賴版本：專案約束為 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（見 `requirements.txt`），以上相容語義迴歸測試在該版本視窗內執行。
> - 可複核測試：
>   - `tests/test_llm_channel_config.py`（配置源優先順序與 provider/base url 對映）
>   - `tests/test_market_review_runtime.py`（`build_market_review_runtime` 複用裝配路徑）
>   - `tests/test_analysis_api_contract.py`（`/api/v1/analysis/market-review` 合約與任務狀態鏈路）
> - 回滾/回退：若新路徑有問題，可先恢復歷史 `LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS` 與 legacy `GEMINI_*` / `OPENAI_*` / `ANTHROPIC_*` / `DEEPSEEK_*`，或透過桌面端備份或已啟用管理員鑑權的 Web 端 `POST /api/v1/system/config/import` 回滾並重啟；在執行時級別可暫時清空 `LITELLM_CONFIG` / `LLM_CHANNELS` 觸發 legacy 回退。

> 進度流說明：`GET /api/v1/analysis/tasks/stream` 除 `task_created / task_started / task_completed / task_failed` 外，新增 `task_progress` 事件。普通分析鏈路會在“行情準備 / 新聞檢索 / 上下文整理 / LLM 生成 / 報告儲存”等階段持續更新 `progress` 與 `message`。LiteLLM 流式返回僅在服務端累積完整文字，最終 JSON 解析成功後才會持久化歷史報告；若流式在首個 chunk 前不可用，會自動回退到原非流式呼叫；若已產生部分 chunk 後失敗，系統先嚐試同模型非流式重試，失敗後再按既有主模型->備用模型順序繼續嘗試。  
> 如果任務進度回撥異常，主鏈路不會中斷，系統會提升警告為 warning 級別並在服務端日誌中輸出完整異常，便於排查 SSE 推送斷點。
>  
> 說明：該特性屬於執行時 SSE 與回退鏈路細節，優先記錄於完整指南（`full-guide*.md`），不在 `README.md` 中展開詳細行為分支。

**呼叫示例**：
```bash
# 健康檢查
curl http://127.0.0.1:8000/api/health

# 觸發分析（TW/US）
curl -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H 'Content-Type: application/json' \
  -d '{"stock_code": "2330"}'

# 透傳策略（可選）
curl -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H 'Content-Type: application/json' \
  -d '{"stock_code": "AAPL", "skills": ["bull_trend", "growth_quality"]}'

# 查詢任務狀態
curl http://127.0.0.1:8000/api/v1/analysis/status/<task_id>

# 查詢今日 LLM 用量
curl "http://127.0.0.1:8000/api/v1/usage/summary?period=today"

# 觸發回測（全部股票）
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"force": false}'

# 觸發回測（指定股票）
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"code": "2330", "force": false}'

# 查詢整體回測表現
curl http://127.0.0.1:8000/api/v1/backtest/performance

# 查詢單股回測表現
curl http://127.0.0.1:8000/api/v1/backtest/performance/2330

# 分頁查詢回測結果
curl "http://127.0.0.1:8000/api/v1/backtest/results?page=1&limit=20"
```

### 自定義配置

修改預設埠或允許區域網訪問：

```bash
python main.py --serve-only --host 127.0.0.1 --port 8888
```

### 支援的股票程式碼格式

| 型別 | 格式 | 示例 |
|------|------|------|
| A股 | 6位數字 | `600519`、`000001`、`300750` |
| 北交所 | 8/4/92 開頭 6 位，支援 `BJ` 字首或 `.BJ` 字尾 | `920748`、`BJ920493`、`920493.BJ` |
| 港股 | hk + 5位數字 | `hk00700`、`hk09988` |
| 美股 | 1-5 字母（可選 .X 字尾） | `AAPL`、`TSLA`、`BRK.B` |
| 美股指數 | SPX/DJI/IXIC 等 | `SPX`、`DJI`、`NASDAQ`、`VIX` |

### 注意事項

- 瀏覽器訪問：`http://127.0.0.1:8000`（或您配置的埠）
- 在雲伺服器上部署後，不知道瀏覽器該輸入什麼地址？請看 [雲伺服器 Web 介面訪問指南](deploy-webui-cloud.md)
- 分析完成後自動推送通知到配置的通道
- 此功能在 GitHub Actions 環境中會自動禁用
- 另見 [openclaw Skill 整合指南](openclaw-skill-integration.md)

---

## 常見問題

### Q: 推送訊息被截斷？
A: 企業微信/飛書有訊息長度限制，系統已自動分段傳送。如需完整內容，可配置飛書雲文件功能。

### Q: 資料獲取失敗？
A: AkShare 使用爬蟲機制，可能被臨時限流。系統已配置重試機制，一般等待幾分鐘後重試即可。

### Q: 如何新增自選股？
A: 修改 `STOCK_LIST` 環境變數，多個程式碼用逗號分隔。

### Q: GitHub Actions 沒有執行？
A: 檢查是否啟用了 Actions，以及 cron 表示式是否正確（注意是 UTC 時間）。

---

更多問題請 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)

## Agent 工具資料快取與持久化

- `get_daily_history` 會先嚐試複用本地 `stock_daily` 日線快取；快取新鮮且至少覆蓋首頁預設的 30 條記錄時，不再重複請求外部資料來源。
- 當 Agent 請求的天數多於本地快取記錄數時，工具會返回實際可用記錄，並透過 `partial_cache=true`、`requested_days`、`actual_records` 標明這是部分快取命中。
- 快取缺失或過期時，工具仍會按原邏輯從資料來源獲取日線資料；獲取成功後會 best-effort 寫回 `stock_daily`，儲存失敗不會阻斷 Agent 回覆。
- `search_stock_news` 與 `search_comprehensive_intel` 成功返回後會 best-effort 寫入 `news_intel`，複用現有 URL / fallback key 去重邏輯。
- `get_realtime_quote` 不復用 `stock_daily` 作為實時行情快取，也不會把盤中實時行情寫入日線表；如需實時行情快取，應單獨設計實時行情儲存。

## Agent 事件警告監控

`AGENT_EVENT_MONITOR_ENABLED=true` 後，schedule 模式會按 `AGENT_EVENT_MONITOR_INTERVAL_MINUTES` 執行警告 worker。worker 每輪讀取 Alert API 建立並啟用的持久化規則，同時繼續相容 `AGENT_EVENT_ALERT_RULES_JSON` 中的 legacy 規則；觸發後仍傳送到現有通知通道。Alert API / Web 持久化規則支援實時價、漲跌幅、成交量、日線技術指標、`watchlist`、`portfolio_holdings`、`portfolio_account`，以及 `market` 大盤紅綠燈目標；legacy JSON 仍僅支援三類基礎規則。

> 相容與遷移說明：本節記錄當前事件警告規則（含 `price_change_percent`）執行時行為，未變更模型名、provider、Base URL、LiteLLM、`OPENAI_*`、`DEEPSEEK_*`、`GEMINI_*` 等外部模型/API 配置語義。legacy JSON 不會被自動遷移、刪除或改寫；若需回退，刪除或關閉 `AGENT_EVENT_MONITOR_ENABLED` 即可停止後臺警告 worker。

| `alert_type` | 方向欄位 | 閾值欄位 | 說明 |
| --- | --- | --- | --- |
| `price_cross` | `above` / `below` | `price` | 當前價上破或下破指定價格 |
| `price_change_percent` | `up` / `down` | `change_pct` | 漲跌幅達到指定百分比 |
| `volume_spike` | - | `multiplier` | 最新成交量超過近 20 日均量的指定倍數 |
| `ma_price_cross` | `above` / `below` | `window` | 日線 close 相對 MA(window) 邊緣上穿或下穿 |
| `rsi_threshold` | `above` / `below` | `period`、`threshold` | RSI 邊緣上穿或下穿閾值 |
| `macd_cross` | `bullish_cross` / `bearish_cross` | `fast_period`、`slow_period`、`signal_period` | DIF/DEA 邊緣金叉或死叉 |
| `kdj_cross` | `bullish_cross` / `bearish_cross` | `period`、`k_period`、`d_period` | K/D 邊緣金叉或死叉 |
| `cci_threshold` | `above` / `below` | `period`、`threshold` | CCI 邊緣上穿或下穿閾值 |
| `portfolio_stop_loss` | `mode=near|breach` | - | 帳戶級止損接近或觸發 |
| `portfolio_concentration` | - | - | 帳戶級 symbol 集中度 |
| `portfolio_drawdown` | - | - | 帳戶級最大回撤警告 |
| `portfolio_price_stale` | - | - | 持股價格 stale 或 missing |
| `market_light_status` | - | `statuses` | 當前大盤紅綠燈狀態命中 `red/yellow` 列表 |
| `market_light_score_drop` | - | `min_drop` | 相比上一交易日 Market Light score 下降達到閾值 |

示例：

```env
AGENT_EVENT_MONITOR_ENABLED=true
AGENT_EVENT_MONITOR_INTERVAL_MINUTES=5
AGENT_EVENT_ALERT_RULES_JSON=[{"stock_code":"2330","alert_type":"price_cross","direction":"above","price":1000},{"stock_code":"AAPL","alert_type":"price_change_percent","direction":"down","change_pct":3.0},{"stock_code":"NVDA","alert_type":"volume_spike","multiplier":2.5}]
```

worker 會把 `triggered`、`skipped`、`degraded`、`failed` 寫入 `alert_triggers` 作為評估歷史；正常未觸發不寫歷史。DB 持久化規則的 `triggered` 歷史按 `rule_id + target + data_source + data_timestamp` 對同一資料點做 best-effort 去重，重複命中會複用最早一條觸發記錄，`data_timestamp` 缺失時不去重。真實觸發後會把每個通知通道的 attempt 寫入 `alert_notifications`，併為 Alert API 建立的持久化規則寫入 `alert_cooldowns` 業務冷卻狀態；若讀取持久化冷卻失敗，worker 會臨時使用程序內 fingerprint 防止 DB 異常期間重複推送。legacy `AGENT_EVENT_ALERT_RULES_JSON` 規則繼續使用程序內 fingerprint 抑制，不寫持久化冷卻；通知基礎設施的 `notification_noise.py` 降噪仍獨立生效。Web 規則列表使用後端返回的 `cooldown_active` 判斷冷卻狀態，避免瀏覽器本地時區解析影響展示。

技術指標規則只使用日線 close 的邊緣觸發，partial bar 處理是伺服器本地時區 + 16:00 的啟發式，不做市場日曆精確判定。`watchlist` 每輪重新整理 `STOCK_LIST` 後展開，`portfolio_holdings` 從持股快照的非零持股按 symbol 去重展開，`portfolio_account` 複用持股風險服務做帳戶級聚合評估。`market` 規則的 target 僅支援 `cn|hk|us`，使用結構化 `MarketLightSnapshot`；`trade_date` 來自當次 market overview，`data_quality=unavailable` 會跳過觸發，非交易日會被交易日 gate 跳過，`market_light_score_drop` 只比較跨交易日 score。WebUI 的“警告”頁面可以管理持久化規則、執行一次性 dry-run 測試，並檢視觸發歷史、通知嘗試結果和只讀冷卻狀態；批次規則的列表冷卻狀態是父規則摘要，子目標冷卻以觸發歷史為準。詳細邊界見 [實時警告中心](alerts.md)。

## 持股管理說明

### `/portfolio` 頁面可做什麼

- 檢視全量持股或切換到單個帳戶視角。
- 在 `fifo` / `avg` 兩種成本法之間切換，檢視快照 KPI、風險摘要和 Top Positions 集中度圖表。
- 直接在 Web 頁面新增帳戶，或錄入交易、現金流水、公司行動等事件。
- 透過 CSV 匯入持股記錄，支援先 `dry_run` 預覽，再決定是否正式寫入。
- 在事件列表中按帳戶、日期、方向、程式碼等條件篩選，並對單帳戶事件做刪除修正。

### 相關介面

| 介面 | 方法 | 說明 |
|------|------|------|
| `/api/v1/portfolio/snapshot` | GET | 查詢持股快照 |
| `/api/v1/portfolio/risk` | GET | 查詢風險摘要 |
| `/api/v1/portfolio/trades` | GET | 分頁查詢交易記錄 |
| `/api/v1/portfolio/cash-ledger` | GET | 分頁查詢現金流水 |
| `/api/v1/portfolio/corporate-actions` | GET | 分頁查詢公司行動 |
| `/api/v1/portfolio/imports/csv/brokers` | GET | 查詢內建 CSV 券商解析器 |
| `/api/v1/portfolio/fx/refresh` | POST | 手動重新整理匯率快取 |
| `/api/v1/portfolio/trades/{trade_id}` | DELETE | 刪除交易記錄 |
| `/api/v1/portfolio/cash-ledger/{entry_id}` | DELETE | 刪除現金流水 |
| `/api/v1/portfolio/corporate-actions/{action_id}` | DELETE | 刪除公司行動 |

> 查詢類介面統一支援 `account_id`、`date_from`、`date_to`、`page`、`page_size` 等常見篩選引數；事件列表會返回統一的 `items`、`total`、`page`、`page_size` 結構。

### 使用行為說明

- CSV 匯入內建 `huatai`、`citic`、`cmb` 解析器；若券商列表介面失敗，Web 端會自動回退到這些內建選項。
- 匯入流程會先把 CSV 解析成標準化記錄，再逐條提交到持股賬本；遇到忙碌行會計入 `failed_count`，不會因為單行衝突讓整批請求整體失敗。
- 交易去重優先使用帳戶內唯一的 `trade_uid`，缺失時回退到基於日期、程式碼、方向、數量、價格、費用、稅費、幣種的確定性雜湊。
- 賣出會先校驗可用數量，超賣返回 `409 portfolio_oversell`；併發寫入衝突時可能返回 `409 portfolio_busy`。
- 持股快照的 `positions[]` 會返回 `price_source`、`price_date`、`price_stale`、`price_available` 等價格元資訊；當天快照會先嚐試實時行情，實時價不可用或非正值時再回退到 `as_of` 當天或之前最近的歷史收盤價，歷史 `as_of` 快照不會拉取實時價，也不會再把成本價靜默當作現價；缺價持股會標記 `price_available=false` 並從市值與未實現盈虧彙總中排除。
- 匯率重新整理會先嚐試線上源；若線上獲取失敗，則回退到最近一次快取並標記 `is_stale=true`，避免快照和風險頁整體不可用。
- 當 `PORTFOLIO_FX_UPDATE_ENABLED=false` 時，手動重新整理介面會明確返回“線上重新整理已禁用”，頁面不會誤導為“當前沒有可重新整理的匯率對”。
- 風險摘要包含集中度、回撤、止損接近度等資訊；`sector_concentration` 會優先嚐試按板塊歸類，失敗時降級到 `UNCLASSIFIED`，不會阻斷風險結果返回。

### Agent 讀取持股

- Agent 可透過 `get_portfolio_snapshot` 獲取面向帳戶的緊湊持股摘要，預設包含精簡風險塊，適合控制 Token 開銷。
- 可選引數包括 `account_id`、`cost_method`、`as_of`、`include_positions`、`include_risk`。
- 若風險塊生成失敗，快照仍會返回；若當前環境未啟用持股模組，工具會返回結構化 `not_supported`。

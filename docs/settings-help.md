# 設定頁配置幫助維護說明

設定頁配置幫助用於把配置項的關鍵說明放到 WebUI 內部，減少使用者在設定頁和文件之間反覆切換。頁面上仍保留短描述，詳細說明透過配置項標題旁的 help icon 開啟。

本文只說明幫助系統的維護規則，不替代完整配置文件。配置語義、預設值、執行時優先順序和排障細節仍以 `.env.example`、`docs/full-guide.md` 及對應專題文件為事實源。

## 資料結構

後端配置登錄檔在 `src/core/config_registry.py` 中為欄位追加幫助後設資料：

- `help_key`：前端多語言幫助文案的穩定 key。
- `examples`：可直接展示的配置樣例。敏感欄位只能使用佔位符，例如 `sk-xxxx`、`your_token`。
- `docs`：相關文件連結，優先指向倉庫內已有專題文件或完整指南。
- `warning_codes`：面向前端或後續校驗擴充套件的穩定提示 code。

前端長文案維護在 `apps/dsa-web/src/locales/settingsHelp.ts`：

- 預設展示中文文案。
- 英文文案保留同樣結構，便於後續擴充套件語言切換。
- 文案應解釋用途、取值說明、影響範圍、注意事項和相關文件，不應複製完整專題文件。

## 覆蓋範圍

PR1 覆蓋基礎設施與首批代表性配置項：

- `STOCK_LIST`
- `LITELLM_MODEL`
- `LLM_CHANNELS`
- `FEISHU_WEBHOOK_URL`
- `WEBUI_HOST`

PR2 繼續覆蓋高頻、易填錯配置項：

- AI 模型執行時：Agent 主模型、fallback 模型、高階 YAML 路由、temperature、provider API Key、OpenAI-compatible Base URL。
- LLM Channels 編輯器內部欄位：通道名、協議、Base URL、API Key、模型列表、執行時能力檢測、主模型、Agent 主模型、fallback、Vision 和 temperature。
- 資料來源與搜尋：Tushare、股票索引遠端更新開關、實時行情優先順序、實時技術指標、搜尋 API Key、SearXNG、籌碼分佈、新聞視窗。
- 通知：Webhook、Telegram、郵件、Discord/Slack 等聊天平臺、報告輸出、Webhook SSL 校驗。
- WebUI / auth / schedule / proxy：Host、Port、登入保護、可信反向代理、定時任務、交易日檢查、網路代理。

PR3 registered-field slice / 階段性補齊：聚焦 Web 設定頁中實際展示/可配置欄位的 Help 補齊，包括通用配置卡片當前可見欄位和 AI legacy 條件可見欄位：

- Agent 配置（21 欄位）：Agent 模式、最大推理步數、策略列表、策略目錄、自然語言路由、架構、編排器模式、超時、風險否決、Deep Research 預算/超時、記憶、策略自動權重、策略路由、問股可見對話上下文壓縮、事件監控開關/間隔、警告規則 JSON。
- 回測配置（5 欄位）：回測開關、評估視窗、最小記錄年齡、引擎版本、中性回報帶。
- 報告配置（9 欄位）：僅推送摘要、顯示模型名、模板目錄、渲染引擎、完整性校驗/重試、歷史訊號對比、逐股推送、合併郵件。
- 通知路由配置（9 欄位）：報告/警告/系統錯誤通道路由、去重/冷卻、靜默時段/時區、最低等級、每日摘要（預留）。
- 系統執行時（7 欄位）：日誌級別、除錯模式、最大併發、分析間隔、大盤分析開關/市場/配色。
- AI legacy 與 Anspire 配置：provider 專用多 Key、模型名、溫度、Vision 模型、max tokens 與 Anspire LLM 閘道器欄位。
- 資料來源與搜尋：TickFlow、SerpAPI、Brave、Bocha、MiniMax、SearXNG 公共例項、BIAS 閾值和 Pytdx 伺服器欄位。
- 通知高階欄位：飛書高階安全/應用欄位、Telegram topic、Discord/Slack 高階欄位、Pushover、ntfy、Gotify、PushPlus、ServerChan3、AstrBot 和自定義 Webhook 高階模板/鑑權欄位。

Issue #1512 收口後，Web 設定頁只展示後端配置登錄檔中的正式欄位。未註冊的 `.env` key 不再作為普通可編輯設定項展示，避免 raw key、`Auto-inferred field metadata.` 和無 help 按鈕的配置項進入中文介面；這些 key 仍可透過 `.env` 檔案或匯入/匯出能力保留和維護。

例外：`LLM_CHANNELS` 宣告的動態通道詳情鍵（如 `LLM_DEEPSEEK_API_KEY`、`LLM_MY_PROXY_MODELS`）會保留在配置介面返回中，供“AI 模型接入”編輯器讀取和儲存；它們不作為普通配置卡片展示，也不復用 `WEB_SETTINGS_HIDDEN_FROM_UI` 的運維隱藏語義。

暫不納入 Web 設定頁展示的低頻/運維類 `.env` 變數包括 `DATABASE_PATH`、`SQLITE_*`、`USE_PROXY`、`PROXY_HOST`、`PROXY_PORT` 等。若後續需要在 Web 中編輯這些欄位，應先在 `src/core/config_registry.py` 中正式註冊並補齊 help 後設資料，而不是依賴自動推斷。

### 覆蓋邊界

- `settingsHelp.ts` 中的 `settings.llm_channel.*` 系列為 LLM 通道編輯器內部欄位說明，僅用於前端渲染，不對應 `.env` 的單獨配置項；這是 PR2 中刻意的“內建擴充套件”設計，用於提升編輯器可用性。
- 其餘 help 文案均應能從 `src/core/config_registry.py` 中某個欄位的 `help_key` 對映到後端註冊後設資料，便於與文件源、`warning_codes` 一起統一維護。

## 事實源優先順序

新增或修改幫助文案時，優先從以下位置核對：

1. `.env.example`：配置鍵名、預設值、樣例格式和敏感佔位符。
2. `docs/full-guide.md`：主要配置說明、執行入口和部署上下文。
3. `docs/LLM_CONFIG_GUIDE.md`、`docs/llm-providers.md`：LLM 優先順序、Channels、provider/model、相容邊界和排障說明。
4. 專題文件：例如 `docs/bot/feishu-bot-config.md`、`docs/deploy-webui-cloud.md`、`docs/desktop-package.md`。
5. 程式碼實現和測試：當文件與程式碼不一致時，先以可執行實現為準，並同步修正文件。

## 維護邊界

- 幫助文案不能改變配置儲存、校驗、執行時優先順序、`.env` 寫回或環境變數覆蓋語義。
- 不展示真實金鑰、賬號、token、Webhook 完整值或本機絕對路徑。
- LLM 相關示例如果寫入具體 provider 字首、模型名或 Base URL，必須能追溯到當前倉庫文件或官方來源；否則應使用佔位符或連結到事實源。
- 對第三方模型/API 的可用性、LiteLLM 相容視窗或 provider fallback 規則，不在設定幫助中單獨承諾；需要變更時必須同步更新專題文件和 PR 相容性說明。
- 中英雙語文案應保持同一語義範圍。若只更新一種語言，需要在交付說明中寫明原因。
- 首屏短描述保持簡潔，詳細說明放在 help dialog 中，避免 hover tooltip 與常駐短描述重複。

## 重啟語義

設定頁儲存通常只寫入 `.env` 並觸發可執行時過載的配置重新整理。幫助文案和 `warning_codes` 必須顯式區分以下情況：

- `WEBUI_HOST`、`WEBUI_PORT`：監聽地址和埠只在程序啟動時繫結，儲存後必須重啟當前程序、Docker 容器或服務管理器才會生效。
- `RUN_IMMEDIATELY`：非 schedule 模式啟動期單次執行配置，儲存後不會讓已執行的 WebUI/API 程序立即觸發分析。
- `SCHEDULE_ENABLED`、`SCHEDULE_RUN_IMMEDIATELY`：schedule 模式啟動行為，儲存後不會啟動、停止或重建當前 scheduler，需要以 schedule 模式重啟後生效。
- `SCHEDULE_TIME`：不是重啟必需項。已執行的 schedule 模式會在下一輪排程檢查中讀取新時間並重建 daily job；但如果當前程序未以 schedule 模式啟動，儲存該欄位不會自動建立 scheduler。

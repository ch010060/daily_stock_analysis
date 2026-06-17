# 通知能力基線

本文件記錄通知能力 P0-P7 終態：通道、配置 key、GitHub Actions 對映、Web 設定後設資料、CLI 診斷口徑、Web 一鍵測試、自定義 Webhook Body 模板語義、通知路由策略、降噪機制、聚合報告失敗隔離、ntfy / Gotify 一等通道、WebPush / Apprise 評估，以及本地 / Docker / GitHub Actions / Desktop 場景化配置說明。P0 只做基線與只讀診斷；P1 增加 Web 單通道真實測試；P2 產品化現有 Body 模板；P3 增加 report / alert / system_error 路由；P4 增加程序內降噪；P5 強化測試診斷和聚合報告逐通道失敗隔離；P6-A 新增 ntfy；P6-C 新增 Gotify；P6-D 只評估 WebPush / Apprise；P7 收口文件與 Actions env 對照表自動化，不新增執行時依賴、配置入口、per-URL 模板、跨程序持久化、真實每日摘要或重試迴圈。

## 通道基線

| 通道 | 型別 | Minimal key | Advanced key | 說明 |
| --- | --- | --- | --- | --- |
| 企業微信 | 靜態配置 | `WECHAT_WEBHOOK_URL` | `WECHAT_MSG_TYPE` | 配置後參與批次通知傳送 |
| 飛書 Webhook | 靜態配置 | `FEISHU_WEBHOOK_URL` | `FEISHU_WEBHOOK_SECRET`, `FEISHU_WEBHOOK_KEYWORD` | `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 不會單獨開啟群 Webhook 推送 |
| Telegram | 靜態配置 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `TELEGRAM_MESSAGE_THREAD_ID` | token 與 chat id 必須同時存在 |
| 郵件 | 靜態配置 | `EMAIL_SENDER`, `EMAIL_PASSWORD` | `EMAIL_RECEIVERS`, `EMAIL_SENDER_NAME` | `EMAIL_RECEIVERS` 留空時發給自己 |
| Pushover | 靜態配置 | `PUSHOVER_USER_KEY`, `PUSHOVER_API_TOKEN` | - | 兩個 key 必須同時存在 |
| ntfy | 靜態配置 | `NTFY_URL` | `NTFY_TOKEN`, `WEBHOOK_VERIFY_SSL` | `NTFY_URL` 必須包含 topic path，例如 `https://ntfy.sh/my-topic` |
| Gotify | 靜態配置 | `GOTIFY_URL`, `GOTIFY_TOKEN` | `WEBHOOK_VERIFY_SSL` | `GOTIFY_URL` 是 server base URL，不包含 `/message`；token 透過 `X-Gotify-Key` Header 傳送 |
| PushPlus | 靜態配置 | `PUSHPLUS_TOKEN` | `PUSHPLUS_TOPIC` | `PUSHPLUS_TOPIC` 僅在 token 存在時生效 |
| Server醬3 | 靜態配置 | `SERVERCHAN3_SENDKEY` | - | 手機 App 推送 |
| 自定義 Webhook | 靜態配置 | `CUSTOM_WEBHOOK_URLS` | `CUSTOM_WEBHOOK_BEARER_TOKEN`, `CUSTOM_WEBHOOK_BODY_TEMPLATE`, `WEBHOOK_VERIFY_SSL` | 支援多個 URL，逗號分隔 |
| Discord | 靜態配置 | `DISCORD_WEBHOOK_URL` 或 `DISCORD_BOT_TOKEN` + `DISCORD_MAIN_CHANNEL_ID` | `DISCORD_INTERACTIONS_PUBLIC_KEY` | Webhook 與 Bot 均可啟用傳送 |
| Slack | 靜態配置 | `SLACK_WEBHOOK_URL` 或 `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` | - | Bot 優先用於文字與圖片同頻道傳送 |
| AstrBot | 靜態配置 | `ASTRBOT_URL` | `ASTRBOT_TOKEN`, `WEBHOOK_VERIFY_SSL` | `ASTRBOT_TOKEN` 可選 |
| `UNKNOWN` | 兜底列舉 | - | - | 僅為未知通道兜底，不由靜態環境變數啟用 |
| 釘釘會話 | 執行時上下文 | - | - | 從來源訊息上下文提取，無法僅由 `.env` 靜態判斷 |
| 飛書會話 | 執行時上下文 | - | - | 從來源訊息上下文提取，互動式命令結果僅回到來源會話 |
| Telegram 會話 | 執行時上下文 | - | - | 從來源訊息上下文提取，互動式命令結果僅回到來源會話 |

## Minimal / Advanced 分層

- Minimal key：足以啟用一個通知通道的最小配置。
- Advanced key：隻影響認證、安全、格式、執行緒、群組、證書校驗或展示行為，不能單獨啟用通道。
- P3 的 `NOTIFICATION_*_CHANNELS` 屬於 Advanced key：只收窄已啟用通道，不會單獨啟用通道。
- P4 的 `NOTIFICATION_DEDUP_TTL_SECONDS`、`NOTIFICATION_COOLDOWN_SECONDS`、`NOTIFICATION_QUIET_HOURS`、`NOTIFICATION_TIMEZONE`、`NOTIFICATION_MIN_SEVERITY`、`NOTIFICATION_DAILY_DIGEST_ENABLED` 屬於 Advanced key：隻影響已啟用靜態通道的傳送策略，不會單獨啟用通道。
- `REPORT_SHOW_LLM_MODEL` 是報告展示開關：預設 `true` 時在通知報告底部顯示本次分析使用的 LLM 模型，設為 `false` 時隱藏。該引數僅影響報告渲染，不會更改執行時的 provider/model/Base URL、LiteLLM 路由、模型儲存、遷移或清理邏輯；回退方式為改回 `true` 或刪除該變數。
- `WEBHOOK_VERIFY_SSL` 是讀取該配置的 webhook-style HTTPS 通知請求共用的證書校驗開關。
- WebPush、Apprise、更細粒度路由、跨程序降噪和真實每日摘要暫不進入執行時實現；相關配置如未來引入，應先更新本文件、`.env.example`、Web 後設資料與迴歸測試。
- Bark 保持 custom webhook 基線，不新增 `BARK_*` 一等配置。

## 報告渲染與分片

當前預設推送報告的入口、內容來源和整體版式保持不變。本階段只收斂通知渲染的技術路線：沉澱通道能力畫像、傳送前訊息結構和結構感知分片能力，避免後續按通道擴充套件時繼續在各 sender 中堆疊平行邏輯。

預設傳送路徑沿用既有 sender 行為，不接入新增 renderer：飛書和 Telegram 繼續使用原有相容轉換，企業微信、Slack 繼續使用原有分片邏輯，避免改變線上可見報告版式。新增的通道能力畫像、PreparedMessage、renderer preset 和結構感知分片僅作為後續擴充套件基礎；如需啟用企業微信、飛書、Telegram、Slack 等通道專用 renderer，應透過顯式配置、真實傳送驗證和迴歸測試逐步接入。

相容性排除說明：
- 本輪未改動 `src/notification_sender/wechat_sender.py`、`src/notification_sender/slack_sender.py`、`src/notification_sender/feishu_sender.py`、`src/notification_sender/telegram_sender.py` 的傳送路徑；現有 `send_to_*` 呼叫鏈（`src/notification.py -> sender method`）沿用既有行為。
- `model_used` 只在報告渲染末尾展示，不參與 provider/model/base_url 的 runtime 選擇、儲存、清理或遷移。若某次 CI 掃描到“provider/API 相容遷移”類關鍵詞，命中範圍應優先回歸到測試夾具中的 `model_used` 示例與報告快照 fixture（`tests/fixtures/notification_reports/*.md`），以及 `src/notification.py` 對 `report_show_llm_model` 的僅展示開關邏輯。
- `REPORT_SHOW_LLM_MODEL` 與 `report_renderer_enabled` 均為展示/降級策略開關：關閉僅影響報告可見結構，不會觸發配置遷移或執行時引數回退；回退方式為恢復 `true`（或移除該項）或恢復預設配置。

關聯板塊渲染保持報告正文生成階段處理：當板塊表現資料不可用且所有板塊型別均缺失時，只輸出一行板塊名稱；有板塊型別或板塊漲跌榜訊號時繼續使用表格。

## GitHub Actions 對映

倉庫自帶 `.github/workflows/00-daily-analysis.yml` 只顯式匯入固定變數名。P0/P3/P4/P6 已把 Body 模板、安全項、PushPlus topic、路由、降噪、ntfy 和 Gotify 等通知 key 納入預設 workflow。下面的表格由 `scripts/generate_notification_actions_env_table.py` 從 workflow `env:` 和通知診斷後設資料生成，避免手寫對照表和真實 Actions 對映繼續漂移。

<!-- notification-actions-env-table:start -->

| Key | Tier | Channel / feature | Actions source | Default |
| --- | --- | --- | --- | --- |
| `WECHAT_WEBHOOK_URL` | minimal | wechat | Secret | - |
| `WECHAT_MSG_TYPE` | advanced | wechat | Variable or Secret | `markdown` |
| `FEISHU_WEBHOOK_URL` | minimal | feishu | Secret | - |
| `FEISHU_WEBHOOK_SECRET` | advanced | feishu | Secret | - |
| `FEISHU_WEBHOOK_KEYWORD` | advanced | feishu | Variable or Secret | - |
| `TELEGRAM_BOT_TOKEN` | minimal | telegram | Secret | - |
| `TELEGRAM_CHAT_ID` | minimal | telegram | Secret | - |
| `TELEGRAM_MESSAGE_THREAD_ID` | advanced | telegram | Secret | - |
| `EMAIL_SENDER` | minimal | email | Variable or Secret | - |
| `EMAIL_PASSWORD` | minimal | email | Secret | - |
| `EMAIL_RECEIVERS` | advanced | email | Variable or Secret | - |
| `EMAIL_SENDER_NAME` | advanced | email | Variable or Secret | `daily_stock_analysis股票分析助手` |
| `PUSHOVER_USER_KEY` | minimal | pushover | Secret | - |
| `PUSHOVER_API_TOKEN` | minimal | pushover | Secret | - |
| `NTFY_URL` | minimal | ntfy | Secret | - |
| `NTFY_TOKEN` | advanced | ntfy | Secret | - |
| `GOTIFY_URL` | minimal | gotify | Secret | - |
| `GOTIFY_TOKEN` | minimal | gotify | Secret | - |
| `PUSHPLUS_TOKEN` | minimal | pushplus | Secret | - |
| `PUSHPLUS_TOPIC` | advanced | pushplus | Variable or Secret | - |
| `CUSTOM_WEBHOOK_URLS` | minimal | custom | Secret | - |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | advanced | custom | Secret | - |
| `CUSTOM_WEBHOOK_BODY_TEMPLATE` | advanced | custom | Variable or Secret | - |
| `WEBHOOK_VERIFY_SSL` | advanced | ntfy, gotify, custom, astrbot | Variable or Secret | `true` |
| `DISCORD_WEBHOOK_URL` | minimal | discord | Secret | - |
| `DISCORD_BOT_TOKEN` | minimal | discord | Secret | - |
| `DISCORD_MAIN_CHANNEL_ID` | minimal | discord | Secret | - |
| `ASTRBOT_URL` | minimal | astrbot | Secret | - |
| `ASTRBOT_TOKEN` | advanced | astrbot | Secret | - |
| `SERVERCHAN3_SENDKEY` | minimal | serverchan3 | Secret | - |
| `SLACK_WEBHOOK_URL` | minimal | slack | Secret | - |
| `SLACK_BOT_TOKEN` | minimal | slack | Secret | - |
| `SLACK_CHANNEL_ID` | minimal | slack | Secret | - |
| `NOTIFICATION_REPORT_CHANNELS` | advanced | routing | Variable or Secret | - |
| `NOTIFICATION_ALERT_CHANNELS` | advanced | routing | Variable or Secret | - |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | advanced | routing | Variable or Secret | - |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | advanced | noise | Variable or Secret | `0` |
| `NOTIFICATION_COOLDOWN_SECONDS` | advanced | noise | Variable or Secret | `0` |
| `NOTIFICATION_QUIET_HOURS` | advanced | noise | Variable or Secret | - |
| `NOTIFICATION_TIMEZONE` | advanced | noise | Variable or Secret | - |
| `NOTIFICATION_MIN_SEVERITY` | advanced | noise | Variable or Secret | - |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | advanced | noise | Variable or Secret | `false` |

<!-- notification-actions-env-table:end -->

預設 workflow 仍不對映 `MARKDOWN_TO_IMAGE_CHANNELS` 與 `MERGE_EMAIL_NOTIFICATION`。它們是傳送形態或聚合行為開關，不是通道憑證；在 Actions 中自動開始讀取同名 Secret/Variable 會引入額外行為變化。

## CLI 診斷

```bash
python main.py --check-notify
```

該命令只讀配置，不傳送通知，不寫入 `.env`。它會在配置載入和日誌初始化後立即執行，完成後直接退出，不再進入 Web、排程、大盤覆盤或預設分析流程。

- 返回碼 `0`：沒有 error 級診斷。
- 返回碼 `1`：存在 error，例如 0 個靜態通知通道已配置，或成對 key 只配置了一半。

## Web 一鍵測試

Web 設定頁的“通知通道”分類提供單通道測試入口。測試會使用當前頁面草稿值合成臨時配置，傳送一條真實測試通知，但不會儲存 `.env`，也不會修改執行時全域性配置。

- 測試範圍：13 個靜態通知通道，不包含 `UNKNOWN` 和執行時上下文通道。
- 普通通道：返回單次傳送結果、耗時和通用錯誤碼。
- 自定義 Webhook：按 URL 順序返回 attempts，展示每個 URL 的成功/失敗、HTTP 狀態、耗時和錯誤碼；多個 URL 部分成功時，頂層 message 會標出成功數 / 總數。
- 返回結果會脫敏 token、secret、password、Bearer、完整 webhook query 和疑似 path token。
- 配置缺失或傳送失敗返回 `success=false`，不會影響已儲存配置和預設分析流程。

## 自定義 Webhook Body 模板

`CUSTOM_WEBHOOK_BODY_TEMPLATE` 是自定義 Webhook 的全域性 JSON body 模板。配置後，它會先於 URL 自動識別生效，因此會覆蓋 Bark、Slack、Discord、釘釘等自動 payload。未配置時仍使用原有 URL 自動識別；渲染後不是合法 JSON object 時會記錄錯誤並回退預設 payload，不中斷主通知流程。

可用佔位符：

- `$content_json`：JSON 轉義後的通知正文，推薦預設使用。
- `$title_json`：JSON 轉義後的通知標題，推薦預設使用。
- `$content` / `$title`：原始字串，不做 JSON 轉義。正文含雙引號、反斜槓或換行時可能導致 JSON 無效並觸發 fallback。

通用 webhook 示例：

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"content":$content_json}
```

Bark 透過 custom webhook 使用時，直接把 Bark endpoint 放入 `CUSTOM_WEBHOOK_URLS`，不需要額外 `BARK_*` 配置。未配置全域性模板時，系統會按 `api.day.app` 自動生成 `title` / `body` / `group`；如果配置全域性模板，需要自己寫出 Bark body：

```env
CUSTOM_WEBHOOK_URLS=https://api.day.app/YOUR_BARK_KEY
```

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"body":$content_json,"group":"stock"}
```

AstrBot 已是一等通知通道，優先使用 `ASTRBOT_URL` 和可選的 `ASTRBOT_TOKEN`。只有需要把 AstrBot 相容端點放入 `CUSTOM_WEBHOOK_URLS` 時，才使用 custom webhook 模板，例如：

```env
CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$content_json}
```

ntfy 已是一等通知通道，優先使用 `NTFY_URL` 和可選的 `NTFY_TOKEN`。`NTFY_URL` 表示完整 topic endpoint，例如 `https://ntfy.sh/my-topic` 或 `https://self-hosted:port/my-topic`；系統會解析最後一個 path segment 作為 topic，並向 server root 傳送 JSON publish：

```env
NTFY_URL=https://ntfy.sh/my-topic
NTFY_TOKEN=
```

Gotify 已是一等通知通道，優先使用 `GOTIFY_URL` 和 `GOTIFY_TOKEN`。`GOTIFY_URL` 表示 Gotify server base URL，可包含反向代理 path prefix，但不包含 `/message`；系統傳送時會拼接固定 `/message` API，並透過 `X-Gotify-Key` Header 傳送 application token。`NTFY_URL` 是完整 topic endpoint，而 `GOTIFY_URL` 是 server base URL，這是兩個服務 API 設計差異導致的刻意選擇：

```env
GOTIFY_URL=https://gotify.example
GOTIFY_TOKEN=app-token
```

```env
# 反向代理 path prefix 示例；實際請求會傳送到 https://example.com/gotify/message
GOTIFY_URL=https://example.com/gotify
GOTIFY_TOKEN=app-token
```

NapCat / OneBot HTTP API 需要按實際 endpoint 和目標型別調整。下面只是常見 body 形態示例，`user_id`、`group_id`、URL 路徑和鑑權方式都應以你的 NapCat 配置為準：

```env
# 私聊：CUSTOM_WEBHOOK_URLS=http://127.0.0.1:3000/send_private_msg
CUSTOM_WEBHOOK_BODY_TEMPLATE={"user_id":123456,"message":$content_json}
```

```env
# 群聊：CUSTOM_WEBHOOK_URLS=http://127.0.0.1:3000/send_group_msg
CUSTOM_WEBHOOK_BODY_TEMPLATE={"group_id":123456789,"message":$content_json}
```

## 通知路由策略

P3 新增三類通知路由配置：

| 路由型別 | 配置 key | 當前生產者 |
| --- | --- | --- |
| `report` | `NOTIFICATION_REPORT_CHANNELS` | 單股推送、聚合日報、大盤覆盤、合併推送、飛書文件成功連結 |
| `alert` | `NOTIFICATION_ALERT_CHANNELS` | EventMonitor 觸發通知 |
| `system_error` | `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | 預留能力；當前不新增自動系統錯誤生產者 |

配置值為逗號分隔通道列舉：`wechat,feishu,telegram,email,pushover,ntfy,gotify,pushplus,serverchan3,custom,discord,slack,astrbot`。

- 留空或未配置：保持舊行為，傳送到所有已配置靜態通道。
- 非空：只傳送到路由列表與已配置通道的交集；交集為空時不會 fallback 到全通道。
- `send_to_context()` 不受路由限制，機器人會話上下文仍會收到觸發任務的回覆。
- 互動式命令（釘釘會話、飛書會話、Telegram）帶有來源上下文時，會跳過 `FEISHU_WEBHOOK_URL` 等靜態通知通道；`SCHEDULE`、CLI、API 或無來源上下文的任務仍按 report 路由傳送。
- 路由過濾發生在 Markdown 轉圖片前，`MARKDOWN_TO_IMAGE_CHANNELS` 只對路由後的通道子集生效。
- `MERGE_EMAIL_NOTIFICATION` 不需要額外配置；只要 `email` 仍在 report 路由後的通道中，現有合併郵件行為保持不變。
- `--check-notify` 會把未知通道值報為 error，把合法但未啟用的路由目標報為 warning。

## 聚合報告失敗隔離

P5 強化聚合報告通知路徑的失敗邊界：`_send_notifications()` 在 report 路由過濾後對每個靜態通知通道單獨傳送。某個通道拋異常會記錄日誌並視為該通道失敗，但不會跳過後續通道，也不會中斷分析主流程。

- 郵件按 receiver group 單獨隔離；某個收件人分組失敗時，後續分組仍會繼續傳送。
- 任一靜態通道傳送成功時，P4 降噪 reservation 會寫入正式記錄；全部靜態通道失敗或拋異常時，會釋放 reservation。
- `send_to_context()` 仍獨立於靜態通道 route 和降噪記錄，用於回覆觸發任務的 Bot 會話上下文。

## 通知降噪機制

P4 新增程序內降噪，隻影響靜態配置通道，不影響 `send_to_context()` 的機器人觸發會話回執。預設所有配置關閉，未設定時保持舊行為。

| 配置 key | 預設值 | 說明 |
| --- | --- | --- |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | `0` | 同一穩定去重 key 在 TTL 內只傳送一次；`0` 關閉 |
| `NOTIFICATION_COOLDOWN_SECONDS` | `0` | 同一冷卻 key 在視窗內限頻；`0` 關閉 |
| `NOTIFICATION_QUIET_HOURS` | 空 | 靜默時段，格式 `HH:MM-HH:MM`，支援跨午夜 |
| `NOTIFICATION_TIMEZONE` | 空 | 靜默時段時區，如 `Asia/Shanghai`；留空使用 Python 執行時本地時區（通常由程序 `TZ` 或系統時區決定） |
| `NOTIFICATION_MIN_SEVERITY` | 空 | `info`, `warning`, `error`, `critical`；留空不過濾 |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | `false` | 預留配置；當前不會傳送每日摘要或持久化摘要內容 |

嚴重級別預設值：

- `report`：`info`
- `alert`：`warning`
- `system_error`：`error`
- 未知或未設定路由：`info`

實現邊界：

- 去重 / 冷卻狀態是當前 Python 程序內 dict，適用於 `main.py` 單程序和 `--serve` 單 worker。
- `uvicorn --workers N`、多容器或多臺機器場景下狀態不共享，降噪為 per-worker 近似生效。
- pipeline 單股和聚合報告路徑使用穩定 key，避免報告內生成時間變化擊穿去重；其他未顯式傳入 `dedup_key` 的 report 通知按內容 hash 去重。
- 未顯式傳入 `cooldown_key` 的呼叫按路由和嚴重級別共享預設冷卻槽位，例如 report / info 的普通通知會共用同一個槽位。
- 同一程序內相同 key 的併發傳送會先佔用短生命週期 in-flight 槽位，避免突發重複傳送；靜態通道全部失敗時釋放該槽位，不寫入正式去重 / 冷卻狀態。
- 降噪判斷異常時 fail-open：記錄日誌並繼續傳送靜態通道。
- `NOTIFICATION_TIMEZONE` 留空時使用 `datetime.now().astimezone()` 解析到的執行時本地時區；Actions / Docker 場景建議顯式配置 `NOTIFICATION_TIMEZONE` 以避免時區歧義。

## WebPush / Apprise 評估

P6-D 只做設計評估，不新增依賴、`.env` 配置或執行時通知路徑。結論是兩者都不適合在本輪直接混入通道實現 PR。

WebPush 後續如要實現，需要先單獨設計訂閱生命週期與安全邊界：

- 需要 Web 前端註冊 Service Worker；Service Worker / `PushManager.subscribe()` 依賴 secure context，生產環境通常必須走 HTTPS，本地開發可使用 localhost。
- 需要 VAPID 公私鑰；訂閱時要下發 public key，服務端傳送時要持有 private key 並保護好金鑰輪換策略。
- 需要瀏覽器許可權互動，訂閱必須由使用者手勢觸發，不能在後臺靜默開啟。
- `PushSubscription` 包含 endpoint 和加密 key，endpoint 屬於 capability URL，應按 secret 處理並脫敏展示。
- 需要持久化訂閱、處理訂閱失效和裝置解綁；當前 `.env` / 單程序配置模型不適合直接塞多個使用者/裝置訂閱。
- 提交、刪除、更新訂閱的 API 要有認證和 CSRF 防護，不能只靠前端隱藏入口。

Apprise 後續如要引入，應先作為可選依賴評估，而不是預設依賴：

- Apprise 是通用通知庫，覆蓋面廣，但會與當前已有 WeChat、Telegram、Discord、Slack、ntfy、Gotify、Pushover 等一等通道重疊。
- 需要評估依賴體積、安裝失敗路徑、Docker 映象膨脹、GitHub Actions 依賴快取和可選 extras 策略。
- secret 傳遞不能直接暴露完整 Apprise URL；需要統一脫敏、Web 測試目標遮罩和錯誤日誌過濾。
- 傳送失敗應隔離在 Apprise 通道內，不能影響已有通道的失敗隔離語義。
- 如果採用 Apprise，建議先新增單獨 experimental channel 或 CLI-only spike，再決定是否納入 Web 設定頁和 Actions env。

## 本地配置

本地執行優先使用專案根目錄 `.env`。複製 `.env.example` 後填寫至少一個 minimal key 即可啟用對應靜態通知通道；advanced key 只改變認證、安全、格式、路由或降噪行為，不會單獨啟用通道。

```bash
python main.py --check-notify
```

`--check-notify` 是隻讀診斷：不傳送通知、不寫 `.env`、不進入分析流程。配置好 WebUI 後，也可以在系統設定頁用單通道測試傳送真實測試訊息；該測試只使用頁面草稿臨時配置，不儲存 `.env`。

## Docker

Docker 場景可透過 `--env-file .env` / Compose `env_file` 注入執行時環境變數，也可以掛載 `.env` 讓 Web 設定頁和後端讀寫同一份配置檔案。只注入環境變數但不掛載 `.env` 時，Web 設定頁儲存後的值在容器重啟後可能被部署環境再次覆蓋。

降噪靜默時段建議顯式配置 `NOTIFICATION_TIMEZONE`，避免容器預設時區與預期不一致。自簽名內網 webhook 可臨時使用 `WEBHOOK_VERIFY_SSL=false`，但不要在公網鏈路關閉證書校驗。

## GitHub Actions

預設 `00-daily-analysis.yml` 只讀取表格中顯式對映的 Secret / Variable。新增 repository Secret 或 Variable 後，只有變數名已經出現在 workflow `env:` 中才會進入執行程序；`STOCK_GROUP_N` / `EMAIL_GROUP_N` 這類任意編號變數不會自動匯入。

Secret 適合 token、password、webhook URL 等敏感項；Variable 適合 `WECHAT_MSG_TYPE`、`EMAIL_SENDER_NAME`、路由、降噪視窗和時區這類非敏感行為配置。`MARKDOWN_TO_IMAGE_CHANNELS` 與 `MERGE_EMAIL_NOTIFICATION` 預設不對映，如需在自己的 fork 中使用，應顯式修改 workflow 並補充對應測試。

## Desktop

桌面端複用 Web 設定頁的通知配置和單通道測試入口。通知測試會傳送真實測試訊息，但只使用當前頁面草稿值，不會自動儲存；需要持久化時仍需點選儲存配置。

桌面端可透過配置匯出 / 匯入恢復 `.env`。回滾某個通知通道時，清空該通道 minimal key 並儲存即可；advanced key 留存不會單獨啟用通道，但建議同步清理以減少後續排障噪音。

## 回滾方式

- 本地 / Docker：恢復舊 `.env`，或刪除對應通道 minimal key 後重啟程序。
- GitHub Actions：清空或刪除對應 Secret / Variable；未對映的 key 不會進入 workflow 執行程序。
- Desktop：使用配置備份匯入舊 `.env`，或在設定頁清空對應通道配置並儲存。
- 版本回退：P6/P7 新增的 `NTFY_*`、`GOTIFY_*`、路由和降噪 key 在舊版本中會被忽略；若要避免誤導，應同時從 `.env` 或 Actions 配置中移除。

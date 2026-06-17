# 飛書通知配置指南

本文只解決兩類常見訴求：

1. 把分析結果推送到飛書群
2. 避免把飛書應用模式和群機器人 Webhook 模式混用

## 先分清兩種模式

### 模式一：群機器人 Webhook 推送

適用場景：
- 你只想把分析報告推送到飛書群
- 不需要處理飛書訊息回撥
- 不需要 Stream Bot

這也是本專案最推薦、最容易落地的飛書通知方式。

需要配置的變數：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
# 按需填寫
FEISHU_WEBHOOK_SECRET=your_sign_secret
FEISHU_WEBHOOK_KEYWORD=股票日報
```

### 模式二：飛書應用 / Stream Bot / 雲文件

適用場景：
- 你要做飛書應用機器人互動
- 你要啟用 Stream 模式
- 你要用飛書雲文件能力

相關變數：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_STREAM_ENABLED=true
```

注意：
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 不會直接開啟群 Webhook 推送
- 只想收通知時，不要只填 App ID / Secret，必須優先配置 `FEISHU_WEBHOOK_URL`
- 如果你做的是應用機器人 / Stream Bot，可直接看文末保留的原流程截圖參考

## Webhook 推送的正確配置步驟

### 1. 在飛書群裡建立自定義機器人

路徑通常是：
- 群聊
- 群設定
- 群機器人
- 新增機器人
- 自定義機器人

完成後複製機器人提供的 Webhook URL。

示例：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### 2. 檢視機器人安全設定

飛書群機器人常見有三種安全限制：

1. 不加任何安全設定
2. 開啟“關鍵詞”
3. 開啟“簽名校驗”

如果你的機器人開啟了額外安全項，專案側也必須同步配置，否則請求會被飛書拒絕。

#### 開啟了關鍵詞

把飛書裡配置的同一個關鍵詞寫到：

```env
FEISHU_WEBHOOK_KEYWORD=股票日報
```

專案會自動在每條飛書訊息前補上這個關鍵詞，你不需要手工改報告模板。

#### 開啟了簽名校驗

把飛書裡顯示的 secret 寫到：

```env
FEISHU_WEBHOOK_SECRET=your_sign_secret
```

專案會自動按飛書要求為每條訊息補 `timestamp` 和 `sign`。

### 3. 啟動並驗證

只要配置了 `FEISHU_WEBHOOK_URL`，通知傳送就會走 Webhook 通道。

如果你還同時填了：

```env
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
```

也不會影響 Webhook 推送；但它們本身不能替代 `FEISHU_WEBHOOK_URL`。

### 4. 在飛書自動化裡配置 Webhook 觸發器

如果你在飛書自動化流程裡消費本專案推送的卡片訊息，請按下面配置：

1. 在建立 Webhook 觸發器時，**引數** 填寫下面 JSON（`content` 可按需保留佔位符）：

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
    "elements": [
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "..."
        }
      }
    ],
    "header": {
      "title": {
        "tag": "plain_text",
        "content": "A股智慧分析報告"
      }
    }
  }
}
```

2. 在 **操作/訊息內容** 部分，不要手填純文字；點選加號選擇 **Webhook 觸發**，並對映到：

`card.elements[0].text.content`

![img_11.png](img_11.png)

## 最常見的失敗原因

### 1. 只填了 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`

現象：
- 你覺得“飛書已經配好了”
- 實際完全收不到群通知

原因：
- 這兩個變數是應用模式用的，不是群 Webhook 推送入口

正確做法：
- 補 `FEISHU_WEBHOOK_URL`

### 2. 飛書機器人開啟了關鍵詞，但本地沒配 `FEISHU_WEBHOOK_KEYWORD`

現象：
- 其他 App 能發
- 本專案發不進去，或者飛書直接返回校驗失敗

正確做法：
- 把飛書機器人安全設定中的關鍵詞原樣填到 `FEISHU_WEBHOOK_KEYWORD`

### 3. 飛書機器人開啟了簽名校驗，但本地沒配 `FEISHU_WEBHOOK_SECRET`

現象：
- Webhook URL 看起來沒問題
- 但飛書返回簽名相關錯誤

正確做法：
- 把機器人 secret 填到 `FEISHU_WEBHOOK_SECRET`

### 4. 機器人沒在目標群裡，或者沒有發言許可權

檢查：
- 機器人是否真的被新增到了目標群
- 群管理員是否限制了機器人發訊息

### 5. 飛書側配置了 IP 白名單

如果你在雲伺服器、Docker、GitHub Actions 上跑，出口 IP 可能和本地不同。

檢查：
- 飛書機器人是否啟用了 IP 白名單
- 當前執行環境出口 IP 是否在白名單裡

## 建議的最小可用配置

### 無額外安全限制

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
```

### 開啟關鍵詞

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
FEISHU_WEBHOOK_KEYWORD=股票日報
```

### 開啟簽名校驗

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
FEISHU_WEBHOOK_SECRET=your_sign_secret
```

### 同時開啟關鍵詞和簽名

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your_hook_token
FEISHU_WEBHOOK_SECRET=your_sign_secret
FEISHU_WEBHOOK_KEYWORD=股票日報
```

## 排查順序建議

1. 先確認你要的是“群 Webhook 推送”還是“應用 / Stream Bot”
2. 只做群推送時，先保證 `FEISHU_WEBHOOK_URL` 已配置
3. 回到飛書機器人安全設定，確認是否啟用了關鍵詞或簽名
4. 若啟用了，就補齊 `FEISHU_WEBHOOK_KEYWORD` / `FEISHU_WEBHOOK_SECRET`
5. 最後再檢查機器人是否在群裡、是否有許可權、是否命中 IP 白名單

## 附：應用 / Stream Bot 原流程截圖參考

如果你不是單純做群 Webhook 推送，而是要繼續配置飛書應用、長連線機器人或雲文件，可以參考下面這組原截圖。

### 1. 建立應用

https://open.feishu.cn/document/develop-an-echo-bot/introduction

![img_6.png](img_6.png)

![img_8.png](img_8.png)

### 2. 獲取金鑰

![img_7.png](img_7.png)

### 3. 釋出應用

![img_5.png](img_5.png)

### 4. 在飛書中開啟應用

![img_9.png](img_9.png)

### 5. 訊息互動

![img_10.png](img_10.png)

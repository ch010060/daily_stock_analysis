<div align="center">

# 📈 股票智慧分析系統

[![GitHub stars](https://img.shields.io/github/stars/ZhuLinsen/daily_stock_analysis?style=social)](https://github.com/ZhuLinsen/daily_stock_analysis/stargazers)
[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Ready-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/zhulinsen/daily_stock_analysis)

<p align="center">
  <a href="https://trendshift.io/repositories/18527" target="_blank"><img src="https://trendshift.io/api/badge/repositories/18527" alt="ZhuLinsen%2Fdaily_stock_analysis | Trendshift" width="230" /></a>&nbsp;<a href="https://hellogithub.com/repository/ZhuLinsen/daily_stock_analysis" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=6daa16e405ce46ed97b4a57706aeb29f&claim_uid=pfiJMqhR9uvDGlT&theme=neutral" alt="Featured｜HelloGitHub" width="230" /></a>
</p>

> 🤖 基於 AI 大模型的台股 / 美股自選股智慧分析系統，每日自動分析並推送「決策儀表板」到企業微信 / 飛書 / Telegram / Discord / Slack / 郵件

[**產品預覽**](#-產品預覽) · [**功能特性**](#-功能特性) · [**快速開始**](#-快速開始) · [**推送效果**](#-推送效果) · [**文件中心**](docs/INDEX.md) · [**完整指南**](docs/full-guide.md)

</div>

## 🖥️ 產品預覽

<p align="center">
  <img src="docs/assets/readme_workspace_tour_20260510.gif" alt="DSA Web 工作臺演示" width="720">
</p>

## ✨ 功能特性

| 能力 | 覆蓋內容 |
|------|------|
| AI 決策報告 | 核心結論、評分、趨勢、買賣點位、風險警報、催化因素、操作檢查清單 |
| 台股 / 美股資料聚合 | 台股、美股、ETF、主要指數；行情、K 線、技術指標、資金流、籌碼、新聞、公告和基本面 |
| 本地標的查詢 | Local-first TW/US symbol universe，支援股票代號、股票名稱、常見英文別名與候選選擇 |
| Web / 桌面工作臺 | 手動分析、任務進度、歷史報告、完整 Markdown、回測、持股、配置管理、淺色 / 深色主題 |
| Agent 策略問股 | 多輪追問，支援均線、纏論、波浪、趨勢、熱點、事件、成長、預期等內建策略，覆蓋 Web/Bot/API |
| 智慧匯入與補全 | 圖片、CSV/Excel、剪貼簿匯入；股票代號 / 名稱 / 別名補全 |
| 自動化與推送 | GitHub Actions、Docker、本地定時任務、FastAPI 服務和企業微信 / 飛書 / Telegram / Discord / Slack / 郵件推送 |

> 功能細節、欄位契約、基本面 P0 超時語義、交易紀律、資料來源優先順序、Web/API 行為請看 [完整配置與部署指南](docs/full-guide.md)。

### 技術棧與資料來源

| 型別 | 支援 |
|------|------|
| AI 模型 | Gemini、OpenAI 相容、DeepSeek、通義千問、Claude、Ollama 本地模型等 |
| 行情資料 | FinMind、YFinance、Longbridge、Alpha Vantage、Finnhub，以及專案內建的台股 / 美股資料適配與降級路徑 |
| 新聞搜尋 | SearXNG、Tavily、Brave Search，以及可選的搜尋服務適配 |
| 社交輿情 | Stock Sentiment API（Reddit / X / Polymarket，僅美股，可選） |

> 完整規則見 [資料來源配置](docs/full-guide.md#資料來源配置)。

## 🚀 快速開始

### 方式一：GitHub Actions（推薦）

> 5 分鐘完成部署，零成本，無需伺服器。

#### 1. Fork 本倉庫

點選右上角 `Fork` 按鈕（順便點個 Star⭐ 支援一下）

#### 2. 配置 Secrets

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**AI 模型配置（至少配置一個）**

預設先選一個模型服務商並填寫 API Key；需要多模型、圖片識別、本地模型或高階路由時，再參考 [LLM 配置指南](docs/LLM_CONFIG_GUIDE.md)。

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `GEMINI_API_KEY` | Google Gemini API Key | 可選 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | 可選 |
| `OPENAI_API_KEY` | OpenAI 相容 API Key（支援 DeepSeek、通義千問等） | 可選 |
| `OPENAI_BASE_URL` / `OPENAI_MODEL` | 使用 OpenAI 相容服務時填寫 | 可選 |

> Ollama 更適合本地 / Docker 部署，GitHub Actions 推薦使用雲端 API。

**通知通道配置（至少配置一個）**

| Secret 名稱 | 說明 |
|------------|------|
| `WECHAT_WEBHOOK_URL` | 企業微信機器人 |
| `FEISHU_WEBHOOK_URL` | 飛書機器人 |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Telegram |
| `DISCORD_WEBHOOK_URL` | Discord Webhook |
| `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` | Slack Bot |
| `EMAIL_SENDER` + `EMAIL_PASSWORD` | 郵件推送 |

更多通道、簽名校驗、分組郵件、Markdown 轉圖片等配置見 [通知通道詳細配置](docs/full-guide.md#通知通道詳細配置)。

**自選股配置（必填）**

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `STOCK_LIST` | 自選股代號，如 `2330,00981A,AAPL,SPY` | ✅ |

**新聞源配置（推薦）**

新聞源會顯著影響輿情、公告、事件和催化因素質量，建議至少配置一個搜尋服務。

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `TAVILY_API_KEYS` | Tavily 通用新聞搜尋 API | 推薦 |
| `BRAVE_API_KEYS` | Brave Search API，美股資訊補強 | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項：無配額兜底，適合私有部署 | 可選 |

更多搜尋源、社交輿情和降級規則見 [搜尋服務配置](docs/full-guide.md#搜尋服務配置)。

#### 3. 啟用 Actions

`Actions` 標籤 → `I understand my workflows, go ahead and enable them`

#### 4. 手動測試

`Actions` → `每日股票分析` → `Run workflow` → `Run workflow`

#### 完成

預設每個**工作日 18:00（台北時間）**自動執行，也可手動觸發。預設非交易日不執行；強制執行、交易日檢查、斷點續傳等規則見 [完整指南](docs/full-guide.md#定時任務配置)。

### 方式二：本地執行 / Docker 部署

```bash
# 克隆專案
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git && cd daily_stock_analysis

# 安裝依賴
pip install -r requirements.txt

# 配置環境變數
cp .env.example .env && vim .env

# 執行分析
python main.py
```

常用命令：

```bash
python main.py --debug
python main.py --dry-run
python main.py --stocks 2330,00981A,AAPL,SPY
python main.py --market-review
python main.py --schedule
python main.py --serve-only
```

> Docker 部署、定時任務、雲伺服器訪問請參考 [完整指南](docs/full-guide.md)；桌面客戶端打包請參考 [桌面端打包說明](docs/desktop-package.md)。

## 📱 推送效果

### 決策儀表板
```
🎯 2026-02-08 決策儀表板
共分析3只股票 | 🟢買進:0 🟡觀望:2 🔴賣出:1

📊 分析結果摘要
⚪ 台積電(2330): 觀望 | 評分 72 | 看多
⚪ Apple(AAPL): 觀望 | 評分 68 | 震盪偏多
🟡 群聯(8299): 賣出 | 評分 42 | 震盪

⚪ 台積電 (2330)
📰 重要資訊速覽
💭 輿情情緒: 市場關注 AI 伺服器與先進製程需求，情緒偏積極，但需留意短期估值與匯率波動。
📊 業績預期: 近期法說與產業新聞顯示高階製程需求仍是主要支撐，後續仍需追蹤毛利率與資本支出。

🚨 風險警報:

風險點1：短線漲幅已高，需留意追價風險。
風險點2：匯率與海外需求變化可能影響財測。
風險點3：供應鏈庫存調整可能造成單季波動。
✨ 利好催化:

利好1：AI 晶片與高效能運算需求維持高檔。
利好2：先進封裝與高階製程仍具長期競爭力。
📢 最新動態: 【最新訊息】相關資訊顯示市場持續關注先進製程、AI 伺服器需求與海外客戶訂單能見度。

---
生成時間: 18:00
```

### 盤勢回顧
```
🎯 2026-01-10 盤勢回顧

📊 主要指數
- 加權指數: 23520.12 (🟢+0.85%)
- S&P 500: 6121.36 (🟢+1.02%)
- Nasdaq 100: 22156.78 (🟢+1.35%)

📈 市場概況
台股電子權值股走強，美股大型科技股延續反彈，市場風險偏好回升。

🔥 類股表現
領漲: 半導體、伺服器、雲端軟體
領跌: 防禦型消費、公用事業、傳統能源
```

## ⚙️ 配置說明

完整環境變數、模型通道、通知通道、資料來源優先順序、交易紀律、基本面 P0 語義和部署說明請參考 [完整配置指南](docs/full-guide.md)。

## 🖥️ Web 介面

Web 工作臺提供配置管理、任務監控、手動分析、歷史報告、完整 Markdown 報告、Agent 問股、回測、持股管理、智慧匯入和淺色 / 深色主題。啟動方式：

```bash
python main.py --webui
python main.py --webui-only
```

訪問 `http://127.0.0.1:8000` 即可使用。認證、智慧匯入、搜尋補全、歷史報告複製、雲伺服器訪問等細節見 [本地 WebUI 管理介面](docs/full-guide.md#本地-webui-管理介面)。

## 🤖 Agent 策略問股

配置任意可用 AI API Key 後，Web `/chat` 頁面即可使用策略問股；如需顯式關閉可設定 `AGENT_MODE=false`。

- 支援均線金叉、纏論、波浪理論、多頭趨勢、熱點題材、事件驅動、成長質量、預期重估等內建策略
- 支援實時行情、K 線、技術指標、新聞和風險資訊呼叫
- 支援多輪追問、會話匯出、傳送到通知通道和後臺執行
- 支援自定義策略檔案與多 Agent 編排（實驗性）

> Agent 具體引數、`skill` 命名相容、多 Agent 模式和預算護欄見 [完整指南](docs/full-guide.md#本地-webui-管理介面) 與 [LLM 配置指南](docs/LLM_CONFIG_GUIDE.md)。

## 📄 License

[MIT License](LICENSE) © 2026 ZhuLinsen

歡迎在二次開發或引用時註明本倉庫來源，感謝支援專案持續維護。

## ⚠️ 免責宣告

本專案僅供學習和研究使用，不構成任何投資建議。股市有風險，投資需謹慎。作者不對使用本專案產生的任何損失負責。

---

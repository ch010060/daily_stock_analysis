# 文件中心

這裡是專案文件入口。README 負責專案概覽和快速開始；更完整的配置、部署、功能說明和排障內容從這裡進入。

## 按場景選擇

| 我想要 | 先看 | 繼續看 |
| --- | --- | --- |
| 快速瞭解專案能做什麼 | [README](../README.md) | [完整配置與部署指南](full-guide.md) |
| 第一次把專案跑起來 | [小白客戶端安裝與配置](beginner-client-setup.md) | [完整配置與部署指南](full-guide.md) |
| 配置大模型通道 | [LLM 配置指南](LLM_CONFIG_GUIDE.md) | [LLM 服務商配置指南](llm-providers.md) |
| 配置推送通知 | [通知能力基線](notifications.md) | [完整配置與部署指南](full-guide.md) |
| 部署到伺服器或雲平臺 | [部署指南](DEPLOY.md) | [雲端 WebUI 部署](deploy-webui-cloud.md)、[Zeabur 部署](docker/zeabur-deployment.md) |
| 使用 Bot / IM 接入 | [Bot 命令與接入](bot-command.md) | [Bot 平臺配置](bot/) |
| 排查執行問題 | [FAQ](FAQ.md) | [更新日誌](CHANGELOG.md) |
| 參與開發或提交 PR | [貢獻指南](CONTRIBUTING.md) | [API 規格](architecture/api_spec.json) |

## 快速開始

| 文件 | 內容 |
| --- | --- |
| [README](../README.md) | 專案定位、核心能力、快速開始、推送效果 |
| [小白客戶端安裝與配置](beginner-client-setup.md) | 面向不會程式碼使用者的客戶端下載、Anspire Open / AIHubMix 模型配置、新聞源配置和常見問題 |
| [完整配置與部署指南](full-guide.md) | 環境準備、執行方式、配置說明、部署路徑和常見問題 |
| [FAQ](FAQ.md) | 常見配置、模型、通知、部署和執行問題 |
| [更新日誌](CHANGELOG.md) | 版本變化、能力調整和遷移說明 |

## 配置

| 文件 | 內容 |
| --- | --- |
| [LLM 配置指南](LLM_CONFIG_GUIDE.md) | 大模型通道、三層配置、Web 設定頁和常見模型配置 |
| [LLM 服務商配置指南](llm-providers.md) | Provider 預設、Actions 對映、錯誤分類和診斷建議 |
| [LiteLLM YAML 示例](examples/litellm_config.example.yaml) | LiteLLM 多通道配置示例 |
| [通知能力基線](notifications.md) | 企業微信、飛書、Telegram、Discord、Slack、郵件等通知通道配置 |
| [Tushare 股票列表指南](TUSHARE_STOCK_LIST_GUIDE.md) | Tushare 股票列表相關配置和使用說明 |

## 使用專題

| 文件 | 內容 |
| --- | --- |
| [Bot 命令與接入](bot-command.md) | Bot 命令、Webhook、平臺接入和回撥說明 |
| [Bot 平臺配置](bot/) | 飛書、釘釘、Discord 等 Bot 配置截圖和補充說明 |
| [實時警告中心](alerts.md) | EventMonitor 基線、Web 規則管理、通知結果、冷卻狀態和 Phase 邊界 |
| [分析上下文包契約、執行態消費與可見性](analysis-context-pack.md) | AnalysisContextPack 首版範圍、欄位質量狀態、P1/P2 內部契約、P3 Prompt 摘要消費、P4 歷史/API/Web 低敏可見性、P5 資料質量評分與原始碼錨點 |
| [圖片識別 Prompt](image-extract-prompt.md) | 圖片識別股票資訊的 Prompt 與使用邊界 |
| [OpenClaw Skill 整合](openclaw-skill-integration.md) | OpenClaw / Skill 外部整合說明 |

## 部署與打包

| 文件 | 內容 |
| --- | --- |
| [部署指南](DEPLOY.md) | 伺服器部署、Docker、systemd、Supervisor 等部署方式 |
| [雲端 WebUI 部署](deploy-webui-cloud.md) | 雲伺服器訪問 WebUI 的部署說明 |
| [Zeabur 部署](docker/zeabur-deployment.md) | Zeabur 平臺部署說明 |
| [桌面端打包說明](desktop-package.md) | Electron 桌面端和 Web 構建產物打包說明 |

## 參考與開發

| 文件 | 內容 |
| --- | --- |
| [API 規格](architecture/api_spec.json) | FastAPI OpenAPI 規格產物 |
| [貢獻指南](CONTRIBUTING.md) | Issue、PR、測試、文件同步和協作要求 |

## 多語言

| 文件 | 內容 |
| --- | --- |
| [英文文件索引](INDEX_EN.md) | English documentation index |
| [英文 README](README_EN.md) | English project overview and quick start |
| [繁中 README](README_CHT.md) | 繁體中文專案概覽與快速開始 |

# 小白客戶端安裝與配置指南

這份文件寫給不會程式碼、只想下載客戶端直接用的使用者。目標很簡單：下載客戶端，填一個模型服務金鑰（Key），填股票程式碼，然後生成第一份分析報告。

> 本專案生成的是輔助分析報告，不構成投資建議。真實交易請自行判斷風險。

## 先準備

1. Windows 或 macOS 電腦。
2. 一個模型服務金鑰（Key），推薦從下面任選一個：
   - [Anspire Open](https://open.anspire.cn/?share_code=QFBC0FYC)：支援全球主流模型，一個 Key 可同時用於模型和新聞搜尋，第一次配置最省事。
   - [AIHubMix](https://aihubmix.com/?aff=CfMq)：支援全球主流模型，適合想在一個平臺切換多種模型的使用者。
3. 想分析的股票程式碼，例如 `600519,hk00700,AAPL`。

## 1. 下載客戶端

開啟發布頁：

<https://github.com/ZhuLinsen/daily_stock_analysis/releases/latest>

在頁面下方 `Assets`（附件）裡下載：

| 電腦 | 下載哪個 |
| --- | --- |
| Windows | `daily-stock-analysis-windows-installer-<版本號>.exe` |
| Windows 不想安裝 | `daily-stock-analysis-windows-noinstall-<版本號>.zip` |
| macOS Apple 晶片 | `daily-stock-analysis-macos-arm64-<版本號>.dmg` |
| macOS Intel 晶片 | `daily-stock-analysis-macos-x64-<版本號>.dmg` |

不用下載 `latest.yml`、`*.blockmap`，它們不是客戶端安裝包。

不知道 Mac 是哪種晶片：點選左上角蘋果圖示 -> 關於本機，看到 M1/M2/M3/M4 就選 `arm64`，看到 Intel 就選 `x64`。

## 2. 安裝並開啟

- Windows 安裝包：雙擊 `.exe`，按提示安裝，安裝目錄用預設位置即可。
- Windows 免安裝包：解壓 `.zip`，雙擊 `Daily Stock Analysis.exe`。
- macOS：雙擊 `.dmg`，把應用拖到 `Applications`。如果提示來自未驗證開發者，在系統設定的隱私與安全性裡允許開啟。

macOS 使用者升級前建議先在客戶端設定裡匯出一次配置備份。

## 3. 配置 AI 模型

開啟客戶端，進入：

`系統設定 -> AI 模型`

只選下面一個方案即可。

> 重要：每次改完設定後，都要點選頁面上的儲存按鈕；看到儲存成功提示後，再切換頁面或回到首頁。

### 方案 A：Anspire Open

1. 開啟 [Anspire Open](https://open.anspire.cn/?share_code=QFBC0FYC)，註冊 / 登入後建立 API Key。
2. 回到客戶端，在快速新增通道里選擇 `Anspire Open`。
3. 貼上 API Key。
4. 模型名選擇控制檯裡已開通的模型；不確定就先選控制檯推薦或輕量模型。
5. 點選儲存；看到儲存成功後，再點選測試連線。

### 方案 B：AIHubMix

1. 開啟 [AIHubMix](https://aihubmix.com/?aff=CfMq)，註冊 / 登入後建立 API Key。
2. 回到客戶端，在快速新增通道里選擇 `AIHubmix（聚合平臺）`。
3. 貼上 API Key。
4. 模型名選擇控制檯裡已開通的模型；不確定就先選控制檯推薦模型。
5. 點選儲存；看到儲存成功後，再點選測試連線。

看到測試成功，就繼續下一步。

## 4. 填寫自選股

進入：

`系統設定 -> 基礎設定`

找到 `自選股列表`，填寫：

`600519,hk00700,AAPL`

多個股票用英文逗號隔開。常見寫法：

- A 股：`600519`、`300750`、`000001`
- 港股：`hk00700`、`hk09988`
- 美股：`AAPL`、`TSLA`、`NVDA`

填完點選儲存，看到儲存成功後再回首頁。

## 5. 建議配置新聞源

新聞源不是必填，但建議配置。它會影響近期新聞、公告、事件驅動、熱點題材和風險提示。

進入：

`系統設定 -> 資料來源`

按你的模型服務選擇：

1. 用 Anspire Open：找到 `Anspire API Keys`，填入同一個 Anspire Key，儲存成功後即可。
2. 用 AIHubMix：建議再申請 [SerpAPI](https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis) 或 [Tavily](https://tavily.com/) 的 Key，填到 `SerpAPI API Keys` 或 `Tavily API Keys`，儲存成功後即可。

想先試用也可以跳過新聞源，客戶端仍然能生成基礎分析。

## 6. 開始分析

回到首頁：

1. 輸入股票程式碼，例如 `600519`。
2. 點選分析。
3. 等任務從排隊、分析中變成分析完成。
4. 在歷史記錄裡檢視報告。

## 常見問題

### 下載頁面裡檔案很多，該下哪個？

普通 Windows 使用者下載 `.exe` 安裝包。不要下載 `latest.yml` 或 `*.blockmap`。

### API Key 填了還是不能用？

檢查這幾項：

1. Key 是否複製完整，沒有多餘空格。
2. 平臺賬號是否有餘額或額度。
3. 當前模型是否已開通。
4. 測試連線裡是否提示模型不存在、許可權不足或餘額不足。

### 配置亂了怎麼辦？

在客戶端設定裡匯出配置備份。出問題時可以匯入之前的備份，或者只保留這三項重新配置：AI 模型、自選股、新聞源。

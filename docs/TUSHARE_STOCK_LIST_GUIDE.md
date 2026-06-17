# Tushare 股票列表獲取工具使用說明

## 功能概述

從 Tushare Pro 獲取 A股、港股、美股列表資訊，儲存為 CSV 檔案到本地。

## 快速開始

### 1. 配置 Token

在專案根目錄的 `.env` 檔案中新增 Tushare Token：

```bash
TUSHARE_TOKEN=你的tushare_token
```

> 獲取 Token：訪問 [Tushare Pro](https://tushare.pro/weborder/#/login) 註冊並獲取

### 2. 執行指令碼

```bash
python3 scripts/fetch_tushare_stock_list.py
```

如需針對 A 股名稱狀態做修正，可以加上 `--a-rk`，指令碼會保持 `stock_basic` 作為基礎來源，再用 `rt_k` 對帶 `XD`、`XR`、`DR`、`N`、`C` 字首的名稱進行回填，並覆蓋輸出到 `data/stock_list_a.csv`：

```bash
python3 scripts/fetch_tushare_stock_list.py --a-rk
```

### 3. 檢視輸出

資料將儲存到 `data/` 目錄：

```
data/
├── stock_list_a.csv       # A股列表（--a-rk 時為修正後名稱）
├── stock_list_hk.csv      # 港股列表
├── stock_list_us.csv      # 美股列表
└── README_stock_list.md   # 資料說明文件
```

## 功能特性

✅ **自動分頁**：美股資料自動分頁讀取（每頁5000條）
✅ **智慧限流**：每次請求之間隨機休息5-10秒
✅ **錯誤處理**：單個市場失敗不影響其他市場
✅ **進度提示**：實時顯示讀取進度
✅ **自動文件**：生成詳細的資料說明文件

## 市場說明

| 市場 | 介面 | 積分要求 | 資料量 |
|------|------|----------|--------|
| A股 | stock_basic | 2000積分 | ~5000只 |
| 港股 | hk_basic | 2000積分 | ~2000只 |
| 美股 | us_basic | 120試用/5000正式 | ~10000只 |

## 輸出檔案格式

### A股（stock_list_a.csv）

執行 `--a-rk` 時，這個檔案會寫入修正後的 A 股名稱。

```csv
ts_code,symbol,name,area,industry,market,exchange,list_date,...
000001.SZ,000001,平安銀行,深圳,銀行,主機板,SZSE,19910403,...
600519.SH,600519,貴州茅臺,貴州,白酒,主機板,SSE,20010827,...
```

### 港股（stock_list_hk.csv）

```csv
ts_code,name,fullname,market,list_date,trade_unit,curr_type,...
00700.HK,騰訊控股,騰訊控股有限公司,主機板,20040616,100,HKD,...
00005.HK,滙豐控股,滙豐控股有限公司,主機板,19750401,100,HKD,...
```

### 美股（stock_list_us.csv）

```csv
ts_code,name,enname,classify,list_date,...
AAPL,蘋果,Apple Inc.,EQT,19801212,...
TSLA,特斯拉,Tesla Inc.,EQT,20100629,...
BABA,阿里巴巴,Alibaba Group,ADR,20140919,...
```

## 使用示例

### Python 讀取資料

```python
import pandas as pd

# 讀取 A股
a_stocks = pd.read_csv('data/stock_list_a.csv')
print(f"A股數量: {len(a_stocks)}")

# 篩選主機板股票
main_board = a_stocks[a_stocks['market'] == '主機板']
print(f"主機板數量: {len(main_board)}")

# 查詢特定股票
stock = a_stocks[a_stocks['ts_code'] == '600519.SH']
print(stock[['name', 'industry', 'list_date']])
```

### 重新整理股票自動補全索引

推薦直接使用一鍵重新整理指令碼，它會預設在抓取 A 股時使用 `--a-rk`，然後生成並同步自動補全索引：

```bash
pip install -r requirements.txt
python3 scripts/refresh_stock_index.py
```

生成自動補全索引依賴 `pypinyin` 寫入中文股票的完整拼音和拼音首字母欄位；缺少該依賴時指令碼會直接失敗，避免生成無法支援拼音搜尋的降級索引。

如果你只想單獨更新 CSV，可以先抓取資料：

```bash
python3 scripts/fetch_tushare_stock_list.py --a-rk
```

如果已經有新的 CSV，只想重新生成索引：

```bash
python3 scripts/generate_index_from_csv.py --test  # 先測試
python3 scripts/generate_index_from_csv.py         # 確認後生成
```

### 本地客戶端自動獲取最新索引

新版客戶端預設會從專案 GitHub `main` 分支讀取最新的 `apps/dsa-web/public/stocks.index.json`，並快取到本地 `data/cache/stocks.index.json`。前端仍訪問本地 `/stocks.index.json`，不需要直接跨域請求 GitHub。

遠端索引地址、檢查頻率和網路超時時間為系統內建值，不提供使用者配置項；使用者只需要決定是否啟用：

```bash
STOCK_INDEX_REMOTE_UPDATE_ENABLED=true
```

預設開啟時，系統最多每 48 小時檢查一次更新。若執行環境無法訪問 GitHub raw、請求超時、返回內容不是合法股票索引，應用會保留已有快取；如果沒有遠端快取，則繼續使用隨應用打包的內建索引。遠端更新失敗不會阻斷 WebUI 啟動、股票自動補全或分析流程；連續失敗達到系統內建閾值後，會在本程序內暫停重試直到下一輪 48 小時視窗。

## 注意事項

1. **積分要求**：確保賬號積分足夠（A股/港股2000，美股120試用）
2. **請求限制**：注意 API 的每分鐘請求次數限制
3. **資料更新**：維護者建議每三天重新整理一次並提交到倉庫；本地客戶端預設最多每 48 小時檢查一次 GitHub `main` 上的索引更新。後續可透過 GitHub Actions workflow 自動化重新整理與提交 PR
4. **網路連線**：需要穩定的網路連線

## 常見問題

### Q: 提示"未找到 TUSHARE_TOKEN"？
**A**: 請在 `.env` 檔案中配置 `TUSHARE_TOKEN=你的token`

### Q: 提示"賬號積分不足"？
**A**:
- A股/港股需要2000積分
- 美股120積分試用，5000積分正式許可權
- 訪問 https://tushare.pro 檢視積分獲取辦法

### Q: 讀取失敗怎麼辦？
**A**:
1. 檢查網路連線
2. 檢查 Token 是否正確
3. 檢視賬號積分是否足夠
4. 當前指令碼不會自動重試；單次請求失敗後會輸出錯誤並結束，請排查原因後重新執行

### Q: 資料更新頻率？
**A**: 對維護者本地 CSV 與倉庫索引，建議每三天更新一次並提交到倉庫；遇到摘帽/更名等高影響事件可臨時重新整理。未來可透過 GitHub Actions workflow 自動化重新整理與提交 PR。對普通本地客戶端，系統預設最多每 48 小時從 GitHub `main` 檢查一次最新索引。

### Q: 無法訪問 GitHub raw 會影響使用嗎？
**A**: 不會。遠端索引更新是 best-effort：失敗時會繼續使用已有遠端快取或隨應用打包的內建索引；如果索引完全不可用，Web 自動補全會進入現有 fallback，股票程式碼仍可手動輸入。

## 相關連結

- [Tushare 官網](https://tushare.pro)
- [Tushare 文件](https://tushare.pro/document/2)
- [積分獲取辦法](https://tushare.pro/document/1)
- [API 資料除錯](https://tushare.pro/document/2)

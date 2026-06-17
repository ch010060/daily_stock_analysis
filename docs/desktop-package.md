# 桌面端打包說明 (Electron + React UI)

本專案可打包為桌面應用，使用 Electron 作為桌面殼，`apps/dsa-web` 的 React UI 作為介面。

## 架構說明

- React UI（Vite 構建）由本地 FastAPI 服務託管
- Electron 啟動時自動拉起後端服務，等待 `/api/health` 就緒後載入 UI
- Windows 便攜/安裝模式下，使用者配置檔案 `.env` 和資料庫放在 exe 同級目錄；macOS 打包版使用 Electron 使用者資料目錄儲存執行時配置

## 本地開發

一鍵啟動（開發模式）：

```bash
powershell -ExecutionPolicy Bypass -File scripts\run-desktop.ps1
```

或手動執行：

1) 構建 React UI（輸出到 `static/`）

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 啟動 Electron 應用（自動拉起後端）

```bash
cd apps/dsa-desktop
npm install
npm run dev
```

首次執行時會自動從 `.env.example` 複製生成 `.env`。

## 打包 (Windows)

### 前置條件

- Node.js 18+
- Python 3.10+
- 開啟 Windows 開發者模式（electron-builder 需要建立符號連結）
  - 設定 -> 隱私和安全性 -> 開發者選項 -> 開發者模式

### 一鍵打包

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-all.ps1
```

該指令碼會依次執行：
1. 構建 React UI
2. 安裝 Python 依賴
3. PyInstaller 打包後端
4. electron-builder 打包桌面應用

當前 Windows 安裝包使用 NSIS 嚮導式安裝流程，僅支援當前使用者安裝且已禁用管理員提權，安裝時可手動選擇目標目錄（例如非 C 盤）。安裝器透過 NSIS `.onVerifyInstDir` 回撥在安裝器層面阻止選擇 `Program Files`、`Windows` 等系統保護目錄——選擇這些路徑時"下一步"按鈕會被自動禁用。安裝完成後，桌面端仍會按現有邏輯在安裝目錄旁生成/讀取 `.env`、`data/stock_analysis.db`（含 `data/stock_analysis.db-wal` / `data/stock_analysis.db-shm`）和 `logs/desktop.log`。推薦使用預設的 per-user 安裝目錄。如果不想安裝，仍可繼續分發 `win-unpacked` 免安裝包。

## GitHub CI 自動打包併發布 Release

倉庫已支援透過 GitHub Actions 自動構建桌面端並上傳到 GitHub Releases：

- 工作流：`.github/workflows/desktop-release.yml`
- 觸發方式：
  - 推送語義化 tag（如 `v3.2.12`）後自動觸發
  - 在 Actions 頁面手動觸發並指定 `release_tag`
- 產物：
  - Windows 安裝包：Release 附件和本地 `apps/dsa-desktop/dist/` 中統一為 `daily-stock-analysis-windows-installer-<tag>.exe`
  - Windows 自動更新後設資料：Release 附件會額外保留 `latest.yml` 和 `*.blockmap`，供安裝版桌面端後臺下載與校驗更新；普通使用者無需手動下載這些後設資料。下載完成後使用者確認“重啟安裝”時，桌面端會先停止內建後端、備份執行時檔案，並以靜默模式執行安裝器。
  - Windows 免安裝包：`daily-stock-analysis-windows-noinstall-<tag>.zip`
  - macOS Intel：`daily-stock-analysis-macos-x64-<tag>.dmg`
  - macOS Apple Silicon：`daily-stock-analysis-macos-arm64-<tag>.dmg`

建議釋出流程：

1. 合併程式碼到 `main`
2. 由自動打 tag 工作流生成版本（或手動建立 tag）
3. `desktop-release` 工作流自動構建並把兩個平臺安裝包附加到對應 GitHub Release

## 發版前可復現驗證（桌面更新鏈路）

桌面端自動更新鏈路依賴 Windows NSIS 安裝產物、`latest.yml` 與 `*.blockmap` 後設資料。當前桌面 CI 不覆蓋 `desktop-release` 打包產物可釋出鏈路，提交前建議補充如下本地驗證：

說明：該清單專注於 Windows NSIS 安裝版與 `electron-updater` 釋出後設資料。當前 Linux 環境無法直接產出 Windows 安裝包和 updater 後設資料（`latest.yml` / `*.blockmap`），此類鏈路需在 Windows 釋出執行器或 Windows 本機環境複核。

若在非 Windows 環境無法完成上述驗證，請在 PR 驗收說明中明確補齊 Windows 釋出鏈路複核人、複核時間窗及 `desktop-release` 產物檢查結果（release/tag 與 `daily-stock-analysis-windows-installer-<tag>.exe`、`latest.yml`、`*.blockmap` 版本一致性與可下載性）。

1. 先構建 Web 靜態產物（桌面端主視窗與設定頁入口依賴）

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

2. 回到桌面端，補齊依賴、執行 preload 單測、再執行 Electron 打包

```bash
cd ../dsa-desktop
npm ci
npm test
npm run build
```

在 Windows 釋出複核環境，還可額外執行：

```powershell
./scripts/verify-desktop-updater-artifacts.ps1 -ReleaseTag v$(node -p "require('./apps/dsa-desktop/package.json').version")
```

> 預期當前執行環境不支援生成 Windows NSIS 安裝器時，請在交付說明中明確註明平臺限制，並要求指定的 Windows 釋出鏈路複核人補齊該項驗證。

3. 檢查更新後設資料是否產出

```bash
ls -1 dist | sort
ls -1 dist/*.yml dist/*.blockmap 2>/dev/null || true
```

4. 強制對齊版本與釋出附件（可在 Windows 環境或能產出 NSIS 產物的執行器上覆核）

```bash
RELEASE_TAG="v$(node -p \"require('./package.json').version\")"
REPO="ZhuLinsen/daily_stock_analysis"

for f in dist/*latest.yml dist/*.blockmap dist/daily-stock-analysis-windows-installer-*.exe; do
  [ -f \"$f\" ] && echo \"[FOUND] $f\"
done

if [ -f dist/latest.yml ]; then
  echo \"---- latest.yml 版本片段 ----\"
  grep -E \"^version:|^files:|^sha512:\" dist/latest.yml
fi

echo \"---- Release 清單（人工核對）----\"
echo \"Release Tag: $RELEASE_TAG\"
echo \"Release 地址: https://github.com/$REPO/releases/tag/$RELEASE_TAG\"
echo \"應核對附件是否包含:\"
echo \"- daily-stock-analysis-windows-installer-*.exe\"
echo \"- latest.yml\"
echo \"- *.blockmap\"
echo \"並確保 latest.yml 中 version 與 tag 的語義化版本一致，path/url 與安裝包附件名一致\"
```

5a. 建議在 PR 描述裡記錄的“可複核輸出”（Windows）：

```bash
echo "release-tag=${RELEASE_TAG}"
echo "latest.yml version:"
grep -E "^version:" dist/latest.yml
echo "latest.yml files:"
sed -n '1,80p' dist/latest.yml
echo "packaging artifacts:"
ls -1 dist/*.yml dist/*.blockmap dist/*installer*.exe 2>/dev/null | sort
```

Windows 釋出鏈路複核清單（在 PR 後由釋出團隊/維護者執行）：

- release/tag 與 `daily-stock-analysis-windows-installer-<tag>.exe` 的版本號一致；
- `latest.yml`、`daily-stock-analysis-windows-installer-<tag>.exe`、`*.blockmap` 同 tag 同步出現且可下載；
- `latest.yml` 中 `version` 與 Release tag 語義一致（去掉 `v` 字首後比對），且 `path` / `files.url` 與安裝包附件名一致；
- 如缺少上述檔案或 `release-tag` 不匹配，需標註阻斷並補齊 `desktop-release` 打包流程。

5. Windows/NSIS 產物與釋出附件一致性請在 Windows 環境手動驗證（可人工觸發釋出流程），並在升級後核對執行時檔案留存：

   1. 安裝前後分別記錄安裝目錄中的 `.env`、`data/stock_analysis.db`、`data/stock_analysis.db-wal`、`data/stock_analysis.db-shm`、`logs/desktop.log` 的 SHA256；
   2. 確認桌面端下一次啟動後，上述檔案仍存在且與安裝前記錄一致；
   3. 如不一致，可在應用退出後檢查使用者資料目錄中的 `.dsa-desktop-update-backup` 是否清理完整，並結合最新日誌串聯排查。

Windows 平臺建議使用 PowerShell 執行：

```bash
Get-FileHash .env,data\\stock_analysis.db,data\\stock_analysis.db-wal,data\\stock_analysis.db-shm,logs\\desktop.log -Algorithm SHA256
```

說明：應用已在 Windows NSIS 安裝版的“重啟安裝”前停止內建後端、備份安裝目錄旁上述執行時檔案，並以靜默模式執行更新安裝器，目的是避免安裝嚮導搶先覆蓋仍在執行的桌面端程序，同時降低更新過程中檔案丟失風險；若恢復失敗，桌面端會顯示更新安裝錯誤並保留手動下載路徑供回退處理。此次修復僅改動 Windows 更新安裝鏈路與內建後端程序生命週期處理，不涉及設定儲存語義、模型執行時清理策略或配置遷移行為。

### 分步打包

1) 構建 React UI

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 打包 Python 後端

```bash
pip install pyinstaller
pip install -r requirements.txt
python -m PyInstaller --name stock_analysis --onefile --noconsole --add-data "static;static" --hidden-import=multipart --hidden-import=multipart.multipart main.py
```

將生成的 exe 複製到 `dist/backend/`：

```bash
mkdir dist\backend
copy dist\stock_analysis.exe dist\backend\stock_analysis.exe
```

3) 打包 Electron 桌面應用

```bash
cd apps/dsa-desktop
npm install
npm run build
```

打包產物位於 `apps/dsa-desktop/dist/`。Windows 安裝器會生成 `daily-stock-analysis-windows-installer-<tag>.exe`，安裝嚮導中可選擇安裝目錄。

## 目錄結構

Windows 安裝包模式下，安裝器僅支援當前使用者安裝且已禁用管理員提權，使用者可在安裝嚮導中選擇安裝目錄；安裝器會在安裝器層面阻止選擇 `Program Files`、`Windows` 等系統保護目錄（選擇時"下一步"按鈕自動禁用），安裝完成後，應用會在安裝目錄旁生成/讀取 `.env`、`data/stock_analysis.db`（含 `data/stock_analysis.db-wal` / `data/stock_analysis.db-shm`）和 `logs/desktop.log`。請保留預設的 per-user 安裝位置或選擇其他使用者可寫目錄。

`win-unpacked` 免安裝模式下，目錄結構如下：

```
win-unpacked/
  Daily Stock Analysis.exe    <- 雙擊啟動
  .env                        <- 使用者配置檔案（首次啟動自動生成）
  data/
    stock_analysis.db         <- 資料庫主檔案
    stock_analysis.db-wal     <- WAL 日誌檔案（更新備份/恢復）
    stock_analysis.db-shm     <- WAL 共享元檔案（更新備份/恢復）
  logs/
    desktop.log               <- 執行日誌
  resources/
    .env.example              <- 配置模板
    backend/
      stock_analysis.exe      <- 後端服務
```

## 配置檔案說明

- Windows 桌面端的 `.env` 放在 exe 同目錄下
- macOS 打包版的 `.env`、`data/` 和 `logs/` 放在 Electron 使用者資料目錄，避免替換 `.app` 時丟失
- 首次啟動時自動從 `.env.example` 複製生成
- 從舊版本升級時，如果舊 `.app` 包內部的 `.env`、`data/stock_analysis.db` 或日誌檔案仍可訪問，新版本會在目標檔案不存在時自動遷移到使用者資料目錄；已有目標檔案不會被覆蓋
- 使用者需要編輯 `.env` 配置以下內容：
  - `GEMINI_API_KEY` 或 `OPENAI_API_KEY`：AI 分析必需
  - `STOCK_LIST`：自選股列表（逗號分隔）
  - 其他可選配置參考 `.env.example`

### 配置備份 / 恢復 `.env`

- WebUI 與桌面端都可以從 `系統設定 -> 配置備份` 看到 `匯出 .env` 和 `匯入 .env` 按鈕
- WebUI 非桌面執行時需要先開啟管理員認證並完成登入；未開啟認證時按鈕會禁用，API 返回 `403`
- `匯出 .env` 會匯出當前**已儲存**的 `.env` 備份檔案；頁面上尚未點選“儲存配置”的本地草稿不會被匯出
- `匯入 .env` 會讀取備份檔案中的鍵值併合併到當前配置中，匯入後會立即觸發配置過載
- 匯入是“鍵級覆蓋”而不是整檔案替換：備份檔案中出現的鍵會覆蓋當前值，未出現的鍵保持不變
- 如果當前頁面還有未儲存草稿，匯入前會先提示確認，避免把本地草稿和已儲存配置混在一起
- Web 端預設 `ADMIN_AUTH_ENABLED=false` 時，設定頁會展示按鈕為禁用態並提示先啟用管理員鑑權；桌面端不受該配置影響，仍可直接使用配置備份/恢復能力。

> 建議：從舊版本升級的 macOS 使用者仍可在升級前執行一次 `匯出 .env` 作為保險；如果舊 `.app` 已經被整體替換，包內舊檔案無法憑空恢復，只能透過備份匯入。

### 設定頁版本資訊

- `系統設定 -> 版本資訊` 中的“桌面端版本”由 Electron 主程序的 `app.getVersion()` 提供，並透過 preload bridge 暴露給前端
- 開發態 `npm run dev` 與打包態 `npm run build` / 安裝包都會複用同一條版本注入鏈路，不再在 `preload.js` 裡維護獨立硬編碼版本號
- `README.md` 繼續保留安裝和執行入口說明；這類桌面端執行時細節統一落在本專題文件維護，避免入門文件膨脹

### 桌面端更新提醒

- 應用在主介面載入完成後會後臺檢查 GitHub Releases 的最新正式版，並與當前 `app.getVersion()` 做語義化版本比較
- Windows NSIS 安裝版會透過內建 GitHub 更新源自動下載新版本；下載完成後彈出一次性提醒，使用者確認後靜默重啟並安裝
- 自動更新靜默安裝會複用當前安裝目錄；如果使用者安裝時選擇了非預設目錄或帶空格目錄，後續自動更新仍會覆蓋同一目錄
- `系統設定 -> 版本資訊` 中的“桌面端更新”區域可手動檢查更新；若更新已下載，會展示“重啟安裝”操作
- Windows 免安裝包、開發態和 macOS DMG 仍保持“提醒 + 跳轉下載頁”的相容路徑，不會因為網路失敗而阻斷桌面端啟動
- 版本檢查失敗、GitHub API 超時、更新後設資料缺失或下載安裝異常時，會記錄到 `logs/desktop.log`，設定頁手動檢查時會展示錯誤狀態

## 常見問題

### 啟動後一直顯示 "Preparing backend..."

1. 檢查 `logs/desktop.log` 檢視錯誤資訊
2. 確認 `.env` 檔案存在且配置正確
3. 確認埠 8000-8100 未被佔用

### 後端啟動報 ModuleNotFoundError

PyInstaller 打包時缺少模組，需要在 `scripts/build-backend.ps1` 中增加 `--hidden-import`。

### UI 載入空白

確認 `static/index.html` 存在，如不存在需重新構建 React UI。

### macOS 升級後配置遷移

舊版本曾把執行時 `.env`、資料庫和日誌寫在 `.app` 包內部。新版本改為使用 Electron 使用者資料目錄，並在舊 `.app` 包內檔案仍可訪問時做一次性遷移。遷移規則是“目標不存在才複製”，避免覆蓋使用者已經在新版本中儲存的配置。

如果舊 `.app` 已經被整體替換，舊包內 `.env` 無法由新版本自動恢復。此時可使用升級前匯出的 `.env` 在 `系統設定 -> 配置備份` 中手動匯入；完成一次遷移或重新配置後，後續版本會繼續複用使用者資料目錄，不再隨 `.app` 替換丟失。

## 分發給使用者

Windows 分發現在有兩種方式：

1. 安裝包：分發 `apps/dsa-desktop/dist/` 下的 `daily-stock-analysis-windows-installer-<tag>.exe`，使用者安裝時可自行選擇目標目錄
2. 免安裝包：將 `apps/dsa-desktop/dist/win-unpacked/` 整個資料夾打包發給使用者

使用 `win-unpacked` 免安裝包時，使用者只需：

1. 解壓資料夾
2. 編輯 `.env` 配置 API Key 和股票列表
3. 雙擊 `Daily Stock Analysis.exe` 啟動

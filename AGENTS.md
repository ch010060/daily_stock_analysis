# AGENTS.md

本檔案用於約束本倉庫的預設開發流程，目標是減少重複溝通、減少返工，並讓改動和當前專案結構保持一致。

如果本檔案與倉庫中的指令碼、工作流、程式碼現狀不一致，以實際可執行內容為準，並在相關改動中順手修正檔案，避免規則繼續漂移。

## 1. 硬規則

- 遵循現有目錄邊界：
  - 後端邏輯優先放在 `src/`、`data_provider/`、`api/`、`bot/`
  - Web 前端改動在 `apps/dsa-web/`
  - 桌面端改動在 `apps/dsa-desktop/`
  - 部署與流水線改動在 `scripts/`、`.github/workflows/`、`docker/`
- 未經明確確認，不執行 `git commit`、`git tag`、`git push`。
- commit message 使用英文，不新增 `Co-Authored-By`。
- 不寫死金鑰、賬號、路徑、模型名、埠或環境差異邏輯。
- 優先複用現有模組、配置入口、指令碼和測試，不新增平行實現。
- 預設穩定性優先於“順手最佳化”；非當前任務直接需要的重構、抽象和基礎設施遷移一律剋制。
- 新增配置項時，必須同步更新 `.env.example` 和相關檔案。
- 涉及使用者可見能力、CLI/API 行為、部署方式、通知方式、報告結構變化時，必須同步更新相關檔案與 `docs/CHANGELOG.md`。
- `docs/CHANGELOG.md` 的 `[Unreleased]` 段使用**扁平格式**：每條獨立一行，格式為 `- [型別] 描述`，型別取值：`新功能`/`改進`/`修復`/`檔案`/`測試`/`chore`；**禁止在 `[Unreleased]` 內新增 `### 類目標題`**，以減少併發 PR 的 merge 衝突。發版時由 maintainer 彙總整理成帶標題的正式格式。
- `README.md` 只用於專案定位、核心能力總覽、快速開始、主要入口、贊助/合作等首頁級資訊；非必要不更新 README，避免持續膨脹。
- 更細的模組行為、頁面互動、專題配置、排障說明、欄位契約、實現語義和邊界條件，優先更新對應 `docs/*.md` 或專題檔案，不寫入 README。
- 變更中英雙語檔案之一時，需評估另一份是否需要同步；若未同步，交付說明裡要寫明原因。
- 註釋、docstring、日誌文案以清晰準確為準，不強制要求英文，但應與檔案語境保持一致。

## 1.1 PR 標題規範（非阻斷建議）

- 推薦使用 `<型別>: <修改內容>` 作為 PR 標題，例如 `fix: 修復大盤分析歷史記錄丟失`，優先型別為 `fix`/`feat`/`refactor`/`docs`/`chore`/`test`/`ci`。
- 標題應描述實際變更內容，建議不新增 `[codex]`、`codex`、`autocode`、`copilot` 或其他工具/agent 來源字首。
- 該規範僅用於協作可讀性與一致性提示，不應單獨作為 review process blocker。

## 2. AI 協作資產治理

- `AGENTS.md` 是倉庫內 AI 協作規則的唯一真源。
- `CLAUDE.md` 必須是指向 `AGENTS.md` 的軟連結，用於相容 Claude 生態。
- `.github/copilot-instructions.md` 與 `.github/instructions/*.instructions.md` 是 GitHub Copilot / Coding Agent 的映象或分層補充；若與本檔案衝突，以 `AGENTS.md` 為準。
- 倉庫協作 skill 存放在 `.claude/skills/`，分析產物存放在 `.claude/reviews/`；前者可以入庫，後者預設視為本地產物。
- 根目錄 `SKILL.md` 與 `docs/openclaw-skill-integration.md` 屬於產品或外部整合說明，不是倉庫協作規則真源。
- 若未來新增 `.agents/skills/` 或其他 agent 專用目錄，必須先明確單一真源，再透過指令碼或映象同步；禁止手工長期維護多份同義內容。
- 修改 AI 協作治理資產時，執行：

```bash
python scripts/check_ai_assets.py
```

## 3. 倉庫速覽

- 專案定位：股票智慧分析系統，覆蓋 A 股、港股、美股。
- 主流程：抓取資料 -> 技術分析/新聞檢索 -> LLM 分析 -> 生成報告 -> 通知推送。
- 關鍵入口：
  - `main.py`：分析任務主入口
  - `server.py`：FastAPI 服務入口
  - `apps/dsa-web/`：Web 前端
  - `apps/dsa-desktop/`：Electron 桌面端
  - `.github/workflows/`：CI、釋出、每日任務
- 核心職責：
  - `src/core/`：主流程編排
  - `src/services/`：業務服務層
  - `src/repositories/`：資料訪問層
  - `src/reports/`：報告生成
  - `src/schemas/`：Schema / 資料結構
  - `data_provider/`：多資料來源適配與 fallback
  - `api/`：FastAPI API
  - `bot/`：機器人接入
  - `scripts/`：本地指令碼
  - `.github/scripts/`：GitHub 自動化指令碼
  - `tests/`：pytest 測試
  - `docs/`：檔案與說明

## 4. 常用命令

### 執行應用

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### 後端驗證

```bash
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh
python -m pytest -m "not network"
python -m py_compile <changed_python_files>
```

### Web / Desktop

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build

cd ../dsa-desktop
npm install
npm run build
```

### PR / CI 證據

```bash
gh pr view <pr_number>
gh pr checks <pr_number>
gh run view <run_id> --log-failed
```

## 5. 預設工作流

1. 先判斷任務型別：`fix / feat / refactor / docs / chore / test / review`
2. 先讀現有實現、配置、測試、指令碼、工作流和檔案，再動手修改。
3. 識別改動邊界：後端 / API / Web / Desktop / Workflow / Docs / AI 協作資產。
4. 先判斷是否命中高風險區域：配置語義、API / Schema、資料來源 fallback、報告結構、認證、排程、釋出流程、桌面端啟動鏈路。
5. 只做和當前任務直接相關的最小改動，不順手夾帶無關重構。
6. 如果發現檔案、指令碼、工作流描述不一致，優先信任實際程式碼與工作流，再決定是否順手修正檔案。
7. 改完後按下面的驗證矩陣執行檢查。
8. 最終交付預設要說明：
   - 改了什麼
   - 為什麼這麼改
   - 驗證情況
   - 未驗證項
   - 風險點
   - 回滾方式

## 6. 驗證矩陣

### CI 覆蓋原則

當前倉庫 CI 主要包含：

| 檢查項 | 來源 | 說明 | 是否阻斷 |
| --- | --- | --- | --- |
| `ai-governance` | `.github/workflows/ci.yml` | 校驗 `AGENTS.md` / `CLAUDE.md` / `.github` 指令 / `.claude/skills` 關係 | 是 |
| `backend-gate` | `.github/workflows/ci.yml` | 執行 `./scripts/ci_gate.sh` | 是 |
| `docker-build` | `.github/workflows/ci.yml` | Docker 構建與關鍵模組匯入 smoke | 是 |
| `web-gate` | `.github/workflows/ci.yml` | 前端改動時執行 `npm run lint` + `npm run build` | 是（觸發時） |
| `network-smoke` | `.github/workflows/network-smoke.yml` | `pytest -m network` + `scripts/test.sh quick` | 否，觀測項 |
| `pr-review` | `.github/workflows/pr-review.yml` | PR 靜態檢查 + AI 審查 + 自動標籤 | 否，輔助項 |

若 PR 上已有對應 CI 結果，可直接引用 CI 結論；若 CI 未覆蓋改動面，或本地與 CI 環境差異較大，需要補充說明本地驗證與缺口。

### 按改動面執行

- Python 後端改動：
  - 適用範圍：`main.py`、`src/`、`data_provider/`、`api/`、`bot/`、`tests/`
  - 優先執行：`./scripts/ci_gate.sh`
  - 最低要求：`python -m py_compile <changed_python_files>`
  - 若影響 API、任務編排、報告生成、通知傳送、資料來源 fallback、認證、排程，交付說明中要寫明是否覆蓋了對應路徑。

- Web 前端改動：
  - 適用範圍：`apps/dsa-web/`
  - 預設執行：`cd apps/dsa-web && npm ci && npm run lint && npm run build`
  - 若涉及 API 聯調、路由、狀態管理、Markdown/圖表渲染或認證狀態，交付說明中要明確說明聯動面和未覆蓋風險。

- 桌面端改動：
  - 適用範圍：`apps/dsa-desktop/`、`scripts/run-desktop.ps1`、`scripts/build-desktop*.ps1`、`scripts/build-*.sh`、`docs/desktop-package.md`
  - 預設執行：先構建 Web，再構建桌面端
  - 如受平臺限制未能完整驗證，需要明確說明是否驗證了 Web 構建產物、Electron 構建以及 Release 工作流影響。

- API / Schema / 認證聯動改動：
  - 適用範圍：`api/**`、`src/schemas/**`、`src/services/**`、`apps/dsa-web/**`、`apps/dsa-desktop/**`
  - 至少覆蓋對應後端驗證 + 受影響客戶端構建驗證。
  - 若涉及登入、Cookie、會話、輪詢狀態、欄位增刪或列舉變化，必須明確寫出相容性影響。

- 檔案與治理檔案改動：
  - 適用範圍：`README.md`、`docs/**`、`AGENTS.md`、`.github/copilot-instructions.md`、`.github/instructions/**`、`.claude/skills/**`
  - 不強製程式碼測試。
  - 需確認命令、配置項、檔名、工作流名稱與實際倉庫一致。
  - 改動 AI 協作治理資產時，執行 `python scripts/check_ai_assets.py`。

- 工作流 / 指令碼 / Docker 改動：
  - 適用範圍：`.github/**`、`scripts/**`、`docker/**`
  - 執行最接近改動面的本地驗證。
  - 交付時說明影響了哪條流水線、釋出路徑或部署路徑。
  - 若未執行 Docker / GitHub Actions 相關驗證，明確說明原因與潛在風險。

- 網路或三方依賴相關改動：
  - 先跑離線或確定性檢查。
  - 優先確認 timeout、retry、fallback、異常文案、降級路徑是否仍然成立。
  - 若未執行線上驗證，必須明確寫出原因。

## 7. 穩定性護欄

- 配置與執行入口：
  - 修改 `.env` 語義、預設值、CLI 引數、服務啟動方式、排程語義時，要同時評估本地執行、Docker、GitHub Actions、API、Web、Desktop 的影響。
  - 新配置優先做到“不配置也可執行，配置後增強能力”，避免疊加開關和互斥模式。

- 資料來源與 fallback：
  - 修改 `data_provider/` 時，要關注資料來源優先順序、失敗降級、欄位標準化、快取與超時策略。
  - 單一資料來源失敗不應拖垮整個分析流程，除非需求明確要求 fail-fast。

- API / Web / Desktop 相容：
  - 改 API / Schema / 認證 / 報告載荷時，要同時檢查後端、Web、Desktop 的相容性。
  - 預設優先追加欄位、保留舊欄位或提供相容層，避免無提示破壞現有客戶端。

- 報告 / Prompt / 通知：
  - 修改報告結構、Prompt、提取器、通知模板、機器人鏈路時，要檢查上游輸入與下游消費方是否仍相容。
  - 單一通知通道失敗不應拖垮整個分析主流程，除非需求明確要求 fail-fast。
  - 修改 `src/services/image_stock_extractor.py` 中 `EXTRACT_PROMPT` 時，要在 PR 描述中附完整最新 prompt。

- 工作流 / 釋出 / 打包：
  - 修改自動 tag、Release、Docker 釋出、日常分析或桌面端打包流程時，要評估觸發條件、產物路徑、許可權邊界和回滾方式。
  - 自動 tag 預設保持 opt-in：只有 commit title 含 `#patch`、`#minor`、`#major` 才觸發版本號更新，除非需求明確要求改變釋出策略。

## 8. Issue / PR / Skill 工作流

- 倉庫內已有以下 skill，可優先複用：
  - `.claude/skills/analyze-issue/SKILL.md`
  - `.claude/skills/analyze-pr/SKILL.md`
  - `.claude/skills/fix-issue/SKILL.md`
- 如果任務明確是 issue 分析、PR 審查、issue 修復，優先按對應 skill 執行，並將產物儲存到 `.claude/reviews/`。
- skill 中的命令、模板、驗證順序和交付結構必須與 `AGENTS.md` 保持一致。
- skill 預設優先讀取 CI / 工作流證據，再決定是否補本地驗證。
- skill 不得預設執行 `git pull`、`git push`、`git tag`、`gh pr create` 等會改變遠端或當前分支狀態的操作；這些操作必須要求使用者確認。
- PR 審查預設順序：
  1. 必要性
  2. 關聯性
  3. 標題建議（`<型別>: <修改內容>`，且不含工具/agent 字首；不作為硬性阻斷項）
  4. 描述完整性（對照 `.github/PULL_REQUEST_TEMPLATE.md`）
  5. 驗證證據
  6. 實現正確性
  7. 合入判定
- 對 `fix` 類 PR，必須說明：原問題、根因、修復點、迴歸風險。
- 合入阻斷條件：
  - 正確性或安全性問題
  - 阻斷型 CI 未透過
  - PR 描述與實際改動內容實質性矛盾
  - 缺少回滾方案

## 9. 交付與釋出

- 預設交付結構：
  - `改了什麼`
  - `為什麼這麼改`
  - `驗證情況`
  - `未驗證項`
  - `風險點`
  - `回滾方式`
- 如果是 `docs` 任務，可直接寫：`Docs only, tests not run`，但仍需說明是否核對了命令和檔名。
- 自動 tag 預設不觸發，只有 commit title 包含 `#patch`、`#minor`、`#major` 才會觸發版本號更新。
- 手動打 tag 必須使用 annotated tag。
- 使用者可見變更優先透過 PR 合入，並補齊 label 與驗證說明。

# AnalysisContextPack：P0 盤點、P1/P2 契約、P3 Runtime Consumption、P4 可見性與 P5 資料質量

本頁是 Issue #1389 的專題文件，用於記錄當前 DSA 分析上下文的真實來源、消費路徑、欄位狀態邊界，以及 `AnalysisContextPack` 內部契約、builder、執行態消費、低敏可見性和資料質量評分邊界。P0 負責現狀盤點和契約邊界；P1 只新增內部 schema/envelope、block catalog、型別約定和脫敏序列化；P2 只從 pipeline 已有 artifacts 組裝 pack；P3 只把低敏摘要接入普通分析和 Agent 初始 Prompt；P4 只把低敏 overview 接入歷史詳情、同步分析響應、completed task status 和 Web 報告頁；P5 在同一 `PACK_VERSION = "1.0"` 內補齊資料質量評分、`fetch_failed` 狀態、Prompt 資料限制和 overview 低敏展示。

## 術語與邊界

當前倉庫裡有多種名為 context / snapshot 的資料面，P0 必須先消歧，避免把現有執行時結構誤寫成未來 pack。

| 術語 | 當前含義 | 當前主要消費方 | P0 邊界 |
| --- | --- | --- | --- |
| `storage.get_analysis_context()` | `src/storage.py` 中從資料庫最近兩天 OHLCV 生成的技術面簡上下文，包含 `today`、`yesterday`、`volume_change_ratio`、`price_change_ratio`、`ma_status` 等。當前實現接收 `target_date`，但實際仍取最新兩天資料。 | 普通分析主鏈路、Agent 工具 `get_analysis_context` | 記錄為歷史技術面輸入來源，不把它直接等同於未來 pack。 |
| `enhanced_context` | 普通分析中由 `src/core/pipeline.py` 基於 DB 簡上下文、實時行情、籌碼、趨勢、基本面和語言資訊增強後的 prompt 上下文。 | `src/analyzer.py` prompt 渲染、`_build_context_snapshot()` | 記錄當前 prompt 輸入面；P0 不改變欄位名或結構。 |
| `analysis_history.context_snapshot` | 分析完成後寫入歷史表的持久化快照。普通分析通常包含 `enhanced_context`、`news_content`、`realtime_quote_raw`、`chip_distribution_raw`；Agent 路徑儲存 `initial_context`。 | 歷史詳情、同步 analysis/status 響應、回測、部分基本面 fallback 展示 | 記錄為持久化消費面；必須保留 `context_snapshot.enhanced_context.date` 相容。 |
| Agent executor message context | `AgentExecutor._build_user_message()` 注入首輪使用者訊息的上下文，適用於 `AGENT_ARCH=single` 路徑，目前包含股票程式碼、報告型別、輸出語言、`realtime_quote`、`chip_distribution`、`news_context`。 | 單 Agent 首輪 LLM 訊息 | 記錄當前首輪可見欄位；P0 不補 runtime 注入。 |
| Agent orchestrator `AgentContext` | `AgentOrchestrator._build_context()` 寫入多 Agent 共享上下文，適用於 `AGENT_ARCH=multi` 路徑，可預注入 `realtime_quote`、`daily_history`、`chip_distribution`、`trend_result`、`news_context`。 | Technical / Intel / Risk / Decision 多 Agent 鏈路 | 記錄為 orchestrator 內部共享資料面；不預注入 `fundamental_context`，`trend_result` 是否存在取決於 caller 是否傳入。 |

## P0 範圍與非目標

P0 的目標是讓後續 P1/P2/P3 可以基於真實倉庫邊界設計 `AnalysisContextPack`，而不是提前改造執行時。

- P0 覆蓋普通分析、Agent、警告、持股、回測、歷史、通知七條路徑的上下文盤點。
- P0 固定欄位質量狀態詞；P1 已新增 `AnalysisContextPack` 內部 schema，但仍不新增 builder、不接入 runtime、不公開完整 pack。
- P0 不新增 builder，不新增配置項，不新增資料庫欄位，不改變 API、報告、歷史或通知 payload。
- P0 不接入 runtime，不改 `src/` 分析、Agent、警告、持股、回測或通知邏輯。
- P0 不 pack 化 `market_review`、`market_light` 或大盤紅綠燈專題快照；這些只作為歷史快照中的其他 `report_kind` / 專題消費邊界記錄。
- P0 當時不把 `fetch_failed` 加入欄位質量狀態詞；P5 已在同一 1.0 umbrella 內追加該狀態，用於明確區分“不支援”和“本次抓取失敗”。
- P0 不在 README 擴寫實現細節；本頁作為專題文件，由 `docs/INDEX.md` / `docs/INDEX_EN.md` 入口發現。

## P1 內部契約

P1 落地 `src/schemas/analysis_context_pack.py`，只定義內部 schema/envelope，方便 P2 builder 和 P3 runtime 消費時複用同一結構。P1 不填充執行時資料、不新增 fetcher、不改變 Prompt、不寫入 history/task/report metadata，也不把完整 pack 暴露到 API、Web、Bot、Desktop 或通知。

P1 schema 包含：

- `PACK_VERSION = "1.0"`，並透過 `AnalysisContextPack.pack_version` 標記契約版本。
- `ContextFieldStatus`：P1 首版只允許 `available`、`missing`、`not_supported`、`fallback`、`stale`、`estimated`、`partial`；P5 已追加 `fetch_failed`，表示欄位或資料塊本次抓取明確失敗，不代表整次分析失敗。
- `AnalysisSubject`：頂層身份槽，只包含 `code`、`stock_name`、`market`；`exchange`、`currency`、`industry` 留給後續擴充套件，P2 builder 不擴 P1 schema，也不重複新增 `identity` block。
- `AnalysisContextItem`：欄位級輸入項，包含 `status`、`value`、`source`、`timestamp`、`fallback_from`、`missing_reason`、`warnings`、`metadata`。
- `AnalysisContextBlock`：資料塊級分組，包含 `status`、`items`、`source`、`timestamp`、`warnings`、`metadata`，其中 `items` 是 `Dict[str, AnalysisContextItem]`。
- `DataQuality`：P1 只保留 `warnings` 與 `metadata` 容器；P5 已追加 `overall_score`、`level`、`block_scores`、`limitations`，仍保持低敏，不承載 raw payload。
- `AnalysisContextPack`：頂層 envelope，包含 `pack_version`、`subject`、`phase`、`blocks`、`data_quality`、`metadata`、`created_at`。

時間欄位約定：

- `AnalysisContextPack.created_at` 使用 `datetime`，由 `model_dump(mode="json")` 輸出 ISO 8601 字串。
- `AnalysisContextItem.timestamp` 與 `AnalysisContextBlock.timestamp` 使用 `Optional[str]`，約定為 ISO 8601 datetime 字串；P1 schema 在構造時校驗該格式，date-only、自然語言時間或斜槓分隔日期會被拒絕；P2 builder 複用現有 artifact 時間戳時不做強制二次轉換。

狀態語義：

- `block.status` 表示整塊可用性。
- `item.status` 表示欄位級質量。
- P1 不實現 `item.status` 到 `block.status` 的自動聚合推導。

P1 Block Catalog：

| block key | P1 語義 | P1 邊界 |
| --- | --- | --- |
| `quote` | 實時行情和報價相關輸入 | 只定義可表達位置，不抓取或填充資料。 |
| `daily_bars` | 完整日線視窗和最近完整日線日期 | P1 不判斷 partial bar。 |
| `technical` | 技術指標、量價結構和形態 | P1 不生成指標。 |
| `fundamentals` | 估值、成長、盈利、財報和股東回報 | P1 不新增基本面 fetcher。 |
| `news` | 新聞、公告、輿情和催化事件輸入 | P1 不改變新聞搜尋。 |
| `portfolio` | 是否持股、帳戶摘要、成本、數量、部位和 stale 摘要 | P1 不納入交易流水、現金流水或完整帳戶隱私資料。 |
| `chip` / `capital_flow` | 籌碼、資金流和主力行為 | 後續擴充套件鍵，P1 只允許契約表達。 |
| `events` / `market_context` | 風險事件、市場寬度、指數、板塊和熱點環境 | 後續擴充套件鍵，不把 `market_review` / `market_light` 作為首版單股 pack。 |

`phase` 欄位只接收 #1386 `MarketPhaseContext.to_dict()` 產物，保持 `Dict[str, Any]`，不重新定義 phase enum 或 phase 子模型。

脫敏邊界：

- `AnalysisContextPack.to_safe_dict()` 先執行 `model_dump(mode="json")`，再呼叫 `redact_sensitive_mapping()`。
- `redact_sensitive_mapping()` 只做 dict/list 的 key-based 遞迴脫敏，命中 `api_key`、`access_token`、`refresh_token`、`authorization_header`、`webhook_url`、`password`、`cookie`、`secret`、`token`、`sendkey`、`license_key` 等敏感鍵或短語時把值替換為 `[REDACTED]`。
- P1 不掃描普通字串值，不做 URL 正則脫敏，不把 `data_api` 或裸 `api` / `key` 當作敏感命中，避免把本契約擴充套件成通用 secrets engine。

## P2 Builder 契約

P2 新增 `AnalysisContextBuilder`，但首版只做 assembler：從普通分析 pipeline 已經拿到的 artifacts 組裝內部 `AnalysisContextPack`。Issue 驗收項裡的“複用現有資料來源”在本 slice 中解釋為複用 pipeline 已 fetch 的 `realtime_quote`、`base_context`、`enhanced_context`、`trend_result`、`chip_data`、`fundamental_context`、`news_context` 等 artifacts；builder 本身 zero-fetch，不呼叫 DB、fetcher、SearchService、Agent 工具或具體 provider。

P2 輸入契約使用 `PipelineAnalysisArtifacts`：`code`、`stock_name`、`market`、`phase`、`base_context`、`enhanced_context`、`realtime_quote`、`trend_result`、`chip_data`、`fundamental_context`、`news_context`、`news_result_count`、`metadata`。單股 `build()` 與批次 `build_batch()` 複用同一結構，避免 P3 runtime 接入時再次改簽名。

P2 block 組裝邊界：

- `subject` 仍只寫 `code`、`stock_name`、`market` 三欄位，不擴 `AnalysisSubject`。
- `phase` 只接收傳入的 `MarketPhaseContext.to_dict()` 產物，不從 `enhanced_context` 反推。
- `quote` 從 `realtime_quote` 組裝；缺失為 `missing`；`source=fallback` 或顯式 `fallback_from` 對映為 `fallback`，但 `source` 保留真實成功源；`fallback_from` 只在 artifact/metadata 顯式提供時填寫，否則只記錄穩定 warning code，不偽造 provider 鏈。
- `quote` 會透傳 #1386 P3 的 `fetched_at`、`provider_timestamp`、`is_stale`、`stale_seconds`、`fallback_from`。狀態優先順序固定為 `STALE > FALLBACK > AVAILABLE`：`is_stale=True`、`price_stale`、`quote_stale`、`quote_stale_seconds` 等顯式 marker 標為 `stale`；`stale_seconds` 且 `is_stale=False` 只是後設資料，不單獨推斷 stale。builder 只對映上游 artifact，不做質量評分。
- `daily_bars` 只表達完整日線視窗，優先讀 `base_context.today`、`base_context.yesterday`、`base_context.date`、`base_context.data_missing`；date-only 放入 `value` 或 `metadata`，不寫入 `timestamp`。
- `enhanced_context.today` 上的 `is_partial_bar`、`is_estimated`、`estimated_fields` 優先進入 `technical`；缺失時仍相容 `enhanced_context.today.data_source` 為 `realtime:*` 的舊 heuristic。partial/estimated 只進入 `technical`，`daily_bars` 不承載 partial/estimated，warning 使用 `intraday_realtime_overlay`。
- `technical` 優先複用 `trend_result.to_dict()`；無 trend artifact 時為 `missing`。
- `chip` 複用 `chip_data.to_dict()`；無 chip artifact 預設 `missing`，只有輸入 metadata/artifact 明確 not_supported 時才標 `not_supported`。
- `fundamentals` 只讀 `fundamental_context` 引數；`ok` 對映為 `available`，`not_supported` 對映為 `not_supported`，`partial` 對映為 `partial`，P5 後 `failed` 對映為 `fetch_failed` + 穩定 reason code `fundamental_pipeline_failed`；不寫入 `errors[]` 原文。
- `news` 非空白字串為 `available`，空白或缺失為 `missing`；`news_result_count` 寫入 pack metadata。

P2 不組裝 `portfolio`、`events`、`market_context`，也不把 `capital_flow` 拆成獨立 block；首版只把它保留在 fundamentals 的 coverage/source chain metadata 中。P2 當時也不改變 Prompt、不讓普通分析或 Agent runtime 消費 pack、不寫入 history/task/report metadata、不暴露完整 pack 到 API/Web/Bot/Desktop/通知；P5 只在現有 builder 上追加低敏評分、`fetch_failed` 細分和 Prompt 限制，不新增 fetcher。

## P3 Runtime Consumption

P3 在 P2 `AnalysisContextBuilder` 之後接入執行態消費，但消費面限定為低敏 `analysis_context_pack_summary`。`StockAnalysisPipeline` 是 summary 的唯一生產者：在普通分析路徑和 Agent 路徑內完成 `PipelineAnalysisArtifacts` -> `AnalysisContextBuilder.build()` -> `format_analysis_context_pack_prompt_section()`，下游 analyzer、single-agent、multi-agent 只接收 summary 字串，不自行構造完整 pack，也不讀取 `AnalysisContextPack.to_safe_dict()` 的 block item 原始值。

普通分析 Prompt 的順序固定為：基礎資訊 -> #1386 `market_phase_context` 渲染區塊 -> `analysis_context_pack_summary` -> 技術面、實時行情、新聞等既有區塊。`analysis_context_pack_summary` 只包含 subject、`pack_version`、block `status` / `source` / `warnings` / `missing_reason`、`metadata.news_result_count`、`data_quality.warnings` 和 P5 低敏資料限制，不得輸出 `news.content`、`trend_result`、`chip`、`fundamental_context` 等原始 payload。

Agent 路徑同樣只傳 summary。`AgentExecutor._build_user_message()` 在 market phase 段之後、pre-fetched JSON 之前插入 summary；`AgentOrchestrator._build_context()` 只把 summary 放入 `ctx.meta["analysis_context_pack_summary"]`，禁止寫入 `ctx.data`；`BaseAgent._build_messages()` 在 market phase user message 之後、`_inject_cached_data()` 之前插入 summary。Agent 路徑會在 `_ensure_agent_history()` 預取後讀取一次 `storage.get_analysis_context()` 作為 `daily_bars` 的低敏狀態來源，讀取失敗或無可用上下文時才標記 `daily_bars_missing`，該讀取 fail-open 且不把日線原始 payload 寫入 Agent runtime context。Agent 首輪沒有複用普通分析新聞檢索，`news` block 為 `missing` 是當前 P3 的預期狀態。

P3 當時不持久化完整 pack，不新增 API/Web/Bot/Desktop 欄位，不改變報告 JSON schema，不把 summary 寫入 `analysis_history.context_snapshot`、task status 或 report metadata；history snapshot 和 diagnostic snapshot 會剝離 `market_phase_context`、`analysis_context_pack`、`analysis_context_pack_summary` 等 runtime prompt key。P4 在此基礎上新增低敏 overview，可見性只覆蓋歷史詳情、同步分析響應、completed task status 和 Web 報告頁；P5 繼續複用 summary 消費路徑，不改 LLM 輸出 JSON schema。Agent 工具級 pack cache 複用仍是後續工作。

## P4 歷史記錄、任務狀態與 Web 可見性

P4 把 P3 已構建的 `AnalysisContextPack` 投影為公共低敏 `analysis_context_pack_overview`。該 overview 由專用 renderer 生成，公共 API 不允許直接返回 `AnalysisContextPack.to_safe_dict()` 或完整 pack dump。renderer 只輸出白名單欄位：`pack_version`、`created_at`、`subject.code` / `stock_name` / `market`、資料塊 `key` / `label` / `status` / `source` / `warnings` / `missing_reasons`、按 block status 計數的 `counts`、頂層 `data_quality.warnings` 和 `metadata.trigger_source` / `metadata.news_result_count`。P5 在同一 overview 上追加 `data_quality` 低敏物件，不重複頂層 `warnings`。

overview 不輸出 `blocks.*.items`、`items.value`、`news.content`、`trend_result`、`chip`、`fundamental_context` 原始 payload，也不輸出 `api_key`、`token`、`cookie`、`webhook_url`、`password`、`secret`、`authorization`、`sendkey`、`license_key` 等敏感鍵或值。

P4 持久化面只在 `analysis_history.context_snapshot` 頂層寫入 `analysis_context_pack_overview`。執行態 prompt 欄位仍會從 `enhanced_context` 和 history snapshot 中剝離：`market_phase_context`、`analysis_context_pack`、`analysis_context_pack_summary` 不進入公開歷史詳情或任務狀態。`SAVE_CONTEXT_SNAPSHOT=false` 時不持久化 overview，舊記錄或缺少 overview 的記錄繼續返回空欄位，不影響歷史詳情讀取。

公共 API 欄位固定為 `report.details.analysis_context_pack_overview`，Web 端經深度 camelCase 後讀取 `analysisContextPackOverview`。接線麵包括：

- `GET /api/v1/history/{record_id}` 歷史詳情。
- 同步 `POST /api/v1/analysis/analyze` 返回的 `AnalysisResultResponse.report.details`。
- completed `GET /api/v1/analysis/status/{task_id}`，包括記憶體佇列 enrichment 和 DB completed fallback。

API 返回給 Web 的 `details.context_snapshot` 會透過 `sanitize_context_snapshot_for_api()` 剝離頂層 `analysis_context_pack_overview`，避免 raw snapshot 面板重複展示或被當作完整上下文匯出；overview 只從 `extract_analysis_context_pack_overview()` 單獨取出。Agent 路徑與普通分析路徑寫入同一 overview 形狀，Agent 無新聞計數時 `metadata.news_result_count` 可為空。

P4 Web 展示只在報告詳情頁渲染 `AnalysisContextSummary`，位置在策略點位和資訊之後、執行診斷之前；該區域預設摺疊，摺疊頭部展示可用數、缺失數、非零的其他狀態計數和觸發來源，展開後展示資料塊狀態 badge、來源、warning、missing reason、狀態計數和新聞結果數。P5 後摺疊頭部還會展示質量分/等級，展開後展示 `limitations` 和 `fetch_failed` 狀態。無 overview 時不渲染佔位。在 #1386 P4b 中，Web 會在同一報告詳情頁展示 `report.meta.market_phase_summary` 階段標籤，並繼續複用該低敏資料質量摘要；不擴大完整 pack、Prompt summary、raw payload 或 snapshot 內部欄位的公開面。P4/P5 不覆蓋 pending/processing TaskPanel 的 AnalysisContextPack 資料質量摘要或 SSE 進行中 overview 可見性，不改通知摘要、Bot/Desktop 專屬展示或 `market_review` overview。

## P5 資料質量評分與 Prompt 資料限制

P5 在不升級 `PACK_VERSION`、不新增 fetcher、不新增配置項、不做歷史遷移的前提下補齊三件事：內部低敏資料質量評分、跨模型通用的 Prompt 資料限制區塊，以及既有 `analysis_context_pack_overview` 的低敏可見性擴充套件。#1389 P5 仍不改變 LLM 輸出 JSON schema，也不做後處理強制改寫；#1386 P5 會消費這裡的低敏輸入質量，在報告 `dashboard.phase_decision` 中輸出盤中動作欄位與質量護欄結果。

狀態契約新增 `fetch_failed`，用於“當前欄位或資料塊本次抓取明確失敗”。首版只在已有 artifact 明確失敗時使用，例如 `fundamental_context.status == "failed"`；空新聞、未配置搜尋、無實時 quote artifact 或 chip 缺失仍保持既有 `missing` / `not_supported` 語義，避免把未啟用能力誤報成抓取失敗。`fetch_failed` 不代表整次分析失敗。

`DataQuality` 追加以下低敏欄位，並保留舊 `warnings` / `metadata`：

- `overall_score: Optional[int]`：0-100 總分。
- `level: Optional["good"|"usable"|"limited"|"poor"]`：`>=85 good`、`>=70 usable`、`>=55 limited`，否則 `poor`。
- `block_scores: Dict[str, int]`：固定六塊的狀態分。
- `limitations: List[str]`：最多 5 條穩定限制說明，使用 `block: status` 形式。

評分只計算固定六塊，不隨輔助塊缺失重歸一化，未來新增 block 不自動影響總分。權重固定為 `quote=25`、`daily_bars=25`、`technical=25`、`news=10`、`fundamentals=10`、`chip=5`；狀態分固定為 `available=100`、`partial=75`、`estimated=75`、`not_supported=70`、`fallback=65`、`stale=50`、`missing=35`、`fetch_failed=25`。總分公式為 `round(sum(block_score * weight) / 100)`。

`limitations` 優先列出核心塊 `quote` / `daily_bars` / `technical` 的 `stale`、`fallback`、`missing`、`fetch_failed`、`partial`、`estimated`；其次列出輔助塊 `news` / `fundamentals` / `chip` 的 `fetch_failed`、`fallback`、`stale`。輔助塊單純缺失不進入限制列表，避免把新聞缺失、未配置搜尋或不支援能力解釋成利好/利空。

Prompt 資料限制只在 `format_analysis_context_pack_prompt_section()` 內渲染，緊跟 pack summary，因此普通分析、single Agent 和 multi-agent 複用同一消費路徑。中文輸出 `資料限制`，英文輸出 `Data Limitations`；只有真實 score 存在時才輸出評分行。若 `quote`、`daily_bars` 或 `technical` 為 degraded 狀態，Prompt 明確要求最終 JSON 的 `confidence_level` 不得為 `高` / `High`。Prompt 繼續只使用 status/source/warnings/missing_reason/低敏評分，不輸出 raw payload、新聞正文、趨勢原始值、secret、token 或 webhook。

#1386 P2-full 在 P5 score/limitations 之後、confidence/safety 之前追加最小的 `phase × degraded data` 交叉約束：當 `AnalysisContextPack.phase` 來自合法 `MarketPhaseContext`，且 `quote`、`daily_bars` 或 `technical` 存在 degraded 狀態時，Prompt 只補充當前階段下資料質量如何限制盤中判斷、開盤計劃或保守分析；它不替代 P5 的 confidence/safety 規則，也不復述 `market_phase_context` 的 phase-only 文案。`pack.phase` 缺失、非 dict 或包含非法 phase 時 fail-open，僅保留 P5 通用資料限制。

overview 只擴充套件現有公開面：`analysis_context_pack_overview.data_quality` 白名單包含 `overall_score`、`level`、`block_scores`、`limitations`，不重複公開 `warnings`。`render_analysis_context_pack_overview()` 與 `extract_analysis_context_pack_overview()` / persisted sanitizer 都會清洗該物件；舊 overview 缺少 `data_quality` 時仍正常讀取。`details.context_snapshot` 繼續剝離頂層 `analysis_context_pack_overview`，不公開完整 pack。

## 欄位質量狀態

未來 pack 的欄位質量狀態在 P0 先固定七詞；P5 在同一 1.0 umbrella 內追加 `fetch_failed`。它們描述欄位或資料塊的質量，不描述業務流程是否成功。

| 狀態 | 含義 | 示例邊界 |
| --- | --- | --- |
| `available` | 欄位存在，來源和時間戳可解釋，當前路徑可正常使用。 | 實時行情返回價格和來源；歷史 K 線視窗滿足計算需求。 |
| `missing` | 當前路徑需要該欄位，但實際未取到或為空。 | DB 無最近日線，普通分析進入 `data_missing` 結果。 |
| `not_supported` | 當前市場、資料來源或路徑不支援該欄位，不應誤報為錯誤。 | 某些市場無籌碼分佈或資金流。 |
| `fallback` | 首選來源不可用，使用了備用來源或舊路徑。 | 持股價格從實時行情 fallback 到歷史收盤價。 |
| `stale` | 欄位存在，但時間新鮮度不足。 | 持股估值中的 `price_stale` / `fx_stale`。 |
| `estimated` | 欄位是估算值，不應當作完整事實。 | 盤中用實時價補今日 bar 後生成技術估計。 |
| `partial` | 資料塊部分可用、部分缺失。 | 大盤紅綠燈 `data_quality=partial` 或工具返回 `partial_cache`。 |
| `fetch_failed` | 當前路徑確認嘗試過抓取，但本次抓取失敗。 | `fundamental_context.status == "failed"` 對映為基本面 block 抓取失敗。 |

## 現有狀態對映

當前倉庫已有不少狀態詞。P0 只建立對映或不對映關係，避免後續把業務結果狀態混入欄位質量列舉。

| 現有詞或欄位 | 當前位置 | 建議關係 | 說明 |
| --- | --- | --- | --- |
| `data_missing` | 普通分析缺歷史資料結果 | 可對映到 `missing` | 這是核心輸入缺失，不是業務成功狀態。 |
| `cache_hit` / `partial_cache` | Agent 歷史資料工具 | `partial_cache` 可對映到 `partial` | `cache_hit` 是來源/快取後設資料，不是質量狀態。 |
| `source` / `data_source` / `realtime_source` | 資料來源、警告、上下文快照 | 不對映 | 這些是來源後設資料，應與欄位質量狀態並列儲存。 |
| `price_source=missing` | 持股快照 | 可對映到 `missing` | 表示估值價格不可用。 |
| `price_stale` / `fx_stale` | 持股快照 | 可對映到 `stale` | 保留原欄位作為業務後設資料。 |
| `triggered` / `skipped` / `degraded` / `failed` | 警告評估與記錄 | 不對映 | 這是規則評估或記錄結果，不是欄位級質量狀態。 |
| `insufficient_data` / `completed` / `error` | 回測服務 | 不對映 | 這是回測執行狀態；可在 pack 摘要中解釋觸發原因。 |
| `sent` / `no_channel` / `partial_failed` / `all_failed` | 通知傳送 | 不對映 | 這是通知投遞結果，不能反推分析輸入質量。 |
| `data_quality=ok/partial/unavailable` | 大盤紅綠燈 | `partial` 可對映，`unavailable` 視欄位場景對映到 `missing` 或 `not_supported` | P0 不把大盤紅綠燈納入首版單股 pack。 |
| `fetch_failed` | 資料質量細分 | P5 對映為 `fetch_failed` | 只在已有 artifact 明確失敗時使用，不代表整次分析失敗。 |

## 七路徑盤點

### 普通分析

普通分析主鏈路在 `src/core/pipeline.py` 中組裝輸入：先讀取 `storage.get_analysis_context()`，再按可用性補充實時行情、籌碼、趨勢分析、新聞、基本面和報告語言，最後交給 `src/analyzer.py` 渲染 prompt。當前重複點主要是實時欄位同時存在於 `enhanced_context.realtime`、`realtime_quote_raw` 和報告 meta；命名上存在 `source`、`data_source`、`realtime_source` 等多種來源欄位。

首版 pack 可從普通分析路徑抽取單股核心身份、行情、日線、技術、新聞、基本面和資料質量摘要；P0 不改變 `_enhance_context()`、`_build_context_snapshot()` 或 analyzer prompt。

### Agent

Agent 有三層需要分開記錄的資料面。`src/core/pipeline.py` 的 Agent 路徑會構造 `initial_context`，固定包含 `fundamental_context`，並在可用時加入 `trend_result`，最終作為 Agent 路徑的 `context_snapshot` 持久化。`AgentExecutor._build_user_message()` 只適用於 `AGENT_ARCH=single`，首輪訊息只顯式注入 `realtime_quote`、`chip_distribution`、`news_context` 等已取上下文，不顯式注入 `fundamental_context` 或 `trend_result`。`AgentOrchestrator._build_context()` 適用於 `AGENT_ARCH=multi`，可預注入 `realtime_quote`、`daily_history`、`chip_distribution`、`trend_result`、`news_context`，這些進入 `AgentContext` 的欄位會作為 pre-fetched data 注入 stage agent 訊息；但 orchestrator 不預注入 `fundamental_context`。`trend_result` 不是天然存在，取決於 caller 是否傳入。

Agent 工具還會獨立呼叫 `get_realtime_quote`、`get_daily_history`、`get_chip_distribution`、`get_analysis_context`、`get_stock_info` 等工具，容易與普通分析前置獲取產生重複請求。當前 pack 生成只在 Agent 歷史預取後複用 `storage.get_analysis_context()` 的日線可用性狀態，不復用或暴露完整工具級 pack cache；P5 再決定是否做更深的資料質量評分與工具快取複用。

### 警告

警告鏈路在 `src/services/alert_worker.py` 中評估規則、記錄觸發歷史並分發通知，具體欄位語義見 [實時警告中心](alerts.md)。警告狀態如 `triggered`、`skipped`、`degraded`、`failed` 是規則評估或記錄狀態，不能直接寫入欄位質量列舉。

首版 pack 不把警告規則評估作為輸入資料塊；警告後續只消費 pack 的欄位質量摘要，例如核心行情是否 fallback、是否 stale、是否 partial。

### 持股

持股快照在 `src/services/portfolio_service.py` 中聚合帳戶、部位、成本、價格、匯率和風險輸入，API 輸出結構在 `api/v1/schemas/portfolio.py`。當前已有 `price_source`、`price_provider`、`price_date`、`price_stale`、`price_available`、`fx_stale` 等欄位。

首版 pack 可記錄“是否持股、帳戶摘要、成本、數量、部位、浮盈浮虧、價格/匯率 stale 摘要”，但不納入交易流水、現金流水、公司行動或完整帳戶隱私資料。

### 回測

回測服務在 `src/services/backtest_service.py` 和 `src/repositories/backtest_repo.py` 中消費歷史分析記錄與日線資料。現有 `parse_analysis_date_from_snapshot()` 依賴 `analysis_history.context_snapshot.enhanced_context.date` 解析分析日期。

P0 必須把 `enhanced_context.date` 標為相容邊界。後續 pack 可以新增更清晰的日期欄位，但不能無遷移地刪除或改名當前歷史快照中的日期位置。

### 歷史

歷史詳情在 `src/services/history_service.py`、`api/v1/endpoints/history.py`、`api/v1/schemas/history.py` 中返回 `raw_result`、`news_content`、`context_snapshot` 等欄位。同步 analysis/status 響應也會在 `api/v1/endpoints/analysis.py` 中讀取 `context_snapshot.enhanced_context`、`realtime_quote_raw` 和基本面 fallback。

P0 只記錄歷史消費面。完整 pack 不應預設公開到歷史詳情或公共 API；後續 P4 如需展示，應優先暴露摘要、來源和降級說明。

### 通知

通知鏈路在 `src/notification.py` 中消費 `AnalysisResult`、dashboard、market snapshot、data_sources 等輸出，並記錄 `sent`、`no_channel`、`partial_failed`、`all_failed` 等投遞狀態；通道配置與邊界見 [通知能力基線](notifications.md)。

通知不是事實資料層，不能把投遞失敗誤寫成輸入質量失敗。後續只應在必要時消費 pack 摘要，例如“實時行情已降級”“基本面缺失”“新聞源不足”。

## 原始碼錨點

| 域 | 錨點 |
| --- | --- |
| 普通分析 | `src/core/pipeline.py`, `src/storage.py`, `src/analyzer.py` |
| Agent | `src/agent/orchestrator.py`, `src/agent/executor.py`, `src/agent/tools/data_tools.py` |
| 警告 | `src/services/alert_worker.py`, `docs/alerts.md` |
| 持股 | `src/services/portfolio_service.py`, `api/v1/schemas/portfolio.py` |
| 回測 | `src/services/backtest_service.py`, `src/repositories/backtest_repo.py` |
| 歷史 | `src/services/history_service.py`, `api/v1/endpoints/history.py`, `api/v1/endpoints/analysis.py`, `api/v1/schemas/history.py` |
| 通知 | `src/notification.py`, `docs/notifications.md` |

## 相容與安全邊界

- `analysis_history.context_snapshot.enhanced_context.date` 是當前回測日期解析相容點，P1/P2 不能在沒有遷移的情況下破壞。
- 完整 pack 不預設公開到歷史、API、Web 或通知；P4/P5 只公開 `analysis_context_pack_overview` 低敏摘要、來源、fallback、stale、missing reason、block status count 和 `data_quality` 低敏評分。
- pack、日誌、歷史快照和 API 響應不得記錄 API key、token、cookie、完整 webhook URL、郵箱密碼、私有環境變數或其他金鑰。
- `source`、`timestamp`、`fallback`、`stale`、`partial` 等質量後設資料只用於解釋輸入限制，不用於阻斷分析；除非現有核心路徑本來就是 fail-fast。
- #1386 的盤前 / 盤中 phase 感知是後續 `phase` / `data_quality` 欄位的重要背景；P0 只記錄關係，不接入 runtime。

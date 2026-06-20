import type React from 'react';
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, CircleAlert, Play, PlusCircle, Search, SlidersHorizontal } from 'lucide-react';
import {
  alphasiftApi,
  type AlphaSiftCandidate,
  type AlphaSiftScreenResponse,
  type AlphaSiftStrategy,
} from '../api/alphasift';
import { AppPage, Button, InlineAlert } from '../components/common';

const MARKETS = [{ id: 'cn', label: 'A 股' }];

const formatScore = (score: AlphaSiftCandidate['score']) => {
  if (score == null || Number.isNaN(Number(score))) {
    return '-';
  }
  return Number(score).toFixed(2);
};

const formatNumber = (value: unknown, digits = 2) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(digits);
};

const formatAmount = (value: unknown) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  const amount = Number(value);
  if (Math.abs(amount) >= 100_000_000) {
    return `${(amount / 100_000_000).toFixed(2)} 億`;
  }
  if (Math.abs(amount) >= 10_000) {
    return `${(amount / 10_000).toFixed(2)} 萬`;
  }
  return amount.toFixed(2);
};

const formatPercent = (value: unknown) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return `${(Number(value) * 100).toFixed(0)}%`;
};

const getCandidateReason = (item: AlphaSiftCandidate) => {
  if (item.reason) {
    return item.reason;
  }
  const summaries = item.postAnalysisSummaries || {};
  const summary = Object.values(summaries).find((value) => typeof value === 'string' && value.trim());
  if (typeof summary === 'string') {
    return summary;
  }
  return 'AlphaSift 返回候選，但沒有給出文字摘要。請檢視下方因子、風險和原始欄位。';
};

const getSignal = (item: AlphaSiftCandidate) => {
  const rawSignal = item.raw.action ?? item.raw.signal ?? item.raw.recommendation;
  return typeof rawSignal === 'string' && rawSignal.trim() ? rawSignal : '觀察';
};

const getFactorEntries = (item: AlphaSiftCandidate) =>
  Object.entries(item.factorScores || {})
    .filter(([, value]) => typeof value === 'number')
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 6);

const toMessageList = (values: string[] | undefined) =>
  Array.isArray(values) ? values.map((value) => String(value).trim()).filter(Boolean) : [];

const normalizeScreenMessageKey = (value: string) =>
  value.replace(/^Snapshot source fallback:\s*/i, '').trim();

const formatScreenMessage = (value: string) => {
  const snapshotFallback = value.match(/^Snapshot source fallback:\s*(.+)$/i);
  if (snapshotFallback) {
    return `資料來源降級：${snapshotFallback[1]}`;
  }
  return value;
};

const getScreenMessages = (meta: AlphaSiftScreenResponse | null) => {
  if (!meta) {
    return [];
  }
  const messages: string[] = [];
  const seen = new Set<string>();
  [...toMessageList(meta.warnings), ...toMessageList(meta.sourceErrors), ...toMessageList(meta.llmParseErrors)].forEach(
    (value) => {
      const key = normalizeScreenMessageKey(value);
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      messages.push(formatScreenMessage(value));
    },
  );
  return messages;
};

const hasLlmInsight = (item: AlphaSiftCandidate) =>
  Boolean(
    item.llmThesis ||
      item.llmSector ||
      item.llmTheme ||
      item.llmConfidence != null ||
      item.llmWatchItems?.length ||
      item.llmCatalysts?.length,
  );

const StockScreeningPage: React.FC = () => {
  const [enabled, setEnabled] = useState(false);
  const [market, setMarket] = useState('cn');
  const [strategy, setStrategy] = useState('dual_low');
  const [strategies, setStrategies] = useState<AlphaSiftStrategy[]>([]);
  const [maxResults, setMaxResults] = useState(3);
  const [candidates, setCandidates] = useState<AlphaSiftCandidate[]>([]);
  const [screenMeta, setScreenMeta] = useState<AlphaSiftScreenResponse | null>(null);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [enabling, setEnabling] = useState(false);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [error, setError] = useState('');
  const [strategyLoadError, setStrategyLoadError] = useState('');

  const selectedStrategy = useMemo(() => strategies.find((item) => item.id === strategy), [strategies, strategy]);
  const selectedStrategyTitle = selectedStrategy?.name || selectedStrategy?.title || '自定義策略';
  const selectedStrategyTag = selectedStrategy?.category || selectedStrategy?.tag || selectedStrategy?.tags?.[0] || '自定義';
  const displayedStrategy = selectedStrategy ? selectedStrategyTitle : `自定義策略 (${strategy})`;
  const screenMessages = useMemo(() => getScreenMessages(screenMeta), [screenMeta]);
  const llmDegraded = screenMeta?.llmRanked === false;
  const llmDegradationMessage = llmDegraded
    ? screenMessages.join('；') || 'LLM 重排未完成或未返回判斷，當前候選來自 AlphaSift 本地因子評分。'
    : '';

  const clearScreeningResults = () => {
    setCandidates([]);
    setScreenMeta(null);
    setExpandedCode(null);
  };

  const loadStrategies = useCallback(async () => {
    setLoadingStrategies(true);
    try {
      setStrategyLoadError('');
      const result = await alphasiftApi.getStrategies();
      const loadedStrategies = result.strategies || [];
      setStrategies(loadedStrategies);
      if (loadedStrategies.length > 0) {
        setStrategy((currentStrategy) =>
          loadedStrategies.some((item) => item.id === currentStrategy) ? currentStrategy : loadedStrategies[0].id,
        );
      }
    } catch (err) {
      setStrategies([]);
      setStrategyLoadError(err instanceof Error ? err.message : 'AlphaSift 策略列表載入失敗');
    } finally {
      setLoadingStrategies(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    alphasiftApi
      .getStatus()
      .then((status) => {
        if (!active) {
          return;
        }
        setEnabled(status.enabled);
        if (status.enabled) {
          void loadStrategies();
        }
      })
      .catch(() => {
        if (active) {
          setEnabled(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadStrategies]);

  const handleEnable = async () => {
    setEnabling(true);
    setError('');
    try {
      await alphasiftApi.enable();
      setEnabled(true);
      await loadStrategies();
    } catch (err) {
      try {
        const status = await alphasiftApi.getStatus();
        setEnabled(status.enabled);
      } catch {
        setEnabled(false);
      }
      setError(err instanceof Error ? err.message : '開啟 AlphaSift 失敗');
    } finally {
      setEnabling(false);
    }
  };

  const handleStrategyChange = (nextStrategy: string) => {
    if (nextStrategy !== strategy) {
      clearScreeningResults();
    }
    setStrategy(nextStrategy);
  };

  const handleMarketChange = (nextMarket: string) => {
    if (nextMarket !== market) {
      clearScreeningResults();
    }
    setMarket(nextMarket);
  };

  const handleMaxResultsChange = (nextMaxResults: number) => {
    if (nextMaxResults !== maxResults) {
      clearScreeningResults();
    }
    setMaxResults(nextMaxResults);
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    setScreenMeta(null);
    try {
      const result = await alphasiftApi.screen({ market, strategy, maxResults });
      setScreenMeta(result);
      setCandidates(result.candidates);
      setExpandedCode(result.candidates[0]?.code ?? null);
    } catch (err) {
      setCandidates([]);
      setError(err instanceof Error ? err.message : '選股失敗');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppPage className="max-w-6xl space-y-6 pb-12 pt-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-cyan text-cyan shadow-[0_0_24px_hsl(var(--primary)/0.18)]">
            <PlusCircle className="h-4 w-4" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-normal text-foreground">AlphaSift 選股</h1>
            <p className="mt-1 text-sm text-secondary-text">開啟後透過 AlphaSift 適配層生成候選股票</p>
          </div>
        </div>

        <div className="inline-flex w-fit items-center gap-2 rounded-2xl border border-border/70 bg-card/80 px-4 py-2 text-sm shadow-soft-card">
          <span className={`h-2.5 w-2.5 rounded-full ${enabled ? 'bg-success' : 'bg-warning'}`} />
          <span className="font-medium text-secondary-text">{enabled ? '選股已開啟' : '選股未開啟'}</span>
        </div>
      </div>

      {!enabled ? (
        <InlineAlert
          variant="info"
          title="AlphaSift 選股發現功能目前未啟用"
          message="此頁面屬於選用的進階探索功能，不影響一般 TW/US 自選股分析。"
          action={
            <Button size="sm" isLoading={enabling} loadingText="開啟中..." onClick={() => void handleEnable()}>
              開啟 AlphaSift
            </Button>
          }
        />
      ) : null}

      <InlineAlert
        variant="warning"
        title="風險提示"
        message="AlphaSift 選股結果僅用於研究和輔助判斷，不構成投資建議；市場有風險，交易決策和損益由使用者自行承擔。"
      />

      {error ? <InlineAlert variant="danger" title="呼叫失敗" message={error} /> : null}

      <section className="rounded-2xl border border-cyan/35 bg-card/95 p-4 shadow-soft-card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">選擇策略</h2>
            <p className="mt-1 text-xs text-secondary-text">策略來自 AlphaSift，DSA 只負責呼叫穩定適配層。</p>
          </div>
          <span className="rounded-full border border-cyan/30 bg-cyan/10 px-3 py-1 text-xs font-semibold text-cyan">
            {selectedStrategyTag}
          </span>
        </div>

        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {loadingStrategies ? (
            <div className="rounded-xl border border-dashed border-border bg-surface/70 p-4 text-sm text-secondary-text">
              正在讀取可用策略...
            </div>
          ) : strategies.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-surface/70 p-4 text-sm text-secondary-text">
              {strategyLoadError || 'AlphaSift 策略列表暫未載入，可在下方手動輸入策略引數。'}
            </div>
          ) : (
            strategies.map((item) => {
              const selected = item.id === strategy;
              return (
                <button
                  key={item.id}
                  className={`min-h-28 rounded-xl border p-4 text-left transition-all ${
                    selected
                      ? 'border-cyan bg-cyan/10 shadow-[0_0_0_1px_hsl(var(--primary)/0.15),0_16px_36px_hsl(var(--primary)/0.12)]'
                      : 'border-border/80 bg-surface/70 hover:border-cyan/45 hover:bg-hover/70'
                  }`}
                  type="button"
                  onClick={() => handleStrategyChange(item.id)}
                >
                  <span className="text-base font-semibold text-foreground">{item.name || item.title || item.id}</span>
                  <span className="mt-2 block text-sm leading-6 text-secondary-text">{item.description || item.id}</span>
                  <span className="mt-3 inline-flex text-xs font-semibold text-cyan">
                    {item.category || item.tag || item.tags?.[0] || item.id}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card/95 p-4 shadow-soft-card">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <SlidersHorizontal className="h-4 w-4 text-cyan" />
          引數設定
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr_180px_auto] lg:items-end">
          <label className="space-y-2 text-xs font-medium text-secondary-text">
            市場
            <select
              className="h-11 w-full rounded-xl border border-border bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-cyan"
              value={market}
              onChange={(event) => handleMarketChange(event.target.value)}
            >
              {MARKETS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-xs font-medium text-secondary-text">
            策略引數
            <input
              className="h-11 w-full rounded-xl border border-border bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-cyan"
              value={strategy}
              onChange={(event) => handleStrategyChange(event.target.value)}
            />
          </label>

          <label className="space-y-2 text-xs font-medium text-secondary-text">
            返回數量
            <input
              className="h-11 w-full rounded-xl border border-border bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-cyan"
              type="number"
              min={1}
              max={100}
              value={maxResults}
              onChange={(event) => handleMaxResultsChange(Number(event.target.value))}
            />
          </label>

          <Button
            className="h-11 min-w-40"
            isLoading={loading}
            loadingText="篩選中..."
            disabled={!enabled || loading}
            onClick={() => void handleSubmit()}
          >
            <Play className="h-4 w-4" />
            執行選股
          </Button>
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card/95 p-4 shadow-soft-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`grid h-7 w-7 place-items-center rounded-full ${
                candidates.length > 0 ? 'text-success' : enabled ? 'text-cyan' : 'text-warning'
              }`}
            >
              {candidates.length > 0 ? <CheckCircle2 className="h-5 w-5" /> : <CircleAlert className="h-5 w-5" />}
            </span>
            <div>
              <h2 className="text-sm font-semibold text-foreground">
                {candidates.length > 0 ? '選股完成' : enabled ? '等待執行' : '等待開啟'}
              </h2>
              <p className="mt-1 text-xs text-secondary-text">
                當前策略：{displayedStrategy} · {MARKETS.find((item) => item.id === market)?.label}
              </p>
            </div>
          </div>
          <div className="grid gap-1 text-xs text-secondary-text sm:text-right">
            <span>Run ID：{screenMeta?.runId || '-'}</span>
            <span>
              快照 {screenMeta?.snapshotCount ?? '-'} · 過濾後 {screenMeta?.afterFilterCount ?? '-'} · 候選 {screenMeta?.candidateCount ?? candidates.length}
            </span>
            <span>
              LLM：{screenMeta?.llmRanked ? '已重排' : screenMeta ? '未重排' : '-'}
              {screenMeta?.llmCoverage != null ? ` · 覆蓋 ${formatPercent(screenMeta.llmCoverage)}` : ''}
            </span>
          </div>
        </div>
      </section>

      {screenMeta && (screenMessages.length > 0 || llmDegradationMessage) ? (
        <InlineAlert
          variant={llmDegraded ? 'warning' : 'info'}
          title={llmDegraded ? 'LLM 已降級' : 'AlphaSift 提示'}
          message={llmDegradationMessage || screenMessages.join('；')}
        />
      ) : null}

      <section className="rounded-2xl border border-border bg-card/95 p-4 shadow-soft-card">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">選股結果</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary-text">
              AlphaSift 返回的候選會在這裡展示，展開後可檢視因子、風險、後置分析摘要和原始欄位。
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-2 text-xs text-secondary-text">
            <Search className="h-4 w-4 text-cyan" />
            {candidates.length} 條候選
          </div>
        </div>

        {candidates.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/70 px-5 py-10 text-center">
            <p className="text-sm font-medium text-foreground">暫無結果</p>
            <p className="mt-2 text-sm text-secondary-text">開啟 AlphaSift 後點選“執行選股”生成候選列表。</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <thead className="bg-surface text-left text-xs text-secondary-text">
                <tr>
                  <th className="w-14 px-4 py-3 font-semibold">#</th>
                  <th className="px-4 py-3 font-semibold">代號</th>
                  <th className="px-4 py-3 font-semibold">名稱</th>
                  <th className="px-4 py-3 font-semibold">行業</th>
                  <th className="px-4 py-3 font-semibold">價格</th>
                  <th className="px-4 py-3 font-semibold">漲跌幅</th>
                  <th className="px-4 py-3 font-semibold">評分</th>
                  <th className="px-4 py-3 font-semibold">LLM</th>
                  <th className="px-4 py-3 font-semibold">風險</th>
                  <th className="px-4 py-3 font-semibold">詳情</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((item) => {
                  const expanded = expandedCode === item.code;
                  const factors = getFactorEntries(item);
                  const llmInsightAvailable = hasLlmInsight(item);
                  const llmFallbackText =
                    llmDegraded && !llmInsightAvailable
                      ? '本次 LLM 重排失敗或未返回判斷，當前展示的是本地因子評分結果。'
                      : '暫無 LLM 判斷';
                  return (
                    <Fragment key={`${item.rank}-${item.code}`}>
                      <tr className="border-t border-border align-top transition-colors hover:bg-hover/50">
                        <td className="px-4 py-3 text-secondary-text">{item.rank}</td>
                        <td className="px-4 py-3 font-mono font-semibold text-foreground">{item.code}</td>
                        <td className="px-4 py-3 font-semibold text-foreground">{item.name || '-'}</td>
                        <td className="px-4 py-3 text-secondary-text">{item.industry || '-'}</td>
                        <td className="px-4 py-3 text-secondary-text">{formatNumber(item.price)}</td>
                        <td className="px-4 py-3 text-secondary-text">{formatNumber(item.changePct)}%</td>
                        <td className="px-4 py-3 font-bold text-cyan">{formatScore(item.score)}</td>
                        <td className="px-4 py-3 text-secondary-text">{llmDegraded ? '未重排' : formatScore(item.llmScore)}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-lg bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
                            {item.riskLevel || 'unknown'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <button
                            className="text-sm font-semibold text-cyan transition-colors hover:text-foreground"
                            type="button"
                            onClick={() => setExpandedCode(expanded ? null : item.code)}
                          >
                            {expanded ? '收起' : '展開檢視'}
                          </button>
                        </td>
                      </tr>
                      {expanded ? (
                        <tr className="border-t border-border bg-surface/45">
                          <td colSpan={10} className="px-4 py-4">
                            <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
                              <div className="space-y-3">
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">摘要</p>
                                  <p className="mt-1 text-sm leading-6 text-foreground">{getCandidateReason(item)}</p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">操作訊號</p>
                                  <p className="mt-1 text-sm text-foreground">{getSignal(item)}</p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">LLM 判斷</p>
                                  <p className="mt-1 text-sm leading-6 text-foreground">
                                    {item.llmThesis || llmFallbackText}
                                  </p>
                                  {llmInsightAvailable ? (
                                    <p className="mt-1 text-xs text-secondary-text">
                                      板塊 {item.llmSector || '-'} · 主題 {item.llmTheme || '-'} · 置信度 {formatPercent(item.llmConfidence)}
                                    </p>
                                  ) : (
                                    <p className="mt-1 text-xs text-secondary-text">LLM 後設資料未返回</p>
                                  )}
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">風險標籤</p>
                                  <p className="mt-1 text-sm text-foreground">
                                    {[...(item.riskFlags || []), ...(item.llmRisks || [])].length
                                      ? [...(item.riskFlags || []), ...(item.llmRisks || [])].join('，')
                                      : '無'}
                                  </p>
                                </div>
                              </div>
                              <div className="space-y-3">
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">主要因子</p>
                                  <div className="mt-2 grid grid-cols-2 gap-2">
                                    {factors.length > 0 ? (
                                      factors.map(([key, value]) => (
                                        <div key={key} className="rounded-lg border border-border bg-card px-3 py-2">
                                          <span className="block text-xs text-secondary-text">{key}</span>
                                          <span className="text-sm font-semibold text-foreground">{formatNumber(value)}</span>
                                        </div>
                                      ))
                                    ) : (
                                      <span className="text-sm text-secondary-text">無因子明細</span>
                                    )}
                                  </div>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">成交額</p>
                                  <p className="mt-1 text-sm text-foreground">{formatAmount(item.amount)}</p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">LLM 關注項</p>
                                  <p className="mt-1 text-sm text-foreground">
                                    {item.llmWatchItems?.length ? item.llmWatchItems.join('，') : llmDegraded ? '未返回（LLM 已降級）' : '無'}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">催化因素</p>
                                  <p className="mt-1 text-sm text-foreground">
                                    {item.llmCatalysts?.length ? item.llmCatalysts.join('，') : llmDegraded ? '未返回（LLM 已降級）' : '無'}
                                  </p>
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppPage>
  );
};

export default StockScreeningPage;

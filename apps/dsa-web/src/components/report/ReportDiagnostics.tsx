import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, Check, ChevronDown, Copy } from 'lucide-react';
import { diagnosticsApi } from '../../api/diagnostics';
import { historyApi } from '../../api/history';
import type {
  NewsProviderProbeMarket,
  NewsProviderProbeMode,
  NewsProviderProbeResponse,
  ReportLanguage,
  RunDiagnosticComponent,
  RunDiagnosticComponentStatus,
  RunDiagnosticStatus,
  RunDiagnosticSummary,
} from '../../types/analysis';
import { normalizeReportLanguage } from '../../utils/reportLanguage';
import { Badge, Button, Card, StatusDot } from '../common';

interface ReportDiagnosticsProps {
  recordId?: number;
  summary?: RunDiagnosticSummary;
  language?: ReportLanguage;
}

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>['variant']>;
type StatusTone = NonNullable<React.ComponentProps<typeof StatusDot>['tone']>;

type ProbeTargetValue = `${NewsProviderProbeMarket}:${string}`;

interface NewsProbeState {
  loading: boolean;
  result: NewsProviderProbeResponse | null;
  error: string | null;
}

interface NewsProbeControls {
  target: ProbeTargetValue;
  setTarget: (value: ProbeTargetValue) => void;
  mode: NewsProviderProbeMode;
  setMode: (value: NewsProviderProbeMode) => void;
  run: () => void;
  state: NewsProbeState;
}

const COMPONENT_ORDER = [
  'realtime_quote',
  'daily_data',
  'news',
  'llm',
  'notification',
  'history',
];

const TEXT = {
  zh: {
    eyebrow: '執行診斷',
    title: '執行狀態',
    loading: '診斷載入中...',
    unavailable: '執行診斷暫不可用',
    noComponents: '暫無元件診斷',
    components: '關鍵鏈路',
    advanced: '高階欄位',
    copy: '複製排障資訊',
    copied: '已複製',
    trace: 'Trace',
    task: 'Task',
    query: 'Query',
    trigger: '觸發來源',
    overall: {
      normal: '正常',
      degraded: '部分降級',
      failed: '失敗',
      unknown: '未知',
    },
    component: {
      ok: '正常',
      degraded: '最近失敗後已降級',
      failed: '失敗',
      unknown: '未知',
      not_configured: '未配置',
      skipped: '已跳過',
    },
  },
  zh_TW: {
    eyebrow: '執行診斷',
    title: '執行狀態',
    loading: '診斷載入中...',
    unavailable: '執行診斷暫不可用',
    noComponents: '暫無元件診斷',
    components: '關鍵鏈路',
    advanced: '進階欄位',
    copy: '複製排障資訊',
    copied: '已複製',
    trace: 'Trace',
    task: 'Task',
    query: 'Query',
    trigger: '觸發來源',
    overall: {
      normal: '正常',
      degraded: '部分降級',
      failed: '失敗',
      unknown: '未知',
    },
    component: {
      ok: '正常',
      degraded: '近期失敗後已降級',
      failed: '失敗',
      unknown: '未知',
      not_configured: '未設定',
      skipped: '已跳過',
    },
  },
  en: {
    eyebrow: 'RUN DIAGNOSTICS',
    title: 'Run Status',
    loading: 'Loading diagnostics...',
    unavailable: 'Diagnostics unavailable',
    noComponents: 'No component diagnostics',
    components: 'Key Path',
    advanced: 'Advanced Fields',
    copy: 'Copy diagnostics',
    copied: 'Copied',
    trace: 'Trace',
    task: 'Task',
    query: 'Query',
    trigger: 'Trigger',
    overall: {
      normal: 'Normal',
      degraded: 'Degraded',
      failed: 'Failed',
      unknown: 'Unknown',
    },
    component: {
      ok: 'Normal',
      degraded: 'Recent failure',
      failed: 'Failed',
      unknown: 'Unknown',
      not_configured: 'Not configured',
      skipped: 'Skipped',
    },
  },
} as const;

const NEWS_PROBE_TARGETS: Array<{ value: ProbeTargetValue; label: string; symbol: string; market: NewsProviderProbeMarket }> = [
  { value: 'tw:2330', label: 'TW 2330', symbol: '2330', market: 'tw' },
  { value: 'tw:2454', label: 'TW 2454', symbol: '2454', market: 'tw' },
  { value: 'us:AAPL', label: 'US AAPL', symbol: 'AAPL', market: 'us' },
  { value: 'us:NVDA', label: 'US NVDA', symbol: 'NVDA', market: 'us' },
];

const NEWS_PROBE_MODES: Array<{ value: NewsProviderProbeMode; label: string }> = [
  { value: 'runtime', label: 'Runtime' },
  { value: 'searxng', label: 'SearXNG' },
  { value: 'tavily', label: 'Tavily' },
];

const OVERALL_STATUS_STYLE: Record<RunDiagnosticStatus, { variant: BadgeVariant; tone: StatusTone }> = {
  normal: { variant: 'success', tone: 'success' },
  degraded: { variant: 'warning', tone: 'warning' },
  failed: { variant: 'danger', tone: 'danger' },
  unknown: { variant: 'default', tone: 'neutral' },
};

const COMPONENT_STATUS_STYLE: Record<RunDiagnosticComponentStatus, { variant: BadgeVariant; tone: StatusTone }> = {
  ok: { variant: 'success', tone: 'success' },
  degraded: { variant: 'warning', tone: 'warning' },
  failed: { variant: 'danger', tone: 'danger' },
  unknown: { variant: 'default', tone: 'neutral' },
  not_configured: { variant: 'default', tone: 'neutral' },
  skipped: { variant: 'default', tone: 'neutral' },
};

const compactId = (value?: string): string | null => {
  const text = (value || '').trim();
  if (!text) return null;
  if (text.length <= 28) return text;
  return `${text.slice(0, 10)}...${text.slice(-8)}`;
};

const getOrderedComponents = (
  components?: Record<string, RunDiagnosticComponent>,
): RunDiagnosticComponent[] => {
  const items = Object.values(components || {});
  const ordered = COMPONENT_ORDER
    .map((key) => items.find((component) => component.key === key))
    .filter((component): component is RunDiagnosticComponent => Boolean(component));
  const remaining = items.filter((component) => !COMPONENT_ORDER.includes(component.key));
  return [...ordered, ...remaining];
};

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
);

const asStringList = (value: unknown): string[] => (
  Array.isArray(value)
    ? value
      .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      .map((item) => item.trim())
    : []
);

const asDisplayValue = (value: unknown): string | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return null;
};

const sanitizeProbeDisplayText = (value: unknown, maxLength = 220): string | null => {
  if (value === null || value === undefined) {
    return null;
  }
  let text = String(value).replace(/\s+/g, ' ').trim();
  if (!text) {
    return null;
  }
  text = text.replace(/https?:\/\/[^\s]+?(?:token|key|secret|webhook)[^\s]*/gi, '<redacted-url>');
  text = text.replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer <redacted>');
  text = text.replace(
    /\b([A-Z0-9_]*?(?:api[_-]?key|access[_-]?token|token|secret|password|passwd|cookie))\s*=\s*([^\s,&;]+)/gi,
    '$1=<redacted>',
  );
  text = text.replace(
    /\b(api[_-]?key|access[_-]?token|token|secret|password|passwd|cookie)\s*:\s*([^\s,&;]+)/gi,
    '$1=<redacted>',
  );
  return text.length > maxLength ? `${text.slice(0, maxLength).trimEnd()}...` : text;
};

const sanitizeProbeDisplayList = (values: unknown[] | undefined, maxLength = 180): string[] => (
  Array.isArray(values)
    ? values
      .map((value) => sanitizeProbeDisplayText(value, maxLength))
      .filter((value): value is string => Boolean(value))
    : []
);

const safeProbeItemUrl = (value: unknown): string | null => {
  const text = sanitizeProbeDisplayText(value, 500);
  if (!text || text.includes('<redacted') || !/^https?:\/\//i.test(text)) {
    return null;
  }
  return text;
};

const selectedProbeTarget = (target: ProbeTargetValue) => (
  NEWS_PROBE_TARGETS.find((item) => item.value === target) || NEWS_PROBE_TARGETS[0]
);

const renderManualProbeResult = (probeState: NewsProbeState): React.ReactNode => {
  const result = probeState.result;
  if (!result && !probeState.error && !probeState.loading) {
    return null;
  }

  const providers = sanitizeProbeDisplayList(result?.providersAttempted, 80);
  const queryVariants = sanitizeProbeDisplayList(result?.queryVariants, 180);
  const errorMessage = sanitizeProbeDisplayText(probeState.error || result?.errorMessage, 220);
  const items = (result?.items || [])
    .map((item) => ({
      title: sanitizeProbeDisplayText(item.title, 220),
      source: sanitizeProbeDisplayText(item.source, 80),
      url: safeProbeItemUrl(item.url),
      publishedAt: sanitizeProbeDisplayText(item.publishedAt, 40),
    }))
    .filter((item) => item.title);

  return (
    <div className="mt-3 rounded-md border border-border/70 bg-surface/70 p-2.5">
      <p className="font-medium text-foreground">手動測試結果</p>
      {probeState.loading ? (
        <p className="mt-2 text-secondary-text">測試中...</p>
      ) : null}
      {result ? (
        <div className="mt-2 grid gap-1.5 text-secondary-text">
          <p>模式：{sanitizeProbeDisplayText(result.providerMode, 40) || 'runtime'}</p>
          <p>狀態：{sanitizeProbeDisplayText(result.status, 40) || 'unknown'}</p>
          {providers.length ? <p>嘗試來源：{providers.join(', ')}</p> : null}
          <p>查詢次數：{result.attemptCount ?? 0}</p>
          <p>結果數：{result.resultCount ?? 0}</p>
          <p>使用備援：{result.fallbackUsed ? '是' : '否'}</p>
          <p>延遲：{result.latencyMs ?? 0} ms</p>
          {errorMessage ? (
            <p className="text-red-600">新聞來源測試失敗：{errorMessage}</p>
          ) : null}
        </div>
      ) : null}
      {items.length ? (
        <ul className="mt-2 space-y-1.5 text-secondary-text">
          {items.map((item, index) => (
            <li key={`${item.title}-${index}`} className="min-w-0">
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="break-words font-medium text-foreground hover:text-cyan"
                >
                  {item.title}
                </a>
              ) : (
                <span className="break-words font-medium text-foreground">{item.title}</span>
              )}
              <span className="mt-0.5 block text-muted-text">
                {[item.source, item.publishedAt].filter(Boolean).join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {queryVariants.length ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-muted-text">本次查詢變體</summary>
          <ul className="mt-1 space-y-1 text-secondary-text">
            {queryVariants.map((query) => (
              <li key={query} className="break-words">
                {query}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
};

const renderNewsSearchDiagnostics = (
  component: RunDiagnosticComponent,
  probeControls: NewsProbeControls,
): React.ReactNode => {
  if (component.key !== 'news') {
    return null;
  }

  const details = asRecord(component.details);
  const providers = asStringList(details.providersAttempted ?? details.providers_attempted);
  const queryVariants = asStringList(details.queryVariants ?? details.query_variants);
  const attemptCount = asDisplayValue(details.attemptCount ?? details.attempt_count);
  const resultCount = asDisplayValue(details.resultCount ?? details.result_count);
  const finalStatus = asDisplayValue(details.finalStatus ?? details.final_status);
  const rawFallbackUsed = details.fallbackUsed ?? details.fallback_used;
  const fallbackUsed = typeof rawFallbackUsed === 'boolean'
    ? (rawFallbackUsed ? '是' : '否')
    : null;

  return (
    <div className="mt-3 rounded-md border border-border/70 bg-base/40 p-2.5 text-xs text-secondary-text">
      <p className="font-medium text-foreground">新聞搜尋診斷</p>
      {providers.length || attemptCount || resultCount || finalStatus || fallbackUsed ? (
        <div className="mt-2 grid gap-1.5">
          {finalStatus ? <p>狀態：{finalStatus}</p> : null}
          {providers.length ? <p>嘗試來源：{providers.join(', ')}</p> : null}
          {attemptCount ? <p>查詢次數：{attemptCount}</p> : null}
          {resultCount ? <p>結果數：{resultCount}</p> : null}
          {fallbackUsed ? <p>使用備援：{fallbackUsed}</p> : null}
        </div>
      ) : null}
      {queryVariants.length ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-muted-text">查詢變體</summary>
          <ul className="mt-1 space-y-1">
            {queryVariants.map((query) => (
              <li key={query} className="break-words">
                {query}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <label className="sr-only" htmlFor="news-provider-probe-target">新聞來源測試標的</label>
        <select
          id="news-provider-probe-target"
          aria-label="新聞來源測試標的"
          value={probeControls.target}
          onChange={(event) => probeControls.setTarget(event.target.value as ProbeTargetValue)}
          className="min-h-8 rounded-md border border-border bg-surface px-2 py-1 text-xs text-foreground"
        >
          {NEWS_PROBE_TARGETS.map((target) => (
            <option key={target.value} value={target.value}>
              {target.label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="news-provider-probe-mode">新聞來源測試模式</label>
        <select
          id="news-provider-probe-mode"
          aria-label="新聞來源測試模式"
          value={probeControls.mode}
          onChange={(event) => probeControls.setMode(event.target.value as NewsProviderProbeMode)}
          className="min-h-8 rounded-md border border-border bg-surface px-2 py-1 text-xs text-foreground"
        >
          {NEWS_PROBE_MODES.map((mode) => (
            <option key={mode.value} value={mode.value}>
              {mode.label}
            </option>
          ))}
        </select>
        <Button
          variant="secondary"
          size="xsm"
          onClick={probeControls.run}
          disabled={probeControls.state.loading}
        >
          測試新聞來源
        </Button>
      </div>
      {renderManualProbeResult(probeControls.state)}
    </div>
  );
};

/**
 * Collapsed report diagnostics for self-hosted troubleshooting.
 */
export const ReportDiagnostics: React.FC<ReportDiagnosticsProps> = ({
  recordId,
  summary,
  language = 'zh',
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = TEXT[reportLanguage];
  const [fetchState, setFetchState] = useState<{
    recordId?: number;
    summary: RunDiagnosticSummary | null;
    failed: boolean;
  }>({
    summary: null,
    failed: false,
  });
  const [copied, setCopied] = useState(false);
  const [probeTarget, setProbeTarget] = useState<ProbeTargetValue>('tw:2330');
  const [probeMode, setProbeMode] = useState<NewsProviderProbeMode>('runtime');
  const [probeState, setProbeState] = useState<NewsProbeState>({
    loading: false,
    result: null,
    error: null,
  });
  const resetCopiedTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (summary || !recordId) {
      return undefined;
    }

    let active = true;
    void historyApi.getDiagnostics(recordId)
      .then((result) => {
        if (active) {
          setFetchState({
            recordId,
            summary: result,
            failed: false,
          });
        }
      })
      .catch(() => {
        if (active) {
          setFetchState({
            recordId,
            summary: null,
            failed: true,
          });
        }
      });

    return () => {
      active = false;
    };
  }, [recordId, summary]);

  useEffect(() => () => {
    if (resetCopiedTimerRef.current !== null) {
      window.clearTimeout(resetCopiedTimerRef.current);
    }
  }, []);

  const fetchedForRecord = recordId !== undefined && fetchState.recordId === recordId
    ? fetchState
    : null;
  const loadedSummary = summary ?? fetchedForRecord?.summary ?? null;
  const loadFailed = !summary && Boolean(fetchedForRecord?.failed);
  const isLoading = Boolean(recordId && !summary && !fetchedForRecord);

  const visibleSummary = useMemo<RunDiagnosticSummary | null>(() => {
    if (loadedSummary) {
      return loadedSummary;
    }
    if (!recordId && !summary) {
      return null;
    }
    if (!isLoading && !loadFailed) {
      return null;
    }
    return {
      status: 'unknown',
      statusLabel: text.overall.unknown,
      reason: loadFailed ? text.unavailable : text.loading,
      components: {},
      copyText: '',
    };
  }, [isLoading, loadFailed, loadedSummary, recordId, summary, text]);

  if (!visibleSummary) {
    return null;
  }

  const statusStyle = OVERALL_STATUS_STYLE[visibleSummary.status] || OVERALL_STATUS_STYLE.unknown;
  const statusLabel = text.overall[visibleSummary.status] || visibleSummary.statusLabel;
  const components = getOrderedComponents(visibleSummary.components);
  const traceId = compactId(visibleSummary.traceId);
  const taskId = compactId(visibleSummary.taskId);
  const queryId = compactId(visibleSummary.queryId);
  const hasCopyText = Boolean(visibleSummary.copyText && !isLoading);
  const advancedPayload = {
    traceId: visibleSummary.traceId,
    taskId: visibleSummary.taskId,
    queryId: visibleSummary.queryId,
    stockCode: visibleSummary.stockCode,
    triggerSource: visibleSummary.triggerSource,
    components: components.reduce<Record<string, Record<string, unknown>>>((payload, component) => {
      payload[component.key] = {
        status: component.status,
        message: component.message,
        details: component.details || {},
      };
      return payload;
    }, {}),
  };
  const hasAdvancedPayload = Boolean(
    visibleSummary.traceId
    || visibleSummary.taskId
    || visibleSummary.queryId
    || visibleSummary.stockCode
    || visibleSummary.triggerSource
    || components.some((component) => component.details && Object.keys(component.details).length > 0),
  );

  const copyDiagnostics = async () => {
    if (!hasCopyText || !navigator.clipboard?.writeText) {
      return;
    }

    try {
      await navigator.clipboard.writeText(visibleSummary.copyText);
      setCopied(true);
      if (resetCopiedTimerRef.current !== null) {
        window.clearTimeout(resetCopiedTimerRef.current);
      }
      resetCopiedTimerRef.current = window.setTimeout(() => {
        setCopied(false);
        resetCopiedTimerRef.current = null;
      }, 2000);
    } catch (err) {
      console.error('Copy diagnostics failed:', err);
    }
  };

  const runNewsProviderProbe = async () => {
    const target = selectedProbeTarget(probeTarget);
    setProbeState({
      loading: true,
      result: null,
      error: null,
    });
    try {
      const result = await diagnosticsApi.probeNewsProvider({
        symbol: target.symbol,
        market: target.market,
        providerMode: probeMode,
        limit: 4,
      });
      setProbeState({
        loading: false,
        result,
        error: null,
      });
    } catch (err) {
      setProbeState({
        loading: false,
        result: null,
        error: sanitizeProbeDisplayText(err instanceof Error ? err.message : err, 220) || 'probe failed',
      });
    }
  };

  const newsProbeControls: NewsProbeControls = {
    target: probeTarget,
    setTarget: setProbeTarget,
    mode: probeMode,
    setMode: setProbeMode,
    run: () => void runNewsProviderProbe(),
    state: probeState,
  };

  return (
    <Card variant="bordered" padding="none" className="home-panel-card text-left">
      <details data-testid="run-diagnostics" className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan/10 text-cyan">
              <Activity className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="label-uppercase">{text.eyebrow}</span>
              <span className="mt-0.5 block truncate text-base font-semibold text-foreground">
                {text.title}
              </span>
            </span>
          </div>
          <span className="flex shrink-0 items-center gap-2">
            {isLoading ? (
              <span className="home-spinner h-3.5 w-3.5 animate-spin border-2" aria-hidden="true" />
            ) : null}
            <Badge variant={statusStyle.variant} className="gap-1.5 shadow-none">
              <StatusDot tone={statusStyle.tone} className="h-1.5 w-1.5" />
              {statusLabel}
            </Badge>
            <ChevronDown className="h-4 w-4 text-muted-text transition-transform group-open:rotate-180" aria-hidden="true" />
          </span>
        </summary>

        <div className="home-divider space-y-4 border-t px-4 pb-4 pt-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0 space-y-2">
              <p className="text-sm leading-6 text-foreground">
                {visibleSummary.reason}
              </p>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-text">
                {traceId ? (
                  <span className="home-accent-chip px-2 py-0.5 font-mono">
                    {text.trace}: {traceId}
                  </span>
                ) : null}
                {taskId ? (
                  <span className="home-accent-chip px-2 py-0.5 font-mono">
                    {text.task}: {taskId}
                  </span>
                ) : null}
                {queryId ? (
                  <span className="home-accent-chip px-2 py-0.5 font-mono">
                    {text.query}: {queryId}
                  </span>
                ) : null}
                {visibleSummary.triggerSource ? (
                  <span className="home-accent-chip px-2 py-0.5">
                    {text.trigger}: {visibleSummary.triggerSource}
                  </span>
                ) : null}
              </div>
            </div>
            <Button
              variant="ghost"
              size="xsm"
              disabled={!hasCopyText}
              onClick={() => void copyDiagnostics()}
              aria-label={copied ? text.copied : text.copy}
              className="shrink-0"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? text.copied : text.copy}
            </Button>
          </div>

          <div>
            <span className="label-uppercase">{text.components}</span>
            <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
              {components.length > 0 ? components.map((component) => {
                const componentStyle = COMPONENT_STATUS_STYLE[component.status] || COMPONENT_STATUS_STYLE.unknown;
                const componentLabel = text.component[component.status] || component.status;
                return (
                  <div key={component.key} className="home-subpanel p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">
                          {component.label}
                        </p>
                      <p className="mt-1 text-xs leading-5 text-secondary-text">
                        {component.message}
                      </p>
                      {renderNewsSearchDiagnostics(component, newsProbeControls)}
                    </div>
                    <Badge variant={componentStyle.variant} className="shrink-0 gap-1.5 shadow-none">
                      <StatusDot tone={componentStyle.tone} className="h-1.5 w-1.5" />
                        {componentLabel}
                      </Badge>
                    </div>
                  </div>
                );
              }) : (
                <p className="home-subpanel p-3 text-sm text-secondary-text">
                  {text.noComponents}
                </p>
              )}
            </div>
          </div>

          {hasAdvancedPayload ? (
            <details className="home-subpanel group/advanced p-3">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                <span className="text-sm font-medium text-foreground">{text.advanced}</span>
                <ChevronDown className="h-4 w-4 text-muted-text transition-transform group-open/advanced:rotate-180" aria-hidden="true" />
              </summary>
              <pre className="home-trace-pre home-trace-pre-content mt-3 max-h-80 overflow-auto rounded-lg bg-base p-3 text-left font-mono text-xs text-foreground">
                {JSON.stringify(advancedPayload, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      </details>
    </Card>
  );
};

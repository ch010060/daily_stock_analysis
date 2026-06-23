import type React from 'react';
import { useEffect, useState } from 'react';
import { ChevronDown, Database } from 'lucide-react';
import { historyApi } from '../../api/history';
import type {
  AnalysisContextPackBlockStatus,
  AnalysisContextPackOverview,
  ReportLanguage,
  RunDiagnosticComponent,
  RunDiagnosticSummary,
} from '../../types/analysis';
import { normalizeReportLanguage } from '../../utils/reportLanguage';
import { Badge, Card, StatusDot } from '../common';
import { DashboardPanelHeader } from '../dashboard';

interface AnalysisContextSummaryProps {
  overview?: AnalysisContextPackOverview | null;
  diagnosticSummary?: RunDiagnosticSummary | null;
  recordId?: number;
  language?: ReportLanguage;
}

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>['variant']>;
type StatusTone = NonNullable<React.ComponentProps<typeof StatusDot>['tone']>;

const STATUS_STYLE: Record<AnalysisContextPackBlockStatus, { variant: BadgeVariant; tone: StatusTone }> = {
  available: { variant: 'success', tone: 'success' },
  missing: { variant: 'danger', tone: 'danger' },
  not_supported: { variant: 'default', tone: 'neutral' },
  fallback: { variant: 'success', tone: 'success' },
  stale: { variant: 'warning', tone: 'warning' },
  estimated: { variant: 'info', tone: 'info' },
  partial: { variant: 'warning', tone: 'warning' },
  fetch_failed: { variant: 'danger', tone: 'danger' },
};

const QUALITY_STYLE = {
  good: { variant: 'success', tone: 'success' },
  usable: { variant: 'info', tone: 'info' },
  limited: { variant: 'warning', tone: 'warning' },
  poor: { variant: 'danger', tone: 'danger' },
} as const satisfies Record<string, { variant: BadgeVariant; tone: StatusTone }>;

const BLOCK_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    quote: '行情',
    daily_bars: '日線',
    technical: '技術',
    news: '新聞',
    fundamentals: '基本面',
    chip: '籌碼',
  },
  zh_TW: {
    quote: '行情',
    daily_bars: '日線',
    technical: '技術',
    news: '新聞',
    fundamentals: '基本面',
    chip: '籌碼',
  },
  en: {
    quote: 'quote',
    daily_bars: 'daily bars',
    technical: 'technical',
    news: 'news',
    fundamentals: 'fundamentals',
    chip: 'chip',
  },
};

const TEXT = {
  zh: {
    eyebrow: '資料上下文',
    title: '輸入資料塊',
    counts: '狀態計數',
    source: '來源',
    warnings: '警告',
    missingReasons: '缺失原因',
    qualityScore: '質量分',
    limitations: '資料限制',
    newsResultCount: '新聞結果數',
    triggerSource: '觸發來源',
    qualityLevel: {
      good: '良好',
      usable: '可用',
      limited: '受限',
      poor: '較差',
    },
    status: {
      available: '可用',
      missing: '缺失',
      not_supported: '不支援',
      fallback: '備援可用',
      stale: '過期',
      estimated: '估算',
      partial: '部分可用',
      fetch_failed: '抓取失敗',
    },
  },
  zh_TW: {
    eyebrow: '資料上下文',
    title: '輸入資料塊',
    counts: '狀態計數',
    source: '來源',
    warnings: '警告',
    missingReasons: '缺失原因',
    qualityScore: '品質分',
    limitations: '資料限制',
    newsResultCount: '新聞結果數',
    triggerSource: '觸發來源',
    qualityLevel: {
      good: '良好',
      usable: '可用',
      limited: '受限',
      poor: '較差',
    },
    status: {
      available: '可用',
      missing: '缺失',
      not_supported: '不支援',
      fallback: '備援可用',
      stale: '過期',
      estimated: '估算',
      partial: '部分可用',
      fetch_failed: '擷取失敗',
    },
  },
  en: {
    eyebrow: 'DATA CONTEXT',
    title: 'Input Blocks',
    counts: 'Status Counts',
    source: 'Source',
    warnings: 'Warnings',
    missingReasons: 'Missing Reasons',
    qualityScore: 'Quality',
    limitations: 'Data Limitations',
    newsResultCount: 'News Results',
    triggerSource: 'Trigger',
    qualityLevel: {
      good: 'Good',
      usable: 'Usable',
      limited: 'Limited',
      poor: 'Poor',
    },
    status: {
      available: 'Available',
      missing: 'Missing',
      not_supported: 'Not supported',
      fallback: 'Fallback available',
      stale: 'Stale',
      estimated: 'Estimated',
      partial: 'Partial',
      fetch_failed: 'Fetch failed',
    },
  },
} as const;

const REASON_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    news_context_missing: '本次分析未取得新聞資料',
    news_provider_timeout: '新聞服務暫時不可用',
    chip_distribution_missing: '此市場暫不支援籌碼資料',
    fundamentals_not_supported: '此資料源暫不支援基本面資料',
    fundamental_pipeline_failed: '基本面資料暫時無法取得',
    realtime_quote_missing: '即時行情未取得可用資料',
    realtime_provider_fallback: '即時行情部分降級，但已取得可用替代資料',
    intraday_realtime_overlay: '盤中資料可能不完整，已以可用資料補足',
  },
  zh_TW: {
    news_context_missing: '本次分析未取得新聞資料',
    news_provider_timeout: '新聞服務暫時不可用',
    chip_distribution_missing: '此市場暫不支援籌碼資料',
    fundamentals_not_supported: '此資料源暫不支援基本面資料',
    fundamental_pipeline_failed: '基本面資料暫時無法取得',
    realtime_quote_missing: '即時行情未取得可用資料',
    realtime_provider_fallback: '即時行情部分降級，但已取得可用替代資料',
    intraday_realtime_overlay: '盤中資料可能不完整，已以可用資料補足',
  },
  en: {
    news_context_missing: 'News data was not retrieved for this analysis',
    news_provider_timeout: 'News service is temporarily unavailable',
    chip_distribution_missing: 'Chip distribution data is not supported for this market',
    fundamentals_not_supported: 'Fundamentals are not supported by this data source',
    fundamental_pipeline_failed: 'Fundamentals are temporarily unavailable',
    realtime_quote_missing: 'No usable realtime quote was retrieved for this analysis',
    realtime_provider_fallback: 'Realtime quote is partially degraded, but usable fallback data was retrieved',
    intraday_realtime_overlay: 'Intraday data may be incomplete and was supplemented with available data',
  },
};

const SOURCE_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    fallback: '備援資料',
    'storage.get_analysis_context': '已保存報告資料',
    realtime_quote: '即時行情',
    api: '手動/API 觸發',
    mock_quote: '其他資料來源',
    cached_quote: '快取行情',
    fundamental_cache: '基本面快取',
    fundamental_pipeline: '基本面資料',
    YfinanceFetcher: 'Yahoo Finance / yfinance',
  },
  zh_TW: {
    fallback: '備援資料',
    'storage.get_analysis_context': '已保存報告資料',
    realtime_quote: '即時行情',
    api: '手動/API 觸發',
    mock_quote: '其他資料來源',
    cached_quote: '快取行情',
    fundamental_cache: '基本面快取',
    fundamental_pipeline: '基本面資料',
    YfinanceFetcher: 'Yahoo Finance / yfinance',
  },
  en: {
    fallback: 'Fallback data',
    'storage.get_analysis_context': 'Saved report data',
    realtime_quote: 'Realtime quote',
    api: 'Manual/API',
    mock_quote: 'Other data source',
    cached_quote: 'Cached quote',
    fundamental_cache: 'Fundamental cache',
    fundamental_pipeline: 'Fundamental data',
    YfinanceFetcher: 'Yahoo Finance / yfinance',
  },
};

const STATUS_ORDER: AnalysisContextPackBlockStatus[] = [
  'available',
  'missing',
  'fetch_failed',
  'not_supported',
  'fallback',
  'stale',
  'estimated',
  'partial',
];

const getCount = (
  overview: AnalysisContextPackOverview,
  status: AnalysisContextPackBlockStatus,
): number => {
  if (status === 'not_supported') {
    return overview.counts.notSupported || 0;
  }
  if (status === 'fetch_failed') {
    return overview.counts.fetchFailed || 0;
  }
  return overview.counts[status] || 0;
};

const formatLimitation = (
  value: string,
  language: ReportLanguage,
  text: typeof TEXT.zh | typeof TEXT.zh_TW | typeof TEXT.en,
): string => {
  const [rawKey, ...statusParts] = value.split(':');
  if (!rawKey || statusParts.length === 0) {
    return value;
  }

  const key = rawKey.trim();
  const status = statusParts.join(':').trim();
  if (!key || !status) {
    return value;
  }

  const label = BLOCK_LABELS[language][key] || key;
  const statusLabel = (text.status as Record<string, string>)[status] || status;
  return language === 'en' ? `${label}: ${statusLabel}` : `${label}：${statusLabel}`;
};

const formatReason = (value: string, language: ReportLanguage): string => {
  const trimmed = (value || '').trim();
  if (!trimmed) {
    return trimmed;
  }
  const [rawKey, ...details] = trimmed.split(':');
  const key = rawKey.trim();
  const label = REASON_LABELS[language][key];
  if (!label) {
    return trimmed;
  }
  const suffix = details.join(':').trim();
  return suffix ? `${label} (${suffix})` : label;
};

const formatReasons = (values: string[] | undefined, language: ReportLanguage): string[] =>
  values?.map((item) => formatReason(item, language)).filter(Boolean) || [];

const sourceLabel = (value: string | null | undefined, language: ReportLanguage): string | null => {
  const text = value?.trim();
  if (!text) return null;
  return SOURCE_LABELS[language][text] || text;
};

const isTwUsMarket = (overview: AnalysisContextPackOverview): boolean => {
  const market = (overview.subject.market || '').trim().toLowerCase();
  const code = overview.subject.code.trim();
  return market === 'tw' || market === 'us' || /^[0-9]{4,6}[a-z]?$/i.test(code) || /^[A-Z]{1,5}$/.test(code);
};

const componentByKey = (
  summary: RunDiagnosticSummary | null | undefined,
  key: string,
): RunDiagnosticComponent | null => (
  Object.values(summary?.components || {}).find((component) => component.key === key) || null
);

const numberDetail = (component: RunDiagnosticComponent | null, ...keys: string[]): number => {
  for (const key of keys) {
    const value = component?.details?.[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return 0;
};

const stringDetail = (component: RunDiagnosticComponent | null, ...keys: string[]): string | null => {
  for (const key of keys) {
    const value = component?.details?.[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
};

const normalizeOverview = (
  overview: AnalysisContextPackOverview,
  diagnosticSummary: RunDiagnosticSummary | null | undefined,
  persistedNewsCount = 0,
): AnalysisContextPackOverview => {
  const twUs = isTwUsMarket(overview);
  const quoteDiagnostic = componentByKey(diagnosticSummary, 'realtime_quote');
  const newsDiagnostic = componentByKey(diagnosticSummary, 'news');
  const newsResultCount = Math.max(
    overview.metadata.newsResultCount || 0,
    persistedNewsCount,
    numberDetail(newsDiagnostic, 'resultCount', 'result_count'),
  );

  const blocks = overview.blocks
    .filter((block) => !(twUs && block.key === 'chip'))
    .map((block) => {
      if (block.key === 'quote' && quoteDiagnostic) {
        const finalQuoteStatus = stringDetail(quoteDiagnostic, 'finalQuoteStatus', 'final_quote_status');
        const quoteSource = sourceLabel(
          stringDetail(quoteDiagnostic, 'sourceLabel', 'source_label', 'provider') || block.source,
          'zh_TW',
        );
        if (quoteDiagnostic.status === 'ok') {
          return {
            ...block,
            status: 'available' as AnalysisContextPackBlockStatus,
            source: quoteSource || block.source,
            warnings: block.warnings || [],
            missingReasons: [],
          };
        }
        if (quoteDiagnostic.status === 'degraded') {
          return {
            ...block,
            status: 'fallback' as AnalysisContextPackBlockStatus,
            source: quoteSource || block.source || '',
            warnings: [],
            missingReasons: [],
          };
        }
        if (quoteDiagnostic.status === 'failed' || finalQuoteStatus === 'missing') {
          return {
            ...block,
            status: 'missing' as AnalysisContextPackBlockStatus,
            source: null,
            warnings: [],
            missingReasons: ['realtime_quote_missing'],
          };
        }
      }
      if (block.key === 'news' && newsResultCount > 0) {
        return {
          ...block,
          status: 'available' as AnalysisContextPackBlockStatus,
          missingReasons: [],
        };
      }
      return block;
    });

  const counts = {
    available: 0,
    missing: 0,
    notSupported: 0,
    fallback: 0,
    stale: 0,
    estimated: 0,
    partial: 0,
    fetchFailed: 0,
  };
  blocks.forEach((block) => {
    if (block.status === 'not_supported') counts.notSupported += 1;
    else if (block.status === 'fetch_failed') counts.fetchFailed += 1;
    else counts[block.status] += 1;
  });

  const normalizedStatusByKey = Object.fromEntries(blocks.map((block) => [block.key, block.status]));

  return {
    ...overview,
    blocks,
    counts,
    dataQuality: overview.dataQuality ? {
      ...overview.dataQuality,
      blockScores: Object.fromEntries(
        Object.entries(overview.dataQuality.blockScores || {}).filter(([key]) => !(twUs && key === 'chip')),
      ),
      limitations: (overview.dataQuality.limitations || []).filter((item) => {
        const [key, ...statusParts] = item.split(':');
        const normalizedStatus = normalizedStatusByKey[key.trim()];
        if (twUs && key.trim() === 'chip') return false;
        return !normalizedStatus || normalizedStatus === statusParts.join(':').trim();
      }),
    } : overview.dataQuality,
    metadata: {
      ...overview.metadata,
      newsResultCount,
    },
  };
};

export const AnalysisContextSummary: React.FC<AnalysisContextSummaryProps> = ({
  overview,
  diagnosticSummary,
  recordId,
  language = 'zh_TW',
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = TEXT[reportLanguage];
  const [historyDiagnostics, setHistoryDiagnostics] = useState<RunDiagnosticSummary | null>(null);
  const [historyNewsCount, setHistoryNewsCount] = useState(0);

  useEffect(() => {
    if (!recordId) return undefined;
    let active = true;
    if (!diagnosticSummary) {
      void historyApi.getDiagnostics(recordId)
        .then((summary) => {
          if (active) setHistoryDiagnostics(summary);
        })
        .catch(() => {});
    }
    void historyApi.getNews(recordId, 1)
      .then((news) => {
        if (active) setHistoryNewsCount(news.total || news.items?.length || 0);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [diagnosticSummary, recordId]);

  if (!overview || !overview.blocks?.length) {
    return null;
  }
  const finalOverview = normalizeOverview(
    overview,
    diagnosticSummary ?? historyDiagnostics,
    historyNewsCount,
  );

  const visibleCounts = STATUS_ORDER
    .map((status) => ({ status, value: getCount(finalOverview, status) }))
    .filter((item) => item.value > 0);
  const summaryCounts = STATUS_ORDER
    .map((status) => ({ status, value: getCount(finalOverview, status) }))
    .filter((item) => item.status === 'available' || item.status === 'missing' || item.value > 0);
  const metadataItems = [
    typeof finalOverview.metadata?.newsResultCount === 'number'
      ? `${text.newsResultCount}: ${finalOverview.metadata.newsResultCount}`
      : null,
  ].filter((item): item is string => Boolean(item));
  const triggerSource = sourceLabel(finalOverview.metadata?.triggerSource, reportLanguage);
  const quality = finalOverview.dataQuality;
  const qualityLevel = quality?.level || undefined;
  const qualityStyle = qualityLevel ? QUALITY_STYLE[qualityLevel] : undefined;
  const qualityLabel = qualityLevel ? text.qualityLevel[qualityLevel] : undefined;
  const limitations = quality?.limitations?.map((item) => formatLimitation(item, reportLanguage, text)) || [];
  const overviewWarnings = formatReasons(finalOverview.warnings, reportLanguage);

  return (
    <Card variant="bordered" padding="none" className="home-panel-card">
      <details data-testid="analysis-context-summary" className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan/10 text-cyan">
              <Database className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="label-uppercase">{text.eyebrow}</span>
              <span className="mt-0.5 block truncate text-base font-semibold text-foreground">
                {text.title}
              </span>
            </span>
          </div>
          <span className="flex min-w-0 flex-wrap items-center justify-end gap-2">
            {typeof quality?.overallScore === 'number' ? (
              <Badge variant={qualityStyle?.variant || 'default'} className="gap-1.5 shadow-none">
                {qualityStyle ? <StatusDot tone={qualityStyle.tone} className="h-1.5 w-1.5" /> : null}
                {text.qualityScore} {quality.overallScore}/100{qualityLabel ? ` ${qualityLabel}` : ''}
              </Badge>
            ) : null}
            {summaryCounts.map(({ status, value }) => {
              const style = STATUS_STYLE[status];
              return (
                <Badge key={status} variant={style.variant} className="gap-1.5 shadow-none">
                  <StatusDot tone={style.tone} className="h-1.5 w-1.5" />
                  {text.status[status]} {value}
                </Badge>
              );
            })}
            {triggerSource ? (
              <span className="home-accent-chip px-2 py-0.5 text-xs text-muted-text">
                {text.triggerSource}: {triggerSource}
              </span>
            ) : null}
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-text transition-transform group-open:rotate-180" aria-hidden="true" />
          </span>
        </summary>

        <div className="home-divider border-t px-4 pb-4 pt-3">
          <DashboardPanelHeader
            eyebrow={text.eyebrow}
            title={text.title}
            leading={(
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan/10 text-cyan">
                <Database className="h-4 w-4" aria-hidden="true" />
              </span>
            )}
            actions={metadataItems.length > 0 || typeof quality?.overallScore === 'number' ? (
              <div className="hidden flex-wrap justify-end gap-2 text-xs text-muted-text md:flex">
                {typeof quality?.overallScore === 'number' ? (
                  <span className="home-accent-chip px-2 py-0.5">
                    {text.qualityScore}: {quality.overallScore}/100{qualityLabel ? ` ${qualityLabel}` : ''}
                  </span>
                ) : null}
                {metadataItems.map((item) => (
                  <span key={item} className="home-accent-chip px-2 py-0.5">
                    {item}
                  </span>
                ))}
              </div>
            ) : undefined}
          />

          {visibleCounts.length > 0 ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="label-uppercase">{text.counts}</span>
              {visibleCounts.map(({ status, value }) => {
                const style = STATUS_STYLE[status];
                return (
                  <Badge key={status} variant={style.variant} className="gap-1.5 shadow-none">
                    <StatusDot tone={style.tone} className="h-1.5 w-1.5" />
                    {text.status[status]} {value}
                  </Badge>
                );
              })}
            </div>
          ) : null}

          {limitations.length ? (
            <div className="mb-3 home-subpanel p-3 text-xs leading-5 text-muted-text">
              <span className="font-medium text-foreground">{text.limitations}: </span>
              {limitations.join(', ')}
            </div>
          ) : null}

          {overviewWarnings.length ? (
            <div className="mb-3 home-subpanel p-3 text-xs leading-5 text-warning">
              <span className="font-medium">{text.warnings}: </span>
              {overviewWarnings.join(', ')}
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {finalOverview.blocks.map((block) => {
              const style = STATUS_STYLE[block.status] || STATUS_STYLE.missing;
              const blockWarnings = formatReasons(block.warnings, reportLanguage);
              const missingReasons = formatReasons(block.missingReasons, reportLanguage);
              const blockSource = sourceLabel(block.source, reportLanguage);
              return (
                <div key={block.key} className="home-subpanel p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{block.label}</p>
                      {blockSource ? (
                        <p className="mt-1 truncate text-xs text-secondary-text">
                          {text.source}: {blockSource}
                        </p>
                      ) : null}
                    </div>
                    <Badge variant={style.variant} className="shrink-0 gap-1.5 shadow-none">
                      <StatusDot tone={style.tone} className="h-1.5 w-1.5" />
                      {text.status[block.status] || block.status}
                    </Badge>
                  </div>

                  {blockWarnings.length ? (
                    <p className="mt-2 text-xs leading-5 text-warning">
                      {text.warnings}: {blockWarnings.join(', ')}
                    </p>
                  ) : null}
                  {missingReasons.length ? (
                    <p className="mt-2 text-xs leading-5 text-muted-text">
                      {text.missingReasons}: {missingReasons.join(', ')}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>

          {metadataItems.length > 0 || typeof quality?.overallScore === 'number' ? (
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-text md:hidden">
              {typeof quality?.overallScore === 'number' ? (
                <span className="home-accent-chip px-2 py-0.5">
                  {text.qualityScore}: {quality.overallScore}/100{qualityLabel ? ` ${qualityLabel}` : ''}
                </span>
              ) : null}
              {metadataItems.map((item) => (
                <span key={item} className="home-accent-chip px-2 py-0.5">
                  {item}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </details>
    </Card>
  );
};

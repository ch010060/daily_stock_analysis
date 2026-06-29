import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, ExternalLink, Newspaper, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { finewsApi, type FinewsSectionKey, type FinewsSnapshot } from '../api/finews';
import { Button, InlineAlert } from '../components/common';

const MAIN_SECTION_CONFIG: Array<{ key: FinewsSectionKey; title: string }> = [
  { key: 'afterMarketSummary', title: '盤後總結' },
  { key: 'majorNews', title: '主要新聞' },
];

const MARKET_SECTION_CONFIG: Array<{ key: FinewsSectionKey; title: string }> = [
  { key: 'marketTemperature', title: '市場溫度' },
  { key: 'majorIndices', title: '主要指數' },
  { key: 'majorStocks', title: '主要股票' },
  { key: 'treasuryYields', title: '美債利率' },
  { key: 'fx', title: '主要匯率' },
];

type FinewsExternalLink = FinewsSnapshot['externalLinks'][number];

type FinewsNewsStory = {
  title: string;
  meta?: string;
  body?: string;
  url?: string;
};

type FinewsMarketRow = {
  label: string;
  symbol?: string;
  value?: string;
  change?: string;
  url?: string;
};

type MarketTone = 'gain' | 'loss' | 'neutral';

const MARKET_TONE_CLASS: Record<MarketTone, string> = {
  gain: 'text-[var(--finews-gain)]',
  loss: 'text-[var(--finews-loss)]',
  neutral: 'text-[var(--finews-muted)]',
};

const hasSnapshotContent = (snapshot: FinewsSnapshot | null): boolean => {
  if (!snapshot) return false;
  return Object.values(snapshot.sections || {}).some((items) => items.length > 0);
};

const formatMetaValue = (value?: string | null): string => value || '未提供';

const chunkItems = <T,>(items: T[], size: number): T[][] => {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
};

const isNewsMetaLine = (line?: string): boolean => {
  if (!line) return false;
  return /·|20\d{2}|Yahoo|Reuters|CNBC|MarketWatch|Bloomberg|Investing|Barron|Financial Times/i.test(line);
};

const buildNewsStories = (items: string[], externalLinks: FinewsExternalLink[]): FinewsNewsStory[] => {
  const linkByTitle = new Map(externalLinks.map((link) => [link.title, link.url]));
  const stories: FinewsNewsStory[] = [];

  for (let index = 0; index < items.length;) {
    const title = items[index];
    const nextLine = items[index + 1];
    const thirdLine = items[index + 2];
    const hasMeta = isNewsMetaLine(nextLine);

    if (!title) {
      index += 1;
      continue;
    }

    stories.push({
      title,
      meta: hasMeta ? nextLine : undefined,
      body: hasMeta ? thirdLine : nextLine,
      url: linkByTitle.get(title),
    });
    index += hasMeta ? 3 : 2;
  }

  return stories;
};

const linkMatchesItem = (link: FinewsExternalLink, item: string): boolean => {
  const title = link.title.trim().toLowerCase();
  const normalizedItem = item.trim().toLowerCase();
  if (!title || !normalizedItem) return false;
  if (title === normalizedItem || title.includes(normalizedItem) || normalizedItem.includes(title)) return true;
  try {
    const parsed = new URL(link.url);
    const haystack = `${parsed.pathname} ${parsed.search} ${parsed.hash}`.toLowerCase();
    const escaped = normalizedItem.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`(^|[^a-z0-9^.-])${escaped}([^a-z0-9.-]|$)`).test(haystack);
  } catch {
    return false;
  }
};

const fallbackSectionLinks = (
  items: string[],
  externalLinks: FinewsExternalLink[],
): FinewsExternalLink[] => (
  externalLinks.filter((link) => items.some((item) => linkMatchesItem(link, item)))
);

const buildMarketRows = (items: string[], externalLinks: FinewsExternalLink[]): FinewsMarketRow[] => {
  const linkByTitle = new Map(externalLinks.map((link) => [link.title, link.url]));
  return chunkItems(items, 4).map((chunk) => ({
    label: chunk[0] || '',
    symbol: chunk[1],
    value: chunk[2],
    change: chunk[3],
    url: chunk[1] ? linkByTitle.get(chunk[1]) : undefined,
  })).filter((row) => row.label);
};

const marketTone = (value?: string): MarketTone => {
  if (!value) return 'neutral';
  if (/[+＋]/.test(value)) return 'gain';
  if (/[-−]/.test(value)) return 'loss';
  return 'neutral';
};

const metricProgress = (row: FinewsMarketRow): number => {
  const match = `${row.symbol || ''} ${row.value || ''}`.match(/-?\d+(?:\.\d+)?/);
  if (!match) return 0;
  const value = Number.parseFloat(match[0]);
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value));
};

const isCalmMetric = (label: string): boolean => /恐慌|貪婪|fear|greed/i.test(label);

const sectionItems = (snapshot: FinewsSnapshot | null, key: FinewsSectionKey): string[] => (
  snapshot?.sections?.[key] || []
);

const sectionLinks = (snapshot: FinewsSnapshot | null, key: FinewsSectionKey): FinewsExternalLink[] => (
  snapshot?.sectionLinks?.[key]?.length
    ? snapshot.sectionLinks[key]
    : fallbackSectionLinks(sectionItems(snapshot, key), snapshot?.externalLinks || [])
);

const FinewsMasthead: React.FC<{
  snapshot: FinewsSnapshot | null;
  isLoading: boolean;
  onRefresh: () => void;
  onBack: () => void;
}> = ({ snapshot, isLoading, onRefresh, onBack }) => (
  <header
    data-testid="finews-masthead"
    className="border-y-[5px] border-[var(--finews-ink)] px-3 py-3 sm:px-5 print:border-y-2 print:px-0"
  >
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[color:var(--finews-rule)] pb-2 text-[11px] font-semibold tracking-[0.14em] text-[var(--finews-muted)]">
      <span>FiNews</span>
      <span>外部公開資訊快照</span>
      <a
        href="https://finews.elsetech.app/"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[var(--finews-risk)] hover:underline"
      >
        原始來源
        <ExternalLink className="h-3 w-3" aria-hidden="true" />
      </a>
      <div className="no-print flex flex-wrap items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          返回首頁
        </Button>
        <Button type="button" variant="secondary" size="sm" isLoading={isLoading} onClick={onRefresh}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          重新整理
        </Button>
      </div>
    </div>
    <div className="grid gap-3 py-3 md:grid-cols-[minmax(0,1fr)_minmax(280px,0.55fr)] md:items-end">
      <div>
        <p className="mb-1 text-xs font-semibold tracking-[0.18em] text-[var(--finews-muted)]">DSA READER EDITION</p>
        <h1 className="font-serif text-5xl font-black leading-none tracking-[-0.07em] text-[var(--finews-ink)] sm:text-6xl lg:text-7xl">
          美股日報
        </h1>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs leading-5 text-[var(--finews-muted)] md:text-right">
        <dt>報告日期</dt>
        <dd className="font-semibold text-[var(--finews-ink)]">{formatMetaValue(snapshot?.reportDate)}</dd>
        <dt>來源更新</dt>
        <dd className="font-semibold text-[var(--finews-ink)]">{formatMetaValue(snapshot?.sourceUpdatedAt)}</dd>
        <dt>擷取時間</dt>
        <dd className="font-semibold text-[var(--finews-ink)]">{formatMetaValue(snapshot?.fetchedAt)}</dd>
        <dt>語言</dt>
        <dd className="font-semibold text-[var(--finews-ink)]">zh-CN / zh-TW</dd>
      </dl>
    </div>
  </header>
);

const FinewsSummarySection: React.FC<{ items: string[] }> = ({ items }) => (
  <section data-testid="finews-summary-section" className="break-inside-avoid border-b-2 border-[var(--finews-ink)] pb-4">
    <h2 className="font-serif text-2xl font-black tracking-[-0.03em] text-[var(--finews-ink)]">盤後總結</h2>
    <div className="mt-3 grid gap-x-4 gap-y-2 md:grid-cols-2">
      {items.map((item, index) => (
        <article key={`summary-${index}`} className="grid grid-cols-[2rem_1fr] gap-2 border-t border-[color:var(--finews-rule)] pt-2">
          <span className="font-mono text-[11px] font-bold text-[var(--finews-risk)]">{String(index + 1).padStart(2, '0')}</span>
          <p className="text-sm leading-6 text-[var(--finews-body)]">{item}</p>
        </article>
      ))}
    </div>
  </section>
);

const FinewsNewsSection: React.FC<{
  stories: FinewsNewsStory[];
}> = ({ stories }) => (
    <section data-testid="finews-news-section" className="pt-4">
      <h2 className="font-serif text-2xl font-black tracking-[-0.03em] text-[var(--finews-ink)]">主要新聞</h2>
      <div className="mt-3 columns-1 gap-5 md:columns-2">
        {stories.map((story, index) => (
          <article
            key={`news-${story.title}-${index}`}
            className="mb-4 break-inside-avoid border-t border-[color:var(--finews-rule)] pt-2"
          >
            {story.url ? (
              <a
                href={story.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group inline-flex items-start gap-1.5 font-serif text-lg font-bold leading-6 text-[var(--finews-ink)] hover:text-[var(--finews-risk)]"
              >
                <span>{story.title}</span>
                <ExternalLink className="mt-1 h-3.5 w-3.5 flex-shrink-0 opacity-60 group-hover:opacity-100" aria-hidden="true" />
              </a>
            ) : (
              <h3 className="font-serif text-lg font-bold leading-6 text-[var(--finews-ink)]">{story.title}</h3>
            )}
            {story.meta ? <p className="mt-1 text-[11px] font-semibold text-[var(--finews-muted)]">{story.meta}</p> : null}
            {story.body ? <p className="mt-1 text-sm leading-6 text-[var(--finews-body)]">{story.body}</p> : null}
          </article>
        ))}
      </div>

    </section>
);

const FinewsMetricSidebar: React.FC<{
  title: string;
  items: string[];
  links: FinewsExternalLink[];
}> = ({ title, items, links }) => {
  const rows = buildMarketRows(items, links);

  if (rows.length === 0) return null;

  if (title === '市場溫度') {
    return (
      <section className="break-inside-avoid border-y-4 border-double border-[var(--finews-ink)] py-3" data-testid="finews-market-temperature">
        <h2 className="font-serif text-xl font-black tracking-[-0.03em] text-[var(--finews-ink)]">{title}</h2>
        <div className="mt-1 border-t border-[color:var(--finews-rule)]">
          {rows.map((row, index) => {
            const calm = isCalmMetric(row.label);
            const metricColor = calm ? 'text-[var(--finews-calm)]' : 'text-[var(--finews-risk)]';
            const progressColor = calm ? 'bg-[var(--finews-calm)]' : 'bg-[var(--finews-risk)]';
            const metric = (
              <div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  {row.url ? (
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`font-mono text-3xl font-black leading-none tracking-[-0.05em] hover:underline ${metricColor}`}
                    >
                      {row.symbol || row.value}
                    </a>
                  ) : (
                    <p className={`font-mono text-3xl font-black leading-none tracking-[-0.05em] ${metricColor}`}>
                      {row.symbol || row.value}
                    </p>
                  )}
                  {row.value && row.symbol ? <p className="text-[11px] font-semibold text-[var(--finews-muted)]">{row.value}</p> : null}
                </div>
                <div className="mt-2 h-1.5 bg-[var(--finews-track)]" data-testid="finews-temperature-track">
                  <div
                    data-testid="finews-temperature-progress"
                    className={`h-full ${progressColor}`}
                    style={{ width: `${metricProgress(row)}%` }}
                  />
                </div>
              </div>
            );

            return row.change ? (
              <details
                key={`${title}-${row.label}-${index}`}
                className="break-inside-avoid border-b border-[color:var(--finews-rule)] py-3 text-xs leading-5 text-[var(--finews-muted)]"
              >
                <summary
                  aria-label="查看市場溫度說明"
                  className="cursor-pointer list-none [&::-webkit-details-marker]:hidden"
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="text-xs font-black tracking-[0.06em] text-[var(--finews-muted)]">{row.label}</span>
                    <span
                      aria-hidden="true"
                      className="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border border-[color:var(--finews-rule)] text-[11px] font-black italic text-[var(--finews-risk)] hover:bg-[var(--finews-soft)]"
                    >
                      i
                    </span>
                  </span>
                  {metric}
                </summary>
                <p className="mt-2 border-l-2 border-[color:var(--finews-rule)] py-1 pl-3 text-[11px] leading-5 text-[var(--finews-body)]">
                  {row.change}
                </p>
              </details>
            ) : (
              <div key={`${title}-${row.label}-${index}`} className="break-inside-avoid border-b border-[color:var(--finews-rule)] py-3">
                <span className="text-xs font-black tracking-[0.06em] text-[var(--finews-muted)]">{row.label}</span>
                {metric}
              </div>
            );
          })}
        </div>
      </section>
    );
  }

  return (
    <section className="break-inside-avoid border-t-2 border-[var(--finews-ink)] pt-3">
      <h2 className="font-serif text-xl font-black tracking-[-0.03em] text-[var(--finews-ink)]">{title}</h2>
      <div className="mt-2 divide-y divide-[color:var(--finews-rule)] text-xs">
        {rows.map((row, index) => (
          <div key={`${title}-${row.label}-${index}`} data-tone={marketTone(row.change)} className="grid grid-cols-[minmax(0,1.15fr)_0.85fr] gap-2 py-1.5">
            <div className="min-w-0">
              <p className="truncate font-bold text-[var(--finews-ink)]">{row.label}</p>
              {row.symbol ? (
                row.url ? (
                  <a
                    href={row.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncate font-mono text-[11px] text-[var(--finews-risk)] hover:underline"
                  >
                    {row.symbol}
                  </a>
                ) : (
                  <p className="truncate font-mono text-[11px] text-[var(--finews-muted)]">{row.symbol}</p>
                )
              ) : null}
            </div>
            <div className="text-right">
              {row.value ? <p className="font-mono font-black text-[var(--finews-ink)]">{row.value}</p> : null}
              {row.change ? <p className={`font-mono text-[11px] ${MARKET_TONE_CLASS[marketTone(row.change)]}`}>{row.change}</p> : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

const FiNewsPage: React.FC = () => {
  const navigate = useNavigate();
  const [snapshot, setSnapshot] = useState<FinewsSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await finewsApi.getLatest();
      setSnapshot(result);
      if (result.fetchError && !hasSnapshotContent(result)) {
        setError('FiNews 目前無法載入，請稍後再試。');
      }
    } catch {
      setError('FiNews 目前無法載入，請稍後再試。');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  const mainSections = useMemo(() => {
    if (!snapshot) return [];
    return MAIN_SECTION_CONFIG.map((section) => ({
      ...section,
      items: sectionItems(snapshot, section.key),
    })).filter((section) => section.items.length > 0);
  }, [snapshot]);

  const marketSections = useMemo(() => {
    if (!snapshot) return [];
    return MARKET_SECTION_CONFIG.map((section) => ({
      ...section,
      items: sectionItems(snapshot, section.key),
      links: sectionLinks(snapshot, section.key),
    })).filter((section) => section.items.length > 0);
  }, [snapshot]);

  const majorNewsItems = useMemo(() => sectionItems(snapshot, 'majorNews'), [snapshot]);
  const newsStories = useMemo(
    () => buildNewsStories(majorNewsItems, sectionLinks(snapshot, 'majorNews')),
    [majorNewsItems, snapshot],
  );

  return (
    <main className="min-h-full bg-[var(--finews-app-bg)] px-3 py-4 text-[var(--finews-ink)] [--finews-app-bg:#ebe3d1] [--finews-body:#33271d] [--finews-calm:#2f7d48] [--finews-gain:#2f7d48] [--finews-ink:#211811] [--finews-loss:#a5452d] [--finews-muted:#6c5a46] [--finews-paper:#fbf7eb] [--finews-risk:#a5452d] [--finews-rule:rgba(33,24,17,0.28)] [--finews-soft:rgba(33,24,17,0.07)] [--finews-track:rgba(33,24,17,0.14)] sm:px-5 lg:px-8 dark:[--finews-app-bg:#17140f] dark:[--finews-body:#e8dcc8] dark:[--finews-calm:#7ccf8c] dark:[--finews-gain:#7ccf8c] dark:[--finews-ink:#f4ead8] dark:[--finews-loss:#f07c62] dark:[--finews-muted:#c9b99d] dark:[--finews-paper:#231f17] dark:[--finews-risk:#f07c62] dark:[--finews-rule:rgba(244,234,216,0.24)] dark:[--finews-soft:rgba(244,234,216,0.08)] dark:[--finews-track:rgba(244,234,216,0.16)] print:bg-white print:px-0 print:py-0" data-testid="finews-paper-shell">
      <article className="mx-auto max-w-6xl border border-[var(--finews-ink)] bg-[var(--finews-paper)] shadow-[0_18px_50px_rgba(65,43,24,0.18)] print:max-w-none print:border-0 print:bg-white print:shadow-none">
        <FinewsMasthead
          snapshot={snapshot}
          isLoading={isLoading}
          onRefresh={() => void loadSnapshot()}
          onBack={() => navigate('/')}
        />

        <div className="px-3 py-3 sm:px-5 print:px-0">
          {snapshot?.stale ? (
            <InlineAlert
              variant="warning"
              title="顯示舊快照"
              message="FiNews 最新內容暫時無法擷取，目前顯示上一份成功保存的本地快照。"
            />
          ) : null}

          {error ? (
            <InlineAlert variant="danger" title="美股日報載入失敗" message={error} />
          ) : null}

          {isLoading && !snapshot ? (
            <div className="grid gap-3 border-y-2 border-[var(--finews-ink)] py-4 md:grid-cols-[1.5fr_0.8fr]">
              <div className="space-y-2">
                <div className="h-4 w-2/3 animate-pulse bg-[var(--finews-track)]" />
                <div className="h-4 w-full animate-pulse bg-[var(--finews-track)]" />
                <div className="h-4 w-5/6 animate-pulse bg-[var(--finews-track)]" />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-full animate-pulse bg-[var(--finews-track)]" />
                <div className="h-4 w-3/4 animate-pulse bg-[var(--finews-track)]" />
              </div>
            </div>
          ) : null}

          {!isLoading && snapshot && !hasSnapshotContent(snapshot) ? (
            <div className="flex items-start gap-3 border-y-2 border-[var(--finews-risk)] bg-[var(--finews-soft)] p-4 text-sm text-[var(--finews-body)]">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-[var(--finews-risk)]" aria-hidden="true" />
              <div>
                <p className="font-semibold text-[var(--finews-ink)]">目前沒有可顯示的 FiNews 快照內容</p>
                <p className="mt-1">請稍後再試；Home page 和市場概覽功能不受影響。</p>
              </div>
            </div>
          ) : null}

          {mainSections.length > 0 || marketSections.length > 0 ? (
            <div
              data-testid="finews-newspaper-grid"
              className="grid gap-5 border-t-2 border-[var(--finews-ink)] pt-4 lg:grid-cols-[minmax(0,1.62fr)_minmax(300px,0.86fr)] print:grid-cols-[minmax(0,1.62fr)_minmax(290px,0.86fr)]"
            >
              <div data-testid="finews-main-column" className="min-w-0">
                {sectionItems(snapshot, 'afterMarketSummary').length > 0 ? (
                  <FinewsSummarySection items={sectionItems(snapshot, 'afterMarketSummary')} />
                ) : null}
                {newsStories.length > 0 ? (
                  <FinewsNewsSection stories={newsStories} />
                ) : null}
              </div>

              <aside
                data-testid="finews-market-sidebar"
                className="space-y-4 border-t-2 border-[var(--finews-ink)] bg-[var(--finews-soft)] p-3 pt-4 lg:border-l-2 lg:border-t-0 lg:pl-4 lg:pt-0 print:border-l-2 print:border-t-0 print:bg-transparent print:pl-4 print:pt-0"
              >
                <div className="flex items-center gap-2 border-b border-[color:var(--finews-rule)] pb-2">
                  <Newspaper className="h-4 w-4 text-[var(--finews-risk)]" aria-hidden="true" />
                  <p className="text-xs font-bold tracking-[0.16em] text-[var(--finews-muted)]">MARKET TAPE</p>
                </div>
                {marketSections.map((section) => (
                  <FinewsMetricSidebar key={section.key} title={section.title} items={section.items} links={section.links} />
                ))}
              </aside>
            </div>
          ) : null}
        </div>
      </article>
    </main>
  );
};

export default FiNewsPage;

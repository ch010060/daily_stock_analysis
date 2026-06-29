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

const buildMarketRows = (items: string[]): FinewsMarketRow[] => (
  chunkItems(items, 4).map((chunk) => ({
    label: chunk[0] || '',
    symbol: chunk[1],
    value: chunk[2],
    change: chunk[3],
  })).filter((row) => row.label)
);

const sectionItems = (snapshot: FinewsSnapshot | null, key: FinewsSectionKey): string[] => (
  snapshot?.sections?.[key] || []
);

const formatLinkHost = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'external';
  }
};

const FinewsMasthead: React.FC<{
  snapshot: FinewsSnapshot | null;
  isLoading: boolean;
  onRefresh: () => void;
  onBack: () => void;
}> = ({ snapshot, isLoading, onRefresh, onBack }) => (
  <header
    data-testid="finews-masthead"
    className="border-y-[5px] border-[#211811] px-3 py-3 sm:px-5 print:border-y-2 print:px-0"
  >
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#211811]/35 pb-2 text-[11px] font-semibold tracking-[0.14em] text-[#554533]">
      <span>FiNews</span>
      <span>外部公開資訊快照</span>
      <a
        href="https://finews.elsetech.app/"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[#7a3518] hover:underline"
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
        <p className="mb-1 text-xs font-semibold tracking-[0.18em] text-[#8a6f47]">DSA READER EDITION</p>
        <h1 className="font-serif text-5xl font-black leading-none tracking-[-0.07em] text-[#211811] sm:text-6xl lg:text-7xl">
          美股日報
        </h1>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs leading-5 text-[#554533] md:text-right">
        <dt>報告日期</dt>
        <dd className="font-semibold text-[#211811]">{formatMetaValue(snapshot?.reportDate)}</dd>
        <dt>來源更新</dt>
        <dd className="font-semibold text-[#211811]">{formatMetaValue(snapshot?.sourceUpdatedAt)}</dd>
        <dt>擷取時間</dt>
        <dd className="font-semibold text-[#211811]">{formatMetaValue(snapshot?.fetchedAt)}</dd>
        <dt>語言</dt>
        <dd className="font-semibold text-[#211811]">zh-CN / zh-TW</dd>
      </dl>
    </div>
  </header>
);

const FinewsSummarySection: React.FC<{ items: string[] }> = ({ items }) => (
  <section data-testid="finews-summary-section" className="break-inside-avoid border-b-2 border-[#211811] pb-4">
    <h2 className="font-serif text-2xl font-black tracking-[-0.03em] text-[#211811]">盤後總結</h2>
    <div className="mt-3 grid gap-x-4 gap-y-2 md:grid-cols-2">
      {items.map((item, index) => (
        <article key={`summary-${index}`} className="grid grid-cols-[2rem_1fr] gap-2 border-t border-[#211811]/25 pt-2">
          <span className="font-mono text-[11px] font-bold text-[#9d4b24]">{String(index + 1).padStart(2, '0')}</span>
          <p className="text-sm leading-6 text-[#30261d]">{item}</p>
        </article>
      ))}
    </div>
  </section>
);

const FinewsNewsSection: React.FC<{
  stories: FinewsNewsStory[];
  externalLinks: FinewsExternalLink[];
}> = ({ stories, externalLinks }) => {
  const storyUrls = new Set(stories.map((story) => story.url).filter(Boolean));
  const remainingLinks = externalLinks.filter((link) => !storyUrls.has(link.url));

  return (
    <section data-testid="finews-news-section" className="pt-4">
      <h2 className="font-serif text-2xl font-black tracking-[-0.03em] text-[#211811]">主要新聞</h2>
      <div className="mt-3 columns-1 gap-5 md:columns-2">
        {stories.map((story, index) => (
          <article
            key={`news-${story.title}-${index}`}
            className="mb-4 break-inside-avoid border-t border-[#211811]/30 pt-2"
          >
            {story.url ? (
              <a
                href={story.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group inline-flex items-start gap-1.5 font-serif text-lg font-bold leading-6 text-[#211811] hover:text-[#9d4b24]"
              >
                <span>{story.title}</span>
                <ExternalLink className="mt-1 h-3.5 w-3.5 flex-shrink-0 opacity-60 group-hover:opacity-100" aria-hidden="true" />
              </a>
            ) : (
              <h3 className="font-serif text-lg font-bold leading-6 text-[#211811]">{story.title}</h3>
            )}
            {story.meta ? <p className="mt-1 text-[11px] font-semibold text-[#7b6249]">{story.meta}</p> : null}
            {story.body ? <p className="mt-1 text-sm leading-6 text-[#3b3026]">{story.body}</p> : null}
          </article>
        ))}
      </div>

      {remainingLinks.length > 0 ? (
        <div className="mt-4 break-inside-avoid border-t-2 border-[#211811] pt-3">
          <h3 className="text-xs font-bold tracking-[0.16em] text-[#7b6249]">外部來源連結</h3>
          <div className="mt-2 columns-1 gap-4 md:columns-2">
            {remainingLinks.map((link, index) => (
              <a
                key={`${link.url}-${index}`}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mb-1.5 block break-inside-avoid text-xs leading-5 text-[#7a3518] hover:underline"
              >
                {link.title}
                <span className="ml-1 text-[#7b6249]">({formatLinkHost(link.url)})</span>
              </a>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
};

const FinewsMetricSidebar: React.FC<{
  title: string;
  items: string[];
}> = ({ title, items }) => {
  const rows = buildMarketRows(items);

  if (rows.length === 0) return null;

  if (title === '市場溫度') {
    return (
      <section className="break-inside-avoid border-t-2 border-[#211811] pt-3">
        <h2 className="font-serif text-xl font-black tracking-[-0.03em] text-[#211811]">{title}</h2>
        <div className="mt-2 grid gap-2">
          {rows.map((row, index) => (
            <div key={`${title}-${row.label}-${index}`} className="border-t border-[#211811]/25 py-2">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-xs font-bold text-[#554533]">{row.label}</span>
                <span className="font-mono text-lg font-black text-[#9d4b24]">{row.symbol || row.value}</span>
              </div>
              {row.value && row.symbol ? <p className="mt-0.5 text-xs font-semibold text-[#211811]">{row.value}</p> : null}
              {row.change ? <p className="mt-1 text-xs leading-5 text-[#554533]">{row.change}</p> : null}
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="break-inside-avoid border-t-2 border-[#211811] pt-3">
      <h2 className="font-serif text-xl font-black tracking-[-0.03em] text-[#211811]">{title}</h2>
      <div className="mt-2 divide-y divide-[#211811]/20 text-xs">
        {rows.map((row, index) => (
          <div key={`${title}-${row.label}-${index}`} className="grid grid-cols-[minmax(0,1.15fr)_0.85fr] gap-2 py-1.5">
            <div className="min-w-0">
              <p className="truncate font-bold text-[#211811]">{row.label}</p>
              {row.symbol ? <p className="truncate font-mono text-[11px] text-[#7b6249]">{row.symbol}</p> : null}
            </div>
            <div className="text-right">
              {row.value ? <p className="font-mono font-black text-[#211811]">{row.value}</p> : null}
              {row.change ? <p className="font-mono text-[11px] text-[#9d4b24]">{row.change}</p> : null}
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
    })).filter((section) => section.items.length > 0);
  }, [snapshot]);

  const externalLinks = useMemo(() => snapshot?.externalLinks || [], [snapshot?.externalLinks]);
  const majorNewsItems = useMemo(() => sectionItems(snapshot, 'majorNews'), [snapshot]);
  const newsStories = useMemo(
    () => buildNewsStories(majorNewsItems, externalLinks),
    [externalLinks, majorNewsItems],
  );

  return (
    <main className="min-h-full bg-[#efe8d6] px-3 py-4 text-[#211811] sm:px-5 lg:px-8 print:bg-white print:px-0 print:py-0">
      <article className="mx-auto max-w-6xl border border-[#211811] bg-[#fbf7eb] shadow-[0_18px_50px_rgba(65,43,24,0.18)] print:max-w-none print:border-0 print:bg-white print:shadow-none">
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
            <div className="grid gap-3 border-y-2 border-[#211811] py-4 md:grid-cols-[1.5fr_0.8fr]">
              <div className="space-y-2">
                <div className="h-4 w-2/3 animate-pulse bg-[#211811]/20" />
                <div className="h-4 w-full animate-pulse bg-[#211811]/15" />
                <div className="h-4 w-5/6 animate-pulse bg-[#211811]/15" />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-full animate-pulse bg-[#211811]/15" />
                <div className="h-4 w-3/4 animate-pulse bg-[#211811]/15" />
              </div>
            </div>
          ) : null}

          {!isLoading && snapshot && !hasSnapshotContent(snapshot) ? (
            <div className="flex items-start gap-3 border-y-2 border-[#9d4b24] bg-[#9d4b24]/10 p-4 text-sm text-[#3b3026]">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-[#9d4b24]" aria-hidden="true" />
              <div>
                <p className="font-semibold text-[#211811]">目前沒有可顯示的 FiNews 快照內容</p>
                <p className="mt-1">請稍後再試；Home page 和市場概覽功能不受影響。</p>
              </div>
            </div>
          ) : null}

          {mainSections.length > 0 || marketSections.length > 0 ? (
            <div
              data-testid="finews-newspaper-grid"
              className="grid gap-5 border-t-2 border-[#211811] pt-4 lg:grid-cols-[minmax(0,1.62fr)_minmax(300px,0.86fr)] print:grid-cols-[minmax(0,1.62fr)_minmax(290px,0.86fr)]"
            >
              <div data-testid="finews-main-column" className="min-w-0">
                {sectionItems(snapshot, 'afterMarketSummary').length > 0 ? (
                  <FinewsSummarySection items={sectionItems(snapshot, 'afterMarketSummary')} />
                ) : null}
                {newsStories.length > 0 || externalLinks.length > 0 ? (
                  <FinewsNewsSection stories={newsStories} externalLinks={externalLinks} />
                ) : null}
              </div>

              <aside
                data-testid="finews-market-sidebar"
                className="space-y-4 border-t-2 border-[#211811] pt-4 lg:border-l-2 lg:border-t-0 lg:pl-4 lg:pt-0 print:border-l-2 print:border-t-0 print:pl-4 print:pt-0"
              >
                <div className="flex items-center gap-2 border-b border-[#211811]/30 pb-2">
                  <Newspaper className="h-4 w-4 text-[#9d4b24]" aria-hidden="true" />
                  <p className="text-xs font-bold tracking-[0.16em] text-[#554533]">MARKET TAPE</p>
                </div>
                {marketSections.map((section) => (
                  <FinewsMetricSidebar key={section.key} title={section.title} items={section.items} />
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

import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, ExternalLink, Newspaper, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { finewsApi, type FinewsSectionKey, type FinewsSnapshot } from '../api/finews';
import { Button, InlineAlert } from '../components/common';

const SECTION_CONFIG: Array<{ key: FinewsSectionKey; title: string }> = [
  { key: 'afterMarketSummary', title: '盤後總結' },
  { key: 'majorNews', title: '主要新聞' },
  { key: 'marketTemperature', title: '市場溫度' },
  { key: 'majorIndices', title: '主要指數' },
  { key: 'majorStocks', title: '主要股票' },
  { key: 'treasuryYields', title: '美債利率' },
  { key: 'fx', title: '主要匯率' },
];

const hasSnapshotContent = (snapshot: FinewsSnapshot | null): boolean => {
  if (!snapshot) return false;
  return Object.values(snapshot.sections || {}).some((items) => items.length > 0);
};

const formatMetaValue = (value?: string | null): string => value || '—';

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

  const visibleSections = useMemo(() => {
    if (!snapshot) return [];
    return SECTION_CONFIG.map((section) => ({
      ...section,
      items: snapshot.sections?.[section.key] || [],
    })).filter((section) => section.items.length > 0);
  }, [snapshot]);

  const externalLinks = snapshot?.externalLinks || [];

  return (
    <main className="min-h-full bg-base px-3 py-4 text-foreground sm:px-5 lg:px-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="flex flex-col gap-3 rounded-2xl border border-subtle bg-surface p-4 shadow-sm sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Newspaper className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">FiNews Snapshot</p>
                <h1 className="text-2xl font-bold text-foreground">美股日報</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => navigate('/')}>
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                返回首頁
              </Button>
              <Button type="button" variant="secondary" size="sm" isLoading={isLoading} onClick={() => void loadSnapshot()}>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                重新整理
              </Button>
            </div>
          </div>

          <div className="grid gap-3 text-sm text-secondary-text md:grid-cols-2 lg:grid-cols-4">
            <div>
              <span className="block text-xs text-muted-text">來源</span>
              <span className="font-medium text-foreground">FiNews</span>
            </div>
            <div>
              <span className="block text-xs text-muted-text">原始 URL</span>
              <a
                href="https://finews.elsetech.app/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
              >
                finews.elsetech.app
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            </div>
            <div>
              <span className="block text-xs text-muted-text">報告日期</span>
              <span className="font-medium text-foreground">{formatMetaValue(snapshot?.reportDate)}</span>
            </div>
            <div>
              <span className="block text-xs text-muted-text">來源更新時間</span>
              <span className="font-medium text-foreground">{formatMetaValue(snapshot?.sourceUpdatedAt)}</span>
            </div>
            <div>
              <span className="block text-xs text-muted-text">擷取時間</span>
              <span className="font-medium text-foreground">{formatMetaValue(snapshot?.fetchedAt)}</span>
            </div>
            <div>
              <span className="block text-xs text-muted-text">語言</span>
              <span className="font-medium text-foreground">zh-CN → zh-TW</span>
            </div>
          </div>
        </div>

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
          <div className="rounded-2xl border border-subtle bg-surface p-6 text-sm text-secondary-text">
            載入美股日報中...
          </div>
        ) : null}

        {!isLoading && snapshot && !hasSnapshotContent(snapshot) ? (
          <div className="flex items-start gap-3 rounded-2xl border border-warning/40 bg-warning/10 p-5 text-sm text-secondary-text">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-warning" aria-hidden="true" />
            <div>
              <p className="font-semibold text-foreground">目前沒有可顯示的 FiNews 快照內容</p>
              <p className="mt-1">請稍後再試；Home page 和市場概覽功能不受影響。</p>
            </div>
          </div>
        ) : null}

        {visibleSections.map((section) => (
          <section key={section.key} className="rounded-2xl border border-subtle bg-surface p-4 shadow-sm sm:p-5">
            <h2 className="text-lg font-bold text-foreground">{section.title}</h2>
            {section.key === 'majorNews' && externalLinks.length > 0 ? (
              <div className="mt-3 rounded-xl border border-subtle bg-surface-muted/60 p-3">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-text">外部來源連結</p>
                <div className="mt-2 grid gap-2">
                  {externalLinks.map((link, index) => (
                    <a
                      key={`${link.url}-${index}`}
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm font-medium text-primary hover:bg-primary/10 hover:underline"
                    >
                      <ExternalLink className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
                      <span>{link.title}</span>
                    </a>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="mt-3 space-y-2">
              {section.items.map((item, index) => (
                <p key={`${section.key}-${index}`} className="rounded-xl bg-surface-muted px-3 py-2 text-sm leading-6 text-secondary-text">
                  {item}
                </p>
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
};

export default FiNewsPage;

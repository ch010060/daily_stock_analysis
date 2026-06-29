import type React from 'react';
import type { TwDailyReportModel, TwDailyRow, TwDailyTone } from './twDailyReportAdapter';

const cx = (...classes: Array<string | undefined | false>) => classes.filter(Boolean).join(' ');

const toneClass: Record<TwDailyTone, string> = {
  gain: 'text-success',
  loss: 'text-danger',
  neutral: 'text-foreground',
  missing: 'text-muted-text',
};

const MarketRows: React.FC<{ rows: TwDailyRow[]; emptyText: string }> = ({ rows, emptyText }) => {
  if (!rows.length) {
    return <p className="py-3 text-sm text-muted-text">{emptyText}</p>;
  }

  return (
    <div className="divide-y divide-border/70">
      {rows.map((row, index) => (
        <div key={`${row.label}-${row.code ?? index}`} className="grid grid-cols-[minmax(0,1fr)_minmax(7rem,auto)] gap-3 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">{row.label}</p>
            {row.code ? <p className="font-mono text-[11px] text-muted-text">{row.code}</p> : null}
          </div>
          <p className={cx('text-right text-sm font-semibold leading-5', toneClass[row.tone])}>{row.value}</p>
        </div>
      ))}
    </div>
  );
};

const ReaderSection: React.FC<{
  title: string;
  children: React.ReactNode;
  className?: string;
}> = ({ title, children, className }) => (
  <section className={cx('border-t border-border/80 pt-4', className)}>
    <h3 className="mb-3 text-xs font-bold tracking-[0.18em] text-muted-text">{title}</h3>
    {children}
  </section>
);

export const TwDailyReportView: React.FC<{ report: TwDailyReportModel; className?: string }> = ({ report, className }) => (
  <article
    data-testid="tw-daily-reader"
    className={cx(
      'tw-daily-reader rounded-2xl border border-border/80 bg-surface/80 p-4 text-foreground shadow-sm md:p-5',
      className,
    )}
  >
    <header className="border-b border-foreground/70 pb-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-bold tracking-[0.22em] text-muted-text">TAIWAN DAILY</p>
          <h2 className="mt-1 text-3xl font-black tracking-tight text-foreground md:text-4xl">台股日報</h2>
          <p className="mt-2 text-sm text-secondary-text">FinMind 台股最後交易日快照</p>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:text-right">
          <div>
            <dt className="font-semibold text-muted-text">資料日期</dt>
            <dd className="mt-0.5 font-mono text-foreground">{report.dataDate ?? '未提供'}</dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-text">資料來源</dt>
            <dd className="mt-0.5 font-semibold text-foreground">{report.source}</dd>
          </div>
        </dl>
      </div>
      {report.dataStatus ? (
        <p className="mt-3 rounded-lg border border-border/70 bg-background/60 px-3 py-2 text-xs leading-5 text-secondary-text">
          {report.dataStatus}
        </p>
      ) : null}
    </header>

    <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.9fr)]">
      <main className="space-y-5">
        <ReaderSection title="今日重點" className="border-t-0 pt-0">
          <ul className="space-y-2">
            {report.highlights.map((item) => (
              <li key={item} className="flex gap-2 text-sm leading-6 text-secondary-text">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </ReaderSection>

        <ReaderSection title={report.title}>
          {report.summary.length ? (
            <div className="space-y-2 text-sm leading-7 text-secondary-text">
              {report.summary.map((item) => <p key={item}>{item}</p>)}
            </div>
          ) : (
            <p className="text-sm leading-7 text-muted-text">主要敘述已整理至今日重點與右側資料表。</p>
          )}
        </ReaderSection>

        <ReaderSection title="法人與資金面">
          <MarketRows rows={report.institutional} emptyText="法人資料暫不可用" />
        </ReaderSection>

        <ReaderSection title="風險解讀 / 操作觀察">
          {report.risks.length ? (
            <ul className="space-y-2 text-sm leading-6 text-secondary-text">
              {report.risks.map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : (
            <p className="text-sm text-muted-text">本次報告未提供額外風險註記。</p>
          )}
        </ReaderSection>
      </main>

      <aside className="space-y-5 rounded-xl border border-border/80 bg-background/55 p-4">
        <ReaderSection title="主要指數" className="border-t-0 pt-0">
          <MarketRows rows={report.indices} emptyText="指數資料暫不可用" />
        </ReaderSection>

        <ReaderSection title="融資融券">
          <MarketRows rows={report.margin} emptyText="融資融券資料暫不可用" />
        </ReaderSection>

        <ReaderSection title="代表標的">
          <MarketRows rows={report.representatives} emptyText="0050 / 臺積電資料暫不可用" />
        </ReaderSection>

        <ReaderSection title="資料狀態">
          <dl className="space-y-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted-text">來源</dt>
              <dd className="font-semibold text-foreground">FinMind</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted-text">日期</dt>
              <dd className="font-mono text-foreground">{report.dataDate ?? '未提供'}</dd>
            </div>
          </dl>
        </ReaderSection>
      </aside>
    </div>
  </article>
);

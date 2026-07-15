import type React from 'react';
import type { TwDailyReportModel, TwDailyRow, TwDailyTone } from './twDailyReportAdapter';

interface TwDailyReportViewProps {
  report: TwDailyReportModel;
  className?: string;
}

const cx = (...classes: Array<string | undefined | false>) => classes.filter(Boolean).join(' ');

const toneClass = (tone: TwDailyTone): string => {
  switch (tone) {
    case 'tw-gain':
    case 'tw-buy':
    case 'net-buy':
      return 'text-danger';
    case 'tw-loss':
    case 'tw-sell':
    case 'net-sell':
      return 'text-success';
    case 'risk':
      return 'text-secondary-text';
    case 'missing':
      return 'text-muted-text';
    case 'neutral':
    default:
      return 'text-foreground';
  }
};

const SUMMARY_FILLERS = new Set(['主要敘述已整理至今日重點與右側資料表。']);
const RISK_FILLERS = new Set(['本次報告未提供額外風險註記。']);

const meaningfulText = (value: string | undefined, fillers: Set<string>) => {
  const text = value?.trim() ?? '';
  return text && !fillers.has(text) ? text : '';
};

const Section: React.FC<{
  title: string;
  children: React.ReactNode;
  compact?: boolean;
}> = ({ title, children, compact }) => (
  <section className={cx('border-t border-border/80 pt-4', compact && 'border-t-0 pt-0')}>
    <h3 className="mb-3 text-xs font-bold tracking-[0.18em] text-muted-text">{title}</h3>
    {children}
  </section>
);

const RowList: React.FC<{ rows: TwDailyRow[]; emptyText: string }> = ({ rows, emptyText }) => {
  if (!rows.length) {
    return <p className="text-sm text-muted-text">{emptyText}</p>;
  }

  return (
    <div className="divide-y divide-border/70">
      {rows.map((row, index) => (
        <div
          key={`${row.code || row.label}-${index}`}
          data-tone={row.tone}
          className="grid grid-cols-1 gap-2 py-3 xl:grid-cols-[minmax(0,1fr)_minmax(10rem,max-content)] xl:items-start"
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-5 text-foreground">{row.label}</p>
            {row.code ? <p className="whitespace-nowrap font-mono text-[11px] text-muted-text">{row.code}</p> : null}
            {row.meta ? (
              <p className="mt-1 text-[11px] leading-4 text-muted-text" title={row.meta}>
                {row.meta}
              </p>
            ) : null}
            {row.notes?.length ? (
              <div className="mt-1 flex flex-wrap gap-1.5">
                {row.notes.map((note) => (
                  <span key={note} className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] font-semibold text-muted-text">
                    {note}
                  </span>
                ))}
              </div>
            ) : null}
            {row.metrics?.length ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {row.metrics.map((metric) => (
                  <span
                    key={`${row.label}-${metric.label}`}
                    data-tone={metric.tone}
                    className={cx(
                      'rounded-full border border-border/70 px-2 py-0.5 text-[11px] font-semibold',
                      toneClass(metric.tone),
                    )}
                  >
                    {metric.value}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <p
            data-tone={row.tone}
            className={cx('whitespace-nowrap text-left text-sm font-semibold leading-5 xl:min-w-[10rem] xl:text-right', toneClass(row.tone))}
          >
            {row.value}
          </p>
        </div>
      ))}
    </div>
  );
};

const AnalysisList: React.FC<{ items: string[] }> = ({ items }) => (
  <ul className="space-y-2">
    {items.map((item) => (
      <li key={item} className="flex gap-2 text-sm leading-6 text-secondary-text">
        <span aria-hidden="true" className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-primary" />
        <span>{item}</span>
      </li>
    ))}
  </ul>
);

const AnalysisParagraphs: React.FC<{ items: string[] }> = ({ items }) => (
  <div className="space-y-4">
    {items.map((item) => (
      <p key={item} className="text-[15px] leading-8 text-secondary-text">{item}</p>
    ))}
  </div>
);

const marketStateLabel = (state: string): string => ({
  closed: '市場已收盤，使用最新完成交易日資料',
  outside_session: '市場休市，使用最新完成交易日資料',
  open_incomplete: '市場交易中，本報告不含當日未完成 K 線',
}[state] || '使用最新完成交易日資料');

export const TwDailyReportView: React.FC<TwDailyReportViewProps> = ({ report, className }) => {
  const summary = meaningfulText(report.summary, SUMMARY_FILLERS);
  const risks = report.risks
    .map((risk) => meaningfulText(risk, RISK_FILLERS))
    .filter((risk): risk is string => Boolean(risk));
  const analysis = report.analysis;
  const article = analysis?.article;

  return (
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
          <p className="mt-2 text-sm text-secondary-text">
            {analysis ? '官方日線技術分析 · 法人與槓桿資料補充' : 'FinMind 台股最後交易日快照'}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:text-right">
          <div>
            <dt className="font-semibold text-muted-text">資料日期</dt>
            <dd className="mt-0.5 whitespace-nowrap font-mono text-foreground">{report.dataDate}</dd>
          </div>
          <div>
            <dt className="font-semibold text-muted-text">資料來源</dt>
            <dd className="mt-0.5 font-semibold text-foreground">{report.source}</dd>
          </div>
        </dl>
      </div>
    </header>

    <div
      className={cx(
        'mt-5 grid gap-6',
        !article && 'xl:grid-cols-[minmax(0,1fr)_20rem]',
      )}
    >
      <main className="space-y-5">
        {analysis ? (
          <>
            <section>
              <p className="text-xs font-semibold text-muted-text">{article?.marketContext || marketStateLabel(analysis.marketState)}</p>
              <h1 className="mt-2 text-2xl font-black leading-tight tracking-tight text-foreground md:text-3xl">
                {analysis.title}
              </h1>
              {analysis.openingSummary ? (
                <p className="mt-4 text-sm leading-7 text-secondary-text">{analysis.openingSummary}</p>
              ) : null}
            </section>

            {analysis.coreJudgement.length ? (
              <section className="rounded-xl border-l-4 border-primary bg-background/60 px-4 py-3">
                <p className="text-xs font-bold tracking-[0.18em] text-muted-text">核心判斷</p>
                <p className="mt-1 text-xl font-black leading-8 text-foreground">{analysis.coreJudgement[0]}</p>
                {analysis.coreJudgement.length > 1 ? (
                  <p className="mt-2 text-[15px] font-semibold leading-7 text-secondary-text">{analysis.coreJudgement[1]}</p>
                ) : null}
              </section>
            ) : null}

            {article ? (
              <>
                {article.trendParagraphs.length ? (
                  <Section title="趨勢與動能"><AnalysisParagraphs items={article.trendParagraphs} /></Section>
                ) : null}
                {[...article.priceActionParagraphs, article.confirmationParagraph].filter(Boolean).length ? (
                  <Section title="K 線、量價與關鍵位置">
                    <AnalysisParagraphs items={[...article.priceActionParagraphs, article.confirmationParagraph].filter(Boolean)} />
                  </Section>
                ) : null}
                {[article.tpexContext, ...article.supportingContext].filter(Boolean).length ? (
                  <Section title="法人、融資與市場廣度佐證">
                    <AnalysisParagraphs items={[article.tpexContext, ...article.supportingContext].filter(Boolean)} />
                  </Section>
                ) : null}
              </>
            ) : (
              <>
                {analysis.movingAverageAnalysis.length ? <Section title="均線位置與結構"><AnalysisList items={analysis.movingAverageAnalysis} /></Section> : null}
                {analysis.momentumAnalysis.length ? <Section title="動能 / 指標解讀"><AnalysisList items={analysis.momentumAnalysis} /></Section> : null}
                {[...analysis.priceActionAnalysis, ...analysis.volumeAnalysis].length ? (
                  <Section title="K 線與量價訊號"><AnalysisList items={[...analysis.priceActionAnalysis, ...analysis.volumeAnalysis]} /></Section>
                ) : null}
                {analysis.supportResistanceAnalysis.length ? <Section title="支撐 / 壓力 / 觀察區"><AnalysisList items={analysis.supportResistanceAnalysis} /></Section> : null}
                {analysis.confirmationConditions.length ? <Section title="反彈確認條件"><AnalysisList items={analysis.confirmationConditions} /></Section> : null}
                {analysis.invalidationConditions.length ? <Section title="失效 / 轉弱條件"><AnalysisList items={analysis.invalidationConditions} /></Section> : null}
                {analysis.tpexBreadth.length ? <Section title="TPEx / 廣度補充"><AnalysisList items={analysis.tpexBreadth} /></Section> : null}
              </>
            )}
          </>
        ) : (
        <Section title="今日重點" compact>
          <ul className="space-y-2">
            {report.highlights.map((item) => (
              <li key={item} className="flex gap-2 text-sm leading-6 text-secondary-text">
                <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </Section>
        )}

        {!analysis && summary ? (
          <Section title={report.title}>
            <p className="text-sm leading-7 text-muted-text">{summary}</p>
          </Section>
        ) : null}

        {!article ? (
          <Section title="法人與資金面">
            <RowList rows={report.institutional} emptyText="法人資金資料暫不可用。" />
          </Section>
        ) : null}

        {risks.length ? (
          <Section title="風險解讀 / 操作觀察">
            <ul className="space-y-2">
              {risks.map((risk) => (
                <li key={risk} className="text-sm leading-6 text-muted-text">{risk}</li>
              ))}
            </ul>
          </Section>
        ) : null}
      </main>

      <aside className="min-w-0 rounded-xl border border-border/80 bg-background/55 p-4">
        <details open={!article}>
          <summary className="cursor-pointer text-sm font-bold text-foreground">完整結構化證據</summary>
          <div className="mt-5 space-y-5">
            <Section title="主要指數" compact>
              <RowList rows={report.indices} emptyText="主要指數資料暫不可用。" />
            </Section>
            {article ? (
              <Section title="法人買賣明細">
                <RowList rows={report.institutional} emptyText="法人資金資料暫不可用。" />
              </Section>
            ) : null}
            <Section title="融資融券">
              <RowList rows={report.margin} emptyText="融資融券資料暫不可用。" />
            </Section>
            <Section title="代表標的">
              <RowList rows={report.representatives} emptyText="代表標的資料暫不可用。" />
            </Section>
          </div>
        </details>
      </aside>
    </div>
  </article>
  );
};

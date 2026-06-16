import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { usageApi } from '../api/usage';
import type { UsageDashboard, UsagePeriod } from '../api/usage';
import { AppPage, Loading, PageHeader, StatCard } from '../components/common';
import { getUsageText } from '../utils/usageText';

const t = getUsageText('zh_TW');

function getLocale(language: string): string {
  if (language === 'zh_TW') return 'zh-TW';
  if (language === 'zh') return 'zh-CN';
  return 'en-US';
}

function fmtNumber(value: number, locale = 'zh-TW'): string {
  return new Intl.NumberFormat(locale).format(value);
}

function fmtDateTime(value: string, locale = 'zh-TW'): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

const PERIODS: UsagePeriod[] = ['today', 'month', 'all'];

const LOCALE = getLocale('zh_TW');

const TokenUsagePage: React.FC = () => {
  const [period, setPeriod] = useState<UsagePeriod>('month');
  const [dashboard, setDashboard] = useState<UsageDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (p: UsagePeriod) => {
      setLoading(true);
      setError(null);
      try {
        const data = await usageApi.getDashboard(p, 50);
        setDashboard(data);
      } catch {
        setError(t.loadError);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    load(period);
  }, [period, load]);

  const handlePeriodChange = (p: UsagePeriod) => {
    setPeriod(p);
  };

  const periodActions = (
    <div className="flex gap-1 rounded-lg border border-subtle bg-card/50 p-1">
      {PERIODS.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => handlePeriodChange(p)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
            period === p
              ? 'bg-cyan/10 text-cyan'
              : 'text-secondary-text hover:text-foreground'
          }`}
        >
          {t.period[p]}
        </button>
      ))}
    </div>
  );

  return (
    <AppPage>
      <PageHeader
        title={t.title}
        description={dashboard ? `${dashboard.fromDate} – ${dashboard.toDate}` : undefined}
        actions={periodActions}
      />

      {loading && (
        <div className="mt-8 flex justify-center">
          <Loading />
        </div>
      )}

      {!loading && error && (
        <div className="mt-8 rounded-xl border border-danger/20 bg-danger/5 px-4 py-3 text-sm text-danger">
          {error}
          <button
            type="button"
            className="ml-3 underline"
            onClick={() => load(period)}
          >
            {t.retry}
          </button>
        </div>
      )}

      {!loading && !error && dashboard && (
        <div className="mt-6 space-y-6">
          {/* Summary stat cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              label={t.totalCalls}
              value={fmtNumber(dashboard.totalCalls, LOCALE)}
              icon={<Activity size={20} />}
              tone="primary"
            />
            <StatCard
              label={t.totalTokens}
              value={fmtNumber(dashboard.totalTokens, LOCALE)}
              tone="default"
            />
            <StatCard
              label={t.promptTokens}
              value={fmtNumber(dashboard.totalPromptTokens, LOCALE)}
              tone="default"
            />
            <StatCard
              label={t.completionTokens}
              value={fmtNumber(dashboard.totalCompletionTokens, LOCALE)}
              tone="default"
            />
          </div>

          {/* By call type */}
          {dashboard.byCallType.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-secondary-text">
                {t.byCallType}
              </h2>
              <div className="overflow-x-auto rounded-xl border border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-subtle bg-card/50 text-xs uppercase tracking-wide text-secondary-text">
                      <th className="px-4 py-2 text-left">{t.callType}</th>
                      <th className="px-4 py-2 text-right">{t.calls}</th>
                      <th className="px-4 py-2 text-right">{t.promptTokens}</th>
                      <th className="px-4 py-2 text-right">{t.completionTokens}</th>
                      <th className="px-4 py-2 text-right">{t.tokens}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.byCallType.map((row) => (
                      <tr
                        key={row.callType}
                        className="border-b border-subtle/50 last:border-0 hover:bg-card/30"
                      >
                        <td className="px-4 py-2 font-mono text-foreground">{row.callType}</td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.calls, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.promptTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.completionTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-foreground">
                          {fmtNumber(row.totalTokens, LOCALE)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* By model */}
          {dashboard.byModel.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-secondary-text">
                {t.byModel}
              </h2>
              <div className="overflow-x-auto rounded-xl border border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-subtle bg-card/50 text-xs uppercase tracking-wide text-secondary-text">
                      <th className="px-4 py-2 text-left">{t.model}</th>
                      <th className="px-4 py-2 text-right">{t.calls}</th>
                      <th className="px-4 py-2 text-right">{t.promptTokens}</th>
                      <th className="px-4 py-2 text-right">{t.completionTokens}</th>
                      <th className="px-4 py-2 text-right">{t.tokens}</th>
                      <th className="px-4 py-2 text-right">{t.maxTokens}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.byModel.map((row) => (
                      <tr
                        key={row.model}
                        className="border-b border-subtle/50 last:border-0 hover:bg-card/30"
                      >
                        <td className="px-4 py-2 font-mono text-foreground">{row.model}</td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.calls, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.promptTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.completionTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-foreground">
                          {fmtNumber(row.totalTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.maxTotalTokens, LOCALE)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Recent calls */}
          {dashboard.recentCalls.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-secondary-text">
                {t.recentCalls}
              </h2>
              <div className="overflow-x-auto rounded-xl border border-subtle">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-subtle bg-card/50 text-xs uppercase tracking-wide text-secondary-text">
                      <th className="px-4 py-2 text-left">{t.calledAt}</th>
                      <th className="px-4 py-2 text-left">{t.callType}</th>
                      <th className="px-4 py-2 text-left">{t.model}</th>
                      <th className="px-4 py-2 text-left">{t.stockCode}</th>
                      <th className="px-4 py-2 text-right">{t.promptTokens}</th>
                      <th className="px-4 py-2 text-right">{t.completionTokens}</th>
                      <th className="px-4 py-2 text-right">{t.tokens}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.recentCalls.map((row) => (
                      <tr
                        key={row.id}
                        className="border-b border-subtle/50 last:border-0 hover:bg-card/30"
                      >
                        <td className="px-4 py-2 text-secondary-text">
                          {fmtDateTime(row.calledAt, LOCALE)}
                        </td>
                        <td className="px-4 py-2 font-mono text-foreground">{row.callType}</td>
                        <td className="px-4 py-2 font-mono text-secondary-text">{row.model}</td>
                        <td className="px-4 py-2 text-secondary-text">
                          {row.stockCode ?? '—'}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.promptTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-secondary-text">
                          {fmtNumber(row.completionTokens, LOCALE)}
                        </td>
                        <td className="px-4 py-2 text-right text-foreground">
                          {fmtNumber(row.totalTokens, LOCALE)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {dashboard.totalCalls === 0 && (
            <div className="flex justify-center py-16 text-secondary-text">{t.noData}</div>
          )}
        </div>
      )}
    </AppPage>
  );
};

export default TokenUsagePage;

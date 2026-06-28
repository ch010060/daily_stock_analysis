import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { historyApi } from '../api/history';
import { ReportMarkdownPanel } from '../components/report/ReportMarkdownPanel';
import type { AnalysisReport } from '../types/analysis';
import { normalizeReportLanguage } from '../utils/reportLanguage';

const PRINT_DELAY_MS = 250;

const ReportPrintPage: React.FC = () => {
  const { historyId } = useParams<{ historyId: string }>();
  const [searchParams] = useSearchParams();
  const recordId = Number(historyId);
  const isValidRecordId = Number.isInteger(recordId) && recordId > 0;
  const autoprint = searchParams.get('autoprint') === '1';
  const pdfMode = searchParams.get('pdf') === '1';
  const didPrintRef = useRef(false);
  const [detail, setDetail] = useState<AnalysisReport | null>(null);
  const [detailSettled, setDetailSettled] = useState(false);
  const [isContentReady, setIsContentReady] = useState(false);

  useEffect(() => {
    if (!isValidRecordId) return;

    let mounted = true;

    historyApi.getDetail(recordId)
      .then((result) => {
        if (mounted) {
          setDetail(result);
        }
      })
      .catch(() => {
        if (mounted) {
          setDetail(null);
        }
      })
      .finally(() => {
        if (mounted) {
          setDetailSettled(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, [isValidRecordId, recordId]);

  useEffect(() => {
    if (pdfMode || !autoprint || !isContentReady || didPrintRef.current) return;

    didPrintRef.current = true;
    const timer = window.setTimeout(() => {
      window.print();
    }, PRINT_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [autoprint, isContentReady, pdfMode]);

  const fallbackTitle = useMemo(() => {
    if (!isValidRecordId) return '列印報告';
    return `記錄 #${recordId}`;
  }, [isValidRecordId, recordId]);

  const stockName = detail?.meta?.stockName || fallbackTitle;
  const stockCode = detail?.meta?.stockCode || (isValidRecordId ? String(recordId) : '—');
  const reportLanguage = normalizeReportLanguage(detail?.meta?.reportLanguage);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  if (!isValidRecordId) {
    return (
      <main
        className="report-print-page"
        data-testid="report-print-page"
        data-print-ready="false"
      >
        <div className="report-print-content">
          <div className="report-print-error">
            <h1>無法載入列印報告</h1>
            <p>請返回完整分析報告後再試一次。</p>
            <Link to="/" className="home-surface-button no-print mt-4 inline-flex rounded-lg px-4 py-2 text-sm">
              返回
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main
      className="report-print-page"
      data-testid="report-print-page"
      data-print-ready={isContentReady ? 'true' : 'false'}
    >
      {!pdfMode && (
      <div
        data-testid="report-print-toolbar"
        className="no-print sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-4 py-3 shadow-sm backdrop-blur"
      >
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">列印報告</div>
            <div className="text-xs text-slate-500">{stockName}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700"
              onClick={handlePrint}
            >
              列印 / 下載 PDF
            </button>
            <Link
              to="/"
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              返回
            </Link>
          </div>
        </div>
      </div>
      )}

      <article className="report-print-content">
        {!pdfMode && (
        <header className="report-print-header report-print-section" data-testid="report-print-header">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Full Report</p>
          <h1>{stockName}</h1>
          <div className="report-print-meta">
            <span>代號：{stockCode}</span>
            {detail?.meta?.createdAt && <span>日期：{detail.meta.createdAt.slice(0, 10)}</span>}
            <span>記錄 ID：{recordId}</span>
          </div>
        </header>
        )}

        {detailSettled ? (
          <div className="report-print-panel">
            <ReportMarkdownPanel
              recordId={recordId}
              stockName={stockName}
              stockCode={stockCode}
              reportLanguage={reportLanguage}
              onRequestClose={() => undefined}
              variant="print"
              initialDetail={detail}
              onContentReady={() => setIsContentReady(true)}
            />
          </div>
        ) : (
          <div className="flex h-64 flex-col items-center justify-center">
            <div className="home-spinner h-10 w-10 animate-spin border-[3px]" />
            <p className="mt-4 text-sm text-slate-500">載入列印報告中...</p>
          </div>
        )}
      </article>
    </main>
  );
};

export default ReportPrintPage;

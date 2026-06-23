import React from 'react';
import type { AnalysisResult, AnalysisReport } from '../../types/analysis';
import { ReportOverview } from './ReportOverview';
import { ReportStrategy } from './ReportStrategy';
import { ReportNews } from './ReportNews';
import { ReportDetails } from './ReportDetails';
import { ReportDiagnostics } from './ReportDiagnostics';
import { AnalysisContextSummary } from './AnalysisContextSummary';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportSummaryProps {
  data: AnalysisResult | AnalysisReport;
  isHistory?: boolean;
  /** 自選相關 */
  watchlist?: {
    isInWatchlist: (code: string) => boolean;
    onToggle: (code: string) => void;
    isActioning: boolean;
    actionMessage: string | null;
  };
}

/**
 * 完整報告展示元件
 * 按主體內容優先、透明度資訊後置的順序展示報告。
 */
export const ReportSummary: React.FC<ReportSummaryProps> = ({
  data,
  isHistory = false,
  watchlist,
}) => {
  // 相容 AnalysisResult 和 AnalysisReport 兩種資料格式
  const report: AnalysisReport = 'report' in data ? data.report : data;
  // 使用 report id，因為 queryId 在批次分析時可能重複，且歷史報告詳情介面需要 recordId 來獲取關聯資訊和詳情資料
  const recordId = report.meta.id;
  const diagnosticSummary = 'diagnosticSummary' in data ? data.diagnosticSummary : undefined;

  const { meta, summary, strategy, details } = report;
  const reportLanguage = normalizeReportLanguage(meta.reportLanguage);
  const text = getReportText(reportLanguage);
  const modelUsed = (meta.modelUsed || '').trim();
  const shouldShowModel = Boolean(
    modelUsed && !['unknown', 'error', 'none', 'null', 'n/a'].includes(modelUsed.toLowerCase()),
  );

  return (
    <div className="space-y-5 pb-8 animate-fade-in">
      {/* 概覽區（首屏） */}
      <ReportOverview
        meta={meta}
        summary={summary}
        details={details}
        isHistory={isHistory}
        watchlist={watchlist}
      />

      {/* 策略點位區 */}
      <ReportStrategy strategy={strategy} language={reportLanguage} />

      {/* 資訊區 */}
      <ReportNews recordId={recordId} limit={8} language={reportLanguage} />

      {/* 輸入資料塊低敏摘要 */}
      <AnalysisContextSummary
        overview={details?.analysisContextPackOverview}
        diagnosticSummary={diagnosticSummary}
        recordId={recordId}
        language={reportLanguage}
      />

      {/* 執行診斷摘要 */}
      <ReportDiagnostics
        recordId={recordId}
        summary={diagnosticSummary}
        language={reportLanguage}
      />

      {/* 透明度與追溯區 */}
      <ReportDetails details={details} recordId={recordId} language={reportLanguage} />

      {/* 分析模型標記（Issue #528）— 報告末尾 */}
      {shouldShowModel && (
        <p className="px-1 text-xs text-muted-text">
          {text.analysisModel}: {modelUsed}
        </p>
      )}
    </div>
  );
};

import type React from 'react';
import type { AnalysisReport } from '../../../types/analysis';
import { adaptToVisualReport } from './reportVisualSummaryAdapter';
import { MarketRiskGauge } from './MarketRiskGauge';
import { MultiPeriodTrendBars } from './MultiPeriodTrendBars';
import { TechnicalSnapshotCards } from './TechnicalSnapshotCards';
import { FinancialResultCards } from './FinancialResultCards';
import { ActionPlanCards } from './ActionPlanCards';
import { KlineChartBlock } from './KlineChartBlock';

interface ReportVisualSummaryProps {
  report: AnalysisReport;
  historyId?: number;
}

/** Sentiment score → decision accent color */
function decisionColorClass(score: number): string {
  if (score <= 35) return 'text-danger';
  if (score >= 65) return 'text-success';
  return 'text-warning';
}

/** Instrument type label */
function instrLabel(t: string): string {
  const map: Record<string, string> = {
    stock: '股票',
    etf: 'ETF',
    index: '指數',
    unknown: '—',
  };
  return map[t] ?? t;
}

/** Format date to compact display */
function formatDate(iso: string): string {
  try {
    return iso.replace('T', ' ').slice(0, 16);
  } catch {
    return iso;
  }
}

function normalizeStrategyText(text: string | null): string {
  return (text ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^(?:建議)?(?:觀望|看多|看空|中性)[，,、：:\s]+/, '');
}

function deriveKeyTrigger(...values: Array<string | null>): { value: string; caption: string } {
  const text = values.map(normalizeStrategyText).find(Boolean) ?? '';
  if (!text) return { value: '等待確認', caption: '訊號未齊' };

  const ma = text.match(/MA\s*(\d+)/i)?.[1];
  const maLabel = ma ? `MA${ma}` : null;

  if (maLabel && /(站回|收復|突破)/.test(text)) return { value: `站回 ${maLabel}`, caption: '確認後再行動' };
  if (maLabel && /回測/.test(text) && /支撐/.test(text)) {
    return { value: `回測 ${maLabel} 支撐`, caption: '確認支撐有效' };
  }
  if (maLabel && /支撐/.test(text)) return { value: `守住 ${maLabel}`, caption: '失守則降風險' };
  if (/放量/.test(text)) return { value: '放量確認', caption: '等待量價配合' };
  if (/成交量/.test(text) && /(收縮|收斂)/.test(text)) return { value: '量能收斂', caption: '等待價格確認' };
  if (/(停損|跌破)/.test(text)) return { value: '守住風控線', caption: '失守不追' };
  if (/(壓力|目標)/.test(text)) return { value: '看壓力帶反應', caption: '不追高' };
  return { value: '等待確認', caption: '訊號未齊' };
}

export const ReportVisualSummary: React.FC<ReportVisualSummaryProps> = ({ report, historyId }) => {
  let vm;
  try {
    vm = adaptToVisualReport(report);
  } catch {
    // Silently skip if adapter fails on malformed data
    return null;
  }

  const decisionColor = decisionColorClass(vm.sentimentScore);
  const priceColor = vm.changePct !== null && vm.changePct < 0 ? 'text-danger' : 'text-success';
  const keyTrigger = deriveKeyTrigger(vm.idealBuy, vm.secondaryBuy, vm.stopLoss, vm.takeProfit);

  return (
    <div
      data-testid="report-visual-summary"
      className="report-light-surface mb-6 rounded-xl border bg-background print:mb-4 print:border-none"
    >
      {/* ── Header: V3-style compact letterhead ── */}
      <div className="border-b px-4 pb-3 pt-4">
        <div className="mb-1 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold uppercase tracking-widest text-muted-foreground">
              {vm.stockCode}
            </span>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">{instrLabel(vm.instrumentType)}</span>
          </div>
          <span className="text-[10px] text-muted-foreground">{formatDate(vm.analysisDate)}</span>
        </div>

        <div className="mb-2 text-base font-semibold text-foreground">{vm.stockName}</div>

        {/* Decision + trend row */}
        <div className="flex flex-wrap items-baseline gap-3">
          <span className={`font-mono text-3xl font-black leading-none ${decisionColor}`}>
            {vm.decision}
          </span>
          <span className={`rounded border px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${decisionColor} border-current opacity-70`}>
            {vm.trend}
          </span>
        </div>

        {vm.oneLiner && (
          <p className="mt-1.5 border-l-2 border-muted-foreground/30 pl-2 text-xs italic text-muted-foreground">
            {vm.oneLiner}
          </p>
        )}
      </div>

      {/* ── KPI Row: V3-style 4-cell grid ── */}
      <div className="grid grid-cols-2 divide-x divide-y border-b sm:grid-cols-4 sm:divide-y-0">
        {vm.currentPrice !== null && (
          <div className="px-3 py-2.5">
            <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">現價</div>
            <div className="flex items-baseline gap-1">
              <span className="font-mono text-lg font-bold text-foreground">{vm.currentPrice.toFixed(2)}</span>
              {vm.changePct !== null && (
                <span className={`text-[10px] font-bold ${priceColor}`}>
                  {vm.changePct > 0 ? '+' : ''}{vm.changePct.toFixed(2)}%
                </span>
              )}
            </div>
          </div>
        )}
        <div className="px-3 py-2.5" data-testid="visual-summary-trigger-kpi">
          <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">關鍵觸發</div>
          <div
            className="whitespace-nowrap text-sm font-semibold leading-tight text-foreground"
            data-testid="visual-summary-trigger-value"
          >
            {keyTrigger.value}
          </div>
          <div className="text-[9px] text-muted-foreground">{keyTrigger.caption}</div>
        </div>
        {vm.rsi !== null && (
          <div className="px-3 py-2.5">
            <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">RSI</div>
            <div className={`font-mono text-lg font-bold ${vm.rsi < 30 ? 'text-danger' : vm.rsi > 70 ? 'text-warning' : 'text-foreground'}`}>
              {vm.rsi.toFixed(1)}
            </div>
            <div className="text-[9px] text-muted-foreground">
              {vm.rsi < 30 ? '超賣' : vm.rsi > 70 ? '超買' : '正常'}
            </div>
          </div>
        )}
      </div>

      {/* ── Body sections ── */}
      <div className="space-y-3 p-4">
        {/* VIX Gauge */}
        <MarketRiskGauge
          vixLevel={vm.vixLevel}
          vixStatus={vm.vixStatus}
          spxChangePct={vm.spxChangePct}
          dataGap={vm.marketRiskDataGap}
          marketRiskKind={vm.marketRiskKind}
          sentimentScore={vm.marketRiskSentimentScore}
          sentimentLabel={vm.marketRiskSentimentLabel}
          marketFearIndex={vm.marketFearIndex}
          systemScore={vm.systemScore}
        />

        {historyId && ['stock', 'etf', 'index'].includes(vm.instrumentType) && (
          <KlineChartBlock historyId={historyId} instrumentType={vm.instrumentType} />
        )}

        {/* Multi-Period Trend */}
        <MultiPeriodTrendBars
          periods={vm.trendPeriods}
          dataGap={vm.trendDataGap}
        />

        {/* Technical cards */}
        <TechnicalSnapshotCards
          ma5={vm.ma5}
          ma10={vm.ma10}
          ma20={vm.ma20}
          ma5DevPct={vm.ma5DevPct}
          ma10DevPct={vm.ma10DevPct}
          ma20DevPct={vm.ma20DevPct}
          supportLevel={vm.supportLevel}
          resistanceLevel={vm.resistanceLevel}
          trendStrength={vm.trendStrength}
          volumeRatio={vm.volumeRatio}
          turnoverRate={vm.turnoverRate}
          rsi={vm.rsi}
        />

        {/* Financial result cards (investor-facing) */}
        <FinancialResultCards valuation={vm.valuationCard} fundamental={vm.fundamentalCard} />

        {/* Action plan */}
        <ActionPlanCards
          idealBuy={vm.idealBuy}
          secondaryBuy={vm.secondaryBuy}
          stopLoss={vm.stopLoss}
          takeProfit={vm.takeProfit}
        />
      </div>

      {/* Print-only divider label */}
      <div className="hidden border-t px-4 py-2 print:block">
        <p className="text-[9px] text-muted-foreground">
          以下為完整分析報告原文 ↓
        </p>
      </div>
    </div>
  );
};

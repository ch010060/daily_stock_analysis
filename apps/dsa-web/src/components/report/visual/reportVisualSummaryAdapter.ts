import type {
  AnalysisReport,
  InstrumentType,
  MultiPeriodTrendPeriod,
  VisualReportRawResult,
} from '../../../types/analysis';

// ─── View models ───────────────────────────────────────────────

export type TrendDirection = 'up' | 'down' | 'neutral' | 'insufficient';

export interface TrendPeriodVM {
  label: string;
  direction: TrendDirection;
  changePct: number | null;
  drawdownPct: number | null;
  barWidthPct: number;
}

export type DataAvailStatus = 'ok' | 'gap' | 'na';

export interface DataAvailabilityVM {
  key: string;
  label: string;
  status: DataAvailStatus;
  reason?: string;
}

export interface VisualReportViewModel {
  stockCode: string;
  stockName: string;
  instrumentType: InstrumentType;
  analysisDate: string;
  // Decision
  decision: string;
  trend: string;
  sentimentScore: number;
  oneLiner: string;
  // Price
  currentPrice: number | null;
  changePct: number | null;
  // Market risk
  vixLevel: number | null;
  vixStatus: string | null;
  spxChangePct: number | null;
  vixDataGap: boolean;
  // Trend
  trendPeriods: TrendPeriodVM[];
  trendDataGap: boolean;
  // Technical
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma5DevPct: number | null;
  ma10DevPct: number | null;
  ma20DevPct: number | null;
  supportLevel: number | null;
  resistanceLevel: number | null;
  trendStrength: number | null;
  volumeRatio: number | null;
  turnoverRate: number | null;
  rsi: number | null;
  // Data availability
  dataAvailability: DataAvailabilityVM[];
  // Action plan
  idealBuy: string | null;
  secondaryBuy: string | null;
  stopLoss: string | null;
  takeProfit: string | null;
  // Extras
  hasValueNetwork: boolean;
}

// ─── Helpers ───────────────────────────────────────────────────

function toNum(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === 'string' ? parseFloat(v) : Number(v);
  return isFinite(n) ? n : null;
}

function toStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  return typeof v === 'string' ? v : null;
}

function asRaw(rawResult: Record<string, unknown> | undefined): VisualReportRawResult {
  return (rawResult ?? {}) as VisualReportRawResult;
}

function mapDirection(period: MultiPeriodTrendPeriod): TrendDirection {
  // toCamelCase converts trend_status → trendStatus (real API); test fixtures use status directly
  const status = period.status ?? period.trendStatus ?? '';
  if (status === 'insufficient_data') return 'insufficient';
  // Status takes priority: don't infer from sign when an explicit status is set
  if (status === 'uptrend') return 'up';
  if (status === 'downtrend') return 'down';
  if (status === 'neutral') return 'neutral';
  // No known status: fall back to sign of changePct
  const change = toNum(period.changePct);
  if (change === null) return 'insufficient';
  if (change > 0) return 'up';
  if (change < 0) return 'down';
  return 'neutral';
}

function buildTrendPeriods(periods: MultiPeriodTrendPeriod[]): TrendPeriodVM[] {
  // Use max abs(changePct) as bar reference; fallback to 30 so bars are always visible
  const absolutes = periods
    .map((p) => Math.abs(toNum(p.changePct) ?? 0))
    .filter((v) => v > 0);
  const maxAbs = absolutes.length > 0 ? Math.max(...absolutes) : 30;

  return periods.map((p): TrendPeriodVM => {
    const change = toNum(p.changePct);
    const barW = change !== null ? Math.min(100, (Math.abs(change) / maxAbs) * 100) : 0;
    return {
      label: p.label ?? p.period ?? '—',
      direction: mapDirection(p),
      changePct: change,
      // toCamelCase converts drawdown_from_high_pct → drawdownFromHighPct (real API)
      drawdownPct: toNum(p.drawdownPct) ?? toNum(p.drawdownFromHighPct),
      barWidthPct: barW,
    };
  });
}

function isAllGap(snap: { dataGapFields?: string[] } | null | undefined): boolean {
  if (!snap) return true;
  return Array.isArray(snap.dataGapFields) && snap.dataGapFields.length > 0;
}

// ─── Public adapter ───────────────────────────────────────────

export function adaptToVisualReport(report: AnalysisReport): VisualReportViewModel {
  const { meta, summary, strategy, details } = report;
  const raw = asRaw(details?.rawResult as Record<string, unknown> | undefined);

  const currentPrice = toNum(meta.currentPrice) ?? toNum(raw.currentPrice);
  const changePct = toNum(meta.changePct) ?? toNum(raw.changePct);

  const mrSnap = raw.marketRiskSnapshot ?? null;
  const vixLevel = toNum(mrSnap?.vixLevel);
  const vixStatus = toStr(mrSnap?.vixStatus);
  const spxChangePct = toNum(mrSnap?.spxChangePct);
  const vixDataGap = !mrSnap || vixLevel === null;

  const trendSnap = raw.multiPeriodTrendSnapshot ?? null;
  const rawPeriods: MultiPeriodTrendPeriod[] = Array.isArray(trendSnap?.periods)
    ? (trendSnap!.periods as MultiPeriodTrendPeriod[])
    : [];
  const trendPeriods = buildTrendPeriods(rawPeriods);
  const trendDataGap = rawPeriods.length === 0;

  const ma5 = toNum(raw.ma5);
  const ma10 = toNum(raw.ma10);
  const ma20 = toNum(raw.ma20);
  // Derive MA deviations from price if not explicitly provided
  const devFrom = currentPrice;
  const ma5DevPct = ma5 !== null && devFrom !== null ? ((devFrom - ma5) / ma5) * 100 : toNum(raw.deviationRate);
  const ma10DevPct = ma10 !== null && devFrom !== null ? ((devFrom - ma10) / ma10) * 100 : null;
  const ma20DevPct = ma20 !== null && devFrom !== null ? ((devFrom - ma20) / ma20) * 100 : null;

  const rsi = toNum(raw.rsi12) ?? toNum(raw.rsi6) ?? toNum(raw.rsi);

  const avail: DataAvailabilityVM[] = [
    {
      key: 'valuation',
      label: '估值快照',
      status: isAllGap(raw.valuationSnapshot) ? 'gap' : 'ok',
      reason: toStr(raw.valuationSnapshot?.gapReason) ?? undefined,
    },
    {
      key: 'fundamental',
      label: '基本面',
      status: isAllGap(raw.fundamentalSnapshot) ? 'gap' : 'ok',
      reason: toStr(raw.fundamentalSnapshot?.gapReason) ?? undefined,
    },
    {
      key: 'market_risk',
      label: '市場風險',
      status: vixDataGap ? 'gap' : 'ok',
    },
    {
      key: 'trend',
      label: '多週期趨勢',
      status: trendDataGap ? 'gap' : 'ok',
    },
  ];

  // Add exposure only for ETF/index
  const instrType: InstrumentType =
    (toStr(raw.instrumentType) as InstrumentType | null) ?? 'unknown';
  if (instrType === 'etf' || instrType === 'index') {
    avail.push({
      key: 'exposure',
      label: '曝險摘要',
      status: isAllGap(raw.exposureSnapshot) ? 'gap' : 'ok',
      reason: toStr(raw.exposureSnapshot?.gapReason) ?? undefined,
    });
  }

  return {
    stockCode: meta.stockCode,
    stockName: meta.stockName,
    instrumentType: instrType,
    analysisDate: meta.createdAt,
    decision: summary.operationAdvice ?? '—',
    trend: summary.trendPrediction ?? '—',
    sentimentScore: summary.sentimentScore ?? 50,
    oneLiner: summary.analysisSummary ?? '',
    currentPrice,
    changePct,
    vixLevel,
    vixStatus,
    spxChangePct,
    vixDataGap,
    trendPeriods,
    trendDataGap,
    ma5,
    ma10,
    ma20,
    ma5DevPct,
    ma10DevPct,
    ma20DevPct,
    supportLevel: toNum(raw.supportLevel),
    resistanceLevel: toNum(raw.resistanceLevel),
    trendStrength: toNum(raw.trendStrength),
    volumeRatio: toNum(raw.volumeRatio),
    turnoverRate: toNum(raw.turnoverRate),
    rsi,
    dataAvailability: avail,
    idealBuy: toStr(strategy?.idealBuy),
    secondaryBuy: toStr(strategy?.secondaryBuy),
    stopLoss: toStr(strategy?.stopLoss),
    takeProfit: toStr(strategy?.takeProfit),
    hasValueNetwork: typeof raw.valueNetworkMermaid === 'string' && raw.valueNetworkMermaid.length > 0,
  };
}

import { getSentimentLabel } from '../../../types/analysis';
import { getReportText } from '../../../utils/reportLanguage';
import type {
  AnalysisReport,
  FundamentalSnapshot,
  InstrumentType,
  MarketFearIndexSnapshot,
  MultiPeriodTrendPeriod,
  ValuationSnapshot,
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

export type DataAvailStatus = 'ok' | 'partial' | 'gap' | 'na';

export interface DataAvailabilityVM {
  key: string;
  label: string;
  status: DataAvailStatus;
  reason?: string;
}

export interface FinancialKpiVM {
  key: string;
  label: string;
  value: string;
  signed: boolean;
}

export interface FinancialCardVM {
  title: string;
  kpis: FinancialKpiVM[];
  source: string | null;
  asOf: string | null;
}

export type MarketFearIndexKind = 'vix' | 'vixtwn';
export type MarketFearIndexBucket = 'green' | 'blue' | 'orange' | 'red' | 'unknown';

export interface MarketFearIndexVM {
  kind: MarketFearIndexKind;
  title: string;
  value: number | null;
  asOf: string | null;
  source: string | null;
  dataGapReason: string | null;
  bucket: MarketFearIndexBucket;
  pointerPosition: number | null;
}

export interface SystemScoreVM {
  label: '系統評分';
  value: number | null;
  sentimentLabel: string | null;
  explanation: string;
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
  marketRiskKind: 'vix' | 'sentiment' | 'market_fear';
  marketRiskDataGap: boolean;
  marketRiskSentimentScore: number | null;
  marketRiskSentimentLabel: string | null;
  marketFearIndex: MarketFearIndexVM | null;
  systemScore: SystemScoreVM;
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
  // Data availability (secondary diagnostics — kept for backwards compat)
  dataAvailability: DataAvailabilityVM[];
  // Financial result cards (primary investor-facing display)
  valuationCard: FinancialCardVM | null;
  fundamentalCard: FinancialCardVM | null;
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

function field<T extends Record<string, unknown>>(obj: T | null | undefined, camel: string, snake: string): unknown {
  return obj ? obj[camel] ?? obj[snake] : undefined;
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

// ─── Financial KPI formatters ──────────────────────────────────

function fmtMultiple(v: unknown): string {
  const n = toNum(v);
  return n !== null ? `${n.toFixed(1)}x` : '—';
}

function fmtPct(v: unknown): string {
  const n = toNum(v);
  if (n === null) return '—';
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`;
}

function fmtMarketCap(v: unknown): string {
  const n = toNum(v);
  if (n === null) return '—';
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
  return `${n.toFixed(0)}`;
}

function buildValuationCard(snap: ValuationSnapshot | null | undefined, applicable: boolean): FinancialCardVM | null {
  if (!applicable) return null;
  return {
    title: '估值快照',
    kpis: [
      { key: 'pe_ttm', label: 'PE(TTM)', value: fmtMultiple(snap?.peTtm), signed: false },
      { key: 'pe_forward', label: 'Forward PE', value: fmtMultiple(snap?.peForward), signed: false },
      { key: 'pb', label: 'PB', value: fmtMultiple(snap?.pb), signed: false },
      { key: 'dividend_yield', label: '股息率', value: fmtPct(snap?.dividendYield), signed: false },
      { key: 'market_cap', label: '市值', value: fmtMarketCap(snap?.marketCap), signed: false },
    ],
    source: toStr(snap?.source),
    asOf: toStr(snap?.asOf),
  };
}

function buildFundamentalCard(snap: FundamentalSnapshot | null | undefined, applicable: boolean): FinancialCardVM | null {
  if (!applicable) return null;
  return {
    title: '基本面',
    kpis: [
      { key: 'revenue_yoy', label: '營收 YoY', value: fmtPct(snap?.revenueYoy), signed: true },
      { key: 'net_profit_yoy', label: '淨利 YoY', value: fmtPct(snap?.netProfitYoy ?? snap?.earningsYoy), signed: true },
      { key: 'roe', label: 'ROE', value: fmtPct(snap?.roe), signed: false },
      { key: 'gross_margin', label: '毛利率', value: fmtPct(snap?.grossMargin), signed: false },
    ],
    source: toStr(snap?.source),
    asOf: toStr(snap?.asOf),
  };
}

const VALUATION_FIELD_COUNT = 5;
const FUNDAMENTAL_FIELD_COUNT = 5;

function snapshotAvailability(
  snap: { dataGapFields?: string[] } | null | undefined,
  fieldCount: number,
  applicable: boolean,
): { status: DataAvailStatus; reason?: string } {
  if (!applicable) return { status: 'na' };
  if (!snap) return { status: 'gap', reason: '未產生快照' };

  const gaps = Array.isArray(snap.dataGapFields) ? snap.dataGapFields : [];
  if (gaps.length === 0) return { status: 'ok' };
  if (gaps.length >= fieldCount) return { status: 'gap', reason: '欄位全缺' };
  return { status: 'partial', reason: `缺少 ${gaps.length}/${fieldCount} 欄位` };
}

function normalizeMarket(v: unknown): 'tw' | 'us' | null {
  const raw = toStr(v)?.toLowerCase();
  if (!raw) return null;
  if (raw === 'tw' || raw === 'taiwan') return 'tw';
  if (raw === 'us' || raw === 'usa' || raw === 'united_states') return 'us';
  return null;
}

function inferReportMarket(report: AnalysisReport, raw: VisualReportRawResult): 'tw' | 'us' | null {
  const fromContext = normalizeMarket(report.details?.analysisContextPackOverview?.subject?.market);
  if (fromContext) return fromContext;
  const fromMeta = normalizeMarket(report.meta.marketPhaseSummary?.market);
  if (fromMeta) return fromMeta;
  const fromRaw = normalizeMarket(raw.market);
  if (fromRaw) return fromRaw;

  const code = report.meta.stockCode.toUpperCase();
  if (/^(?:TW:)?\d{4,6}(?:\.TW)?$/.test(code)) return 'tw';
  if (/^(?:US:)?[A-Z]{1,5}(?:[.-][A-Z]{1,2})?$/.test(code)) return 'us';
  return null;
}

function clampPct(v: number): number {
  return Math.max(0, Math.min(100, v));
}

function marketFearTitle(kind: MarketFearIndexKind): string {
  return kind === 'vixtwn' ? '台灣恐慌指數 VIXTWN' : '恐慌指數 VIX';
}

export function marketFearBucket(kind: MarketFearIndexKind, value: number | null): MarketFearIndexBucket {
  if (value === null) return 'unknown';
  if (value < 20) return 'green';
  if (kind === 'vixtwn') {
    if (value < 30) return 'blue';
    if (value < 40) return 'orange';
    return 'red';
  }
  if (value < 28.7) return 'blue';
  if (value < 33.5) return 'orange';
  return 'red';
}

export function marketFearPointerPosition(kind: MarketFearIndexKind, value: number | null): number | null {
  if (value === null) return null;
  const stops = kind === 'vixtwn' ? [0, 20, 30, 40, 60] : [0, 20, 28.7, 33.5, 45];
  if (value <= stops[0]) return 0;
  for (let i = 1; i < stops.length; i += 1) {
    if (value < stops[i]) {
      const start = stops[i - 1];
      const end = stops[i];
      return clampPct((i - 1) * 25 + ((value - start) / (end - start)) * 25);
    }
  }
  return 100;
}

function marketFearKind(v: unknown): MarketFearIndexKind | null {
  if (v === 'vix' || v === 'vixtwn') return v;
  return null;
}

function buildMarketFearIndex(
  snap: MarketFearIndexSnapshot | null | undefined,
  fallbackVix: { value: number | null; asOf: string | null; source: string | null } | null,
): MarketFearIndexVM | null {
  const rawSnap = snap as (MarketFearIndexSnapshot & Record<string, unknown>) | null | undefined;
  const snapKind = marketFearKind(rawSnap?.kind);
  if (snapKind) {
    const value = toNum(rawSnap?.value);
    return {
      kind: snapKind,
      title: marketFearTitle(snapKind),
      value,
      asOf: toStr(field(rawSnap, 'asOf', 'as_of')),
      source: toStr(rawSnap?.source),
      dataGapReason: toStr(field(rawSnap, 'dataGapReason', 'data_gap_reason')),
      bucket: marketFearBucket(snapKind, value),
      pointerPosition: marketFearPointerPosition(snapKind, value),
    };
  }

  if (fallbackVix && fallbackVix.value !== null) {
    return {
      kind: 'vix',
      title: marketFearTitle('vix'),
      value: fallbackVix.value,
      asOf: fallbackVix.asOf,
      source: fallbackVix.source,
      dataGapReason: null,
      bucket: marketFearBucket('vix', fallbackVix.value),
      pointerPosition: marketFearPointerPosition('vix', fallbackVix.value),
    };
  }

  return null;
}

// ─── Public adapter ───────────────────────────────────────────

export function adaptToVisualReport(report: AnalysisReport): VisualReportViewModel {
  const { meta, summary, strategy, details } = report;
  const raw = asRaw(details?.rawResult as Record<string, unknown> | undefined);

  const currentPrice = toNum(meta.currentPrice) ?? toNum(raw.currentPrice);
  const changePct = toNum(meta.changePct) ?? toNum(raw.changePct);

  const mrSnap = (raw.marketRiskSnapshot ?? raw.market_risk_snapshot ?? null) as (Record<string, unknown> | null);
  const vixLevel = toNum(field(mrSnap, 'vixLevel', 'vix_level'));
  const vixStatus = toStr(field(mrSnap, 'vixStatus', 'vix_status'));
  const spxChangePct = toNum(field(mrSnap, 'spxChangePct', 'spx_change_pct'));
  const vixDataGap = !mrSnap || vixLevel === null;
  const rawSentimentScore = toNum(summary.sentimentScore);
  const market = inferReportMarket(report, raw);
  const marketRiskSentimentLabel =
    rawSentimentScore !== null
      ? (toStr(summary.sentimentLabel) ?? getSentimentLabel(rawSentimentScore, meta.reportLanguage ?? 'zh_TW'))
      : null;
  const rawMarketFearIndexSnapshot = raw.marketFearIndexSnapshot ?? raw.market_fear_index_snapshot;
  const marketFearIndex = buildMarketFearIndex(rawMarketFearIndexSnapshot as MarketFearIndexSnapshot | null | undefined, {
    value: vixLevel,
    asOf: toStr(field(mrSnap, 'asOf', 'as_of')),
    source: toStr(mrSnap?.source),
  });
  const hasPersistedMarketFearIndex = Boolean(rawMarketFearIndexSnapshot && marketFearIndex);
  const marketRiskKind = hasPersistedMarketFearIndex ? 'market_fear' : vixLevel !== null || market !== 'tw' ? 'vix' : 'sentiment';
  const marketRiskDataGap = marketFearIndex
    ? marketFearIndex.value === null
    : marketRiskKind === 'vix'
      ? vixDataGap
      : rawSentimentScore === null;
  const systemScore: SystemScoreVM = {
    label: '系統評分',
    value: rawSentimentScore,
    sentimentLabel: marketRiskSentimentLabel,
    explanation: getReportText(meta.reportLanguage ?? 'zh_TW').systemScoreProvenance,
  };

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

  const instrType: InstrumentType =
    (toStr(raw.instrumentType) as InstrumentType | null) ?? 'unknown';
  const stockOnlySnapshotsApply = instrType === 'stock';
  const valuationAvailability = snapshotAvailability(
    raw.valuationSnapshot,
    VALUATION_FIELD_COUNT,
    stockOnlySnapshotsApply,
  );
  const fundamentalAvailability = snapshotAvailability(
    raw.fundamentalSnapshot,
    FUNDAMENTAL_FIELD_COUNT,
    stockOnlySnapshotsApply,
  );

  const avail: DataAvailabilityVM[] = [
    {
      key: 'valuation',
      label: '估值快照',
      status: valuationAvailability.status,
      reason: toStr(raw.valuationSnapshot?.gapReason) ?? valuationAvailability.reason,
    },
    {
      key: 'fundamental',
      label: '基本面',
      status: fundamentalAvailability.status,
      reason: toStr(raw.fundamentalSnapshot?.gapReason) ?? fundamentalAvailability.reason,
    },
    {
      key: 'market_risk',
      label: '市場風險',
      status: marketRiskDataGap ? 'gap' : 'ok',
      reason: marketRiskKind === 'sentiment' && marketRiskDataGap ? '情緒分數未產生' : undefined,
    },
    {
      key: 'trend',
      label: '多週期趨勢',
      status: trendDataGap ? 'gap' : 'ok',
    },
  ];

  // Add exposure only for ETF/index
  if (instrType === 'etf' || instrType === 'index') {
    const exposureAvailability = snapshotAvailability(raw.exposureSnapshot, 1, true);
    avail.push({
      key: 'exposure',
      label: '曝險摘要',
      status: exposureAvailability.status,
      reason: toStr(raw.exposureSnapshot?.gapReason) ?? exposureAvailability.reason,
    });
  }

  const valuationCard = buildValuationCard(raw.valuationSnapshot, stockOnlySnapshotsApply);
  const fundamentalCard = buildFundamentalCard(raw.fundamentalSnapshot, stockOnlySnapshotsApply);

  return {
    stockCode: meta.stockCode,
    stockName: meta.stockName,
    instrumentType: instrType,
    analysisDate: meta.createdAt,
    decision: summary.operationAdvice ?? '—',
    trend: summary.trendPrediction ?? '—',
    sentimentScore: rawSentimentScore ?? 50,
    oneLiner: summary.analysisSummary ?? '',
    currentPrice,
    changePct,
    vixLevel,
    vixStatus,
    spxChangePct,
    vixDataGap,
    marketRiskKind,
    marketRiskDataGap,
    marketRiskSentimentScore: rawSentimentScore,
    marketRiskSentimentLabel,
    marketFearIndex,
    systemScore,
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
    valuationCard,
    fundamentalCard,
    idealBuy: toStr(strategy?.idealBuy),
    secondaryBuy: toStr(strategy?.secondaryBuy),
    stopLoss: toStr(strategy?.stopLoss),
    takeProfit: toStr(strategy?.takeProfit),
    hasValueNetwork: typeof raw.valueNetworkMermaid === 'string' && raw.valueNetworkMermaid.length > 0,
  };
}

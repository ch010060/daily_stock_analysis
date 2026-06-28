import type { KlineBar, KlineRange, KlineResponse } from '../../../types/analysis';

export type MaKey = 'ma20' | 'ma60' | 'ma120' | 'ma252';
export type MarketReviewColorScheme = 'green_up' | 'red_up';

export interface MarketMovementColors {
  upColor: string;
  downColor: string;
  borderUpColor: string;
  borderDownColor: string;
  wickUpColor: string;
  wickDownColor: string;
  volumeUpColor: string;
  volumeDownColor: string;
  upTextClass: string;
  downTextClass: string;
}

export interface KlinePointVM {
  time: string;
  chartTime: string | number;
  dateLabel: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  ma20: number | null;
  ma60: number | null;
  ma120: number | null;
  ma252: number | null;
}

export interface KlineChartVM {
  symbol: string;
  market: string;
  range: KlineRange;
  granularity: 'daily' | 'intraday' | string;
  interval: string | null;
  source: string;
  sourceType: string;
  sourceChain: string[];
  sourceNote: string;
  asOf: string | null;
  snapshotCreatedAt: string | null;
  points: KlinePointVM[];
  visibleMaKeys: MaKey[];
  showMaLines: boolean;
  currentPrice: number | null;
  supportLevel: number | null;
  resistanceLevel: number | null;
  dataGapReason: string | null;
}

const DAILY_MA_KEYS: Record<KlineRange, MaKey[]> = {
  '1d': [],
  '5d': [],
  '1w': ['ma20'],
  '1m': ['ma20', 'ma60'],
  '3m': ['ma20', 'ma60', 'ma120'],
  '1y': ['ma20', 'ma60', 'ma120', 'ma252'],
};

const GREEN_UP_COLORS: MarketMovementColors = {
  upColor: '#16a34a',
  downColor: '#dc2626',
  borderUpColor: '#16a34a',
  borderDownColor: '#dc2626',
  wickUpColor: '#15803d',
  wickDownColor: '#b91c1c',
  volumeUpColor: 'rgba(22, 163, 74, 0.25)',
  volumeDownColor: 'rgba(220, 38, 38, 0.25)',
  upTextClass: 'text-success',
  downTextClass: 'text-danger',
};

const RED_UP_COLORS: MarketMovementColors = {
  upColor: '#dc2626',
  downColor: '#16a34a',
  borderUpColor: '#dc2626',
  borderDownColor: '#16a34a',
  wickUpColor: '#b91c1c',
  wickDownColor: '#15803d',
  volumeUpColor: 'rgba(220, 38, 38, 0.25)',
  volumeDownColor: 'rgba(22, 163, 74, 0.25)',
  upTextClass: 'text-danger',
  downTextClass: 'text-success',
};

export function normalizeMarketReviewColorScheme(value: unknown): MarketReviewColorScheme {
  return String(value || '').trim().toLowerCase().replace('-', '_') === 'red_up' ? 'red_up' : 'green_up';
}

export function getMarketMovementColors(colorScheme: unknown): MarketMovementColors {
  return normalizeMarketReviewColorScheme(colorScheme) === 'red_up' ? RED_UP_COLORS : GREEN_UP_COLORS;
}

function finite(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeChartTime(raw: string, granularity: string): string | number | null {
  if (granularity !== 'intraday') return raw;
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : null;
}

function formatDateLabel(raw: string, granularity: string): string {
  if (granularity !== 'intraday') return raw;
  return raw.replace('T', ' ').slice(0, 16);
}

function toPoint(row: KlineBar, granularity: string): KlinePointVM | null {
  const rawTime = row.timestamp || row.date;
  const open = finite(row.open);
  const high = finite(row.high);
  const low = finite(row.low);
  const close = finite(row.close);
  const chartTime = rawTime ? normalizeChartTime(rawTime, granularity) : null;
  if (open === null || high === null || low === null || close === null || !rawTime || chartTime === null) return null;
  return {
    time: rawTime,
    chartTime,
    dateLabel: formatDateLabel(rawTime, granularity),
    open,
    high,
    low,
    close,
    volume: finite(row.volume),
    ma20: finite(row.ma20),
    ma60: finite(row.ma60),
    ma120: finite(row.ma120),
    ma252: finite(row.ma252),
  };
}

function visibleMaKeys(range: KlineRange, granularity: string): MaKey[] {
  if (granularity === 'intraday') return [];
  return DAILY_MA_KEYS[range] || [];
}

function sourceNote(response: KlineResponse): string {
  if (response.granularity === 'intraday') {
    const intervalLabel = response.range === '1d' ? '1D=5m' : response.range === '5d' ? '5D=15m' : `${response.range}=${response.interval || 'intraday'}`;
    return `盤中 K｜yfinance snapshot｜${intervalLabel}`;
  }
  return '日 K｜report snapshot / DB cache｜1M/3M/1Y 為日線視窗';
}

export function adaptKlineResponse(response: KlineResponse): KlineChartVM {
  const granularity = response.granularity || 'daily';
  const sourceRows = granularity === 'intraday' ? (response.candles || []) : (response.rows?.length ? response.rows : response.candles || []);
  const points = sourceRows
    .map((row) => toPoint(row, granularity))
    .filter((point): point is KlinePointVM => point !== null);
  const maKeys = visibleMaKeys(response.range, granularity);
  return {
    symbol: response.symbol,
    market: response.market || 'unknown',
    range: response.range,
    granularity,
    interval: response.interval ?? null,
    source: response.source || '—',
    sourceType: response.sourceType || 'data_gap',
    sourceChain: response.sourceChain || [],
    sourceNote: sourceNote(response),
    asOf: response.asOf ?? null,
    snapshotCreatedAt: response.snapshotCreatedAt ?? null,
    points,
    visibleMaKeys: maKeys,
    showMaLines: maKeys.length > 0,
    currentPrice: finite(response.currentPrice),
    supportLevel: finite(response.supportLevel),
    resistanceLevel: finite(response.resistanceLevel),
    dataGapReason: response.dataGapReason ?? null,
  };
}

function trimTwDecimal(text: string): string {
  return text.replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
}

export function formatKlinePrice(value: number | null | undefined, market: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (market === 'tw') return trimTwDecimal(value.toFixed(2));
  return value.toFixed(2);
}

export function formatKlineVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return Math.round(value).toLocaleString('zh-TW');
}

export function formatKlineStrip(
  point: KlinePointVM | null,
  market: string,
  options: { granularity?: string; interval?: string | null; source?: string | null } = {},
): string {
  const intraday = options.granularity === 'intraday';
  const prefix = intraday ? '日期時間' : '日期';
  if (!point) {
    return intraday
      ? `${prefix} —｜開 —｜高 —｜低 —｜收 —｜量 —｜interval ${options.interval || '—'}｜source ${options.source || '—'}`
      : `${prefix} —｜開 —｜高 —｜低 —｜收 —｜量 —｜MA20 —｜MA60 —｜MA120 —｜MA252 —`;
  }
  const price = (value: number | null) => formatKlinePrice(value, market);
  const base = [
    `${prefix} ${point.dateLabel}`,
    `開 ${price(point.open)}`,
    `高 ${price(point.high)}`,
    `低 ${price(point.low)}`,
    `收 ${price(point.close)}`,
    `量 ${formatKlineVolume(point.volume)}`,
  ];
  if (intraday) {
    return [...base, `interval ${options.interval || '—'}`, `source ${options.source || '—'}`].join('｜');
  }
  return [
    ...base,
    `MA20 ${price(point.ma20)}`,
    `MA60 ${price(point.ma60)}`,
    `MA120 ${price(point.ma120)}`,
    `MA252 ${price(point.ma252)}`,
  ].join('｜');
}

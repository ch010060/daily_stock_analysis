import type { KlineBar, KlineResponse } from '../../../types/analysis';

export interface KlinePointVM {
  time: string;
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
  source: string;
  sourceType: string;
  asOf: string | null;
  points: KlinePointVM[];
  currentPrice: number | null;
  supportLevel: number | null;
  resistanceLevel: number | null;
  dataGapReason: string | null;
}

function finite(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function toPoint(row: KlineBar): KlinePointVM | null {
  const open = finite(row.open);
  const high = finite(row.high);
  const low = finite(row.low);
  const close = finite(row.close);
  if (open === null || high === null || low === null || close === null || !row.date) return null;
  return {
    time: row.date,
    dateLabel: row.date,
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

export function adaptKlineResponse(response: KlineResponse): KlineChartVM {
  const points = (response.rows || [])
    .map(toPoint)
    .filter((point): point is KlinePointVM => point !== null);
  return {
    symbol: response.symbol,
    market: response.market || 'unknown',
    source: response.source || '—',
    sourceType: response.sourceType || 'data_gap',
    asOf: response.asOf ?? null,
    points,
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

export function formatKlineStrip(point: KlinePointVM | null, market: string): string {
  if (!point) return '日期 —｜開 —｜高 —｜低 —｜收 —｜量 —｜MA20 —｜MA60 —｜MA120 —｜MA252 —';
  const price = (value: number | null) => formatKlinePrice(value, market);
  return [
    `日期 ${point.dateLabel}`,
    `開 ${price(point.open)}`,
    `高 ${price(point.high)}`,
    `低 ${price(point.low)}`,
    `收 ${price(point.close)}`,
    `量 ${formatKlineVolume(point.volume)}`,
    `MA20 ${price(point.ma20)}`,
    `MA60 ${price(point.ma60)}`,
    `MA120 ${price(point.ma120)}`,
    `MA252 ${price(point.ma252)}`,
  ].join('｜');
}

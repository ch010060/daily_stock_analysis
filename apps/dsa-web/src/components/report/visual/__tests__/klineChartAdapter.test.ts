import { describe, expect, it } from 'vitest';
import type { KlineResponse } from '../../../../types/analysis';
import {
  adaptKlineResponse,
  formatKlinePrice,
  formatKlineStrip,
  getMarketMovementColors,
} from '../klineChartAdapter';

const DAILY_RESPONSE: KlineResponse = {
  historyId: 65,
  symbol: 'MSFT',
  market: 'us',
  instrumentType: 'stock',
  range: '3m',
  granularity: 'daily',
  interval: '1d',
  source: 'analysis_kline_snapshot',
  sourceType: 'db_cache',
  sourceChain: ['analysis_kline_snapshot', 'stock_daily'],
  asOf: '2026-06-26',
  currentPrice: 372.97,
  supportLevel: 355.43,
  resistanceLevel: 400.12,
  dataGapReason: null,
  rows: [
    {
      date: '2026-06-26',
      open: 357.15,
      high: 376.61,
      low: 355.43,
      close: 372.97,
      volume: 36_360_000,
      ma20: 400.12,
      ma60: 410.55,
      ma120: 421,
      ma252: null,
    },
  ],
};

const INTRADAY_RESPONSE: KlineResponse = {
  ...DAILY_RESPONSE,
  range: '1d',
  granularity: 'intraday',
  interval: '5m',
  source: 'yfinance',
  rows: [],
  candles: [
    {
      timestamp: '2026-06-26T09:30:00-04:00',
      open: 357.15,
      high: 358.42,
      low: 356.9,
      close: 357.8,
      volume: 123_456,
    },
  ],
};

describe('klineChartAdapter', () => {
  it('adapts daily API rows into tooltip-ready VM points and MA policy', () => {
    const vm = adaptKlineResponse(DAILY_RESPONSE);
    expect(vm.points).toHaveLength(1);
    expect(vm.visibleMaKeys).toEqual(['ma20', 'ma60', 'ma120']);
    expect(vm.showMaLines).toBe(true);
    expect(vm.sourceNote).toContain('日 K');
    expect(vm.points[0]).toMatchObject({
      time: '2026-06-26',
      chartTime: '2026-06-26',
      open: 357.15,
      high: 376.61,
      low: 355.43,
      close: 372.97,
      ma20: 400.12,
      ma252: null,
    });
  });

  it('adapts intraday candles without daily MA lines', () => {
    const vm = adaptKlineResponse(INTRADAY_RESPONSE);
    expect(vm.points).toHaveLength(1);
    expect(vm.visibleMaKeys).toEqual([]);
    expect(vm.showMaLines).toBe(false);
    expect(vm.interval).toBe('5m');
    expect(vm.sourceNote).toContain('盤中 K');
    expect(vm.points[0].dateLabel).toBe('2026-06-26 09:30');
    expect(typeof vm.points[0].chartTime).toBe('number');
  });

  it('keeps daily MA policy by range', () => {
    expect(adaptKlineResponse({ ...DAILY_RESPONSE, range: '1m' }).visibleMaKeys).toEqual(['ma20', 'ma60']);
    expect(adaptKlineResponse({ ...DAILY_RESPONSE, range: '3m' }).visibleMaKeys).toEqual(['ma20', 'ma60', 'ma120']);
    expect(adaptKlineResponse({ ...DAILY_RESPONSE, range: '1y' }).visibleMaKeys).toEqual(['ma20', 'ma60', 'ma120', 'ma252']);
  });

  it('formats US prices with two decimals', () => {
    expect(formatKlinePrice(357, 'us')).toBe('357.00');
    expect(formatKlinePrice(357.1, 'us')).toBe('357.10');
  });

  it('formats TW prices without ugly trailing decimals', () => {
    expect(formatKlinePrice(4150, 'tw')).toBe('4150');
    expect(formatKlinePrice(244.4, 'tw')).toBe('244.4');
    expect(formatKlinePrice(238.75, 'tw')).toBe('238.75');
  });

  it('renders missing MA values as dash in the daily data strip', () => {
    const strip = formatKlineStrip(adaptKlineResponse(DAILY_RESPONSE).points[0], 'us');
    expect(strip).toContain('日期 2026-06-26');
    expect(strip).toContain('開 357.15');
    expect(strip).toContain('高 376.61');
    expect(strip).toContain('低 355.43');
    expect(strip).toContain('收 372.97');
    expect(strip).toContain('量 36,360,000');
    expect(strip).toContain('MA252 —');
  });

  it('renders intraday data strip with interval and source instead of daily MA values', () => {
    const vm = adaptKlineResponse(INTRADAY_RESPONSE);
    const strip = formatKlineStrip(vm.points[0], 'us', { granularity: vm.granularity, interval: vm.interval, source: vm.source });
    expect(strip).toContain('日期時間 2026-06-26 09:30');
    expect(strip).toContain('interval 5m');
    expect(strip).toContain('source yfinance');
    expect(strip).not.toContain('MA20');
  });

  it('maps movement colors for green_up and red_up', () => {
    expect(getMarketMovementColors('green_up')).toMatchObject({ upColor: '#16a34a', downColor: '#dc2626' });
    expect(getMarketMovementColors('red_up')).toMatchObject({ upColor: '#dc2626', downColor: '#16a34a' });
  });
});

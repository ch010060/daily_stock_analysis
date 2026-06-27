import { describe, expect, it } from 'vitest';
import type { KlineResponse } from '../../../../types/analysis';
import { adaptKlineResponse, formatKlinePrice, formatKlineStrip } from '../klineChartAdapter';

const RESPONSE: KlineResponse = {
  historyId: 65,
  symbol: 'MSFT',
  market: 'us',
  instrumentType: 'stock',
  range: '3m',
  source: 'YfinanceFetcher',
  sourceType: 'db_cache',
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

describe('klineChartAdapter', () => {
  it('adapts API rows into tooltip-ready VM points', () => {
    const vm = adaptKlineResponse(RESPONSE);
    expect(vm.points).toHaveLength(1);
    expect(vm.points[0]).toMatchObject({
      time: '2026-06-26',
      open: 357.15,
      high: 376.61,
      low: 355.43,
      close: 372.97,
      ma20: 400.12,
      ma252: null,
    });
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

  it('renders missing MA values as dash in the data strip', () => {
    const strip = formatKlineStrip(adaptKlineResponse(RESPONSE).points[0], 'us');
    expect(strip).toContain('日期 2026-06-26');
    expect(strip).toContain('開 357.15');
    expect(strip).toContain('高 376.61');
    expect(strip).toContain('低 355.43');
    expect(strip).toContain('收 372.97');
    expect(strip).toContain('量 36,360,000');
    expect(strip).toContain('MA252 —');
  });
});

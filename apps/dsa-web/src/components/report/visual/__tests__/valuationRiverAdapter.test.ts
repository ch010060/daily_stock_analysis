import { describe, expect, it } from 'vitest';
import { adaptValuationRiverSnapshot } from '../valuationRiverAdapter';

const validSnapshot = () => ({
  enabled: true,
  market: 'tw',
  symbol: '2330',
  currency: 'TWD',
  source: 'finmind',
  method: 'per_implied_eps_river',
  basis: 'implied_eps',
  bandMultiples: [14, 18, 22, 26, 30, 34, 38],
  neutralMultiple: 26,
  asOf: '2026-01-20',
  range: { startDate: '2026-01-01', endDate: '2026-01-20', tradingDays: 20 },
  points: [
    { date: '2026-01-01', close: 1000, per: 20, impliedEps: 50, bands: { per14: 700, per26: 1300 } },
    { date: '2026-01-20', close: 1100, per: 22, impliedEps: 50, bands: { per14: 700, per26: 1300 } },
  ],
  current: { close: 1100, per: 22, impliedEps: 50, zone: 'undervalued' },
  quality: {
    status: 'ok',
    warnings: [],
    dataGapFields: [],
    methodologyNote: '倍數帶為固定視覺參考基準，非估值結論、目標價或買賣建議。',
  },
});

describe('adaptValuationRiverSnapshot', () => {
  it('normalizes a valid enabled camelCase payload', () => {
    const vm = adaptValuationRiverSnapshot(validSnapshot());
    expect(vm.enabled).toBe(true);
    if (!vm.enabled) throw new Error('expected enabled vm');
    expect(vm.symbol).toBe('2330');
    expect(vm.bandMultiples).toEqual([14, 18, 22, 26, 30, 34, 38]);
    expect(vm.neutralMultiple).toBe(26);
    expect(vm.points).toHaveLength(2);
    expect(vm.points[0].bands).toEqual([
      { multiple: 14, value: 700 },
      { multiple: 26, value: 1300 },
    ]);
    expect(vm.current.zone).toBe('undervalued');
    expect(vm.tradingDays).toBe(20);
    expect(vm.isPartial).toBe(false);
  });

  it('tolerates snake_case keys (raw payload parity)', () => {
    const vm = adaptValuationRiverSnapshot({
      enabled: true,
      symbol: '2330',
      currency: 'TWD',
      band_multiples: [14, 26, 38],
      neutral_multiple: 26,
      range: { start_date: '2026-01-01', end_date: '2026-01-02', trading_days: 2 },
      points: [
        { date: '2026-01-01', close: 1000, per: 20, implied_eps: 50, bands: { per_14: 700, per_26: 1300 } },
        { date: '2026-01-02', close: 1000, per: 20, implied_eps: 50, bands: { per_14: 700, per_26: 1300 } },
      ],
      current: { close: 1000, per: 20, implied_eps: 50, zone: 'undervalued' },
      quality: { status: 'ok', warnings: [], methodology_note: 'note' },
    });
    expect(vm.enabled).toBe(true);
    if (!vm.enabled) throw new Error('expected enabled vm');
    expect(vm.startDate).toBe('2026-01-01');
    expect(vm.endDate).toBe('2026-01-02');
    expect(vm.tradingDays).toBe(2);
    expect(vm.points[0].bands).toEqual([
      { multiple: 14, value: 700 },
      { multiple: 26, value: 1300 },
    ]);
  });

  it('returns enabled:false for missing, null, or malformed payloads', () => {
    expect(adaptValuationRiverSnapshot(undefined)).toEqual({
      enabled: false,
      market: null,
      reason: '尚無估值河流圖資料',
    });
    expect(adaptValuationRiverSnapshot(null)).toEqual({
      enabled: false,
      market: null,
      reason: '尚無估值河流圖資料',
    });
    expect(adaptValuationRiverSnapshot('not-an-object')).toEqual({
      enabled: false,
      market: null,
      reason: '尚無估值河流圖資料',
    });
    expect(adaptValuationRiverSnapshot([1, 2, 3])).toEqual({
      enabled: false,
      market: null,
      reason: '尚無估值河流圖資料',
    });
  });

  it('surfaces the explicit unavailable reason for US/ETF/index payloads', () => {
    const vm = adaptValuationRiverSnapshot({
      enabled: false,
      market: 'us',
      quality: { status: 'unsupported', warnings: ['US 股票歷史估值河流圖資料尚未支援'] },
    });
    expect(vm).toEqual({
      enabled: false,
      market: 'us',
      reason: 'US 股票歷史估值河流圖資料尚未支援',
    });
  });

  it('falls back to enabled:false when points are empty even if enabled:true', () => {
    const payload = validSnapshot();
    payload.points = [];
    const vm = adaptValuationRiverSnapshot(payload);
    expect(vm.enabled).toBe(false);
  });

  it('marks isPartial from quality.status', () => {
    const payload = validSnapshot();
    payload.quality.status = 'partial';
    const vm = adaptValuationRiverSnapshot(payload);
    if (!vm.enabled) throw new Error('expected enabled vm');
    expect(vm.isPartial).toBe(true);
  });

  it('never emits forbidden fields regardless of malicious/extra input keys', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.targetPrice = 1500;
    payload.fairValue = 1400;
    payload.recommendation = 'buy';
    const vm = adaptValuationRiverSnapshot(payload);
    const blob = JSON.stringify(vm);
    for (const forbidden of ['targetPrice', 'fairValue', 'recommendation', 'buySignal', 'sellSignal']) {
      expect(blob).not.toContain(forbidden);
    }
  });
});

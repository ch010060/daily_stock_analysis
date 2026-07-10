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

  it('labels TW eps_kind as implied and surfaces actual/forward eps stats', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.epsKind = 'implied';
    payload.epsSource = 'finmind';
    payload.epsPeriod = 'point_in_time';
    (payload.current as Record<string, unknown>).eps_actual = { value: 22.08, period: 'quarterly', source: 'finmind' };
    (payload.current as Record<string, unknown>).eps_forward = null;
    (payload.quality as Record<string, unknown>).codes = ['missing_bvps'];

    const vm = adaptValuationRiverSnapshot(payload);
    expect(vm.enabled).toBe(true);
    if (!vm.enabled) throw new Error('expected enabled vm');
    expect(vm.method).toBe('per_implied_eps_river');
    expect(vm.epsKind).toBe('implied');
    expect(vm.codes).toEqual(['missing_bvps']);
    expect(vm.current.epsActual).toEqual({ value: 22.08, period: 'quarterly', source: 'finmind' });
    expect(vm.current.epsForward).toBeNull();
  });

  it('labels US eps_kind as reported and never confuses it with implied', () => {
    const payload = {
      enabled: true,
      market: 'us',
      symbol: 'AAPL',
      currency: 'USD',
      source: 'yfinance',
      method: 'us_reported_eps_annual_river',
      basis: 'reported_eps',
      epsKind: 'reported',
      epsSource: 'yfinance',
      epsPeriod: 'annual',
      bandMultiples: [14, 18, 22, 26, 30, 34, 38],
      neutralMultiple: 26,
      range: { startDate: '2025-10-01', endDate: '2025-10-02', tradingDays: 2 },
      points: [
        { date: '2025-10-01', close: 200, per: 26.8, impliedEps: 7.46, bands: { per26: 194.0 } },
        { date: '2025-10-02', close: 201, per: 26.9, impliedEps: 7.46, bands: { per26: 194.0 } },
      ],
      current: {
        close: 201, per: 26.9, pbr: 40.3, impliedEps: 7.46, impliedBvps: 4.99, zone: 'overvalued',
        epsActual: { value: 8.35, period: 'ttm', source: 'yfinance' },
        epsForward: { value: 9.60895, period: 'point_in_time', source: 'yfinance' },
      },
      quality: { status: 'ok', warnings: [], codes: [], methodologyNote: 'note' },
    };

    const vm = adaptValuationRiverSnapshot(payload);
    expect(vm.enabled).toBe(true);
    if (!vm.enabled) throw new Error('expected enabled vm');
    expect(vm.epsKind).toBe('reported');
    expect(vm.current.impliedEps).toBe(7.46);
    expect(vm.current.impliedBvps).toBe(4.99);
    expect(vm.current.pbr).toBe(40.3);
    expect(vm.current.epsActual?.value).toBe(8.35);
    expect(vm.current.epsForward?.value).toBe(9.60895);
    // the annual-anchor EPS the bands are built from must never equal the
    // TTM actual EPS reference stat by construction of this fixture
    expect(vm.current.impliedEps).not.toBe(vm.current.epsActual?.value);
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
    const emptyFallback = {
      enabled: false,
      market: null,
      reason: '尚無估值河流圖資料',
      epsActual: null,
      epsForward: null,
    };
    expect(adaptValuationRiverSnapshot(undefined)).toEqual(emptyFallback);
    expect(adaptValuationRiverSnapshot(null)).toEqual(emptyFallback);
    expect(adaptValuationRiverSnapshot('not-an-object')).toEqual(emptyFallback);
    expect(adaptValuationRiverSnapshot([1, 2, 3])).toEqual(emptyFallback);
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
      epsActual: null,
      epsForward: null,
    });
  });

  it('surfaces point-in-time eps_actual/eps_forward even when the river itself is unsupported', () => {
    const vm = adaptValuationRiverSnapshot({
      enabled: false,
      market: 'us',
      quality: { status: 'unsupported', warnings: ['yfinance 年度財報 EPS 資料點過少'] },
      current: {
        epsActual: { value: 8.35, period: 'ttm', source: 'yfinance' },
        epsForward: { value: 9.6, period: 'point_in_time', source: 'yfinance' },
      },
    });
    expect(vm.enabled).toBe(false);
    if (vm.enabled) throw new Error('expected disabled vm');
    expect(vm.epsActual).toEqual({ value: 8.35, period: 'ttm', source: 'yfinance' });
    expect(vm.epsForward).toEqual({ value: 9.6, period: 'point_in_time', source: 'yfinance' });
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

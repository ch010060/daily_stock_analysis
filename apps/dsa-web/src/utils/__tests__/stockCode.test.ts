import { describe, expect, it } from 'vitest';
import { normalizeStockCode } from '../stockCode';

describe('normalizeStockCode', () => {
  it('keeps clean TW stock and ETF codes as-is', () => {
    expect(normalizeStockCode('2330')).toBe('2330');
    expect(normalizeStockCode('006208')).toBe('006208');
    expect(normalizeStockCode('00981A')).toBe('00981A');
  });

  it('strips TW prefix', () => {
    expect(normalizeStockCode('TW:2330')).toBe('2330');
    expect(normalizeStockCode('TW:00981A')).toBe('00981A');
  });

  it('strips TW suffix', () => {
    expect(normalizeStockCode('2330.TW')).toBe('2330');
    expect(normalizeStockCode('00981A.TW')).toBe('00981A');
  });

  it('keeps US tickers as-is', () => {
    expect(normalizeStockCode('AAPL')).toBe('AAPL');
    expect(normalizeStockCode('TSLA')).toBe('TSLA');
    expect(normalizeStockCode('GOOGL')).toBe('GOOGL');
  });

  it('strips US prefix and suffix', () => {
    expect(normalizeStockCode('US:AAPL')).toBe('AAPL');
    expect(normalizeStockCode('AAPL.US')).toBe('AAPL');
  });

  it('handles TW variants as equivalent', () => {
    const codes = ['2330', 'TW:2330', '2330.TW'];
    const normalized = codes.map(normalizeStockCode);
    expect(new Set(normalized).size).toBe(1);
    expect(normalized[0]).toBe('2330');
  });

  it('handles US variants as equivalent', () => {
    const codes = ['AAPL', 'US:AAPL', 'AAPL.US'];
    const normalized = codes.map(normalizeStockCode);
    expect(new Set(normalized).size).toBe(1);
    expect(normalized[0]).toBe('AAPL');
  });
});

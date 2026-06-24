import { describe, expect, it } from 'vitest';
import { extractStockCodeFromMessage } from '../chatStockCode';

describe('extractStockCodeFromMessage', () => {
  it('extracts a plain TW code', () => {
    expect(extractStockCodeFromMessage('幫我看看2330')).toBe('2330');
  });

  it('extracts a plain US ticker', () => {
    expect(extractStockCodeFromMessage('look at AAPL')).toBe('AAPL');
  });

  it('does not treat finance jargon as a ticker', () => {
    expect(extractStockCodeFromMessage('what is the TTM revenue')).toBeNull();
    expect(extractStockCodeFromMessage('check the EBITDA margin')).toBeNull();
  });

  it('does not treat common English filler words as a ticker', () => {
    expect(extractStockCodeFromMessage("let's GO now")).toBeNull();
  });
});

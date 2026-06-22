import { describe, expect, it } from 'vitest';
import { isObviouslyInvalidStockQuery, validateStockCode } from '../validation';

describe('stock input validation', () => {
  it.each(['S&P500', 'S&P 500', '^GSPC', 'SP500', '標普500', '標普500指數'])(
    'accepts natural S&P500 input %s as a supported index target',
    (input) => {
      expect(isObviouslyInvalidStockQuery(input)).toBe(false);
      expect(validateStockCode(input)).toMatchObject({
        valid: true,
        normalized: 'SPX',
      });
    },
  );

  it('keeps SPY as SPY instead of treating it as a fuzzy company-name query', () => {
    expect(isObviouslyInvalidStockQuery('SPY')).toBe(false);
    expect(validateStockCode('SPY')).toMatchObject({
      valid: true,
      normalized: 'SPY',
    });
  });

  it.each([
    '群聯',
    'Phison',
    'Meta Platforms',
    'Facebook',
    '台達電',
    'Delta Electronics',
    '廣達',
    'Quanta',
    '緯穎',
    'Wiwynn',
    '奇鋐',
    'Asia Vital Components',
    '金像電',
    'Kinsus',
    '智邦',
    'Accton',
    '欣興',
    'Unimicron',
    '世芯-KY',
    'Alchip',
    'Microsoft',
    'Google',
    'Amazon',
    'Tesla',
    'Broadcom',
    'Advanced Micro Devices',
    'Micron',
    'Arm Holdings',
    'Oracle',
    'Palantir',
  ])(
    'allows supported natural name %s to reach backend resolver',
    (input) => {
      expect(isObviouslyInvalidStockQuery(input)).toBe(false);
    },
  );
});

/**
 * normalizeQuery Unit Tests
 *
 * Test various edge cases for query string normalization functions
 */

import {
  normalizeQuery,
  isChineseChar,
  containsChinese,
  extractMarketSuffix,
  removeMarketSuffix,
  normalizeStockCode,
  isStockCodeLike,
  isStockNameLike,
  isPinyinLike,
} from '../normalizeQuery';
import { describe, expect, test } from 'vitest';

describe('normalizeQuery', () => {
  describe('normalizeQuery - Query normalization', () => {
    test('removes leading and trailing spaces', () => {
      expect(normalizeQuery('  2330  ')).toBe('2330');
      expect(normalizeQuery('  台積電  ')).toBe('台積電');
    });

    test('converts to lowercase', () => {
      expect(normalizeQuery('AAPL')).toBe('aapl');
      expect(normalizeQuery('PHISON')).toBe('phison');
    });

    test('removes internal extra spaces', () => {
      expect(normalizeQuery('00981 A')).toBe('00981a');
      expect(normalizeQuery('Meta  Platforms')).toBe('metaplatforms');
    });

    test('combines space and case operations', () => {
      expect(normalizeQuery('  AAPL  US  ')).toBe('aaplus');
    });

    test('normalizes full-width latin characters to ASCII', () => {
      expect(normalizeQuery('台積電Ａ')).toBe('台積電a');
      expect(normalizeQuery('tsmcＡ')).toBe('tsmca');
    });

    test('handles empty strings', () => {
      expect(normalizeQuery('')).toBe('');
      expect(normalizeQuery('   ')).toBe('');
    });

    test('preserves special characters', () => {
      expect(normalizeQuery('2330.TW')).toBe('2330.tw');
      expect(normalizeQuery('AAPL.US')).toBe('aapl.us');
    });
  });

  describe('isChineseChar - Chinese character detection', () => {
    test('identifies Chinese characters', () => {
      expect(isChineseChar('積')).toBe(true);
      expect(isChineseChar('臺')).toBe(true);
      expect(isChineseChar('股')).toBe(true);
    });

    test('rejects non-Chinese characters', () => {
      expect(isChineseChar('A')).toBe(false);
      expect(isChineseChar('1')).toBe(false);
      expect(isChineseChar('.')).toBe(false);
      expect(isChineseChar(' ')).toBe(false);
    });

    test('boundary characters: CJK range', () => {
      // 一  (\u4e00)
      expect(isChineseChar('\u4e00')).toBe(true);
      // 龥  (\u9fa5)
      expect(isChineseChar('\u9fa5')).toBe(true);
      // Out of range
      expect(isChineseChar('\u9fa6')).toBe(false);
    });
  });

  describe('containsChinese - Contains Chinese detection', () => {
    test('pure Chinese strings', () => {
      expect(containsChinese('台積電')).toBe(true);
      expect(containsChinese('群聯')).toBe(true);
    });

    test('mixed Chinese-English strings', () => {
      expect(containsChinese('2330台積電')).toBe(true);
      expect(containsChinese('AAPL蘋果')).toBe(true);
    });

    test('pure English strings', () => {
      expect(containsChinese('AAPL')).toBe(false);
      expect(containsChinese('metaplatforms')).toBe(false);
    });

    test('pure numeric strings', () => {
      expect(containsChinese('2330')).toBe(false);
      expect(containsChinese('AAPL')).toBe(false);
    });

    test('empty strings', () => {
      expect(containsChinese('')).toBe(false);
    });
  });

  describe('extractMarketSuffix - Extract market suffix', () => {
    test('extracts TW market suffix', () => {
      expect(extractMarketSuffix('2330.TW')).toBe('TW');
      expect(extractMarketSuffix('00981A.TW')).toBe('TW');
    });

    test('extracts US stock market suffix', () => {
      expect(extractMarketSuffix('AAPL.US')).toBe('US');
    });

    test('returns null for no market suffix', () => {
      expect(extractMarketSuffix('2330')).toBeNull();
      expect(extractMarketSuffix('AAPL')).toBeNull();
      expect(extractMarketSuffix('')).toBeNull();
    });

    test('handles multiple dots', () => {
      expect(extractMarketSuffix('2330.TW.TEST')).toBe('TEST');
    });
  });

  describe('removeMarketSuffix - Remove market suffix', () => {
    test('removes TW market suffix', () => {
      expect(removeMarketSuffix('2330.TW')).toBe('2330');
      expect(removeMarketSuffix('00981A.TW')).toBe('00981A');
    });

    test('removes US stock market suffix', () => {
      expect(removeMarketSuffix('AAPL.US')).toBe('AAPL');
    });

    test('keeps unchanged without market suffix', () => {
      expect(removeMarketSuffix('2330')).toBe('2330');
      expect(removeMarketSuffix('AAPL')).toBe('AAPL');
    });

    test('handles empty strings', () => {
      expect(removeMarketSuffix('')).toBe('');
    });
  });

  describe('normalizeStockCode - Stock code normalization', () => {
    test('converts to uppercase', () => {
      expect(normalizeStockCode('aapl')).toBe('AAPL');
      expect(normalizeStockCode('phison')).toBe('PHISON');
    });

    test('removes spaces', () => {
      expect(normalizeStockCode('00981 A')).toBe('00981A');
      expect(normalizeStockCode('AAPL US')).toBe('AAPLUS');
    });

    test('preserves market suffix', () => {
      expect(normalizeStockCode('2330.TW')).toBe('2330.TW');
      expect(normalizeStockCode('AAPL.US')).toBe('AAPL.US');
    });

    test('removes leading and trailing spaces', () => {
      expect(normalizeStockCode('  2330.TW  ')).toBe('2330.TW');
    });

    test('combines operations', () => {
      expect(normalizeStockCode('  aapl.us  ')).toBe('AAPL.US');
    });
  });

  describe('isStockCodeLike - Check if looks like stock code', () => {
    test('identifies TW numeric and ETF codes', () => {
      expect(isStockCodeLike('2330')).toBe(true);
      expect(isStockCodeLike('006208')).toBe(true);
      expect(isStockCodeLike('00981A')).toBe(true);
    });

    test('identifies codes with market suffix', () => {
      expect(isStockCodeLike('2330.TW')).toBe(true);
      // US stock codes without numbers return false for isStockCodeLike.
      // Full symbol validation is handled by the local TW/US candidate search.
      expect(isStockCodeLike('AAPL')).toBe(false);
      expect(isStockCodeLike('AAPL.US')).toBe(false);
    });

    test('handles US stock codes', () => {
      // US stock codes without numbers, isStockCodeLike designed for A-share numeric codes
      expect(isStockCodeLike('AAPL')).toBe(false);
      expect(isStockCodeLike('TSLA')).toBe(false);
      // But pure letters should be identified as pinyin
      expect(isPinyinLike('AAPL')).toBe(true);
      expect(isPinyinLike('TSLA')).toBe(true);
    });

    test('rejects Chinese names', () => {
      expect(isStockCodeLike('台積電')).toBe(false);
      expect(isStockCodeLike('群聯')).toBe(false);
    });

    test('rejects pinyin', () => {
      expect(isStockCodeLike('phison')).toBe(false);
      expect(isStockCodeLike('largan')).toBe(false);
    });

    test('identifies pure numbers', () => {
      expect(isStockCodeLike('12345')).toBe(true);
    });

    test('handles empty strings', () => {
      expect(isStockCodeLike('')).toBe(false);
    });
  });

  describe('isStockNameLike - Check if looks like stock name', () => {
    test('identifies Chinese names', () => {
      expect(isStockNameLike('台積電')).toBe(true);
      expect(isStockNameLike('群聯')).toBe(true);
      expect(isStockNameLike('國泰金')).toBe(true);
    });

    test('rejects English codes', () => {
      expect(isStockNameLike('AAPL')).toBe(false);
      expect(isStockNameLike('2330')).toBe(false);
    });

    test('rejects pinyin', () => {
      expect(isStockNameLike('phison')).toBe(false);
      expect(isStockNameLike('largan')).toBe(false);
    });

    test('identifies mixed Chinese-English', () => {
      expect(isStockNameLike('台積電2330')).toBe(true);
      expect(isStockNameLike('AAPL蘋果')).toBe(true);
    });

    test('handles empty strings', () => {
      expect(isStockNameLike('')).toBe(false);
    });
  });

  describe('isPinyinLike - Check if looks like pinyin', () => {
    test('identifies pure pinyin', () => {
      expect(isPinyinLike('phison')).toBe(true);
      expect(isPinyinLike('larganprecision')).toBe(true);
      expect(isPinyinLike('metaplatforms')).toBe(true);
    });

    test('identifies pinyin abbreviations', () => {
      expect(isPinyinLike('tsmc')).toBe(true);
      expect(isPinyinLike('umc')).toBe(true);
      expect(isPinyinLike('nvda')).toBe(true);
    });

    test('identifies uppercase pinyin', () => {
      expect(isPinyinLike('PHISON')).toBe(true);
      expect(isPinyinLike('LARGAN')).toBe(true);
    });

    test('rejects numbers', () => {
      expect(isPinyinLike('guizhou123')).toBe(false);
      expect(isPinyinLike('2330')).toBe(false);
    });

    test('rejects Chinese characters', () => {
      expect(isPinyinLike('台積電tsmc')).toBe(false);
      expect(isPinyinLike('群聯')).toBe(false);
    });

    test('handles empty strings', () => {
      expect(isPinyinLike('')).toBe(false);
    });

    test('rejects special characters', () => {
      expect(isPinyinLike('phison-tw')).toBe(false);
      expect(isPinyinLike('meta.platforms')).toBe(false);
    });
  });

  describe('Edge case comprehensive tests', () => {
    test('null and undefined', () => {
      // TypeScript should catch these at compile time, but runtime needs handling
      expect(() => normalizeQuery(null as unknown as string)).toThrow();
      expect(() => normalizeQuery(undefined as unknown as string)).toThrow();
    });

    test('extra long strings', () => {
      const longString = 'a'.repeat(10000);
      expect(() => normalizeQuery(longString)).not.toThrow();
    });

    test('special Unicode characters', () => {
      expect(normalizeQuery('股票🚀')).toBe('股票🚀');
      expect(normalizeQuery('©2023')).toBe('©2023');
    });
  });
});

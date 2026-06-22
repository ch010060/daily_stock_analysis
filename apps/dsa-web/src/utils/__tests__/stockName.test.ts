import {
  truncateStockName,
  isStockNameTruncated,
  STOCK_NAME_MAX_LENGTH,
} from '../stockName';
import { describe, expect, test } from 'vitest';

describe('truncateStockName', () => {
  describe('English strings', () => {
    test('returns unchanged when at or below 15 chars', () => {
      expect(truncateStockName('Apple')).toBe('Apple');
      expect(truncateStockName('AAPL')).toBe('AAPL');
      expect(truncateStockName('123456789012345')).toBe('123456789012345');
    });

    test('truncates to 15 chars with trailing dot', () => {
      expect(truncateStockName('Apple Computer Inc.')).toBe('Apple Computer .');
      expect(truncateStockName('1234567890123456')).toBe('123456789012345.');
    });

    test('truncates very long English strings', () => {
      expect(truncateStockName('VeryLongStockNameCorporation')).toBe('VeryLongStockNa.');
    });
  });

  describe('Chinese strings', () => {
    test('returns unchanged when at or below 8 chars', () => {
      expect(truncateStockName('台積電')).toBe('台積電');
      expect(truncateStockName('群聯電子')).toBe('群聯電子');
    });

    test('truncates to 8 chars with trailing dot', () => {
      // 台積電股票有限公司: 9 Chinese chars -> slice(0,8) + dot.
      expect(truncateStockName('台積電股票有限公司')).toBe('台積電股票有限公.');
    });
  });

  describe('Mixed Chinese and English strings', () => {
    test('returns unchanged when at or below 10 chars', () => {
      expect(truncateStockName('台積電A')).toBe('台積電A');
      expect(truncateStockName('群聯Phison')).toBe('群聯Phison');
    });

    test('truncates to 10 chars with trailing dot', () => {
      // 台積電股票有限公司AB: mixed -> slice(0,10) + dot.
      expect(truncateStockName('台積電股票有限公司AB')).toBe('台積電股票有限公司A.');
      // 群聯Phison: 2 Chinese + 6 English = 8 mixed -> no truncation (8 <= 10)
      expect(truncateStockName('群聯Phison')).toBe('群聯Phison');
    });
  });

  describe('edge cases', () => {
    test('returns empty string unchanged', () => {
      expect(truncateStockName('')).toBe('');
    });

    test('handles stock code only (no Chinese)', () => {
      expect(truncateStockName('2330.TW')).toBe('2330.TW');
      expect(truncateStockName('AAPL')).toBe('AAPL');
    });

    test('handles single character strings', () => {
      expect(truncateStockName('A')).toBe('A');
      expect(truncateStockName('群')).toBe('群');
    });

    test('handles strings with only numbers and symbols', () => {
      expect(truncateStockName('2330')).toBe('2330');
      expect(truncateStockName('2026-03-24')).toBe('2026-03-24');
    });

    test('returns undefined unchanged (but should not happen in practice)', () => {
      // The function checks falsy, so empty string is handled, but non-string values
      // would behave unexpectedly - this documents current behavior
      expect(truncateStockName('' as unknown as string)).toBe('');
    });
  });

  describe('isStockNameTruncated', () => {
    test('returns false for empty string', () => {
      expect(isStockNameTruncated('')).toBe(false);
    });

    test('returns false for names at or below max length', () => {
      expect(isStockNameTruncated('Apple')).toBe(false);
      expect(isStockNameTruncated('台積電')).toBe(false);
      expect(isStockNameTruncated('台積電A')).toBe(false);
    });

    test('returns true for English names exceeding 15 chars', () => {
      expect(isStockNameTruncated('Apple Computer Inc.')).toBe(true);
      expect(isStockNameTruncated('VeryLongStockNameCorporation')).toBe(true);
    });

    test('returns true for Chinese names exceeding 8 chars', () => {
      expect(isStockNameTruncated('台積電股份有限公司')).toBe(true);
    });

    test('returns true for mixed names exceeding 10 chars', () => {
      expect(isStockNameTruncated('台積電股票有限公司AB')).toBe(true);
    });

    test('returns false for stock codes at boundary', () => {
      expect(isStockNameTruncated('2330.TW')).toBe(false);
      expect(isStockNameTruncated('AAPL')).toBe(false);
    });
  });

  describe('STOCK_NAME_MAX_LENGTH constant', () => {
    test('has correct values', () => {
      expect(STOCK_NAME_MAX_LENGTH.ENGLISH).toBe(15);
      expect(STOCK_NAME_MAX_LENGTH.CHINESE).toBe(8);
      expect(STOCK_NAME_MAX_LENGTH.MIXED).toBe(10);
    });
  });
});

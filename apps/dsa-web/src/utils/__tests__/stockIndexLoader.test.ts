/**
 * stockIndexLoader unit tests for Route B TW/US symbol index behavior.
 */

import { beforeEach, describe, expect, test, vi } from 'vitest';
import {
  loadStockIndex,
  compressIndex,
  findStockInIndex,
  getPopularStocks,
  groupStocksByMarket,
} from '../stockIndexLoader';
import type { StockIndexItem } from '../../types/stockIndex';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as unknown as typeof fetch;

describe('stockIndexLoader', () => {
  const mockIndexData: StockIndexItem[] = [
    {
      canonicalCode: 'AAPL',
      displayCode: 'AAPL',
      nameZh: 'Apple',
      pinyinFull: 'apple',
      pinyinAbbr: 'aapl',
      aliases: ['Apple Inc'],
      market: 'US',
      exchange: 'NASDAQ',
      assetType: 'stock',
      active: true,
      popularity: 98,
    },
    {
      canonicalCode: 'META',
      displayCode: 'META',
      nameZh: 'META PLATFORMS A',
      pinyinFull: 'metaplatformsa',
      pinyinAbbr: 'meta',
      aliases: [],
      market: 'US',
      assetType: 'stock',
      active: true,
      popularity: 97,
    },
    {
      canonicalCode: '8299',
      displayCode: '8299',
      nameZh: '群聯',
      pinyinFull: 'qunlian',
      pinyinAbbr: 'ql',
      aliases: [],
      market: 'TW',
      assetType: 'stock',
      active: true,
      popularity: 94,
    },
    {
      canonicalCode: 'OLD',
      displayCode: 'OLD',
      nameZh: 'Inactive US',
      pinyinFull: 'inactiveus',
      pinyinAbbr: 'old',
      aliases: [],
      market: 'US',
      assetType: 'stock',
      active: false,
      popularity: 80,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('loadStockIndex', () => {
    test('loads object format and filters unsupported markets', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockIndexData,
      } as unknown as Response);

      const result = await loadStockIndex();

      expect(result.loaded).toBe(true);
      expect(result.fallback).toBe(false);
      expect(result.data.every((item) => item.market === 'TW' || item.market === 'US')).toBe(true);
      expect(result.error).toBeUndefined();
    });

    test('loads compressed tuple format and still appends required Route B instruments', async () => {
      const compressedData = [
        ['AAPL', 'AAPL', 'Apple', 'apple', 'aapl', ['Apple Inc'], 'US', 'stock', true, 98, 'NASDAQ'],
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => compressedData,
      } as unknown as Response);

      const result = await loadStockIndex();

      expect(result.loaded).toBe(true);
      expect(result.data).toEqual(expect.arrayContaining([
        expect.objectContaining({ canonicalCode: 'AAPL', market: 'US', exchange: 'NASDAQ' }),
        expect.objectContaining({ canonicalCode: '8299', market: 'TW' }),
        expect.objectContaining({ canonicalCode: '006208', market: 'TW', assetType: 'etf' }),
        expect.objectContaining({ canonicalCode: '00981A', market: 'TW', assetType: 'etf' }),
        expect.objectContaining({ canonicalCode: 'META', market: 'US' }),
        expect.objectContaining({ canonicalCode: 'SPY', market: 'US' }),
        expect.objectContaining({ canonicalCode: 'SPX', market: 'US', assetType: 'index' }),
      ]));
    });

    test('merges required aliases into existing provider records', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockIndexData,
      } as unknown as Response);

      const result = await loadStockIndex();
      const meta = result.data.find((item) => item.canonicalCode === 'META');
      const phison = result.data.find((item) => item.canonicalCode === '8299');

      expect(meta).toBeDefined();
      expect(meta?.aliases).toEqual(expect.arrayContaining(['Facebook', 'Meta', 'Meta Platforms Inc']));
      expect(phison).toBeDefined();
      expect(phison?.aliases).toEqual(expect.arrayContaining(['Phison', 'Phison Electronics']));
    });

    test('adds required Route B instruments when the served index is missing them', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as unknown as Response);

      const result = await loadStockIndex();
      const byCode = new Map(result.data.map((item) => [item.canonicalCode, item]));

      expect(result.data).toEqual(expect.arrayContaining([
        expect.objectContaining({ canonicalCode: '2330', nameZh: '台積電', market: 'TW' }),
        expect.objectContaining({ canonicalCode: '3008', nameZh: '大立光', market: 'TW' }),
        expect.objectContaining({ canonicalCode: '8299', nameZh: '群聯', market: 'TW' }),
        expect.objectContaining({ canonicalCode: 'META', nameZh: 'Meta Platforms', market: 'US' }),
        expect.objectContaining({ canonicalCode: 'NVDA', nameZh: 'NVIDIA', market: 'US' }),
      ]));
      for (const [code, name] of [
        ['2308', '台達電'],
        ['2382', '廣達'],
        ['6669', '緯穎'],
        ['3017', '奇鋐'],
        ['2368', '金像電'],
        ['2345', '智邦'],
        ['3037', '欣興'],
        ['3661', '世芯-KY'],
        ['2303', '聯電'],
        ['2882', '國泰金'],
        ['006208', '富邦台50'],
        ['00981A', '主動統一台股增長'],
        ['MSFT', 'Microsoft'],
        ['GOOGL', 'Alphabet'],
        ['AMZN', 'Amazon'],
        ['TSLA', 'Tesla'],
        ['AVGO', 'Broadcom'],
        ['AMD', 'Advanced Micro Devices'],
        ['MU', 'Micron Technology'],
        ['ARM', 'Arm Holdings'],
        ['ORCL', 'Oracle'],
        ['PLTR', 'Palantir Technologies'],
      ]) {
        expect(byCode.get(code)).toMatchObject({ canonicalCode: code, nameZh: name });
      }
    });

    test('returns fallback mode on load errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const result = await loadStockIndex();

      expect(result.loaded).toBe(false);
      expect(result.fallback).toBe(true);
      expect(result.data).toEqual([]);
      expect(result.error).toBeInstanceOf(Error);
    });

    test('fetch call includes cache-busting parameter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as unknown as Response);

      await loadStockIndex();

      const fetchCallArgs = mockFetch.mock.calls[0][0];
      expect(fetchCallArgs).toContain('?_t=');
    });

  });

  describe('index utilities', () => {
    test('compressIndex converts object format to tuple format', () => {
      const compressed = compressIndex(mockIndexData.filter((item) => item.market === 'TW' || item.market === 'US'));

      expect(compressed[0]).toEqual([
        'AAPL',
        'AAPL',
        'Apple',
        'apple',
        'aapl',
        ['Apple Inc'],
        'US',
        'stock',
        true,
        98,
        'NASDAQ',
      ]);
    });

    test('findStockInIndex finds supported TW/US records', () => {
      const result = findStockInIndex('8299', mockIndexData);

      expect(result).not.toBeNull();
      expect(result?.nameZh).toBe('群聯');
    });

    test('findStockInIndex returns null for non-existent stock', () => {
      const result = findStockInIndex('NOTFOUND', mockIndexData);

      expect(result).toBeNull();
    });

    test('getPopularStocks filters inactive records and sorts by popularity', () => {
      const result = getPopularStocks(mockIndexData.filter((item) => item.market === 'TW' || item.market === 'US'), 3);

      expect(result).toHaveLength(3);
      expect(result[0].canonicalCode).toBe('AAPL');
      expect(result.some((item) => !item.active)).toBe(false);
    });

    test('groupStocksByMarket groups supported markets', () => {
      const routeBItems = mockIndexData.filter((item) => item.market === 'TW' || item.market === 'US');
      const result = groupStocksByMarket(routeBItems);

      expect(result.size).toBe(2);
      expect(result.get('TW')).toHaveLength(1);
      expect(result.get('US')).toHaveLength(2);
    });

    test('handles large Route B datasets', () => {
      const largeIndex: StockIndexItem[] = Array.from({ length: 10000 }, (_, i) => ({
        canonicalCode: `TEST${i}`,
        displayCode: `TEST${i}`,
        nameZh: `Test ${i}`,
        pinyinFull: `test${i}`,
        pinyinAbbr: `t${i}`,
        aliases: [],
        market: 'US',
        assetType: 'stock',
        active: i % 2 === 0,
        popularity: i % 100,
      }));

      expect(() => compressIndex(largeIndex)).not.toThrow();
      expect(() => findStockInIndex('TEST5000', largeIndex)).not.toThrow();
      expect(() => getPopularStocks(largeIndex, 10)).not.toThrow();
    });
  });
});

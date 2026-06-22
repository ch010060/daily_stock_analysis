/**
 * useAutocomplete hook tests.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAutocomplete } from '../useAutocomplete';
import type { StockIndexItem } from '../../types/stockIndex';

const searchStocksMock = vi.fn();

vi.mock('../../utils/searchStocks', () => ({
  searchStocks: (...args: unknown[]) => searchStocksMock(...args),
}));

const mockIndex: StockIndexItem[] = [
  {
    canonicalCode: 'TW:2330',
    displayCode: '2330',
    nameZh: '台積電',
    pinyinFull: 'taijidian',
    pinyinAbbr: 'tjd',
    aliases: ['台積電', 'TSMC'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 100,
  },
];

describe('useAutocomplete', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('activates runtime fallback when search throws', () => {
    searchStocksMock.mockImplementation(() => {
      throw new Error('Search exploded');
    });

    const { result } = renderHook(() => useAutocomplete(mockIndex, { debounceMs: 10 }));

    act(() => {
      result.current.setQuery('2330');
    });

    act(() => {
      vi.advanceTimersByTime(10);
    });

    expect(result.current.runtimeFallback).toBe(true);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.isOpen).toBe(false);
    expect(result.current.suggestions).toEqual([]);
  });

  it('keeps suggestions open without auto-highlighting the first result', () => {
    searchStocksMock.mockReturnValue([
      {
        canonicalCode: '2330.TW',
        displayCode: '2330',
        nameZh: '台積電',
        market: 'TW',
        matchType: 'exact',
        matchField: 'code',
        score: 100,
      },
    ]);

    const { result } = renderHook(() => useAutocomplete(mockIndex, { debounceMs: 10 }));

    act(() => {
      result.current.setQuery('2330');
    });

    act(() => {
      vi.advanceTimersByTime(10);
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.suggestions).toHaveLength(1);
    expect(result.current.highlightedIndex).toBe(-1);
  });
});

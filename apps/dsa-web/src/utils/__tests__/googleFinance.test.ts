import { describe, expect, it } from 'vitest';
import {
  buildGoogleFinanceQuoteUrl,
  buildGoogleFinanceResearchPrompt,
  inferGoogleFinanceMarket,
  normalizeGoogleFinanceExchange,
} from '../googleFinance';

describe('googleFinance external reference helpers', () => {
  it('builds TW stock and ETF quote URLs with TPE', () => {
    expect(buildGoogleFinanceQuoteUrl({ symbol: '2330', market: 'tw' })).toBe(
      'https://www.google.com/finance/beta/quote/2330:TPE'
    );
    expect(buildGoogleFinanceQuoteUrl({ symbol: '0050', market: 'TW', assetType: 'etf' })).toBe(
      'https://www.google.com/finance/beta/quote/0050:TPE'
    );
  });

  it('builds US quote URLs only from explicit trusted exchange metadata', () => {
    expect(buildGoogleFinanceQuoteUrl({ symbol: ' mu ', market: 'us', exchange: 'NASDAQ' })).toBe(
      'https://www.google.com/finance/beta/quote/MU:NASDAQ'
    );
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'SPY', market: 'US', exchange: 'NYSE Arca' })).toBe(
      'https://www.google.com/finance/beta/quote/SPY:NYSEARCA'
    );
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'QQQ', market: 'US', exchange: 'NASDAQ' })).toBe(
      'https://www.google.com/finance/beta/quote/QQQ:NASDAQ'
    );
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'NOW', market: 'us', exchange: 'NYSE' })).toBe(
      'https://www.google.com/finance/beta/quote/NOW:NYSE'
    );
  });

  it('returns null for unknown exchange, unsupported market, and malformed symbols', () => {
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'ABC', market: 'us', exchange: null })).toBeNull();
    expect(buildGoogleFinanceQuoteUrl({ symbol: '0700', market: 'eu', exchange: 'EURONEXT' } as never)).toBeNull();
    expect(buildGoogleFinanceQuoteUrl({ symbol: '123456', market: 'tw' })).toBeNull();
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'BRK/B', market: 'us', exchange: 'NYSE' })).toBeNull();
    expect(buildGoogleFinanceQuoteUrl({ symbol: '   ', market: 'tw' })).toBeNull();
  });

  it('does not infer US exchange from stock or ETF type alone', () => {
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'SPY', market: 'US', assetType: 'etf' })).toBeNull();
    expect(buildGoogleFinanceQuoteUrl({ symbol: 'MU', market: 'US', assetType: 'stock' })).toBeNull();
  });

  it('normalizes only approved exchange namespaces', () => {
    expect(normalizeGoogleFinanceExchange('NasdaqGS')).toBe('NASDAQ');
    expect(normalizeGoogleFinanceExchange('NYSE Arca')).toBe('NYSEARCA');
    expect(normalizeGoogleFinanceExchange('PCX')).toBe('NYSEARCA');
    expect(normalizeGoogleFinanceExchange('NYSE American')).toBe('NYSEAMERICAN');
    expect(normalizeGoogleFinanceExchange('CBOE')).toBeNull();
  });

  it('builds a safe zh_TW research prompt without report body text', () => {
    expect(buildGoogleFinanceResearchPrompt({ symbol: '2330', market: 'tw', name: '台積電' })).toBe(
      '請分析 2330 台積電 近期是否適合長期持有，請結合股價趨勢、財報、新聞、估值與主要風險。'
    );
    expect(buildGoogleFinanceResearchPrompt({ symbol: 'MU', market: 'us' })).toBe(
      '請分析 MU 近期是否適合長期持有，請結合股價趨勢、財報、新聞、估值與主要風險。'
    );
  });
});

it('infers only supported TW-style and approved US-style market scopes', () => {
  expect(inferGoogleFinanceMarket('2330')).toBe('tw');
  expect(inferGoogleFinanceMarket('00981A')).toBe('tw');
  expect(inferGoogleFinanceMarket('MU')).toBe('us');
  expect(inferGoogleFinanceMarket('123456')).toBeNull();
});

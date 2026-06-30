/**
 * searchStocks unit tests for Route B TW/US symbol lookup.
 */

import { describe, expect, test } from 'vitest';
import { searchStocks } from '../searchStocks';
import type { StockIndexItem } from '../../types/stockIndex';

const stock = (
  canonicalCode: string,
  nameZh: string,
  market: 'TW' | 'US',
  aliases: string[] = [],
  popularity = 90,
  exchange: string | null = null,
): StockIndexItem => ({
  canonicalCode,
  displayCode: canonicalCode,
  nameZh,
  pinyinFull: nameZh.toLowerCase(),
  pinyinAbbr: canonicalCode.toLowerCase(),
  aliases,
  market,
  exchange,
  assetType: 'stock',
  active: true,
  popularity,
});

const expandedMatrixIndex: StockIndexItem[] = [
  stock('2308', '台達電', 'TW', ['Delta Electronics'], 95),
  stock('2382', '廣達', 'TW', ['Quanta'], 95),
  stock('6669', '緯穎', 'TW', ['Wiwynn'], 95),
  stock('3017', '奇鋐', 'TW', ['AVC', 'Asia Vital Components'], 95),
  stock('2368', '金像電', 'TW', ['Kinsus'], 95),
  stock('2345', '智邦', 'TW', ['Accton'], 95),
  stock('3037', '欣興', 'TW', ['Unimicron'], 95),
  stock('3661', '世芯-KY', 'TW', ['世芯', 'Alchip'], 95),
  stock('2303', '聯電', 'TW', ['UMC'], 95),
  stock('2882', '國泰金', 'TW', ['Cathay Financial'], 95),
  stock('3231', '緯創', 'TW', ['Wistron'], 95),
  stock('2356', '英業達', 'TW', ['Inventec'], 95),
  stock('2376', '技嘉', 'TW', ['Gigabyte'], 95),
  stock('2408', '南亞科', 'TW', ['Nanya Technology'], 95),
  stock('2409', '友達', 'TW', ['AUO'], 95),
  stock('2002', '中鋼', 'TW', ['China Steel'], 95),
  stock('2891', '中信金', 'TW', ['CTBC Financial'], 95),
  stock('2892', '第一金', 'TW', ['First Financial'], 95),
  stock('5880', '合庫金', 'TW', ['Taiwan Cooperative Financial'], 95),
  stock('1101', '台泥', 'TW', ['Taiwan Cement'], 95),
  stock('1402', '遠東新', 'TW', ['Far Eastern New Century'], 95),
  stock('MSFT', 'Microsoft', 'US', ['Microsoft Corporation'], 95),
  stock('GOOGL', 'Alphabet', 'US', ['Google'], 95),
  stock('AMZN', 'Amazon', 'US', ['Amazon.com'], 95),
  stock('TSLA', 'Tesla', 'US', ['Tesla Inc'], 95),
  stock('AVGO', 'Broadcom', 'US', ['Broadcom Inc.'], 95),
  stock('AMD', 'Advanced Micro Devices', 'US', ['AMD'], 95),
  stock('MU', 'Micron Technology', 'US', ['Micron'], 95),
  stock('ARM', 'Arm Holdings', 'US', ['Arm'], 95),
  stock('ORCL', 'Oracle', 'US', ['Oracle Corporation'], 95),
  stock('PLTR', 'Palantir Technologies', 'US', ['Palantir'], 95),
  stock('CRM', 'Salesforce', 'US', ['Salesforce Inc'], 95),
  stock('IBM', 'IBM', 'US', ['International Business Machines'], 95),
  stock('JPM', 'JPMorgan Chase', 'US', ['JPMorgan Chase & Co'], 95),
  stock('BAC', 'Bank of America', 'US', ['Bank of America Corporation'], 95),
  stock('WMT', 'Walmart', 'US', ['Walmart Inc'], 95),
  stock('HD', 'Home Depot', 'US', ['The Home Depot'], 95),
  stock('DIS', 'Disney', 'US', ['Walt Disney'], 95),
  stock('UBER', 'Uber', 'US', ['Uber Technologies'], 95),
  stock('SNOW', 'Snowflake', 'US', ['Snowflake Inc'], 95),
  stock('GE', 'General Electric', 'US', ['GE Aerospace'], 95),
  stock('CAT', 'Caterpillar', 'US', ['Caterpillar Inc'], 95),
  stock('CSCO', 'Cisco', 'US', ['Cisco Systems'], 95),
  stock('COST', 'Costco', 'US', ['Costco Wholesale'], 95),
  stock('POR', 'Portland General Electric', 'US', [], 70),
  stock('THFF', 'First Financial', 'US', ['First Financial Corporation'], 70),
];

const mockIndex: StockIndexItem[] = [
  {
    canonicalCode: '2330',
    displayCode: '2330',
    nameZh: '台積電',
    pinyinFull: 'taijidian',
    pinyinAbbr: 'tjd',
    aliases: ['台灣積體電路', 'TSMC', 'Taiwan Semiconductor'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 100,
  },
  {
    canonicalCode: '3008',
    displayCode: '3008',
    nameZh: '大立光',
    pinyinFull: 'daliguang',
    pinyinAbbr: 'dlg',
    aliases: ['大立光精密', 'Largan', 'Largan Precision'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 96,
  },
  {
    canonicalCode: '8299',
    displayCode: '8299',
    nameZh: '群聯',
    pinyinFull: 'qunlian',
    pinyinAbbr: 'ql',
    aliases: ['群聯電子', 'Phison', 'Phison Electronics'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 94,
  },
  ...expandedMatrixIndex,
  {
    canonicalCode: 'AAPL',
    displayCode: 'AAPL',
    nameZh: 'Apple',
    pinyinFull: 'apple',
    pinyinAbbr: 'aapl',
    aliases: ['Apple Inc'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 98,
  },
  {
    canonicalCode: 'NVDA',
    displayCode: 'NVDA',
    nameZh: 'NVIDIA',
    pinyinFull: 'nvidia',
    pinyinAbbr: 'nvda',
    aliases: ['NVIDIA Corporation', 'Nvidia'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 98,
  },
  {
    canonicalCode: 'META',
    displayCode: 'META',
    nameZh: 'Meta Platforms',
    pinyinFull: 'metaplatforms',
    pinyinAbbr: 'meta',
    aliases: ['Facebook', 'Meta', 'Meta Platforms Inc'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 97,
  },
  {
    canonicalCode: 'SPX',
    displayCode: 'SPX',
    nameZh: '標普500指數',
    pinyinFull: 'biaopu500zhishu',
    pinyinAbbr: 'bp500zs',
    aliases: ['S&P500', 'S&P 500', '^GSPC', 'SP500', '標普500'],
    market: 'US',
    assetType: 'index',
    active: true,
    popularity: 99,
  },
  {
    canonicalCode: 'SPY',
    displayCode: 'SPY',
    nameZh: 'SPDR S&P 500 ETF',
    pinyinFull: 'spdrs&p500etf',
    pinyinAbbr: 'spy',
    aliases: ['SPDR S&P 500', 'SPY ETF'],
    market: 'US',
    assetType: 'etf',
    active: true,
    popularity: 97,
  },
  {
    canonicalCode: '00981A',
    displayCode: '00981A',
    nameZh: '主動統一台股增長',
    pinyinFull: 'zhudongtongyitaiguzengzhang',
    pinyinAbbr: 'zdtytgzz',
    aliases: [],
    market: 'TW',
    assetType: 'etf',
    active: true,
    popularity: 97,
  },
  {
    canonicalCode: '006208',
    displayCode: '006208',
    nameZh: '富邦台50',
    pinyinFull: 'fubangtai50',
    pinyinAbbr: 'fbt50',
    aliases: [],
    market: 'TW',
    assetType: 'etf',
    active: true,
    popularity: 97,
  },
  {
    canonicalCode: 'SYRE',
    displayCode: 'SYRE',
    nameZh: 'Spyre Therapeutics',
    pinyinFull: 'spyretherapeutics',
    pinyinAbbr: 'syre',
    aliases: ['Spyre'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 25,
  },
  {
    canonicalCode: 'OLD.US',
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

describe('searchStocks', () => {
  test('preserves exchange metadata in US stock suggestions', () => {
    const results = searchStocks('LLY', [
      stock('LLY', 'Eli Lilly', 'US', ['Eli Lilly and Company'], 90, 'NYSE'),
    ]);

    expect(results[0]).toMatchObject({
      canonicalCode: 'LLY',
      market: 'US',
      exchange: 'NYSE',
    });
  });

  test.each([
    ['2330', '2330', 'code', 'exact'],
    ['台積電', '2330', 'name', 'exact'],
    ['TSMC', '2330', 'alias', 'exact'],
    ['大立光', '3008', 'name', 'exact'],
    ['Largan', '3008', 'alias', 'exact'],
    ['群聯', '8299', 'name', 'exact'],
    ['8299', '8299', 'code', 'exact'],
    ['Phison', '8299', 'alias', 'exact'],
    ['NVIDIA', 'NVDA', 'name', 'exact'],
    ['NVDA', 'NVDA', 'code', 'exact'],
    ['META', 'META', 'code', 'exact'],
    ['Meta Platforms', 'META', 'name', 'exact'],
    ['Facebook', 'META', 'alias', 'exact'],
  ])('returns the canonical TW/US candidate for %s', (query, expectedCode, matchField, matchType) => {
    const results = searchStocks(query, mockIndex);

    expect(results.length).toBeGreaterThan(0);
    expect(results[0]).toMatchObject({
      canonicalCode: expectedCode,
      matchField,
      matchType,
    });
    expect(results.every((result) => result.market === 'TW' || result.market === 'US')).toBe(true);
  });

  test.each([
    ['2308', '2308'],
    ['台達電', '2308'],
    ['Delta Electronics', '2308'],
    ['2382', '2382'],
    ['廣達', '2382'],
    ['Quanta', '2382'],
    ['6669', '6669'],
    ['緯穎', '6669'],
    ['Wiwynn', '6669'],
    ['3017', '3017'],
    ['奇鋐', '3017'],
    ['AVC', '3017'],
    ['2368', '2368'],
    ['金像電', '2368'],
    ['Kinsus', '2368'],
    ['2345', '2345'],
    ['智邦', '2345'],
    ['Accton', '2345'],
    ['3037', '3037'],
    ['欣興', '3037'],
    ['Unimicron', '3037'],
    ['3661', '3661'],
    ['世芯', '3661'],
    ['Alchip', '3661'],
    ['Microsoft', 'MSFT'],
    ['Google', 'GOOGL'],
    ['Amazon', 'AMZN'],
    ['Tesla', 'TSLA'],
    ['Broadcom', 'AVGO'],
    ['AMD', 'AMD'],
    ['Micron', 'MU'],
    ['Arm', 'ARM'],
    ['Oracle', 'ORCL'],
    ['Palantir', 'PLTR'],
    ['Wistron', '3231'],
    ['Inventec', '2356'],
    ['Gigabyte', '2376'],
    ['Nanya Technology', '2408'],
    ['AUO', '2409'],
    ['China Steel', '2002'],
    ['CTBC Financial', '2891'],
    ['Taiwan Cooperative Financial', '5880'],
    ['Taiwan Cement', '1101'],
    ['Far Eastern New Century', '1402'],
    ['Salesforce', 'CRM'],
    ['International Business Machines', 'IBM'],
    ['JPMorgan Chase', 'JPM'],
    ['Bank of America', 'BAC'],
    ['Walmart', 'WMT'],
    ['Home Depot', 'HD'],
    ['Disney', 'DIS'],
    ['Uber', 'UBER'],
    ['Snowflake', 'SNOW'],
    ['General Electric', 'GE'],
    ['Caterpillar', 'CAT'],
    ['Cisco', 'CSCO'],
    ['Costco', 'COST'],
    ['00981A', '00981A'],
    ['主動統一台股增長', '00981A'],
    ['006208', '006208'],
    ['富邦台50', '006208'],
  ])('returns expanded matrix candidate for %s', (query, expectedCode) => {
    const results = searchStocks(query, mockIndex);

    expect(results.length).toBeGreaterThan(0);
    expect(results[0].canonicalCode).toBe(expectedCode);
    expect(results.every((result) => result.market === 'TW' || result.market === 'US')).toBe(true);
  });

  test.each(['S&P500', 'S&P 500', '^GSPC', 'SP500', '標普500'])(
    'maps natural S&P500 query %s to SPX',
    (query) => {
      const results = searchStocks(query, mockIndex);

      expect(results.length).toBeGreaterThan(0);
      expect(results[0]).toMatchObject({
        canonicalCode: 'SPX',
        market: 'US',
      });
    },
  );

  test('prioritizes exact SPY ticker over SYRE fuzzy/name matches', () => {
    const results = searchStocks('SPY', mockIndex);

    expect(results.length).toBeGreaterThan(0);
    expect(results[0].canonicalCode).toBe('SPY');
    expect(results[0].canonicalCode).not.toBe('SYRE');
  });

  test('does not substitute an uppercase SPY ticker query with SYRE when SPY is absent', () => {
    const indexWithoutSpy = mockIndex.filter((item) => item.canonicalCode !== 'SPY');
    const results = searchStocks('SPY', indexWithoutSpy);

    expect(results.some((item) => item.canonicalCode === 'SYRE')).toBe(false);
  });

  test('default search stays inside TW/US universe', () => {
    const results = searchStocks('8299', mockIndex);

    expect(results[0].canonicalCode).toBe('8299');
    expect(results.every((result) => result.market === 'TW' || result.market === 'US')).toBe(true);
  });

  test('keeps exact aliases ahead of substring collisions', () => {
    expect(searchStocks('General Electric', mockIndex)[0].canonicalCode).toBe('GE');
    expect(searchStocks('General Electric', mockIndex)[0].canonicalCode).not.toBe('POR');
  });

  test('returns an explicit candidate list for exact cross-market aliases without market scope', () => {
    const results = searchStocks('First Financial', mockIndex);
    const codes = results.map((result) => result.canonicalCode);

    expect(codes).toContain('2892');
    expect(codes).toContain('THFF');
    expect(results.filter((result) => result.matchType === 'exact').length).toBeGreaterThanOrEqual(2);
  });

  test('can filter exact alias collisions by explicit market scope', () => {
    const twResults = searchStocks('First Financial', mockIndex, { marketScope: 'TW' });
    const usResults = searchStocks('First Financial', mockIndex, { marketScope: 'US' });

    expect(twResults[0].canonicalCode).toBe('2892');
    expect(twResults.every((result) => result.market === 'TW')).toBe(true);
    expect(usResults[0].canonicalCode).toBe('THFF');
    expect(usResults.every((result) => result.market === 'US')).toBe(true);
  });

  test('does not silently auto-pick a TW alias over a same-named US ticker for a strict-ticker-shaped query', () => {
    const teamIndex: StockIndexItem[] = [
      ...mockIndex,
      stock('4967', '十銓', 'TW', ['TEAM'], 90),
      stock('TISI', 'Team', 'US', [], 90),
    ];

    const results = searchStocks('TEAM', teamIndex);
    const codes = results.map((result) => result.canonicalCode);

    expect(codes).toContain('4967');
    expect(codes).toContain('TISI');
    expect(results[0].canonicalCode).not.toBe('4967');
    expect(results.filter((result) => result.matchType === 'exact').length).toBeGreaterThanOrEqual(2);
  });

  test('does not return unsupported candidates even with all scope', () => {
    const results = searchStocks('非支援市場測試標的', mockIndex, { marketScope: 'all' });

    expect(results).toHaveLength(0);
  });

  test('filters out inactive stocks by default', () => {
    const results = searchStocks('OLD', mockIndex);

    expect(results).toHaveLength(0);
  });

  test('shows inactive stocks only when explicitly requested and still limited to TW/US', () => {
    const results = searchStocks('OLD', mockIndex, { activeOnly: false });

    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ canonicalCode: 'OLD.US', market: 'US' });
  });

  test('sorts by popularity when scores are tied', () => {
    const tieIndex: StockIndexItem[] = [
      {
        canonicalCode: 'AAA',
        displayCode: 'AAA',
        nameZh: 'Alpha Test',
        pinyinFull: 'alphatest',
        pinyinAbbr: 'aaa',
        aliases: [],
        market: 'US',
        assetType: 'stock',
        active: true,
        popularity: 10,
      },
      {
        canonicalCode: 'AAB',
        displayCode: 'AAB',
        nameZh: 'Alpha Better',
        pinyinFull: 'alphabetter',
        pinyinAbbr: 'aab',
        aliases: [],
        market: 'US',
        assetType: 'stock',
        active: true,
        popularity: 50,
      },
    ];

    const results = searchStocks('Alpha', tieIndex);

    expect(results).toHaveLength(2);
    expect(results[0].canonicalCode).toBe('AAB');
  });

  test('returns empty array for unsupported, blank, and special queries', () => {
    expect(searchStocks('NOTFOUND', mockIndex)).toHaveLength(0);
    expect(searchStocks('', mockIndex)).toHaveLength(0);
    expect(searchStocks('   ', mockIndex)).toHaveLength(0);
    expect(searchStocks('@#$%', mockIndex)).toHaveLength(0);
    expect(searchStocks('股票🚀', mockIndex)).toHaveLength(0);
  });

  test('large Route B index search remains fast', () => {
    const largeIndex: StockIndexItem[] = Array.from({ length: 5000 }, (_, i) => ({
      canonicalCode: `TEST${i}`,
      displayCode: `TEST${i}`,
      nameZh: `Test ${i}`,
      pinyinFull: `test${i}`,
      pinyinAbbr: `t${i}`,
      aliases: [],
      market: 'US',
      assetType: 'stock',
      active: true,
      popularity: i % 100,
    }));

    const startTime = Date.now();
    const results = searchStocks('TEST1', largeIndex);
    const elapsed = Date.now() - startTime;

    expect(elapsed).toBeLessThan(100);
    expect(results.length).toBeGreaterThan(0);
  });
});

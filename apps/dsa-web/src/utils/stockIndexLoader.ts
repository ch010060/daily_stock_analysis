/**
 * Stock Index Loader
 *
 * Responsible for loading and parsing stock index data
 */

import type { StockIndexData, StockIndexItem, StockIndexTuple } from '../types/stockIndex';
import { INDEX_FIELD } from './stockIndexFields';

export interface IndexLoadResult {
  /** Index data */
  data: StockIndexItem[];
  /** Successfully loaded */
  loaded: boolean;
  /** Error information */
  error?: Error;
  /** Whether fallback mode is used */
  fallback: boolean;
}

const REQUIRED_ROUTE_B_ITEMS: StockIndexItem[] = [
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
    canonicalCode: '2317',
    displayCode: '2317',
    nameZh: '鴻海',
    pinyinFull: 'honghai',
    pinyinAbbr: 'hh',
    aliases: ['鴻海精密', 'Hon Hai', 'Foxconn'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 98,
  },
  {
    canonicalCode: '2454',
    displayCode: '2454',
    nameZh: '聯發科',
    pinyinFull: 'lianfake',
    pinyinAbbr: 'lfk',
    aliases: ['MediaTek'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 97,
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
  {
    canonicalCode: '2308',
    displayCode: '2308',
    nameZh: '台達電',
    pinyinFull: 'taidadian',
    pinyinAbbr: 'tdd',
    aliases: ['台達電子', 'Delta Electronics', 'Delta'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '2382',
    displayCode: '2382',
    nameZh: '廣達',
    pinyinFull: 'guangda',
    pinyinAbbr: 'gd',
    aliases: ['廣達電腦', 'Quanta', 'Quanta Computer'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '6669',
    displayCode: '6669',
    nameZh: '緯穎',
    pinyinFull: 'weiying',
    pinyinAbbr: 'wy',
    aliases: ['Wiwynn', 'Wiwynn Corporation'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '3017',
    displayCode: '3017',
    nameZh: '奇鋐',
    pinyinFull: 'qihong',
    pinyinAbbr: 'qh',
    aliases: ['奇鋐科技', 'AVC', 'Asia Vital Components'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '2368',
    displayCode: '2368',
    nameZh: '金像電',
    pinyinFull: 'jinxiangdian',
    pinyinAbbr: 'jxd',
    aliases: ['金像電子', 'Kinsus', 'Kinsus Interconnect'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '2345',
    displayCode: '2345',
    nameZh: '智邦',
    pinyinFull: 'zhibang',
    pinyinAbbr: 'zb',
    aliases: ['智邦科技', 'Accton', 'Accton Technology'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '3037',
    displayCode: '3037',
    nameZh: '欣興',
    pinyinFull: 'xinxing',
    pinyinAbbr: 'xx',
    aliases: ['欣興電子', 'Unimicron', 'Unimicron Technology'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '3661',
    displayCode: '3661',
    nameZh: '世芯-KY',
    pinyinFull: 'shixin-ky',
    pinyinAbbr: 'sx',
    aliases: ['世芯', 'Alchip', 'Alchip Technologies'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '2303',
    displayCode: '2303',
    nameZh: '聯電',
    pinyinFull: 'liandian',
    pinyinAbbr: 'ld',
    aliases: ['UMC', 'United Microelectronics'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '2882',
    displayCode: '2882',
    nameZh: '國泰金',
    pinyinFull: 'guotaijin',
    pinyinAbbr: 'gtj',
    aliases: ['國泰金控', 'Cathay Financial'],
    market: 'TW',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: '006208',
    displayCode: '006208',
    nameZh: '富邦台50',
    pinyinFull: 'fubangtai50',
    pinyinAbbr: 'fbt50',
    aliases: ['富邦台灣50', 'Fubon Taiwan 50'],
    market: 'TW',
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
    aliases: ['統一台股增長', 'UPAMC Taiwan Active Growth'],
    market: 'TW',
    assetType: 'etf',
    active: true,
    popularity: 97,
  },
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
    aliases: ['Nvidia', 'NVIDIA Corporation'],
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
    aliases: ['Meta', 'Facebook', 'Meta Platforms Inc'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 97,
  },
  {
    canonicalCode: 'MSFT',
    displayCode: 'MSFT',
    nameZh: 'Microsoft',
    pinyinFull: 'microsoft',
    pinyinAbbr: 'msft',
    aliases: ['Microsoft Corporation'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'GOOGL',
    displayCode: 'GOOGL',
    nameZh: 'Alphabet',
    pinyinFull: 'alphabet',
    pinyinAbbr: 'googl',
    aliases: ['Alphabet Inc', 'Google'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'AMZN',
    displayCode: 'AMZN',
    nameZh: 'Amazon',
    pinyinFull: 'amazon',
    pinyinAbbr: 'amzn',
    aliases: ['Amazon.com', 'Amazon.com Inc'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'TSLA',
    displayCode: 'TSLA',
    nameZh: 'Tesla',
    pinyinFull: 'tesla',
    pinyinAbbr: 'tsla',
    aliases: ['Tesla Inc'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'AVGO',
    displayCode: 'AVGO',
    nameZh: 'Broadcom',
    pinyinFull: 'broadcom',
    pinyinAbbr: 'avgo',
    aliases: ['Broadcom Inc.'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'AMD',
    displayCode: 'AMD',
    nameZh: 'Advanced Micro Devices',
    pinyinFull: 'advancedmicrodevices',
    pinyinAbbr: 'amd',
    aliases: ['AMD'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'MU',
    displayCode: 'MU',
    nameZh: 'Micron Technology',
    pinyinFull: 'microntechnology',
    pinyinAbbr: 'mu',
    aliases: ['Micron'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'ARM',
    displayCode: 'ARM',
    nameZh: 'Arm Holdings',
    pinyinFull: 'armholdings',
    pinyinAbbr: 'arm',
    aliases: ['Arm'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'ORCL',
    displayCode: 'ORCL',
    nameZh: 'Oracle',
    pinyinFull: 'oracle',
    pinyinAbbr: 'orcl',
    aliases: ['Oracle Corporation'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'PLTR',
    displayCode: 'PLTR',
    nameZh: 'Palantir Technologies',
    pinyinFull: 'palantirtechnologies',
    pinyinAbbr: 'pltr',
    aliases: ['Palantir'],
    market: 'US',
    assetType: 'stock',
    active: true,
    popularity: 95,
  },
  {
    canonicalCode: 'SPX',
    displayCode: 'SPX',
    nameZh: '標普500指數',
    pinyinFull: 'biaopu500zhishu',
    pinyinAbbr: 'bp500zs',
    aliases: ['S&P500', 'S&P 500', '^GSPC', 'SP500', '標普500', '標普500指數'],
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
];

const SUPPORTED_ROUTE_B_MARKETS = new Set(['TW', 'US']);

function uniqueStrings(values: (string | undefined)[]): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function mergeRequiredRouteBItem(existing: StockIndexItem, required: StockIndexItem): StockIndexItem {
  return {
    ...existing,
    aliases: uniqueStrings([...(existing.aliases || []), ...(required.aliases || [])]),
    popularity: Math.max(existing.popularity || 0, required.popularity || 0),
    active: existing.active || required.active,
    market: required.market,
    exchange: existing.exchange ?? required.exchange ?? null,
    assetType: existing.assetType || required.assetType,
  };
}

function withRequiredRouteBItems(items: StockIndexItem[]): StockIndexItem[] {
  const routeBItems = items.filter((item) => SUPPORTED_ROUTE_B_MARKETS.has(item.market));
  const byCanonicalCode = new Map(routeBItems.map((item) => [item.canonicalCode, item]));

  for (const required of REQUIRED_ROUTE_B_ITEMS) {
    const existing = byCanonicalCode.get(required.canonicalCode);
    byCanonicalCode.set(
      required.canonicalCode,
      existing ? mergeRequiredRouteBItem(existing, required) : required,
    );
  }

  return Array.from(byCanonicalCode.values());
}

/**
 * Load stock index
 *
 * @returns Index load result
 */
export async function loadStockIndex(): Promise<IndexLoadResult> {
  try {
    // Add time parameter to bypass cache (in case the backend doesn't handle ETag/Cache-Control)
    const response = await fetch(`/stocks.index.json?_t=${Math.floor(Date.now() / 3600000)}`);

    if (!response.ok) {
      throw new Error(`Failed to load index: ${response.status} ${response.statusText}`);
    }

    const data: StockIndexData = await response.json();

    // Uncompress format (if array format)
    const items = isCompressedFormat(data)
      ? unpackTuples(data as StockIndexTuple[])
      : data as StockIndexItem[];

    return {
      data: withRequiredRouteBItems(items),
      loaded: true,
      fallback: false,
    };
  } catch (error) {
    console.error('[StockIndexLoader] Failed to load stock index:', error);
    return {
      data: [],
      loaded: false,
      error: error as Error,
      fallback: true,  // Load failed, fallback to old mode
    };
  }
}

/**
 * Check if data is in compressed format
 */
function isCompressedFormat(data: StockIndexData): data is StockIndexTuple[] {
  if (!Array.isArray(data) || data.length === 0) return false;
  const firstItem = data[0];
  return Array.isArray(firstItem) && typeof firstItem[0] === 'string';
}

/**
 * Uncompress tuple format to object format
 */
function unpackTuples(tuples: StockIndexTuple[]): StockIndexItem[] {
  return tuples.map(tuple => ({
    canonicalCode: tuple[INDEX_FIELD.CANONICAL_CODE],
    displayCode: tuple[INDEX_FIELD.DISPLAY_CODE],
    nameZh: tuple[INDEX_FIELD.NAME_ZH],
    pinyinFull: tuple[INDEX_FIELD.PINYIN_FULL],
    pinyinAbbr: tuple[INDEX_FIELD.PINYIN_ABBR],
    aliases: tuple[INDEX_FIELD.ALIASES],
    market: tuple[INDEX_FIELD.MARKET],
    exchange: tuple[INDEX_FIELD.EXCHANGE] ?? null,
    assetType: tuple[INDEX_FIELD.ASSET_TYPE],
    active: tuple[INDEX_FIELD.ACTIVE],
    popularity: tuple[INDEX_FIELD.POPULARITY],
  }));
}

/**
 * Compress object format to tuple format
 *
 * For reducing index file size
 */
export function compressIndex(items: StockIndexItem[]): StockIndexTuple[] {
  return items.map(item => [
    item.canonicalCode,
    item.displayCode,
    item.nameZh,
    item.pinyinFull,
    item.pinyinAbbr,
    item.aliases || [],
    item.market,
    item.assetType,
    item.active,
    item.popularity,
    item.exchange ?? null,
  ]);
}

/**
 * Find stock in index
 *
 * @param canonicalCode - Canonical code
 * @param index - Stock index
 * @returns Stock index item or null
 */
export function findStockInIndex(
  canonicalCode: string,
  index: StockIndexItem[]
): StockIndexItem | null {
  return index.find(item => item.canonicalCode === canonicalCode) || null;
}

/**
 * Get popular stocks list
 *
 * @param index - Stock index
 * @param limit - Number of results to return
 * @returns Popular stocks list
 */
export function getPopularStocks(
  index: StockIndexItem[],
  limit: number = 20
): StockIndexItem[] {
  return [...index]
    .filter(item => item.active)
    .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))
    .slice(0, limit);
}

/**
 * Group stocks by market
 *
 * @param index - Stock index
 * @returns Map of stocks grouped by market
 */
export function groupStocksByMarket(
  index: StockIndexItem[]
): Map<string, StockIndexItem[]> {
  const grouped = new Map<string, StockIndexItem[]>();

  for (const item of index) {
    if (!item.active) continue;

    const market = item.market;
    if (!grouped.has(market)) {
      grouped.set(market, []);
    }
    const group = grouped.get(market);
    if (group) {
      group.push(item);
    }
  }

  return grouped;
}

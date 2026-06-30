/**
 * Stock Index Type Definitions
 *
 * Stock data index for autocomplete functionality
 */

export type Market = 'US' | 'TW';
export type AssetType = 'stock' | 'index' | 'etf';

/**
 * Stock index item (full format)
 */
export interface StockIndexItem {
  /** Canonical code: 2330 or META */
  canonicalCode: string;
  /** Display code: 2330 or META */
  displayCode: string;
  /** Display name: 台積電 or Meta Platforms */
  nameZh: string;
  /** English name: Taiwan Semiconductor */
  nameEn?: string;
  /** Pinyin full: taijidian */
  pinyinFull?: string;
  /** Pinyin abbreviation: tjd */
  pinyinAbbr?: string;
  /** Aliases: ["TSMC"] */
  aliases?: string[];
  /** Market */
  market: Market;
  /** Exchange metadata from local symbol universe */
  exchange?: string | null;
  /** Asset type */
  assetType: AssetType;
  /** Is active */
  active: boolean;
  /** Popularity */
  popularity?: number;
}

/**
 * Stock search suggestion item
 */
export interface StockSuggestion {
  /** Canonical code */
  canonicalCode: string;
  /** Display code */
  displayCode: string;
  /** Chinese name */
  nameZh: string;
  /** Market */
  market: Market;
  /** Exchange metadata from local symbol universe */
  exchange?: string | null;
  /** Match type */
  matchType: 'exact' | 'prefix' | 'contains' | 'fuzzy';
  /** Match field */
  matchField: 'code' | 'name' | 'pinyin' | 'alias';
  /** Sort score */
  score: number;
}

/**
 * Compressed format stock index item (for reducing file size)
 */
export type StockIndexTuple = [
  string,  // canonicalCode
  string,  // displayCode
  string,  // nameZh
  string | undefined, // pinyinFull
  string | undefined, // pinyinAbbr
  string[], // aliases (required, use empty array if none)
  Market,
  AssetType,
  boolean, // active
  number | undefined, // popularity
  (string | null)?, // exchange
];

/**
 * Stock index data (supports two formats)
 */
export type StockIndexData = StockIndexItem[] | StockIndexTuple[];

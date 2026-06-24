import { validateStockCode } from './validation';
import { normalizeStockCode } from './stockCode';

const MARKET_PREFIXES = new Set(['TW', 'US']);

// Common English filler words and finance jargon that should NOT be treated
// as a free-text ticker candidate. Mirrors the backend's _COMMON_WORDS set
// (src/agent/orchestrator.py) for the free-text extraction path only;
// explicit validation via validateStockCode() keeps its original contract.
const FREE_TEXT_TICKER_DENYLIST = new Set([
  'AM', 'AS', 'AT', 'BE', 'BY', 'DO', 'GO', 'HE', 'IF', 'IN',
  'IS', 'IT', 'ME', 'MY', 'NO', 'OF', 'ON', 'OR', 'SO', 'TO',
  'UP', 'WE',
  'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL',
  'CAN', 'HAD', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'HAS',
  'HIS', 'HOW', 'ITS', 'LET', 'MAY', 'NEW', 'NOW', 'OLD',
  'SEE', 'WAY', 'WHO', 'DID', 'GET', 'HIM', 'USE', 'SAY',
  'SHE', 'TOO', 'ANY', 'WITH', 'FROM', 'THAT', 'THAN',
  'THIS', 'WHAT', 'WHEN', 'WILL', 'JUST', 'ALSO',
  'BEEN', 'EACH', 'HAVE', 'MUCH', 'ONLY', 'OVER',
  'SOME', 'SUCH', 'THEM', 'THEN', 'THEY', 'VERY',
  'WERE', 'YOUR', 'ABOUT', 'AFTER', 'COULD', 'EVERY',
  'OTHER', 'THEIR', 'THERE', 'THESE', 'THOSE', 'WHICH',
  'WOULD', 'BEING', 'STILL', 'WHERE',
  'BUY', 'SELL', 'HOLD', 'LONG', 'PUT', 'CALL',
  'ETF', 'IPO', 'RSI', 'EPS', 'PEG', 'ROE', 'ROA',
  'STOCK', 'TRADE', 'PRICE', 'INDEX', 'FUND',
  'HIGH', 'LOW', 'OPEN', 'CLOSE', 'STOP', 'LOSS',
  'TREND', 'BULL', 'BEAR', 'RISK', 'CASH', 'BOND',
  'MACD', 'VWAP', 'BOLL',
  'TTM', 'LTM', 'NTM', 'FWD', 'YOY', 'QOQ', 'YTD',
  'EBIT', 'EBITDA', 'DCF', 'CAGR', 'FCF', 'NAV', 'AUM',
  'PE', 'PB',
  'HELLO', 'PLEASE', 'THANKS', 'CHECK', 'LOOK', 'THINK',
  'MAYBE', 'GUESS', 'TELL', 'SHOW', 'WHATS',
  'WHY', 'HOWDY', 'HEY', 'HI',
]);

function isDeniedTickerCandidate(value: string): boolean {
  return FREE_TEXT_TICKER_DENYLIST.has(value.trim().toUpperCase());
}

export function extractStockCodeFromMessage(message: string): string | null {
  // TW/US only. More specific patterns first.
  const patterns = [
    /\b(TW:(?:\d{4,6}|\d{4,5}[A-Z]))\b/gi,
    /\b((?:\d{4,6}|\d{4,5}[A-Z])\.TW)\b/gi,
    /\b(US:[A-Z]{1,5}(?:[.-][A-Z])?)\b/g,
    /\b([A-Z]{1,5}(?:[.-][A-Z])?\.US)\b/g,
    /\b(\d{4,6}|\d{4,5}[A-Z])\b/g,
    /\b([A-Z]{2,5})\b/g,
  ];
  for (const pattern of patterns) {
    const matches = message.match(pattern);
    if (matches) {
      for (const m of matches) {
        if (MARKET_PREFIXES.has(m.toUpperCase())) {
          continue;
        }
        if (isDeniedTickerCandidate(m)) {
          continue;
        }
        const { valid, normalized } = validateStockCode(m);
        if (valid) return normalizeStockCode(normalized);
      }
    }
  }
  return null;
}

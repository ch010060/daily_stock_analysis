import { validateStockCode } from './validation';
import { normalizeStockCode } from './stockCode';

const MARKET_PREFIXES = new Set(['TW', 'US']);

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
        const { valid, normalized } = validateStockCode(m);
        if (valid) return normalizeStockCode(normalized);
      }
    }
  }
  return null;
}

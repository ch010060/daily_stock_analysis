/**
 * Normalize supported TW/US stock code formats.
 *
 * Mirrors the behavior of data_provider.base.normalize_stock_code in the backend.
 *
 *   2330      → 2330
 *   006208    → 006208
 *   00981A    → 00981A
 *   TW:2330   → 2330
 *   2330.TW   → 2330
 *   AAPL      → AAPL
 *   US:AAPL   → AAPL
 *   AAPL.US   → AAPL
 */
export function normalizeStockCode(stockCode: string): string {
  const code = stockCode.trim();
  const upper = code.toUpperCase();
  const twPattern = /^(?:\d{4,6}|\d{4,5}[A-Z])$/;

  if (upper.startsWith('TW:')) {
    const candidate = upper.slice(3);
    if (twPattern.test(candidate)) return candidate;
  }
  if (upper.startsWith('US:')) {
    const candidate = upper.slice(3);
    if (/^[A-Z]{1,5}(?:[.-][A-Z])?$/.test(candidate)) return candidate;
  }

  if (code.includes('.')) {
    const dotIndex = code.lastIndexOf('.');
    const base = code.slice(0, dotIndex);
    const suffix = code.slice(dotIndex + 1).toUpperCase();

    // 2330.TW → 2330
    if (suffix === 'TW' && twPattern.test(base.toUpperCase())) {
      return base.toUpperCase();
    }
    if (suffix === 'US' && /^[A-Z]{1,5}(?:[.-][A-Z])?$/.test(base.toUpperCase())) {
      return base.toUpperCase();
    }
  }

  if (twPattern.test(upper)) return upper;
  return /^[A-Z]{1,5}(?:[.-][A-Z])?$/.test(upper) ? upper : code;
}

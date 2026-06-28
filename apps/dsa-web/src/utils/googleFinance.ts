export type GoogleFinanceQuoteInput = {
  symbol: string;
  market?: 'tw' | 'us' | 'TW' | 'US' | string;
  exchange?: string | null;
  googleFinanceExchange?: string | null;
  assetType?: string | null;
};

const GOOGLE_FINANCE_QUOTE_BASE = 'https://www.google.com/finance/beta/quote';

const US_EXCHANGE_SUFFIX: Record<string, string> = {
  NASDAQ: 'NASDAQ',
  NASDAQGS: 'NASDAQ',
  NASDAQGM: 'NASDAQ',
  NASDAQCM: 'NASDAQ',
  NASDAQGLOBALSELECT: 'NASDAQ',
  NASDAQGLOBALMARKET: 'NASDAQ',
  NASDAQCAPITALMARKET: 'NASDAQ',
  NMS: 'NASDAQ',
  NGM: 'NASDAQ',
  NCM: 'NASDAQ',
  NYSE: 'NYSE',
  NYQ: 'NYSE',
  NEWYORKSTOCKEXCHANGE: 'NYSE',
  NYSEARCA: 'NYSEARCA',
  ARCA: 'NYSEARCA',
  PCX: 'NYSEARCA',
  NYSEAMERICAN: 'NYSEAMERICAN',
  NYSEMKT: 'NYSEAMERICAN',
  AMEX: 'NYSEAMERICAN',
  ASE: 'NYSEAMERICAN',
  ASEMKT: 'NYSEAMERICAN',
};

function cleanSymbol(symbol: string): string | null {
  const cleaned = symbol.trim().toUpperCase();
  if (!cleaned) return null;
  if (/[/\s]/u.test(cleaned)) return null;
  if (Array.from(cleaned).some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127;
  })) {
    return null;
  }
  return cleaned;
}

function isSupportedTwSymbol(symbol: string): boolean {
  return /^\d{4}$/u.test(symbol) || /^00\d{3,4}[A-Z]?$/u.test(symbol);
}

export function inferGoogleFinanceMarket(symbol: string): 'tw' | 'us' | null {
  const cleaned = cleanSymbol(symbol);
  if (!cleaned) return null;
  if (isSupportedTwSymbol(cleaned)) return 'tw';
  if (/^[A-Z][A-Z0-9.-]{0,14}$/u.test(cleaned)) return 'us';
  return null;
}

export function normalizeGoogleFinanceExchange(exchange: string | null | undefined): string | null {
  const key = Array.from((exchange || '').trim().toUpperCase())
    .filter((character) => /[A-Z0-9]/u.test(character))
    .join('');
  if (!key) return null;
  return US_EXCHANGE_SUFFIX[key] ?? null;
}

export function buildGoogleFinanceQuoteUrl(input: GoogleFinanceQuoteInput): string | null {
  const symbol = cleanSymbol(input.symbol);
  const market = (input.market || '').trim().toUpperCase();
  if (!symbol) return null;

  if (market === 'TW') {
    if (!isSupportedTwSymbol(symbol)) return null;
    return `${GOOGLE_FINANCE_QUOTE_BASE}/${symbol}:TPE`;
  }

  if (market === 'US') {
    if (!/^[A-Z][A-Z0-9.-]{0,14}$/u.test(symbol)) return null;
    const exchange = normalizeGoogleFinanceExchange(input.googleFinanceExchange ?? input.exchange);
    return exchange ? `${GOOGLE_FINANCE_QUOTE_BASE}/${symbol}:${exchange}` : null;
  }

  return null;
}

export function buildGoogleFinanceResearchPrompt(input: GoogleFinanceQuoteInput & { name?: string | null }): string {
  const symbol = cleanSymbol(input.symbol) || input.symbol.trim();
  const name = (input.name || '').trim();
  const subject = name ? `${symbol} ${name}` : symbol;
  return `請分析 ${subject} 近期是否適合長期持有，請結合股價趨勢、財報、新聞、估值與主要風險。`;
}

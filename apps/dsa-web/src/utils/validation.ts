interface ValidationResult {
  valid: boolean;
  message?: string;
  normalized: string;
}

const SUPPORTED_QUERY_CHARACTERS = /^[A-Z0-9.&^\u3400-\u9FFF\s]+$/;
const SP500_CANONICAL_CODE = 'SPX';
const SP500_ALIASES = new Set([
  'S&P500',
  'S&P 500',
  '^GSPC',
  'SP500',
  '標普500',
  '標普500指數',
]);

const STOCK_CODE_PATTERNS = [
  /^\d{4}$/, // TW 4-digit code, for example 2330
  /^\d{6}$/, // A-share 6-digit code
  /^(SH|SZ|BJ)\d{6}$/, // A-share code with exchange prefix
  /^\d{6}\.(SH|SZ|SS|BJ)$/, // A-share code with exchange suffix
  /^\d{5}$/, // HK code without prefix
  /^HK\d{1,5}$/, // HK-prefixed code, for example HK00700
  /^\d{1,5}\.HK$/, // HK suffix format, for example 00700.HK
  /^[A-Z]{1,5}(?:\.(?:US|[A-Z]))?$/, // Common US ticker format
];

const normalizeSp500Alias = (value: string): string | null => {
  const normalized = value.trim().toUpperCase();
  if (SP500_ALIASES.has(normalized)) {
    return SP500_CANONICAL_CODE;
  }
  const compact = normalized.replace(/\s+/g, '');
  return compact === 'S&P500' || compact === 'SP500' ? SP500_CANONICAL_CODE : null;
};

/**
 * Check whether the input looks like a stock code.
 */
export const looksLikeStockCode = (value: string): boolean => {
  const normalized = value.trim().toUpperCase();
  if (normalizeSp500Alias(normalized)) {
    return true;
  }
  return STOCK_CODE_PATTERNS.some((regex) => regex.test(normalized));
};

/**
 * Validate common A-share, HK, and US stock code formats.
 */
export const validateStockCode = (value: string): ValidationResult => {
  const normalized = value.trim().toUpperCase();

  if (!normalized) {
    return { valid: false, message: '請輸入股票代號', normalized };
  }

  const sp500Alias = normalizeSp500Alias(normalized);
  if (sp500Alias) {
    return { valid: true, normalized: sp500Alias };
  }

  const valid = looksLikeStockCode(normalized);

  return {
    valid,
    message: valid ? undefined : '股票代號格式不正確',
    normalized,
  };
};

/**
 * Reject obviously invalid free-text queries before they reach the backend.
 */
export const isObviouslyInvalidStockQuery = (value: string): boolean => {
  const normalized = value.trim().toUpperCase();

  if (!normalized || looksLikeStockCode(normalized) || normalizeSp500Alias(normalized)) {
    return false;
  }

  if (!SUPPORTED_QUERY_CHARACTERS.test(normalized)) {
    return true;
  }

  const hasLetters = /[A-Z]/.test(normalized);
  const hasDigits = /\d/.test(normalized);

  return hasLetters && hasDigits;
};

interface ValidationResult {
  valid: boolean;
  message?: string;
  normalized: string;
}

const SUPPORTED_QUERY_CHARACTERS = /^[A-Z0-9.&^\-\u3400-\u9FFF\s]+$/;
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
  /^(?:TW:)?(?:\d{4,6}|\d{4,5}[A-Z])(?:\.TW)?$/, // TW universe codes, for example 2330, 006208, 00981A
  /^(?:US:)?[A-Z]{1,5}(?:[.-][A-Z])?(?:\.US)?$/, // Common US ticker format
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
 * Validate supported TW/US stock code formats.
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

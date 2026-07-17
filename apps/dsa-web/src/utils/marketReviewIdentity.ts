export interface MarketReviewIdentity {
  displayName: string;
  regionBadge: string;
}

const IDENTITY_BY_REGION: Record<string, MarketReviewIdentity> = {
  tw: { displayName: '台股日報', regionBadge: 'TW' },
  us: { displayName: '美股日報', regionBadge: 'US' },
  'tw,us': { displayName: '台美市場日報', regionBadge: 'TW+US' },
};

const GENERIC_IDENTITY: MarketReviewIdentity = { displayName: '市場日報', regionBadge: 'MARKET' };
// Pre-region-tracking records never persisted `market_review_region` at all;
// back then the product was Taiwan-only, so treat a missing field (not an
// explicitly unresolvable one) as legacy Taiwan-only, matching prior behavior.
const LEGACY_MISSING_REGION_IDENTITY: MarketReviewIdentity = { displayName: '台股日報', regionBadge: 'TW' };

/**
 * Canonical, order-independent region -> display identity mapping, mirroring
 * `resolve_market_review_identity()` in `src/core/market_review.py`. Ensures
 * a US-only or combined market-review record never shows up as 台股日報.
 */
export function resolveMarketReviewIdentity(region?: string | null): MarketReviewIdentity {
  if (region === undefined || region === null) {
    return LEGACY_MISSING_REGION_IDENTITY;
  }
  const tokens = new Set(
    region.split(',').map((part) => part.trim().toLowerCase()).filter(Boolean),
  );
  if (tokens.has('all') || tokens.has('both')) {
    tokens.add('tw');
    tokens.add('us');
  }
  const hasTw = tokens.has('tw');
  const hasUs = tokens.has('us');
  const key = hasTw && hasUs ? 'tw,us' : hasTw ? 'tw' : hasUs ? 'us' : null;
  return key ? IDENTITY_BY_REGION[key] : GENERIC_IDENTITY;
}

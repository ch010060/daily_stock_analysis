import { describe, expect, it } from 'vitest';
import { resolveMarketReviewIdentity } from '../marketReviewIdentity';

describe('resolveMarketReviewIdentity', () => {
  it('resolves tw-only region to 台股日報 / TW', () => {
    expect(resolveMarketReviewIdentity('tw')).toEqual({ displayName: '台股日報', regionBadge: 'TW' });
  });

  it('resolves us-only region to 美股日報 / US', () => {
    expect(resolveMarketReviewIdentity('us')).toEqual({ displayName: '美股日報', regionBadge: 'US' });
  });

  it('resolves combined tw,us region to 台美市場日報 / TW+US', () => {
    expect(resolveMarketReviewIdentity('tw,us')).toEqual({ displayName: '台美市場日報', regionBadge: 'TW+US' });
  });

  it('is order-independent: us,tw equals tw,us', () => {
    expect(resolveMarketReviewIdentity('us,tw')).toEqual(resolveMarketReviewIdentity('tw,us'));
  });

  it('resolves "all" and "both" to the combined identity', () => {
    expect(resolveMarketReviewIdentity('all')).toEqual({ displayName: '台美市場日報', regionBadge: 'TW+US' });
    expect(resolveMarketReviewIdentity('both')).toEqual({ displayName: '台美市場日報', regionBadge: 'TW+US' });
  });

  it('resolves an unresolvable-but-present region string to the generic fallback', () => {
    expect(resolveMarketReviewIdentity('eu')).toEqual({ displayName: '市場日報', regionBadge: 'MARKET' });
    expect(resolveMarketReviewIdentity('')).toEqual({ displayName: '市場日報', regionBadge: 'MARKET' });
  });

  it('falls back to the pre-region-tracking legacy default (台股日報 / TW) when region is missing entirely', () => {
    expect(resolveMarketReviewIdentity(undefined)).toEqual({ displayName: '台股日報', regionBadge: 'TW' });
    expect(resolveMarketReviewIdentity(null)).toEqual({ displayName: '台股日報', regionBadge: 'TW' });
  });
});

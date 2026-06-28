import { describe, expect, it } from 'vitest';
import {
  adaptToVisualReport,
  marketFearBucket,
  marketFearPointerPosition,
} from '../reportVisualSummaryAdapter';
import { MSFT_REPORT, MINIMAL_REPORT } from './fixtures';

describe('adaptToVisualReport', () => {
  it('extracts VIX and trend from MSFT fixture', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    expect(vm.vixLevel).toBeCloseTo(18.89);
    expect(vm.vixStatus).toBe('calm');
    expect(vm.vixDataGap).toBe(false);
    expect(vm.marketRiskKind).toBe('vix');
    expect(vm.marketRiskDataGap).toBe(false);
    expect(vm.marketFearIndex?.kind).toBe('vix');
    expect(vm.marketFearIndex?.title).toBe('恐慌指數 VIX');
    expect(vm.marketFearIndex?.asOf).toBe('2025-03-14');
    expect(vm.systemScore.value).toBe(42);
    expect('pointerPosition' in vm.systemScore).toBe(false);
    expect(vm.trendPeriods).toHaveLength(5);
    expect(vm.trendDataGap).toBe(false);
  });

  it('maps persisted TW VIXTWN snapshot to market fear VM', () => {
    const twReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '006208',
        stockName: '富邦台50',
      },
      summary: {
        ...MSFT_REPORT.summary,
        sentimentScore: 42,
        sentimentLabel: '中性' as const,
      },
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          marketFearIndexSnapshot: {
            market: 'tw',
            kind: 'vixtwn',
            label: '台灣恐慌指數 VIXTWN',
            value: 44.27,
            asOf: '2026-06-26',
            source: 'taifex',
            sourceUrlKey: 'taifex_vixtwn_daily_txt',
            status: 'unknown',
            dataGapReason: null,
          },
          marketRiskSnapshot: {
            source: null,
            vixLevel: null,
            vixStatus: null,
            spxChangePct: null,
            dataGapFields: ['vix_level', 'vix_status', 'spx_change_pct'],
          },
          exposureSnapshot: { dataGapFields: [] },
        },
      },
    };

    const vm = adaptToVisualReport(twReport);
    expect(vm.marketRiskKind).toBe('market_fear');
    expect(vm.marketRiskDataGap).toBe(false);
    expect(vm.marketFearIndex?.kind).toBe('vixtwn');
    expect(vm.marketFearIndex?.title).toBe('台灣恐慌指數 VIXTWN');
    expect(vm.marketFearIndex?.value).toBe(44.27);
    expect(vm.marketFearIndex?.asOf).toBe('2026-06-26');
    expect(vm.marketFearIndex?.bucket).toBe('red');
    expect('pointerPosition' in vm.systemScore).toBe(false);
  });

  it('reads persisted snake_case market fear snapshots from raw_result', () => {
    const twReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '006208',
        stockName: '富邦台50',
      },
      details: {
        rawResult: {
          instrument_type: 'etf',
          market_fear_index_snapshot: {
            market: 'tw',
            kind: 'vixtwn',
            label: '台灣恐慌指數 VIXTWN',
            value: 44.27,
            as_of: '2026-06-26',
            source: 'taifex',
            source_url_key: 'taifex_vixtwn_daily_txt',
            status: 'unknown',
            data_gap_reason: null,
          },
          market_risk_snapshot: {
            vix_level: null,
            vix_status: null,
            spx_change_pct: null,
          },
        },
      },
    };

    const vm = adaptToVisualReport(twReport);
    expect(vm.marketRiskKind).toBe('market_fear');
    expect(vm.marketFearIndex?.kind).toBe('vixtwn');
    expect(vm.marketFearIndex?.value).toBe(44.27);
    expect(vm.marketFearIndex?.asOf).toBe('2026-06-26');
    expect(vm.marketRiskDataGap).toBe(false);
  });

  it('normalizes market fear buckets and system-score risk direction', () => {
    expect(marketFearBucket('vix', 19.99)).toBe('green');
    expect(marketFearBucket('vix', 20)).toBe('blue');
    expect(marketFearBucket('vix', 28.7)).toBe('orange');
    expect(marketFearBucket('vix', 33.5)).toBe('red');
    expect(marketFearBucket('vixtwn', 19.99)).toBe('green');
    expect(marketFearBucket('vixtwn', 20)).toBe('blue');
    expect(marketFearBucket('vixtwn', 30)).toBe('orange');
    expect(marketFearBucket('vixtwn', 40)).toBe('red');
    expect(marketFearPointerPosition('vix', -1)).toBe(0);
    expect(marketFearPointerPosition('vixtwn', 80)).toBe(100);
  });

  it('uses dashboard sentiment for TW stock when VIX is absent', () => {
    const twReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '2454',
        stockName: '聯發科',
      },
      summary: {
        ...MSFT_REPORT.summary,
        sentimentScore: 22,
        sentimentLabel: '悲觀' as const,
      },
      details: {
        analysisContextPackOverview: {
          packVersion: 'test',
          subject: { code: '2454', market: 'tw' },
          blocks: [],
          counts: { available: 0, missing: 0, notSupported: 0, fallback: 0, stale: 0, estimated: 0, partial: 0, fetchFailed: 0 },
          warnings: [],
          metadata: {},
        },
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'stock',
          marketRiskSnapshot: {
            source: null,
            vixLevel: null,
            vixStatus: null,
            spxChangePct: null,
            dataGapFields: ['vix_level', 'vix_status', 'spx_change_pct'],
          },
        },
      },
    };

    const vm = adaptToVisualReport(twReport);
    expect(vm.vixDataGap).toBe(true);
    expect(vm.marketRiskKind).toBe('sentiment');
    expect(vm.marketRiskDataGap).toBe(false);
    expect(vm.marketRiskSentimentScore).toBe(22);
    expect(vm.marketRiskSentimentLabel).toBe('悲觀');
    expect(vm.dataAvailability.find((d) => d.key === 'market_risk')?.status).toBe('ok');
  });

  it('uses dashboard sentiment for TW ETF when VIX is absent', () => {
    const twEtfReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '006208',
        stockName: '富邦台50',
      },
      summary: {
        ...MSFT_REPORT.summary,
        sentimentScore: 42,
        sentimentLabel: '中性' as const,
      },
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          marketRiskSnapshot: {
            source: null,
            vixLevel: null,
            vixStatus: null,
            spxChangePct: null,
            dataGapFields: ['vix_level', 'vix_status', 'spx_change_pct'],
          },
          exposureSnapshot: { dataGapFields: [] },
        },
      },
    };

    const vm = adaptToVisualReport(twEtfReport);
    expect(vm.marketRiskKind).toBe('sentiment');
    expect(vm.marketRiskDataGap).toBe(false);
    expect(vm.marketRiskSentimentScore).toBe(42);
    expect(vm.marketRiskSentimentLabel).toBe('中性');
  });

  it('keeps an explicit TW sentiment gap when dashboard score is missing', () => {
    const twMissingScoreReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '2454',
      },
      summary: {
        ...MSFT_REPORT.summary,
        sentimentScore: null,
        sentimentLabel: undefined,
      },
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'stock',
          marketRiskSnapshot: {
            source: null,
            vixLevel: null,
            vixStatus: null,
            spxChangePct: null,
            dataGapFields: ['vix_level', 'vix_status', 'spx_change_pct'],
          },
        },
      },
    } as unknown as typeof MSFT_REPORT;

    const vm = adaptToVisualReport(twMissingScoreReport);
    expect(vm.marketRiskKind).toBe('sentiment');
    expect(vm.marketRiskDataGap).toBe(true);
    expect(vm.marketRiskSentimentScore).toBeNull();
    expect(vm.dataAvailability.find((d) => d.key === 'market_risk')?.status).toBe('gap');
    expect(vm.dataAvailability.find((d) => d.key === 'market_risk')?.reason).toBe('情緒分數未產生');
  });

  it('extracts price and change from meta', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    expect(vm.currentPrice).toBeCloseTo(388.47);
    expect(vm.changePct).toBeCloseTo(-1.23);
  });

  it('derives MA deviations from price', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    // price=388.47, ma5=392.1 → deviation = (388.47-392.1)/392.1 ≈ -0.93%
    expect(vm.ma5DevPct).toBeCloseTo(((388.47 - 392.1) / 392.1) * 100, 1);
    expect(vm.ma10DevPct).toBeCloseTo(((388.47 - 389.5) / 389.5) * 100, 1);
    expect(vm.ma20DevPct).toBeCloseTo(((388.47 - 385.2) / 385.2) * 100, 1);
  });

  it('maps action plan from strategy', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    expect(vm.idealBuy).toBe('375–380 回測 MA20 支撐後確認');
    expect(vm.stopLoss).toBe('跌破 365 停損');
  });

  it('data availability shows ok when no gap fields', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    const valuationItem = vm.dataAvailability.find((d) => d.key === 'valuation');
    expect(valuationItem?.status).toBe('ok');
  });

  it('data availability shows partial when usable valuation fields exist with some gaps', () => {
    const report = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          valuationSnapshot: {
            peTtm: 32.5,
            marketCap: 3200000000000,
            dataGapFields: ['pe_forward', 'pb'],
          },
          fundamentalSnapshot: {
            revenueYoy: 16.6,
            grossMargin: 47.9,
            dataGapFields: ['earnings_yoy'],
          },
        },
      },
    };

    const vm = adaptToVisualReport(report);
    const valuationItem = vm.dataAvailability.find((d) => d.key === 'valuation');
    const fundamentalItem = vm.dataAvailability.find((d) => d.key === 'fundamental');
    expect(valuationItem?.status).toBe('partial');
    expect(valuationItem?.reason).toBe('缺少 2/5 欄位');
    expect(fundamentalItem?.status).toBe('partial');
    expect(fundamentalItem?.reason).toBe('缺少 1/5 欄位');
  });

  it('data availability shows not applicable for stock-only snapshots on ETF reports', () => {
    const etfReport = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          valuationSnapshot: null,
          fundamentalSnapshot: null,
          exposureSnapshot: { dataGapFields: [] },
        },
      },
    };

    const vm = adaptToVisualReport(etfReport);
    expect(vm.dataAvailability.find((d) => d.key === 'valuation')?.status).toBe('na');
    expect(vm.dataAvailability.find((d) => d.key === 'fundamental')?.status).toBe('na');
  });

  it('does not include exposure item for stock type', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    expect(vm.dataAvailability.find((d) => d.key === 'exposure')).toBeUndefined();
  });

  it('includes exposure item for etf type', () => {
    const etfReport = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          exposureSnapshot: { dataGapFields: [] },
        },
      },
    };
    const vm = adaptToVisualReport(etfReport);
    expect(vm.dataAvailability.find((d) => d.key === 'exposure')).toBeDefined();
  });

  it('extracts valuation card with actual field values', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    expect(vm.valuationCard).not.toBeNull();
    expect(vm.valuationCard?.title).toBe('估值快照');
    const pe = vm.valuationCard?.kpis.find((k) => k.key === 'pe_ttm');
    expect(pe?.value).toBe('28.5x');
    const fpe = vm.valuationCard?.kpis.find((k) => k.key === 'pe_forward');
    expect(fpe?.value).toBe('25.1x');
    const cap = vm.valuationCard?.kpis.find((k) => k.key === 'market_cap');
    expect(cap?.value).toBe('3.08T');
    const div = vm.valuationCard?.kpis.find((k) => k.key === 'dividend_yield');
    expect(div?.value).toBe('+0.7%');
    expect(vm.valuationCard?.source).toBe('yfinance');
    expect(vm.valuationCard?.asOf).toBe('2025-03-14');
  });

  it('extracts fundamental card with signed YoY values', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    expect(vm.fundamentalCard).not.toBeNull();
    const rev = vm.fundamentalCard?.kpis.find((k) => k.key === 'revenue_yoy');
    expect(rev?.value).toBe('+17.2%');
    expect(rev?.signed).toBe(true);
    const np = vm.fundamentalCard?.kpis.find((k) => k.key === 'net_profit_yoy');
    expect(np?.value).toBe('+21.4%');
    const roe = vm.fundamentalCard?.kpis.find((k) => k.key === 'roe');
    expect(roe?.value).toBe('+35.2%');
    expect(roe?.signed).toBe(false);
  });

  it('returns null financial cards for ETF instrument type', () => {
    const etfReport = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          valuationSnapshot: null,
          fundamentalSnapshot: null,
        },
      },
    };
    const vm = adaptToVisualReport(etfReport);
    expect(vm.valuationCard).toBeNull();
    expect(vm.fundamentalCard).toBeNull();
  });

  it('shows dash for missing snapshot fields', () => {
    const report = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          valuationSnapshot: { source: 'yfinance', dataGapFields: ['pe_forward', 'market_cap'] },
          fundamentalSnapshot: { source: 'yfinance', dataGapFields: ['earnings_yoy'] },
        },
      },
    };
    const vm = adaptToVisualReport(report);
    expect(vm.valuationCard?.kpis.find((k) => k.key === 'pe_forward')?.value).toBe('—');
    expect(vm.valuationCard?.kpis.find((k) => k.key === 'market_cap')?.value).toBe('—');
  });

  it('handles null/missing raw_result gracefully', () => {
    expect(() => adaptToVisualReport(MINIMAL_REPORT)).not.toThrow();
    const vm = adaptToVisualReport(MINIMAL_REPORT);
    expect(vm.vixDataGap).toBe(true);
    expect(vm.trendDataGap).toBe(true);
    expect(vm.currentPrice).toBeNull();
  });

  it('hasValueNetwork is false when no mermaid', () => {
    expect(adaptToVisualReport(MSFT_REPORT).hasValueNetwork).toBe(false);
  });

  it('hasValueNetwork is true when mermaid string present', () => {
    const r = {
      ...MSFT_REPORT,
      details: { rawResult: { ...MSFT_REPORT.details?.rawResult, valueNetworkMermaid: 'graph LR; A-->B' } },
    };
    expect(adaptToVisualReport(r).hasValueNetwork).toBe(true);
  });

  it('trendPeriods barWidthPct is 100 for the max absolute change', () => {
    const vm = adaptToVisualReport(MSFT_REPORT);
    // 1Y has changePct=22.4 which is the highest absolute
    const maxBar = Math.max(...vm.trendPeriods.map((p) => p.barWidthPct));
    expect(maxBar).toBeCloseTo(100);
  });

  // F1.3: status takes priority over changePct sign
  it('status=neutral overrides negative changePct — direction must be neutral', () => {
    const report = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          multiPeriodTrendSnapshot: {
            periods: [
              { label: '1季', changePct: -4.48, drawdownPct: -6.0, status: 'neutral' },
            ],
            dataGapFields: [],
          },
        },
      },
    };
    const vm = adaptToVisualReport(report);
    expect(vm.trendPeriods[0].direction).toBe('neutral');
  });

  // Real API path: toCamelCase converts trend_status → trendStatus (not status)
  it('trendStatus=neutral (real API camelCase) overrides negative changePct', () => {
    const report = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          multiPeriodTrendSnapshot: {
            periods: [
              { label: '1季', changePct: -4.48, drawdownFromHighPct: -24.34, trendStatus: 'neutral' },
            ],
            dataGapFields: [],
          },
        },
      },
    };
    const vm = adaptToVisualReport(report);
    expect(vm.trendPeriods[0].direction).toBe('neutral');
    expect(vm.trendPeriods[0].drawdownPct).toBeCloseTo(-24.34);
  });

  it('missing status falls back to changePct sign', () => {
    const report = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          multiPeriodTrendSnapshot: {
            periods: [
              { label: '1W', changePct: -3.0, drawdownPct: -3.0, status: '' },
            ],
            dataGapFields: [],
          },
        },
      },
    };
    const vm = adaptToVisualReport(report);
    expect(vm.trendPeriods[0].direction).toBe('down');
  });
});

import type { AnalysisReport } from '../../../../types/analysis';

/** MSFT-like fixture derived from Phase 19D real data */
export const MSFT_REPORT: AnalysisReport = {
  meta: {
    queryId: 'q-msft-001',
    stockCode: 'MSFT',
    stockName: 'Microsoft Corp',
    reportType: 'detailed',
    createdAt: '2025-03-14T09:30:00',
    currentPrice: 388.47,
    changePct: -1.23,
  },
  summary: {
    analysisSummary: '短期動能偏弱，VIX 持穩，建議觀望等待回測支撐確認。',
    operationAdvice: '觀望',
    trendPrediction: '盤整',
    sentimentScore: 42,
  },
  strategy: {
    idealBuy: '375–380 回測 MA20 支撐後確認',
    secondaryBuy: '370 以下分批',
    stopLoss: '跌破 365 停損',
    takeProfit: '400 以上分批獲利',
  },
  details: {
    rawResult: {
      instrumentType: 'stock',
      currentPrice: 388.47,
      changePct: -1.23,
      ma5: 392.1,
      ma10: 389.5,
      ma20: 385.2,
      supportLevel: 375.0,
      resistanceLevel: 400.0,
      trendStrength: 38,
      rsi12: 44.5,
      volumeRatio: 0.87,
      marketRiskSnapshot: {
        source: 'yfinance',
        asOf: '2025-03-14',
        vixLevel: 18.89,
        vixStatus: 'calm',
        spxChangePct: -0.45,
        dataGapFields: [],
      },
      multiPeriodTrendSnapshot: {
        source: 'yfinance',
        asOf: '2025-03-14',
        periods: [
          { label: '1W', changePct: -2.1, drawdownPct: -3.2, status: 'downtrend' },
          { label: '1M', changePct: -5.4, drawdownPct: -7.1, status: 'downtrend' },
          { label: '3M', changePct: 3.2, drawdownPct: -8.5, status: 'uptrend' },
          { label: '6M', changePct: 8.7, drawdownPct: -12.3, status: 'uptrend' },
          { label: '1Y', changePct: 22.4, drawdownPct: -15.8, status: 'uptrend' },
        ],
        dataGapFields: [],
      },
      valuationSnapshot: {
        source: 'yfinance',
        asOf: '2025-03-14',
        peTtm: 28.5,
        peForward: 25.1,
        pb: 12.3,
        dividendYield: 0.72,
        marketCap: 3080000000000,
        dataGapFields: [],
      },
      fundamentalSnapshot: {
        source: 'yfinance',
        asOf: '2025-03-14',
        revenueYoy: 17.2,
        netProfitYoy: 21.4,
        earningsYoy: 21.4,
        roe: 35.2,
        grossMargin: 69.4,
        dataGapFields: [],
      },
    },
  },
};

export const MINIMAL_REPORT: AnalysisReport = {
  meta: {
    queryId: 'q-min-001',
    stockCode: 'TEST',
    stockName: 'Test Co',
    reportType: 'simple',
    createdAt: '2025-01-01T00:00:00',
  },
  summary: {
    analysisSummary: '',
    operationAdvice: '中性',
    trendPrediction: '震盪',
    sentimentScore: 50,
  },
};

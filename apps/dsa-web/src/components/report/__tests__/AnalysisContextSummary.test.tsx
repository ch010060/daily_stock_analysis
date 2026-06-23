import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import type {
  AnalysisContextPackOverview,
  AnalysisReport,
  AnalysisResult,
  RunDiagnosticSummary,
} from '../../../types/analysis';
import { AnalysisContextSummary } from '../AnalysisContextSummary';
import { ReportSummary } from '../ReportSummary';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getDiagnostics: vi.fn(),
    getNews: vi.fn(),
  },
}));

const overview: AnalysisContextPackOverview = {
  packVersion: '1.0',
  createdAt: '2026-04-10T08:30:00+00:00',
  subject: {
    code: '2330',
    stockName: '台積電',
    market: 'cn',
  },
  blocks: [
    {
      key: 'quote',
      label: '行情',
      status: 'available',
      source: 'mock_quote',
      warnings: [],
      missingReasons: ['realtime_quote_missing'],
    },
    {
      key: 'news',
      label: '新聞',
      status: 'missing',
      source: null,
      warnings: ['news_provider_timeout'],
      missingReasons: ['news_context_missing'],
    },
    {
      key: 'fundamentals',
      label: '基本面',
      status: 'fetch_failed',
      source: 'fundamental_pipeline',
      warnings: [],
      missingReasons: ['fundamental_pipeline_failed'],
    },
  ],
  counts: {
    available: 1,
    missing: 1,
    notSupported: 0,
    fallback: 0,
    stale: 0,
    estimated: 0,
    partial: 0,
    fetchFailed: 1,
  },
  dataQuality: {
    overallScore: 82,
    level: 'usable',
    blockScores: {
      quote: 100,
      daily_bars: 100,
      technical: 100,
      news: 35,
      fundamentals: 25,
      chip: 100,
    },
    limitations: ['fundamentals: fetch_failed'],
  },
  warnings: ['intraday_realtime_overlay'],
  metadata: {
    triggerSource: 'api',
    newsResultCount: 3,
  },
};

describe('AnalysisContextSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a collapsed summary and expands overview details on demand', () => {
    render(<AnalysisContextSummary overview={overview} />);

    const panel = screen.getByTestId('analysis-context-summary');
    expect(panel).not.toHaveAttribute('open');
    expect(within(panel).getAllByText('輸入資料塊')[0]).toBeVisible();
    expect(screen.getAllByText('可用 2')[0]).toBeVisible();
    expect(screen.getAllByText('缺失 0')[0]).toBeVisible();
    expect(screen.getAllByText('擷取失敗 1')[0]).toBeVisible();
    expect(screen.getAllByText('品質分 82/100 可用')[0]).toBeVisible();
    expect(screen.getByText('觸發來源: 手動/API 觸發')).toBeVisible();
    expect(screen.getByText('來源: 其他資料來源')).not.toBeVisible();

    fireEvent.click(within(panel).getAllByText('輸入資料塊')[0]);

    expect(panel).toHaveAttribute('open');
    expect(screen.getByText('行情')).toBeInTheDocument();
    expect(screen.getByText('來源: 其他資料來源')).toBeVisible();
    expect(screen.queryByText(/source: fallback/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/storage\.get_analysis_context/)).not.toBeInTheDocument();
    expect(screen.getByText('警告:')).toBeInTheDocument();
    expect(screen.queryByText(/intraday_realtime_overlay/)).not.toBeInTheDocument();
    expect(screen.getByText(/盤中資料可能不完整/)).toBeInTheDocument();
    expect(screen.getByText('資料限制:')).toBeInTheDocument();
    expect(screen.getByText(/基本面：擷取失敗/)).toBeInTheDocument();
    expect(screen.queryByText(/news_provider_timeout/)).not.toBeInTheDocument();
    expect(screen.queryByText(/news_context_missing/)).not.toBeInTheDocument();
    expect(screen.queryByText(/本次分析未取得新聞資料/)).not.toBeInTheDocument();
    expect(screen.queryByText(/realtime_quote_missing/)).not.toBeInTheDocument();
    expect(screen.getByText(/即時行情未取得可用資料/)).toBeInTheDocument();
    expect(screen.queryByText(/fundamental_pipeline_failed/)).not.toBeInTheDocument();
    expect(screen.getByText(/基本面資料暫時無法取得/)).toBeInTheDocument();
    expect(screen.getAllByText('新聞結果數: 3').some((item) => item.textContent === '新聞結果數: 3')).toBe(true);
  });

  it('localizes the collapsed summary for english reports', () => {
    render(<AnalysisContextSummary overview={overview} language="en" />);

    const panel = screen.getByTestId('analysis-context-summary');
    expect(panel).not.toHaveAttribute('open');
    expect(screen.getAllByText('Input Blocks')[0]).toBeVisible();
    expect(screen.getAllByText('Available 2')[0]).toBeVisible();
    expect(screen.getAllByText('Missing 0')[0]).toBeVisible();
    expect(screen.getAllByText('Fetch failed 1')[0]).toBeVisible();
    expect(screen.getAllByText('Quality 82/100 Usable')[0]).toBeVisible();
    expect(screen.getByText('Trigger: Manual/API')).toBeVisible();

    fireEvent.click(within(panel).getAllByText('Input Blocks')[0]);

    expect(screen.getByText('Data Limitations:')).toBeInTheDocument();
    expect(screen.getByText(/fundamentals: Fetch failed/)).toBeInTheDocument();
  });

  it('surfaces degraded non-zero states in the collapsed summary', () => {
    const degradedOverview: AnalysisContextPackOverview = {
      ...overview,
      blocks: [
        {
          key: 'quote',
          label: '行情',
          status: 'fallback',
          source: 'cached_quote',
          warnings: ['quote_fallback'],
          missingReasons: [],
        },
        {
          key: 'fundamental',
          label: '基本面',
          status: 'stale',
          source: 'fundamental_cache',
          warnings: ['stale_fundamental'],
          missingReasons: [],
        },
      ],
      counts: {
        available: 0,
        missing: 0,
        notSupported: 0,
        fallback: 1,
        stale: 1,
        estimated: 0,
        partial: 0,
        fetchFailed: 0,
      },
    };

    render(<AnalysisContextSummary overview={degradedOverview} />);

    const panel = screen.getByTestId('analysis-context-summary');
    expect(panel).not.toHaveAttribute('open');
    expect(within(panel).getByText('可用 0')).toBeVisible();
    expect(within(panel).getByText('缺失 0')).toBeVisible();
    expect(within(panel).getAllByText('備援可用 1')[0]).toBeVisible();
    expect(within(panel).getAllByText('過期 1')[0]).toBeVisible();
  });

  it('does not render without an overview', () => {
    const { container } = render(<AnalysisContextSummary overview={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('does not render raw values or unexpected sensitive fields', () => {
    const unsafeOverview = {
      ...overview,
      value: 'raw trend payload',
      content: '完整新聞正文不應出現',
      apiKey: 'secret-key',
      blocks: [
        {
          ...overview.blocks[0],
          items: {
            price: {
              value: 1880,
              apiKey: 'secret-key',
            },
          },
        },
      ],
    } as unknown as AnalysisContextPackOverview;

    render(<AnalysisContextSummary overview={unsafeOverview} />);

    fireEvent.click(screen.getAllByText('輸入資料塊')[0]);

    expect(screen.queryByText('raw trend payload')).not.toBeInTheDocument();
    expect(screen.queryByText('完整新聞正文不應出現')).not.toBeInTheDocument();
    expect(screen.queryByText('secret-key')).not.toBeInTheDocument();
  });

  it('uses final diagnostics to resolve stale quote and news context without counting unsupported TW chips', () => {
    const staleOverview: AnalysisContextPackOverview = {
      ...overview,
      subject: {
        code: '2379',
        stockName: '瑞昱',
        market: 'tw',
      },
      blocks: [
        {
          key: 'quote',
          label: '行情',
          status: 'missing',
          source: 'fallback',
          warnings: [],
          missingReasons: ['realtime_quote_missing'],
        },
        {
          key: 'news',
          label: '新聞',
          status: 'missing',
          source: null,
          warnings: [],
          missingReasons: ['news_context_missing'],
        },
        {
          key: 'chip',
          label: '籌碼',
          status: 'missing',
          source: null,
          warnings: [],
          missingReasons: ['chip_distribution_missing'],
        },
      ],
      counts: {
        available: 0,
        missing: 3,
        notSupported: 0,
        fallback: 0,
        stale: 0,
        estimated: 0,
        partial: 0,
        fetchFailed: 0,
      },
      dataQuality: {
        overallScore: 65,
        level: 'limited',
        blockScores: {
          quote: 20,
          daily_bars: 100,
          technical: 100,
          news: 20,
          fundamentals: 100,
          chip: 0,
        },
        limitations: [
          'quote: missing',
          'news: missing',
          'chip: missing',
        ],
      },
      metadata: {
        triggerSource: 'api',
        newsResultCount: 0,
      },
    };
    const finalDiagnostics: RunDiagnosticSummary = {
      status: 'degraded',
      statusLabel: '部分降級',
      reason: '即時行情部分降級，但已取得可用替代資料',
      copyText: '',
      stockCode: '2379',
      components: {
        realtimeQuote: {
          key: 'realtime_quote',
          label: '實時行情',
          status: 'degraded',
          message: '即時行情部分降級，但已取得可用替代資料',
          details: {
            finalQuoteStatus: 'degraded',
            quoteUsable: true,
            sourceLabel: '備援資料',
            fallbackUsed: true,
          },
        },
        news: {
          key: 'news',
          label: '新聞搜尋',
          status: 'ok',
          message: '新聞搜尋取得 5 筆結果',
          details: {
            resultCount: 5,
            finalStatus: 'available',
          },
        },
      },
    };

    render(<AnalysisContextSummary overview={staleOverview} diagnosticSummary={finalDiagnostics} />);

    fireEvent.click(screen.getAllByText('輸入資料塊')[0]);

    expect(screen.getAllByText('可用 1')[0]).toBeVisible();
    expect(screen.getAllByText('備援可用 1')[0]).toBeVisible();
    expect(screen.queryByText(/缺失 3/)).not.toBeInTheDocument();
    expect(screen.queryByText('籌碼')).not.toBeInTheDocument();
    expect(screen.queryByText(/本次分析未取得新聞資料/)).not.toBeInTheDocument();
    expect(screen.queryByText(/即時行情未取得可用資料/)).not.toBeInTheDocument();
    expect(screen.queryByText(/警告: 即時行情部分降級/)).not.toBeInTheDocument();
    expect(screen.queryByText(/source: fallback/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/來源: fallback/i)).not.toBeInTheDocument();
  });

  it('uses persisted history diagnostics and news items when record id is provided', async () => {
    const staleOverview: AnalysisContextPackOverview = {
      ...overview,
      subject: {
        code: 'NVDA',
        stockName: 'NVIDIA',
        market: 'us',
      },
      blocks: [
        {
          key: 'quote',
          label: '行情',
          status: 'fallback',
          source: 'fallback',
          warnings: [],
          missingReasons: [],
        },
        {
          key: 'news',
          label: '新聞',
          status: 'missing',
          source: null,
          warnings: [],
          missingReasons: ['news_context_missing'],
        },
        {
          key: 'chip',
          label: '籌碼',
          status: 'missing',
          source: null,
          warnings: [],
          missingReasons: ['chip_distribution_missing'],
        },
      ],
      counts: {
        available: 0,
        missing: 2,
        notSupported: 0,
        fallback: 1,
        stale: 0,
        estimated: 0,
        partial: 0,
        fetchFailed: 0,
      },
      metadata: {
        triggerSource: 'api',
        newsResultCount: 0,
      },
    };
    vi.mocked(historyApi.getDiagnostics).mockResolvedValue({
      status: 'degraded',
      statusLabel: '部分降級',
      reason: '即時行情部分降級，但已取得可用替代資料',
      copyText: '',
      stockCode: 'NVDA',
      components: {
        realtimeQuote: {
          key: 'realtime_quote',
          label: '實時行情',
          status: 'degraded',
          message: '即時行情部分降級，但已取得可用替代資料',
          details: {
            finalQuoteStatus: 'degraded',
            quoteUsable: true,
            sourceLabel: '備援資料',
          },
        },
      },
    });
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 8,
      items: [],
    });

    render(<AnalysisContextSummary overview={staleOverview} recordId={8} />);

    await waitFor(() => {
      expect(screen.getAllByText('可用 1')[0]).toBeVisible();
      expect(screen.getAllByText('備援可用 1')[0]).toBeVisible();
    });
    fireEvent.click(screen.getAllByText('輸入資料塊')[0]);

    expect(historyApi.getDiagnostics).toHaveBeenCalledWith(8);
    expect(historyApi.getNews).toHaveBeenCalledWith(8, 1);
    expect(screen.queryByText(/本次分析未取得新聞資料/)).not.toBeInTheDocument();
    expect(screen.queryByText(/即時行情未取得可用資料/)).not.toBeInTheDocument();
    expect(screen.queryByText('籌碼')).not.toBeInTheDocument();
  });

  it('uses final quote status to show missing instead of stale provider success', () => {
    const staleOverview: AnalysisContextPackOverview = {
      ...overview,
      subject: {
        code: '2379',
        stockName: '瑞昱',
        market: 'tw',
      },
      blocks: [
        {
          key: 'quote',
          label: '行情',
          status: 'available',
          source: 'YfinanceFetcher',
          warnings: [],
          missingReasons: [],
        },
        {
          key: 'news',
          label: '新聞',
          status: 'available',
          source: 'news',
          warnings: [],
          missingReasons: [],
        },
      ],
      counts: {
        available: 2,
        missing: 0,
        notSupported: 0,
        fallback: 0,
        stale: 0,
        estimated: 0,
        partial: 0,
        fetchFailed: 0,
      },
      metadata: {
        triggerSource: 'api',
        newsResultCount: 1,
      },
    };
    const finalDiagnostics: RunDiagnosticSummary = {
      status: 'degraded',
      statusLabel: '部分降級',
      reason: '即時行情未取得可用資料',
      copyText: '',
      stockCode: '2379',
      components: {
        realtimeQuote: {
          key: 'realtime_quote',
          label: '實時行情',
          status: 'failed',
          message: '即時行情未取得可用資料',
          details: {
            finalQuoteStatus: 'missing',
            quoteUsable: false,
            reason: 'empty_or_incomplete_quote',
          },
        },
      },
    };

    render(<AnalysisContextSummary overview={staleOverview} diagnosticSummary={finalDiagnostics} />);

    fireEvent.click(screen.getAllByText('輸入資料塊')[0]);

    expect(screen.getAllByText('缺失 1')[0]).toBeVisible();
    expect(screen.getByText(/即時行情未取得可用資料/)).toBeVisible();
    expect(screen.queryByText(/YfinanceFetcher 成功/)).not.toBeInTheDocument();
  });
});

describe('ReportSummary analysis context placement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders strategy and news before context, diagnostics and traceability', async () => {
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 0,
      items: [],
    });

    const report: AnalysisReport = {
      meta: {
        id: 1,
        queryId: 'q1',
        stockCode: '2330',
        stockName: '台積電',
        reportType: 'detailed',
        reportLanguage: 'zh',
        createdAt: '2026-04-10T12:00:00',
        marketPhaseSummary: {
          market: 'cn',
          phase: 'intraday',
          marketLocalTime: '2026-04-10T10:30:00+08:00',
          sessionDate: '2026-04-10',
          effectiveDailyBarDate: '2026-04-09',
          isTradingDay: true,
          isMarketOpenNow: true,
          isPartialBar: true,
          minutesToOpen: null,
          minutesToClose: 150,
          triggerSource: 'api',
          analysisIntent: 'auto',
          warnings: [],
        },
      },
      summary: {
        analysisSummary: 'summary',
        operationAdvice: '持有',
        trendPrediction: '震盪',
        sentimentScore: 70,
      },
      strategy: {
        idealBuy: '120',
      },
      details: {
        analysisContextPackOverview: overview,
      },
    };
    const result: AnalysisResult = {
      queryId: 'q1',
      stockCode: '2330',
      stockName: '台積電',
      report,
      diagnosticSummary: {
        status: 'normal',
        statusLabel: '正常',
        reason: '執行正常',
        components: {},
        copyText: '',
      },
      createdAt: '2026-04-10T12:00:00',
    };

    render(<ReportSummary data={result} />);

    await waitFor(() => {
      expect(screen.getByText('暫無相關資訊')).toBeInTheDocument();
    });

    expect(screen.getByText('市場階段: CN · 盤中')).toBeInTheDocument();
    expect(screen.getByText('日線未完成')).toBeInTheDocument();
    expect(screen.getAllByText('質量分 82/100 可用')[0]).toBeInTheDocument();

    const strategy = screen.getByText('狙擊點位');
    const news = screen.getByText('相關資訊');
    const diagnostics = screen.getByTestId('run-diagnostics');
    const contextSummary = screen.getByTestId('analysis-context-summary');
    const traceability = screen.getByText('資料追溯');

    expect(strategy.compareDocumentPosition(news) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(news.compareDocumentPosition(contextSummary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(contextSummary.compareDocumentPosition(diagnostics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(diagnostics.compareDocumentPosition(traceability) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

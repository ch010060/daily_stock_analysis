import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { diagnosticsApi } from '../../../api/diagnostics';
import { historyApi } from '../../../api/history';
import type { RunDiagnosticSummary } from '../../../types/analysis';
import { ReportDiagnostics } from '../ReportDiagnostics';

vi.mock('../../../api/diagnostics', () => ({
  diagnosticsApi: {
    probeNewsProvider: vi.fn(),
  },
}));

vi.mock('../../../api/history', () => ({
  historyApi: {
    getDiagnostics: vi.fn(),
  },
}));

const diagnosticSummary: RunDiagnosticSummary = {
  traceId: 'trace-1234567890abcdef',
  taskId: 'task-1',
  queryId: 'query-1',
  stockCode: '2330',
  triggerSource: 'web',
  status: 'degraded',
  statusLabel: '部分降級',
  reason: '實時行情 baostock 成功，前置資料來源失敗後已繼續',
  copyText: 'trace_id: trace-1234567890abcdef\ndata_status: degraded',
  components: {
    realtimeQuote: {
      key: 'realtime_quote',
      label: '實時行情',
      status: 'degraded',
      message: '實時行情 baostock 成功，前置資料來源失敗後已繼續',
      details: {
        provider: 'baostock',
        attempts: 2,
      },
    },
    notification: {
      key: 'notification',
      label: '通知',
      status: 'not_configured',
      message: '通知未配置或本次跳過',
    },
  },
};

const newsSearchDiagnosticSummary: RunDiagnosticSummary = {
  ...diagnosticSummary,
  copyText:
    'trace_id: trace-1234567890abcdef\n' +
    'news_search: status=available; providers=SearXNG,Tavily; attempts=3; results=4; fallback_used=true\n' +
    'news_queries: 2330 台積電 新聞 | 台積電 最新消息',
  components: {
    ...diagnosticSummary.components,
    news: {
      key: 'news',
      label: '新聞搜尋',
      status: 'ok',
      message: '新聞搜尋取得 4 筆結果',
      details: {
        providersAttempted: ['SearXNG', 'Tavily'],
        queryVariants: ['2330 台積電 新聞', '台積電 最新消息'],
        attemptCount: 3,
        resultCount: 4,
        fallbackUsed: true,
        finalStatus: 'available',
      },
    },
  },
};

const missingQuoteDiagnosticSummary: RunDiagnosticSummary = {
  ...diagnosticSummary,
  status: 'degraded',
  statusLabel: '部分降級',
  reason: '即時行情未取得可用資料',
  components: {
    ...diagnosticSummary.components,
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

const quoteFallbackDiagnosticSummary: RunDiagnosticSummary = {
  ...diagnosticSummary,
  reason: '即時行情部分降級，但已取得可用替代資料',
  components: {
    ...diagnosticSummary.components,
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
  },
};

const realtekDiagnosticSummary: RunDiagnosticSummary = {
  ...newsSearchDiagnosticSummary,
  stockCode: '2379',
};

const intelDiagnosticSummary: RunDiagnosticSummary = {
  ...newsSearchDiagnosticSummary,
  stockCode: 'INTC',
};

describe('ReportDiagnostics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('loads historical diagnostics in a collapsed panel and copies sanitized text', async () => {
    vi.mocked(historyApi.getDiagnostics).mockResolvedValue(diagnosticSummary);

    render(<ReportDiagnostics recordId={1} />);

    expect(historyApi.getDiagnostics).toHaveBeenCalledWith(1);
    expect(await screen.findByText('執行狀態')).toBeInTheDocument();
    const panel = screen.getByTestId('run-diagnostics');
    expect(panel).not.toHaveAttribute('open');
    expect(screen.getByText('部分降級')).toBeInTheDocument();

    fireEvent.click(screen.getByText('執行狀態'));

    expect(panel).toHaveAttribute('open');
    expect(screen.getByText('最近失敗後已降級')).toBeInTheDocument();
    expect(screen.getByText('未配置')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '複製排障資訊' }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(diagnosticSummary.copyText);
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '已複製' })).toBeInTheDocument();
    });
  });

  it('uses the provided summary without fetching history diagnostics', () => {
    render(<ReportDiagnostics summary={diagnosticSummary} />);

    expect(historyApi.getDiagnostics).not.toHaveBeenCalled();
    expect(screen.getByText('執行狀態')).toBeInTheDocument();
    expect(screen.getByText('部分降級')).toBeInTheDocument();
  });

  it('shows final quote missing without stale provider success wording', () => {
    render(<ReportDiagnostics summary={missingQuoteDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));

    expect(screen.getByText('失敗')).toBeInTheDocument();
    expect(screen.getAllByText('即時行情未取得可用資料').length).toBeGreaterThan(0);
    expect(screen.queryByText(/YfinanceFetcher 成功/)).not.toBeInTheDocument();
    expect(screen.queryByText(/實時行情.*成功/)).not.toBeInTheDocument();
  });

  it('shows quote fallback success as available backup instead of warning status', () => {
    render(<ReportDiagnostics summary={quoteFallbackDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));

    expect(screen.getByText('備援可用')).toBeInTheDocument();
    expect(screen.getAllByText('即時行情部分降級，但已取得可用替代資料').length).toBeGreaterThan(0);
    expect(screen.queryByText('近期失敗後已降級')).not.toBeInTheDocument();
  });

  it('displays and copies sanitized news search diagnostics', async () => {
    render(<ReportDiagnostics summary={newsSearchDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));

    expect(screen.getByText('新聞搜尋診斷')).toBeInTheDocument();
    expect(screen.getByText('嘗試來源：SearXNG, Tavily')).toBeInTheDocument();
    expect(screen.getByText('查詢次數：3')).toBeInTheDocument();
    expect(screen.getByText('結果數：4')).toBeInTheDocument();
    expect(screen.getByText('使用備援：是')).toBeInTheDocument();
    expect(screen.getByText('狀態：available')).toBeInTheDocument();
    expect(screen.getByText('2330 台積電 新聞')).toBeInTheDocument();
    expect(screen.queryByText(/phase15-test-token/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '複製排障資訊' }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        newsSearchDiagnosticSummary.copyText,
      );
    });
    expect(navigator.clipboard.writeText).not.toHaveBeenCalledWith(
      expect.stringContaining('phase15-test-token'),
    );
    expect(historyApi.getDiagnostics).not.toHaveBeenCalled();
  });

  it('shows manual news provider probe controls without auto probing on render', () => {
    render(<ReportDiagnostics summary={newsSearchDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));

    expect(screen.getByRole('button', { name: '測試新聞來源' })).toBeInTheDocument();
    expect(screen.getByLabelText('新聞來源測試標的')).toBeInTheDocument();
    expect(screen.getByLabelText('新聞來源測試模式')).toBeInTheDocument();
    expect(diagnosticsApi.probeNewsProvider).not.toHaveBeenCalled();
  });

  it('defaults the manual news provider probe to the current TW report symbol', () => {
    render(<ReportDiagnostics summary={realtekDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));

    expect(screen.getByLabelText('新聞來源測試市場')).toHaveValue('tw');
    expect(screen.getByLabelText('新聞來源測試標的')).toHaveValue('2379');
    expect(diagnosticsApi.probeNewsProvider).not.toHaveBeenCalled();
  });

  it('defaults the manual news provider probe to the current US report symbol', () => {
    render(<ReportDiagnostics summary={intelDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));

    expect(screen.getByLabelText('新聞來源測試市場')).toHaveValue('us');
    expect(screen.getByLabelText('新聞來源測試標的')).toHaveValue('INTC');
    expect(diagnosticsApi.probeNewsProvider).not.toHaveBeenCalled();
  });

  it('resets the manual probe target when switching to another report symbol', () => {
    const { rerender } = render(<ReportDiagnostics summary={realtekDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: '2379' },
    });

    rerender(<ReportDiagnostics summary={intelDiagnosticSummary} />);

    expect(screen.getByLabelText('新聞來源測試市場')).toHaveValue('us');
    expect(screen.getByLabelText('新聞來源測試標的')).toHaveValue('INTC');
    expect(diagnosticsApi.probeNewsProvider).not.toHaveBeenCalled();
  });

  it('runs the manual news provider probe for typed fresh TW and US symbols', async () => {
    vi.mocked(diagnosticsApi.probeNewsProvider)
      .mockResolvedValueOnce({
        symbol: '2379',
        market: 'tw',
        providerMode: 'runtime',
        status: 'available',
        providersAttempted: ['SearXNG'],
        queryVariants: ['2379 瑞昱 新聞', 'Realtek 最新消息'],
        attemptCount: 2,
        resultCount: 2,
        fallbackUsed: false,
        latencyMs: 111,
        items: [
          {
            title: '瑞昱 2379 Realtek 新聞',
            source: 'Example TW',
            url: 'https://example.com/tw/2379',
          },
        ],
      })
      .mockResolvedValueOnce({
        symbol: 'INTC',
        market: 'us',
        providerMode: 'runtime',
        status: 'available',
        providersAttempted: ['Tavily'],
        queryVariants: ['INTC Intel stock news', 'Intel earnings AI PC stock news'],
        attemptCount: 2,
        resultCount: 3,
        fallbackUsed: true,
        latencyMs: 222,
        items: [
          {
            title: 'Intel INTC AI PC earnings news',
            source: 'Example US',
            url: 'https://example.com/us/intc',
          },
        ],
      });

    render(<ReportDiagnostics summary={realtekDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.change(screen.getByLabelText('新聞來源測試市場'), {
      target: { value: 'tw' },
    });
    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: '2379' },
    });
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    await waitFor(() => {
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenCalledWith({
        symbol: '2379',
        market: 'tw',
        providerMode: 'runtime',
        limit: 4,
      });
    });
    expect(await screen.findByText('瑞昱 2379 Realtek 新聞')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('新聞來源測試市場'), {
      target: { value: 'us' },
    });
    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: 'INTC' },
    });
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    await waitFor(() => {
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenCalledTimes(2);
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenLastCalledWith({
        symbol: 'INTC',
        market: 'us',
        providerMode: 'runtime',
        limit: 4,
      });
    });
    expect(await screen.findByText('Intel INTC AI PC earnings news')).toBeInTheDocument();
  });

  it('runs the manual news provider probe after click and displays sanitized results', async () => {
    vi.mocked(diagnosticsApi.probeNewsProvider).mockResolvedValue({
      symbol: '2330',
      market: 'tw',
      providerMode: 'runtime',
      status: 'available',
      providersAttempted: ['SearXNG'],
      queryVariants: ['2330 台積電 新聞', '台積電 最新消息'],
      attemptCount: 2,
      resultCount: 4,
      fallbackUsed: false,
      latencyMs: 123,
      items: [
        {
          title: '台積電 2330 法說新聞',
          source: 'Example News',
          url: 'https://example.com/news/1',
          publishedAt: '2026-06-20',
        },
      ],
    });

    render(<ReportDiagnostics summary={newsSearchDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    await waitFor(() => {
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenCalledWith({
        symbol: '2330',
        market: 'tw',
        providerMode: 'runtime',
        limit: 4,
      });
    });
    expect(await screen.findByText('手動測試結果')).toBeInTheDocument();
    expect(screen.getByText('模式：runtime')).toBeInTheDocument();
    expect(screen.getAllByText('狀態：available').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('嘗試來源：SearXNG')).toBeInTheDocument();
    expect(screen.getByText('查詢次數：2')).toBeInTheDocument();
    expect(screen.getAllByText('結果數：4').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('使用備援：否')).toBeInTheDocument();
    expect(screen.getByText('延遲：123 ms')).toBeInTheDocument();
    expect(screen.getByText('台積電 2330 法說新聞')).toBeInTheDocument();
    expect(screen.getByText(/Example News/)).toBeInTheDocument();
  });

  it('supports manual probe selection for fresh TW and US targets', async () => {
    vi.mocked(diagnosticsApi.probeNewsProvider)
      .mockResolvedValueOnce({
        symbol: '3008',
        market: 'tw',
        providerMode: 'runtime',
        status: 'available',
        providersAttempted: ['SearXNG'],
        queryVariants: ['3008 大立光 新聞', '大立光 最新消息'],
        attemptCount: 2,
        resultCount: 2,
        fallbackUsed: false,
        latencyMs: 111,
        items: [
          {
            title: '大立光 3008 法說新聞',
            source: 'Example TW',
            url: 'https://example.com/tw/3008',
          },
        ],
      })
      .mockResolvedValueOnce({
        symbol: 'NVDA',
        market: 'us',
        providerMode: 'runtime',
        status: 'available',
        providersAttempted: ['Tavily'],
        queryVariants: ['NVDA NVIDIA stock news', 'NVIDIA earnings AI GPU stock news'],
        attemptCount: 2,
        resultCount: 3,
        fallbackUsed: true,
        latencyMs: 222,
        items: [
          {
            title: 'NVIDIA NVDA AI GPU earnings news',
            source: 'Example US',
            url: 'https://example.com/us/nvda',
          },
        ],
      });

    render(<ReportDiagnostics summary={newsSearchDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: 'tw:3008' },
    });
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    await waitFor(() => {
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenCalledWith({
        symbol: '3008',
        market: 'tw',
        providerMode: 'runtime',
        limit: 4,
      });
    });
    expect(await screen.findByText('大立光 3008 法說新聞')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: 'us:NVDA' },
    });
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    await waitFor(() => {
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenCalledTimes(2);
      expect(diagnosticsApi.probeNewsProvider).toHaveBeenLastCalledWith({
        symbol: 'NVDA',
        market: 'us',
        providerMode: 'runtime',
        limit: 4,
      });
    });
    expect(await screen.findByText('NVIDIA NVDA AI GPU earnings news')).toBeInTheDocument();
  });

  it('keeps a completed manual probe result after diagnostics remount', async () => {
    vi.mocked(diagnosticsApi.probeNewsProvider).mockResolvedValue({
      symbol: '3008',
      market: 'tw',
      providerMode: 'runtime',
      status: 'available',
      providersAttempted: ['SearXNG'],
      queryVariants: ['3008 大立光 新聞', '大立光 最新消息'],
      attemptCount: 2,
      resultCount: 2,
      fallbackUsed: false,
      latencyMs: 111,
      items: [
        {
          title: '大立光 3008 法說新聞',
          source: 'Example TW',
          url: 'https://example.com/tw/3008',
        },
      ],
    });

    const firstRender = render(
      <ReportDiagnostics recordId={61} summary={newsSearchDiagnosticSummary} />,
    );

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: 'tw:3008' },
    });
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    expect(await screen.findByText('大立光 3008 法說新聞')).toBeInTheDocument();
    firstRender.unmount();

    render(<ReportDiagnostics recordId={61} summary={newsSearchDiagnosticSummary} />);
    fireEvent.click(screen.getByText('執行狀態'));

    expect(await screen.findByText('手動測試結果')).toBeInTheDocument();
    expect(screen.getByText('大立光 3008 法說新聞')).toBeInTheDocument();
    expect(diagnosticsApi.probeNewsProvider).toHaveBeenCalledTimes(1);
  });

  it('shows explicit manual probe failure status', async () => {
    vi.mocked(diagnosticsApi.probeNewsProvider).mockResolvedValue({
      symbol: '2330',
      market: 'tw',
      providerMode: 'runtime',
      status: 'failed',
      providersAttempted: [],
      queryVariants: [],
      attemptCount: 0,
      resultCount: 0,
      fallbackUsed: false,
      latencyMs: 50,
      items: [],
      errorMessage: 'provider unavailable',
    });

    render(<ReportDiagnostics summary={newsSearchDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    expect(await screen.findByText('狀態：failed')).toBeInTheDocument();
    expect(screen.getByText('新聞來源測試失敗：provider unavailable')).toBeInTheDocument();
  });

  it('redacts secret-like values from manual probe UI output', async () => {
    vi.mocked(diagnosticsApi.probeNewsProvider).mockResolvedValue({
      symbol: 'AAPL',
      market: 'us',
      providerMode: 'tavily',
      status: 'available',
      providersAttempted: ['Bearer phase15-provider-secret'],
      queryVariants: ['AAPL Apple stock news api_key=phase15-query-secret'],
      attemptCount: 1,
      resultCount: 1,
      fallbackUsed: false,
      latencyMs: 25,
      items: [
        {
          title: 'token=phase15-title-secret',
          source: 'source password=phase15-source-secret',
          url: 'https://example.com/news?api_key=phase15-url-secret',
        },
      ],
    });

    render(<ReportDiagnostics summary={newsSearchDiagnosticSummary} />);

    fireEvent.click(screen.getByText('執行狀態'));
    fireEvent.change(screen.getByLabelText('新聞來源測試標的'), {
      target: { value: 'us:AAPL' },
    });
    fireEvent.change(screen.getByLabelText('新聞來源測試模式'), {
      target: { value: 'tavily' },
    });
    fireEvent.click(screen.getByRole('button', { name: '測試新聞來源' }));

    await screen.findByText('手動測試結果');
    expect(screen.queryByText(/phase15-provider-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/phase15-query-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/phase15-title-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/phase15-source-secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/phase15-url-secret/i)).not.toBeInTheDocument();
  });

  it('refetches diagnostics after StrictMode cleans up the first effect run', async () => {
    vi.mocked(historyApi.getDiagnostics).mockResolvedValue(diagnosticSummary);

    render(
      <StrictMode>
        <ReportDiagnostics recordId={1} />
      </StrictMode>,
    );

    await waitFor(() => {
      expect(historyApi.getDiagnostics).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('執行狀態')).toBeInTheDocument();
  });
});

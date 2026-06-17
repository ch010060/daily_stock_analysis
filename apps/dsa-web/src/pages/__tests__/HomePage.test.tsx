import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi, DuplicateTaskError } from '../../api/analysis';
import { agentApi } from '../../api/agent';
import { historyApi } from '../../api/history';
import { systemConfigApi } from '../../api/systemConfig';
import { useStockPoolStore } from '../../stores';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import HomePage from '../HomePage';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../api/history', () => ({
  historyApi: {
    getList: vi.fn(),
    getDetail: vi.fn(),
    getNews: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    getMarkdown: vi.fn().mockResolvedValue('# report'),
    getDiagnostics: vi.fn(),
    deleteByCode: vi.fn(),
    getStockBarList: vi.fn().mockResolvedValue({ total: 0, items: [] }),
  },
}));

vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>('../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      analyzeAsync: vi.fn(),
      triggerMarketReview: vi.fn(),
      getStatus: vi.fn(),
      getTasks: vi.fn(),
    },
  };
});

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSetupStatus: vi.fn(),
    getWatchlist: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../../api/agent', () => ({
  agentApi: {
    getSkills: vi.fn(),
  },
}));

vi.mock('../../hooks/useTaskStream', () => ({
  useTaskStream: vi.fn(),
}));

const historyItem = {
  id: 1,
  queryId: 'q-1',
  stockCode: '600519',
  stockName: '貴州茅臺',
  sentimentScore: 82,
  operationAdvice: '買進',
  createdAt: '2026-03-18T08:00:00Z',
};

const historyReport = {
  meta: {
    id: 1,
    queryId: 'q-1',
    stockCode: '600519',
    stockName: '貴州茅臺',
    reportType: 'detailed' as const,
    reportLanguage: 'zh' as const,
    createdAt: '2026-03-18T08:00:00Z',
  },
  summary: {
    analysisSummary: '趨勢維持強勢',
    operationAdvice: '繼續觀察買點',
    trendPrediction: '短線震盪偏強',
    sentimentScore: 78,
  },
};

const marketReviewHistoryItem = {
  id: 2,
  queryId: 'market-review-q-1',
  stockCode: 'MARKET',
  stockName: '大盤覆盤',
  reportType: 'market_review' as const,
  createdAt: '2026-03-18T08:00:00Z',
};

const marketReviewHistoryReport = {
  meta: {
    id: 2,
    queryId: 'market-review-q-1',
    stockCode: 'MARKET',
    stockName: '大盤覆盤',
    reportType: 'market_review' as const,
    reportLanguage: 'zh' as const,
    createdAt: '2026-03-18T08:00:00Z',
  },
  summary: {
    analysisSummary: '大盤覆盤摘要',
    operationAdvice: '檢視覆盤',
    trendPrediction: '大盤覆盤',
    sentimentScore: 50,
  },
};

describe('HomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigateMock.mockReset();
    useStockPoolStore.getState().resetDashboardState();
    vi.mocked(analysisApi.getTasks).mockResolvedValue({
      total: 0,
      pending: 0,
      processing: 0,
      tasks: [],
    });
    vi.mocked(agentApi.getSkills).mockResolvedValue({ skills: [], default_skill_id: '' });
    vi.mocked(historyApi.getDiagnostics).mockResolvedValue({
      status: 'unknown',
      statusLabel: '未知',
      reason: '舊報告或診斷證據不足，無法判斷本次執行狀態',
      components: {},
      copyText: 'data_status: unknown',
    });
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [],
    });
  });

  it('renders the dashboard workspace and auto-loads the first report', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 20,
      items: [historyItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(historyReport);
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'task-1',
      status: 'pending',
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const dashboard = await screen.findByTestId('home-dashboard');
    expect(dashboard).toBeInTheDocument();
    expect(dashboard.className).toContain('h-[calc(100vh-5rem)]');
    expect(dashboard.className).toContain('lg:h-[calc(100vh-2rem)]');
    expect(dashboard.firstElementChild?.className).toContain('min-h-0');
    expect(dashboard.querySelector('.flex-1.flex.min-h-0.overflow-hidden')).toBeTruthy();
    expect(screen.getByTestId('home-dashboard-scroll')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('輸入股票程式碼或名稱，如 2330、AAPL')).toBeInTheDocument();
    expect(await screen.findByText('趨勢維持強勢')).toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: getReportText(normalizeReportLanguage(historyReport.meta.reportLanguage)).fullReport,
      }),
    ).toBeInTheDocument();
    expect(historyApi.getMarkdown).not.toHaveBeenCalled();
  });

  it('loads markdown only after opening the full report drawer', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 20,
      items: [historyItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(historyReport);
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Full Markdown Report');

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const fullReportButton = await screen.findByRole('button', {
      name: getReportText(normalizeReportLanguage(historyReport.meta.reportLanguage)).fullReport,
    });
    expect(historyApi.getMarkdown).not.toHaveBeenCalled();

    fireEvent.click(fullReportButton);

    expect(await screen.findByText('載入報告中...')).toBeInTheDocument();
  });

  it('shows the empty report workspace when history is empty', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('開始分析')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '開始分析', level: 3 })).toBeInTheDocument();
    expect(screen.getByText('輸入股票程式碼進行分析，或從左側選擇歷史報告檢視。')).toBeInTheDocument();
    expect(screen.getByText('暫無個股記錄')).toBeInTheDocument();
  });

  it('shows market review history in the stock bar', async () => {
    vi.mocked(historyApi.getStockBarList).mockResolvedValue({
      total: 1,
      items: [{
        id: 11,
        stockCode: 'AAPL',
        stockName: 'Apple',
        reportType: 'detailed',
        sentimentScore: 72,
        operationAdvice: '觀察',
        analysisCount: 2,
        lastAnalysisTime: '2026-03-19T08:00:00Z',
      }],
    });
    vi.mocked(historyApi.getList).mockImplementation((params: { reportType?: string } = {}) => {
      if (params.reportType === 'market_review') {
        return Promise.resolve({
          total: 1,
          page: 1,
          limit: 10,
          items: [marketReviewHistoryItem],
        });
      }
      return Promise.resolve({
        total: 0,
        page: 1,
        limit: 20,
        items: [],
      });
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(marketReviewHistoryReport);

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('button', { name: /MARKET/ })).toBeInTheDocument();
    const newerStockButton = await screen.findByRole('button', { name: /AAPL/ });
    const marketButton = await screen.findByRole('button', { name: /MARKET/ });
    expect(newerStockButton.compareDocumentPosition(marketButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText('大盤覆盤歷史')).not.toBeInTheDocument();
    expect(historyApi.getList).toHaveBeenCalledWith({
      stockCode: 'MARKET',
      reportType: 'market_review',
      page: 1,
      limit: 10,
    });

    fireEvent.click(await screen.findByRole('button', { name: /MARKET/ }));

    expect(await screen.findByText('大盤覆盤摘要')).toBeInTheDocument();
  });

  it('removes the MARKET stock bar item after deleting market review history', async () => {
    let isMarketReviewDeleted = false;
    vi.mocked(historyApi.getStockBarList).mockResolvedValue({
      total: 0,
      items: [],
    });
    vi.mocked(historyApi.getList).mockImplementation((params: { reportType?: string } = {}) => {
      if (params.reportType === 'market_review') {
        return Promise.resolve({
          total: isMarketReviewDeleted ? 0 : 1,
          page: 1,
          limit: 10,
          items: isMarketReviewDeleted ? [] : [marketReviewHistoryItem],
        });
      }
      return Promise.resolve({
        total: 0,
        page: 1,
        limit: 20,
        items: [],
      });
    });
    vi.mocked(historyApi.deleteByCode).mockImplementation(async () => {
      isMarketReviewDeleted = true;
      return { deleted: 1 };
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('button', { name: /MARKET/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '刪除 大盤覆盤 歷史記錄' }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /MARKET/ })).not.toBeInTheDocument();
    });
    expect(historyApi.deleteByCode).toHaveBeenCalledWith('MARKET');
  });

  it('surfaces duplicate task warnings from dashboard submission', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });
    vi.mocked(analysisApi.analyzeAsync).mockRejectedValue(
      new DuplicateTaskError('600519', 'task-1', '股票 600519 正在分析中'),
    );

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const input = await screen.findByPlaceholderText('輸入股票程式碼或名稱，如 2330、AAPL');
    fireEvent.change(input, { target: { value: '600519' } });
    fireEvent.click(screen.getByRole('button', { name: '分析' }));

    await waitFor(() => {
      expect(screen.getByText(/股票 600519 正在分析中/)).toBeInTheDocument();
    });
    expect(screen.getByText(/股票 600519 正在分析中/).closest('[role="alert"]')).toBeInTheDocument();
  });

  it('submits market review from the home toolbar', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盤覆盤任務已提交',
      taskId: 'task-1',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'task-1',
      status: 'completed',
      marketReviewReport: '市場覆盤報告示例文字',
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '大盤覆盤' }));

    await waitFor(() => {
      expect(analysisApi.triggerMarketReview).toHaveBeenCalledWith({ sendNotification: true });
    });
    expect(await screen.findByText('大盤覆盤已完成')).toBeInTheDocument();
    expect(await screen.findByText('市場覆盤報告示例文字')).toBeInTheDocument();
    expect(analysisApi.getStatus).toHaveBeenCalledWith('task-1');
  });

  it('scrolls the dashboard to market review feedback after toolbar clicks', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 20,
      items: [historyItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(historyReport);
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盤覆盤任務已提交',
      taskId: 'task-1',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'task-1',
      status: 'completed',
      marketReviewReport: '市場覆盤報告示例文字',
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('趨勢維持強勢');
    const dashboardScroll = screen.getByTestId('home-dashboard-scroll');
    const scrollToMock = vi.fn(function scrollTo(this: HTMLElement, options?: ScrollToOptions) {
      if (typeof options?.top === 'number') {
        this.scrollTop = options.top;
      }
    });
    Object.defineProperty(dashboardScroll, 'scrollTo', {
      configurable: true,
      value: scrollToMock,
    });
    dashboardScroll.scrollTop = 480;

    fireEvent.click(screen.getByRole('button', { name: '大盤覆盤' }));

    await waitFor(() => {
      expect(scrollToMock).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
    });
    expect(dashboardScroll.scrollTop).toBe(0);
    expect(await screen.findByText('大盤覆盤已完成')).toBeInTheDocument();
  });

  it('keeps market review results in the main dashboard scroll area', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盤覆盤任務已提交',
      taskId: 'task-1',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'task-1',
      status: 'completed',
      marketReviewReport: Array.from({ length: 30 }, (_, index) => `第 ${index + 1} 行復盤內容`).join('\n'),
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '大盤覆盤' }));

    const dashboardScroll = screen.getByTestId('home-dashboard-scroll');
    const marketReviewReport = await screen.findByTestId('market-review-report');
    expect(dashboardScroll).toContainElement(marketReviewReport);
    expect(marketReviewReport.className).not.toContain('max-h-64');
    expect(marketReviewReport.className).not.toContain('overflow-y-auto');
    expect(await screen.findByText('開始分析')).toBeInTheDocument();
  });

  it('shows first-run setup gaps and links to settings', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['llm_primary', 'stock_list'],
      nextStepKey: 'llm_primary',
      checks: [
        {
          key: 'llm_primary',
          title: 'LLM 主通道',
          category: 'ai_model',
          required: true,
          status: 'needs_action',
          message: '缺少主模型配置',
        },
        {
          key: 'stock_list',
          title: '自選股',
          category: 'base',
          required: true,
          status: 'needs_action',
          message: '缺少自選股',
        },
      ],
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('基礎設定未完成')).toBeInTheDocument();
    expect(screen.getByText(/LLM 主通道、自選股/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '去配置' }));
    expect(navigateMock).toHaveBeenCalledWith('/settings');
  });

  it('navigates to chat with report context when asking a follow-up question', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 20,
      items: [historyItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(historyReport);

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const followUpButton = await screen.findByRole('button', { name: '追問 AI' });
    fireEvent.click(followUpButton);

    expect(navigateMock).toHaveBeenCalledWith(
      '/chat?stock=600519&name=%E8%B2%B4%E5%B7%9E%E8%8C%85%E8%87%BA&recordId=1',
    );
  });

  it('opens and closes the mobile history drawer without changing dashboard styles', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });

    const { container } = render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const trigger = await screen.findByRole('button', { name: '歷史記錄' });
    fireEvent.click(trigger);

    expect(container.querySelector('.page-drawer-overlay')).toBeTruthy();
    expect(container.querySelector('.dashboard-card')).toBeTruthy();

    fireEvent.click(container.querySelector('.fixed.inset-0.z-40') as HTMLElement);

    await waitFor(() => {
      expect(container.querySelector('.page-drawer-overlay')).toBeFalsy();
    });
  });

  it('keeps same-stock history range controls in empty result state and allows switching back', async () => {
    const staleReport = {
      ...historyReport,
      meta: {
        ...historyReport.meta,
        createdAt: '2020-01-01T08:00:00Z',
      },
    };

    vi.mocked(historyApi.getStockBarList).mockResolvedValue({
      total: 1,
      items: [
        {
          id: 1,
          stockCode: '600519',
          stockName: '貴州茅臺',
          reportType: 'detailed',
          sentimentScore: 58,
          operationAdvice: '繼續觀察買點',
          analysisCount: 2,
          lastAnalysisTime: '2026-03-21T08:00:00Z',
        },
      ],
    });

    vi.mocked(historyApi.getList).mockImplementation((params: { stockCode?: string; startDate?: string } = {}) => {
      if (!Object.prototype.hasOwnProperty.call(params, 'stockCode')) {
        return Promise.resolve({
          total: 1,
          page: 1,
          limit: 20,
          items: [historyItem],
        });
      }

      return Promise.resolve({
        total: 0,
        page: 1,
        limit: 20,
        items: [],
      });
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(staleReport);

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const historyTrendButton = await screen.findByRole('button', { name: '歷史趨勢' });
    fireEvent.click(historyTrendButton);

    const range30Button = await screen.findByRole('button', { name: '近30天' });
    fireEvent.click(range30Button);

    await waitFor(() => {
      expect(screen.getByText('暫無更多同股歷史分析')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '全部歷史' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '全部歷史' }));

    await waitFor(() => {
      expect(screen.queryByText('暫無更多同股歷史分析')).not.toBeInTheDocument();
    });
    expect(screen.getAllByRole('button', { name: /貴州茅臺/ }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/2次/)).toBeInTheDocument();

    const historyCalls = vi.mocked(historyApi.getList).mock.calls.filter((call) => call[0]?.stockCode === '600519');
    expect(historyCalls).toHaveLength(3);
    expect(historyCalls[1][0]).toHaveProperty('startDate');
    expect(historyCalls[2][0]).not.toHaveProperty('startDate');
  });

  it('renders active task panel content from dashboard state', async () => {
    const activeTask = {
      taskId: 'task-1',
      stockCode: '600519',
      stockName: '貴州茅臺',
      status: 'processing' as const,
      progress: 45,
      message: '正在抓取最新行情',
      reportType: 'detailed',
      createdAt: '2026-03-18T08:00:00Z',
    };
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });
    vi.mocked(analysisApi.getTasks).mockResolvedValue({
      total: 1,
      pending: 0,
      processing: 1,
      tasks: [activeTask],
    });

    useStockPoolStore.setState({
      activeTasks: [activeTask],
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('分析任務')).toBeInTheDocument();
    expect(screen.getByText('正在抓取最新行情')).toBeInTheDocument();
  });

  it('triggers reanalyze for the current report even if the search input has other text', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 20,
      items: [historyItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(historyReport);
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'task-re-1',
      status: 'pending',
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    // Wait for the report to load
    await screen.findByText('趨勢維持強勢');

    // Type something else in the search box
    const input = screen.getByPlaceholderText('輸入股票程式碼或名稱，如 2330、AAPL');
    fireEvent.change(input, { target: { value: 'AAPL' } });

    // Click "Reanalyze"
    const reanalyzeButton = screen.getByRole('button', { name: '重新分析' });
    fireEvent.click(reanalyzeButton);

    // Verify that analyzeAsync is called with the report's stock code, not the search box text
    expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(expect.objectContaining({
      stockCode: '600519',
      originalQuery: '600519',
      forceRefresh: true,
    }));
  });

  it('passes the selected strategy when submitting stock analysis', async () => {
    vi.mocked(agentApi.getSkills).mockResolvedValue({
      default_skill_id: 'bull_trend',
      skills: [
        { id: 'bull_trend', name: '預設多頭趨勢', description: '趨勢分析' },
        { id: 'growth_quality', name: '成長質量', description: '成長股分析' },
      ],
    });
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'task-strategy-1',
      status: 'pending',
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '策略' }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: /成長質量/ }));

    const input = screen.getByPlaceholderText('輸入股票程式碼或名稱，如 2330、AAPL');
    fireEvent.change(input, { target: { value: '600519' } });
    fireEvent.click(screen.getByRole('button', { name: '分析' }));

    await waitFor(() => {
      expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(expect.objectContaining({
        stockCode: '600519',
        skills: ['growth_quality'],
      }));
    });
  });

  it('supports keyboard navigation in the strategy menu', async () => {
    vi.mocked(agentApi.getSkills).mockResolvedValue({
      default_skill_id: 'bull_trend',
      skills: [
        { id: 'bull_trend', name: '預設多頭趨勢', description: '趨勢分析' },
        { id: 'growth_quality', name: '成長質量', description: '成長股分析' },
      ],
    });
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    const trigger = await screen.findByRole('button', { name: '策略' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });

    const defaultOption = await screen.findByRole('menuitemradio', { name: /預設策略/ });
    await waitFor(() => {
      expect(defaultOption).toHaveFocus();
    });

    const menu = screen.getByRole('menu');
    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    expect(screen.getByRole('menuitemradio', { name: /預設多頭趨勢/ })).toHaveFocus();

    fireEvent.keyDown(menu, { key: 'End' });
    expect(screen.getByRole('menuitemradio', { name: /成長質量/ })).toHaveFocus();

    fireEvent.keyDown(menu, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });
    expect(trigger).toHaveFocus();
  });

  it('disables stock reanalysis and follow-up for market review history reports', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 20,
      items: [marketReviewHistoryItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(marketReviewHistoryReport);

    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );

    await screen.findByText('大盤覆盤摘要');
    expect(screen.queryByRole('button', { name: '重新分析' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '追問 AI' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '歷史趨勢' })).toBeInTheDocument();

    expect(analysisApi.analyzeAsync).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { finewsApi } from '../../api/finews';
import FiNewsPage from '../FiNewsPage';

vi.mock('../../api/finews', () => ({
  finewsApi: {
    getLatest: vi.fn(),
  },
}));

const snapshot = {
  source: 'finews' as const,
  sourceUrl: 'https://finews.elsetech.app/',
  reportDate: '2026-06-26',
  sourceUpdatedAt: '2026-06-26 21:13:18 UTC',
  fetchedAt: '2026-06-29T00:00:00+00:00',
  stale: false,
  fetchError: null,
  languageOriginal: 'zh-CN' as const,
  languageRendered: 'zh-TW' as const,
  externalLinks: [
    {
      title: '美股收低，科技股拋售。',
      url: 'https://example.com/news-one',
    },
  ],
  sections: {
    afterMarketSummary: ['美股主要指數盤後偏弱。', '科技股承壓，防禦板塊相對抗跌。'],
    majorNews: ['主要新聞已整理。', 'Yahoo Finance · 2026-06-26', '投資人等待通膨與聯準會訊號。'],
    marketTemperature: ['恐慌貪婪指數', '25', '極度恐慌', '市場溫度偏低。'],
    majorIndices: ['標普 500', '^GSPC', '6,000.00', '-0.05%'],
    majorStocks: ['Nvidia', 'NVDA', '190.10', '+1.20%'],
    treasuryYields: ['美國 10 年期國債', 'US10Y', '4.20%', '+0.01'],
    fx: ['美元 / 人民幣', 'USD/CNY', '7.18', '-0.02%'],
  },
};

const renderPage = () => render(
  <MemoryRouter>
    <FiNewsPage />
  </MemoryRouter>,
);

describe('FiNewsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(finewsApi.getLatest).mockResolvedValue(snapshot);
  });

  it('renders the local FiNews reader with attribution and zh_TW content', async () => {
    const { container } = renderPage();

    expect(await screen.findByRole('heading', { name: '美股日報', level: 1 })).toBeInTheDocument();
    expect(screen.getAllByText('FiNews').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /原始來源/ })).toHaveAttribute(
      'href',
      'https://finews.elsetech.app/',
    );
    expect(screen.getByText('2026-06-26')).toBeInTheDocument();
    expect(screen.getByText('2026-06-26 21:13:18 UTC')).toBeInTheDocument();
    expect(screen.getByText('2026-06-29T00:00:00+00:00')).toBeInTheDocument();
    expect(screen.getByText('美股主要指數盤後偏弱。')).toBeInTheDocument();
    expect(screen.getByText('恐慌貪婪指數')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /美股收低，科技股拋售。/ })).toHaveAttribute(
      'href',
      'https://example.com/news-one',
    );
    expect(container.querySelector('iframe')).toBeNull();
  });

  it('renders the compact newspaper masthead, main column, and market sidebar', async () => {
    renderPage();

    expect(await screen.findByTestId('finews-masthead')).toBeInTheDocument();
    expect(screen.getByTestId('finews-newspaper-grid')).toHaveClass('lg:grid-cols-[minmax(0,1.62fr)_minmax(300px,0.86fr)]');

    const mainColumn = screen.getByTestId('finews-main-column');
    expect(mainColumn).toHaveTextContent('盤後總結');
    expect(mainColumn).toHaveTextContent('主要新聞');

    const marketSidebar = screen.getByTestId('finews-market-sidebar');
    expect(marketSidebar).toHaveTextContent('市場溫度');
    expect(marketSidebar).toHaveTextContent('主要指數');
    expect(marketSidebar).toHaveTextContent('主要股票');
    expect(marketSidebar).toHaveTextContent('美債利率');
    expect(marketSidebar).toHaveTextContent('主要匯率');
  });

  it('shows stale and fetch-failed state while keeping cached content visible', async () => {
    vi.mocked(finewsApi.getLatest).mockResolvedValue({
      ...snapshot,
      stale: true,
      fetchError: 'finews_fetch_failed: TimeoutError',
    });

    renderPage();

    expect(await screen.findByText('顯示舊快照')).toBeInTheDocument();
    expect(screen.getByText('美股主要指數盤後偏弱。')).toBeInTheDocument();
  });

  it('shows a graceful error when no snapshot content is available', async () => {
    vi.mocked(finewsApi.getLatest).mockResolvedValue({
      ...snapshot,
      fetchError: 'finews_fetch_failed: TimeoutError',
      sections: {
        afterMarketSummary: [],
        majorNews: [],
        marketTemperature: [],
        majorIndices: [],
        majorStocks: [],
        treasuryYields: [],
        fx: [],
      },
    });

    renderPage();

    expect(await screen.findByText('美股日報載入失敗')).toBeInTheDocument();
    expect(screen.getByText('目前沒有可顯示的 FiNews 快照內容')).toBeInTheDocument();
  });

  it('shows a graceful error when the API call fails', async () => {
    vi.mocked(finewsApi.getLatest).mockRejectedValue(new Error('network'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('美股日報載入失敗')).toBeInTheDocument();
    });
    expect(screen.getByText('FiNews 目前無法載入，請稍後再試。')).toBeInTheDocument();
  });
});

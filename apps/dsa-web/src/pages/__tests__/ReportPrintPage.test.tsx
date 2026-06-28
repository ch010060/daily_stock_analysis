import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../api/history';
import ReportPrintPage from '../ReportPrintPage';

vi.mock('../../api/history', () => ({
  historyApi: {
    getDetail: vi.fn(),
    getMarkdown: vi.fn(),
  },
}));

vi.mock('../../components/report/visual/ReportVisualSummary', () => ({
  ReportVisualSummary: () => <div data-testid="visual-summary-stub">Visual summary</div>,
}));

vi.mock('../../components/report/MermaidDiagram', () => ({
  MermaidDiagram: (props: { code: string }) => <div data-testid="mermaid-stub">{props.code}</div>,
}));

const reportDetail = {
  meta: {
    id: 74,
    queryId: 'q-74',
    stockCode: '006208',
    stockName: '富邦台50',
    reportType: 'full',
    reportLanguage: 'zh_TW',
    createdAt: '2026-06-28T12:00:00',
  },
  summary: {},
};

function renderPrintPage(path = '/reports/74/print') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/reports/:historyId/print" element={<ReportPrintPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ReportPrintPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(historyApi.getDetail).mockResolvedValue(reportDetail as never);
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# 完整報告\n\n報告內容');
    Object.defineProperty(window, 'print', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  it('renders the print route with toolbar, visual summary, and markdown content', async () => {
    renderPrintPage();

    expect(await screen.findByRole('heading', { name: '富邦台50', level: 1 })).toBeInTheDocument();
    expect(screen.getByTestId('report-print-toolbar')).toHaveClass('no-print');
    expect(await screen.findByTestId('visual-summary-stub')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: '完整報告' })).toBeInTheDocument();
    expect(screen.getByTestId('report-markdown-body')).toBeInTheDocument();
    expect(historyApi.getDetail).toHaveBeenCalledWith(74);
    expect(historyApi.getMarkdown).toHaveBeenCalledWith(74);
  });

  it('renders pdf=1 mode without toolbar or auto print and exposes readiness marker', async () => {
    renderPrintPage('/reports/74/print?pdf=1');

    expect(await screen.findByRole('heading', { name: '完整報告' })).toBeInTheDocument();
    expect(screen.queryByTestId('report-print-toolbar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-print-header')).not.toBeInTheDocument();
    expect(screen.queryByText(/Full Report/i)).not.toBeInTheDocument();
    expect(await screen.findByTestId('visual-summary-stub')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('report-print-page')).toHaveAttribute('data-print-ready', 'true');
    });
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    expect(window.print).not.toHaveBeenCalled();
  });

  it('does not auto print without autoprint=1', async () => {
    renderPrintPage('/reports/74/print');

    expect(await screen.findByRole('heading', { name: '完整報告' })).toBeInTheDocument();
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    expect(window.print).not.toHaveBeenCalled();
  });

  it('calls window.print after content is ready when autoprint=1', async () => {
    renderPrintPage('/reports/74/print?autoprint=1');

    expect(await screen.findByRole('heading', { name: '完整報告' })).toBeInTheDocument();
    await waitFor(() => {
      expect(window.print).toHaveBeenCalledTimes(1);
    });
  });

  it('shows a zh_TW error state and does not print when markdown loading fails', async () => {
    vi.mocked(historyApi.getMarkdown).mockRejectedValue(new Error('markdown failed'));

    renderPrintPage('/reports/74/print?autoprint=1');

    expect(await screen.findByText('無法載入列印報告')).toBeInTheDocument();
    expect(screen.getByText('請返回完整分析報告後再試一次。')).toBeInTheDocument();
    await new Promise((resolve) => window.setTimeout(resolve, 300));
    expect(window.print).not.toHaveBeenCalled();
  });
});

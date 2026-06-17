import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import type { RunDiagnosticSummary } from '../../../types/analysis';
import { ReportDiagnostics } from '../ReportDiagnostics';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getDiagnostics: vi.fn(),
  },
}));

const diagnosticSummary: RunDiagnosticSummary = {
  traceId: 'trace-1234567890abcdef',
  taskId: 'task-1',
  queryId: 'query-1',
  stockCode: '600519',
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

describe('ReportDiagnostics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

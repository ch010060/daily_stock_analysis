import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TokenUsagePage from '../TokenUsagePage';

const { getDashboard } = vi.hoisted(() => ({
  getDashboard: vi.fn(),
}));

vi.mock('../../api/usage', () => ({
  usageApi: { getDashboard },
}));

const FAKE_DASHBOARD = {
  period: 'month' as const,
  fromDate: '2026-06-01',
  toDate: '2026-06-16',
  totalCalls: 5,
  totalPromptTokens: 400,
  totalCompletionTokens: 800,
  totalTokens: 1200,
  byCallType: [
    { callType: 'analysis', calls: 3, promptTokens: 300, completionTokens: 600, totalTokens: 900 },
  ],
  byModel: [
    {
      model: 'gemini/gemini-2.5-flash',
      calls: 3,
      promptTokens: 300,
      completionTokens: 600,
      totalTokens: 900,
      maxTotalTokens: 300,
    },
  ],
  recentCalls: [
    {
      id: 1,
      calledAt: '2026-06-16T10:00:00',
      callType: 'analysis',
      model: 'gemini/gemini-2.5-flash',
      stockCode: '2330',
      promptTokens: 100,
      completionTokens: 200,
      totalTokens: 300,
    },
  ],
};

describe('TokenUsagePage', () => {
  beforeEach(() => {
    getDashboard.mockReset();
  });

  it('renders page title', async () => {
    getDashboard.mockResolvedValueOnce(FAKE_DASHBOARD);
    render(<TokenUsagePage />);
    await waitFor(() => {
      expect(screen.getByText('Token 用量')).toBeTruthy();
    });
  });

  it('renders total token count after load', async () => {
    getDashboard.mockResolvedValueOnce(FAKE_DASHBOARD);
    render(<TokenUsagePage />);
    await waitFor(() => {
      expect(screen.getByText('1,200')).toBeTruthy();
    });
  });

  it('renders stock code in recent calls table', async () => {
    getDashboard.mockResolvedValueOnce(FAKE_DASHBOARD);
    render(<TokenUsagePage />);
    await waitFor(() => {
      expect(screen.getByText('2330')).toBeTruthy();
    });
  });

  it('shows empty state when total_calls is 0', async () => {
    getDashboard.mockResolvedValueOnce({
      ...FAKE_DASHBOARD,
      totalCalls: 0,
      byCallType: [],
      byModel: [],
      recentCalls: [],
    });
    render(<TokenUsagePage />);
    await waitFor(() => {
      expect(screen.getByText('暫無資料')).toBeTruthy();
    });
  });

  it('shows error state on fetch failure', async () => {
    getDashboard.mockRejectedValueOnce(new Error('network'));
    render(<TokenUsagePage />);
    await waitFor(() => {
      expect(screen.getByText('載入失敗，請重試')).toBeTruthy();
    });
  });

  it('switches period when button clicked', async () => {
    getDashboard.mockResolvedValue(FAKE_DASHBOARD);
    render(<TokenUsagePage />);
    await waitFor(() => screen.getByText('今日'));

    fireEvent.click(screen.getByText('今日'));
    await waitFor(() => {
      expect(getDashboard).toHaveBeenCalledWith('today', 50);
    });
  });
});

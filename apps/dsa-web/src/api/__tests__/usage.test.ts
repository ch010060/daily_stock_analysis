import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usageApi } from '../usage';

const { get } = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get },
}));

const FAKE_DASHBOARD_SNAKE = {
  period: 'month',
  from_date: '2026-06-01',
  to_date: '2026-06-16',
  total_calls: 5,
  total_prompt_tokens: 400,
  total_completion_tokens: 800,
  total_tokens: 1200,
  by_call_type: [
    {
      call_type: 'analysis',
      calls: 3,
      prompt_tokens: 300,
      completion_tokens: 600,
      total_tokens: 900,
    },
  ],
  by_model: [
    {
      model: 'gemini/gemini-2.5-flash',
      calls: 3,
      prompt_tokens: 300,
      completion_tokens: 600,
      total_tokens: 900,
      max_total_tokens: 300,
    },
  ],
  recent_calls: [
    {
      id: 1,
      called_at: '2026-06-16T10:00:00',
      call_type: 'analysis',
      model: 'gemini/gemini-2.5-flash',
      stock_code: '2330',
      prompt_tokens: 100,
      completion_tokens: 200,
      total_tokens: 300,
    },
  ],
};

describe('usageApi', () => {
  beforeEach(() => {
    get.mockReset();
  });

  it('getDashboard sends correct params and returns camelCase response', async () => {
    get.mockResolvedValueOnce({ data: FAKE_DASHBOARD_SNAKE });

    const result = await usageApi.getDashboard('month', 50);

    expect(get).toHaveBeenCalledWith('/api/v1/usage/dashboard', {
      params: { period: 'month', limit: 50 },
    });
    expect(result.period).toBe('month');
    expect(result.totalCalls).toBe(5);
    expect(result.totalPromptTokens).toBe(400);
    expect(result.totalCompletionTokens).toBe(800);
    expect(result.totalTokens).toBe(1200);
  });

  it('getDashboard maps by_call_type to camelCase', async () => {
    get.mockResolvedValueOnce({ data: FAKE_DASHBOARD_SNAKE });

    const result = await usageApi.getDashboard('month', 50);
    const ct = result.byCallType[0];

    expect(ct.callType).toBe('analysis');
    expect(ct.promptTokens).toBe(300);
    expect(ct.completionTokens).toBe(600);
    expect(ct.totalTokens).toBe(900);
  });

  it('getDashboard maps by_model with maxTotalTokens', async () => {
    get.mockResolvedValueOnce({ data: FAKE_DASHBOARD_SNAKE });

    const result = await usageApi.getDashboard('month', 50);
    const m = result.byModel[0];

    expect(m.model).toBe('gemini/gemini-2.5-flash');
    expect(m.maxTotalTokens).toBe(300);
  });

  it('getDashboard maps recent_calls with TW stock code', async () => {
    get.mockResolvedValueOnce({ data: FAKE_DASHBOARD_SNAKE });

    const result = await usageApi.getDashboard('month', 50);
    const rec = result.recentCalls[0];

    expect(rec.stockCode).toBe('2330');
    expect(rec.calledAt).toBe('2026-06-16T10:00:00');
    expect(rec.promptTokens).toBe(100);
    expect(rec.completionTokens).toBe(200);
    expect(rec.totalTokens).toBe(300);
  });

  it('getDashboard defaults to month period', async () => {
    get.mockResolvedValueOnce({ data: FAKE_DASHBOARD_SNAKE });

    await usageApi.getDashboard();

    expect(get).toHaveBeenCalledWith('/api/v1/usage/dashboard', {
      params: { period: 'month', limit: 50 },
    });
  });
});

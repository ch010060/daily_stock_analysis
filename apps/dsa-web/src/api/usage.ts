import apiClient from './index';
import { toCamelCase } from './utils';

export type UsagePeriod = 'today' | 'month' | 'all';

export interface UsageCallTypeBreakdown {
  callType: string;
  calls: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface UsageModelBreakdown {
  model: string;
  calls: number;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  maxTotalTokens: number;
}

export interface UsageCallRecord {
  id: number;
  calledAt: string;
  callType: string;
  model: string;
  stockCode: string | null;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface UsageDashboard {
  period: UsagePeriod;
  fromDate: string;
  toDate: string;
  totalCalls: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  byCallType: UsageCallTypeBreakdown[];
  byModel: UsageModelBreakdown[];
  recentCalls: UsageCallRecord[];
}

export const usageApi = {
  async getDashboard(period: UsagePeriod = 'month', limit = 50): Promise<UsageDashboard> {
    const response = await apiClient.get('/api/v1/usage/dashboard', {
      params: { period, limit },
    });
    return toCamelCase<UsageDashboard>(response.data);
  },
};

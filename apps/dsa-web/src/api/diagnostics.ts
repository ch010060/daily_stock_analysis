import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  NewsProviderProbeItem,
  NewsProviderProbeRequest,
  NewsProviderProbeResponse,
} from '../types/analysis';

export const diagnosticsApi = {
  probeNewsProvider: async (
    payload: NewsProviderProbeRequest,
  ): Promise<NewsProviderProbeResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/diagnostics/news-provider-probe',
      {
        symbol: payload.symbol,
        market: payload.market,
        provider_mode: payload.providerMode ?? 'runtime',
        limit: payload.limit ?? 4,
      },
    );

    const data = toCamelCase<NewsProviderProbeResponse>(response.data);
    return {
      ...data,
      providersAttempted: data.providersAttempted || [],
      queryVariants: data.queryVariants || [],
      attemptCount: data.attemptCount ?? 0,
      resultCount: data.resultCount ?? 0,
      fallbackUsed: Boolean(data.fallbackUsed),
      latencyMs: data.latencyMs ?? 0,
      items: (data.items || []).map((item) => toCamelCase<NewsProviderProbeItem>(item)),
    };
  },
};

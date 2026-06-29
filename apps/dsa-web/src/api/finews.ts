import apiClient from './index';
import { toCamelCase } from './utils';

export type FinewsSectionKey =
  | 'afterMarketSummary'
  | 'majorNews'
  | 'marketTemperature'
  | 'majorIndices'
  | 'majorStocks'
  | 'treasuryYields'
  | 'fx';

export type FinewsSections = Record<FinewsSectionKey, string[]>;

export type FinewsExternalLink = {
  title: string;
  url: string;
};

export type FinewsSectionLinks = Record<FinewsSectionKey, FinewsExternalLink[]>;

export type FinewsSnapshot = {
  source: 'finews';
  sourceUrl: string;
  reportDate: string | null;
  sourceUpdatedAt: string | null;
  fetchedAt: string;
  stale: boolean;
  fetchError: string | null;
  languageOriginal: 'zh-CN';
  languageRendered: 'zh-TW';
  externalLinks: FinewsExternalLink[];
  sectionLinks?: FinewsSectionLinks;
  sections: FinewsSections;
};

export const finewsApi = {
  getLatest: async (): Promise<FinewsSnapshot> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/finews/latest');
    return toCamelCase<FinewsSnapshot>(response.data);
  },
};

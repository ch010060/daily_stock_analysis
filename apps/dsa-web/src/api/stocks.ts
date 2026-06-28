import apiClient from './index';
import { toCamelCase } from './utils';

export type ExtractItem = {
  code?: string | null;
  name?: string | null;
  confidence: string;
};

export type ExtractFromImageResponse = {
  codes: string[];
  items?: ExtractItem[];
  rawText?: string;
};

export type SymbolCandidateResponse = {
  canonicalSymbol: string;
  rawSymbol: string;
  symbol: string;
  market: string;
  exchange?: string | null;
  instrumentType: string;
  name: string;
  aliases: string[];
  providerSource: string;
  isActive: boolean;
  lastUpdated?: string | null;
  confidence: number;
  matchReason: string;
};

export type SymbolResolveResponse = {
  query: string;
  status: string;
  selected?: SymbolCandidateResponse | null;
  candidates: SymbolCandidateResponse[];
  message?: string | null;
};

export const stocksApi = {
  async resolveSymbol(q: string, market?: 'TW' | 'US' | 'tw' | 'us'): Promise<SymbolResolveResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stocks/resolve', {
      params: {
        q,
        ...(market ? { market } : {}),
      },
    });
    return toCamelCase<SymbolResolveResponse>(response.data);
  },

  async extractFromImage(file: File): Promise<ExtractFromImageResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
    const response = await apiClient.post(
      '/api/v1/stocks/extract-from-image',
      formData,
      {
        headers,
        timeout: 60000, // Vision API can be slow; 60s
      },
    );

    const data = response.data as { codes?: string[]; items?: ExtractItem[]; raw_text?: string };
    return {
      codes: data.codes ?? [],
      items: data.items,
      rawText: data.raw_text,
    };
  },

  async parseImport(file?: File, text?: string): Promise<ExtractFromImageResponse> {
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
      const response = await apiClient.post('/api/v1/stocks/parse-import', formData, { headers });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    if (text) {
      const response = await apiClient.post('/api/v1/stocks/parse-import', { text });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    throw new Error('請提供檔案或貼上文字');
  },
};

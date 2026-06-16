import { normalizeReportLanguage } from './reportLanguage';

const USAGE_TEXT = {
  zh: {
    title: 'Token 用量',
    period: {
      today: '今日',
      month: '本月',
      all: '全部',
    },
    totalCalls: '总调用次数',
    totalTokens: '总 Token 数',
    promptTokens: '输入 Token',
    completionTokens: '输出 Token',
    byCallType: '按调用类型',
    byModel: '按模型',
    recentCalls: '最近调用',
    callType: '类型',
    model: '模型',
    stockCode: '股票代码',
    calledAt: '调用时间',
    tokens: 'Token',
    maxTokens: '单次峰值',
    calls: '次数',
    loading: '加载中...',
    loadError: '加载失败，请重试',
    noData: '暂无数据',
    retry: '重试',
  },
  zh_TW: {
    title: 'Token 用量',
    period: {
      today: '今日',
      month: '本月',
      all: '全部',
    },
    totalCalls: '總呼叫次數',
    totalTokens: '總 Token 數',
    promptTokens: '輸入 Token',
    completionTokens: '輸出 Token',
    byCallType: '依呼叫類型',
    byModel: '依模型',
    recentCalls: '最近呼叫',
    callType: '類型',
    model: '模型',
    stockCode: '股票代碼',
    calledAt: '呼叫時間',
    tokens: 'Token',
    maxTokens: '單次峰值',
    calls: '次數',
    loading: '載入中...',
    loadError: '載入失敗，請重試',
    noData: '暫無資料',
    retry: '重試',
  },
  en: {
    title: 'Token Usage',
    period: {
      today: 'Today',
      month: 'This Month',
      all: 'All Time',
    },
    totalCalls: 'Total Calls',
    totalTokens: 'Total Tokens',
    promptTokens: 'Prompt Tokens',
    completionTokens: 'Completion Tokens',
    byCallType: 'By Call Type',
    byModel: 'By Model',
    recentCalls: 'Recent Calls',
    callType: 'Type',
    model: 'Model',
    stockCode: 'Stock Code',
    calledAt: 'Called At',
    tokens: 'Tokens',
    maxTokens: 'Peak per Call',
    calls: 'Calls',
    loading: 'Loading...',
    loadError: 'Failed to load. Please retry.',
    noData: 'No data available',
    retry: 'Retry',
  },
};

export type UsageText = {
  title: string;
  period: { today: string; month: string; all: string };
  totalCalls: string;
  totalTokens: string;
  promptTokens: string;
  completionTokens: string;
  byCallType: string;
  byModel: string;
  recentCalls: string;
  callType: string;
  model: string;
  stockCode: string;
  calledAt: string;
  tokens: string;
  maxTokens: string;
  calls: string;
  loading: string;
  loadError: string;
  noData: string;
  retry: string;
};

export const getUsageText = (language?: string | null): UsageText =>
  USAGE_TEXT[normalizeReportLanguage(language)];

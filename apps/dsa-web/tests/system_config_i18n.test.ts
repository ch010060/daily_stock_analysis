import { describe, expect, it } from 'vitest';
import { getFieldDescriptionZh, getFieldOptionLabelZh, getFieldTitleZh } from '../src/utils/systemConfigI18n';

const requiredLocalizedKeys = [
  'TICKFLOW_API_KEY',
  'STOCK_INDEX_REMOTE_UPDATE_ENABLED',
  'SEARXNG_BASE_URLS',
  'ENABLE_REALTIME_QUOTE',
  'ENABLE_CHIP_DISTRIBUTION',
  'PYTDX_HOST',
  'PYTDX_PORT',
  'PYTDX_SERVERS',
  'BIAS_THRESHOLD',
  'TELEGRAM_BOT_TOKEN',
  'TELEGRAM_CHAT_ID',
  'TELEGRAM_MESSAGE_THREAD_ID',
  'FEISHU_STREAM_ENABLED',
  'DINGTALK_STREAM_ENABLED',
  'EMAIL_SENDER',
  'EMAIL_PASSWORD',
  'EMAIL_RECEIVERS',
  'DISCORD_WEBHOOK_URL',
  'DISCORD_BOT_TOKEN',
  'DISCORD_MAIN_CHANNEL_ID',
  'DISCORD_INTERACTIONS_PUBLIC_KEY',
  'SLACK_BOT_TOKEN',
  'SLACK_CHANNEL_ID',
  'SLACK_WEBHOOK_URL',
  'PUSHPLUS_TOPIC',
  'PUSHOVER_USER_KEY',
  'PUSHOVER_API_TOKEN',
  'SERVERCHAN3_SENDKEY',
  'ASTRBOT_URL',
  'ASTRBOT_TOKEN',
  'CUSTOM_WEBHOOK_BEARER_TOKEN',
  'WEBHOOK_VERIFY_SSL',
  'SINGLE_STOCK_NOTIFY',
  'REPORT_TYPE',
  'REPORT_LANGUAGE',
  'REPORT_TEMPLATES_DIR',
  'REPORT_INTEGRITY_ENABLED',
  'REPORT_RENDERER_ENABLED',
  'REPORT_INTEGRITY_RETRY',
  'REPORT_HISTORY_COMPARE_N',
  'MERGE_EMAIL_NOTIFICATION',
  'NOTIFICATION_REPORT_CHANNELS',
  'NOTIFICATION_ALERT_CHANNELS',
  'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
  'NOTIFICATION_DEDUP_TTL_SECONDS',
  'NOTIFICATION_COOLDOWN_SECONDS',
  'NOTIFICATION_QUIET_HOURS',
  'NOTIFICATION_TIMEZONE',
  'NOTIFICATION_MIN_SEVERITY',
  'NOTIFICATION_DAILY_DIGEST_ENABLED',
  'SCHEDULE_ENABLED',
  'SCHEDULE_RUN_IMMEDIATELY',
  'TRADING_DAY_CHECK_ENABLED',
  'WEBUI_HOST',
  'LOG_DIR',
  'WEBUI_ENABLED',
  'WEBUI_AUTO_BUILD',
  'ADMIN_AUTH_ENABLED',
  'TRUST_X_FORWARDED_FOR',
  'RUN_IMMEDIATELY',
  'MARKET_REVIEW_ENABLED',
  'MARKET_REVIEW_REGION',
  'ANALYSIS_DELAY',
  'DEBUG',
  'AGENT_NL_ROUTING',
  'AGENT_DEEP_RESEARCH_BUDGET',
  'AGENT_DEEP_RESEARCH_TIMEOUT',
  'AGENT_EVENT_MONITOR_ENABLED',
  'AGENT_EVENT_MONITOR_INTERVAL_MINUTES',
  'AGENT_EVENT_ALERT_RULES_JSON',
] as const;

describe('systemConfigI18n required key coverage', () => {
  it('provides zh title and description mapping for known missing keys', () => {
    requiredLocalizedKeys.forEach((key) => {
      expect(getFieldTitleZh(key, key)).not.toBe(key);
      expect(getFieldDescriptionZh(key, 'schema fallback description')).not.toBe('schema fallback description');
    });
  });

  it('uses a Chinese primary title for SearXNG base URLs', () => {
    const title = getFieldTitleZh('SEARXNG_BASE_URLS', 'SEARXNG_BASE_URLS');

    expect(title).toBe('SearXNG 自建例項地址');
    expect(title).not.toBe('SearXNG Base URLs');
  });
});

describe('systemConfigI18n option label localization', () => {
  const realSelectOptionCases = [
    ['NEWS_STRATEGY_PROFILE', 'ultra_short', undefined, '超短線（1天）'],
    ['NEWS_STRATEGY_PROFILE', 'short', undefined, '短期（3天）'],
    ['NEWS_STRATEGY_PROFILE', 'medium', undefined, '中期（7天）'],
    ['NEWS_STRATEGY_PROFILE', 'long', undefined, '長期（30天）'],
    ['REPORT_TYPE', 'simple', undefined, '簡潔'],
    ['REPORT_TYPE', 'full', undefined, '完整'],
    ['REPORT_TYPE', 'brief', undefined, '簡報'],
    ['REPORT_LANGUAGE', 'zh', 'Chinese', '中文'],
    ['REPORT_LANGUAGE', 'en', 'English', '英文'],
    ['NOTIFICATION_MIN_SEVERITY', '', 'Not set', '未設定'],
    ['NOTIFICATION_MIN_SEVERITY', 'info', 'info', '資訊'],
    ['NOTIFICATION_MIN_SEVERITY', 'warning', 'warning', '警告'],
    ['NOTIFICATION_MIN_SEVERITY', 'error', 'error', '錯誤'],
    ['NOTIFICATION_MIN_SEVERITY', 'critical', 'critical', '嚴重'],
    ['LOG_LEVEL', 'DEBUG', undefined, '除錯'],
    ['LOG_LEVEL', 'INFO', undefined, '資訊'],
    ['LOG_LEVEL', 'WARNING', undefined, '警告'],
    ['LOG_LEVEL', 'ERROR', undefined, '錯誤'],
    ['LOG_LEVEL', 'CRITICAL', undefined, '嚴重'],
    ['MARKET_REVIEW_REGION', 'cn', undefined, 'A 股'],
    ['MARKET_REVIEW_REGION', 'hk', undefined, '港股'],
    ['MARKET_REVIEW_REGION', 'us', undefined, '美股'],
    ['MARKET_REVIEW_REGION', 'both', undefined, '全部市場'],
    ['MARKET_REVIEW_COLOR_SCHEME', 'green_up', 'Green Up / Red Down', '綠漲紅跌'],
    ['MARKET_REVIEW_COLOR_SCHEME', 'red_up', 'Red Up / Green Down', '紅漲綠跌'],
    ['AGENT_ARCH', 'single', 'Single Agent', '單 Agent'],
    ['AGENT_ARCH', 'multi', 'Multi Agent (Orchestrator)', '多 Agent（編排）'],
    ['AGENT_ORCHESTRATOR_MODE', 'quick', 'Quick', '快速'],
    ['AGENT_ORCHESTRATOR_MODE', 'standard', 'Standard', '標準'],
    ['AGENT_ORCHESTRATOR_MODE', 'full', 'Full', '完整'],
    ['AGENT_ORCHESTRATOR_MODE', 'specialist', 'Specialist', '專家'],
    ['AGENT_SKILL_ROUTING', 'auto', 'Auto (Regime-based)', '自動（按市場狀態）'],
    ['AGENT_SKILL_ROUTING', 'manual', 'Manual (Use AGENT_SKILLS)', '手動（使用 AGENT_SKILLS）'],
  ] as const;

  it('localizes all select options currently exposed by system config schema', () => {
    realSelectOptionCases.forEach(([key, value, fallbackLabel, expectedLabel]) => {
      const label = getFieldOptionLabelZh(key, value, fallbackLabel);

      expect(label).toBe(expectedLabel);
      expect(label).not.toBe(value);
      if (fallbackLabel) {
        expect(label).not.toBe(fallbackLabel);
      }
    });
  });
});

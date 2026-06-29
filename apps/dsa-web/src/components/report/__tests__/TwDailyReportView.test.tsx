import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TwDailyReportView } from '../TwDailyReportView';
import { parseTwDailyReportMarkdown } from '../twDailyReportAdapter';

const PARSEABLE_MARKET_REVIEW = [
  '# 台股大盤回顧',
  '',
  '> 資料日期：2026-06-26',
  '',
  '## 今日盤勢摘要',
  '',
  '今日所有必要指標資料完整，可進行完整分析。',
  '',
  '## 指數表現',
  '',
  '- 加權報酬指數（TAIEX）：23,000.00 點 🟢 +120.00（+0.52%）',
  '- 櫃買報酬指數（TPEx）：260.00 點 🔴 -1.50（-0.57%）',
  '',
  '## 法人與資金面',
  '',
  '- 外資：買 1,200.0 億，賣 1,000.0 億，淨 ▲ 200.0 億',
  '- 投信：買 80.0 億，賣 60.0 億，淨 ▲ 20.0 億',
  '',
  '## 融資融券觀察',
  '',
  '- 融資餘額：今日 2,200.0 億，較昨日 ▼ 10.0 億',
  '- 融券張數：今日 55,000 張，較昨日 ▲ 2,000 張',
  '',
  '## 0050 / 臺積電參考',
  '',
  '- 元大台灣50（0050）：收盤 180.20（2026-06-26）',
  '- 臺積電（2330）：收盤 1,080.00（2026-06-26）',
  '',
  '## 風險與注意事項',
  '',
  '- 市場有風險，投資需謹慎。以上資料僅供參考，不構成投資建議。',
].join('\n');

describe('TwDailyReportView', () => {
  it('parses the deterministic Taiwan daily markdown into a structured view model', () => {
    const report = parseTwDailyReportMarkdown(PARSEABLE_MARKET_REVIEW);

    expect(report).not.toBeNull();
    expect(report?.dataDate).toBe('2026-06-26');
    expect(report?.source).toBe('FinMind');
    expect(report?.indices).toHaveLength(2);
    expect(report?.institutional).toHaveLength(2);
    expect(report?.margin).toHaveLength(2);
    expect(report?.representatives).toHaveLength(2);
    expect(report?.dataStatus).toContain('必要指標資料完整');
  });

  it('renders the structured Taiwan daily reader with main and market-tape sections', () => {
    const report = parseTwDailyReportMarkdown(PARSEABLE_MARKET_REVIEW);
    expect(report).not.toBeNull();

    render(<TwDailyReportView report={report!} />);

    expect(screen.getByTestId('tw-daily-reader')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '台股日報' })).toBeInTheDocument();
    expect(screen.getByText('FinMind 台股最後交易日快照')).toBeInTheDocument();
    expect(screen.getAllByText('2026-06-26')).not.toHaveLength(0);
    expect(screen.getByText('今日重點')).toBeInTheDocument();
    expect(screen.getByText('主要指數')).toBeInTheDocument();
    expect(screen.getByText('法人與資金面')).toBeInTheDocument();
    expect(screen.getByText('融資融券')).toBeInTheDocument();
    expect(screen.getByText('代表標的')).toBeInTheDocument();
    expect(screen.getByText('資料狀態')).toBeInTheDocument();
    expect(screen.getByText('TAIEX')).toBeInTheDocument();
    expect(screen.getByText('0050')).toBeInTheDocument();
  });

  it('returns null for legacy or incomplete markdown so callers can use the old fallback', () => {
    expect(parseTwDailyReportMarkdown('# 台股大盤回顧\n\n只有標題')).toBeNull();
    expect(parseTwDailyReportMarkdown('# 普通報告\n\n內容')).toBeNull();
  });

  it('does not render unsafe remote containers or raw HTML paths', () => {
    const report = parseTwDailyReportMarkdown(PARSEABLE_MARKET_REVIEW);
    const { container } = render(<TwDailyReportView report={report!} />);

    expect(container.querySelector('iframe')).toBeNull();
    expect(container.innerHTML).not.toContain('dangerouslySetInnerHTML');
    expect(container.innerHTML).not.toContain('html2canvas');
    expect(container.innerHTML).not.toContain('jsPDF');
  });
});

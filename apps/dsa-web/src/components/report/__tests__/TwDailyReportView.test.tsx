import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TwDailyReportView } from '../TwDailyReportView';
import { buildTwDailyReportFromSnapshot, parseTwDailyReportMarkdown } from '../twDailyReportAdapter';

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

const STRUCTURED_TW_DAILY_SNAPSHOT = {
  kind: 'tw_daily_snapshot',
  source: 'finmind',
  dataDate: '2026-06-26',
  datasets: [
    { key: 'taiex', dataset: 'TaiwanStockTotalReturnIndex', ok: true, as_of: '2026-06-26' },
    { key: 'ref_006208', dataset: 'TaiwanStockPrice', data_id: '006208', ok: true, as_of: '2026-06-26' },
  ],
  indices: [
    {
      symbol: 'TAIEX',
      name: '加權報酬指數',
      value: 23000,
      change: -120,
      changePct: -0.52,
      dataDate: '2026-06-26',
      semanticDirection: 'tw_loss',
    },
    {
      symbol: 'TPEx',
      name: '櫃買報酬指數',
      value: 260,
      change: 1.5,
      changePct: 0.57,
      dataDate: '2026-06-26',
      semanticDirection: 'tw_gain',
    },
  ],
  institutionalFlows: [
    {
      name: '外資',
      buy: 140000000000,
      sell: 120000000000,
      net: 20000000000,
      unit: 'TWD',
      displayDivisor: 100000000,
      dataDate: '2026-06-26',
      semanticDirection: 'net_buy',
    },
    {
      name: '投信',
      buy: 30000000000,
      sell: 45000000000,
      net: -15000000000,
      unit: 'TWD',
      displayDivisor: 100000000,
      dataDate: '2026-06-26',
      semanticDirection: 'net_sell',
    },
    {
      name: 'Foreign_Dealer_Self',
      buy: 0,
      sell: 0,
      net: 0,
      unit: 'TWD',
      displayDivisor: 100000000,
      dataDate: '2026-06-26',
      semanticDirection: 'neutral',
    },
  ],
  marginShort: [
    {
      name: 'MarginPurchase',
      todayBalance: 220000000000,
      yesterdayBalance: 221000000000,
      change: -1000000000,
      unit: 'TWD',
      displayDivisor: 100000000,
      dataDate: '2026-06-26',
      semanticType: 'risk_or_leverage',
    },
    {
      name: 'ShortSale',
      todayBalance: 0,
      yesterdayBalance: 0,
      change: -0,
      unit: 'shares',
      dataDate: '2026-06-26',
      semanticType: 'risk_or_leverage',
    },
  ],
  representatives: [
    {
      symbol: '0050',
      name: '元大台灣50',
      close: 180.2,
      previousClose: 179.2,
      change: 1,
      changePct: 0.56,
      volume: 12000000,
      turnover: 2162400000,
      dataDate: '2026-06-26',
      missingFields: ['PER', 'PBR', 'dividend_yield'],
      semanticDirection: 'tw_gain',
    },
    {
      symbol: '006208',
      name: '富邦台50',
      close: 112.4,
      previousClose: 112.8,
      change: -0.4,
      changePct: -0.35,
      volume: 3400000,
      turnover: 382160000,
      dataDate: '2026-06-26',
      missingFields: ['PER', 'PBR', 'dividend_yield'],
      semanticDirection: 'tw_loss',
    },
    {
      symbol: '2330',
      name: '臺積電',
      close: 1415,
      previousClose: 1400,
      change: 15,
      changePct: 1.07,
      volume: 26000000,
      turnover: 36790000000,
      dataDate: '2026-06-26',
      PER: 24.5,
      PBR: 6.8,
      dividendYield: 1.45,
      valuationAsOf: '2026-06-26',
      semanticDirection: 'tw_gain',
    },
  ],
  dataStatus: {
    missingFields: [
      'representatives.0050.PER',
      'representatives.0050.PBR',
      'representatives.0050.dividend_yield',
      'representatives.006208.PER',
      'representatives.006208.PBR',
      'representatives.006208.dividend_yield',
    ],
    staleFields: [],
    partialFailures: ['per_0050', 'per_006208'],
  },
};

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
    expect(screen.getByText('TAIEX')).toBeInTheDocument();
    expect(screen.getByText('0050')).toBeInTheDocument();
  });

  it('returns null for legacy or incomplete markdown so callers can use the old fallback', () => {
    expect(parseTwDailyReportMarkdown('# 台股大盤回顧\n\n只有標題')).toBeNull();
    expect(parseTwDailyReportMarkdown('# 普通報告\n\n內容')).toBeNull();
  });

  it('builds and renders a Taiwan daily reader from structured tw_daily_snapshot', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);

    expect(report).not.toBeNull();
    render(<TwDailyReportView report={report!} />);

    expect(screen.getByText('0050')).toBeInTheDocument();
    expect(screen.getByText('006208')).toBeInTheDocument();
    expect(screen.getByText('2330')).toBeInTheDocument();
    expect(screen.getByText(/PER 24\.50/)).toBeInTheDocument();
    expect(screen.getAllByText('估值資料未提供').length).toBeGreaterThan(0);
  });

  it('uses Taiwan color semantics for price, flow, and margin rows', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);
    render(<TwDailyReportView report={report!} />);

    expect(screen.getByText('TAIEX').closest('[data-tone]')).toHaveAttribute('data-tone', 'tw-loss');
    expect(screen.getByText('TPEx').closest('[data-tone]')).toHaveAttribute('data-tone', 'tw-gain');
    expect(screen.getByText('006208').closest('[data-tone]')).toHaveAttribute('data-tone', 'tw-loss');
    expect(screen.getByText('買 1,400.0 億')).toHaveAttribute('data-tone', 'tw-buy');
    expect(screen.getByText('賣 1,200.0 億')).toHaveAttribute('data-tone', 'tw-sell');
    expect(screen.getAllByText('淨買超 200.0 億').some((node) => node.getAttribute('data-tone') === 'net-buy')).toBe(true);
    expect(screen.getAllByText('淨賣超 150.0 億').some((node) => node.getAttribute('data-tone') === 'net-sell')).toBe(true);
    expect(screen.getByText('融資').closest('[data-tone]')).toHaveAttribute('data-tone', 'risk');
    expect(screen.getByText('淨額 0.0 億')).toHaveAttribute('data-tone', 'neutral');
    expect(screen.queryByText('淨買超 0.0 億')).not.toBeInTheDocument();
    expect(screen.queryByText('淨賣超 0.0 億')).not.toBeInTheDocument();
  });

  it('hides raw snapshot ids, raw missing keys, and object serialization', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);
    const { container } = render(<TwDailyReportView report={report!} />);
    const text = container.textContent || '';

    expect(text).not.toContain('Foreign_Dealer_Self');
    expect(text).not.toContain('MarginPurchase');
    expect(text).not.toContain('ShortSale');
    expect(text).not.toContain('representatives.0050.PER');
    expect(text).not.toContain('representatives.006208.dividend_yield');
    expect(text).not.toContain('[object Object]');
    expect(screen.getByText('外資自營商')).toBeInTheDocument();
    expect(screen.getByText('融資')).toBeInTheDocument();
    expect(screen.getByText('融券')).toBeInTheDocument();
    expect(screen.getAllByText('估值資料未提供')).toHaveLength(2);
    expect(screen.queryByText('資料集：2 項')).not.toBeInTheDocument();
    expect(screen.queryByText('資料狀態')).not.toBeInTheDocument();
  });

  it('uses non-wrapping sidebar structure for ticker, date, and value fields', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);
    render(<TwDailyReportView report={report!} />);

    expect(screen.getByText('006208')).toHaveClass('whitespace-nowrap');
    expect(screen.getAllByText(/2026-06-26/)[0]).toHaveClass('whitespace-nowrap');
    expect(screen.getByText(/收盤 112\.40/)).toHaveClass('whitespace-nowrap');
  });

  it('does not truncate market tape labels with ellipsis classes', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);
    const { container } = render(<TwDailyReportView report={report!} />);

    expect(screen.getByText('加權報酬指數')).toBeInTheDocument();
    expect(screen.getByText('櫃買報酬指數')).toBeInTheDocument();
    expect(container.querySelector('.truncate')).toBeNull();
  });

  it('omits filler-only recap and risk sections', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);
    render(<TwDailyReportView report={report!} />);

    expect(screen.queryByText('台股大盤回顧')).not.toBeInTheDocument();
    expect(screen.queryByText('主要敘述已整理至今日重點與右側資料表。')).not.toBeInTheDocument();
    expect(screen.queryByText('風險解讀 / 操作觀察')).not.toBeInTheDocument();
    expect(screen.queryByText('本次報告未提供額外風險註記。')).not.toBeInTheDocument();
  });

  it('renders meaningful recap and risk sections when provided', () => {
    const report = buildTwDailyReportFromSnapshot(STRUCTURED_TW_DAILY_SNAPSHOT);
    render(
      <TwDailyReportView
        report={{
          ...report!,
          summary: '加權指數反彈，但櫃買仍偏弱，資金集中在大型權值股。',
          risks: ['外資期現貨同步偏空時，反彈延續性需要保守看待。'],
        }}
      />,
    );

    expect(screen.getByText('台股大盤回顧')).toBeInTheDocument();
    expect(screen.getByText('加權指數反彈，但櫃買仍偏弱，資金集中在大型權值股。')).toBeInTheDocument();
    expect(screen.getByText('風險解讀 / 操作觀察')).toBeInTheDocument();
    expect(screen.getByText('外資期現貨同步偏空時，反彈延續性需要保守看待。')).toBeInTheDocument();
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

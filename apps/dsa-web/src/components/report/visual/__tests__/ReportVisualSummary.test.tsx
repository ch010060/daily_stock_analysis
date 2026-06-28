import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ReportVisualSummary } from '../ReportVisualSummary';
import { MSFT_REPORT, MINIMAL_REPORT } from './fixtures';

vi.mock('../KlineChartBlock', () => ({
  KlineChartBlock: ({ instrumentType }: { instrumentType: string }) => (
    <div data-testid="kline-chart-block">K-line {instrumentType}</div>
  ),
}));

describe('ReportVisualSummary', () => {
  it('renders the main container with testid', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('report-visual-summary')).toBeInTheDocument();
  });

  it('shows stock code and name', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    const el = screen.getByTestId('report-visual-summary');
    expect(el.textContent).toContain('MSFT');
    expect(el.textContent).toContain('Microsoft Corp');
  });

  it('shows decision text', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('report-visual-summary').textContent).toContain('觀望');
  });

  it('shows VIX gauge', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('market-risk-gauge')).toBeInTheDocument();
  });

  it('shows multi-period trend bars', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('multi-period-trend-bars')).toBeInTheDocument();
  });

  it('shows technical snapshot cards', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('technical-snapshot-cards')).toBeInTheDocument();
  });

  it('shows financial result cards for stock reports', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('financial-result-cards')).toBeInTheDocument();
  });

  it('shows action plan cards', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('action-plan-cards')).toBeInTheDocument();
  });

  it('renders without crashing on minimal report with no rawResult', () => {
    render(<ReportVisualSummary report={MINIMAL_REPORT} />);
    // Should either render or return null — must not throw
    // It may render the visual summary with gap states
  });

  it('shows VIX value in the KPI row when available', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    const el = screen.getByTestId('report-visual-summary');
    expect(el.textContent).toContain('18.89');
  });

  it('renders TW market sentiment instead of a misleading VIX gap', () => {
    const twEtfReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '006208',
        stockName: '富邦台50',
      },
      summary: {
        ...MSFT_REPORT.summary,
        sentimentScore: 42,
        sentimentLabel: '中性' as const,
      },
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          marketRiskSnapshot: {
            source: null,
            vixLevel: null,
            vixStatus: null,
            spxChangePct: null,
            dataGapFields: ['vix_level', 'vix_status', 'spx_change_pct'],
          },
          exposureSnapshot: { dataGapFields: [] },
        },
      },
    };

    render(<ReportVisualSummary report={twEtfReport} />);
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('系統評分');
    expect(gauge.textContent).toContain('42');
    expect(gauge.textContent).toContain('中性');
    expect(gauge.textContent).not.toContain(['恐慌', '貪婪', '分數'].join(''));
    expect(gauge.textContent).not.toContain('VIX 資料不足');
    expect(gauge.textContent).not.toContain('VIX 恐慌指數');
    expect(screen.getByText('系統評分')).toHaveAttribute('aria-label', expect.stringContaining('非 VIXTWN'));
  });

  it('renders TW VIXTWN and system score in one market gauge when snapshot exists', () => {
    const twEtfReport = {
      ...MSFT_REPORT,
      meta: {
        ...MSFT_REPORT.meta,
        stockCode: '006208',
        stockName: '富邦台50',
      },
      summary: {
        ...MSFT_REPORT.summary,
        sentimentScore: 42,
        sentimentLabel: '中性' as const,
      },
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'etf',
          marketFearIndexSnapshot: {
            market: 'tw',
            kind: 'vixtwn',
            label: '台灣恐慌指數 VIXTWN',
            value: 44.27,
            asOf: '2026-06-26',
            source: 'taifex',
            sourceUrlKey: 'taifex_vixtwn_daily_txt',
            status: 'unknown',
            dataGapReason: null,
          },
          marketRiskSnapshot: {
            source: null,
            vixLevel: null,
            vixStatus: null,
            spxChangePct: null,
            dataGapFields: ['vix_level', 'vix_status', 'spx_change_pct'],
          },
          exposureSnapshot: { dataGapFields: [] },
        },
      },
    };

    render(<ReportVisualSummary report={twEtfReport} />);
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('台灣恐慌指數 VIXTWN');
    expect(gauge.textContent).toContain('VIXTWN 44.27');
    expect(gauge.textContent).toContain('日期：2026-06-26');
    expect(gauge.textContent).toContain('系統評分');
    expect(screen.getAllByTestId(/market-risk-gauge/)).toHaveLength(1);
    expect(screen.getByTestId('market-fear-meter')).toBeInTheDocument();
    expect(screen.getByTestId('market-fear-pointer')).toBeInTheDocument();
    expect(screen.getByTestId('system-score-pointer')).toBeInTheDocument();
    expect(gauge.textContent).not.toContain('市場情緒 ·');
    expect(gauge.textContent).not.toContain('市場風險 ·');
  });

  it('renders without crashing on malformed rawResult', () => {
    const badReport = {
      ...MSFT_REPORT,
      details: {
        rawResult: { marketRiskSnapshot: 'not-an-object', multiPeriodTrendSnapshot: null },
      },
    };
    expect(() => render(<ReportVisualSummary report={badReport} />)).not.toThrow();
  });

  // F1.1: root must carry report-light-surface to force light surface regardless of app theme
  it('root container has report-light-surface class', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    const el = screen.getByTestId('report-visual-summary');
    expect(el.className).toContain('report-light-surface');
  });

  // R3: hero remains the only primary decision anchor; KPI row must not repeat operationAdvice
  it('shows a compact key-trigger KPI instead of repeating operation advice', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    const el = screen.getByTestId('report-visual-summary');
    expect(el.textContent).toContain('觀望');
    expect(el.textContent).not.toContain('操作建議');
    expect(el.textContent).not.toContain('空倉觀望');

    const trigger = screen.getByTestId('visual-summary-trigger-kpi');
    const triggerValue = screen.getByTestId('visual-summary-trigger-value');
    expect(trigger.textContent).toContain('關鍵觸發');
    expect(trigger.textContent).toMatch(/MA|放量|量能|風控|壓力|確認|等待/);
    expect(trigger.textContent).not.toContain('觀望');
    expect(trigger.textContent).not.toContain('詳見');
    expect(trigger.textContent).not.toContain('下方');
    expect(triggerValue.className).toContain('whitespace-nowrap');
  });

  it('shows a safe key-trigger fallback when strategy details are unavailable', () => {
    render(<ReportVisualSummary report={MINIMAL_REPORT} />);
    const trigger = screen.getByTestId('visual-summary-trigger-kpi');
    expect(trigger.textContent).toContain('關鍵觸發');
    expect(trigger.textContent).toContain('等待確認');
    expect(trigger.textContent).toContain('訊號未齊');
    expect(trigger.textContent).not.toContain('詳見');
    expect(trigger.textContent).not.toContain('下方');
  });

  it('renders KlineChartBlock when historyId is provided', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} historyId={58} />);
    expect(screen.getByTestId('kline-chart-block')).toBeInTheDocument();
  });

  it('does not restore old CandlestickChartBlock when historyId is provided', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} historyId={58} />);
    expect(screen.queryByTestId('candlestick-chart-block')).not.toBeInTheDocument();
    expect(screen.queryByTestId('candlestick-data-gap')).not.toBeInTheDocument();
  });

  it('does not render KlineChartBlock without historyId', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.queryByTestId('kline-chart-block')).not.toBeInTheDocument();
    expect(screen.queryByTestId('candlestick-chart-block')).not.toBeInTheDocument();
    expect(screen.queryByTestId('candlestick-data-gap')).not.toBeInTheDocument();
  });

  it('renders KlineChartBlock between MarketRiskGauge and MultiPeriodTrendBars', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} historyId={58} />);
    expect(screen.getByTestId('market-risk-gauge')).toBeInTheDocument();
    expect(screen.getByTestId('kline-chart-block')).toBeInTheDocument();
    expect(screen.getByTestId('multi-period-trend-bars')).toBeInTheDocument();
    expect(screen.getByTestId('financial-result-cards')).toBeInTheDocument();
    expect(screen.getByTestId('action-plan-cards')).toBeInTheDocument();
    const gaugeEl = screen.getByTestId('market-risk-gauge');
    const klineEl = screen.getByTestId('kline-chart-block');
    const trendEl = screen.getByTestId('multi-period-trend-bars');
    const financialEl = screen.getByTestId('financial-result-cards');
    const actionEl = screen.getByTestId('action-plan-cards');
    const gaugeToKline = gaugeEl.compareDocumentPosition(klineEl);
    const klineToTrend = klineEl.compareDocumentPosition(trendEl);
    const trendToFinancial = trendEl.compareDocumentPosition(financialEl);
    const financialToAction = financialEl.compareDocumentPosition(actionEl);
    // DOCUMENT_POSITION_FOLLOWING = 4
    expect(gaugeToKline & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(klineToTrend & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(trendToFinancial & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(financialToAction & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('does not render KlineChartBlock for unknown instrument type', () => {
    const report = {
      ...MSFT_REPORT,
      details: {
        rawResult: {
          ...MSFT_REPORT.details?.rawResult,
          instrumentType: 'unknown',
        },
      },
    };
    render(<ReportVisualSummary report={report} historyId={58} />);
    expect(screen.queryByTestId('kline-chart-block')).not.toBeInTheDocument();
  });
});

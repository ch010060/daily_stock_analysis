import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportVisualSummary } from '../ReportVisualSummary';
import { MSFT_REPORT, MINIMAL_REPORT } from './fixtures';

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

  // R1: CandlestickChartBlock stays disabled in production drawer pending chart-library/removal decision
  it('does not render CandlestickChartBlock when historyId is provided', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} historyId={58} />);
    expect(screen.queryByTestId('candlestick-chart-block')).not.toBeInTheDocument();
    expect(screen.queryByTestId('candlestick-data-gap')).not.toBeInTheDocument();
  });

  it('does not render CandlestickChartBlock without historyId', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.queryByTestId('candlestick-chart-block')).not.toBeInTheDocument();
    expect(screen.queryByTestId('candlestick-data-gap')).not.toBeInTheDocument();
  });

  it('renders MultiPeriodTrendBars after MarketRiskGauge when candlestick is disabled', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} historyId={58} />);
    expect(screen.getByTestId('market-risk-gauge')).toBeInTheDocument();
    expect(screen.getByTestId('multi-period-trend-bars')).toBeInTheDocument();
    const gaugeEl = screen.getByTestId('market-risk-gauge');
    const trendEl = screen.getByTestId('multi-period-trend-bars');
    const pos = gaugeEl.compareDocumentPosition(trendEl);
    // DOCUMENT_POSITION_FOLLOWING = 4
    expect(pos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

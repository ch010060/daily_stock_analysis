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

  it('shows data availability cards', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    expect(screen.getByTestId('data-availability-cards')).toBeInTheDocument();
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

  // F1.4: no hardcoded "0%" position value; shows operationAdvice and 操作建議 label
  it('shows 操作建議 label with vm.decision text, not hardcoded 0%', () => {
    render(<ReportVisualSummary report={MSFT_REPORT} />);
    const el = screen.getByTestId('report-visual-summary');
    expect(el.textContent).toContain('操作建議');
    expect(el.textContent).toContain('觀望');
    expect(el.textContent).not.toContain('空倉觀望');
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

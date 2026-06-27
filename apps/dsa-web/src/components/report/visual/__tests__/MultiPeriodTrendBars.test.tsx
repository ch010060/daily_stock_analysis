import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TrendPeriodVM } from '../reportVisualSummaryAdapter';
import { MultiPeriodTrendBars } from '../MultiPeriodTrendBars';

const FIVE_PERIODS: TrendPeriodVM[] = [
  { label: '1W', direction: 'down', changePct: -2.1, drawdownPct: -3.2, barWidthPct: 24.1 },
  { label: '1M', direction: 'down', changePct: -5.4, drawdownPct: -7.1, barWidthPct: 62.1 },
  { label: '3M', direction: 'up', changePct: 3.2, drawdownPct: -8.5, barWidthPct: 36.8 },
  { label: '6M', direction: 'up', changePct: 8.7, drawdownPct: -12.3, barWidthPct: 100 },
  { label: '1Y', direction: 'up', changePct: 22.4, drawdownPct: -15.8, barWidthPct: 87.6 },
];

describe('MultiPeriodTrendBars', () => {
  it('renders all 5 period labels', () => {
    render(<MultiPeriodTrendBars periods={FIVE_PERIODS} />);
    const el = screen.getByTestId('multi-period-trend-bars');
    expect(el).toBeInTheDocument();
    for (const p of FIVE_PERIODS) {
      expect(el.textContent).toContain(p.label);
    }
  });

  it('shows up arrows for uptrend periods and down arrows for downtrend periods', () => {
    render(<MultiPeriodTrendBars periods={FIVE_PERIODS} />);
    const el = screen.getByTestId('multi-period-trend-bars');
    // up=↑, down=↓
    expect(el.textContent).toContain('↑');
    expect(el.textContent).toContain('↓');
  });

  it('renders gap fallback when dataGap=true', () => {
    render(<MultiPeriodTrendBars periods={[]} dataGap />);
    expect(screen.getByTestId('multi-period-trend-bars').textContent).toMatch(/不足|暫不可用/);
  });

  it('renders gap fallback when periods is empty', () => {
    render(<MultiPeriodTrendBars periods={[]} />);
    expect(screen.getByTestId('multi-period-trend-bars').textContent).toMatch(/不足|暫不可用/);
  });

  it('handles insufficient direction', () => {
    const insuf: TrendPeriodVM[] = [
      { label: '5Y', direction: 'insufficient', changePct: null, drawdownPct: null, barWidthPct: 0 },
    ];
    render(<MultiPeriodTrendBars periods={insuf} />);
    expect(screen.getByTestId('multi-period-trend-bars').textContent).toContain('—');
  });

  // F1.3: neutral status renders → not ↓ even when changePct is negative
  it('neutral direction renders → arrow', () => {
    const neutral: TrendPeriodVM[] = [
      { label: '1季', direction: 'neutral', changePct: -4.48, drawdownPct: -6.0, barWidthPct: 50 },
    ];
    render(<MultiPeriodTrendBars periods={neutral} />);
    const el = screen.getByTestId('multi-period-trend-bars');
    expect(el.textContent).toContain('→');
    expect(el.textContent).not.toContain('↓');
  });
});

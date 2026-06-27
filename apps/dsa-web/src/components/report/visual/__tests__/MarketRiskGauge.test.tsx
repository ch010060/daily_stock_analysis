import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarketRiskGauge } from '../MarketRiskGauge';

describe('MarketRiskGauge', () => {
  it('renders SVG gauge for VIX 18.89 calm', () => {
    render(
      <MarketRiskGauge vixLevel={18.89} vixStatus="calm" spxChangePct={-0.45} />
    );
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge).toBeInTheDocument();
    expect(gauge.querySelector('svg')).toBeTruthy();
    expect(gauge.textContent).toContain('18.89');
    expect(gauge.textContent).toContain('calm');
  });

  it('renders data gap fallback when dataGap=true', () => {
    render(<MarketRiskGauge vixLevel={null} vixStatus={null} spxChangePct={null} dataGap />);
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.querySelector('svg')).toBeFalsy();
    expect(gauge.textContent).toMatch(/暫不可用|缺口|unavailable/i);
  });

  it('renders data gap fallback when vixLevel is null', () => {
    render(<MarketRiskGauge vixLevel={null} vixStatus="calm" spxChangePct={null} />);
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.querySelector('svg')).toBeFalsy();
  });

  it('renders without crashing for extreme VIX values (clamped to max)', () => {
    // VIX=80 > 45 max; pointerX should clamp to 600 per Math.min guard
    expect(() =>
      render(<MarketRiskGauge vixLevel={80} vixStatus="extreme fear" spxChangePct={-5} />)
    ).not.toThrow();
    expect(screen.getByTestId('market-risk-gauge')).toBeInTheDocument();
  });
});

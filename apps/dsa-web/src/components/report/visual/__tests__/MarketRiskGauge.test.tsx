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

  it('renders TW sentiment score without labeling it as VIX', () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="sentiment"
        sentimentScore={42}
        sentimentLabel="中性"
      />
    );
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('系統評分');
    expect(gauge.textContent).toContain('42');
    expect(gauge.textContent).toContain('中性');
    expect(gauge.textContent).not.toContain('VIX');
    expect(gauge.textContent).not.toContain(['恐慌', '貪婪', '分數'].join(''));
    expect(screen.getByText('系統評分')).toHaveAttribute('title', expect.stringContaining('非 VIX'));
    expect(screen.getByText('系統評分')).toHaveAttribute('title', expect.stringContaining('沒有固定公開公式'));
  });

  it('renders TW sentiment data gap without a VIX unavailable label', () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="sentiment"
        sentimentScore={null}
        dataGap
      />
    );
    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('系統評分資料不足');
    expect(gauge.textContent).not.toContain('VIX 資料不足');
  });

  it('renders without crashing for extreme VIX values (clamped to max)', () => {
    // VIX=80 > 45 max; pointerX should clamp to 600 per Math.min guard
    expect(() =>
      render(<MarketRiskGauge vixLevel={80} vixStatus="extreme fear" spxChangePct={-5} />)
    ).not.toThrow();
    expect(screen.getByTestId('market-risk-gauge')).toBeInTheDocument();
  });
});

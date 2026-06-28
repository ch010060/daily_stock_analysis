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
    expect(gauge.textContent).toContain('恐慌指數 VIX');
    expect(gauge.textContent).not.toContain('市場風險 ·');
    expect(screen.getByTestId('market-fear-value').className).toContain('text-success');
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

  it('renders one dual-pointer card when market index and system score exist', () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="market_fear"
        sentimentScore={44}
        sentimentLabel="中性"
        marketFearIndex={{
          kind: 'vix',
          title: '恐慌指數 VIX',
          value: 18.41,
          asOf: '2026-06-26',
          source: 'yfinance_yahoo_quote',
          dataGapReason: null,
          bucket: 'green',
          pointerPosition: 23,
        }}
      />
    );

    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('恐慌指數 VIX');
    expect(gauge.textContent).toContain('VIX 18.41');
    expect(gauge.textContent).toContain('日期：2026-06-26');
    expect(gauge.textContent).toContain('系統評分');
    expect(screen.getByTestId('market-fear-value').className).toContain('text-success');
    expect(gauge.textContent).toContain('28.7');
    expect(gauge.textContent).toContain('33.5');
    expect(screen.getByTestId('market-fear-meter')).toBeInTheDocument();
    expect(screen.getByTestId('market-fear-pointer').querySelector('polygon')).toBeTruthy();
    expect(screen.getByTestId('system-score-pointer').querySelector('circle')).toBeTruthy();
  });

  it('renders TW VIXTWN title/date and does not fake missing values', () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="market_fear"
        sentimentScore={42}
        sentimentLabel="中性"
        marketFearIndex={{
          kind: 'vixtwn',
          title: '台灣恐慌指數 VIXTWN',
          value: 44.27,
          asOf: '2026-06-26',
          source: 'taifex',
          dataGapReason: null,
          bucket: 'red',
          pointerPosition: 89,
        }}
      />
    );

    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('台灣恐慌指數 VIXTWN');
    expect(gauge.textContent).toContain('VIXTWN 44.27');
    expect(gauge.textContent).toContain('日期：2026-06-26');
    expect(gauge.textContent).toContain('系統評分');
    expect(screen.getByTestId('market-fear-value').className).toContain('text-danger');
    expect(gauge.textContent).toContain('30');
    expect(gauge.textContent).toContain('40');
    expect(gauge.textContent).not.toContain('市場情緒 ·');
  });

  it('keeps system score when the market index snapshot is a gap', () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="market_fear"
        sentimentScore={42}
        sentimentLabel="中性"
        marketFearIndex={{
          kind: 'vixtwn',
          title: '台灣恐慌指數 VIXTWN',
          value: null,
          asOf: null,
          source: 'taifex',
          dataGapReason: 'taifex_vixtwn_fetch_failed',
          bucket: 'unknown',
          pointerPosition: null,
        }}
      />
    );

    const gauge = screen.getByTestId('market-risk-gauge');
    expect(gauge.textContent).toContain('台灣恐慌指數 VIXTWN');
    expect(gauge.textContent).toContain('指數資料暫缺');
    expect(gauge.textContent).toContain('系統評分');
    expect(screen.queryByTestId('market-fear-pointer')).not.toBeInTheDocument();
    expect(screen.getByTestId('system-score-pointer')).toBeInTheDocument();
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

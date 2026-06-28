import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
    expect(gauge.textContent).toContain('平穩');
    expect(gauge.textContent).toContain('VIX');
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
    expect(screen.getByLabelText('系統評分說明')).toBeInTheDocument();
  });

  it('renders one compact market index card when market index and system score exist', () => {
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
    expect(gauge.textContent).toContain('VIX');
    expect(screen.getByTestId('market-fear-value')).toHaveTextContent('18.41');
    expect(gauge.textContent).not.toContain('VIX 18.41');
    expect(gauge.textContent).toContain('日期：2026-06-26');
    expect(gauge.textContent).toContain('系統評分');
    expect(gauge.textContent).toContain('平穩');
    expect(gauge.textContent).toContain('中性');
    expect(screen.getByTestId('market-fear-value').className).toContain('text-success');
    expect(gauge.textContent).toContain('28.7');
    expect(gauge.textContent).toContain('33.5');
    expect(gauge.textContent).toContain('恐慌指數：數值越高代表市場恐慌程度越高');
    expect(gauge.textContent).toContain('系統評分：分數越高代表本標的評估越偏多');
    expect(gauge.textContent).not.toContain('原始標籤');
    expect(screen.getByTestId('market-fear-meter')).toBeInTheDocument();
    expect(screen.queryByTestId('market-fear-marker-row')).not.toBeInTheDocument();
    expect(screen.getByTestId('market-fear-pointer').querySelector('polygon')).toBeTruthy();
    expect(screen.queryByTestId('system-score-pointer')).not.toBeInTheDocument();
  });

  it('renders dashboard as a semi-arc meter without duplicated bottom scale', () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="market_fear"
        layout="dashboard"
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
        systemScore={{
          label: '系統評分',
          value: 42,
          sentimentLabel: '中性',
          explanation: '非市場官方指數、非 VIX、非 VIXTWN，目前沒有固定公開公式。',
        }}
      />,
    );

    expect(screen.getByTestId('market-fear-meter').querySelectorAll('path')).toHaveLength(4);
    expect(screen.queryByTestId('market-fear-scale')).not.toBeInTheDocument();
    expect(screen.getByTestId('market-risk-gauge').textContent).toContain('系統評分：分數越高代表本標的評估越偏多');
    expect(screen.getByTestId('market-risk-gauge').textContent).not.toContain('原始標籤');
    expect(screen.queryByTestId('market-fear-marker-row')).not.toBeInTheDocument();
    expect(screen.queryByTestId('system-score-pointer')).not.toBeInTheDocument();
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
    expect(gauge.textContent).toContain('VIXTWN');
    expect(within(gauge).getByText('VIXTWN')).not.toHaveClass('truncate');
    expect(screen.getByTestId('market-fear-value')).toHaveTextContent('44.27');
    expect(gauge.textContent).not.toContain('VIXTWN 44.27');
    expect(gauge.textContent).toContain('日期：2026-06-26');
    expect(within(gauge).getByText('日期：')).toBeInTheDocument();
    expect(within(gauge).getByText('2026-06-26')).toBeInTheDocument();
    expect(gauge.textContent).toContain('系統評分');
    expect(gauge.textContent).toContain('恐慌');
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
    expect(gauge.textContent).toContain('VIXTWN');
    expect(gauge.textContent).toContain('指數資料暫缺');
    expect(gauge.textContent).toContain('系統評分');
    expect(screen.queryByTestId('market-fear-pointer')).not.toBeInTheDocument();
    expect(screen.queryByTestId('system-score-pointer')).not.toBeInTheDocument();
    expect(screen.queryByTestId('market-fear-marker-row')).not.toBeInTheDocument();
  });

  it('opens one info tooltip at a time and includes score ranges before provenance', async () => {
    render(
      <MarketRiskGauge
        vixLevel={null}
        vixStatus={null}
        spxChangePct={null}
        marketRiskKind="market_fear"
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
        systemScore={{
          label: '系統評分',
          value: 42,
          sentimentLabel: '中性',
          explanation: '本系統依分析模型對行情、技術、新聞與報告上下文的綜合判斷產生此分數；非市場官方指數、非 VIX、非 VIXTWN。目前沒有固定公開公式。',
        }}
      />,
    );

    fireEvent.click(screen.getByLabelText('VIXTWN 說明'));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('VIXTWN 台灣市場恐慌指標');

    fireEvent.click(screen.getByLabelText('系統評分說明'));
    await waitFor(() => {
      expect(screen.getAllByRole('tooltip')).toHaveLength(1);
    });
    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('0–24 明顯偏空');
    expect(tooltip).toHaveTextContent('75–100 明顯偏多');
    expect(tooltip).toHaveTextContent('非市場官方指數');
    expect(tooltip).toHaveTextContent('沒有固定公開公式');
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

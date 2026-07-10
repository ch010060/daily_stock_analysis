import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ValuationRiverChart } from '../ValuationRiverChart';

const validSnapshot = () => ({
  enabled: true,
  market: 'tw',
  symbol: '2330',
  currency: 'TWD',
  bandMultiples: [14, 18, 22, 26, 30, 34, 38],
  neutralMultiple: 26,
  range: { startDate: '2026-01-01', endDate: '2026-01-20', tradingDays: 20 },
  points: Array.from({ length: 20 }, (_, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, '0')}`,
    close: 1000 + i * 5,
    per: 20 + i * 0.2,
    impliedEps: 50,
    bands: { per14: 700, per18: 900, per22: 1100, per26: 1300, per30: 1500, per34: 1700, per38: 1900 },
  })),
  current: { close: 1100, per: 22, impliedEps: 50, zone: 'undervalued' },
  quality: {
    status: 'ok' as string,
    warnings: [] as string[],
    dataGapFields: [] as string[],
    methodologyNote: '倍數帶為固定視覺參考基準，非估值結論、目標價或買賣建議。',
  },
});

describe('ValuationRiverChart', () => {
  it('renders the chart for a valid enabled TW snapshot', () => {
    render(<ValuationRiverChart rawSnapshot={validSnapshot()} />);
    expect(screen.getByTestId('valuation-river-chart')).toBeInTheDocument();
    expect(screen.getByTestId('valuation-river-zone-badge')).toHaveTextContent('偏低估');
    expect(screen.getByText(/倍數帶為固定視覺參考基準/)).toBeInTheDocument();
  });

  it('renders the unavailable fallback card for enabled:false payloads', () => {
    render(
      <ValuationRiverChart
        rawSnapshot={{ enabled: false, market: 'us', quality: { warnings: ['US 股票歷史估值河流圖資料尚未支援'] } }}
      />
    );
    expect(screen.getByTestId('valuation-river-unavailable')).toBeInTheDocument();
    expect(screen.getByText('US 股票歷史估值河流圖資料尚未支援')).toBeInTheDocument();
    expect(screen.queryByTestId('valuation-river-chart')).toBeNull();
  });

  it('renders the unavailable fallback card for missing/malformed payloads (never crashes)', () => {
    const { container: c1 } = render(<ValuationRiverChart rawSnapshot={undefined} />);
    expect(c1.querySelector('[data-testid="valuation-river-unavailable"]')).not.toBeNull();

    const { container: c2 } = render(<ValuationRiverChart rawSnapshot={{ garbage: true }} />);
    expect(c2.querySelector('[data-testid="valuation-river-unavailable"]')).not.toBeNull();
  });

  it('does not render a fake river for ETF/index instrument types', () => {
    render(
      <ValuationRiverChart
        rawSnapshot={{ enabled: false, market: 'tw', quality: { warnings: ['僅支援股票標的的估值河流圖（instrument_type=etf）'] } }}
      />
    );
    expect(screen.queryByTestId('valuation-river-chart')).toBeNull();
    expect(screen.getByText(/僅支援股票標的的估值河流圖/)).toBeInTheDocument();
  });

  it('never uses dangerouslySetInnerHTML-style raw markup for the methodology note', () => {
    const payload = validSnapshot();
    payload.quality.methodologyNote = '<img src=x onerror=alert(1)>note';
    const { container } = render(<ValuationRiverChart rawSnapshot={payload} />);
    expect(container.querySelector('img')).toBeNull();
  });

  it('shows a partial-data warning banner when quality.status is partial', () => {
    const payload = validSnapshot();
    payload.quality.status = 'partial';
    payload.quality.warnings = ['僅 10 個交易日聯集資料，低於建議下限 20 天'];
    render(<ValuationRiverChart rawSnapshot={payload} />);
    expect(screen.getByText(/僅 10 個交易日聯集資料/)).toBeInTheDocument();
  });

  it('labels TW as 反推 EPS/反推 BVPS and shows actual/forward eps stats', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.method = 'per_implied_eps_river';
    payload.epsKind = 'implied';
    (payload.current as Record<string, unknown>).pbr = 6.0;
    (payload.current as Record<string, unknown>).impliedBvps = 176.01;
    (payload.current as Record<string, unknown>).epsActual = { value: 22.08, period: 'quarterly', source: 'finmind' };
    (payload.current as Record<string, unknown>).epsForward = null;

    render(<ValuationRiverChart rawSnapshot={payload} />);
    const stats = screen.getByTestId('valuation-river-eps-stats');
    expect(stats).toHaveTextContent('反推 EPS');
    expect(stats).toHaveTextContent('反推 BVPS');
    expect(stats).toHaveTextContent('實際 EPS');
    expect(stats).toHaveTextContent('22.08');
    expect(stats).toHaveTextContent('預估 EPS');
  });

  it('labels US as 財報年度 EPS/實際 BVPS, never presenting implied EPS as actual', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.market = 'us';
    payload.method = 'us_reported_eps_annual_river';
    payload.epsKind = 'reported';
    (payload.current as Record<string, unknown>).epsActual = { value: 8.35, period: 'ttm', source: 'yfinance' };
    (payload.current as Record<string, unknown>).epsForward = { value: 9.61, period: 'point_in_time', source: 'yfinance' };

    render(<ValuationRiverChart rawSnapshot={payload} />);
    expect(screen.getByText(/財報年度實際 EPS 建構台階狀倍數視覺參考帶/)).toBeInTheDocument();
    const stats = screen.getByTestId('valuation-river-eps-stats');
    expect(stats).toHaveTextContent('財報年度 EPS');
    expect(stats).toHaveTextContent('實際 BVPS');
    expect(stats).toHaveTextContent('8.35');
    expect(stats).toHaveTextContent('9.61');
  });

  it('renders a clean "—" placeholder when actual/forward EPS is unavailable, never crashing', () => {
    const payload = validSnapshot();
    render(<ValuationRiverChart rawSnapshot={payload} />);
    const stats = screen.getByTestId('valuation-river-eps-stats');
    // validSnapshot() carries no epsActual/epsForward — must degrade to '—', not throw
    expect(stats.textContent).toContain('—');
  });

  it('shows real actual/forward EPS in the unavailable fallback card when the river itself could not be built', () => {
    render(
      <ValuationRiverChart
        rawSnapshot={{
          enabled: false,
          market: 'us',
          quality: { warnings: ['yfinance 年度財報 EPS 資料點過少'] },
          current: {
            epsActual: { value: 8.35, period: 'ttm', source: 'yfinance' },
            epsForward: { value: 9.61, period: 'point_in_time', source: 'yfinance' },
          },
        }}
      />
    );
    const card = screen.getByTestId('valuation-river-unavailable');
    expect(card).toHaveTextContent('實際 EPS');
    expect(card).toHaveTextContent('8.35');
    expect(card).toHaveTextContent('預估 EPS');
    expect(card).toHaveTextContent('9.61');
  });

});

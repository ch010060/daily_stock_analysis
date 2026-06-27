import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../../api/history';
import type { KlineResponse } from '../../../../types/analysis';
import { KlineChartBlock } from '../KlineChartBlock';

let crosshairHandler: ((param: { time?: string }) => void) | null = null;
const setData = vi.fn();
const createPriceLine = vi.fn();
const remove = vi.fn();
const addSeries = vi.fn(() => ({
  setData,
  createPriceLine,
  priceScale: () => ({ applyOptions: vi.fn() }),
}));

function lineSeriesCalls() {
  return (addSeries.mock.calls as unknown[][]).filter(([kind]) => kind === 'LineSeries');
}

vi.mock('../../../../api/history', () => ({
  historyApi: { getKline: vi.fn() },
}));

vi.mock('lightweight-charts', () => ({
  CandlestickSeries: 'CandlestickSeries',
  HistogramSeries: 'HistogramSeries',
  LineSeries: 'LineSeries',
  CrosshairMode: { Normal: 0 },
  LineStyle: { Dashed: 2 },
  createChart: vi.fn(() => ({
    addSeries,
    applyOptions: vi.fn(),
    remove,
    subscribeCrosshairMove: vi.fn((handler) => {
      crosshairHandler = handler;
    }),
    timeScale: () => ({ fitContent: vi.fn() }),
  })),
}));

const RESPONSE: KlineResponse = {
  historyId: 65,
  symbol: 'MSFT',
  market: 'us',
  instrumentType: 'stock',
  range: '3m',
  source: 'YfinanceFetcher',
  sourceType: 'db_cache',
  asOf: '2026-06-26',
  currentPrice: 372.97,
  supportLevel: 355.43,
  resistanceLevel: 400.12,
  dataGapReason: null,
  rows: [
    {
      date: '2026-06-25',
      open: 350,
      high: 360,
      low: 345,
      close: 355,
      volume: 10,
      ma20: null,
      ma60: null,
      ma120: null,
      ma252: null,
    },
    {
      date: '2026-06-26',
      open: 357.15,
      high: 376.61,
      low: 355.43,
      close: 372.97,
      volume: 36_360_000,
      ma20: 400.12,
      ma60: 410.55,
      ma120: 421,
      ma252: null,
    },
  ],
};

describe('KlineChartBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    crosshairHandler = null;
    vi.mocked(historyApi.getKline).mockResolvedValue(RESPONSE);
  });

  it('renders data-gap state for empty rows', async () => {
    vi.mocked(historyApi.getKline).mockResolvedValue({ ...RESPONSE, rows: [], dataGapReason: 'no_cached_ohlc' });
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    expect(await screen.findByTestId('kline-data-gap')).toHaveTextContent('no_cached_ohlc');
  });

  it('renders chart container and fixed hover data strip with latest candle by default', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    const strip = await screen.findByTestId('kline-hover-strip');
    expect(strip).toHaveTextContent('日期 2026-06-26');
    expect(strip).toHaveTextContent('開 357.15');
    expect(strip).toHaveTextContent('高 376.61');
    expect(strip).toHaveTextContent('低 355.43');
    expect(strip).toHaveTextContent('收 372.97');
    expect(strip).toHaveTextContent('MA252 —');
    expect(screen.getByTestId('kline-chart-canvas-host')).toBeInTheDocument();
  });

  it('uses 3M as the default range and does not refetch in a loop', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByTestId('kline-chart-block');
    await waitFor(() => expect(historyApi.getKline).toHaveBeenCalledTimes(1));
    expect(historyApi.getKline).toHaveBeenCalledWith(65, '3m');
  });

  it('range chips request the selected range', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByTestId('kline-chart-block');
    fireEvent.click(screen.getByRole('button', { name: '1W' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1w'));
  });

  it('1W only creates and shows MA20', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByTestId('kline-chart-block');
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(3));
    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '1W' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1w'));
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(1));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA20');
    expect(screen.getByTestId('kline-ma-legend')).not.toHaveTextContent('MA60');
    expect(screen.getByTestId('kline-ma-legend')).not.toHaveTextContent('MA120');
    expect(screen.getByTestId('kline-ma-legend')).not.toHaveTextContent('MA252');
  });

  it('shows range-specific MA legends and does not create hidden MA series', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByTestId('kline-chart-block');
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(3));

    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '1M' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1m'));
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(2));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA20');
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA60');
    expect(screen.getByTestId('kline-ma-legend')).not.toHaveTextContent('MA120');

    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '3M' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '3m'));
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(3));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA120');
    expect(screen.getByTestId('kline-ma-legend')).not.toHaveTextContent('MA252');

    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '1Y' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1y'));
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(4));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA252');
  });

  it('simulated crosshair move updates OHLC values', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByText(/日期 2026-06-26/);
    act(() => crosshairHandler?.({ time: '2026-06-25' }));
    expect(screen.getByTestId('kline-hover-strip')).toHaveTextContent('日期 2026-06-25');
    expect(screen.getByTestId('kline-hover-strip')).toHaveTextContent('收 355.00');
  });

  it('renders current/support/resistance level labels', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    expect(await screen.findByTestId('kline-current-price-label')).toHaveTextContent('現價 372.97');
    expect(screen.getByTestId('kline-support-label')).toHaveTextContent('支撐 355.43');
    expect(screen.getByTestId('kline-resistance-label')).toHaveTextContent('壓力 400.12');
  });

  it('renders daily-candle non-intraday note', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    expect(await screen.findByTestId('kline-source-note')).toHaveTextContent('日 K｜yfinance cache｜1W 為短期日線視窗，非盤中線');
  });

  it('StrictMode does not leave a permanent loading skeleton', async () => {
    render(
      <StrictMode>
        <KlineChartBlock historyId={65} instrumentType="stock" />
      </StrictMode>
    );
    expect(await screen.findByTestId('kline-hover-strip')).toHaveTextContent('日期 2026-06-26');
  });

  it('suppresses unsupported instrument types without fetching', () => {
    render(<KlineChartBlock historyId={65} instrumentType="unknown" />);
    expect(screen.queryByTestId('kline-chart-block')).not.toBeInTheDocument();
    expect(historyApi.getKline).not.toHaveBeenCalled();
  });
});

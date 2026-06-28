import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../../api/history';
import { SYSTEM_CONFIG_CHANGED_EVENT } from '../../../../api/alphasift';
import { systemConfigApi } from '../../../../api/systemConfig';
import type { KlineRange, KlineResponse } from '../../../../types/analysis';
import { KlineChartBlock } from '../KlineChartBlock';

let crosshairHandler: ((param: { time?: string | number }) => void) | null = null;
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

function candleSeriesOptions() {
  return (addSeries.mock.calls as unknown[][]).filter(([kind]) => kind === 'CandlestickSeries').at(-1)?.[1] as Record<string, unknown>;
}

function latestVolumeData() {
  return (setData.mock.calls as unknown[][])
    .map(([data]) => data)
    .find((data) => Array.isArray(data) && data[0] && typeof data[0] === 'object' && 'value' in data[0]) as Array<Record<string, unknown>> | undefined;
}

vi.mock('../../../../api/history', () => ({
  historyApi: { getKline: vi.fn() },
}));

vi.mock('../../../../api/systemConfig', () => ({
  systemConfigApi: { getConfig: vi.fn() },
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

function dailyResponse(range: KlineRange = '3m'): KlineResponse {
  return {
    historyId: 65,
    symbol: 'MSFT',
    market: 'us',
    instrumentType: 'stock',
    range,
    granularity: 'daily',
    interval: '1d',
    source: 'analysis_kline_snapshot',
    sourceType: 'db_cache',
    sourceChain: ['analysis_kline_snapshot', 'stock_daily'],
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
    candles: [],
  };
}

function intradayResponse(range: '1d' | '5d' = '1d'): KlineResponse {
  return {
    ...dailyResponse(range),
    range,
    granularity: 'intraday',
    interval: range === '1d' ? '5m' : '15m',
    source: 'yfinance',
    rows: [],
    candles: [
      {
        timestamp: '2026-06-26T09:30:00-04:00',
        open: 357.15,
        high: 358.42,
        low: 356.9,
        close: 357.8,
        volume: 123_456,
      },
      {
        timestamp: '2026-06-26T09:35:00-04:00',
        open: 357.8,
        high: 359,
        low: 357.2,
        close: 358.8,
        volume: 234_567,
      },
    ],
  };
}

function config(value = 'green_up') {
  return {
    configVersion: 'v1',
    maskToken: '******',
    items: [{ key: 'MARKET_REVIEW_COLOR_SCHEME', value, rawValueExists: true, isMasked: false }],
  };
}

describe('KlineChartBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    crosshairHandler = null;
    vi.mocked(systemConfigApi.getConfig).mockResolvedValue(config());
    vi.mocked(historyApi.getKline).mockImplementation(async (_id, range = '3m') => {
      if (range === '1d' || range === '5d') return intradayResponse(range);
      return dailyResponse(range);
    });
  });

  it('renders tabs exactly 1D / 5D / 1M / 3M / 1Y and hides 1W', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    const tabs = await screen.findByTestId('kline-range-tabs');
    expect(tabs.textContent).toBe('1D5D1M3M1Y');
    expect(screen.queryByRole('button', { name: '1W' })).not.toBeInTheDocument();
  });

  it('uses 3M as the default range and fetches only 3M initially', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByTestId('kline-chart-block');
    await waitFor(() => expect(historyApi.getKline).toHaveBeenCalledTimes(1));
    expect(historyApi.getKline).toHaveBeenCalledWith(65, '3m');
  });

  it('fetches 1D and 5D on demand and does not refetch cached ranges', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByText(/日期 2026-06-26/);

    fireEvent.click(screen.getByRole('button', { name: '1D' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1d'));
    expect(await screen.findByText(/日期時間 2026-06-26 09:35/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '5D' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '5d'));

    fireEvent.click(screen.getByRole('button', { name: '3M' }));
    await screen.findByText(/日期 2026-06-26/);
    expect(historyApi.getKline).toHaveBeenCalledTimes(3);
  });

  it('ignores stale selected-tab responses during fast switching', async () => {
    let resolve1d: ((value: KlineResponse) => void) | null = null;
    let resolve5d: ((value: KlineResponse) => void) | null = null;
    vi.mocked(historyApi.getKline).mockImplementation((_id, nextRange = '3m') => {
      if (nextRange === '1d') return new Promise((resolve) => { resolve1d = resolve; });
      if (nextRange === '5d') return new Promise((resolve) => { resolve5d = resolve; });
      return Promise.resolve(dailyResponse(nextRange));
    });

    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByText(/日期 2026-06-26/);
    fireEvent.click(screen.getByRole('button', { name: '1D' }));
    fireEvent.click(screen.getByRole('button', { name: '5D' }));

    act(() => resolve5d?.(intradayResponse('5d')));
    expect(await screen.findByText(/interval 15m/)).toBeInTheDocument();
    act(() => resolve1d?.(intradayResponse('1d')));
    expect(screen.getByTestId('kline-hover-strip')).toHaveTextContent('interval 15m');
  });

  it('intraday ranges render no MA lines and daily ranges keep MA policy', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(3));

    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '1D' }));
    await screen.findByText(/日期時間/);
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(0));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('');

    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '1M' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1m'));
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(2));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA20');
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA60');
    expect(screen.getByTestId('kline-ma-legend')).not.toHaveTextContent('MA120');
  });

  it('daily 1Y renders MA252', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByTestId('kline-chart-block');
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(3));
    addSeries.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '1Y' }));
    await waitFor(() => expect(historyApi.getKline).toHaveBeenLastCalledWith(65, '1y'));
    await waitFor(() => expect(lineSeriesCalls()).toHaveLength(4));
    expect(screen.getByTestId('kline-ma-legend')).toHaveTextContent('MA252');
  });

  it('intraday data-gap renders only for selected tab and daily tabs remain usable', async () => {
    vi.mocked(historyApi.getKline).mockImplementation(async (_id, nextRange = '3m') => {
      if (nextRange === '1d') return { ...intradayResponse('1d'), candles: [], dataGapReason: 'report_kline_snapshot_missing' };
      return dailyResponse(nextRange);
    });
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByText(/日期 2026-06-26/);
    fireEvent.click(screen.getByRole('button', { name: '1D' }));
    expect(await screen.findByTestId('kline-data-gap')).toHaveTextContent('此報告未保存 1D 盤中 K snapshot');
    fireEvent.click(screen.getByRole('button', { name: '1M' }));
    expect(await screen.findByText(/日期 2026-06-26/)).toBeInTheDocument();
  });

  it('simulated crosshair move updates daily and intraday strip values', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await screen.findByText(/日期 2026-06-26/);
    act(() => crosshairHandler?.({ time: '2026-06-25' }));
    expect(screen.getByTestId('kline-hover-strip')).toHaveTextContent('日期 2026-06-25');

    fireEvent.click(screen.getByRole('button', { name: '1D' }));
    await screen.findByText(/日期時間 2026-06-26 09:35/);
    const firstIntradayTime = Math.floor(Date.parse('2026-06-26T09:30:00-04:00') / 1000);
    act(() => crosshairHandler?.({ time: firstIntradayTime }));
    expect(screen.getByTestId('kline-hover-strip')).toHaveTextContent('日期時間 2026-06-26 09:30');
  });

  it('green_up maps up candles and volume to green and down to red', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await waitFor(() => expect(candleSeriesOptions()).toMatchObject({ upColor: '#16a34a', downColor: '#dc2626' }));
    expect(latestVolumeData()?.[0].color).toBe('rgba(22, 163, 74, 0.25)');
  });

  it('red_up maps up candles and volume to red and down to green', async () => {
    vi.mocked(systemConfigApi.getConfig).mockResolvedValue(config('red_up'));
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await waitFor(() => expect(candleSeriesOptions()).toMatchObject({ upColor: '#dc2626', downColor: '#16a34a' }));
    expect(latestVolumeData()?.[0].color).toBe('rgba(220, 38, 38, 0.25)');
  });

  it('color scheme change updates chart options without refetching /kline', async () => {
    vi.mocked(systemConfigApi.getConfig)
      .mockResolvedValueOnce(config('green_up'))
      .mockResolvedValueOnce(config('red_up'));
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    await waitFor(() => expect(candleSeriesOptions()).toMatchObject({ upColor: '#16a34a' }));
    window.dispatchEvent(new Event(SYSTEM_CONFIG_CHANGED_EVENT));
    await waitFor(() => expect(candleSeriesOptions()).toMatchObject({ upColor: '#dc2626' }));
    expect(historyApi.getKline).toHaveBeenCalledTimes(1);
  });

  it('renders current/support/resistance level labels', async () => {
    render(<KlineChartBlock historyId={65} instrumentType="stock" />);
    expect(await screen.findByTestId('kline-current-price-label')).toHaveTextContent('現價 372.97');
    expect(screen.getByTestId('kline-support-label')).toHaveTextContent('支撐 355.43');
    expect(screen.getByTestId('kline-resistance-label')).toHaveTextContent('壓力 400.12');
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

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type Time,
} from 'lightweight-charts';
import { historyApi } from '../../../api/history';
import type { KlineRange, KlineResponse } from '../../../types/analysis';
import {
  adaptKlineResponse,
  formatKlinePrice,
  formatKlineStrip,
  type KlineChartVM,
  type KlinePointVM,
} from './klineChartAdapter';

type MaKey = 'ma20' | 'ma60' | 'ma120' | 'ma252';

const RANGES: Array<{ value: KlineRange; label: string }> = [
  { value: '1w', label: '1W' },
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: '1y', label: '1Y' },
];

const MA_CONFIG: Record<MaKey, { label: string; color: string; className: string }> = {
  ma20: { label: 'MA20', color: '#2563eb', className: 'text-blue-600' },
  ma60: { label: 'MA60', color: '#f59e0b', className: 'text-amber-600' },
  ma120: { label: 'MA120', color: '#7c3aed', className: 'text-violet-600' },
  ma252: { label: 'MA252', color: '#64748b', className: 'text-slate-500' },
};

const RANGE_MA_KEYS: Record<KlineRange, MaKey[]> = {
  '1w': ['ma20'],
  '1m': ['ma20', 'ma60'],
  '3m': ['ma20', 'ma60', 'ma120'],
  '1y': ['ma20', 'ma60', 'ma120', 'ma252'],
};

interface KlineChartBlockProps {
  historyId: number;
  instrumentType: string;
}

function isSupportedInstrument(type: string): boolean {
  return ['stock', 'etf', 'index'].includes(type);
}

function toChartTime(time: string): Time {
  return time as Time;
}

function sourceNote(vm: KlineChartVM | null): string {
  const source = (vm?.source || '').toLowerCase();
  let provider = '等待資料';
  if (source.includes('finmind') || vm?.market === 'tw') provider = 'FinMind cache';
  else if (source.includes('yfinance') || vm?.market === 'us') provider = 'yfinance cache';
  else if (vm?.source) provider = `${vm.source} cache`;
  return `日 K｜${provider}｜1W 為短期日線視窗，非盤中線`;
}

export function KlineChartBlock({ historyId, instrumentType }: KlineChartBlockProps) {
  const [range, setRange] = useState<KlineRange>('3m');
  const [response, setResponse] = useState<KlineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hoverPoint, setHoverPoint] = useState<KlinePointVM | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!isSupportedInstrument(instrumentType)) return;
    const controller = new AbortController();
    historyApi.getKline(historyId, range)
      .then((data) => {
        if (!controller.signal.aborted) {
          setResponse(data);
          setError(null);
          setHoverPoint(null);
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'kline_fetch_failed');
          setResponse(null);
        }
      });
    return () => controller.abort();
  }, [historyId, instrumentType, range]);

  const vm = useMemo(() => (response ? adaptKlineResponse(response) : null), [response]);
  const latestPoint = vm?.points[vm.points.length - 1] ?? null;
  const activePoint = hoverPoint ?? latestPoint;
  const currentPrice = vm?.currentPrice ?? latestPoint?.close ?? null;
  const visibleMaKeys = RANGE_MA_KEYS[range];

  useEffect(() => {
    if (!vm || vm.points.length === 0 || !containerRef.current) return;

    chartRef.current?.remove();
    const chart = createChart(containerRef.current, {
      height: 260,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#1f2937',
      },
      grid: {
        vertLines: { color: '#eef2f7' },
        horzLines: { color: '#eef2f7' },
      },
      rightPriceScale: { borderColor: '#d8dee9' },
      timeScale: { borderColor: '#d8dee9', timeVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
      width: Math.max(containerRef.current.clientWidth, 320),
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#16a34a',
      downColor: '#dc2626',
      borderUpColor: '#16a34a',
      borderDownColor: '#dc2626',
      wickUpColor: '#15803d',
      wickDownColor: '#b91c1c',
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      color: '#94a3b8',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    const candleData = vm.points.map((point) => ({
      time: toChartTime(point.time),
      open: point.open,
      high: point.high,
      low: point.low,
      close: point.close,
    }));
    candleSeries.setData(candleData);
    volumeSeries.setData(vm.points.map((point) => ({
      time: toChartTime(point.time),
      value: point.volume ?? 0,
      color: point.close >= point.open ? 'rgba(22, 163, 74, 0.25)' : 'rgba(220, 38, 38, 0.25)',
    })));

    for (const key of visibleMaKeys) {
      const series = chart.addSeries(LineSeries, {
        color: MA_CONFIG[key].color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(vm.points
        .filter((point) => point[key] !== null)
        .map((point) => ({ time: toChartTime(point.time), value: point[key] as number })));
    }

    const addLevel = (price: number | null, title: string, color: string) => {
      if (price === null || !Number.isFinite(price)) return;
      candleSeries.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title,
      });
    };
    addLevel(currentPrice, `現價 ${formatKlinePrice(currentPrice, vm.market)}`, '#111827');
    addLevel(vm.supportLevel, `支撐 ${formatKlinePrice(vm.supportLevel, vm.market)}`, '#16a34a');
    addLevel(vm.resistanceLevel, `壓力 ${formatKlinePrice(vm.resistanceLevel, vm.market)}`, '#dc2626');

    chart.subscribeCrosshairMove((param) => {
      const time = param.time ? String(param.time) : null;
      setHoverPoint(time ? vm.points.find((point) => point.time === time) ?? latestPoint : latestPoint);
    });

    const resize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: Math.max(containerRef.current.clientWidth, 320) });
      }
    };
    window.addEventListener('resize', resize);
    chart.timeScale().fitContent();

    return () => {
      window.removeEventListener('resize', resize);
      chart.remove();
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, [currentPrice, latestPoint, visibleMaKeys, vm]);

  if (!isSupportedInstrument(instrumentType)) return null;

  if (vm && vm.points.length === 0) {
    return (
      <section data-testid="kline-data-gap" className="rounded-lg border bg-white p-4">
        <div className="text-sm font-semibold text-foreground">價格走勢 · K 線圖</div>
        <p className="mt-1 text-xs text-muted-foreground">
          K-line 資料不足：{vm.dataGapReason || 'no_cached_ohlc'}
        </p>
      </section>
    );
  }

  return (
    <section data-testid="kline-chart-block" className="rounded-lg border bg-white p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">價格走勢 · K 線圖</h3>
          <p className="text-[10px] text-muted-foreground">
            {vm?.source || '—'} · {vm?.asOf ? `截至 ${vm.asOf}` : '等待資料'}
          </p>
          <p data-testid="kline-source-note" className="text-[10px] text-muted-foreground">
            {sourceNote(vm)}
          </p>
        </div>
        <div className="flex rounded-full border bg-muted/20 p-0.5" role="group" aria-label="K-line range">
          {RANGES.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setRange(item.value)}
              className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${
                range === item.value ? 'bg-foreground text-background' : 'text-muted-foreground'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div data-testid="kline-hover-strip" className="mb-2 rounded-md bg-slate-50 px-2.5 py-2 font-mono text-[11px] text-slate-700">
        {formatKlineStrip(activePoint, vm?.market || 'unknown')}
      </div>

      <div className="mb-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground" data-testid="kline-level-labels">
        <span data-testid="kline-current-price-label">現價 {formatKlinePrice(currentPrice, vm?.market || 'unknown')}</span>
        {vm?.supportLevel !== null && vm?.supportLevel !== undefined && (
          <span data-testid="kline-support-label">支撐 {formatKlinePrice(vm.supportLevel, vm.market)}</span>
        )}
        {vm?.resistanceLevel !== null && vm?.resistanceLevel !== undefined && (
          <span data-testid="kline-resistance-label">壓力 {formatKlinePrice(vm.resistanceLevel, vm.market)}</span>
        )}
      </div>

      <div className="h-[260px] w-full" ref={containerRef} data-testid="kline-chart-canvas-host">
        {!vm && !error && <div className="flex h-full items-center justify-center text-xs text-muted-foreground">載入 K-line...</div>}
        {error && <div className="flex h-full items-center justify-center text-xs text-danger">K-line 載入失敗</div>}
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground" data-testid="kline-ma-legend">
        {visibleMaKeys.map((key) => (
          <span key={key} className={MA_CONFIG[key].className}>{MA_CONFIG[key].label}</span>
        ))}
      </div>
    </section>
  );
}

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
import { SYSTEM_CONFIG_CHANGED_EVENT } from '../../../api/alphasift';
import { systemConfigApi } from '../../../api/systemConfig';
import type { KlineRange, KlineResponse } from '../../../types/analysis';
import {
  adaptKlineResponse,
  formatKlinePrice,
  formatKlineStrip,
  getMarketMovementColors,
  normalizeMarketReviewColorScheme,
  type KlineChartVM,
  type KlinePointVM,
  type MaKey,
  type MarketReviewColorScheme,
} from './klineChartAdapter';

const RANGES: Array<{ value: KlineRange; label: string }> = [
  { value: '1d', label: '1D' },
  { value: '5d', label: '5D' },
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

interface KlineChartBlockProps {
  historyId: number;
  instrumentType: string;
}

function isSupportedInstrument(type: string): boolean {
  return ['stock', 'etf', 'index'].includes(type);
}

function toChartTime(time: string | number): Time {
  return time as Time;
}

function gapMessage(vm: KlineChartVM): string {
  if (vm.range === '1d' && vm.dataGapReason === 'report_kline_snapshot_missing') {
    return '1D 盤中資料暫不可用：此報告未保存 1D 盤中 K snapshot。';
  }
  if (vm.range === '5d' && vm.dataGapReason === 'report_kline_snapshot_missing') {
    return '5D 盤中資料暫不可用：此報告未保存 5D 盤中 K snapshot。';
  }
  if (vm.range === '1d') return '1D 盤中資料暫不可用：yfinance 未回傳完整 OHLCV。';
  if (vm.range === '5d') return '5D 盤中資料暫不可用：資料來源暫時失敗，保留日 K 視圖。';
  return `K-line 資料不足：${vm.dataGapReason || 'no_cached_ohlc'}`;
}

export function KlineChartBlock({ historyId, instrumentType }: KlineChartBlockProps) {
  const [range, setRange] = useState<KlineRange>('3m');
  const [responses, setResponses] = useState<Partial<Record<KlineRange, KlineResponse>>>({});
  const [errors, setErrors] = useState<Partial<Record<KlineRange, string>>>({});
  const [hoverPoint, setHoverPoint] = useState<KlinePointVM | null>(null);
  const [colorScheme, setColorScheme] = useState<MarketReviewColorScheme>('green_up');
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    let active = true;
    const loadColorScheme = async () => {
      try {
        const config = await systemConfigApi.getConfig(false);
        const item = config.items.find((entry) => entry.key === 'MARKET_REVIEW_COLOR_SCHEME');
        if (active) setColorScheme(normalizeMarketReviewColorScheme(item?.value));
      } catch {
        if (active) setColorScheme('green_up');
      }
    };
    void loadColorScheme();
    window.addEventListener(SYSTEM_CONFIG_CHANGED_EVENT, loadColorScheme);
    return () => {
      active = false;
      window.removeEventListener(SYSTEM_CONFIG_CHANGED_EVENT, loadColorScheme);
    };
  }, []);

  useEffect(() => {
    if (!isSupportedInstrument(instrumentType)) return;
    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;
    if (responses[range]) return;

    historyApi.getKline(historyId, range)
      .then((data) => {
        setResponses((prev) => ({ ...prev, [data.range || range]: data }));
        setErrors((prev) => ({ ...prev, [range]: undefined }));
        if (requestSeqRef.current === seq) setHoverPoint(null);
      })
      .catch((err: unknown) => {
        if (requestSeqRef.current !== seq) return;
        setErrors((prev) => ({ ...prev, [range]: err instanceof Error ? err.message : 'kline_fetch_failed' }));
      });
  }, [historyId, instrumentType, range, responses]);

  const response = responses[range] ?? null;
  const vm = useMemo(() => (response ? adaptKlineResponse(response) : null), [response]);
  const latestPoint = vm?.points[vm.points.length - 1] ?? null;
  const activePoint = hoverPoint ?? latestPoint;
  const currentPrice = vm?.currentPrice ?? latestPoint?.close ?? null;
  const movementColors = useMemo(() => getMarketMovementColors(colorScheme), [colorScheme]);
  const error = errors[range] ?? null;

  useEffect(() => {
    if (!vm || vm.points.length === 0 || !containerRef.current) return;

    chartRef.current?.remove();
    const chartWidth = Math.max(1, containerRef.current.clientWidth);
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
      timeScale: { borderColor: '#d8dee9', timeVisible: vm.granularity === 'intraday' },
      crosshair: { mode: CrosshairMode.Normal },
      width: chartWidth,
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: movementColors.upColor,
      downColor: movementColors.downColor,
      borderUpColor: movementColors.borderUpColor,
      borderDownColor: movementColors.borderDownColor,
      wickUpColor: movementColors.wickUpColor,
      wickDownColor: movementColors.wickDownColor,
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      color: '#94a3b8',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    candleSeries.setData(vm.points.map((point) => ({
      time: toChartTime(point.chartTime),
      open: point.open,
      high: point.high,
      low: point.low,
      close: point.close,
    })));
    volumeSeries.setData(vm.points.map((point) => ({
      time: toChartTime(point.chartTime),
      value: point.volume ?? 0,
      color: point.close >= point.open ? movementColors.volumeUpColor : movementColors.volumeDownColor,
    })));

    for (const key of vm.visibleMaKeys) {
      const series = chart.addSeries(LineSeries, {
        color: MA_CONFIG[key].color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(vm.points
        .filter((point) => point[key] !== null)
        .map((point) => ({ time: toChartTime(point.chartTime), value: point[key] as number })));
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
      const time = param.time !== undefined ? String(param.time) : null;
      setHoverPoint(time ? vm.points.find((point) => String(point.chartTime) === time) ?? latestPoint : latestPoint);
    });

    const resize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: Math.max(1, containerRef.current.clientWidth) });
      }
    };
    window.addEventListener('resize', resize);
    chart.timeScale().fitContent();

    return () => {
      window.removeEventListener('resize', resize);
      chart.remove();
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, [currentPrice, latestPoint, movementColors, vm]);

  if (!isSupportedInstrument(instrumentType)) return null;

  const selectRange = (nextRange: KlineRange) => {
    setHoverPoint(null);
    setRange(nextRange);
  };

  const rangeTabs = (
    <div className="flex rounded-full border bg-muted/20 p-0.5" role="group" aria-label="K-line range" data-testid="kline-range-tabs">
      {RANGES.map((item) => (
        <button
          key={item.value}
          type="button"
          onClick={() => selectRange(item.value)}
          className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${
            range === item.value ? 'bg-foreground text-background' : 'text-muted-foreground'
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );

  return (
    <section data-testid="kline-chart-block" className="min-w-0 max-w-full overflow-hidden rounded-lg border bg-white p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">價格走勢 · K 線圖</h3>
          <p className="text-[10px] text-muted-foreground">
            {vm?.source || '—'} · {vm?.asOf ? `截至 ${vm.asOf}` : '等待資料'}
          </p>
          <p data-testid="kline-source-note" className="text-[10px] text-muted-foreground">
            {vm?.sourceNote || '等待 K-line snapshot'}
          </p>
        </div>
        {rangeTabs}
      </div>

      {vm && vm.points.length === 0 ? (
        <div data-testid="kline-data-gap" className="rounded-md bg-slate-50 px-3 py-4 text-xs text-muted-foreground">
          {gapMessage(vm)}
        </div>
      ) : (
        <>
          <div data-testid="kline-hover-strip" className="mb-2 rounded-md bg-slate-50 px-2.5 py-2 font-mono text-[11px] text-slate-700">
            {formatKlineStrip(activePoint, vm?.market || 'unknown', {
              granularity: vm?.granularity,
              interval: vm?.interval,
              source: vm?.source,
            })}
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

          <div className="h-[260px] min-w-0 max-w-full overflow-hidden" ref={containerRef} data-testid="kline-chart-canvas-host">
            {!vm && !error && <div className="flex h-full items-center justify-center text-xs text-muted-foreground">載入 K-line...</div>}
            {error && <div className="flex h-full items-center justify-center text-xs text-danger">K-line 載入失敗</div>}
          </div>

          <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground" data-testid="kline-ma-legend">
            {vm?.visibleMaKeys.map((key) => (
              <span key={key} className={MA_CONFIG[key].className}>{MA_CONFIG[key].label}</span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

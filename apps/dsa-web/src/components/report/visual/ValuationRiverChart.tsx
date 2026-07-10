import type React from 'react';
import { useMemo, useRef, useState } from 'react';
import { adaptValuationRiverSnapshot } from './valuationRiverAdapter';
import type {
  ValuationRiverChartVM,
  ValuationRiverEpsKindVM,
  ValuationRiverEpsStatVM,
  ValuationRiverZoneVM,
} from './valuationRiverAdapter';

// Phase 26.1/26.2: production valuation river chart for TW + US stock full
// reports. Commentary/action-free — every number here is backend-
// deterministic (see src/services/valuation_river_snapshot.py); this
// component never renders a buy/sell action, fair value, or target price,
// only the fixed visual reference bands + the actual close price line.
//
// Phase 26.2 adds explicit EPS/BVPS labeling: an "implied" (TW,
// PER-back-derived) or "reported" (US, real financial-statement) EPS must
// never be shown to the user as if it were the other, and a real actual/
// forward EPS point-in-time stat is surfaced separately from whichever
// basis the plotted bands use.

interface ValuationRiverChartProps {
  rawSnapshot: unknown;
}

const ZONE_LABEL: Record<ValuationRiverZoneVM, string> = {
  undervalued: '偏低估',
  neutral: '中性',
  overvalued: '偏高估',
  unknown: '—',
};

const ZONE_BADGE_CLASS: Record<ValuationRiverZoneVM, string> = {
  undervalued: 'text-success border-success/40 bg-success/10',
  neutral: 'text-warning border-warning/40 bg-warning/10',
  overvalued: 'text-danger border-danger/40 bg-danger/10',
  unknown: 'text-muted-foreground border-border bg-muted/30',
};

const BASIS_EPS_LABEL: Record<ValuationRiverEpsKindVM, string> = {
  implied: '反推 EPS',
  reported: '財報年度 EPS',
  unavailable: 'EPS',
};

const BASIS_BVPS_LABEL: Record<ValuationRiverEpsKindVM, string> = {
  implied: '反推 BVPS',
  reported: '實際 BVPS',
  unavailable: 'BVPS',
};

const EPS_PERIOD_LABEL: Record<string, string> = {
  ttm: 'TTM',
  quarterly: '單季',
  annual: '年度',
  point_in_time: '即時',
};

const METHOD_SUBTITLE: Record<string, string> = {
  per_implied_eps_river: '以 PER 反推隱含 EPS，畫出固定倍數視覺參考帶——非估值結論或目標價',
  us_reported_eps_annual_river: '以財報年度實際 EPS 建構台階狀倍數視覺參考帶——非估值結論或目標價',
};

function formatEpsStat(stat: ValuationRiverEpsStatVM | null): string {
  if (!stat) return '—';
  const periodLabel = EPS_PERIOD_LABEL[stat.period] ?? stat.period;
  return `${stat.value.toFixed(2)}（${periodLabel}）`;
}

// Fixed hex palette for SVG stroke/fill (Tailwind CSS-variable utilities do
// not reliably apply to raw SVG attributes) — mirrors the hardcoded-hex
// convention already used in MarketRiskGauge.tsx for this same reason.
const ACCENT = '#2563EB';
const GOOD = '#16A34A';
const GOOD_FILL = 'rgba(22, 163, 74, 0.14)';
const CRITICAL = '#DC2626';
const CRITICAL_FILL = 'rgba(220, 38, 38, 0.14)';
const NEUTRAL_LINE = '#94A3B8';
const NEUTRAL_FILL = 'rgba(148, 163, 184, 0.12)';

const W = 720;
const H = 300;
const MARGIN = { top: 12, right: 46, bottom: 24, left: 4 };

function ValuationRiverUnavailableCard({
  reason,
  epsActual,
  epsForward,
}: {
  reason: string;
  epsActual: ValuationRiverEpsStatVM | null;
  epsForward: ValuationRiverEpsStatVM | null;
}) {
  const hasEpsStats = epsActual !== null || epsForward !== null;
  return (
    <div
      data-testid="valuation-river-unavailable"
      className="report-light-surface rounded-xl border bg-background p-4 text-sm text-muted-foreground print:hidden"
    >
      <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        估值河流圖
      </div>
      <p>{reason}</p>
      {hasEpsStats && (
        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t pt-2 text-[11px]">
          <div>
            <div className="text-muted-foreground">實際 EPS</div>
            <div className="font-mono font-semibold text-foreground">{formatEpsStat(epsActual)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">預估 EPS</div>
            <div className="font-mono font-semibold text-foreground">{formatEpsStat(epsForward)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function ValuationRiverChartInner({ vm }: { vm: ValuationRiverChartVM }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const { points, bandMultiples, neutralMultiple } = vm;
  const n = points.length;

  const plotW = W - MARGIN.left - MARGIN.right;
  const plotH = H - MARGIN.top - MARGIN.bottom;

  const x = (i: number) => MARGIN.left + (n <= 1 ? 0 : (i / (n - 1)) * plotW);

  const { yMin, yMax } = useMemo(() => {
    const closes = points.map((p) => p.close);
    const bandValues = points.flatMap((p) => p.bands.map((b) => b.value));
    const all = [...closes, ...bandValues].filter((v) => Number.isFinite(v));
    if (all.length === 0) return { yMin: 0, yMax: 1 };
    const min = Math.min(...all);
    const max = Math.max(...all);
    const pad = (max - min) * 0.05 || max * 0.05 || 1;
    return { yMin: min - pad, yMax: max + pad };
  }, [points]);

  const y = (v: number) => MARGIN.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;

  const closePath = useMemo(
    () => points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(p.close).toFixed(2)}`).join(' '),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [points, yMin, yMax]
  );

  const bandSeriesByMultiple = useMemo(() => {
    const map = new Map<number, (number | null)[]>();
    for (const mult of bandMultiples) {
      map.set(
        mult,
        points.map((p) => p.bands.find((b) => b.multiple === mult)?.value ?? null)
      );
    }
    return map;
  }, [points, bandMultiples]);

  function pathForSeries(series: (number | null)[]): string {
    let d = '';
    let started = false;
    series.forEach((v, i) => {
      if (v === null) {
        started = false;
        return;
      }
      d += `${started ? 'L' : 'M'}${x(i).toFixed(2)},${y(v).toFixed(2)} `;
      started = true;
    });
    return d.trim();
  }

  function areaForBand(topSeries: (number | null)[], bottomSeries: (number | null)[]): string {
    const topPts: Array<[number, number]> = [];
    const bottomPts: Array<[number, number]> = [];
    for (let i = 0; i < n; i++) {
      const t = topSeries[i];
      const b = bottomSeries[i];
      if (t === null || b === null) continue;
      topPts.push([x(i), y(t)]);
      bottomPts.push([x(i), y(b)]);
    }
    if (topPts.length === 0) return '';
    const top = topPts.map(([px, py], i) => `${i === 0 ? 'M' : 'L'}${px.toFixed(2)},${py.toFixed(2)}`).join(' ');
    const bottom = bottomPts
      .slice()
      .reverse()
      .map(([px, py]) => `L${px.toFixed(2)},${py.toFixed(2)}`)
      .join(' ');
    return `${top} ${bottom} Z`;
  }

  function handleMouseMove(ev: React.MouseEvent<SVGRectElement>) {
    const svg = ev.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scaleX = W / rect.width;
    const mx = (ev.clientX - rect.left) * scaleX;
    let idx = Math.round(((mx - MARGIN.left) / plotW) * (n - 1));
    idx = Math.max(0, Math.min(n - 1, idx));
    setHoverIndex(idx);
  }

  const hovered = hoverIndex !== null ? points[hoverIndex] : null;
  const last = points[n - 1];

  // Tooltip position clamped so it can never overflow the container's own
  // bounds (required: no horizontal document overflow on mobile).
  const tooltipStyle = useMemo(() => {
    if (hoverIndex === null) return undefined;
    const leftPct = n <= 1 ? 50 : (x(hoverIndex) / W) * 100;
    const clamped = Math.min(88, Math.max(12, leftPct));
    return { left: `${clamped}%` };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoverIndex, n]);

  return (
    <div
      data-testid="valuation-river-chart"
      className="report-light-surface rounded-xl border bg-background p-4 print:break-inside-avoid"
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            估值河流圖
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {METHOD_SUBTITLE[vm.method] ?? '固定倍數視覺參考帶——非估值結論或目標價'}
          </p>
        </div>
        <span
          className={`shrink-0 rounded border px-2 py-0.5 text-[11px] font-bold ${ZONE_BADGE_CLASS[vm.current.zone]}`}
          data-testid="valuation-river-zone-badge"
        >
          {ZONE_LABEL[vm.current.zone]}
        </span>
      </div>

      <div ref={containerRef} className="relative w-full overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" style={{ minWidth: 280 }}>
          {/* horizontal gridlines */}
          {[0, 1, 2, 3, 4].map((g) => {
            const v = yMin + (g / 4) * (yMax - yMin);
            const gy = y(v);
            return (
              <g key={g}>
                <line x1={MARGIN.left} x2={W - MARGIN.right} y1={gy} y2={gy} stroke="currentColor" className="text-border" strokeWidth={1} opacity={0.5} />
                <text x={W - MARGIN.right + 6} y={gy + 3.5} className="fill-muted-foreground" style={{ fontSize: 9, fontFamily: 'ui-monospace, monospace' }}>
                  {Math.round(v).toLocaleString()}
                </text>
              </g>
            );
          })}

          {/* bands: fill between adjacent multiple lines */}
          {bandMultiples.slice(0, -1).map((mult, idx) => {
            const nextMult = bandMultiples[idx + 1];
            const bottom = bandSeriesByMultiple.get(mult) ?? [];
            const top = bandSeriesByMultiple.get(nextMult) ?? [];
            const isBelowNeutral = neutralMultiple !== null && nextMult <= neutralMultiple;
            const isAboveNeutral = neutralMultiple !== null && mult >= neutralMultiple;
            const fill = isBelowNeutral ? GOOD_FILL : isAboveNeutral ? CRITICAL_FILL : NEUTRAL_FILL;
            return <path key={mult} d={areaForBand(top, bottom)} fill={fill} stroke="none" />;
          })}

          {/* band divider lines + right-edge labels */}
          {bandMultiples.map((mult) => {
            const series = bandSeriesByMultiple.get(mult) ?? [];
            const isNeutral = mult === neutralMultiple;
            const color = isNeutral ? NEUTRAL_LINE : mult < (neutralMultiple ?? mult) ? GOOD : CRITICAL;
            const lastVal = [...series].reverse().find((v) => v !== null);
            return (
              <g key={mult}>
                <path
                  d={pathForSeries(series)}
                  fill="none"
                  stroke={color}
                  strokeWidth={isNeutral ? 1.5 : 1}
                  strokeDasharray={isNeutral ? '3 3' : undefined}
                  opacity={isNeutral ? 0.85 : 0.5}
                />
                {lastVal !== null && lastVal !== undefined && (
                  <text x={W - MARGIN.right + 6} y={y(lastVal) + 3} className="fill-muted-foreground" style={{ fontSize: 9, fontFamily: 'ui-monospace, monospace' }}>
                    {mult}x
                  </text>
                )}
              </g>
            );
          })}

          {/* actual close price line, drawn last so it stays on top */}
          <path d={closePath} fill="none" stroke={ACCENT} strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" />

          {/* hover crosshair */}
          {hovered && (
            <>
              <line x1={x(hoverIndex ?? 0)} x2={x(hoverIndex ?? 0)} y1={MARGIN.top} y2={MARGIN.top + plotH} stroke="currentColor" className="text-muted-foreground" strokeWidth={1} opacity={0.5} />
              <circle cx={x(hoverIndex ?? 0)} cy={y(hovered.close)} r={4} fill={ACCENT} stroke="white" strokeWidth={2} />
            </>
          )}

          {/* invisible overlay for hover tracking */}
          <rect
            x={MARGIN.left}
            y={MARGIN.top}
            width={plotW}
            height={plotH}
            fill="transparent"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoverIndex(null)}
            style={{ cursor: 'crosshair' }}
          />
        </svg>

        {hovered && (
          <div
            data-testid="valuation-river-tooltip"
            className="pointer-events-none absolute top-1 -translate-x-1/2 rounded-md bg-foreground px-2 py-1.5 text-[11px] leading-relaxed text-background shadow-lg"
            style={tooltipStyle}
          >
            <div className="whitespace-nowrap font-mono">{hovered.date}</div>
            <div className="whitespace-nowrap font-mono">
              收盤 <span className="font-bold">{hovered.close.toLocaleString()}</span>
            </div>
            {hovered.per !== null && <div className="whitespace-nowrap font-mono">PER {hovered.per.toFixed(2)}x</div>}
            {hovered.impliedEps !== null && (
              <div className="whitespace-nowrap font-mono">
                {BASIS_EPS_LABEL[vm.epsKind]} {hovered.impliedEps.toFixed(2)}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t pt-2 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 rounded" style={{ background: ACCENT }} />
          實際收盤價
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 rounded" style={{ background: GOOD }} />
          偏低估倍數帶
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 rounded" style={{ background: NEUTRAL_LINE }} />
          {neutralMultiple ?? '—'}x 中性分界
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 rounded" style={{ background: CRITICAL }} />
          偏高估倍數帶
        </span>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t pt-2 text-[11px] sm:grid-cols-4">
        <div>
          <div className="text-muted-foreground">最新收盤</div>
          <div className="font-mono font-semibold text-foreground">{last.close.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted-foreground">最新 PER</div>
          <div className="font-mono font-semibold text-foreground">{vm.current.per !== null ? `${vm.current.per.toFixed(1)}x` : '—'}</div>
        </div>
        <div>
          <div className="text-muted-foreground">資料範圍</div>
          <div className="font-mono text-foreground">
            {vm.startDate ?? '—'} → {vm.endDate ?? '—'}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">交易日數</div>
          <div className="font-mono text-foreground">{vm.tradingDays}</div>
        </div>
      </div>

      <div
        className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t pt-2 text-[11px] sm:grid-cols-4"
        data-testid="valuation-river-eps-stats"
      >
        <div>
          <div className="text-muted-foreground">{BASIS_EPS_LABEL[vm.epsKind]}</div>
          <div className="font-mono font-semibold text-foreground">
            {vm.current.impliedEps !== null ? vm.current.impliedEps.toFixed(2) : '—'}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">{BASIS_BVPS_LABEL[vm.epsKind]}</div>
          <div className="font-mono font-semibold text-foreground">
            {vm.current.impliedBvps !== null ? vm.current.impliedBvps.toFixed(2) : '—'}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">實際 EPS</div>
          <div className="font-mono font-semibold text-foreground">{formatEpsStat(vm.current.epsActual)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">預估 EPS</div>
          <div className="font-mono font-semibold text-foreground">{formatEpsStat(vm.current.epsForward)}</div>
        </div>
      </div>

      {vm.isPartial && vm.warnings.length > 0 && (
        <p className="mt-2 rounded bg-warning/10 px-2 py-1 text-[10.5px] text-warning">
          {vm.warnings[0]}
        </p>
      )}

      <p className="mt-2 text-[10px] leading-snug text-muted-foreground/80">{vm.methodologyNote}</p>
    </div>
  );
}

export const ValuationRiverChart: React.FC<ValuationRiverChartProps> = ({ rawSnapshot }) => {
  const vm = adaptValuationRiverSnapshot(rawSnapshot);
  if (!vm.enabled) {
    return <ValuationRiverUnavailableCard reason={vm.reason} epsActual={vm.epsActual} epsForward={vm.epsForward} />;
  }
  return <ValuationRiverChartInner vm={vm} />;
};

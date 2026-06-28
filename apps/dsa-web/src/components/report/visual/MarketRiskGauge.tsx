import type React from 'react';
import { Tooltip } from '../../common/Tooltip';
import { getReportText } from '../../../utils/reportLanguage';
import type { MarketFearIndexVM, SystemScoreVM } from './reportVisualSummaryAdapter';
import { marketFearBucket, marketFearPointerPosition } from './reportVisualSummaryAdapter';

interface MarketRiskGaugeProps {
  vixLevel: number | null;
  vixStatus: string | null;
  spxChangePct: number | null;
  dataGap?: boolean;
  marketRiskKind?: 'vix' | 'sentiment' | 'market_fear';
  sentimentScore?: number | null;
  sentimentLabel?: string | null;
  marketFearIndex?: MarketFearIndexVM | null;
  systemScore?: SystemScoreVM;
  layout?: 'report' | 'dashboard';
  className?: string;
}

const TEXT = getReportText('zh_TW');
const HORIZONTAL_W = 600;
const ARC_W = 340;
const ARC_CX = 170;
const ARC_CY = 150;
const ARC_R = 116;
const SEGMENT_COLORS = ['#16A34A', '#2563EB', '#EA580C', '#DC2626'];
const MARKER_FILL = '#F8FAFC';
const MARKER_STROKE = '#0F172A';

type Bucket = 'green' | 'blue' | 'orange' | 'red' | 'unknown';

function clampPct(v: number): number {
  return Math.max(0, Math.min(100, v));
}

function pctToX(pct: number): number {
  return Math.max(0, Math.min(HORIZONTAL_W, (pct / 100) * HORIZONTAL_W));
}

function bucketTextClass(bucket: Bucket | undefined): string {
  if (bucket === 'green') return 'text-success';
  if (bucket === 'blue') return 'text-blue-600';
  if (bucket === 'orange') return 'text-orange-600';
  if (bucket === 'red') return 'text-danger';
  return 'text-foreground';
}

function bucketTagClass(bucket: Bucket | undefined): string {
  if (bucket === 'green') return 'border-green-500/40 bg-green-50 text-green-700';
  if (bucket === 'blue') return 'border-blue-500/40 bg-blue-50 text-blue-700';
  if (bucket === 'orange') return 'border-orange-500/40 bg-orange-50 text-orange-700';
  if (bucket === 'red') return 'border-red-500/40 bg-red-50 text-red-700';
  return 'border-border bg-muted text-muted-foreground';
}

function marketStatusLabel(bucket: Bucket | undefined): string {
  if (bucket === 'green') return '平穩';
  if (bucket === 'blue') return '警戒';
  if (bucket === 'orange') return '緊張';
  if (bucket === 'red') return '恐慌';
  return '未知';
}

function systemScoreLabel(score: number | null): string {
  if (score === null) return '—';
  if (score <= 24) return '明顯偏空';
  if (score <= 39) return '偏空';
  if (score <= 59) return '中性';
  if (score <= 74) return '偏多';
  return '明顯偏多';
}

function systemTagClass(score: number | null): string {
  if (score === null) return 'border-border bg-muted text-muted-foreground';
  if (score <= 24) return 'border-red-500/40 bg-red-50 text-red-700';
  if (score <= 39) return 'border-orange-500/40 bg-orange-50 text-orange-700';
  if (score <= 59) return 'border-amber-500/40 bg-amber-50 text-amber-700';
  if (score <= 74) return 'border-green-500/40 bg-green-50 text-green-700';
  return 'border-emerald-500/40 bg-emerald-50 text-emerald-700';
}

function systemTextClass(score: number | null): string {
  if (score === null) return 'text-muted-foreground';
  if (score <= 24) return 'text-danger';
  if (score <= 39) return 'text-orange-600';
  if (score <= 59) return 'text-warning';
  return 'text-success';
}

function arcPoint(pct: number, radius = ARC_R): { x: number; y: number } {
  const angle = Math.PI * (1 - clampPct(pct) / 100);
  return {
    x: ARC_CX + radius * Math.cos(angle),
    y: ARC_CY - radius * Math.sin(angle),
  };
}

function arcPath(startPct: number, endPct: number): string {
  const start = arcPoint(startPct);
  const end = arcPoint(endPct);
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${ARC_R} ${ARC_R} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function InfoIcon({ label }: { label: string }) {
  return (
    <button
      type="button"
      className="inline-flex h-5 w-5 items-center justify-center rounded-full border text-[11px] font-black leading-none text-muted-foreground hover:border-foreground/50 hover:text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
      aria-label={label}
    >
      i
    </button>
  );
}

function StatusTag({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-black leading-none ${className}`}>
      {children}
    </span>
  );
}

function SystemScoreHelp({ explanation }: { explanation: string }) {
  return (
    <span className="block max-w-[24rem] space-y-1 text-left">
      <span className="block font-semibold">系統評分說明</span>
      <span className="block">0–24 明顯偏空</span>
      <span className="block">25–39 偏空</span>
      <span className="block">40–59 中性</span>
      <span className="block">60–74 偏多</span>
      <span className="block">75–100 明顯偏多</span>
      <span className="block pt-1 text-muted-foreground">{explanation}</span>
    </span>
  );
}

function MarketHelp({ kind, valueText }: { kind: 'vix' | 'vixtwn'; valueText: string }) {
  if (kind === 'vixtwn') {
    return (
      <span className="block max-w-[25rem] space-y-1 text-left">
        <span className="block font-semibold">VIXTWN 台灣市場恐慌指標</span>
        <span className="block">目前 VIXTWN：約 {valueText}</span>
        <span className="block">綠色（VIXTWN &lt; 20）：正常水位，台灣市場平穩，多頭常態。</span>
        <span className="block">藍色（20 ≤ VIXTWN &lt; 30）：警戒狀態，市場波動加劇，留意風險。</span>
        <span className="block">橘色（30 ≤ VIXTWN &lt; 40）：過度恐慌，投資人大舉買進避險，殺盤發生，可能為布局機會。</span>
        <span className="block">紅色（VIXTWN ≥ 40）：史詩級極度恐慌，通常伴隨系統性風險或重大黑天鵝，歷史上為強力買點。</span>
      </span>
    );
  }
  return (
    <span className="block max-w-[25rem] space-y-1 text-left">
      <span className="block font-semibold">VIX 市場恐慌指標</span>
      <span className="block">目前 VIX：約 {valueText}</span>
      <span className="block">綠色（VIX &lt; 20）：市場平穩。</span>
      <span className="block">藍色（20 ≤ VIX &lt; 28.7）：此時買進未來 12 個月的投資報酬率其實非常差。</span>
      <span className="block">橘色（28.7 ≤ VIX &lt; 33.5）：此時買進未來 12 個月的平均報酬約可達 15%。</span>
      <span className="block">紅色（VIX ≥ 33.5）：此時買進未來 12 個月的平均報酬約可達 25%。</span>
    </span>
  );
}

export const MarketRiskGauge: React.FC<MarketRiskGaugeProps> = ({
  vixLevel,
  spxChangePct,
  dataGap = false,
  marketRiskKind = 'vix',
  sentimentScore = null,
  sentimentLabel = null,
  marketFearIndex = null,
  systemScore,
  layout = 'report',
  className = '',
}) => {
  const pct = (n: number | null, decimals = 2) =>
    n !== null ? `${n > 0 ? '+' : ''}${n.toFixed(decimals)}%` : '—';

  const resolvedSystemScore: SystemScoreVM = systemScore ?? {
    label: '系統評分',
    value: sentimentScore,
    sentimentLabel,
    explanation: TEXT.systemScoreProvenance,
  };
  const resolvedMarketFear: MarketFearIndexVM | null = marketFearIndex ?? (
    vixLevel !== null
      ? {
          kind: 'vix',
          title: '恐慌指數 VIX',
          value: vixLevel,
          asOf: null,
          source: 'yfinance_yahoo_quote',
          dataGapReason: null,
          bucket: marketFearBucket('vix', vixLevel),
          pointerPosition: marketFearPointerPosition('vix', vixLevel),
        }
      : null
  );
  const hasMarket = resolvedMarketFear?.value !== null && resolvedMarketFear?.value !== undefined;
  const hasSystem = resolvedSystemScore.value !== null && resolvedSystemScore.value !== undefined;

  if (!resolvedMarketFear && (dataGap || !hasSystem)) {
    return (
      <div data-testid="market-risk-gauge" className={`rounded-lg border bg-muted/30 p-3 ${className}`}>
        <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          {marketRiskKind === 'sentiment' ? TEXT.systemScore : '恐慌指數 VIX'}
        </div>
        <p className="text-xs text-muted-foreground">
          {marketRiskKind === 'sentiment' ? '系統評分資料不足 / 暫不可用' : '指數資料暫不可用'}
        </p>
      </div>
    );
  }

  if (!resolvedMarketFear) {
    const scoreValue = hasSystem ? resolvedSystemScore.value!.toFixed(0) : '—';
    const systemStatus = systemScoreLabel(resolvedSystemScore.value);
    const systemTone = systemTextClass(resolvedSystemScore.value);

    return (
      <div data-testid="market-risk-gauge" className={`rounded-lg border bg-card p-3 ${className}`}>
        <div className="flex items-center gap-1.5">
          <span
            className="text-xs font-black uppercase tracking-wider text-muted-foreground"
            aria-label={`${resolvedSystemScore.label}：${resolvedSystemScore.explanation}`}
          >
            {resolvedSystemScore.label}
          </span>
          <Tooltip content={<SystemScoreHelp explanation={resolvedSystemScore.explanation} />} focusable contentClassName="max-w-[26rem]">
            <InfoIcon label="系統評分說明" />
          </Tooltip>
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className={`font-mono text-2xl font-black ${systemTone}`}>{scoreValue}</span>
          <StatusTag className={systemTagClass(resolvedSystemScore.value)}>{systemStatus}</StatusTag>
        </div>
      </div>
    );
  }

  const title = resolvedMarketFear?.title ?? TEXT.systemScore;
  const indexCode = resolvedMarketFear?.kind === 'vixtwn' ? 'VIXTWN' : 'VIX';
  const valueText = hasMarket ? resolvedMarketFear!.value!.toFixed(2) : '—';
  const marketValueClass = bucketTextClass(resolvedMarketFear?.bucket);
  const marketStatus = hasMarket ? marketStatusLabel(resolvedMarketFear?.bucket) : '指數資料暫缺';
  const marketPointerPct = resolvedMarketFear?.pointerPosition ?? null;
  const marketPointerX = marketPointerPct !== null ? pctToX(marketPointerPct) : null;
  const spxStr = spxChangePct !== null ? pct(spxChangePct) : null;
  const spxColor = spxChangePct !== null && spxChangePct < 0 ? '#DC2626' : '#16A34A';
  const scoreValue = hasSystem ? resolvedSystemScore.value!.toFixed(0) : '—';
  const systemStatus = systemScoreLabel(resolvedSystemScore.value);
  const systemTone = systemTextClass(resolvedSystemScore.value);
  const splitTicks = resolvedMarketFear?.kind === 'vixtwn'
    ? [
        { label: '20', pct: 25 },
        { label: '30', pct: 50 },
        { label: '40', pct: 75 },
      ]
    : [
        { label: '20', pct: 25 },
        { label: '28.7', pct: 50 },
        { label: '33.5', pct: 75 },
      ];
  const allTicks = resolvedMarketFear?.kind === 'vixtwn' ? ['0', '20', '30', '40'] : ['0', '20', '28.7', '33.5'];

  const marketHelp = resolvedMarketFear ? <MarketHelp kind={resolvedMarketFear.kind} valueText={valueText} /> : null;
  const systemHelp = <SystemScoreHelp explanation={resolvedSystemScore.explanation} />;
  const dashboardMeta = layout === 'dashboard' ? (
    <div className="mb-2 flex min-w-0 flex-wrap items-center justify-between gap-x-2 gap-y-1 px-1 text-[10px] font-semibold leading-tight">
      <span className="min-w-0 text-muted-foreground">
        <span className="font-mono">{resolvedMarketFear?.asOf ?? '—'}</span>
      </span>
      {spxStr && (
        <span className="ml-auto whitespace-nowrap" style={{ color: spxColor }}>
          S&amp;P 500 {spxStr}
        </span>
      )}
    </div>
  ) : null;
  const metricSummary = layout === 'dashboard' ? (
    <div className="min-w-0 rounded-xl border border-border/60 bg-muted/20 px-2.5 py-2.5">
      <div className="grid min-w-0 grid-cols-2 divide-x divide-border/60">
        <div className="min-w-0 px-1.5 text-center">
          <div className="mb-1 flex min-w-0 items-center justify-center gap-1">
            <span className="whitespace-nowrap text-[11px] font-black uppercase tracking-wider text-muted-foreground">{indexCode}</span>
            {resolvedMarketFear && (
              <Tooltip content={marketHelp} focusable contentClassName="max-w-[26rem]">
                <InfoIcon label={`${indexCode} 說明`} />
              </Tooltip>
            )}
          </div>
          <div className="flex min-w-0 flex-col items-center gap-1">
            <span className={`font-mono text-xl font-black leading-none ${marketValueClass}`} data-testid="market-fear-value">
              {valueText}
            </span>
            <StatusTag className={bucketTagClass(resolvedMarketFear?.bucket)}>{marketStatus}</StatusTag>
          </div>
          {!hasMarket && resolvedMarketFear?.dataGapReason && (
            <div className="mt-1 text-[11px] text-muted-foreground">{resolvedMarketFear.dataGapReason}</div>
          )}
        </div>
        <div className="min-w-0 px-1.5 text-center">
          <div className="mb-1 flex min-w-0 items-center justify-center gap-1">
            <span className="whitespace-nowrap text-[11px] font-black uppercase tracking-wider text-muted-foreground">{resolvedSystemScore.label}</span>
            <Tooltip content={systemHelp} focusable contentClassName="max-w-[26rem]">
              <InfoIcon label="系統評分說明" />
            </Tooltip>
          </div>
          <div className="flex min-w-0 flex-col items-center gap-1">
            <span className={`font-mono text-xl font-black leading-none ${systemTone}`}>{scoreValue}</span>
            <StatusTag className={systemTagClass(resolvedSystemScore.value)}>{systemStatus}</StatusTag>
          </div>
        </div>
      </div>
    </div>
  ) : (
    <div className="min-w-0 rounded-xl border border-border/60 bg-muted/20 px-3 py-2.5">
      <div className="grid min-w-0 gap-2.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start lg:gap-3">
        <div className="min-w-0">
          <div className="mb-1.5 flex items-center gap-1.5">
            <span className="whitespace-nowrap text-[11px] font-black uppercase tracking-wider text-muted-foreground">{indexCode}</span>
            {resolvedMarketFear && (
              <Tooltip content={marketHelp} focusable contentClassName="max-w-[26rem]">
                <InfoIcon label={`${indexCode} 說明`} />
              </Tooltip>
            )}
          </div>
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className={`font-mono text-xl font-black ${marketValueClass}`} data-testid="market-fear-value">
              {valueText}
            </span>
            <StatusTag className={bucketTagClass(resolvedMarketFear?.bucket)}>{marketStatus}</StatusTag>
          </div>
          <div className="mt-1 text-[12px] leading-tight text-muted-foreground">
            <span className="block">日期：</span>
            <span className="block font-mono">{resolvedMarketFear?.asOf ?? '—'}</span>
          </div>
          {!hasMarket && resolvedMarketFear?.dataGapReason && (
            <div className="mt-1 text-[11px] text-muted-foreground">{resolvedMarketFear.dataGapReason}</div>
          )}
        </div>
        <div className="min-w-0 border-t border-border/60 pt-2 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
          <div className="mb-1.5 flex items-center gap-1.5 lg:justify-end">
            <span className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">{resolvedSystemScore.label}</span>
            <Tooltip content={systemHelp} focusable contentClassName="max-w-[26rem]">
              <InfoIcon label="系統評分說明" />
            </Tooltip>
          </div>
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 lg:justify-end">
            <span className={`font-mono text-xl font-black ${systemTone}`}>{scoreValue}</span>
            <StatusTag className={systemTagClass(resolvedSystemScore.value)}>{systemStatus}</StatusTag>
          </div>
        </div>
      </div>
    </div>
  );
  const legend = (
    <div className="mt-2 grid gap-1.5 text-[12px] font-semibold text-muted-foreground sm:grid-cols-2">
      <span>恐慌指數：數值越高代表市場恐慌程度越高</span>
      <span>系統評分：分數越高代表本標的評估越偏多</span>
    </div>
  );

  if (layout === 'dashboard') {
    const marketPoint = marketPointerPct !== null ? arcPoint(marketPointerPct, ARC_R + 4) : null;
    const dashboardLabelX = marketPoint ? Math.min(ARC_W - 26, Math.max(26, marketPoint.x)) : null;
    const dashboardLabelY = marketPoint ? Math.min(166, marketPoint.y + 34) : null;

      return (
      <div data-testid="market-risk-gauge" className={`min-w-0 rounded-lg border bg-card p-3 ${className}`}>
        {dashboardMeta}
        {layout !== 'dashboard' && spxStr && (
          <div className="mb-2 text-right text-xs font-semibold" style={{ color: spxColor }}>
            S&amp;P 500 {spxStr}
          </div>
        )}
        {metricSummary}
        <svg
          data-testid="market-fear-meter"
          viewBox={`0 0 ${ARC_W} 178`}
          width="100%"
          className="mt-3 block max-w-full overflow-hidden"
          aria-label={`${indexCode} 官方恐慌指數半圓量表`}
          role="img"
        >
          {[0, 25, 50, 75].map((start, index) => (
            <path
              key={start}
              d={arcPath(start, start + 25)}
              fill="none"
              stroke={SEGMENT_COLORS[index]}
              strokeWidth="18"
              strokeLinecap="round"
              opacity="0.86"
            />
          ))}
          {splitTicks.map((tick) => {
            const p = arcPoint(tick.pct, ARC_R + 24);
            return (
              <text key={tick.label} x={p.x} y={p.y} textAnchor="middle" className="fill-muted-foreground text-[14px] font-black">
                {tick.label}
              </text>
            );
          })}
            {marketPoint && (
              <g data-testid="market-fear-pointer" aria-label={`${title} 指標位置：${valueText}`}>
                <title>{`${title} 指標位置：${valueText}`}</title>
                <polygon
                  points={`${marketPoint.x},${marketPoint.y - 10} ${marketPoint.x - 10},${marketPoint.y + 9} ${marketPoint.x + 10},${marketPoint.y + 9}`}
                  fill={MARKER_FILL}
                  stroke={MARKER_STROKE}
                  strokeWidth="2.5"
                />
                {dashboardLabelX !== null && dashboardLabelY !== null && (
                  <g aria-hidden="true">
                    <line
                      x1={marketPoint.x}
                      y1={marketPoint.y + 10}
                      x2={dashboardLabelX}
                      y2={dashboardLabelY - 12}
                      stroke={MARKER_STROKE}
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      opacity="0.38"
                    />
                    <g transform={`translate(${dashboardLabelX - 23}, ${dashboardLabelY - 9})`}>
                    <rect width="46" height="18" rx="9" fill={MARKER_FILL} stroke={MARKER_STROKE} strokeWidth="1.5" />
                    <text x="23" y="13" textAnchor="middle" className="fill-slate-950 text-[11px] font-black">
                      {valueText}
                    </text>
                    </g>
                  </g>
                )}
              </g>
            )}
          </svg>
          {legend}
        </div>
      );
  }

  const reportLabelX = marketPointerX !== null ? Math.min(574, Math.max(26, marketPointerX)) : null;

  return (
    <div data-testid="market-risk-gauge" className={`min-w-0 rounded-lg border bg-card p-3 ${className}`}>
      {spxStr && (
        <div className="mb-2 text-right text-xs font-semibold" style={{ color: spxColor }}>
          S&amp;P 500 {spxStr}
        </div>
      )}
      {metricSummary}

      <svg
        data-testid="market-fear-meter"
        viewBox="0 0 600 82"
        width="100%"
        className="mt-3 overflow-visible"
        aria-label={`${indexCode} 官方恐慌指數量表`}
        role="img"
      >
        <rect x="0" y="30" width="150" height="17" rx="2" fill="#16A34A" opacity="0.78" />
        <rect x="150" y="30" width="150" height="17" fill="#2563EB" opacity="0.72" />
        <rect x="300" y="30" width="150" height="17" fill="#EA580C" opacity="0.76" />
        <rect x="450" y="30" width="150" height="17" rx="2" fill="#DC2626" opacity="0.72" />
        {[150, 300, 450].map((x) => (
          <line key={x} x1={x} y1="28" x2={x} y2="49" stroke="white" strokeWidth="2" />
        ))}
        {allTicks.map((label, index) => (
          <text key={label} x={index * 150} y="69" textAnchor={index === 0 ? 'start' : 'middle'} className="fill-muted-foreground text-[15px] font-black">
            {label}
          </text>
        ))}
        {marketPointerX !== null && (
          <g data-testid="market-fear-pointer" aria-label={`${title} 指標位置：${valueText}`}>
            <title>{`${title} 指標位置：${valueText}`}</title>
            <line x1={marketPointerX} y1="20" x2={marketPointerX} y2="30" stroke={MARKER_STROKE} strokeWidth="2" strokeLinecap="round" />
            <polygon
              points={`${marketPointerX},30 ${marketPointerX - 7},20 ${marketPointerX + 7},20`}
              fill={MARKER_FILL}
              stroke={MARKER_STROKE}
              strokeWidth="2"
            />
            {reportLabelX !== null && (
              <g aria-hidden="true" transform={`translate(${reportLabelX - 23}, 0)`}>
                <rect width="46" height="18" rx="9" fill={MARKER_FILL} stroke={MARKER_STROKE} strokeWidth="1.5" />
                <text x="23" y="13" textAnchor="middle" className="fill-slate-950 text-[11px] font-black">
                  {valueText}
                </text>
              </g>
            )}
          </g>
        )}
      </svg>
      {legend}
    </div>
  );
};

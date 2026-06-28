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
  className?: string;
}

const SVG_W = 600;
const SYSTEM_SCORE_TEXT = getReportText('zh_TW');

function pctToX(pct: number): number {
  return Math.max(0, Math.min(SVG_W, (pct / 100) * SVG_W));
}

function bucketTextClass(bucket: string | undefined): string {
  if (bucket === 'green') return 'text-success';
  if (bucket === 'blue') return 'text-blue-600';
  if (bucket === 'orange') return 'text-orange-600';
  if (bucket === 'red') return 'text-danger';
  return 'text-foreground';
}

export const MarketRiskGauge: React.FC<MarketRiskGaugeProps> = ({
  vixLevel,
  vixStatus,
  spxChangePct,
  dataGap = false,
  marketRiskKind = 'vix',
  sentimentScore = null,
  sentimentLabel = null,
  marketFearIndex = null,
  systemScore,
  className = '',
}) => {
  const pct = (n: number | null, decimals = 2) =>
    n !== null ? `${n > 0 ? '+' : ''}${n.toFixed(decimals)}%` : '—';

  const resolvedSystemScore: SystemScoreVM = systemScore ?? {
    label: '系統評分',
    value: sentimentScore,
    sentimentLabel,
    pointerPosition: sentimentScore === null ? null : Math.max(0, Math.min(100, 100 - sentimentScore)),
    explanation: SYSTEM_SCORE_TEXT.systemScoreProvenance,
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
          {marketRiskKind === 'sentiment' ? SYSTEM_SCORE_TEXT.systemScore : '恐慌指數 VIX'}
        </div>
        <p className="text-xs text-muted-foreground">
          {marketRiskKind === 'sentiment' ? '系統評分資料不足 / 暫不可用' : '指數資料暫不可用'}
        </p>
      </div>
    );
  }

  const title = resolvedMarketFear?.title ?? SYSTEM_SCORE_TEXT.systemScore;
  const indexCode = resolvedMarketFear?.kind === 'vixtwn' ? 'VIXTWN' : 'VIX';
  const valueText = hasMarket ? resolvedMarketFear!.value!.toFixed(2) : '—';
  const marketValueClass = bucketTextClass(resolvedMarketFear?.bucket);
  const marketPointerX = resolvedMarketFear?.pointerPosition !== null && resolvedMarketFear?.pointerPosition !== undefined
    ? pctToX(resolvedMarketFear.pointerPosition)
    : null;
  const systemPointerX = resolvedSystemScore.pointerPosition !== null ? pctToX(resolvedSystemScore.pointerPosition) : null;
  const spxStr = spxChangePct !== null ? pct(spxChangePct) : null;
  const spxColor = spxChangePct !== null && spxChangePct < 0 ? '#DC2626' : '#16A34A';
  const scoreValue = hasSystem ? resolvedSystemScore.value!.toFixed(0) : '—';
  const showSystemLabelInValueRow = Boolean(resolvedMarketFear);
  const systemTone =
    !hasSystem ? 'text-muted-foreground' : resolvedSystemScore.value! <= 40 ? 'text-danger' : resolvedSystemScore.value! <= 60 ? 'text-warning' : 'text-success';
  const marketHelp = resolvedMarketFear?.kind === 'vixtwn'
    ? (
        <span className="block max-w-[22rem] space-y-1 text-left">
          <span className="block font-semibold">VIXTWN 台灣市場恐慌指標</span>
          <span className="block">目前 VIXTWN：約 {valueText}</span>
          <span className="block">綠色（VIXTWN &lt; 20）：正常水位，台灣市場平穩，多頭常態。</span>
          <span className="block">藍色（20 ≤ VIXTWN &lt; 30）：警戒狀態，市場波動加劇，留意風險。</span>
          <span className="block">橘色（30 ≤ VIXTWN &lt; 40）：過度恐慌，可能為布局機會。</span>
          <span className="block">紅色（VIXTWN ≥ 40）：極度恐慌，通常伴隨系統性風險或重大黑天鵝。</span>
        </span>
      )
    : (
        <span className="block max-w-[22rem] space-y-1 text-left">
          <span className="block font-semibold">VIX 市場恐慌指標</span>
          <span className="block">目前 VIX：約 {valueText}</span>
          <span className="block">綠色（VIX &lt; 20）：市場平穩。</span>
          <span className="block">藍色（20 ≤ VIX &lt; 28.7）：此時買進未來 12 個月的投資報酬率其實非常差。</span>
          <span className="block">橘色（28.7 ≤ VIX &lt; 33.5）：此時買進未來 12 個月的平均報酬約可達 15%。</span>
          <span className="block">紅色（VIX ≥ 33.5）：此時買進未來 12 個月的平均報酬約可達 25%。</span>
        </span>
      );
  const scaleTicks = resolvedMarketFear?.kind === 'vixtwn'
    ? [
        { range: '0', className: 'text-muted-foreground' },
        { range: '20', className: 'text-muted-foreground' },
        { range: '30', className: 'text-muted-foreground' },
        { range: '40', className: 'text-muted-foreground' },
      ]
    : [
        { range: '0', className: 'text-muted-foreground' },
        { range: '20', className: 'text-muted-foreground' },
        { range: '28.7', className: 'text-muted-foreground' },
        { range: '33.5', className: 'text-muted-foreground' },
      ];

  return (
    <div data-testid="market-risk-gauge" className={`rounded-lg border bg-card p-3 ${className}`}>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span
            className="text-xs font-bold uppercase tracking-wider text-muted-foreground"
            title={!resolvedMarketFear ? resolvedSystemScore.explanation : undefined}
            aria-label={!resolvedMarketFear ? `${resolvedSystemScore.label}：${resolvedSystemScore.explanation}` : undefined}
          >
            {title}
          </span>
          {resolvedMarketFear && (
            <Tooltip content={marketHelp} focusable contentClassName="max-w-[24rem]">
              <span
                className="inline-flex h-4 w-4 items-center justify-center rounded-full border text-[10px] font-bold text-muted-foreground"
                aria-label={`${title} 說明`}
                title={`${title} 說明`}
              >
                i
              </span>
            </Tooltip>
          )}
        </div>
        {spxStr && (
          <span className="text-xs font-semibold" style={{ color: spxColor }}>
            S&amp;P 500 {spxStr}
          </span>
        )}
      </div>

      <div className="mb-2 grid gap-1.5 text-xs">
        {resolvedMarketFear && (
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className={`font-mono text-lg font-bold ${marketValueClass}`} data-testid="market-fear-value">
              {indexCode} {valueText}
            </span>
            <span className="text-muted-foreground">日期：{resolvedMarketFear.asOf ?? '—'}</span>
            {vixStatus && !marketFearIndex && (
              <span className="rounded border border-amber-400 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                {vixStatus}
              </span>
            )}
            {!hasMarket && (
              <span className="text-muted-foreground">
                指數資料暫缺{resolvedMarketFear.dataGapReason ? `：${resolvedMarketFear.dataGapReason}` : ''}
              </span>
            )}
          </div>
        )}
        <Tooltip content={resolvedSystemScore.explanation} focusable>
          <span
            className="inline-flex w-fit flex-wrap items-baseline gap-x-2"
            title={resolvedSystemScore.explanation}
            aria-label={`${resolvedSystemScore.label}：${resolvedSystemScore.explanation}`}
          >
            {showSystemLabelInValueRow && (
              <span
                className={`font-semibold ${systemTone}`}
                title={resolvedSystemScore.explanation}
                aria-label={`${resolvedSystemScore.label}：${resolvedSystemScore.explanation}`}
              >
                {resolvedSystemScore.label}
              </span>
            )}
            <span className={`font-mono text-base font-bold ${systemTone}`}>
              {scoreValue}
            </span>
            {resolvedSystemScore.sentimentLabel && (
              <span className={`rounded border border-current px-1.5 py-0.5 text-[10px] font-bold ${systemTone}`}>
                {resolvedSystemScore.sentimentLabel}
              </span>
            )}
          </span>
        </Tooltip>
      </div>

      {resolvedMarketFear && (
        <div className="mb-1 flex items-center justify-end gap-4 text-[12px] font-bold text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-0 border-x-[6px] border-b-[10px] border-x-transparent border-b-slate-950" />
            {indexCode}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-3.5 w-3.5 rounded-full border-[2.5px] border-slate-950 bg-white" />
            系統評分
          </span>
        </div>
      )}


      <svg
        data-testid="market-fear-meter"
        viewBox="0 0 600 56"
        width="100%"
        aria-label={`${title} 與系統評分雙指針量表`}
        role="img"
      >
        <rect x="0" y="24" width="150" height="16" rx="2" fill="#16A34A" opacity="0.78" />
        <rect x="150" y="24" width="150" height="16" fill="#2563EB" opacity="0.72" />
        <rect x="300" y="24" width="150" height="16" fill="#EA580C" opacity="0.76" />
        <rect x="450" y="24" width="150" height="16" rx="2" fill="#DC2626" opacity="0.72" />
        {[150, 300, 450].map((x) => (
          <line key={x} x1={x} y1="22" x2={x} y2="42" stroke="white" strokeWidth="2" />
        ))}
        {marketPointerX !== null && (
          <g data-testid="market-fear-pointer" aria-label={`${title} 指標位置：${valueText}`}>
            <title>{`${title} 指標位置：${valueText}`}</title>
            <polygon points={`${marketPointerX},24 ${marketPointerX - 13},5 ${marketPointerX + 13},5`} fill="#111827" />
            <line x1={marketPointerX} y1="5" x2={marketPointerX} y2="25" stroke="#111827" strokeWidth="2.25" />
          </g>
        )}
        {systemPointerX !== null && (
          <g data-testid="system-score-pointer" aria-label={`系統評分指標位置：${scoreValue}`}>
            <title>{`系統評分指標位置：${scoreValue}`}</title>
            <circle cx={systemPointerX} cy="49" r="7" fill="white" stroke="#111827" strokeWidth="2.5" />
            <line x1={systemPointerX} y1="40" x2={systemPointerX} y2="49" stroke="#111827" strokeWidth="2" strokeDasharray="3 2" />
          </g>
        )}
      </svg>
      <div data-testid="market-fear-scale" className="-mt-1 grid grid-cols-4 gap-1 text-center text-[15px] font-black leading-tight">
        {scaleTicks.map((tick) => (
          <span key={tick.range} className={tick.className}>
            {tick.range}
          </span>
        ))}
      </div>
    </div>
  );
};

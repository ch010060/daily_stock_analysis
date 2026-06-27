import type React from 'react';

interface MarketRiskGaugeProps {
  vixLevel: number | null;
  vixStatus: string | null;
  spxChangePct: number | null;
  dataGap?: boolean;
  marketRiskKind?: 'vix' | 'sentiment';
  sentimentScore?: number | null;
  sentimentLabel?: string | null;
  sentimentSourceLabel?: string | null;
}

// VIX scale: 0-45. SVG viewBox 600 wide.
const SCALE_MAX = 45;
const SVG_W = 600;

function vixToX(vix: number): number {
  return Math.min(SVG_W, Math.max(0, (Math.min(vix, SCALE_MAX) / SCALE_MAX) * SVG_W));
}

export const MarketRiskGauge: React.FC<MarketRiskGaugeProps> = ({
  vixLevel,
  vixStatus,
  spxChangePct,
  dataGap = false,
  marketRiskKind = 'vix',
  sentimentScore = null,
  sentimentLabel = null,
  sentimentSourceLabel = '分析儀表板分數',
}) => {
  const pct = (n: number | null, decimals = 2) =>
    n !== null ? `${n > 0 ? '+' : ''}${n.toFixed(decimals)}%` : '—';

  if (marketRiskKind === 'sentiment') {
    if (dataGap || sentimentScore === null) {
      return (
        <div data-testid="market-risk-gauge" className="rounded-lg border bg-muted/30 p-3">
          <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            市場情緒 · 恐慌貪婪分數
          </div>
          <p className="text-xs text-muted-foreground">情緒分數資料不足 / 暫不可用</p>
        </div>
      );
    }

    const boundedScore = Math.max(0, Math.min(100, sentimentScore));
    const toneClass =
      boundedScore <= 40 ? 'bg-danger text-danger' : boundedScore <= 60 ? 'bg-warning text-warning' : 'bg-success text-success';

    return (
      <div data-testid="market-risk-gauge" className="rounded-lg border bg-card p-3">
        <div className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          市場情緒 · 恐慌貪婪分數
        </div>
        <div className="mb-2 flex items-baseline gap-2">
          <span className="font-mono text-2xl font-bold text-foreground">
            {boundedScore.toFixed(0)}
          </span>
          {sentimentLabel && (
            <span className={`rounded border border-current bg-transparent px-2 py-0.5 text-xs font-bold ${toneClass.replace('bg-', 'text-')}`}>
              {sentimentLabel}
            </span>
          )}
        </div>
        <div className="h-2 rounded-full bg-muted">
          <div
            className={`h-2 rounded-full ${toneClass.split(' ')[0]}`}
            style={{ width: `${boundedScore}%` }}
            aria-label={`恐慌貪婪分數 ${boundedScore.toFixed(0)}`}
          />
        </div>
        <div className="mt-1 flex justify-between text-[9px] text-muted-foreground">
          <span>恐慌</span>
          <span>中性</span>
          <span>貪婪</span>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">來源：{sentimentSourceLabel}</p>
      </div>
    );
  }

  if (dataGap || vixLevel === null) {
    return (
      <div data-testid="market-risk-gauge" className="rounded-lg border bg-muted/30 p-3">
        <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          市場風險 · VIX 恐慌指數
        </div>
        <p className="text-xs text-muted-foreground">VIX 資料不足 / 暫不可用</p>
      </div>
    );
  }

  const pointerX = vixToX(vixLevel);
  const spxStr = spxChangePct !== null ? pct(spxChangePct) : null;
  const spxColor = spxChangePct !== null && spxChangePct < 0 ? '#DC2626' : '#16A34A';

  return (
    <div data-testid="market-risk-gauge" className="rounded-lg border bg-card p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          市場風險 · VIX 恐慌指數
        </span>
        {spxStr && (
          <span className="text-xs font-semibold" style={{ color: spxColor }}>
            S&amp;P 500 {spxStr}
          </span>
        )}
      </div>

      <div className="mb-2 flex items-baseline gap-2">
        <span className="font-mono text-2xl font-bold text-amber-600">
          {vixLevel.toFixed(2)}
        </span>
        {vixStatus && (
          <span className="rounded border border-amber-400 bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-700">
            {vixStatus}
          </span>
        )}
      </div>

      {/* SVG segmented gauge */}
      <svg
        viewBox="0 0 600 52"
        width="100%"
        aria-label={`VIX 恐慌指數量表，當前值 ${vixLevel}`}
        role="img"
      >
        {/* segments: <15 low | 15-20 calm | 20-30 tense | >30 panic */}
        <rect x="0"   y="22" width="200" height="16" rx="2" fill="#16A34A" opacity="0.8" />
        <rect x="200" y="22" width="67"  height="16" fill="#CA8A04" opacity="0.9" />
        <rect x="267" y="22" width="133" height="16" fill="#EA580C" opacity="0.75" />
        <rect x="400" y="22" width="200" height="16" rx="2" fill="#DC2626" opacity="0.7" />
        <line x1="200" y1="20" x2="200" y2="42" stroke="white" strokeWidth="2" />
        <line x1="267" y1="20" x2="267" y2="42" stroke="white" strokeWidth="2" />
        <line x1="400" y1="20" x2="400" y2="42" stroke="white" strokeWidth="2" />
        {/* Pointer */}
        <polygon points={`${pointerX},20 ${pointerX - 7},10 ${pointerX + 7},10`} fill="#CA8A04" />
        <line x1={pointerX} y1="10" x2={pointerX} y2="22" stroke="#CA8A04" strokeWidth="1.5" />
        <rect x={pointerX - 20} y="0" width="40" height="13" rx="2" fill="#78350F" />
        <text
          x={pointerX}
          y="10.5"
          textAnchor="middle"
          fontSize="9"
          fontWeight="700"
          fill="white"
          fontFamily="monospace"
        >
          {vixLevel.toFixed(2)}
        </text>
        {/* Scale labels */}
        <text x="100"  y="50" textAnchor="middle" fontSize="9" fill="#15803D" fontFamily="system-ui">低波動 &lt;15</text>
        <text x="233"  y="50" textAnchor="middle" fontSize="9" fill="#A16207" fontFamily="system-ui" fontWeight="700">平穩 15-20</text>
        <text x="333"  y="50" textAnchor="middle" fontSize="9" fill="#C2410C" fontFamily="system-ui">緊張 20-30</text>
        <text x="500"  y="50" textAnchor="middle" fontSize="9" fill="#B91C1C" fontFamily="system-ui">恐慌 &gt;30</text>
      </svg>
    </div>
  );
};

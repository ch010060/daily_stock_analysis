import type React from 'react';
import type { TrendPeriodVM } from './reportVisualSummaryAdapter';

interface MultiPeriodTrendBarsProps {
  periods: TrendPeriodVM[];
  dataGap?: boolean;
}

const DIRECTION_SYMBOL: Record<string, string> = {
  up: '↑',
  down: '↓',
  neutral: '→',
  insufficient: '—',
};

const DIRECTION_COLOR_CLASS: Record<string, string> = {
  up: 'text-success',
  down: 'text-danger',
  neutral: 'text-warning',
  insufficient: 'text-muted-foreground',
};

const BAR_BG: Record<string, string> = {
  up: '#16A34A',
  down: '#DC2626',
  neutral: '#CA8A04',
  insufficient: '#94A3B8',
};

export const MultiPeriodTrendBars: React.FC<MultiPeriodTrendBarsProps> = ({
  periods,
  dataGap = false,
}) => {
  if (dataGap || periods.length === 0) {
    return (
      <div data-testid="multi-period-trend-bars" className="rounded-lg border bg-muted/30 p-3">
        <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          多週期趨勢
        </div>
        <p className="text-xs text-muted-foreground">趨勢資料不足 / 暫不可用</p>
      </div>
    );
  }

  return (
    <div data-testid="multi-period-trend-bars" className="rounded-lg border bg-card p-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        多週期趨勢快照
      </div>
      <div className="space-y-1.5">
        {/* Header row */}
        <div className="grid items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
          style={{ gridTemplateColumns: '44px 16px 60px 1fr 60px' }}>
          <span>週期</span>
          <span></span>
          <span className="text-right">漲跌幅</span>
          <span className="pl-2">相對強度</span>
          <span className="text-right">最大回撤</span>
        </div>

        {periods.map((p) => (
          <div
            key={p.label}
            className="grid items-center gap-2"
            style={{ gridTemplateColumns: '44px 16px 60px 1fr 60px' }}
          >
            <span className="font-mono text-xs font-bold text-foreground">{p.label}</span>
            <span className={`text-center text-sm font-bold ${DIRECTION_COLOR_CLASS[p.direction]}`}>
              {DIRECTION_SYMBOL[p.direction]}
            </span>
            <span
              className={`text-right font-mono text-xs font-bold ${DIRECTION_COLOR_CLASS[p.direction]}`}
            >
              {p.changePct !== null ? `${p.changePct > 0 ? '+' : ''}${p.changePct.toFixed(2)}%` : '—'}
            </span>
            {/* Bar track */}
            <div className="h-[5px] overflow-hidden rounded-sm bg-muted">
              <div
                className="h-full rounded-sm transition-none"
                style={{
                  width: `${p.barWidthPct}%`,
                  backgroundColor: BAR_BG[p.direction],
                  opacity: p.direction === 'insufficient' ? 0.3 : 0.55,
                }}
              />
            </div>
            <span className="text-right font-mono text-[10px] text-muted-foreground">
              {p.drawdownPct !== null ? `${p.drawdownPct.toFixed(2)}%` : '—'}
            </span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] text-muted-foreground">
        回撤欄 = 期間最大高點回撤 · 條寬 = 相對最大絕對漲跌幅
      </p>
    </div>
  );
};

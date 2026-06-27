import type React from 'react';

interface TechnicalSnapshotCardsProps {
  currentPrice: number | null;
  changePct: number | null;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  ma5DevPct: number | null;
  ma10DevPct: number | null;
  ma20DevPct: number | null;
  supportLevel: number | null;
  resistanceLevel: number | null;
  trendStrength: number | null;
  volumeRatio: number | null;
  turnoverRate: number | null;
  rsi: number | null;
}

const fmt = (n: number | null, decimals = 2): string =>
  n !== null ? n.toFixed(decimals) : '—';

const fmtPct = (n: number | null): string =>
  n !== null ? `${n > 0 ? '+' : ''}${n.toFixed(2)}%` : '—';

function DevBadge({ pct }: { pct: number | null }) {
  if (pct === null) return null;
  const isNeg = pct < 0;
  return (
    <span
      className={`ml-1 rounded px-1 py-0.5 font-mono text-[9px] font-bold ${
        isNeg ? 'text-danger' : 'text-success'
      }`}
    >
      {fmtPct(pct)}
    </span>
  );
}

function StatRow({ label, value, accent = false }: { label: string; value: React.ReactNode; accent?: boolean }) {
  return (
    <div className="flex items-baseline justify-between border-b border-border/50 py-1 last:border-b-0">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`font-mono text-xs font-bold ${accent ? 'text-foreground' : 'text-secondary-foreground'}`}>
        {value}
      </span>
    </div>
  );
}

export const TechnicalSnapshotCards: React.FC<TechnicalSnapshotCardsProps> = (props) => {
  const {
    currentPrice, changePct,
    ma5, ma10, ma20,
    ma5DevPct, ma10DevPct, ma20DevPct,
    supportLevel, resistanceLevel,
    trendStrength, volumeRatio, turnoverRate, rsi,
  } = props;

  const hasAnyTech = [ma5, ma10, ma20, supportLevel, resistanceLevel].some(v => v !== null);

  if (!hasAnyTech && currentPrice === null) return null;

  const rsiColor = rsi !== null ? (rsi < 30 ? 'text-danger' : rsi > 70 ? 'text-warning' : 'text-muted-foreground') : 'text-muted-foreground';

  return (
    <div data-testid="technical-snapshot-cards" className="rounded-lg border bg-card p-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        技術指標
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Price & MA */}
        <div>
          {currentPrice !== null && (
            <div className="mb-2">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">現價</div>
              <div className="flex items-baseline gap-1">
                <span className="font-mono text-xl font-bold text-foreground">{fmt(currentPrice)}</span>
                {changePct !== null && (
                  <span className={`text-xs font-bold ${changePct < 0 ? 'text-danger' : 'text-success'}`}>
                    {fmtPct(changePct)}
                  </span>
                )}
              </div>
            </div>
          )}
          {ma5 !== null && (
            <StatRow label="MA5" value={<>{fmt(ma5)}<DevBadge pct={ma5DevPct} /></>} />
          )}
          {ma10 !== null && (
            <StatRow label="MA10" value={<>{fmt(ma10)}<DevBadge pct={ma10DevPct} /></>} />
          )}
          {ma20 !== null && (
            <StatRow label="MA20" value={<>{fmt(ma20)}<DevBadge pct={ma20DevPct} /></>} />
          )}
        </div>

        {/* S/R + RSI + Strength */}
        <div>
          {supportLevel !== null && (
            <StatRow
              label="支撐"
              value={<span className="text-success">{fmt(supportLevel)}</span>}
            />
          )}
          {resistanceLevel !== null && (
            <StatRow
              label="壓力"
              value={<span className="text-danger">{fmt(resistanceLevel)}</span>}
            />
          )}
          {rsi !== null && (
            <StatRow
              label="RSI"
              value={<span className={rsiColor}>{fmt(rsi, 1)}{rsi < 30 ? ' 超賣' : rsi > 70 ? ' 超買' : ''}</span>}
            />
          )}
          {trendStrength !== null && (
            <div className="mt-1">
              <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                <span>趨勢強度</span>
                <span className="font-mono font-bold text-foreground">{trendStrength}/100</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-danger opacity-60"
                  style={{ width: `${Math.min(100, trendStrength)}%` }}
                />
              </div>
            </div>
          )}
          {(volumeRatio !== null || turnoverRate !== null) && (
            <div className="mt-1 flex gap-2">
              {volumeRatio !== null && (
                <StatRow label="量比" value={fmt(volumeRatio, 2)} />
              )}
              {turnoverRate !== null && (
                <StatRow label="換手" value={`${fmt(turnoverRate, 2)}%`} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

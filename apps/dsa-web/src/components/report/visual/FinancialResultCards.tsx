import type React from 'react';
import type { FinancialCardVM, FinancialKpiVM } from './reportVisualSummaryAdapter';

function kpiValueColor(kpi: FinancialKpiVM): string {
  if (!kpi.signed || kpi.value === '—') return 'text-foreground';
  if (kpi.value.startsWith('+')) return 'text-success';
  if (kpi.value.startsWith('-')) return 'text-danger';
  return 'text-foreground';
}

function FinancialCard({ card }: { card: FinancialCardVM }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-card p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
        {card.title}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3">
        {card.kpis.map((kpi) => (
          <div key={kpi.key} className="flex flex-col gap-0.5">
            <div className="text-[9px] text-muted-foreground">{kpi.label}</div>
            <div className={`font-mono text-sm font-semibold leading-tight ${kpiValueColor(kpi)}`}>
              {kpi.value}
            </div>
          </div>
        ))}
      </div>
      {(card.source || card.asOf) && (
        <div className="text-[9px] text-muted-foreground/60">
          {[card.source, card.asOf].filter(Boolean).join(' · ')}
        </div>
      )}
    </div>
  );
}

interface FinancialResultCardsProps {
  valuation: FinancialCardVM | null;
  fundamental: FinancialCardVM | null;
}

export const FinancialResultCards: React.FC<FinancialResultCardsProps> = ({
  valuation,
  fundamental,
}) => {
  if (!valuation && !fundamental) return null;

  return (
    <div data-testid="financial-result-cards" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {valuation && <FinancialCard card={valuation} />}
      {fundamental && <FinancialCard card={fundamental} />}
    </div>
  );
};

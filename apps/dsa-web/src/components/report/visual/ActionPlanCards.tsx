import type React from 'react';

interface ActionPlanCardsProps {
  idealBuy: string | null;
  secondaryBuy: string | null;
  stopLoss: string | null;
  takeProfit: string | null;
}

function PlanRow({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: string;
  colorClass: string;
}) {
  return (
    <div className="flex gap-2 border-b border-border/50 py-1.5 last:border-b-0">
      <span
        className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${colorClass}`}
      >
        {label}
      </span>
      <span className="text-xs text-secondary-foreground">{value}</span>
    </div>
  );
}

export const ActionPlanCards: React.FC<ActionPlanCardsProps> = ({
  idealBuy,
  secondaryBuy,
  stopLoss,
  takeProfit,
}) => {
  const hasAny = [idealBuy, secondaryBuy, stopLoss, takeProfit].some(Boolean);

  if (!hasAny) {
    return (
      <div data-testid="action-plan-cards" className="rounded-lg border bg-card p-3">
        <div className="mb-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          作戰計畫
        </div>
        <p className="text-xs text-muted-foreground">詳見下方完整分析報告</p>
      </div>
    );
  }

  return (
    <div data-testid="action-plan-cards" className="rounded-lg border bg-card p-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        作戰計畫
      </div>
      <div>
        {idealBuy && (
          <PlanRow
            label="理想買進"
            value={idealBuy}
            colorClass="border-success/40 bg-success/10 text-success"
          />
        )}
        {secondaryBuy && (
          <PlanRow
            label="次優買進"
            value={secondaryBuy}
            colorClass="border-success/30 bg-success/5 text-success"
          />
        )}
        {stopLoss && (
          <PlanRow
            label="止損"
            value={stopLoss}
            colorClass="border-danger/40 bg-danger/10 text-danger"
          />
        )}
        {takeProfit && (
          <PlanRow
            label="目標"
            value={takeProfit}
            colorClass="border-primary/40 bg-primary/10 text-primary"
          />
        )}
      </div>
    </div>
  );
};

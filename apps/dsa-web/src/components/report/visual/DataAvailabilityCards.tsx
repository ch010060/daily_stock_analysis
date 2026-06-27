import type React from 'react';
import type { DataAvailabilityVM } from './reportVisualSummaryAdapter';

interface DataAvailabilityCardsProps {
  items: DataAvailabilityVM[];
}

function StatusBadge({ status }: { status: DataAvailabilityVM['status'] }) {
  if (status === 'ok') {
    return (
      <span className="rounded border border-success/40 bg-success/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-success">
        可用
      </span>
    );
  }
  if (status === 'gap') {
    return (
      <span className="rounded border border-danger/40 bg-danger/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-danger">
        資料缺口
      </span>
    );
  }
  if (status === 'partial') {
    return (
      <span className="rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-warning">
        部分可用
      </span>
    );
  }
  return (
    <span className="rounded border border-border bg-muted/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
      不適用
    </span>
  );
}

export const DataAvailabilityCards: React.FC<DataAvailabilityCardsProps> = ({ items }) => {
  if (items.length === 0) return null;

  return (
    <div data-testid="data-availability-cards" className="rounded-lg border bg-card p-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        數據可用性
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.key} className="flex flex-col gap-1">
            <div className="text-[10px] font-semibold text-foreground">{item.label}</div>
            <StatusBadge status={item.status} />
            {(item.status === 'gap' || item.status === 'partial') && item.reason && (
              <div className="text-[9px] text-muted-foreground">{item.reason}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

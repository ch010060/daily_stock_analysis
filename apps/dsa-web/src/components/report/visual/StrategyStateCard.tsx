import type React from 'react';
import { adaptStrategyStateSnapshot } from './strategyStateAdapter';
import type { SupportedStrategyStateVM } from './strategyStateAdapter';

// Phase 27.2/27.2R: authoritative deterministic strategy-state section.
// Renders ONLY when an authoritative strategy_state_snapshot exists on the
// report (feature-flagged backend). Legacy reports render nothing here.
// This card is the primary action display — it never shows conflicting LLM
// action labels (the backend rewrites those fields under the same flag),
// and it never recalculates strategy state client-side.
//
// Phase 27.2R: UNSUPPORTED is intentionally excluded from the label maps
// below (both `vm.state` and `vm.previousState` are typed to exclude it —
// the adapter never returns UNSUPPORTED for either field) so there is no
// user-facing "不支援" strategy copy anywhere in this component, even for a
// stale previous snapshot persisted before instrument routing moved ahead
// of the engine.

interface StrategyStateCardProps {
  rawSnapshot: unknown;
}

const STATE_LABEL: Record<SupportedStrategyStateVM, string> = {
  WATCHLIST: '觀察名單',
  WAIT_FOR_PULLBACK: '等待回檔',
  ACCUMULATE_ZONE: '分批布局區',
  DO_NOT_CHASE: '不追價',
  HOLD_ONLY: '僅續抱',
  REDUCE_RISK: '降低風險',
  INVALIDATED: '論點失效',
};

const STATE_BADGE_CLASS: Record<SupportedStrategyStateVM, string> = {
  ACCUMULATE_ZONE: 'text-success border-success/40 bg-success/10',
  WAIT_FOR_PULLBACK: 'text-warning border-warning/40 bg-warning/10',
  WATCHLIST: 'text-muted-foreground border-border bg-muted/30',
  DO_NOT_CHASE: 'text-warning border-warning/40 bg-warning/10',
  HOLD_ONLY: 'text-muted-foreground border-border bg-muted/30',
  REDUCE_RISK: 'text-danger border-danger/40 bg-danger/10',
  INVALIDATED: 'text-danger border-danger/40 bg-danger/10',
};

export const StrategyStateCard: React.FC<StrategyStateCardProps> = ({ rawSnapshot }) => {
  const vm = adaptStrategyStateSnapshot(rawSnapshot);
  if (!vm.enabled) return null;

  return (
    <div
      data-testid="strategy-state-card"
      className="report-light-surface rounded-xl border bg-background p-4 print:break-inside-avoid"
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            策略狀態（決定性引擎）
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            由後端策略狀態機決定的最終行動，非 LLM 敘事；AI 文字內容為輔助情境解讀
          </p>
        </div>
        <span
          data-testid="strategy-state-badge"
          className={`shrink-0 rounded border px-2 py-0.5 text-xs font-bold ${STATE_BADGE_CLASS[vm.state]}`}
        >
          {STATE_LABEL[vm.state]}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[12px] sm:grid-cols-4">
        <div>
          <div className="text-muted-foreground">操作建議</div>
          <div className="font-semibold text-foreground">{vm.operationAdvice || '—'}</div>
        </div>
        <div>
          <div className="text-muted-foreground">策略買區</div>
          <div className="font-mono font-semibold text-foreground" data-testid="strategy-buy-zone">
            {vm.buyZone ? `${vm.buyZone.low}～${vm.buyZone.high}` : `無有效買區${vm.noZoneReason ? `（${vm.noZoneReason}）` : ''}`}
          </div>
          {vm.buyZone && vm.buyZone.createdAt && (
            <div className="text-[10px] text-muted-foreground">建立於 {vm.buyZone.createdAt}</div>
          )}
        </div>
        <div>
          <div className="text-muted-foreground">失效位</div>
          <div className="font-mono font-semibold text-foreground">
            {vm.invalidationLevel !== null ? vm.invalidationLevel : '—'}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">狀態持續</div>
          <div className="font-mono text-foreground">
            {vm.daysInState} 天{vm.changed && vm.previousState ? `（自 ${STATE_LABEL[vm.previousState]} 轉入）` : ''}
          </div>
        </div>
      </div>

      <div className="mt-2 border-t pt-2 text-[11px] text-muted-foreground">
        <div>
          轉移依據：{vm.transitionRuleId}
          {vm.reasons.length > 0 ? `｜${vm.reasons.join('；')}` : ''}
        </div>
        {vm.dataLimitations.length > 0 && <div>資料限制：{vm.dataLimitations.join('；')}</div>}
      </div>
    </div>
  );
};

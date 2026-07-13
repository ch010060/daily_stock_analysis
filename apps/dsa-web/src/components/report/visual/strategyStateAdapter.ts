// Phase 27.2: strategy-state snapshot adapter.
// Normalizes rawResult.strategyStateSnapshot (deep camelCase from the API
// layer; snake_case tolerated for raw payload parity, same convention as
// valuationRiverAdapter.ts) into a strict view model. The snapshot is the
// AUTHORITATIVE strategy decision computed by the deterministic backend
// engine — this adapter never recalculates state and never invents values.
// Absent / malformed / non-authoritative payloads yield { enabled: false }
// so legacy reports render completely unchanged.

export type StrategyStateValueVM =
  | "WATCHLIST"
  | "WAIT_FOR_PULLBACK"
  | "ACCUMULATE_ZONE"
  | "DO_NOT_CHASE"
  | "HOLD_ONLY"
  | "REDUCE_RISK"
  | "INVALIDATED"
  | "UNSUPPORTED";

const STATE_VALUES: readonly StrategyStateValueVM[] = [
  "WATCHLIST", "WAIT_FOR_PULLBACK", "ACCUMULATE_ZONE", "DO_NOT_CHASE",
  "HOLD_ONLY", "REDUCE_RISK", "INVALIDATED", "UNSUPPORTED",
];

// Phase 27.2R: the states a rendered card can ever carry — UNSUPPORTED is
// structurally excluded (compile-time, not just a runtime check) since this
// adapter never returns it for `state` or `previousState` when enabled=true.
export type SupportedStrategyStateVM = Exclude<StrategyStateValueVM, "UNSUPPORTED">;

export interface StrategyBuyZoneVM {
  low: number;
  high: number;
  basis: string[];
  createdAt: string | null;
}

export interface StrategyStateVM {
  enabled: true;
  state: SupportedStrategyStateVM;
  previousState: SupportedStrategyStateVM | null;
  changed: boolean;
  operationAdvice: string;
  decisionType: string;
  buyZone: StrategyBuyZoneVM | null;
  noZoneReason: string | null;
  invalidationLevel: number | null;
  transitionRuleId: string;
  asOf: string | null;
  daysInState: number;
  reasons: string[];
  dataLimitations: string[];
}

export interface StrategyStateDisabledVM {
  enabled: false;
}

export type StrategyStateAdapterResult = StrategyStateVM | StrategyStateDisabledVM;

const MAX_LIST = 6;
const MAX_TEXT = 200;

function pick(source: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null) return source[key];
  }
  return undefined;
}

function toFiniteNumber(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) ? n : null;
}

function sanitize(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.replace(/<[^>]*>/g, "").replace(/[<>]/g, "").replace(/\s+/g, " ").trim();
  return text ? text.slice(0, MAX_TEXT) : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(sanitize)
    .filter((item): item is string => Boolean(item))
    .slice(0, MAX_LIST);
}

function coerceState(value: unknown): StrategyStateValueVM | null {
  const text = typeof value === "string" ? value.trim().toUpperCase() : "";
  return (STATE_VALUES as readonly string[]).includes(text)
    ? (text as StrategyStateValueVM)
    : null;
}

export function adaptStrategyStateSnapshot(rawValue: unknown): StrategyStateAdapterResult {
  const disabled: StrategyStateDisabledVM = { enabled: false };
  if (typeof rawValue !== "object" || rawValue === null || Array.isArray(rawValue)) {
    return disabled;
  }
  const raw = rawValue as Record<string, unknown>;

  // Non-authoritative snapshots (e.g. ETF UNSUPPORTED) render nothing —
  // the legacy report stays exactly as it was.
  if (raw.authoritative !== true) return disabled;

  const state = coerceState(pick(raw, ["state"]));
  if (state === null || state === "UNSUPPORTED") return disabled;

  // Phase 27.2R: a legacy/stale previous snapshot could carry UNSUPPORTED
  // (persisted before instrument routing moved before the engine) — never
  // surface it as a user-facing "previous state" label.
  const rawPreviousState = coerceState(pick(raw, ["previousState", "previous_state"]));
  const previousState = rawPreviousState === "UNSUPPORTED" ? null : rawPreviousState;

  const zoneRaw = pick(raw, ["buyZone", "buy_zone"]);
  let buyZone: StrategyBuyZoneVM | null = null;
  if (typeof zoneRaw === "object" && zoneRaw !== null) {
    const z = zoneRaw as Record<string, unknown>;
    const low = toFiniteNumber(z.low);
    const high = toFiniteNumber(z.high);
    if (low !== null && high !== null) {
      buyZone = {
        low,
        high,
        basis: stringList(pick(z, ["basis"])),
        createdAt: sanitize(pick(z, ["createdAt", "created_at"])),
      };
    }
  }

  const reasons = stringList(pick(raw, ["reasons"]));

  return {
    enabled: true,
    state,
    previousState,
    changed: Boolean(pick(raw, ["transitionTriggered", "transition_triggered"])),
    operationAdvice: sanitize(pick(raw, ["operationAdvice", "operation_advice"])) ?? "",
    decisionType: sanitize(pick(raw, ["decisionType", "decision_type"])) ?? "",
    buyZone,
    noZoneReason: buyZone === null ? (reasons[0] ?? null) : null,
    invalidationLevel: toFiniteNumber(pick(raw, ["invalidationLevel", "invalidation_level"])),
    transitionRuleId: sanitize(pick(raw, ["transitionRuleId", "transition_rule_id"])) ?? "",
    asOf: sanitize(pick(raw, ["asOf", "as_of"])),
    daysInState: toFiniteNumber(pick(raw, ["daysInState", "days_in_state"])) ?? 0,
    reasons,
    dataLimitations: stringList(pick(raw, ["dataLimitations", "data_limitations"])),
  };
}

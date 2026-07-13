import { describe, expect, it } from 'vitest';
import { adaptStrategyStateSnapshot } from '../strategyStateAdapter';

const validSnapshot = () => ({
  schemaVersion: 1,
  symbol: '2454',
  market: 'tw',
  asOf: '2026-07-09',
  state: 'ACCUMULATE_ZONE',
  previousState: 'WAIT_FOR_PULLBACK',
  actionability: 'ACTIONABLE_ACCUMULATE',
  operationAdvice: '分批布局',
  decisionType: 'buy',
  buyZone: {
    low: 3880.0, high: 3950.0,
    basis: ['support:3880.0', 'valuation_band'],
    createdAt: '2026-07-01', revision: 0, zoneType: 'VALUATION_AND_TECHNICAL',
  },
  invalidationLevel: 3802.4,
  transitionRuleId: 'RULE_VALID_BUY_ZONE_ENTERED',
  transitionTriggered: true,
  stateEnteredAt: '2026-07-09',
  lastTransitionAt: '2026-07-09',
  daysInState: 0,
  transitionCountInWindow: 1,
  invalidationConfirmCount: 0,
  reasons: [],
  dataLimitations: [],
  authoritative: true,
});

describe('adaptStrategyStateSnapshot', () => {
  it('normalizes a valid authoritative camelCase payload', () => {
    const vm = adaptStrategyStateSnapshot(validSnapshot());
    expect(vm.enabled).toBe(true);
    if (!vm.enabled) throw new Error('expected enabled');
    expect(vm.state).toBe('ACCUMULATE_ZONE');
    expect(vm.previousState).toBe('WAIT_FOR_PULLBACK');
    expect(vm.changed).toBe(true);
    expect(vm.operationAdvice).toBe('分批布局');
    expect(vm.buyZone).toEqual({
      low: 3880.0, high: 3950.0,
      basis: ['support:3880.0', 'valuation_band'],
      createdAt: '2026-07-01',
    });
    expect(vm.invalidationLevel).toBe(3802.4);
    expect(vm.transitionRuleId).toBe('RULE_VALID_BUY_ZONE_ENTERED');
  });

  it('tolerates snake_case keys (raw payload parity)', () => {
    const vm = adaptStrategyStateSnapshot({
      state: 'WAIT_FOR_PULLBACK',
      previous_state: 'WATCHLIST',
      operation_advice: '等待回檔',
      decision_type: 'wait',
      buy_zone: { low: 3880, high: 3950, basis: ['support:3880.0'], created_at: '2026-07-01' },
      invalidation_level: 3802.4,
      transition_rule_id: 'RULE_WAIT_FOR_PULLBACK',
      transition_triggered: false,
      days_in_state: 6,
      reasons: [],
      data_limitations: [],
      authoritative: true,
    });
    expect(vm.enabled).toBe(true);
    if (!vm.enabled) throw new Error('expected enabled');
    expect(vm.operationAdvice).toBe('等待回檔');
    expect(vm.buyZone?.createdAt).toBe('2026-07-01');
    expect(vm.daysInState).toBe(6);
  });

  it('returns disabled for missing, malformed, or legacy payloads', () => {
    expect(adaptStrategyStateSnapshot(undefined)).toEqual({ enabled: false });
    expect(adaptStrategyStateSnapshot(null)).toEqual({ enabled: false });
    expect(adaptStrategyStateSnapshot('junk')).toEqual({ enabled: false });
    expect(adaptStrategyStateSnapshot({ garbage: true })).toEqual({ enabled: false });
  });

  it('returns disabled for non-authoritative snapshots (ETF UNSUPPORTED)', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.authoritative = false;
    expect(adaptStrategyStateSnapshot(payload)).toEqual({ enabled: false });

    const unsupported = validSnapshot() as Record<string, unknown>;
    unsupported.state = 'UNSUPPORTED';
    expect(adaptStrategyStateSnapshot(unsupported)).toEqual({ enabled: false });
  });

  it('exposes a no-zone reason when the engine produced no valid zone', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.state = 'WATCHLIST';
    payload.buyZone = null;
    payload.reasons = ['risk_reward_below_threshold'];
    const vm = adaptStrategyStateSnapshot(payload);
    if (!vm.enabled) throw new Error('expected enabled');
    expect(vm.buyZone).toBeNull();
    expect(vm.noZoneReason).toBe('risk_reward_below_threshold');
  });

  it('never crashes on unknown state strings', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.state = 'SOMETHING_NEW';
    expect(adaptStrategyStateSnapshot(payload)).toEqual({ enabled: false });
  });

  it('never surfaces a stale UNSUPPORTED previousState label (Phase 27.2R)', () => {
    const payload = validSnapshot() as Record<string, unknown>;
    payload.previousState = 'UNSUPPORTED';
    const vm = adaptStrategyStateSnapshot(payload);
    if (!vm.enabled) throw new Error('expected enabled');
    expect(vm.previousState).toBeNull();
  });
});

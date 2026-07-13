# Phase 27.3U — DO_NOT_CHASE Lifecycle Result

Status: `PHASE_27_3U_FAILED_PERSISTENCE_OR_STRUCTURAL_GATES`

Phase 27.3U isolates lifecycle behavior on the already-seen Phase 27.3 and
Phase 27.3S fixtures. It does not change policy thresholds, causal-level
parameters, breakdown/reclaim semantics, or operation-advice mappings. The
Phase 27.3S-A panel was not captured or inspected.

## Control-flow audit

`DO_NOT_CHASE` is entered when the current close is above a valid zone, or when
no valid zone exists but a support anchor does, and current-price risk/reward
is below the frozen 2.0 minimum. The engine recalculates this RR trigger on
every observation before generic hysteresis. Zone entry and confirmed support
break remain higher-priority, hysteresis-exempt transitions.

The committed Phase 27.3T engine had no absorbing DO_NOT_CHASE branch. Its only
blind persistence path was the generic below-zone/unconfirmed-break branch,
which copied `previous.state`. Ordinary RR-cleared exits to WAIT_FOR_PULLBACK or
WATCHLIST were already selected from current evidence and could be delayed only
inside the frozen three-day hysteresis window.

Phase 27.3U makes the lifecycle explicit:

- `RULE_RISK_REWARD_OVEREXTENDED`: entry from a different state.
- `RULE_DO_NOT_CHASE_REVALIDATED`: current RR trigger remains true.
- `RULE_DO_NOT_CHASE_CLEARED`: the stale below-zone carry is cleared to WATCHLIST.
- Existing `RULE_WAIT_FOR_PULLBACK`, `RULE_VALID_BUY_ZONE_ENTERED`,
  `RULE_CONFIRMED_SUPPORT_BREAK`, and `RULE_HYSTERESIS_HOLD` retain their meaning.

No snapshot metadata or policy parameter was added. Older schema-v1 snapshots
deserialize unchanged and are reevaluated against current evidence.

## Development A/B

Both arms used byte-equivalent inputs, `causal_swing_cluster_v1`, and the frozen
Phase 27.2R policy across 2,436 observations (Phase 27.3: 1,468; Phase 27.3S:
968). Arm A reproduces the committed Phase 27.3T lifecycle; Arm B uses the
explicit revalidation and neutral stale-carry exit.

| Metric | A: Phase 27.3T | B: lifecycle repair |
| --- | ---: | ---: |
| DO_NOT_CHASE transitions | 75 | 75 |
| DO_NOT_CHASE observations | 1,768 (72.58%) | 1,765 (72.45%) |
| Median / p75 / p90 duration | 8 / 28.25 / 50.9 | 7.5 / 28.25 / 50.9 |
| Maximum duration | 125 | 125 |
| Right-censored runs | 14 | 14 |
| Current trigger true and retained | 1,666 | 1,666 |
| Hysteresis-delayed retained observations | 24 | 24 |
| Current trigger cleared but persisted | 3 | 0 |
| Right-censored after trigger cleared | 0 | 0 |
| ACCUMULATE_ZONE | 152 | 152 |
| WAIT_FOR_PULLBACK | 55 | 55 |
| WATCHLIST | 231 | 234 |
| REDUCE_RISK | 219 | 219 |

The repair changed only three matched observations from DO_NOT_CHASE to
WATCHLIST. Twenty-four exits to ACCUMULATE had valid-zone proof; no such exit
lacked a valid zone. Breakdown recognition remained 11/11, confirmed reclaim
exits remained 9, terminal invalidations remained 0, and direct
REDUCE_RISK-to-ACCUMULATE exits remained 0.

All 1,693 Arm A retained observations and all 1,690 Arm B retained
observations are classified, including 13 left-censored runs. Exit-lag
accounting covers all 74 observed exits in each arm: 24 to ACCUMULATE_ZONE,
19 to WAIT_FOR_PULLBACK, 30/31 to WATCHLIST, and Arm A's one confirmed-break
exit to REDUCE_RISK. The earlier Phase 27.3T figure of 1,155
DO_NOT_CHASE-to-DO_NOT_CHASE matches was a same-date cross-arm comparison,
not a chronological retained-observation count; it therefore cannot be
substituted for this lifecycle classification.

DO_NOT_CHASE remained dominant in both panels: 918/1,468 (62.53%) for Phase
27.3 and 847/968 (87.50%) for Phase 27.3S. It also remained dominant in TW
(930/1,332, 69.82%) and US (835/1,104, 75.63%). Regime occupancy was highest
in high volatility (95.19%), ordinary pullbacks (89.17%), strong uptrends
(86.27%), and sideways periods (83.13%). Thirteen of 18 symbols exceeded 65%
DO_NOT_CHASE occupancy; GOOGL remained 100%.

All measured lifecycle structural rates remained zero: same-input and
same-sequence nondeterminism, anchor lint, zone movement without trigger,
zone-entry contradictions, untriggered flips, and unjustified rally/decline
transitions. The no-lookahead result is inherited from the causal-prefix tests;
both lifecycle arms reuse identical frozen input and provenance hashes.

Outcome diagnostics were unchanged for almost every cell. Two US
WATCHLIST/sharp-rally deltas exceeded 0.10, but their cell size changed only
from one to two observations, so they are mixed and underpowered rather than
policy-selection evidence.

## Gate decision

The explicit lifecycle correctness gates passed: no stale trigger retention,
no right-censoring after trigger clearance, preserved causal provenance,
determinism, zone behavior, and breakdown/reclaim behavior.

The product gates failed: DO_NOT_CHASE did not improve by 20%, combined and
per-panel occupancy stayed above 50%, median duration stayed above five,
right-censored runs stayed above eight, and DO_NOT_CHASE remained a majority
state. The dominant cause is current resistance/RR evidence, not
previous-state inertia. This corrects Phase 27.3T's preliminary persistence
diagnosis. Forcing exits, hiding a still-true constraint behind a
non-persisted guard, or adding a duration timeout would contradict the
measured trigger and is rejected. A separately scoped resistance/RR
investigation would be required before any further product approval.

Phase 27.3S-A readiness: `DO_NOT_CONSUME_PHASE_27_3S_A`

Recommendation: `RETAIN_PHASE_27_3R_AND_STOP_STRATEGY_PRODUCTIZATION`

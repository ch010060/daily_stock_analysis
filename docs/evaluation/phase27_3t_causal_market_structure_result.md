# Phase 27.3T — Causal Market-Structure Development Result

Status: `PHASE_27_3T_CAUSAL_LEVELS_VALID_RR_PERSISTENCE_BLOCKED`

Phase 27.3T adds a pure, causal swing-pivot producer and compares it with the committed level source on the already-seen Phase 27.3 and Phase 27.3S fixtures. StrategyPolicy thresholds and state-transition semantics are unchanged. Phase 27.3S-A was not captured or inspected.

## Contract

- Additive analyzer fields: `market_structure_support_levels`, `market_structure_resistance_levels`
- Engine priority: active causal structure → compatible legacy independent level → MA60/MA20 fallback
- Provenance: price, kind, confirmation/first/last dates, touches, prominence, source window, status
- Broken/stale/out-of-side diagnostics are retained but never offered to the engine
- Agent/non-Agent paths share the same normalized StrategyStateInput

Algorithm `causal_swing_cluster_v1` uses 3-left/3-right confirmed pivots, a three-observation delay, 14-observation ATR, minimum 0.75-ATR prominence, bounded 0.5%-2% clustering tolerance, median representatives, a 120-observation source window, 60-observation expiry, and a two-close 1% break rule. Resistance-to-support role reversal is disabled.

## Development A/B

Panels: Phase 27.3 = 1,468 evaluations; Phase 27.3S = 968; combined = 2,436 across 18 symbols.

| Metric | A: committed source | B: causal structure |
| --- | ---: | ---: |
| Independent support inputs | 0 | 2,124 (87.19%) |
| Independent resistance inputs | 0 | 2,101 (86.25%) |
| MA fallback zone observations | 1,306 | 0 observed |
| Market-structure zone-basis observations | 0 | 1,769 |
| RR-overextension rule observations | 96 | 84 |
| DO_NOT_CHASE transitions | 88 | 75 |
| DO_NOT_CHASE occupancy | 1,231 (50.53%) | 1,768 (72.58%) |
| DO_NOT_CHASE median duration | 5 | 8 |
| DO_NOT_CHASE maximum duration | 125 | 125 |
| DO_NOT_CHASE right-censored runs | 8 | 14 |
| ACCUMULATE_ZONE | 255 | 152 |
| WAIT_FOR_PULLBACK | 45 | 55 |
| WATCHLIST | 563 | 231 |
| REDUCE_RISK | 329 | 219 |
| Confirmed breaks | 10 | 11 |
| Confirmed reclaims | 9 | 9 |

TW support coverage was 1,179/1,332 (88.51%) and US 945/1,104 (85.60%). TW resistance coverage was 1,216/1,332 (91.29%) and US 885/1,104 (80.16%). Every one of the 18 symbols produced usable support; coverage was not concentrated.

Across as-of diagnostics, support statuses were active 4,078, broken 2,923, stale 3,804, and out-of-side 170; resistance statuses were active 4,000, broken 2,222, stale 3,378, and out-of-side 112. Support touch provenance included 7,675 single-pivot, 2,424 double-touch, 683 triple-touch, and 193 four-touch observations.

Per-panel DO_NOT_CHASE occupancy also worsened independently: Phase 27.3 changed 606→921; Phase 27.3S changed 625→847. Thus the combined result is not an artifact of only one panel.

DO_NOT_CHASE exits changed from 39→24 via valid-zone entry, 32→30 via WATCHLIST, 19→19 via WAIT, and 1→1 via confirmed break. Fewer entries and fewer RR-overextension rule observations nevertheless produced much longer total occupancy. This isolates persistence/exit behavior as the primary blocker rather than missing support alone.

Matched-date state changes include 1,155 DO_NOT_CHASE→DO_NOT_CHASE observations, 294 WATCHLIST→DO_NOT_CHASE, 167 REDUCE_RISK→DO_NOT_CHASE, and 125 ACCUMULATE_ZONE→DO_NOT_CHASE. Only 15 DO_NOT_CHASE observations changed to ACCUMULATE.

All structural rates remained zero: no-lookahead failures, same-input/sequence nondeterminism, anchor lint, zone movement, zone-entry contradiction, untriggered flips, rally upgrades, and decline downgrades. Sparse-history and malformed-level tests prove MA fallback compatibility even though the high-coverage B arm did not need it in these panels.

Outcome diagnostics had four eligible market/state/regime metrics worsen by more than 0.10 and one improve by more than 0.10. They are diagnostic only and do not override the failed state-distribution gates.

Verification: 139 focused tests passed with four opt-in skips; Phase 27.3 heavy replay passed 19/3 skips; Phase 27.3S heavy replay passed 19/3 skips; the Phase 27.3T A/B opt-in passed; py_compile, focused flake8, and `git diff --check` passed. Every replay ran with `DSA_ALLOW_EXTERNAL_NETWORK=false`.

## Gate result

Passed: causal/no-lookahead, determinism, structural consistency, both-market coverage, all-symbol distribution, fallback compatibility, and ACCUMULATE reachability.

Failed:

- no state may become an indiscriminate majority;
- DO_NOT_CHASE occupancy must materially decrease or be separately blocked.

The separate blocker is confirmed: entries decreased 14.77%, but occupancy increased 43.62% because runs persisted longer.

## Decision

Root cause: `DO_NOT_CHASE_PERSISTENCE_IS_PRIMARY_CAUSE`

S-A readiness: `DO_NOT_CONSUME_PHASE_27_3S_A`

Recommendation: `REVISE_DO_NOT_CHASE_EXIT_SEMANTICS`

The Phase 27.3T work remains uncommitted pending operator review.

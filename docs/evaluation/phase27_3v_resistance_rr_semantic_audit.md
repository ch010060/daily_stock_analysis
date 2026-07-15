# Phase 27.3V — Resistance/RR Semantic Audit

Status: `PHASE_27_3V_CONFIRMS_STRATEGY_PRODUCTIZATION_SHOULD_STOP`

This audit uses only the already-seen Phase 27.3 and Phase 27.3S fixtures.
Phase 27.3S-A remains unconsumed. No production policy, state mapping, causal
level parameter, provider, database, runtime, or outcome label is an input.

## Frozen production contract

- A new zone is centered on the selected support with the committed ±2%
  tolerance and is intersected with valuation constraints when present.
- Its invalidation is `zone.low * 0.98`.
- Zone feasibility uses `entry = zone.high`, the nearest eligible resistance
  above that entry, and `RR = (resistance-entry)/(entry-invalidation)`.
- A missing resistance does not reject the zone.
- Above a valid zone, the chase check instead uses `entry = current close` and
  the persisted/current invalidation. `RR < 2.0` produces
  `RULE_RISK_REWARD_OVEREXTENDED`.
- With no zone, the chase downside reference is the nearest support itself.
- The engine selects the nearest resistance among at most three active causal
  levels passed by the orchestrator, then falls back to the nearest legacy
  deterministic resistance. Full causal provenance remains available only to
  evaluation.
- Actual holder/non-holder position ownership is absent from the deterministic
  input contract and must not be inferred from prior strategy states.

## Frozen resistance selectors

Only causal levels with `status=active` are eligible. Broken, stale, and
out-of-side levels remain diagnostics, never targets. Legacy fallback is
labelled `legacy_unqualified`.

- `R0`: exact production-equivalent selection.
- `R1`: nearest active resistance from all retained causal provenance above
  the entry; legacy nearest-above fallback.
- `R2`: strongest producer-ranked active resistance above the entry; `R1`
  fallback.
- `R3`: nearest active resistance above the zone midpoint; legacy
  nearest-above fallback.
- `R4`: second price-ordered active resistance above the entry; `R1` fallback
  when fewer than two exist.
- `R5`: equal-weight mean reward to the first two price-ordered active
  resistances; one-target `R1` fallback.

Arm E is permitted only if, before outcome inspection, R0 returns no causal
target or a legacy target while an eligible causal target exists in retained
provenance. Mere disagreement between nearest and strongest is not a defect.

## Frozen entry references

- `E0`: production chase reference; current close for DNC.
- `E1`: current close, reported explicitly to expose that E0=E1 here.
- `E2`: zone midpoint.
- `E3`: zone upper bound; canonical `RR_AT_PLANNED_ZONE`.
- `E4`: zone lower bound.

All references use the same deterministic invalidation. `RR_NOW` is E1 and
`RR_AT_PLANNED_ZONE` is E3. They answer immediate-buy and planned-entry
questions respectively and are never substituted for one another.

## Frozen primary DNC classification

The first matching rule wins, giving exactly one category per observation:

1. selected/available ceiling is broken, stale, or out-of-side →
   `RESISTANCE_STALE_OR_ALREADY_BROKEN`;
2. no persisted/current valid zone → `NO_VALID_ZONE`;
3. a persisted zone no longer passes E3 RR →
   `PREVIOUS_ZONE_SEMANTIC_CONFLICT`;
4. price is inside or within the committed 2% tolerance above the zone while
   RR fails → `PRICE_INSIDE_OR_NEAR_ZONE_BUT_RR_FAIL`;
5. price is above a valid zone, E1 fails, and E3 passes →
   `PRICE_ABOVE_VALID_ZONE_RR_FROM_CURRENT_PRICE`;
6. price is above a valid zone and E3 also fails →
   `PRICE_ABOVE_VALID_ZONE_RR_FROM_ZONE_ENTRY`;
7. when E3 is unavailable, R0 E1 fails but R4 E1 passes →
   `RESISTANCE_TOO_CLOSE`;
8. when E3 is unavailable, R0 E1 and E4 both fail →
   `RISK_DISTANCE_TOO_LARGE`;
9. price is above every known eligible/legacy resistance →
   `CURRENT_PRICE_OVEREXTENSION`;
10. otherwise → `OTHER_EXPLICIT_REASON`.

`RESISTANCE_TOO_CLOSE`, `RISK_DISTANCE_TOO_LARGE`, and overextension are also
reported as orthogonal drivers because reward/risk algebra alone cannot prove
which side is economically defective.

Replay holder meaning is frozen as `AMBIGUOUS_CURRENT_CONTRACT`: no position
input exists. Synthetic counterfactuals alone may emit the four explicit
holder/non-holder meanings.

## Frozen semantic arms

- Arm A: committed Phase 27.3U production semantics.
- Arm B: only when a DNC result has a valid zone below price, `RR_NOW < 2`, and
  `RR_AT_PLANNED_ZONE >= 2`, persist `WAIT_FOR_PULLBACK` instead.
- Arm C: DNC is a non-persisted `DO_NOT_CHASE_NOW` guard. The underlying state
  is WAIT when a valid zone is below price, otherwise WATCHLIST. Zone entry,
  breakdown, reclaim, and terminal behavior retain priority.
- Arm D: paired synthetic counterfactual only. Non-holder + valid zone below
  price maps to WAIT; holder + intact structure maps to HOLD_ONLY with a
  no-add guard. It is not run as historical truth because position ownership
  is unavailable.
- Arm E: R1 input precedence with current state semantics, only if the
  preregistered structural R0 defect above is observed before outcomes.

No duration timeout, parameter grid, symbol exception, or outcome-selected arm
is allowed.

## Frozen gates and execution order

State outputs, distributions, classifications, transition matrices, input
hashes, and gates are written before forward labels are attached. Only then
are existing outcome cells calculated as diagnostics.

The twenty operator-specified structural and distribution gates remain
unchanged: zero leakage/nondeterminism/anchor/zone failures; chase/panic at
most 5%; unchanged breakdown/reclaim safety; no state above 50% combined or
55% per panel; no unexplained 100% symbol concentration; actionable states
remain reachable; no WAIT/WATCH/HOLD misuse; DNC materially decreases while
true immediate overextension remains detectable; zone entry remains
ACCUMULATE; and no symbol-specific rules or thresholds.

For this audit, “materially decreases” is frozen as at least a 20% relative
reduction from Arm A's DNC count. `ACCUMULATE_ZONE` remains meaningfully
reachable at a minimum 5% share. WAIT and WATCH are indiscriminate if either
breaches the already-frozen 50% combined or 55% per-panel concentration caps.

## Frozen replay result

The replay completed 2,436 evaluations per state arm: 1,468 from Phase 27.3
and 968 from Phase 27.3S. Input and causal-provenance fingerprints were
identical, same-input and same-sequence nondeterminism were zero, and no
Phase 27.3S-A data was captured or inspected.

### Entry-reference result

Of 1,765 Arm A DNC observations, 1,310 (74.22%) had `RR_NOW < 2` while
`RR_AT_PLANNED_ZONE >= 2`. The disagreements occurred in both markets (TW
739; US 571), every represented regime, and 17 symbols. GOOGL contributed
125, AVGO 123, 3231 115, 2382 114, 2454 106, LLY 99, 2330 98, 2308 91,
3008 76, 2891 62, AAPL 55, NVDA 52, AMZN 51, 2317 39, 2881/MSFT 38 each,
and META 28.

`RR_NOW` had median 0.3260 (p25 0.1290, p75 0.6331, p90 1.1057; n=1,764).
`RR_AT_PLANNED_ZONE` had median 3.4548 (p25 2.3882, p75 4.8398, p90
7.2071; n=1,537). The exact-one DNC categories were:

| Primary category | Count | Share |
| --- | ---: | ---: |
| PRICE_ABOVE_VALID_ZONE_RR_FROM_CURRENT_PRICE | 1,307 | 74.05% |
| NO_VALID_ZONE | 227 | 12.86% |
| PREVIOUS_ZONE_SEMANTIC_CONFLICT | 222 | 12.58% |
| PRICE_INSIDE_OR_NEAR_ZONE_BUT_RR_FAIL | 6 | 0.34% |
| OTHER_EXPLICIT_REASON | 3 | 0.17% |

The first two categories alone cover 86.91% of DNC occupancy. All 1,765
historical holder meanings remain `AMBIGUOUS_CURRENT_CONTRACT`; position
ownership is not present in the deterministic input.

### Resistance-quality result

R0 and R1 were identical on every observation. R0 selected 2,087 causal
levels, 336 legacy unqualified levels, and had 13 missing targets. It selected
zero broken/stale/out-of-side levels and had zero preregistered structural
coverage defects, so Arm E was not run. R0 differed from strongest-level R2
on 515 observations, and 1,212 selected levels had a higher active target,
but the two-target R5 changed the immediate RR gate only 43 times. In DNC
observations, moving to the next target made RR pass only 55 times.

Selected resistance distance from current price had median 5.59% (p25 2.68%,
p75 10.00%, p90 16.09%); distance from the zone midpoint had median 21.68%
(p25 15.64%, p75 30.51%, p90 44.82%). Median confirmation age was 18 days
and median last-touch age was 23 days. These results reject resistance
selection as the primary 72.45% DNC cause, while retaining the 43 multi-target
gate changes as diagnostic evidence only.

### Semantic-arm result

| State | A current | B planned-zone | C action guard |
| --- | ---: | ---: | ---: |
| ACCUMULATE_ZONE | 152 | 152 | 152 |
| DO_NOT_CHASE | 1,765 | 446 | 0 |
| HOLD_ONLY | 11 | 11 | 11 |
| REDUCE_RISK | 219 | 219 | 219 |
| WAIT_FOR_PULLBACK | 55 | 1,374 | 1,596 |
| WATCHLIST | 234 | 234 | 458 |

Arm B remapped 1,319 matched DNC observations to WAIT. Its DNC duration fell
from median/p75/p90/max 7.5/28.25/50.9/125 to 4/8/15.6/25 and right-censored
runs fell from 14 to 2. However WAIT became 56.40% combined and 74.38% on
Phase 27.3S. Arm C emitted 1,736 `DO_NOT_CHASE_NOW` guards and removed DNC as
a persisted state, but WAIT became 65.52% combined and 86.05% on Phase 27.3S.
Both arms left ACCUMULATE, HOLD, REDUCE, confirmed-break, reclaim, zone-entry,
anchor, chase/panic, and determinism metrics unchanged.

Both alternatives failed the same six preregistered gates: combined state
majority, per-panel concentration, four symbols with 100% non-terminal state
concentration (2382, 3231, AVGO, GOOGL), indiscriminate WAIT fallback,
complete immediate-overextension detection, and holder/non-holder semantics.
The holder gate is intentionally unpassable without position truth; this is
why Arm D cannot establish a historically viable replacement.
Arm D remained a synthetic-only counterfactual because no deterministic
holder input exists. Across the 1,765 baseline DNC observations, its holder
lens mapped all 1,765 to `HOLD_ONLY` / `HOLDER_HOLD_WITHOUT_ADDING`; its
non-holder lens mapped 1,315 to `WAIT_FOR_PULLBACK` /
`NON_HOLDER_WAIT_FOR_ENTRY` and 450 to `DO_NOT_CHASE` /
`NON_HOLDER_TRUE_CHASE_RISK`. This is classification evidence, not a
historically executable arm.

The frozen immediate-overextension diagnostic found 456 eligible observations.
Arm A detected 431, Arm B 427, and Arm C 436. The preregistered strict gate
requires every eligible observation to remain detectable, so both alternatives
failed it. The gate was not relaxed after viewing these results.

Outcome diagnostics were inspected only after state outputs and gates were
frozen. Most >0.10 deltas came from cells reduced to very small samples; only
one Arm B cell with at least 20 observations in both compared cells exceeded
0.10 (`tw:DO_NOT_CHASE:support_breakdown` maximum adverse excursion,
-0.1019). Outcomes were not used to select or reject an arm.

## Decision

Root cause: `MULTIPLE_SEMANTIC_DEFECTS`

The primary measured defect is `ENTRY_REFERENCE_SEMANTIC_MISMATCH`, compounded
by a persisted state taxonomy that cannot represent “good planned setup, bad
immediate entry” without collapsing into WAIT, plus an absent deterministic
holder/non-holder contract. Resistance selection is not the primary defect.

Phase 27.3S-A readiness: `DO_NOT_CONSUME_PHASE_27_3S_A`

Recommendation: `RETAIN_PHASE_27_3R_AND_CLOSE_PHASE_27`

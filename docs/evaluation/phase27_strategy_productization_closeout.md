# Phase 27 Strategy Productization Close-out

## Final status

`PHASE_27_CLOSEOUT_RESEARCH_COMPLETE_NO_PRODUCT`

Phase 27 is closed as a research line. Its branch history and evaluation
assets are retained for audit, but no Phase 27 strategy is approved for
production use.

## Original problem

Production evidence showed price-action narrative inertia: reports chased
rallies, downgraded in panic after declines, anchored entries to prior closes,
moved buy zones with short moving averages, and lacked deterministic authority
from the previous strategy state. The same market input could consequently
produce conflicting advice across reruns.

## Work completed

- Phase 27.1 built the pure deterministic strategy-state engine and snapshot
  contract.
- Phase 27.2/27.2R added persistence, Agent/non-Agent authority parity,
  instrument routing, provider-failure handling, and the offline data contract.
- Phase 27.3 added consecutive replay and holdout calibration; calibration
  failed to generalize and the baseline was retained.
- Phase 27.3R serialized support/resistance and separated temporary technical
  breakdown (`REDUCE_RISK`) from terminal invalidation.
- Phase 27.3S executed a new preregistered holdout; it was underpowered for
  invalidation validation and exposed zero independent support coverage.
- Phase 27.3T added causal market-structure levels; coverage improved, but
  `DO_NOT_CHASE` state concentration worsened.
- Phase 27.3U corrected stale `DO_NOT_CHASE` carry by revalidating current
  evidence, proving lifecycle persistence was not the dominant remaining cause.
- Phase 27.3V audited resistance and RR semantics and found no non-collapsing
  replacement state mapping.

## Durable technical assets

The deterministic engine and snapshots, Agent/non-Agent authority parity,
offline sequential replay framework, no-lookahead and determinism checks,
causal market-structure producer, current-trigger revalidation fix, structured
semantic diagnostics, and frozen-gate evaluation discipline remain useful
research infrastructure. They are not approval for production strategy
decisions.

## Final root-cause findings

```text
MULTIPLE_SEMANTIC_DEFECTS
ENTRY_REFERENCE_SEMANTIC_MISMATCH
HOLDER_NONHOLDER_STATE_CONFLATION
```

Decisive evidence:

```text
Baseline DO_NOT_CHASE occupancy: 72.45%
RR_NOW < 2 while RR_AT_PLANNED_ZONE >= 2: 1,310 / 1,765
Planned-zone arm WAIT_FOR_PULLBACK: 56.40%
Action-guard arm WAIT_FOR_PULLBACK: 65.52%
```

The alternatives reduced `DO_NOT_CHASE` by moving the concentration into
`WAIT_FOR_PULLBACK`; neither produced a viable state distribution.

## Final product decision

```text
Phase 27 strategy productization: NO-GO
Phase 27.3S-A unseen capture: NO-GO
Phase 27.4 portfolio gating: NO-GO
PR to main: NO-GO
Merge to main: NO-GO
```

## Future restart criteria

Any future attempt is a new product design, not Phase 27.3W threshold tuning.
It must explicitly separate:

```text
underlying structural state
holder state
non-holder opportunity state
planned-entry quality
immediate-entry action guard
portfolio opportunity cost
```

The current eight-state contract must not be reused unchanged.

## Repository disposition

The complete research line is archived on
`feat/phase27-strategy-inertia-research` and is intentionally not merged into
main.

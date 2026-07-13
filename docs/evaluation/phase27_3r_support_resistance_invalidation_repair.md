# Phase 27.3R — Support/Resistance and Invalidation Repair

Status: `PHASE_27_3R_SUPPORT_RESISTANCE_AND_INVALIDATION_REPAIR_READY_FOR_REVIEW`

This repair follows checkpoint `c486ea9946cfdc0ac19a67b025076c1fd65bdcfd`. It is intentionally uncommitted and does not approve a new threshold set.

## Scope and safety

- Branch: `fix/phase27-3r-strategy-invalidation-semantics`
- Parent: Phase 27.3 replay checkpoint `c486ea9946cfdc0ac19a67b025076c1fd65bdcfd`
- No production DB/runtime access, network replay, push, PR, merge, or portfolio gating
- Reused the sanitized Phase 27.3 panel only for baseline regression comparison
- Did not run the 300-policy grid and did not use the old holdout for selection

## Deterministic S/R serialization

`StockTrendAnalyzer` already calculated `support_levels` and `resistance_levels`, but `TrendAnalysisResult.to_dict()` omitted them. Both production paths serialize this dictionary before `build_strategy_state_input`, so the strategy engine lost the arrays.

The repair adds the existing names as additive fields:

```text
support_levels
resistance_levels
```

Sanitization is centralized in `normalize_price_levels`:

- reject booleans, malformed values, NaN, infinities, zero, and negatives;
- convert accepted values to float;
- support ordering: descending (nearest/highest support first);
- resistance ordering: ascending (nearest/lowest resistance first);
- adjacent sorted values are duplicates when `math.isclose(rel_tol=1e-6, abs_tol=1e-8)`;
- preserve all existing MA and result fields.

The orchestrator applies the same sanitizer to legacy dictionary callers and independently rejects non-finite scalar values. Agent and non-Agent paths still share `_attach_strategy_state_snapshot`, and the parity test now captures and compares the actual `StrategyStateInput` built from a `TrendAnalysisResult` object.

Important provenance guard: the analyzer's current support list contains conditional MA5/MA10/MA20 values, not independently calculated swing-low supports. The engine therefore ignores serialized support entries that match MA5, MA10, or MA20 within the same tolerance; otherwise serialization would relabel moving averages as `support:*` and bypass the existing zone-drift guard. A distinct non-MA support remains preferred when supplied by a compatible deterministic producer, then legacy MA60/MA20 fallback remains available. The current replay panel has no such independent support values; the serialized resistance values are the analyzer's deterministic 20-day highs.

## State semantics

### Confirmed technical break

Two consecutive closes below the frozen invalidation level now produce:

```text
state = REDUCE_RISK
rule = RULE_CONFIRMED_SUPPORT_BREAK
buy_zone = None
invalidation_level = breached frozen level
```

The rule remains hysteresis-exempt. A price break alone can no longer emit `INVALIDATED`.

### Terminal invalidation

`INVALIDATED` is reserved for deterministic terminal thesis invalidation. `thesis_status="invalidated"` still uses `RULE_THESIS_INVALIDATED`, bypasses hysteresis, and becomes absorbing through `RULE_TERMINAL_STATE_PERSISTED`. Production still supplies `thesis_status=None` and no deterministic risk flags, so normal price movement cannot reach terminal invalidation.

No terminal flags were fabricated. Existing non-terminal deterministic risk flags continue to map to REDUCE_RISK.

### Reclaim/reactivation

A new centralized policy field is preregistered before replay:

```text
reclaim_confirmation_days = 2
```

Reclaim is counted in consecutive replay/market observations:

1. First close back at or above the breached level: remain REDUCE_RISK with `RULE_SUPPORT_RECLAIM_PENDING`.
2. Any close back below the level resets the reclaim count.
3. Second consecutive reclaimed close: transition to WATCHLIST with `RULE_CONFIRMED_SUPPORT_RECLAIM`.
4. The old zone and invalidation level are cleared.
5. No REDUCE_RISK→ACCUMULATE transition is allowed. A later evaluation must generate a fresh deterministic zone and RR basis.

`StrategyStateSnapshot.reclaim_confirm_count` is additive; legacy snapshots without it deserialize as zero. Legacy technical `INVALIDATED` snapshots carrying `RULE_CONFIRMED_SUPPORT_BREAK` enter the same reclaim path rather than remaining terminal.

## Baseline-only replay comparison

Policy:

```text
support tolerance = 2%
anchor lint tolerance = 1%
minimum RR = 2.0
hysteresis = 3
break confirmation = 2
reclaim confirmation = 2
```

| Metric | Old Phase 27.3 | Repaired baseline |
| --- | ---: | ---: |
| INVALIDATED observations | 257 | 0 |
| REDUCE_RISK observations | 0 | 209 |
| Quick-recovery false invalidations | 13/17 | 0 |
| Quick-recovery technical breaks | not separated | 2 |
| Confirmed-break recognition | 17/17 (100%) | 8/8 (100%) |
| Confirmation lag | 2 | 2 |
| ACCUMULATE_ZONE | 311 | 176 |
| WAIT_FOR_PULLBACK | 742 | 23 |
| DO_NOT_CHASE | 0 | 606 |
| WATCHLIST | 87 | 443 |
| HOLD_ONLY | 71 | 11 |
| Untriggered flips | 0% | 0% |
| Zone-entry contradictions | 0% | 0% |
| Zone movement without trigger | 0% | 0% |
| Anchor lint failures | 0% | 0% |
| Unjustified rally upgrades | 0% | 0% |
| Unjustified decline downgrades | 2.33% | 0% |
| REDUCE_RISK direct-to-ACCUMULATE exits | n/a | 0 |
| Same-sequence nondeterminism | 0% | 0% |

Input coverage after serialization:

- serialized support arrays: 864/1,468 (58.86%), all MA-derived;
- independent non-MA support arrays: 0/1,468 (0%);
- serialized resistance arrays: 1,457/1,468 (99.25%);
- emitted independent-support zone bases: 0;
- emitted MA20/MA60 fallback bases: 597.

The semantic correction succeeded: technical breaks emitted by the repaired engine moved from INVALIDATED to REDUCE_RISK, terminal false invalidations disappeared, reclaim was neutral-first, and chase/panic/zone gates did not regress.

The distribution changed materially because serialized resistance is now active in RR construction: DO_NOT_CHASE rose to 606 and ACCUMULATE fell to 176. ACCUMULATE did not collapse (11.99%), and no state exceeded 41.28%, but the reused panel cannot approve that distribution. The old and repaired confirmed-break episode counts (17 versus 8) are not directly comparable because S/R and RR input construction changed at the same time as the state semantics. The primary semantic evidence is that every repaired technical break produced REDUCE_RISK and none produced INVALIDATED; this reused panel cannot isolate the causal contribution of serialization from the transition repair.

Generated baseline artifact remains outside git:

```text
/private/tmp/phase27_3r_baseline/phase27_3r_repaired_baseline.json
```

Validation commands for the reviewed working tree:

```text
DSA_ALLOW_EXTERNAL_NETWORK=false python -m pytest -q <focused Phase 27 suites>
RUN_PHASE27_EVAL=1 DSA_ALLOW_EXTERNAL_NETWORK=false python -m pytest -q tests/evaluation/test_phase27_3_strategy_sequence_replay.py
DSA_ALLOW_EXTERNAL_NETWORK=false ./scripts/ci_gate.sh
python -m py_compile <changed Python files>
python -m flake8 <changed Python files>
git diff --check
```

Final results:

- focused Phase 27 regression: 125 passed, 115 repository-defined skips;
- heavy repaired offline replay: 14 passed, one intentionally frozen legacy-grid skip;
- py_compile: passed;
- focused flake8: changed files passed; `stock_analyzer.py` passed when excluding only its pre-existing W293/F541/F811 categories;
- `git diff --check`: passed;
- backend gate: 3,734 passed, 397 skipped, 22 failed. Ten failures came from the unrelated pre-existing untracked `tests/test_history_candles_api.py`, four from unrelated untracked Kronos validation files, and eight from `tests/test_yfinance_intraday_kline.py`, whose mocked-provider expectations conflict with the gate-wide fail-closed `DSA_ALLOW_EXTERNAL_NETWORK=false` setting. None of the 22 failing files is modified by Phase 27.3R.

The broad regression suite's 115 skips come from files listed by the existing polluted-test-file guard; they are not repair failures. The heavy replay intentionally skips the frozen legacy calibration-grid test unless `RUN_PHASE27_LEGACY_CALIBRATION=1` is set. The backend-gate failures are retained as an explicit verification limitation rather than being hidden by altering or staging unrelated worktree files.

## Recommendation

`PROCEED_TO_NEW_PREREGISTERED_HOLDOUT`

Use `docs/evaluation/phase27_3r_new_holdout_plan.md`. Run the repaired baseline first; do not reuse the Phase 27.3 holdout for threshold selection.

# Phase 27.3 — Real consecutive strategy replay and threshold calibration

## Status

`PHASE_27_3_FAILED_KILL_CRITERIA_TRIGGERED`

The committed Phase 27.2R policy remains unchanged because the frozen calibration candidate failed holdout. This result does **not** approve Phase 27.4 opportunity gating: the replay found unresolved invalidation churn and a production input-serialization limitation that prevents meaningful RR calibration.

## Isolation and reproducibility

- Branch: `feat/phase27-3-strategy-replay-calibration`
- Base: `809a349b5f28fc2b4eea15f7c6ce97e1b705e65b`
- Production database/runtime: never opened or started
- Capture source: Yahoo Finance through the already-installed `yfinance` adapter
- Requested capture range: 2024-08-01 through 2025-09-01 inclusive
- Adjustment mode: `auto_adjust=True`
- Raw capture path: `/private/tmp/phase27_3_capture` (`/tmp` resolves to `/private/tmp` on this macOS host; temporary, not committed)
- Sanitized fixture: `tests/fixtures/phase27_3/panel.csv` (OHLCV and source labels only)
- Capture metadata/hash: `tests/fixtures/phase27_3/manifest.json`
- Final generated artifact: `/private/tmp/phase27_3_final/phase27_3_evaluation.json` (outside git)
- Offline replay gate: `DSA_ALLOW_EXTERNAL_NETWORK=false`

The replay builder filters the immutable bar sequence at each `as_of`, runs that prefix through `StockTrendAnalyzer.analyze(...).to_dict()`, and then calls the production `build_strategy_state_input`. Future bars are attached only after snapshots are frozen. A poisoning test changes a future close to 9999 and proves the earlier input is byte-equivalent.

## Panel and split

Stock panel:

- TW: 2330, 2454, 2308, 2317, 2881, 6505
- US: AAPL, MSFT, NVDA, LLY
- Label-only benchmarks: 0050 for TW, SPY for US

Final replay range: 2024-10-25 through 2025-06-06. The 60 preceding observations warm MA60; 60 later observations remain label-only. Total stock evaluations: 1,468.

Observed deterministic regimes: strong uptrend, sideways, ordinary pullback, sharp rally, sharp decline, support breakdown, rebound after decline, and high volatility.

Frozen split:

- Calibration through 2025-03-31: 2330, 2454, 2308, 2317, 2881, AAPL, MSFT, NVDA
- Holdout from 2025-04-01: all ten stocks
- Unseen holdout-only symbols: 6505 and LLY
- Split fingerprint: `ce47131251a3231b15d6902d90075f9d3709ff4da043820f636c0a02dea97da1`

## Metrics fixed for the final run

- Sharp rally/decline: daily return at least +5% / at most -5%
- Zone movement: serialized zone changes require a `zone_revised:*` reason and a revision increment; critical invalidation may clear a zone
- Zone-entry contradiction: prior WAIT zone contains the close, no critical trigger exists, but output becomes REDUCE_RISK/INVALIDATED
- False invalidation diagnostic: the first confirmed-break transition in an episode is followed by a close back at/above the frozen invalidation level within five market observations
- Repeated days already in INVALIDATED are not counted as new confirmed-break events
- Material holdout worsening: more than 2 percentage points on a primary structural rate, more false invalidations, state share above 85%, or state-level 20D/60D outcome deterioration above 0.10
- Generalization: the same primary relative improvement must appear in both TW and US holdout subsets

During harness development, a unit test found that repeated days already in INVALIDATED were initially being counted as separate breakdown events. The metric was corrected before the final evidence run. The frozen candidate did not change, and no second candidate was selected from holdout results.

## Baseline result

Committed policy:

```text
support_tolerance_pct = 0.02
anchor_lint_tolerance_pct = 0.01
minimum_risk_reward = 2.0
hysteresis_days = 3
invalidation_confirmation_days = 2
```

Primary results:

| Metric | Result |
| --- | ---: |
| Same-input nondeterminism | 0% |
| Same-sequence nondeterminism | 0% |
| Completed unsupported stock reports | 0 |
| Provider-failure completed reports | 0 |
| Anchor lint failures | 0% |
| Zone movement without trigger | 0% |
| Zone-entry contradiction | 0% |
| Untriggered state flips | 0% |
| WAIT↔ACCUMULATE boundary oscillations | 0 |
| Unjustified rally upgrades | 0% |
| Unjustified decline downgrades | 2.33% (1/43) |
| Confirmed-break recognition | 100% (17/17 episodes) |
| Confirmation lag | 2.0 market observations |
| Critical transitions suppressed by hysteresis | 0 |
| Quick-recovery false invalidations | 76.47% (13/17 episodes) |
| INVALIDATED → non-INVALIDATED reactivations | 15 |
| Transitions per 20 observations | 1.91 |

State distribution:

| State | Count | Share |
| --- | ---: | ---: |
| WAIT_FOR_PULLBACK | 742 | 50.55% |
| ACCUMULATE_ZONE | 311 | 21.19% |
| INVALIDATED | 257 | 17.51% |
| WATCHLIST | 87 | 5.93% |
| HOLD_ONLY | 71 | 4.84% |

The state mix does not collapse to one state, and all mandatory structural consistency gates pass. However, invalidation behavior is not yet product-ready: 13 of 17 first confirmed-break episodes recovered above the invalidation level within five observations, and 15 sequences later left INVALIDATED. INVALIDATED observations also had positive mean forward returns in this panel (20D +6.04%, 60D +22.39%), which is diagnostic evidence of recoverable-bottom classification—not a profitability claim.

## Calibration and holdout

Full bounded grid (300 policies):

```text
support_tolerance_pct: 0.01, 0.015, 0.02, 0.025, 0.03
minimum_risk_reward: 1.5, 1.75, 2.0, 2.25, 2.5
hysteresis_days: 2, 3, 4, 5
invalidation_confirmation_days: 1, 2, 3
```

The calibration split selected this frozen candidate on primary structural rates:

```text
support_tolerance_pct = 0.01
minimum_risk_reward = 1.5
hysteresis_days = 2
invalidation_confirmation_days = 1
```

It failed holdout:

- TW quick-recovery false invalidations: baseline 0, candidate 4
- US quick-recovery false invalidations: baseline 4, candidate 5
- Candidate holdout state distribution: INVALIDATED 293/450 (65.11%), WAIT 142/450, ACCUMULATE 7/450, HOLD 3/450, WATCHLIST 5/450
- TW ACCUMULATE fell from 41 to 3; US ACCUMULATE fell from 29 to 4
- The calibration improvement did not generalize safely across both markets

Decision: `BASELINE_POLICY_RETAINED_HOLDOUT_FALSE_INVALIDATIONS`. Production defaults remain at the Phase 27.2R values.

## Production-semantic limitation

`StockTrendAnalyzer` computes `support_levels` and `resistance_levels`, but `TrendAnalysisResult.to_dict()` does not serialize either field. The production pipeline passes this exact dictionary into `build_strategy_state_input`; therefore the replay correctly receives empty explicit support/resistance arrays and falls back to MA60/MA20. Consequences:

- the explicit resistance-based RR path is usually unavailable;
- varying `minimum_risk_reward` cannot be interpreted as a valid production RR calibration;
- injecting the omitted arrays only in evaluation would create a second, more favorable contract and was deliberately rejected.

This limitation must be resolved and separately regression-tested before another threshold-selection holdout is credible.

## Regression scenarios and parity

The combined Phase 27.1/27.2R/27.3 suite passes:

- 2454-style persisted-zone entry becomes ACCUMULATE without moving the zone
- large red day does not reduce risk without confirmed invalidation
- large green day does not become ACCUMULATE solely from the rally
- support-boundary motion does not flip daily
- a confirmed two-observation break bypasses hysteresis
- technical-only stock remains supported
- provider outage raises and does not produce a completed snapshot
- Agent/non-Agent mocked LLM actions produce identical chained strategy snapshots, final authority fields, deterministic sniper points, and provider-failure behavior

## Deterministic field audit

| Field | Classification | Evidence / decision |
| --- | --- | --- |
| `previous_close` | `DIAGNOSTIC_ONLY` | Deterministically reconstructed and parity-tested; no engine transition consumes it. |
| `daily_change_pct` | `DIAGNOSTIC_ONLY` | Used only by replay chase/panic diagnostics; engine state does not consume its sign. |
| `multi_period_trend` | `DEFERRED_NEEDS_DETERMINISTIC_SOURCE` | Production builder currently sets `None`; no leakage-safe historical production source is wired into the strategy input. |
| `volume_ratio` | `DIAGNOSTIC_ONLY` | Trustworthy OHLCV source and reconstructed without leakage; no measured failure justified a new rule. |
| `capital_flow_bias` | `DIAGNOSTIC_ONLY` | Production computation exists, but the historical fixture has no point-in-time fundamental-flow series; no rule added. |
| `valuation_zone` | `DIAGNOSTIC_ONLY` | Categorical field is not consumed; numeric valuation-band constraints remain the relevant engine inputs when available. |
| `thesis_status` | `DEFERRED_NEEDS_DETERMINISTIC_SOURCE` | Engine supports deterministic invalidation, but production deliberately supplies `None`; never inferred from LLM prose. |
| `deterministic_risk_flags` | `DEFERRED_NEEDS_DETERMINISTIC_SOURCE` | Engine contract exists, but production supplies an empty tuple; no flags were fabricated. |

## Production changes and rollback

- Added only offline evaluation code, tests, sanitized fixtures, and this document.
- `StrategyPolicy` defaults, feature flag defaults, production DB schema, runtime paths, LLM prompts, ranking, sizing, allocation, and broker behavior are unchanged.
- No dependency was added.
- Generated JSON remains outside git.

Rollback:

```bash
git switch feat/phase27-2-strategy-authority-integration
git branch -D feat/phase27-3-strategy-replay-calibration
```

## Recommendation

`REVISE_PHASE_27_3_POLICY_OR_REPLAY`

Before Phase 27.4, repair and lock the production technical S/R serialization contract, define whether INVALIDATED should be absorbing or require a deterministic reactivation rule, then run a new preregistered holdout. Do not change thresholds based on this failed candidate.

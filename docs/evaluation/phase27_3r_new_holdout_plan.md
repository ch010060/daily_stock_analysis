# Phase 27.3R — Preregistered New Holdout Plan

Status: `PREREGISTERED_NOT_CAPTURED_NOT_EVALUATED`

This plan is frozen before capture. Phase 27.3R does not fetch or evaluate this set.

## Data contract

- Source: Yahoo Finance through the installed `yfinance` adapter
- Adjustment: `auto_adjust=True`
- Raw capture window: 2025-07-01 through 2026-07-01 inclusive
- Capture call convention: request `start=2025-07-01` and exclusive `end=2026-07-02`; the expected last row is the latest trading date on or before 2026-07-01
- Evaluation window: 2025-10-01 through 2026-03-31
- Pre-evaluation rows provide MA60 warmup; post-evaluation rows provide 60D labels
- Sanitized columns only: symbol, market, date, open, high, low, close, volume, source ticker, benchmark
- Raw payload/cache outside git; immutable fixture includes capture timestamp and SHA-256 manifest
- Replay must pass with `DSA_ALLOW_EXTERNAL_NETWORK=false`

## Frozen panel

TW stocks:

```text
2382  2891  3008  3231
```

US stocks:

```text
AMZN  META  GOOGL  AVGO
```

Label-only benchmarks:

```text
TW → 0050
US → SPY
```

No stock overlaps the old Phase 27.3 panel. No symbol-specific policy or exception is allowed.

## Required regime coverage

Episode definitions are frozen as follows:

- A confirmed technical-break episode starts on the first `REDUCE_RISK` snapshot carrying `RULE_CONFIRMED_SUPPORT_BREAK`; its reference level is that snapshot's retained, non-null invalidation level.
- A quick break/recovery is an episode with a close at or above the retained reference level within the next five market observations.
- A sustained break is an episode with no close at or above the retained reference level in the next 20 market observations. An episode without all 20 future observations is right-censored and excluded from sustained-break coverage.
- An eligible reclaim episode is a technical-break episode with a retained reference level and at least `reclaim_confirmation_days` subsequent market observations. A confirmed reclaim exit is counted only when `RULE_CONFIRMED_SUPPORT_RECLAIM` is emitted. End-of-window episodes lacking the required observations are censored, not failures.

Regimes use the existing Phase 27.3 `_classify_regime` implementation and thresholds, in its current precedence order:

1. daily return >= 5%: sharp rally;
2. daily return <= -5%: sharp decline;
3. 5D return >= 5% after prior 5D return <= -8%: rebound;
4. close < MA60 × 0.98: support breakdown;
5. 20D daily-return standard deviation >= 3%: high volatility;
6. 20D return >= 10%: strong uptrend;
7. absolute 20D return <= 3%: sideways;
8. otherwise: ordinary pullback.

The fixed panel/window must contain, after deterministic classification:

- at least two confirmed technical-break episodes per market;
- at least one quick break/recovery episode per market;
- at least one sustained-break episode per market;
- sharp rally, sharp decline, sideways, pullback, rebound, and high-volatility observations;
- at least 20 consecutive evaluations per symbol.

If the frozen set lacks coverage, the evaluation is `INSUFFICIENT_PREREGISTERED_REGIME_COVERAGE`. Do not add symbols or move dates after inspecting outcomes. Publish the failed coverage result, then preregister a replacement set before capture.

## Execution order

1. Capture once outside the repository and sanitize/hash the immutable subset.
2. Build all inputs through `StockTrendAnalyzer.to_dict()` and `build_strategy_state_input` with strict as-of filtering.
3. Run only the repaired Phase 27.3R baseline.
4. Verify structural, state-distribution, reclaim, and breakdown gates.
5. Attach outcome labels only after snapshots are frozen.
6. Do not run a parameter grid unless a separate calibration/holdout protocol is preregistered with another untouched evaluation set.

## Frozen primary gates

```text
same-input nondeterminism = 0%
same-sequence nondeterminism = 0%
completed unsupported/provider-failure reports = 0
anchor lint failures = 0%
zone movement without trigger = 0%
zone-entry contradiction = 0%
untriggered state flips = 0%
unjustified rally upgrades <= 5%
unjustified decline downgrades <= 5%
confirmed-break recognition = 100%
critical transition hysteresis suppression = 0
technical break producing INVALIDATED = 0
unjustified terminal INVALIDATED = 0
REDUCE_RISK direct-to-ACCUMULATE exits = 0
confirmed reclaim exits / eligible reclaim episodes = 100%
```

Distribution gates:

```text
no single state > 70%
ACCUMULATE_ZONE >= 5%
REDUCE_RISK must occur when confirmed-break episodes exist
DO_NOT_CHASE must not exceed 50%
```

Outcome diagnostics are non-optimization gates:

- compare equal-weight market/state cells separately at 20D and 60D; a cell is gate-eligible only with at least 10 uncensored observations in both datasets;
- no gate-eligible cell's mean raw or benchmark-relative return may deteriorate by more than 0.10 in decimal-return units (10 percentage points) versus the repaired reused-panel baseline;
- a state absent from either dataset, or a cell below the minimum sample size, is reported as diagnostic-only and cannot independently pass or fail the gate;
- report forward 5D/20D/60D, MAE, MFE, and benchmark-relative returns by market/state/regime;
- do not claim profitability or alpha.

## Stop conditions

- no-lookahead or production-construction parity cannot be proven;
- explicit S/R disappears on either integration path;
- technical breaks produce terminal INVALIDATED;
- one-day reclaim exits REDUCE_RISK;
- confirmed reclaim jumps directly to ACCUMULATE;
- candidate selection reads this validation set;
- state distribution breaches a frozen gate.

Passing this baseline validation permits a separately planned calibration phase; it does not itself approve new thresholds.

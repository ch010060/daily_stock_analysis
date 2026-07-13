# Phase 27.3S-A — Underpowered Holdout Preregistration Amendment

Status: `PREREGISTERED_NOT_CAPTURED_NOT_EVALUATED`

This is a separate validation set created only after the frozen Phase 27.3S result was declared underpowered. It does not alter, extend, or replace that result. No capture is authorized by this document alone.

## Frozen expansion

- TW stocks: 2379, 2882, 3034, 5871
- US stocks: AMD, JPM, NFLX, TSLA
- Benchmarks: TW→0050, US→SPY
- Raw capture: 2024-07-01 through 2026-07-01 inclusive (`end=2026-07-02` exclusive)
- Evaluation: 2025-01-02 through 2026-03-31
- Source/adjustment: Yahoo Finance via yfinance, `auto_adjust=True`

The panel is disjoint from both prior Phase 27 panels. Selection is fixed at four liquid stocks per market with varied business and volatility profiles; it does not use Phase 27.3S outcomes to alter policy.

## Unchanged contract

Use the same baseline policy, input construction, episode definitions, censoring rules, regime classifier, structural gates, distribution gates, and 0.10 outcome-deterioration gate from `phase27_3r_new_holdout_plan.md`. Run no grid. Capture once outside git, hash the sanitized fixture, delete raw data, and replay with `DSA_ALLOW_EXTERNAL_NETWORK=false`.

Required episode coverage remains at least two confirmed breaks, one quick recovery, and one sustained breakdown per market. Failure remains underpowered; do not add symbols or extend dates after capture.

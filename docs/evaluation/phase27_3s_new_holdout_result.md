# Phase 27.3S — New Preregistered Holdout Result

Status: `PHASE_27_3S_NEW_HOLDOUT_UNDERPOWERED`

The frozen Phase 27.3S panel was captured once and evaluated unchanged with the Phase 27.2R thresholds plus the preregistered two-observation reclaim rule. No grid or threshold selection ran.

## Isolation

- Source: Yahoo Finance via yfinance, `auto_adjust=True`
- Requested capture: 2025-07-01 through 2026-07-01 inclusive (`end=2026-07-02` exclusive)
- Capture timestamp: 2026-07-13T03:11:03.414288+00:00
- Raw capture path: `/private/tmp/phase27_3s_capture/raw` (deleted after sanitization)
- Sanitized fixture SHA-256: `47fa30bf8958ed22bf5f3c6dad2671963519e2aa227264cfd32ff0d2f241a217`
- Final replay: `DSA_ALLOW_EXTERNAL_NETWORK=false`
- Production DB/runtime: not accessed

## Frozen panel

TW: 2382, 2891, 3008, 3231. US: AMZN, META, GOOGL, AVGO. Evaluation: 2025-10-01 through 2026-03-31.

Total evaluations: 968 (TW 468; US 500).

All required regime labels occurred: sharp rally 15, sharp decline 12, sideways 224, ordinary pullback 230, rebound 5, and high volatility 58. Strong-uptrend and support-breakdown labels also occurred.

## Results

| State | Total | TW | US |
| --- | ---: | ---: | ---: |
| ACCUMULATE_ZONE | 79 | 45 | 34 |
| DO_NOT_CHASE | 625 | 332 | 293 |
| HOLD_ONLY | 2 | 0 | 2 |
| REDUCE_RISK | 120 | 0 | 120 |
| WAIT_FOR_PULLBACK | 22 | 17 | 5 |
| WATCHLIST | 120 | 74 | 46 |

DO_NOT_CHASE occupied 64.57% overall, 70.94% in TW, and 58.60% in US, breaching the frozen 50% gate. ACCUMULATE remained reachable at 8.16%; WAIT remained reachable but sparse at 2.27%. RR-overextension transitions occurred 29 times (TW 16, US 13; 3.00% overall); their persisted state occupancy, rather than transition frequency alone, drove DO_NOT_CHASE dominance.

Break episodes: 2 total, both US. Both entered REDUCE_RISK; zero entered INVALIDATED. There were zero quick recoveries, one sustained breakdown, one confirmed reclaim at 17 observations, and one episode still in REDUCE_RISK at window end. Mean REDUCE_RISK duration was 60 observations (maximum 103). One-day rebound violations and direct REDUCE_RISK→ACCUMULATE transitions were zero.

The preregistered coverage requirement failed: TW had no confirmed, quick-recovery, or sustained-break episodes; US had no quick-recovery episode. Therefore invalidation semantics cannot be accepted or rejected from this holdout even though the two observed breaks followed the repaired contract.

Structural metrics remained clean: same-sequence nondeterminism, anchor lint, zone movement, zone-entry contradictions, untriggered flips, unjustified rally upgrades, and unjustified decline downgrades were all 0%; confirmed-break recognition was 2/2.

Four outcome cells breached the frozen 0.10 deterioration bar: TW DO_NOT_CHASE benchmark-relative 60D, TW WAIT_FOR_PULLBACK benchmark-relative 60D, and US REDUCE_RISK raw and benchmark-relative 60D. These are diagnostic failures, not profitability claims.

Verification: focused Phase 27 suites 114 passed/3 opt-in skips; new heavy offline holdout 17 passed/2 unrelated opt-in skips; py_compile, focused flake8, and `git diff --check` passed.

## Support provenance

- Serialized support: 621/968 (64.15%)
- Independent non-MA support: 0/968 (0%)
- MA fallback: 607/968 (62.71%)
- Serialized resistance: 960/968 (99.17%)
- Emitted zone bases: `ma60` only, 709 basis observations

`INVALIDATION_SEMANTICS_NOT_VALIDATED_UNDERPOWERED`

`INDEPENDENT_SUPPORT_CONSTRUCTION_NOT_VALIDATED`

## Decision

`IMPLEMENT_INDEPENDENT_SUPPORT_SOURCE_BEFORE_PRODUCT_APPROVAL`

No Phase 27.4 gating and no threshold revision is approved. See `phase27_3s_underpowered_preregistration_amendment.md` before any expanded capture.

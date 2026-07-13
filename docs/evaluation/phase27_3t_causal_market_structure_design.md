# Phase 27.3T — Causal Market-Structure Level Design

Status: `DESIGN_FROZEN_BEFORE_IMPLEMENTATION`

This design uses only OHLCV already available at the evaluation date. It changes neither strategy thresholds nor state-transition semantics.

## Candidate audit

1. **Rolling-window low/high** — causal when trailing-only, but rejected as the primary source because it changes mechanically with the window edge, provides no confirmation/touch provenance, and repeats the current rolling-high weakness.
2. **Confirmed swing pivots** — selected as the primitive. A pivot is unavailable until its fixed right-side confirmation observations exist, so its availability date is explicit and reproducible.
3. **Clustered multi-touch swing levels** — selected as the aggregation layer. It combines nearby confirmed pivots with bounded volatility-aware tolerance and ranks repeated structure above isolated pivots.
4. **Volume profile** — rejected for this phase. Daily OHLCV cannot reconstruct price-at-volume distribution without fabricating intraday allocation.
5. **MA/ATR dynamic levels** — rejected as a level source because it would relabel another moving statistic as structure. ATR is used only to bound clustering and break buffers.

## Frozen algorithm v1

- Minimum history: 30 observations; otherwise emit no market-structure levels.
- Source window: latest 120 observations at the requested as-of date.
- Pivot neighborhood: 3 observations left and 3 right.
- Confirmation delay: 3 market observations. A pivot at index `t` is available only from `t+3`.
- Pivot low/high: deterministic seven-observation extremum; the first occurrence wins ties.
- ATR period: trailing 14 observations, causal simple mean of true range.
- Minimum pivot prominence: 0.75 ATR at confirmation. Low prominence uses the smaller left/right shoulder excursion above the pivot; high prominence is symmetric below it.
- Cluster tolerance: `clamp(0.5 × ATR/pivot_price, 0.5%, 2.0%)`.
- Cluster membership: absolute price distance from the current deterministic cluster median divided by that median is within the frozen tolerance.
- Representative: median member-pivot price, rounded to four decimals.
- Touch count: number of confirmed pivots in the cluster.
- Prominence: maximum normalized shoulder excursion among member pivots, serialized to six decimals.
- Ranking: touch count descending, last confirmation descending, prominence descending, distance to current close ascending, then price.
- Maximum candidates: three active levels per side for strategy input; diagnostics may retain broken/stale clusters.
- Stale rule: last touch older than 60 market observations is `stale` and not actionable.
- Break buffer: fixed 1%.
- Broken support: two consecutive closes below `price × 0.99` after confirmation.
- Broken resistance: two consecutive closes above `price × 1.01` after confirmation.
- Side rule: actionable support must be below current close; actionable resistance must be above current close.
- Role reversal: disabled in v1. Broken resistance is not implicitly converted to support.

Each diagnostic level contains `price`, `kind`, `confirmed_at`, `first_seen_at`, `last_seen_at`, `touch_count`, `prominence`, `source_window`, and `status`.

## No-lookahead proof obligations

- The pure producer filters rows to `date <= as_of` before any calculation.
- Right-side pivot observations must also be dated on or before `as_of`.
- Prefix and longer-frame calls with the same `as_of` must serialize byte-identically.
- Appending future rows cannot revise an emitted historical result because clustering, ATR, status, and ranking are recomputed only from the frozen prefix.
- No centered rolling API, provider, DB, LLM, environment, filesystem, or wall-clock input is used.

## Integration contract

`TrendAnalysisResult` additively exposes `market_structure_support_levels` and `market_structure_resistance_levels`. The orchestrator extracts only active numeric prices. Engine precedence becomes causal market structure, then compatible legacy independent levels, then MA60/MA20 fallback. Existing `support_levels`, `resistance_levels`, and MA fields retain their historical meaning.

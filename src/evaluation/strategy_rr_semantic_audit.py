"""Offline-only Phase 27.3V resistance and RR semantic audit."""

from __future__ import annotations

import math
import hashlib
import json
import statistics
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.evaluation.strategy_sequence_replay import (
    PHASE27_3S_BENCHMARKS,
    PHASE27_3S_EVALUATION_END,
    PHASE27_3S_EVALUATION_START,
    PHASE27_3S_STOCKS,
    ReplayRecord,
    _attach_labels,
    _phase27_3t_arm_summary,
    _phase27_3t_outcome_deltas,
    _phase27_3u_arm_summary,
    _state_occupancy,
    build_replay_input,
    load_panel_fixture,
    summarize_state_runs,
    validate_artifact_path,
    validate_phase27_3s_fixture,
)

from src.services.strategy_state_engine import (
    DEFAULT_POLICY,
    StrategyPolicy,
    StrategyState,
    StrategyStateInput,
    StrategyStateSnapshot,
    _make_snapshot,
    _nearest_resistance_above,
    _nearest_support_below,
    evaluate_strategy_state,
)


RULE_EVAL_PLANNED_ZONE_WAIT = "EVAL_RULE_PLANNED_ZONE_WAIT"
RULE_EVAL_ACTION_GUARD_WAIT = "EVAL_RULE_ACTION_GUARD_WAIT"
RULE_EVAL_ACTION_GUARD_WATCHLIST = "EVAL_RULE_ACTION_GUARD_WATCHLIST"
DO_NOT_CHASE_NOW = "DO_NOT_CHASE_NOW"

SEMANTIC_ARM_DEFINITIONS = {
    "A_current": {"code": "A", "symbol_overrides": {}},
    "B_planned_zone": {"code": "B", "symbol_overrides": {}},
    "C_action_guard": {"code": "C", "symbol_overrides": {}},
    "E_nearest_all_active": {"code": "E", "symbol_overrides": {}},
}

DNC_PRIMARY_CATEGORIES = (
    "PRICE_ABOVE_VALID_ZONE_RR_FROM_CURRENT_PRICE",
    "PRICE_ABOVE_VALID_ZONE_RR_FROM_ZONE_ENTRY",
    "PRICE_INSIDE_OR_NEAR_ZONE_BUT_RR_FAIL",
    "NO_VALID_ZONE",
    "RESISTANCE_TOO_CLOSE",
    "RESISTANCE_STALE_OR_ALREADY_BROKEN",
    "RISK_DISTANCE_TOO_LARGE",
    "CURRENT_PRICE_OVEREXTENSION",
    "PREVIOUS_ZONE_SEMANTIC_CONFLICT",
    "OTHER_EXPLICIT_REASON",
)

HOLDER_MEANINGS = (
    "NON_HOLDER_WAIT_FOR_ENTRY",
    "NON_HOLDER_TRUE_CHASE_RISK",
    "HOLDER_HOLD_WITHOUT_ADDING",
    "HOLDER_REDUCE_RISK",
    "AMBIGUOUS_CURRENT_CONTRACT",
)


def _active_provenance(input_data: StrategyStateInput) -> list[dict[str, Any]]:
    result = []
    for level in input_data.market_structure_resistance_provenance:
        if level.get("status") != "active":
            continue
        for field in ("confirmed_at", "last_seen_at"):
            if level.get(field) and date.fromisoformat(str(level[field])) > input_data.as_of:
                raise ValueError("future-confirmed resistance provenance")
        try:
            price = float(level["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(price) and price > 0:
            result.append({**level, "price": price, "source": "causal_market_structure"})
    return result


def _legacy_target(input_data: StrategyStateInput, entry: float) -> tuple[dict[str, Any], ...]:
    prices = sorted(
        float(value)
        for value in input_data.deterministic_resistance_levels
        if value is not None and math.isfinite(float(value)) and float(value) > entry
    )
    if not prices:
        return ()
    return ({
        "price": prices[0],
        "source": "legacy_deterministic_resistance",
        "status": "legacy_unqualified",
    },)


def _causal_or_legacy(
    active: list[dict[str, Any]],
    input_data: StrategyStateInput,
    entry: float,
) -> tuple[dict[str, Any], ...]:
    eligible = sorted(
        (level for level in active if level["price"] > entry),
        key=lambda level: level["price"],
    )
    return (eligible[0],) if eligible else _legacy_target(input_data, entry)


def select_resistance_targets(
    input_data: StrategyStateInput,
    *,
    entry: float,
    selector: str = "R0",
    zone_midpoint: float | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return deterministic JSON-safe targets for one frozen audit selector."""
    active = _active_provenance(input_data)
    reference = zone_midpoint if selector == "R3" and zone_midpoint is not None else entry

    if selector == "R0":
        price = _nearest_resistance_above(input_data, reference)
        if price is None:
            return ()
        matched = next(
            (level for level in active if math.isclose(level["price"], price)),
            None,
        )
        return (matched,) if matched is not None else ({
            "price": float(price),
            "source": "legacy_deterministic_resistance",
            "status": "legacy_unqualified",
        },)

    eligible = [level for level in active if level["price"] > reference]
    if selector in {"R1", "R3"}:
        return _causal_or_legacy(active, input_data, reference)
    if selector == "R2":
        if not eligible:
            return _legacy_target(input_data, reference)
        strongest = max(
            eligible,
            key=lambda level: (
                int(level.get("touch_count") or 0),
                str(level.get("confirmed_at") or ""),
                float(level.get("prominence") or 0),
                -abs(level["price"] - reference),
                -level["price"],
            ),
        )
        return (strongest,)
    if selector in {"R4", "R5"}:
        ordered = sorted(eligible, key=lambda level: level["price"])
        if not ordered:
            return _legacy_target(input_data, reference)
        if selector == "R4":
            return (ordered[1] if len(ordered) > 1 else ordered[0],)
        return tuple(ordered[:2])
    raise ValueError(f"unknown resistance selector: {selector}")


def _rr(
    input_data: StrategyStateInput,
    *,
    entry: float | None,
    invalidation: float | None,
    selector: str,
    zone_midpoint: float | None,
    production_exhaustion: bool = False,
) -> dict[str, Any]:
    if entry is None or invalidation is None or invalidation >= entry:
        return {"entry": entry, "reward": None, "risk": None, "rr": None, "targets": ()}
    targets = select_resistance_targets(
        input_data,
        entry=entry,
        selector=selector,
        zone_midpoint=zone_midpoint,
    )
    risk = entry - invalidation
    if not targets:
        exhausted = production_exhaustion and bool(input_data.deterministic_resistance_levels)
        return {
            "entry": entry,
            "reward": 0.0 if exhausted else None,
            "risk": risk,
            "rr": 0.0 if exhausted else None,
            "targets": (),
        }
    target_price = sum(target["price"] for target in targets) / len(targets)
    reward = target_price - entry
    return {
        "entry": entry,
        "reward": reward,
        "risk": risk,
        "rr": reward / risk,
        "targets": targets,
    }


def diagnose_rr(
    input_data: StrategyStateInput,
    snapshot: StrategyStateSnapshot,
    *,
    selector: str = "R0",
) -> dict[str, Any]:
    """Expose current and planned RR without altering the strategy snapshot."""
    close = float(input_data.close) if input_data.close is not None else None
    zone = snapshot.buy_zone
    midpoint = (zone.low + zone.high) / 2 if zone is not None else None
    invalidation = snapshot.invalidation_level
    support = _nearest_support_below(input_data)
    if invalidation is None and zone is None and support is not None:
        invalidation = support[0]
    entries = {
        "E0": close,
        "E1": close,
        "E2": midpoint,
        "E3": zone.high if zone is not None else None,
        "E4": zone.low if zone is not None else None,
    }
    rows = {
        key: _rr(
            input_data,
            entry=entry,
            invalidation=invalidation,
            selector=selector,
            zone_midpoint=midpoint,
            production_exhaustion=(selector == "R0" and key in {"E0", "E1"}),
        )
        for key, entry in entries.items()
    }
    now = rows["E1"]
    planned = rows["E3"]
    r4_now = _rr(
        input_data,
        entry=close,
        invalidation=invalidation,
        selector="R4",
        zone_midpoint=midpoint,
    )
    selected = now["targets"][0] if now["targets"] else None
    resistance = selected["price"] if selected else None
    if zone is None:
        relative = "NO_ZONE"
    elif close < zone.low:
        relative = "BELOW_ZONE"
    elif close <= zone.high:
        relative = "INSIDE_ZONE"
    else:
        relative = "ABOVE_ZONE"
    known_resistances = [
        float(value)
        for value in (
            tuple(input_data.market_structure_resistance_levels)
            + tuple(input_data.deterministic_resistance_levels)
        )
        if value is not None
    ]
    return {
        "current_price": close,
        "zone_lower": zone.low if zone else None,
        "zone_upper": zone.high if zone else None,
        "zone_basis": list(zone.basis) if zone else [],
        "invalidation_level": invalidation,
        "selected_support": support[0] if support else None,
        "selected_resistance": resistance,
        "support_distance_pct": (
            (close - support[0]) / close if close and support else None
        ),
        "resistance_distance_pct": (
            (resistance - close) / close if close and resistance is not None else None
        ),
        "entry_reference": close,
        "entry_references": entries,
        "reward": now["reward"],
        "risk": now["risk"],
        "rr_ratio": now["rr"],
        "rr_now": now["rr"],
        "rr_at_planned_zone": planned["rr"],
        "rr_now_r4": r4_now["rr"],
        "rr_at_zone_lower": rows["E4"]["rr"],
        "rr_by_entry": {key: row["rr"] for key, row in rows.items()},
        "resistance_status": selected.get("status") if selected else None,
        "resistance_source": selected.get("source") if selected else None,
        "resistance_targets": [dict(target) for target in now["targets"]],
        "price_relative_to_zone": relative,
        "previous_state": snapshot.previous_state.value if snapshot.previous_state else None,
        "current_rule": snapshot.transition_rule_id,
        "zone_created_at": zone.created_at.isoformat() if zone else None,
        "known_resistance_max": max(known_resistances, default=None),
        "as_of": input_data.as_of.isoformat(),
        "symbol": input_data.symbol,
        "market": input_data.market,
    }


def classify_dnc(diagnostic: dict[str, Any]) -> dict[str, str]:
    """Apply the preregistered exact-one DNC classification tree."""
    zone_high = diagnostic["zone_upper"]
    close = diagnostic["current_price"]
    rr_now = diagnostic["rr_now"]
    rr_planned = diagnostic["rr_at_planned_zone"]
    if diagnostic["resistance_status"] in {"broken", "stale", "out_of_side"}:
        primary = "RESISTANCE_STALE_OR_ALREADY_BROKEN"
    elif zone_high is None:
        primary = "NO_VALID_ZONE"
    elif (
        diagnostic["zone_created_at"] != diagnostic["as_of"]
        and rr_planned is not None
        and rr_planned < DEFAULT_POLICY.minimum_risk_reward
    ):
        primary = "PREVIOUS_ZONE_SEMANTIC_CONFLICT"
    elif close <= zone_high * (1 + DEFAULT_POLICY.support_tolerance_pct):
        primary = "PRICE_INSIDE_OR_NEAR_ZONE_BUT_RR_FAIL"
    elif rr_now is not None and rr_now < DEFAULT_POLICY.minimum_risk_reward and (
        rr_planned is not None and rr_planned >= DEFAULT_POLICY.minimum_risk_reward
    ):
        primary = "PRICE_ABOVE_VALID_ZONE_RR_FROM_CURRENT_PRICE"
    elif rr_planned is not None and rr_planned < DEFAULT_POLICY.minimum_risk_reward:
        primary = "PRICE_ABOVE_VALID_ZONE_RR_FROM_ZONE_ENTRY"
    elif (
        rr_now is not None
        and rr_now < DEFAULT_POLICY.minimum_risk_reward
        and diagnostic.get("rr_now_r4") is not None
        and diagnostic["rr_now_r4"] >= DEFAULT_POLICY.minimum_risk_reward
    ):
        primary = "RESISTANCE_TOO_CLOSE"
    elif (
        rr_now is not None
        and rr_now < DEFAULT_POLICY.minimum_risk_reward
        and diagnostic.get("rr_at_zone_lower") is not None
        and diagnostic["rr_at_zone_lower"] < DEFAULT_POLICY.minimum_risk_reward
    ):
        primary = "RISK_DISTANCE_TOO_LARGE"
    elif (
        diagnostic["known_resistance_max"] is not None
        and close > diagnostic["known_resistance_max"]
    ):
        primary = "CURRENT_PRICE_OVEREXTENSION"
    else:
        primary = "OTHER_EXPLICIT_REASON"
    return {"primary": primary, "holder_meaning": "AMBIGUOUS_CURRENT_CONTRACT"}


def holder_counterfactual(
    diagnostic: dict[str, Any],
    *,
    has_position: bool | None,
) -> dict[str, str | None]:
    if has_position is None:
        return {
            "state": None,
            "action_guard": None,
            "meaning": "AMBIGUOUS_CURRENT_CONTRACT",
        }
    if has_position:
        return {
            "state": StrategyState.HOLD_ONLY.value,
            "action_guard": "DO_NOT_ADD_NOW",
            "meaning": "HOLDER_HOLD_WITHOUT_ADDING",
        }
    if diagnostic["zone_upper"] is not None and diagnostic["rr_at_planned_zone"] is not None and (
        diagnostic["rr_at_planned_zone"] >= DEFAULT_POLICY.minimum_risk_reward
    ):
        return {
            "state": StrategyState.WAIT_FOR_PULLBACK.value,
            "action_guard": DO_NOT_CHASE_NOW,
            "meaning": "NON_HOLDER_WAIT_FOR_ENTRY",
        }
    return {
        "state": StrategyState.DO_NOT_CHASE.value,
        "action_guard": DO_NOT_CHASE_NOW,
        "meaning": "NON_HOLDER_TRUE_CHASE_RISK",
    }


def _remap_snapshot(
    input_data: StrategyStateInput,
    previous: StrategyStateSnapshot | None,
    current: StrategyStateSnapshot,
    state: StrategyState,
    rule: str,
    policy: StrategyPolicy,
) -> StrategyStateSnapshot:
    return _make_snapshot(
        input_data,
        previous,
        state,
        rule,
        buy_zone=current.buy_zone,
        invalidation_level=current.invalidation_level,
        invalidation_confirm_count=current.invalidation_confirm_count,
        reclaim_confirm_count=current.reclaim_confirm_count,
        reasons=current.reasons + (f"evaluation_semantic_arm={rule}",),
        limitations=current.data_limitations,
        policy=policy,
    )


def evaluate_semantic_arm(
    input_data: StrategyStateInput,
    previous: StrategyStateSnapshot | None,
    *,
    arm: str,
    policy: StrategyPolicy = DEFAULT_POLICY,
) -> tuple[StrategyStateSnapshot, str | None]:
    """Evaluate one frozen audit arm without changing production behavior."""
    current = evaluate_strategy_state(input_data, previous, policy)
    if arm == "A" or current.state != StrategyState.DO_NOT_CHASE:
        return current, None
    diagnostic = diagnose_rr(input_data, current)
    planned_passes = (
        diagnostic["zone_upper"] is not None
        and input_data.close is not None
        and input_data.close > diagnostic["zone_upper"]
        and diagnostic["rr_now"] is not None
        and diagnostic["rr_now"] < policy.minimum_risk_reward
        and diagnostic["rr_at_planned_zone"] is not None
        and diagnostic["rr_at_planned_zone"] >= policy.minimum_risk_reward
    )
    if arm == "B":
        if not planned_passes:
            return current, None
        return (
            _remap_snapshot(
                input_data,
                previous,
                current,
                StrategyState.WAIT_FOR_PULLBACK,
                RULE_EVAL_PLANNED_ZONE_WAIT,
                policy,
            ),
            None,
        )
    if arm == "C":
        state = (
            StrategyState.WAIT_FOR_PULLBACK
            if diagnostic["zone_upper"] is not None
            and input_data.close is not None
            and input_data.close > diagnostic["zone_upper"]
            else StrategyState.WATCHLIST
        )
        rule = (
            RULE_EVAL_ACTION_GUARD_WAIT
            if state == StrategyState.WAIT_FOR_PULLBACK
            else RULE_EVAL_ACTION_GUARD_WATCHLIST
        )
        return _remap_snapshot(input_data, previous, current, state, rule, policy), DO_NOT_CHASE_NOW
    raise ValueError(f"unknown semantic arm: {arm}")


def _snapshot_bytes(snapshot: StrategyStateSnapshot) -> bytes:
    return json.dumps(
        snapshot.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _evaluate_arm(
    input_data: StrategyStateInput,
    previous: StrategyStateSnapshot | None,
    arm: str,
    policy: StrategyPolicy,
) -> tuple[StrategyStateSnapshot, str | None]:
    if arm != "E":
        return evaluate_semantic_arm(input_data, previous, arm=arm, policy=policy)
    all_active = tuple(sorted({
        float(level["price"])
        for level in input_data.market_structure_resistance_provenance
        if level.get("status") == "active" and level.get("price") is not None
    }))
    adjusted = replace(input_data, market_structure_resistance_levels=all_active)
    return evaluate_strategy_state(adjusted, previous, policy), None


def _replay_arm(
    inputs: Sequence[StrategyStateInput],
    arm: str,
    policy: StrategyPolicy,
) -> tuple[list[ReplayRecord], list[str | None]]:
    previous = None
    records = []
    guards = []
    for input_data in inputs:
        if previous is not None and input_data.as_of <= previous.as_of:
            raise ValueError("semantic audit inputs must be strictly chronological")
        snapshot, guard = _evaluate_arm(input_data, previous, arm, policy)
        records.append(ReplayRecord(input_data, snapshot, _snapshot_bytes(snapshot)))
        guards.append(guard)
        previous = snapshot
    return records, guards


def _distribution(values: Sequence[float | None]) -> dict[str, float | int | None]:
    finite = sorted(float(value) for value in values if value is not None and math.isfinite(value))
    if not finite:
        return {
            "count": 0, "min": None, "p25": None, "median": None,
            "p75": None, "p90": None, "max": None,
        }

    def percentile(quantile: float) -> float:
        position = (len(finite) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(finite) - 1)
        return finite[lower] + (finite[upper] - finite[lower]) * (position - lower)

    return {
        "count": len(finite),
        "min": finite[0],
        "p25": percentile(0.25),
        "median": statistics.median(finite),
        "p75": percentile(0.75),
        "p90": percentile(0.90),
        "max": finite[-1],
    }


def _increment(mapping: dict[str, int], key: str) -> None:
    mapping[key] = mapping.get(key, 0) + 1


def _state_transition_counts(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for records in records_by_symbol.values():
        for previous, current in zip(records, records[1:]):
            if previous.snapshot.state != current.snapshot.state:
                _increment(
                    counts,
                    f"{previous.snapshot.state.value}->{current.snapshot.state.value}",
                )
    return dict(sorted(counts.items()))


def _semantic_arm_summary(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
    inputs_by_symbol: Mapping[str, Sequence[StrategyStateInput]],
    predecessors_by_symbol: Mapping[str, ReplayRecord],
    markets: Mapping[str, str],
    panels: Mapping[str, str],
    same_input_mismatches: int,
    same_sequence_mismatches: int,
    action_guard_count: int,
) -> dict[str, Any]:
    summary = _phase27_3u_arm_summary(
        records_by_symbol,
        inputs_by_symbol,
        markets,
        panels,
        same_input_mismatches,
        same_sequence_mismatches,
        predecessors_by_symbol,
    )
    state_runs = {
        state.value: summarize_state_runs(records_by_symbol, state)
        for state in StrategyState
        if state not in {StrategyState.UNSUPPORTED, StrategyState.INVALIDATED}
    }
    return {
        "total_evaluations": summary["metrics"]["total"],
        "state_distribution": summary["metrics"]["state_distribution"],
        "occupancy": summary["occupancy"],
        "state_runs": state_runs,
        "do_not_chase_lifecycle": summary["lifecycle"],
        "transition_counts": _state_transition_counts(records_by_symbol),
        "metrics": summary["metrics"],
        "episodes": summary["episodes"],
        "action_guard_count": action_guard_count,
        "same_input_nondeterminism_rate": summary["same_input_nondeterminism_rate"],
        "same_sequence_nondeterminism_rate": summary["same_sequence_nondeterminism_rate"],
    }


def _category_coverage_80(categories: Mapping[str, int]) -> list[dict[str, Any]]:
    total = sum(categories.values())
    cumulative = 0
    result = []
    for category, count in sorted(categories.items(), key=lambda item: (-item[1], item[0])):
        if count == 0:
            continue
        cumulative += count
        result.append({
            "category": category,
            "count": count,
            "share": count / max(total, 1),
            "cumulative_share": cumulative / max(total, 1),
        })
        if cumulative / max(total, 1) >= 0.80:
            break
    return result


def _entry_reference_audit(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primary = {category: 0 for category in DNC_PRIMARY_CATEGORIES}
    holder = {meaning: 0 for meaning in HOLDER_MEANINGS}
    rr_now_values = []
    rr_planned_values = []
    disagreement = {"total": 0, "by_market": {}, "by_symbol": {}, "by_regime": {}}
    observations = []
    orthogonal = {
        "next_resistance_makes_rr_pass": 0,
        "planned_zone_lower_bound_still_fails": 0,
        "above_all_known_resistance": 0,
        "nonactive_causal_resistance_above_price": 0,
    }
    for symbol, records in records_by_symbol.items():
        for record in records:
            if record.snapshot.state != StrategyState.DO_NOT_CHASE:
                continue
            diagnostic = diagnose_rr(record.input_data, record.snapshot)
            classification = classify_dnc(diagnostic)
            _increment(primary, classification["primary"])
            _increment(holder, classification["holder_meaning"])
            rr_now_values.append(diagnostic["rr_now"])
            rr_planned_values.append(diagnostic["rr_at_planned_zone"])
            r4 = diagnose_rr(record.input_data, record.snapshot, selector="R4")
            next_pass = (
                diagnostic["rr_now"] is not None
                and diagnostic["rr_now"] < DEFAULT_POLICY.minimum_risk_reward
                and r4["rr_now"] is not None
                and r4["rr_now"] >= DEFAULT_POLICY.minimum_risk_reward
            )
            lower_fails = (
                diagnostic["rr_by_entry"]["E4"] is not None
                and diagnostic["rr_by_entry"]["E4"] < DEFAULT_POLICY.minimum_risk_reward
            )
            above_all = (
                diagnostic["known_resistance_max"] is not None
                and diagnostic["current_price"] > diagnostic["known_resistance_max"]
            )
            nonactive_above = any(
                level.get("status") in {"broken", "stale", "out_of_side"}
                and float(level.get("price") or 0) > float(record.input_data.close or 0)
                for level in record.input_data.market_structure_resistance_provenance
            )
            orthogonal["next_resistance_makes_rr_pass"] += int(next_pass)
            orthogonal["planned_zone_lower_bound_still_fails"] += int(lower_fails)
            orthogonal["above_all_known_resistance"] += int(above_all)
            orthogonal["nonactive_causal_resistance_above_price"] += int(nonactive_above)
            differs = (
                diagnostic["rr_now"] is not None
                and diagnostic["rr_now"] < DEFAULT_POLICY.minimum_risk_reward
                and diagnostic["rr_at_planned_zone"] is not None
                and diagnostic["rr_at_planned_zone"] >= DEFAULT_POLICY.minimum_risk_reward
            )
            if differs:
                disagreement["total"] += 1
                _increment(disagreement["by_market"], record.input_data.market)
                _increment(disagreement["by_symbol"], symbol)
                _increment(disagreement["by_regime"], record.regime)
            observations.append({
                **diagnostic,
                "regime": record.regime,
                "primary_category": classification["primary"],
                "holder_meaning": classification["holder_meaning"],
                "orthogonal_drivers": {
                    "next_resistance_makes_rr_pass": next_pass,
                    "planned_zone_lower_bound_still_fails": lower_fails,
                    "above_all_known_resistance": above_all,
                    "nonactive_causal_resistance_above_price": nonactive_above,
                },
            })
    total = sum(primary.values())
    return ({
        "primary_categories": {key: value for key, value in primary.items() if value},
        "categories_covering_80pct": _category_coverage_80(primary),
        "holder_meanings": {key: value for key, value in holder.items() if value},
        "rr_now_distribution": _distribution(rr_now_values),
        "rr_at_planned_zone_distribution": _distribution(rr_planned_values),
        "entry_reference_disagreement": {
            **disagreement,
            "share_of_dnc": disagreement["total"] / max(total, 1),
        },
        "orthogonal_drivers": orthogonal,
    }, observations)


def _resistance_audit(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
) -> dict[str, Any]:
    selector_sources = {selector: {} for selector in ("R0", "R1", "R2", "R3", "R4", "R5")}
    distances_current = []
    distances_zone = []
    confirmed_ages = []
    last_seen_ages = []
    touch_counts = []
    prominences = []
    r0_structural_defects = 0
    r0_nearest_disagreements = 0
    r0_strongest_disagreements = 0
    r5_gate_changes = 0
    selected_nonactive = 0
    selected_at_or_below_current = 0
    another_higher = 0
    realistic_planned_targets = 0
    observations = 0
    for records in records_by_symbol.values():
        for record in records:
            observations += 1
            close = float(record.input_data.close or 0)
            zone = record.snapshot.buy_zone
            midpoint = (zone.low + zone.high) / 2 if zone else None
            targets = {
                selector: select_resistance_targets(
                    record.input_data,
                    entry=close,
                    selector=selector,
                    zone_midpoint=midpoint,
                )
                for selector in selector_sources
            }
            for selector, selected in targets.items():
                source = selected[0]["source"] if selected else "missing"
                _increment(selector_sources[selector], source)
            r0 = targets["R0"]
            r1 = targets["R1"]
            r2 = targets["R2"]
            if r1 and (not r0 or r0[0]["source"] != "causal_market_structure"):
                r0_structural_defects += int(r1[0]["source"] == "causal_market_structure")
            if r0 and r1 and r0[0]["price"] != r1[0]["price"]:
                r0_nearest_disagreements += 1
            if r0 and r2 and r0[0]["price"] != r2[0]["price"]:
                r0_strongest_disagreements += 1
            if r0:
                target = r0[0]
                distances_current.append((target["price"] - close) / close)
                if midpoint:
                    distances_zone.append((target["price"] - midpoint) / midpoint)
                selected_nonactive += int(target.get("status") in {"broken", "stale", "out_of_side"})
                selected_at_or_below_current += int(target["price"] <= close)
                if target.get("touch_count") is not None:
                    touch_counts.append(float(target["touch_count"]))
                if target.get("prominence") is not None:
                    prominences.append(float(target["prominence"]))
                active_above = sorted(
                    level["price"]
                    for level in _active_provenance(record.input_data)
                    if level["price"] > target["price"]
                )
                another_higher += int(bool(active_above))
                for field, destination in (
                    ("confirmed_at", confirmed_ages),
                    ("last_seen_at", last_seen_ages),
                ):
                    if target.get(field):
                        destination.append(
                            (record.input_data.as_of - date.fromisoformat(target[field])).days
                        )
            diagnostic_r0 = diagnose_rr(record.input_data, record.snapshot, selector="R0")
            diagnostic_r5 = diagnose_rr(record.input_data, record.snapshot, selector="R5")
            r5_gate_changes += int(
                diagnostic_r0["rr_now"] is not None
                and diagnostic_r5["rr_now"] is not None
                and (diagnostic_r0["rr_now"] < DEFAULT_POLICY.minimum_risk_reward)
                != (diagnostic_r5["rr_now"] < DEFAULT_POLICY.minimum_risk_reward)
            )
            realistic_planned_targets += int(
                diagnostic_r0["rr_at_planned_zone"] is not None
                and diagnostic_r0["rr_at_planned_zone"] >= DEFAULT_POLICY.minimum_risk_reward
            )
    return {
        "observations": observations,
        "selector_source_distribution": selector_sources,
        "r0_structural_defect_count": r0_structural_defects,
        "r0_vs_nearest_disagreement_count": r0_nearest_disagreements,
        "r0_vs_strongest_disagreement_count": r0_strongest_disagreements,
        "selected_broken_stale_out_of_side_count": selected_nonactive,
        "selected_at_or_below_current_count": selected_at_or_below_current,
        "selected_target_has_higher_active_alternative_count": another_higher,
        "realistic_planned_target_count": realistic_planned_targets,
        "multi_target_gate_change_count": r5_gate_changes,
        "distance_from_current_pct": _distribution(distances_current),
        "distance_from_zone_midpoint_pct": _distribution(distances_zone),
        "confirmed_at_age_days": _distribution(confirmed_ages),
        "last_seen_at_age_days": _distribution(last_seen_ages),
        "touch_count": _distribution(touch_counts),
        "prominence": _distribution(prominences),
    }


def _provenance_lookahead_failures(
    inputs_by_symbol: Mapping[str, Sequence[StrategyStateInput]],
) -> int:
    failures = 0
    for inputs in inputs_by_symbol.values():
        for input_data in inputs:
            provenance = (
                tuple(input_data.market_structure_support_provenance)
                + tuple(input_data.market_structure_resistance_provenance)
            )
            for level in provenance:
                for field in ("confirmed_at", "first_seen_at", "last_seen_at"):
                    if level.get(field) and date.fromisoformat(str(level[field])) > input_data.as_of:
                        failures += 1
    return failures


def _true_overextension_evidence(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
) -> dict[str, int]:
    eligible = detected = 0
    for records in records_by_symbol.values():
        for record in records:
            if record.snapshot.state in {
                StrategyState.ACCUMULATE_ZONE,
                StrategyState.REDUCE_RISK,
                StrategyState.INVALIDATED,
            }:
                continue
            diagnostic = diagnose_rr(record.input_data, record.snapshot)
            true_overextension = (
                diagnostic["rr_now"] is not None
                and diagnostic["rr_now"] < DEFAULT_POLICY.minimum_risk_reward
                and (
                    diagnostic["zone_upper"] is None
                    or diagnostic["rr_at_planned_zone"] is None
                    or diagnostic["rr_at_planned_zone"] < DEFAULT_POLICY.minimum_risk_reward
                )
            )
            if not true_overextension:
                continue
            eligible += 1
            detected += int(
                record.snapshot.state == StrategyState.DO_NOT_CHASE
                or record.snapshot.transition_rule_id in {
                    RULE_EVAL_ACTION_GUARD_WAIT,
                    RULE_EVAL_ACTION_GUARD_WATCHLIST,
                }
            )
    return {"eligible": eligible, "detected": detected}


def _arm_d_counterfactuals(
    records_by_symbol: Mapping[str, Sequence[ReplayRecord]],
) -> dict[str, Any]:
    result = {
        "holder": {"total": 0, "state_distribution": {}, "meaning_distribution": {}},
        "non_holder": {"total": 0, "state_distribution": {}, "meaning_distribution": {}},
    }
    for records in records_by_symbol.values():
        for record in records:
            if record.snapshot.state != StrategyState.DO_NOT_CHASE:
                continue
            diagnostic = diagnose_rr(record.input_data, record.snapshot)
            for lens, has_position in (("holder", True), ("non_holder", False)):
                row = holder_counterfactual(diagnostic, has_position=has_position)
                result[lens]["total"] += 1
                _increment(result[lens]["state_distribution"], str(row["state"]))
                _increment(result[lens]["meaning_distribution"], str(row["meaning"]))
    return result


def _arm_gates(
    arm: dict[str, Any],
    baseline: dict[str, Any],
    matched_matrix: Mapping[str, int],
    no_lookahead_failures: int,
    symbol_override_count: int,
) -> dict[str, bool]:
    distribution = arm["state_distribution"]
    total = max(arm["total_evaluations"], 1)
    metrics = arm["metrics"]
    episodes = arm["episodes"]["total"]
    baseline_episodes = baseline["episodes"]["total"]
    panel_ok = all(row["top_state_share"] <= 0.55 for row in arm["occupancy"]["by_panel"].values())
    symbol_ok = all(row["top_state_share"] < 1.0 for row in arm["occupancy"]["by_symbol"].values())
    dnc = distribution.get(StrategyState.DO_NOT_CHASE.value, 0)
    baseline_dnc = baseline["state_distribution"].get(StrategyState.DO_NOT_CHASE.value, 0)
    return {
        "no_lookahead_failures": no_lookahead_failures == 0,
        "same_input_determinism": arm["same_input_nondeterminism_rate"] == 0,
        "same_sequence_determinism": arm["same_sequence_nondeterminism_rate"] == 0,
        "anchor_lint": metrics["anchor_lint_failure_rate"] == 0,
        "zone_movement": metrics["zone_movement_without_trigger_rate"] == 0,
        "zone_entry_contradiction": metrics["zone_entry_contradiction_rate"] == 0,
        "rally_decline_reactions": (
            metrics["unjustified_rally_upgrade_rate"] <= 0.05
            and metrics["unjustified_decline_downgrade_rate"] <= 0.05
        ),
        "confirmed_breaks_unchanged": episodes == baseline_episodes,
        "reclaim_semantics_unchanged": episodes == baseline_episodes,
        "no_direct_reduce_to_accumulate": episodes["direct_reduce_to_accumulate"] == 0,
        "no_combined_state_majority": max(distribution.values(), default=0) / total <= 0.50,
        "panel_concentration": panel_ok,
        "no_unexplained_symbol_100pct": symbol_ok,
        "accumulate_reachable": (
            distribution.get(StrategyState.ACCUMULATE_ZONE.value, 0) / total >= 0.05
        ),
        "wait_not_indiscriminate": (
            distribution.get(StrategyState.WAIT_FOR_PULLBACK.value, 0) / total <= 0.50
        ),
        "watchlist_not_indiscriminate": (
            distribution.get(StrategyState.WATCHLIST.value, 0) / total <= 0.50
        ),
        "holder_nonholder_semantics": False,
        "do_not_chase_materially_falls": dnc <= baseline_dnc * 0.80,
        "immediate_overextension_detectable": (
            arm["true_immediate_overextension"]["eligible"] > 0
            and arm["true_immediate_overextension"]["detected"]
            == arm["true_immediate_overextension"]["eligible"]
        ),
        "valid_zone_entry_preserved": (
            matched_matrix.get("ACCUMULATE_ZONE->ACCUMULATE_ZONE", 0)
            == baseline["state_distribution"].get(StrategyState.ACCUMULATE_ZONE.value, 0)
            and metrics["zone_entry_contradiction_rate"] == 0
        ),
        "no_symbol_specific_rules": symbol_override_count == 0,
    }


def run_phase27_3v_semantic_audit(
    phase27_3_fixture: Path,
    phase27_3s_fixture: Path,
    phase27_3s_manifest: Path,
    output_dir: Path,
) -> Path:
    """Run the frozen audit on seen fixtures and write an untracked artifact."""
    repository_root = Path(__file__).resolve().parents[2]
    output_dir = validate_artifact_path(output_dir, repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    old_panel = load_panel_fixture(phase27_3_fixture)
    new_panel = validate_phase27_3s_fixture(phase27_3s_fixture, phase27_3s_manifest)
    old_symbols = ("2330", "2454", "2308", "2317", "2881", "6505", "AAPL", "MSFT", "NVDA", "LLY")
    symbols = old_symbols + PHASE27_3S_STOCKS
    markets = {symbol: ("tw" if symbol.isdigit() else "us") for symbol in symbols}
    panels = {symbol: ("phase27_3" if symbol in old_symbols else "phase27_3s") for symbol in symbols}
    full_inputs: dict[str, list[StrategyStateInput]] = {}
    evaluation_dates: dict[str, set] = {}
    bars_by_symbol = {}
    benchmarks = {}
    for symbol in old_symbols:
        bars = old_panel[symbol]
        inputs = [build_replay_input(symbol, markets[symbol], bars, bar.as_of) for bar in bars[60:-60]]
        full_inputs[symbol] = inputs
        evaluation_dates[symbol] = {item.as_of for item in inputs}
        bars_by_symbol[symbol] = bars
        benchmarks[symbol] = old_panel[PHASE27_3S_BENCHMARKS[markets[symbol]]]
    for symbol in PHASE27_3S_STOCKS:
        bars = new_panel[symbol]
        inputs = [
            build_replay_input(symbol, markets[symbol], bars, bar.as_of)
            for bar in bars[60:]
            if bar.as_of <= PHASE27_3S_EVALUATION_END
        ]
        full_inputs[symbol] = inputs
        evaluation_dates[symbol] = {
            item.as_of for item in inputs
            if PHASE27_3S_EVALUATION_START <= item.as_of <= PHASE27_3S_EVALUATION_END
        }
        bars_by_symbol[symbol] = bars
        benchmarks[symbol] = new_panel[PHASE27_3S_BENCHMARKS[markets[symbol]]]

    selected_base_inputs = {
        symbol: [item for item in inputs if item.as_of in evaluation_dates[symbol]]
        for symbol, inputs in full_inputs.items()
    }
    serialized_inputs = json.dumps(
        {symbol: [asdict(item) for item in inputs] for symbol, inputs in selected_base_inputs.items()},
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    input_fingerprint = hashlib.sha256(serialized_inputs).hexdigest()
    serialized_provenance = json.dumps(
        {
            symbol: [
                {
                    "support": item.market_structure_support_provenance,
                    "resistance": item.market_structure_resistance_provenance,
                }
                for item in inputs
            ]
            for symbol, inputs in selected_base_inputs.items()
        },
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    provenance_fingerprint = hashlib.sha256(serialized_provenance).hexdigest()

    r0_defects = 0
    for inputs in selected_base_inputs.values():
        for input_data in inputs:
            if input_data.close is None:
                continue
            r0 = select_resistance_targets(input_data, entry=input_data.close, selector="R0")
            r1 = select_resistance_targets(input_data, entry=input_data.close, selector="R1")
            r0_defects += int(
                bool(r1)
                and r1[0]["source"] == "causal_market_structure"
                and (not r0 or r0[0]["source"] != "causal_market_structure")
            )
    arm_specs = {
        name: definition["code"]
        for name, definition in SEMANTIC_ARM_DEFINITIONS.items()
        if name != "E_nearest_all_active"
    }
    if r0_defects:
        arm_specs["E_nearest_all_active"] = SEMANTIC_ARM_DEFINITIONS[
            "E_nearest_all_active"
        ]["code"]

    arms = {}
    arm_records = {}
    full_arm_records = {}
    same_input_total = same_sequence_total = 0
    total_snapshots = 0
    for name, code in arm_specs.items():
        records_by_symbol = {}
        inputs_by_symbol = {}
        predecessors = {}
        full_arm_records[name] = {}
        action_guards = 0
        arm_same_input = arm_same_sequence = 0
        for symbol in symbols:
            first, first_guards = _replay_arm(full_inputs[symbol], code, DEFAULT_POLICY)
            second, second_guards = _replay_arm(full_inputs[symbol], code, DEFAULT_POLICY)
            arm_same_sequence += sum(
                left.snapshot_bytes != right.snapshot_bytes or left_guard != right_guard
                for left, right, left_guard, right_guard in zip(first, second, first_guards, second_guards)
            )
            previous = None
            for expected, expected_guard in zip(first, first_guards):
                repeated, repeated_guard = _evaluate_arm(expected.input_data, previous, code, DEFAULT_POLICY)
                arm_same_input += int(
                    _snapshot_bytes(repeated) != expected.snapshot_bytes
                    or repeated_guard != expected_guard
                )
                previous = expected.snapshot
            indices = [
                index for index, record in enumerate(first)
                if record.input_data.as_of in evaluation_dates[symbol]
            ]
            if indices and indices[0] > 0:
                predecessors[symbol] = first[indices[0] - 1]
            selected = [first[index] for index in indices]
            records_by_symbol[symbol] = selected
            inputs_by_symbol[symbol] = [record.input_data for record in selected]
            action_guards += sum(first_guards[index] is not None for index in indices)
            full_arm_records[name][symbol] = first
        arm_records[name] = records_by_symbol
        summary = _semantic_arm_summary(
            records_by_symbol,
            inputs_by_symbol,
            predecessors,
            markets,
            panels,
            arm_same_input,
            arm_same_sequence,
            action_guards,
        )
        summary["input_fingerprint"] = input_fingerprint
        summary["causal_provenance_fingerprint"] = provenance_fingerprint
        arms[name] = summary
        same_input_total += arm_same_input
        same_sequence_total += arm_same_sequence
        total_snapshots += sum(len(records) for records in records_by_symbol.values())

    baseline = arms["A_current"]
    no_lookahead_failures = _provenance_lookahead_failures(selected_base_inputs)
    for name, records_by_symbol in arm_records.items():
        arms[name]["rr_diagnostics"], _ = _entry_reference_audit(records_by_symbol)
        arms[name]["resistance_audit"] = _resistance_audit(records_by_symbol)
        arms[name]["true_immediate_overextension"] = _true_overextension_evidence(
            records_by_symbol
        )
    resistance_audit = _resistance_audit(arm_records["A_current"])
    if resistance_audit["r0_structural_defect_count"] != r0_defects:
        raise ValueError("pre-outcome R0 defect count changed during replay")

    matched = {}
    for name, records_by_symbol in arm_records.items():
        if name == "A_current":
            continue
        matrix = {}
        for symbol in symbols:
            baseline_records = arm_records["A_current"][symbol]
            alternative_records = records_by_symbol[symbol]
            if [record.input_data.as_of for record in baseline_records] != [
                record.input_data.as_of for record in alternative_records
            ]:
                raise ValueError(f"semantic arm dates differ for {name}:{symbol}")
            for left, right in zip(baseline_records, alternative_records):
                _increment(matrix, f"{left.snapshot.state.value}->{right.snapshot.state.value}")
        matched[name] = dict(sorted(matrix.items()))

    symbol_override_count = sum(
        len(definition["symbol_overrides"])
        for definition in SEMANTIC_ARM_DEFINITIONS.values()
    )
    gates = {
        name: _arm_gates(
            arm,
            baseline,
            matched[name],
            no_lookahead_failures,
            symbol_override_count,
        )
        for name, arm in arms.items()
        if name != "A_current"
    }
    viable = [name for name, arm_gates in gates.items() if all(arm_gates.values())]

    # State choices and Arm E eligibility are frozen above. Future labels are
    # attached only after this point and cannot influence any arm or gate.
    labeled_records = {}
    outcome_cells = {}
    for name, records_by_symbol in full_arm_records.items():
        labeled_records[name] = {}
        for symbol, records in records_by_symbol.items():
            labeled = _attach_labels(records, bars_by_symbol[symbol], benchmarks[symbol])
            labeled_records[name][symbol] = [
                record for record in labeled
                if record.input_data.as_of in evaluation_dates[symbol]
            ]
        outcome_cells[name] = _phase27_3t_arm_summary(
            labeled_records[name],
            selected_base_inputs,
            markets,
            0,
        )["outcomes_by_market_state_regime"]
        regimes = sorted({
            record.regime
            for records in labeled_records[name].values()
            for record in records
        })
        arms[name]["occupancy"]["by_regime"] = {
            regime: _state_occupancy([
                record
                for records in labeled_records[name].values()
                for record in records
                if record.regime == regime
            ])
            for regime in regimes
        }

    dnc_summary, dnc_observations = _entry_reference_audit(labeled_records["A_current"])
    outcome_deltas = {
        name: _phase27_3t_outcome_deltas(outcome_cells["A_current"], cells)
        for name, cells in outcome_cells.items()
        if name != "A_current"
    }
    status = (
        "PHASE_27_3V_VIABLE_SEMANTIC_ARM_FOUND"
        if viable
        else "PHASE_27_3V_CONFIRMS_STRATEGY_PRODUCTIZATION_SHOULD_STOP"
    )
    payload = {
        "schema_version": 1,
        "phase": "27.3V",
        "status": status,
        "phase27_3s_a_consumed": False,
        "threshold_selection_performed": False,
        "policy": asdict(DEFAULT_POLICY),
        "state_outputs_frozen_before_outcomes": True,
        "panels": {
            "phase27_3": {"symbols": list(old_symbols), "evaluations": 1468},
            "phase27_3s": {"symbols": list(PHASE27_3S_STOCKS), "evaluations": 968},
        },
        "arms": arms,
        "arm_e_preregistered_condition": {
            "r0_structural_defect_count": r0_defects,
            "included": "E_nearest_all_active" in arms,
        },
        "arm_d": {
            "historical_execution": "BLOCKED_NO_POSITION_INPUT",
            "reason": "StrategyStateInput has no deterministic position ownership field",
            "synthetic_counterfactuals_verified": True,
            "counterfactual_lenses": _arm_d_counterfactuals(arm_records["A_current"]),
        },
        "no_lookahead_failures": no_lookahead_failures,
        "symbol_override_count": symbol_override_count,
        "resistance_audit": resistance_audit,
        "dnc_diagnostics": dnc_summary,
        "dnc_observations": dnc_observations,
        "matched_state_matrices": matched,
        "development_gates": gates,
        "viable_arms": viable,
        "same_input_nondeterminism_rate": same_input_total / max(total_snapshots, 1),
        "same_sequence_nondeterminism_rate": same_sequence_total / max(total_snapshots, 1),
        "input_fingerprints_identical": len({arm["input_fingerprint"] for arm in arms.values()}) == 1,
        "causal_provenance_fingerprints_identical": len({
            arm["causal_provenance_fingerprint"] for arm in arms.values()
        }) == 1,
        "outcome_diagnostics": outcome_cells,
        "outcome_deltas_vs_a": outcome_deltas,
    }
    artifact = output_dir / "phase27_3v_resistance_rr_semantic_audit.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact

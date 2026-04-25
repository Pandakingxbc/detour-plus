"""
LangChain @tool wrappers for the Detour agent system.

Wraps raw physics functions from tools/ and state helpers from api/
into LangChain tools that agents can call via function-calling.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np
from langchain_core.tools import tool

from api.demo_data import load_demo_data
from api.state import get_catalog, get_cdm_inbox, get_satellite
from tools.constraints import check_constraints
from tools.maneuver import propose_maneuvers, simulate_maneuver
from tools.propagate import propagate_orbit
from tools.refine import refine_conjunction
from tools.risk import assess_conjunction_risk
from tools.screening import screen_conjunctions

# Multi-maneuver planning imports
from engine.maneuver.multi_impulse import plan_multi_maneuver_avoidance, MultiImpulseOptimizer, OptimizerConfig
from engine.maneuver.harmonic_analysis import (
    analyze_maneuver_harmonics,
    evaluate_maneuver_safety,
    detect_orbital_resonance,
    OrbitalElements,
)


# ─────────────────────────────────────────────────────────────────────────
# CDM / Catalog tools (Agent 0 — Scout)
# ─────────────────────────────────────────────────────────────────────────

@tool
def get_pending_cdms() -> str:
    """Get all pending (unprocessed) Conjunction Data Messages from the inbox."""
    inbox = get_cdm_inbox()
    pending = inbox.get_pending()
    return json.dumps(pending, indent=2, default=str)


@tool
def scan_conjunctions(lookahead_hours: float = 24.0, threshold_km: float = 50.0) -> str:
    """
    Screen the orbital catalog for close approaches to the active satellite.

    Args:
        lookahead_hours: how far ahead to scan (hours)
        threshold_km: only report conjunctions closer than this (km)
    """
    sat = get_satellite()
    catalog = get_catalog()
    debris_list = [obj.to_dict() for obj in catalog.list_debris()]

    if not debris_list:
        return json.dumps({"events": [], "message": "No debris in catalog. Use scan_demo_conjunctions or load data first."})

    events = screen_conjunctions(
        primary_pos=sat.position,
        primary_vel=sat.velocity,
        debris_list=debris_list,
        lookahead_sec=lookahead_hours * 3600,
        threshold_km=threshold_km,
    )
    return json.dumps({"total_screened": len(debris_list), "events_found": len(events), "events": events}, indent=2)


@tool
def scan_demo_conjunctions() -> str:
    """Load demo debris data and scan for conjunctions. Use this for testing/demo."""
    summary = load_demo_data()
    sat = get_satellite()
    catalog = get_catalog()
    debris_list = [obj.to_dict() for obj in catalog.list_debris()]

    events = screen_conjunctions(
        primary_pos=sat.position,
        primary_vel=sat.velocity,
        debris_list=debris_list,
        lookahead_sec=86400,
        threshold_km=50.0,
    )
    return json.dumps({
        "demo_loaded": True,
        "debris_count": len(debris_list),
        "events_found": len(events),
        "events": events,
        "satellite": {"norad_id": sat.norad_id, "name": sat.name},
    }, indent=2)


# ─────────────────────────────────────────────────────────────────────────
# Risk assessment tools (Agent 0 — Analyst)
# ─────────────────────────────────────────────────────────────────────────

@tool
def assess_risk(
    secondary_id: int,
    miss_distance_m: Optional[float] = None,
) -> str:
    """
    Compute detailed collision probability and risk for a conjunction event.

    Args:
        secondary_id: NORAD ID of the debris object
        miss_distance_m: known miss distance (optional, computed if not given)
    """
    sat = get_satellite()
    catalog = get_catalog()
    obj = catalog.get(secondary_id)
    if obj is None:
        return json.dumps({"error": f"Object {secondary_id} not found in catalog"})

    result = assess_conjunction_risk(
        primary_pos=sat.position,
        primary_vel=sat.velocity,
        secondary_pos=obj.position,
        secondary_vel=obj.velocity,
        miss_distance_m=miss_distance_m,
    )
    result["secondary_id"] = secondary_id
    result["secondary_name"] = obj.name
    return json.dumps(result, indent=2, default=str)


@tool
def refine_conjunction_hifi(secondary_id: int, window_sec: float = 3600.0) -> str:
    """
    Run Engine2 high-fidelity propagation (RK45 + J2/J3/J4 + drag) for TCA refinement.

    Args:
        secondary_id: NORAD ID of the debris object
        window_sec: propagation window in seconds
    """
    sat = get_satellite()
    catalog = get_catalog()
    obj = catalog.get(secondary_id)
    if obj is None:
        return json.dumps({"error": f"Object {secondary_id} not found in catalog"})

    result = refine_conjunction(
        primary_pos=sat.position,
        primary_vel=sat.velocity,
        secondary_pos=obj.position,
        secondary_vel=obj.velocity,
        window_sec=window_sec,
    )
    result["secondary_id"] = secondary_id
    return json.dumps(result, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────
# Maneuver planning tools (Agent 1 — Planner)
# ─────────────────────────────────────────────────────────────────────────

@tool
def propose_avoidance_maneuvers(
    secondary_id: int,
    tca_offset_sec: float,
    miss_distance_m: float,
    target_miss_km: float = 5.0,
) -> str:
    """
    Generate ranked avoidance maneuver candidates for a conjunction event.

    Args:
        secondary_id: NORAD ID of the debris object
        tca_offset_sec: time to closest approach (seconds)
        miss_distance_m: current predicted miss distance (meters)
        target_miss_km: desired post-maneuver miss distance (km)
    """
    sat = get_satellite()
    catalog = get_catalog()
    obj = catalog.get(secondary_id)
    if obj is None:
        return json.dumps({"error": f"Object {secondary_id} not found in catalog"})

    candidates = propose_maneuvers(
        primary_pos=sat.position,
        primary_vel=sat.velocity,
        secondary_pos=obj.position,
        secondary_vel=obj.velocity,
        tca_offset_sec=tca_offset_sec,
        miss_distance_m=miss_distance_m,
        target_miss_km=target_miss_km,
        mass_kg=sat.total_mass,
    )
    return json.dumps({"secondary_id": secondary_id, "candidates": candidates}, indent=2)


@tool
def simulate_maneuver_effect(
    secondary_id: int,
    delta_v: List[float],
    burn_time_sec: float,
) -> str:
    """
    Simulate a specific maneuver and compute before/after miss distance.

    Args:
        secondary_id: NORAD ID of the debris object
        delta_v: delta-v vector [x, y, z] in m/s (ECI)
        burn_time_sec: when to apply the burn (seconds from now)
    """
    sat = get_satellite()
    catalog = get_catalog()
    obj = catalog.get(secondary_id)
    if obj is None:
        return json.dumps({"error": f"Object {secondary_id} not found in catalog"})

    result = simulate_maneuver(
        primary_pos=sat.position,
        primary_vel=sat.velocity,
        secondary_pos=obj.position,
        secondary_vel=obj.velocity,
        delta_v=delta_v,
        burn_time_sec=burn_time_sec,
    )
    return json.dumps(result, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────
# Constraint checking tools (Agent 2 — Safety)
# ─────────────────────────────────────────────────────────────────────────

@tool
def get_satellite_status() -> str:
    """Get current satellite telemetry: fuel, power, position, delta-v budget."""
    sat = get_satellite()
    return json.dumps(sat.get_status(), indent=2, default=str)


@tool
def check_maneuver_constraints(
    delta_v: List[float],
    burn_time_sec: float = 0.0,
) -> str:
    """
    Validate a proposed maneuver against operational constraints.

    Args:
        delta_v: delta-v vector [x, y, z] in m/s
        burn_time_sec: when the burn occurs (seconds from now)
    """
    sat = get_satellite()
    result = check_constraints(
        delta_v=delta_v,
        primary_position=sat.position,
        primary_velocity=sat.velocity,
        mass_kg=sat.total_mass,
        isp_s=sat.config.isp_s,
        remaining_fuel_kg=sat.fuel_kg,
        burn_time_sec=burn_time_sec,
    )
    return json.dumps(result, indent=2, default=str)


@tool
def check_maneuver_feasibility(
    delta_v: List[float],
) -> str:
    """
    Quick feasibility check: can the satellite execute this maneuver?

    Args:
        delta_v: delta-v vector [x, y, z] in m/s
    """
    sat = get_satellite()
    dv_mag = float(np.linalg.norm(delta_v))
    ve = sat.config.isp_s * 9.80665
    fuel_needed = sat.total_mass * (1 - np.exp(-dv_mag / ve))
    feasible = fuel_needed <= sat.fuel_kg and dv_mag <= 50.0

    return json.dumps({
        "feasible": feasible,
        "delta_v_ms": round(dv_mag, 4),
        "fuel_required_kg": round(float(fuel_needed), 4),
        "fuel_available_kg": round(sat.fuel_kg, 4),
        "reason": "OK" if feasible else ("Insufficient fuel" if fuel_needed > sat.fuel_kg else "Exceeds max delta-v"),
    }, indent=2)


# ─────────────────────────────────────────────────────────────────────────
# Execution tools (Agent 3 — Ops)
# ─────────────────────────────────────────────────────────────────────────

@tool
def execute_maneuver_on_satellite(delta_v: List[float]) -> str:
    """
    Execute a maneuver by applying delta-v to the active satellite.

    Args:
        delta_v: delta-v vector [x, y, z] in m/s (ECI)
    """
    sat = get_satellite()
    dv = np.array(delta_v, dtype=float)

    # Apply maneuver (handles fuel, power, velocity update)
    result = sat.apply_maneuver(dv)
    return json.dumps(result, indent=2, default=str)


@tool
def propagate_satellite_orbit(duration_hours: float = 1.5) -> str:
    """
    Propagate the satellite orbit forward to verify trajectory.

    Args:
        duration_hours: how far ahead to propagate (hours)
    """
    sat = get_satellite()
    result = propagate_orbit(
        position=sat.position,
        velocity=sat.velocity,
        duration_sec=duration_hours * 3600,
        dt=60.0,
    )
    # Return summary, not full trajectory
    return json.dumps({
        "duration_hours": duration_hours,
        "total_points": result["total_points"],
        "start_altitude_km": result["start_altitude_km"],
        "end_altitude_km": result["end_altitude_km"],
        "altitude_range_km": [min(result["altitudes_km"]), max(result["altitudes_km"])],
    }, indent=2)


# ─────────────────────────────────────────────────────────────────────────
# Multi-Maneuver Strategic Planning Tools (Strategist Agent)
# ─────────────────────────────────────────────────────────────────────────

@tool
def plan_multi_maneuver_sequence(
    conjunction_ids: List[int],
    fuel_budget_kg: float = 10.0,
    target_miss_km: float = 5.0,
) -> str:
    """
    Plan optimal sequence of maneuvers for multiple conjunction threats.

    Args:
        conjunction_ids: List of NORAD IDs of debris objects to avoid
        fuel_budget_kg: Maximum fuel to use for all maneuvers
        target_miss_km: Desired miss distance for each conjunction (km)

    Returns:
        Optimized maneuver sequence with timing, delta-v, and fuel costs
    """
    sat = get_satellite()
    catalog = get_catalog()

    # Build conjunction list
    conjunctions = []
    for debris_id in conjunction_ids:
        obj = catalog.get(debris_id)
        if obj is None:
            continue

        # Get TCA and miss distance
        from engine.physics.cw_relative import cw_time_of_closest_approach
        tca, miss, _, _ = cw_time_of_closest_approach(
            sat.position, sat.velocity,
            obj.position, obj.velocity,
            horizon=86400,
        )

        conjunctions.append({
            "debris_id": debris_id,
            "debris_name": obj.name,
            "debris_pos": obj.position.tolist(),
            "debris_vel": obj.velocity.tolist(),
            "tca_sec": tca,
            "miss_distance_m": miss,
            "collision_prob": 0.01 if miss < 1000 else 0.001,
        })

    if not conjunctions:
        return json.dumps({"error": "No valid conjunctions found for given IDs"})

    # Plan sequence
    result = plan_multi_maneuver_avoidance(
        sat_pos=sat.position.tolist(),
        sat_vel=sat.velocity.tolist(),
        conjunctions=conjunctions,
        fuel_available_kg=min(fuel_budget_kg, sat.fuel_kg),
        config={"target_miss_km": target_miss_km},
    )

    return json.dumps(result, indent=2, default=str)


@tool
def check_secondary_conjunctions(
    delta_v: List[float],
    burn_time_sec: float = 0.0,
    horizon_hours: float = 48.0,
) -> str:
    """
    Check if a maneuver creates new (secondary) conjunctions with catalog objects.

    Args:
        delta_v: Proposed delta-v vector [x, y, z] in m/s
        burn_time_sec: When the burn occurs (seconds from now)
        horizon_hours: How far ahead to check for new conjunctions

    Returns:
        List of any new conjunctions that would be created
    """
    sat = get_satellite()
    catalog = get_catalog()
    debris_list = [obj.to_dict() for obj in catalog.list_debris()]

    # Compute post-maneuver state
    dv = np.array(delta_v, dtype=float)
    post_vel = sat.velocity + dv

    from engine.maneuver.multi_impulse import MultiImpulseOptimizer, ManeuverSequence, ManeuverCandidate

    optimizer = MultiImpulseOptimizer()

    # Create dummy sequence
    maneuver = ManeuverCandidate(
        burn_time_sec=burn_time_sec,
        delta_v=dv,
        fuel_kg=0,
        target_conjunction_idx=0,
    )
    sequence = ManeuverSequence(
        maneuvers=[maneuver],
        total_fuel_kg=0,
        total_delta_v_ms=float(np.linalg.norm(dv)),
        post_miss_distances={},
        feasible=True,
    )

    secondary = optimizer.check_secondary_conjunctions(
        sat.position, sat.velocity, sequence, debris_list, horizon_hours * 3600
    )

    return json.dumps({
        "secondary_conjunctions_found": len(secondary),
        "conjunctions": secondary,
        "safe": len(secondary) == 0,
        "recommendation": "Safe to execute" if len(secondary) == 0 else "Consider alternative maneuver",
    }, indent=2, default=str)


@tool
def analyze_orbital_harmonics(
    delta_v: List[float],
) -> str:
    """
    Analyze if a maneuver creates problematic orbital resonances.

    Checks for:
    - Orbital resonances with catalog debris (could cause recurring encounters)
    - Changes to orbital period that increase long-term collision risk
    - Harmonic return to original conjunction geometry

    Args:
        delta_v: Proposed delta-v vector [x, y, z] in m/s
    """
    sat = get_satellite()
    catalog = get_catalog()
    debris_list = [obj.to_dict() for obj in catalog.list_debris()]

    dv = np.array(delta_v, dtype=float)
    post_vel = sat.velocity + dv

    result = analyze_maneuver_harmonics(
        pre_maneuver_pos=sat.position,
        pre_maneuver_vel=sat.velocity,
        post_maneuver_vel=post_vel,
        debris_list=debris_list,
    )

    return json.dumps(result, indent=2, default=str)


@tool
def evaluate_maneuver_safety_score(
    delta_v: List[float],
    target_debris_id: int,
) -> str:
    """
    Comprehensive safety evaluation of a proposed maneuver.

    Combines:
    - Harmonic/resonance analysis
    - Secondary conjunction detection
    - Recurrence prediction
    - Overall safety score (0-100)

    Args:
        delta_v: Proposed delta-v vector [x, y, z] in m/s
        target_debris_id: NORAD ID of the primary threat being avoided
    """
    sat = get_satellite()
    catalog = get_catalog()
    debris_list = [obj.to_dict() for obj in catalog.list_debris()]

    dv = np.array(delta_v, dtype=float)

    result = evaluate_maneuver_safety(
        sat_pos=sat.position,
        sat_vel=sat.velocity,
        delta_v=dv,
        debris_catalog=debris_list,
        original_conjunction_id=target_debris_id,
    )

    return json.dumps(result, indent=2, default=str)


@tool
def get_multi_threat_summary() -> str:
    """
    Get summary of all active threats for strategic planning.

    Returns threats sorted by TCA with risk levels for multi-maneuver planning.
    """
    sat = get_satellite()
    catalog = get_catalog()
    debris_list = [obj.to_dict() for obj in catalog.list_debris()]

    if not debris_list:
        return json.dumps({"threats": [], "message": "No debris in catalog"})

    threats = []
    for debris in debris_list:
        deb_pos = np.array(debris["position"], dtype=float)
        deb_vel = np.array(debris["velocity"], dtype=float)

        from engine.physics.cw_relative import cw_time_of_closest_approach
        try:
            tca, miss, _, _ = cw_time_of_closest_approach(
                sat.position, sat.velocity, deb_pos, deb_vel, horizon=172800  # 48 hours
            )

            if miss < 50000:  # 50 km threshold
                risk = "CRITICAL" if miss < 1000 else ("HIGH" if miss < 5000 else ("MEDIUM" if miss < 10000 else "LOW"))
                threats.append({
                    "debris_id": debris["norad_id"],
                    "debris_name": debris["name"],
                    "tca_hours": round(tca / 3600, 2),
                    "miss_distance_km": round(miss / 1000, 2),
                    "risk_level": risk,
                })
        except Exception:
            pass

    # Sort by TCA
    threats.sort(key=lambda x: x["tca_hours"])

    return json.dumps({
        "total_threats": len(threats),
        "critical_count": sum(1 for t in threats if t["risk_level"] == "CRITICAL"),
        "high_count": sum(1 for t in threats if t["risk_level"] == "HIGH"),
        "threats": threats[:10],  # Top 10
        "fuel_available_kg": round(sat.fuel_kg, 2),
        "max_delta_v_ms": round(sat.max_delta_v, 2),
    }, indent=2)


# ─────────────────────────────────────────────────────────────────────────
# Tool groups for each agent
# ─────────────────────────────────────────────────────────────────────────

SCOUT_TOOLS = [
    get_pending_cdms,
    scan_conjunctions,
    scan_demo_conjunctions,
]

ANALYST_TOOLS = [
    get_pending_cdms,
    scan_conjunctions,
    scan_demo_conjunctions,
    assess_risk,
    refine_conjunction_hifi,
]

PLANNER_TOOLS = [
    propose_avoidance_maneuvers,
    simulate_maneuver_effect,
    assess_risk,
]

SAFETY_TOOLS = [
    get_satellite_status,
    check_maneuver_constraints,
    check_maneuver_feasibility,
    propagate_satellite_orbit,
]

STRATEGIST_TOOLS = [
    plan_multi_maneuver_sequence,
    check_secondary_conjunctions,
    analyze_orbital_harmonics,
    evaluate_maneuver_safety_score,
    get_multi_threat_summary,
    get_satellite_status,
    propagate_satellite_orbit,
]

ALL_TOOLS = list({id(t): t for group in [SCOUT_TOOLS, ANALYST_TOOLS, PLANNER_TOOLS, SAFETY_TOOLS,
                                   STRATEGIST_TOOLS, [execute_maneuver_on_satellite, propagate_satellite_orbit]] for t in group}.values())

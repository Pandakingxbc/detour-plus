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

ALL_TOOLS = list({id(t): t for group in [SCOUT_TOOLS, ANALYST_TOOLS, PLANNER_TOOLS, SAFETY_TOOLS,
                                   [execute_maneuver_on_satellite, propagate_satellite_orbit]] for t in group}.values())

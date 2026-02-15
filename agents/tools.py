"""
LangChain tool wrappers around the Detour physics/simulation tools.

These wrap the deterministic Python functions in tools/ so the LLM
*never hallucinates physics* — it calls tools that compute real numbers.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

logger = logging.getLogger("detour.agents.tools")


# ─────────────────────────────────────────────────────────────────────────
# 1. SCAN / SCREENING
# ─────────────────────────────────────────────────────────────────────────
@tool
def scan_conjunctions(
    primary_norad_id: Annotated[int, "NORAD ID of the satellite to protect"],
    lookahead_sec: Annotated[float, "Screening horizon in seconds (default 86400 = 24h)"] = 86400.0,
    threshold_km: Annotated[float, "Only report conjunctions closer than this (km)"] = 50.0,
    max_objects: Annotated[int, "Max catalog objects to screen"] = 200,
) -> str:
    """Scan the orbital catalog for conjunction threats against a satellite.
    Returns a list of conjunction events with miss distance, probability,
    relative velocity, and risk level. Use this first to identify threats."""
    from api.state import get_catalog
    from tools.screening import screen_conjunctions

    catalog = get_catalog()
    primary = catalog.get(primary_norad_id)
    if primary is None:
        return json.dumps({"error": f"Satellite {primary_norad_id} not found in catalog"})

    objects = catalog.list_all()
    events = screen_conjunctions(
        primary=primary,
        catalog_objects=objects,
        lookahead_sec=lookahead_sec,
        threshold_km=threshold_km,
        max_objects=max_objects,
    )

    # Summarize for LLM (don't send huge lists)
    summary = {
        "primary_id": primary_norad_id,
        "total_events": len(events),
        "high_risk_count": sum(1 for e in events if e["risk_level"] in ("critical", "high")),
        "events": events[:10],  # top 10 by risk
    }
    return json.dumps(summary, default=str)


@tool
def scan_demo_conjunctions(
    primary_norad_id: Annotated[int, "NORAD ID of the satellite to protect"],
) -> str:
    """Scan the pre-computed demo conjunction data for threats against a satellite.
    Use this when working with the demo dataset (not live catalog).
    Returns conjunction events from the demo_conjunctions.json file."""
    import os

    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "frontend2", "public", "demo_conjunctions.json",
    )
    # Also try frontend/public
    if not os.path.exists(data_path):
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "frontend", "public", "demo_conjunctions.json",
        )

    if not os.path.exists(data_path):
        return json.dumps({"error": "Demo data not found. Run: python -m tools.generate_demo_data"})

    with open(data_path) as f:
        data = json.load(f)

    events = [e for e in data["conjunction_events"] if e["primary_id"] == primary_norad_id]
    high_risk = [e for e in events if e["risk_level"] in ("critical", "high")]

    summary = {
        "primary_id": primary_norad_id,
        "total_events": len(events),
        "high_risk_count": len(high_risk),
        "events": (high_risk[:10] if high_risk else events[:10]),
    }
    return json.dumps(summary, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 2. RISK ASSESSMENT
# ─────────────────────────────────────────────────────────────────────────
@tool
def assess_risk(
    primary_norad_id: Annotated[int, "NORAD ID of the primary satellite"],
    secondary_norad_id: Annotated[int, "NORAD ID of the debris/secondary object"],
    tca_offset_sec: Annotated[float, "Time to closest approach from now (seconds)"] = 0.0,
    miss_distance_m: Annotated[Optional[float], "Known miss distance in meters"] = None,
    mc_samples: Annotated[int, "Monte Carlo samples (0 = skip MC)"] = 0,
) -> str:
    """Compute detailed risk assessment for a specific conjunction event.
    Uses Chan probability, Gaussian fallback, and optional Monte Carlo.
    Returns risk score, probability, level, and recommendation."""
    from api.state import get_catalog
    from tools.risk import estimate_risk

    catalog = get_catalog()
    primary = catalog.get(primary_norad_id)
    secondary = catalog.get(secondary_norad_id)

    if primary is None:
        return json.dumps({"error": f"Primary {primary_norad_id} not found"})
    if secondary is None:
        return json.dumps({"error": f"Secondary {secondary_norad_id} not found"})

    result = estimate_risk(
        primary=primary,
        secondary=secondary,
        tca_offset_sec=tca_offset_sec,
        miss_distance_m=miss_distance_m,
        mc_samples=mc_samples,
    )
    return json.dumps(result, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 3. TCA REFINEMENT
# ─────────────────────────────────────────────────────────────────────────
@tool
def refine_conjunction(
    primary_norad_id: Annotated[int, "NORAD ID of the primary satellite"],
    secondary_norad_id: Annotated[int, "NORAD ID of the debris/secondary object"],
    window_sec: Annotated[float, "Propagation window around TCA (seconds)"] = 3600.0,
) -> str:
    """Run high-fidelity Engine2 propagation to refine TCA, miss distance,
    and relative velocity for a conjunction event. Use this after screening
    to get more accurate numbers before planning maneuvers."""
    from api.state import get_catalog
    from tools.refine import refine_tca

    catalog = get_catalog()
    primary = catalog.get(primary_norad_id)
    secondary = catalog.get(secondary_norad_id)

    if primary is None:
        return json.dumps({"error": f"Primary {primary_norad_id} not found"})
    if secondary is None:
        return json.dumps({"error": f"Secondary {secondary_norad_id} not found"})

    result = refine_tca(primary=primary, secondary=secondary, window_sec=window_sec)
    return json.dumps(result, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 4. MANEUVER PLANNING
# ─────────────────────────────────────────────────────────────────────────
@tool
def propose_avoidance_maneuvers(
    primary_norad_id: Annotated[int, "NORAD ID of the satellite to maneuver"],
    secondary_norad_id: Annotated[int, "NORAD ID of the threat object"],
    tca_offset_sec: Annotated[float, "Time to closest approach (seconds)"],
    miss_distance_m: Annotated[float, "Current predicted miss distance (meters)"],
    target_miss_km: Annotated[float, "Desired post-maneuver miss distance (km)"] = 5.0,
) -> str:
    """Generate 3-5 ranked avoidance maneuver candidates using CW dynamics.
    Returns maneuver options sorted by fuel cost with delta-v vectors,
    burn times, fuel requirements, and predicted new miss distance."""
    from api.state import get_catalog
    from tools.maneuver import propose_maneuvers

    catalog = get_catalog()
    primary = catalog.get(primary_norad_id)
    secondary = catalog.get(secondary_norad_id)

    if primary is None:
        return json.dumps({"error": f"Primary {primary_norad_id} not found"})
    if secondary is None:
        return json.dumps({"error": f"Secondary {secondary_norad_id} not found"})

    candidates = propose_maneuvers(
        primary=primary,
        secondary=secondary,
        tca_offset_sec=tca_offset_sec,
        miss_distance_m=miss_distance_m,
        target_miss_km=target_miss_km,
    )
    return json.dumps({"candidates": candidates}, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 5. MANEUVER SIMULATION
# ─────────────────────────────────────────────────────────────────────────
@tool
def simulate_maneuver(
    primary_norad_id: Annotated[int, "NORAD ID of the satellite"],
    secondary_norad_id: Annotated[int, "NORAD ID of the threat"],
    delta_v: Annotated[List[float], "Delta-v vector [dvx, dvy, dvz] in m/s (ECI)"],
    burn_time_sec: Annotated[float, "When to apply burn (seconds from now)"],
) -> str:
    """Simulate a specific maneuver using Engine2 high-fidelity propagation.
    Compares before/after miss distance and checks for secondary conjunctions.
    Use this to verify a maneuver candidate before recommendation."""
    from api.state import get_catalog
    from tools.maneuver import simulate_maneuver as _simulate

    catalog = get_catalog()
    primary = catalog.get(primary_norad_id)
    secondary = catalog.get(secondary_norad_id)

    if primary is None:
        return json.dumps({"error": f"Primary {primary_norad_id} not found"})
    if secondary is None:
        return json.dumps({"error": f"Secondary {secondary_norad_id} not found"})

    result = _simulate(
        primary=primary,
        secondary=secondary,
        delta_v=delta_v,
        burn_time_sec=burn_time_sec,
    )
    return json.dumps(result, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 6. CONSTRAINT CHECKING
# ─────────────────────────────────────────────────────────────────────────
@tool
def check_maneuver_constraints(
    delta_v: Annotated[List[float], "Delta-v vector [dvx, dvy, dvz] in m/s"],
    primary_norad_id: Annotated[int, "NORAD ID of the satellite"],
    remaining_fuel_kg: Annotated[float, "Remaining fuel budget (kg)"] = 50.0,
    burn_time_sec: Annotated[float, "Proposed burn time (seconds from now)"] = 0.0,
    secondary_conjunction_count: Annotated[int, "Number of secondary conjunctions"] = 0,
) -> str:
    """Check operational constraints for a proposed maneuver:
    fuel budget, max delta-v, minimum orbit altitude, blackout windows,
    and secondary conjunction avoidance. Returns pass/fail for each."""
    from api.state import get_catalog
    from tools.constraints import check_constraints

    catalog = get_catalog()
    primary = catalog.get(primary_norad_id)

    if primary is None:
        return json.dumps({"error": f"Primary {primary_norad_id} not found"})

    result = check_constraints(
        delta_v=delta_v,
        primary_position=primary.position,
        primary_velocity=primary.velocity,
        remaining_fuel_kg=remaining_fuel_kg,
        burn_time_sec=burn_time_sec,
        secondary_conjunction_count=secondary_conjunction_count,
    )
    return json.dumps(result, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 7. ORBIT PROPAGATION
# ─────────────────────────────────────────────────────────────────────────
@tool
def propagate_orbit(
    norad_id: Annotated[int, "NORAD ID of the object to propagate"],
    duration_sec: Annotated[float, "Propagation duration (seconds)"] = 5400.0,
    dt: Annotated[float, "Timestep (seconds)"] = 60.0,
    fidelity: Annotated[str, "Propagation method: sgp4, rk4, or rk45"] = "sgp4",
) -> str:
    """Propagate an orbital object forward in time and return its trajectory.
    Returns times, positions, and velocities."""
    from api.state import get_catalog
    from tools.propagate import propagate_orbits

    catalog = get_catalog()
    obj = catalog.get(norad_id)
    if obj is None:
        return json.dumps({"error": f"Object {norad_id} not found"})

    results = propagate_orbits(
        objects=[obj],
        duration_sec=duration_sec,
        dt=dt,
        fidelity=fidelity,
    )

    if norad_id not in results:
        return json.dumps({"error": f"Propagation failed for {norad_id}"})

    traj = results[norad_id]
    # Truncate for LLM context (send summary + endpoints)
    n = len(traj["times"])
    summary = {
        "norad_id": norad_id,
        "total_points": n,
        "duration_sec": traj["times"][-1] if n > 0 else 0,
        "start_position": traj["positions"][0] if n > 0 else None,
        "end_position": traj["positions"][-1] if n > 0 else None,
        "start_velocity": traj["velocities"][0] if n > 0 else None,
        "end_velocity": traj["velocities"][-1] if n > 0 else None,
    }
    return json.dumps(summary, default=str)


# ─────────────────────────────────────────────────────────────────────────
# 8. SATELLITE STATUS & RESOURCE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────

# Singleton satellite instance for the active session
_active_satellite = None


def _get_or_create_satellite():
    """Get or create the active satellite instance."""
    global _active_satellite
    if _active_satellite is None:
        import numpy as np
        from engine.models.active_satellite import Satellite

        # ISS-like default (420 km altitude, ~7.66 km/s)
        EARTH_R = 6_378_137  # m
        ALT = 420_000  # m
        r = EARTH_R + ALT
        _active_satellite = Satellite(
            position=np.array([r * 0.8, r * 0.5, r * 0.3]),
            velocity=np.array([-5500.0, 6000.0, 2000.0]),
            name="DETOUR-SAT-1",
        )
    return _active_satellite


@tool
def get_satellite_status() -> str:
    """
    Get the operational status of the active satellite.

    Returns comprehensive telemetry including:
    - Position, velocity, altitude
    - Fuel level and percentage
    - Power/battery status
    - Available delta-v
    - Maneuver history count

    Use this BEFORE planning maneuvers to check resource availability.
    """
    sat = _get_or_create_satellite()
    status = sat.get_status()
    return json.dumps(status, default=str)


@tool
def check_maneuver_feasibility(
    delta_v_ms: Annotated[float, "Maneuver delta-v magnitude in m/s"],
    min_fuel_margin_kg: Annotated[float, "Minimum fuel to keep in reserve (kg)"] = 1.0,
) -> str:
    """
    Check if the satellite can execute a maneuver given current resources.

    Evaluates:
    - Fuel sufficiency (including reserve margin)
    - Power availability for thruster operation
    - Operational status

    Returns feasibility assessment with resource impact estimates.
    """
    sat = _get_or_create_satellite()
    import numpy as np

    feasible = sat.can_perform_maneuver(delta_v_ms, min_fuel_margin_kg)

    # Estimate fuel cost
    mass_ratio = np.exp(delta_v_ms / (sat.exhaust_velocity * 1000.0))
    fuel_needed = sat.total_mass * (1 - 1 / mass_ratio)

    result = {
        "feasible": feasible,
        "delta_v_requested_ms": delta_v_ms,
        "fuel_required_kg": round(fuel_needed, 3),
        "fuel_available_kg": round(sat.fuel, 3),
        "fuel_after_maneuver_kg": round(sat.fuel - fuel_needed, 3) if feasible else None,
        "fuel_percentage_after": round(
            (sat.fuel - fuel_needed) / (sat.total_mass - sat.dry_mass) * 100, 1
        ) if feasible else None,
        "power_ok": sat.power >= sat.maneuver_power_draw * (60.0 / 3600.0),
        "satellite_operational": sat.is_operational,
        "max_delta_v_available_ms": round(sat.max_delta_v, 2),
    }
    return json.dumps(result, default=str)


@tool
def execute_maneuver_on_satellite(
    delta_v_x: Annotated[float, "Delta-v X component in m/s (ECI)"],
    delta_v_y: Annotated[float, "Delta-v Y component in m/s (ECI)"],
    delta_v_z: Annotated[float, "Delta-v Z component in m/s (ECI)"],
) -> str:
    """
    Execute a maneuver on the active satellite, updating its state.

    This applies the delta-v, consumes fuel and power, and records
    the maneuver in the satellite's history. Only call this after
    the Safety agent has approved the maneuver.

    Returns updated satellite status after maneuver execution.
    """
    import numpy as np

    sat = _get_or_create_satellite()
    dv = np.array([delta_v_x, delta_v_y, delta_v_z])
    dv_mag = np.linalg.norm(dv)

    if not sat.can_perform_maneuver(dv_mag):
        return json.dumps({
            "executed": False,
            "reason": "Insufficient resources for maneuver",
            "delta_v_requested": dv_mag,
            "max_delta_v_available": sat.max_delta_v,
        })

    sat.apply_maneuver(dv)
    status = sat.get_status()
    status["executed"] = True
    status["delta_v_applied_ms"] = round(dv_mag, 4)
    return json.dumps(status, default=str)


# ─────────────────────────────────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────────────────────────────────

# Tools available to the Scout agent
SCOUT_TOOLS = [scan_conjunctions, scan_demo_conjunctions]

# Tools available to the Analyst agent
ANALYST_TOOLS = [assess_risk, refine_conjunction, propagate_orbit]

# Tools available to the Planner agent
PLANNER_TOOLS = [
    propose_avoidance_maneuvers,
    simulate_maneuver,
    get_satellite_status,
    check_maneuver_feasibility,
]

# Tools available to the Safety agent
SAFETY_TOOLS = [
    check_maneuver_constraints,
    simulate_maneuver,
    get_satellite_status,
    check_maneuver_feasibility,
    execute_maneuver_on_satellite,
]

# All tools (for single-agent mode)
ALL_TOOLS = [
    scan_conjunctions,
    scan_demo_conjunctions,
    assess_risk,
    refine_conjunction,
    propose_avoidance_maneuvers,
    simulate_maneuver,
    check_maneuver_constraints,
    propagate_orbit,
    get_satellite_status,
    check_maneuver_feasibility,
    execute_maneuver_on_satellite,
]

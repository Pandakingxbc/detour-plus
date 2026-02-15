"""
constraints.py — Validate maneuver candidates against operational constraints.

Checks fuel budget, max delta-v, minimum orbit altitude, blackout windows,
and secondary conjunction avoidance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from engine.config.settings import RE, GM

# Default constraint parameters
G0 = 9.80665
MIN_PERIGEE_ALT_M = 200_000.0  # 200 km minimum altitude
MAX_DV_PER_BURN_MPS = 50.0     # 50 m/s maximum single-burn delta-v


def check_constraints(
    delta_v: List[float],
    primary_position: np.ndarray,
    primary_velocity: np.ndarray,
    mass_kg: float = 465.0,
    isp_s: float = 220.0,
    remaining_fuel_kg: float = 45.0,
    max_dv_mps: float = MAX_DV_PER_BURN_MPS,
    min_altitude_m: float = MIN_PERIGEE_ALT_M,
    blackout_windows: Optional[List[Dict]] = None,
    burn_time_sec: float = 0.0,
    secondary_conjunction_count: int = 0,
) -> Dict[str, Any]:
    """
    Check operational constraints for a proposed maneuver.

    Returns per-constraint pass/fail and overall result.
    """
    dv = np.array(delta_v, dtype=float)
    dv_mag = float(np.linalg.norm(dv))

    constraints = {}

    # 1. Fuel budget (Tsiolkovsky)
    ve = isp_s * G0
    fuel_required = mass_kg * (1 - np.exp(-dv_mag / ve))
    constraints["fuel_budget"] = {
        "pass": bool(fuel_required <= remaining_fuel_kg),
        "fuel_required_kg": round(float(fuel_required), 4),
        "fuel_remaining_kg": round(float(remaining_fuel_kg), 4),
        "margin_kg": round(float(remaining_fuel_kg - fuel_required), 4),
    }

    # 2. Max delta-v per burn
    constraints["max_delta_v"] = {
        "pass": bool(dv_mag <= max_dv_mps),
        "delta_v_mps": round(float(dv_mag), 4),
        "limit_mps": float(max_dv_mps),
    }

    # 3. Minimum altitude check (post-maneuver perigee)
    post_vel = np.array(primary_velocity, dtype=float) + dv
    r = np.linalg.norm(primary_position)
    v = np.linalg.norm(post_vel)

    energy = 0.5 * v**2 - GM / r
    if energy < 0:
        a = -GM / (2 * energy)
        h_vec = np.cross(primary_position, post_vel)
        h = np.linalg.norm(h_vec)
        e = np.sqrt(max(0, 1 - (h**2) / (GM * a)))
        perigee_alt = a * (1 - e) - RE
    else:
        perigee_alt = 0.0  # hyperbolic — bad

    constraints["min_altitude"] = {
        "pass": bool(perigee_alt >= min_altitude_m),
        "perigee_alt_m": round(float(perigee_alt), 1),
        "perigee_alt_km": round(float(perigee_alt / 1000), 2),
        "limit_m": float(min_altitude_m),
    }

    # 4. Blackout windows
    blackout_ok = True
    if blackout_windows:
        for window in blackout_windows:
            start = window.get("start_sec", 0)
            end = window.get("end_sec", 0)
            if start <= burn_time_sec <= end:
                blackout_ok = False
                break

    constraints["blackout_window"] = {
        "pass": blackout_ok,
        "burn_time_sec": float(burn_time_sec),
    }

    # 5. No secondary conjunctions
    constraints["no_secondary_conjunctions"] = {
        "pass": bool(secondary_conjunction_count == 0),
        "count": secondary_conjunction_count,
    }

    all_pass = all(c["pass"] for c in constraints.values())

    return {
        "overall_pass": all_pass,
        "constraints": constraints,
        "summary": "ALL PASS ✓" if all_pass else "FAILED: " + ", ".join(
            k for k, v in constraints.items() if not v["pass"]
        ),
    }

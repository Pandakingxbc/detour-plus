"""
check_constraints() — validate maneuver candidates against operational constraints.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from engine.config.settings import RE

# Default constraint parameters
DEFAULT_MASS_KG = 500.0
DEFAULT_ISP_S = 220.0
G0 = 9.80665
MIN_PERIGEE_ALT_M = 200_000.0  # 200 km minimum altitude
MAX_DV_PER_BURN_MPS = 50.0     # 50 m/s maximum single-burn delta-v


def check_constraints(
    delta_v: List[float],
    primary_position: np.ndarray,
    primary_velocity: np.ndarray,
    mass_kg: float = DEFAULT_MASS_KG,
    isp_s: float = DEFAULT_ISP_S,
    remaining_fuel_kg: float = 50.0,
    max_dv_mps: float = MAX_DV_PER_BURN_MPS,
    min_altitude_m: float = MIN_PERIGEE_ALT_M,
    blackout_windows: Optional[List[Dict]] = None,
    burn_time_sec: float = 0.0,
    secondary_conjunction_count: int = 0,
) -> Dict:
    """
    Check operational constraints for a proposed maneuver.

    Args:
        delta_v: [dvx, dvy, dvz] in m/s
        primary_position: satellite ECI position (meters)
        primary_velocity: satellite ECI velocity (m/s)
        mass_kg: spacecraft mass (kg)
        isp_s: specific impulse (seconds)
        remaining_fuel_kg: remaining fuel budget (kg)
        max_dv_mps: maximum delta-v per burn (m/s)
        min_altitude_m: minimum acceptable perigee altitude (meters)
        blackout_windows: list of {start_sec, end_sec} blackout windows
        burn_time_sec: proposed burn time (seconds from epoch)
        secondary_conjunction_count: number of secondary conjunctions from simulation

    Returns:
        dict with per-constraint pass/fail and overall result
    """
    dv = np.array(delta_v, dtype=float)
    dv_mag = float(np.linalg.norm(dv))

    constraints = {}

    # 1. Fuel budget
    fuel_required = mass_kg * (1 - np.exp(-dv_mag / (isp_s * G0)))
    constraints["fuel_budget"] = {
        "pass": fuel_required <= remaining_fuel_kg,
        "fuel_required_kg": float(fuel_required),
        "fuel_remaining_kg": float(remaining_fuel_kg),
    }

    # 2. Max delta-v per burn
    constraints["max_delta_v"] = {
        "pass": dv_mag <= max_dv_mps,
        "delta_v_mps": float(dv_mag),
        "limit_mps": float(max_dv_mps),
    }

    # 3. Minimum altitude check (approximate post-maneuver perigee)
    post_vel = primary_velocity + dv
    r = np.linalg.norm(primary_position)
    v = np.linalg.norm(post_vel)

    # Vis-viva for semi-major axis
    from engine.config.settings import GM
    energy = 0.5 * v ** 2 - GM / r
    if energy < 0:
        a = -GM / (2 * energy)
        # Angular momentum
        h_vec = np.cross(primary_position, post_vel)
        h = np.linalg.norm(h_vec)
        # Eccentricity
        e = np.sqrt(max(0, 1 - (h ** 2) / (GM * a)))
        perigee_alt = a * (1 - e) - RE
    else:
        # Hyperbolic — bad
        perigee_alt = 0.0

    constraints["min_altitude"] = {
        "pass": perigee_alt >= min_altitude_m,
        "perigee_alt_m": float(perigee_alt),
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
        "pass": secondary_conjunction_count == 0,
        "count": secondary_conjunction_count,
    }

    # Overall
    all_pass = all(c["pass"] for c in constraints.values())

    return {
        "overall_pass": all_pass,
        "constraints": constraints,
    }

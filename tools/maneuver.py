"""
maneuver.py — Avoidance maneuver planning using CW (Hill) dynamics.

Generates ranked maneuver candidates (along-track, radial, cross-track)
and simulates their effect on miss distance.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engine.config.settings import GM, RE
from engine.physics.state import State
from engine.physics.forces import NewtonianGravity, J2Perturbation, CompositeForce
from engine.physics.solver import RK4Solver

logger = logging.getLogger("detour.tools.maneuver")

G0 = 9.80665  # m/s²


def _hill_frame(r_sat: np.ndarray, v_sat: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute Hill (LVLH) frame basis vectors from ECI state.

    Returns (radial, along-track, cross-track) unit vectors in ECI.
    """
    r_hat = r_sat / np.linalg.norm(r_sat)
    h = np.cross(r_sat, v_sat)
    h_hat = h / np.linalg.norm(h)
    s_hat = np.cross(h_hat, r_hat)  # along-track
    return r_hat, s_hat, h_hat


def propose_maneuvers(
    primary_pos: np.ndarray,
    primary_vel: np.ndarray,
    secondary_pos: np.ndarray,
    secondary_vel: np.ndarray,
    tca_offset_sec: float,
    miss_distance_m: float,
    target_miss_km: float = 5.0,
    mass_kg: float = 465.0,
    isp_s: float = 220.0,
) -> List[Dict[str, Any]]:
    """
    Generate ranked avoidance maneuver candidates.

    Produces maneuvers in along-track, radial, and cross-track directions,
    plus an optimal combined maneuver.

    Args:
        primary_pos/vel: satellite state (ECI)
        secondary_pos/vel: debris state (ECI)
        tca_offset_sec: time to closest approach (seconds)
        miss_distance_m: current predicted miss distance (m)
        target_miss_km: desired post-maneuver miss distance (km)
        mass_kg: satellite mass (kg)
        isp_s: specific impulse (s)

    Returns:
        Ranked list of maneuver candidates
    """
    target_miss_m = target_miss_km * 1000.0
    p_pos = np.array(primary_pos, dtype=float)
    p_vel = np.array(primary_vel, dtype=float)
    s_pos = np.array(secondary_pos, dtype=float)
    s_vel = np.array(secondary_vel, dtype=float)

    # Hill frame at satellite
    r_hat, s_hat, h_hat = _hill_frame(p_pos, p_vel)

    # Orbital parameters
    r = np.linalg.norm(p_pos)
    n = math.sqrt(GM / r**3)  # mean motion (rad/s)

    # Required displacement (m) to achieve target miss distance
    delta_needed = max(0, target_miss_m - miss_distance_m)

    # CW dynamics: along-track burn at time t_burn before TCA
    # produces along-track displacement ≈ 3 * n * dv * (tca - t_burn)² / 2
    # We try burns at different lead times
    candidates = []

    for burn_lead_frac in [0.25, 0.5, 0.75]:
        t_burn = tca_offset_sec * burn_lead_frac
        dt_to_tca = tca_offset_sec - t_burn

        if dt_to_tca < 60:  # need at least 60s lead time
            continue

        # Along-track maneuver (most fuel-efficient in LEO)
        # CW: along-track displacement ≈ 3 * n * dv_s * dt² / 2
        dv_along = delta_needed / max(1.5 * n * dt_to_tca**2, 1.0)
        dv_along = min(dv_along, 20.0)  # cap at 20 m/s
        dv_along = max(dv_along, 0.1)   # minimum useful burn

        dv_vec_along = dv_along * s_hat
        fuel_along = _fuel_for_dv(dv_along, mass_kg, isp_s)
        predicted_miss_along = miss_distance_m + 1.5 * n * dv_along * dt_to_tca**2

        candidates.append({
            "type": "along-track",
            "delta_v_vector": dv_vec_along.tolist(),
            "delta_v_magnitude_ms": round(dv_along, 4),
            "burn_time_sec": round(t_burn, 1),
            "lead_time_sec": round(dt_to_tca, 1),
            "fuel_cost_kg": round(fuel_along, 4),
            "predicted_miss_distance_m": round(predicted_miss_along, 1),
            "miss_improvement_m": round(predicted_miss_along - miss_distance_m, 1),
            "efficiency": "high",
        })

        # Radial maneuver (less efficient but different geometry)
        dv_radial = delta_needed / max(n * dt_to_tca**2, 1.0)
        dv_radial = min(dv_radial, 20.0)
        dv_radial = max(dv_radial, 0.1)

        dv_vec_radial = dv_radial * r_hat
        fuel_radial = _fuel_for_dv(dv_radial, mass_kg, isp_s)
        predicted_miss_radial = miss_distance_m + n * dv_radial * dt_to_tca**2

        candidates.append({
            "type": "radial",
            "delta_v_vector": dv_vec_radial.tolist(),
            "delta_v_magnitude_ms": round(dv_radial, 4),
            "burn_time_sec": round(t_burn, 1),
            "lead_time_sec": round(dt_to_tca, 1),
            "fuel_cost_kg": round(fuel_radial, 4),
            "predicted_miss_distance_m": round(predicted_miss_radial, 1),
            "miss_improvement_m": round(predicted_miss_radial - miss_distance_m, 1),
            "efficiency": "medium",
        })

        # Cross-track maneuver
        dv_cross = delta_needed / max(dt_to_tca * np.linalg.norm(p_vel), 1.0)
        dv_cross = min(dv_cross, 20.0)
        dv_cross = max(dv_cross, 0.1)

        dv_vec_cross = dv_cross * h_hat
        fuel_cross = _fuel_for_dv(dv_cross, mass_kg, isp_s)
        predicted_miss_cross = miss_distance_m + dv_cross * dt_to_tca

        candidates.append({
            "type": "cross-track",
            "delta_v_vector": dv_vec_cross.tolist(),
            "delta_v_magnitude_ms": round(dv_cross, 4),
            "burn_time_sec": round(t_burn, 1),
            "lead_time_sec": round(dt_to_tca, 1),
            "fuel_cost_kg": round(fuel_cross, 4),
            "predicted_miss_distance_m": round(predicted_miss_cross, 1),
            "miss_improvement_m": round(predicted_miss_cross - miss_distance_m, 1),
            "efficiency": "low",
        })

    # Sort by fuel cost (most efficient first)
    candidates.sort(key=lambda c: c["fuel_cost_kg"])

    # Add ranking
    for i, c in enumerate(candidates):
        c["rank"] = i + 1

    return candidates


def simulate_maneuver(
    primary_pos: np.ndarray,
    primary_vel: np.ndarray,
    secondary_pos: np.ndarray,
    secondary_vel: np.ndarray,
    delta_v: List[float],
    burn_time_sec: float,
    duration_sec: float = 86400.0,
    dt: float = 10.0,
) -> Dict[str, Any]:
    """
    Simulate a maneuver and compute before/after miss distance.

    Propagates both objects, applies delta-v at burn_time, then finds
    the new closest approach.

    Returns:
        Simulation results with before/after comparison
    """
    dv = np.array(delta_v, dtype=float)
    force = CompositeForce(NewtonianGravity(), J2Perturbation())
    steps = int(duration_sec / dt)

    # Before: propagate without maneuver
    sat_state = State(np.array(primary_pos), np.array(primary_vel))
    deb_state = State(np.array(secondary_pos), np.array(secondary_vel))
    solver_s = RK4Solver(force)
    solver_d = RK4Solver(force)

    min_dist_before = float("inf")
    tca_before = 0.0

    for i in range(steps):
        t = i * dt
        sat_state = solver_s.step(sat_state, dt)
        deb_state = solver_d.step(deb_state, dt)
        d = float(np.linalg.norm(sat_state.r - deb_state.r))
        if d < min_dist_before:
            min_dist_before = d
            tca_before = t + dt

    # After: propagate with maneuver at burn_time
    sat_state2 = State(np.array(primary_pos), np.array(primary_vel))
    deb_state2 = State(np.array(secondary_pos), np.array(secondary_vel))
    solver_s2 = RK4Solver(force)
    solver_d2 = RK4Solver(force)

    min_dist_after = float("inf")
    tca_after = 0.0
    burn_applied = False

    for i in range(steps):
        t = i * dt
        # Apply burn
        if not burn_applied and t >= burn_time_sec:
            sat_state2 = State(sat_state2.r, sat_state2.v + dv)
            burn_applied = True

        sat_state2 = solver_s2.step(sat_state2, dt)
        deb_state2 = solver_d2.step(deb_state2, dt)
        d = float(np.linalg.norm(sat_state2.r - deb_state2.r))
        if d < min_dist_after:
            min_dist_after = d
            tca_after = t + dt

    return {
        "before": {
            "miss_distance_m": round(min_dist_before, 1),
            "tca_sec": round(tca_before, 1),
        },
        "after": {
            "miss_distance_m": round(min_dist_after, 1),
            "tca_sec": round(tca_after, 1),
        },
        "improvement_m": round(min_dist_after - min_dist_before, 1),
        "improvement_percent": round(
            (min_dist_after - min_dist_before) / max(min_dist_before, 1) * 100, 1
        ),
        "delta_v_applied": dv.tolist(),
        "delta_v_magnitude_ms": round(float(np.linalg.norm(dv)), 4),
        "burn_time_sec": burn_time_sec,
        "effective": min_dist_after > min_dist_before,
    }


def _fuel_for_dv(dv_ms: float, mass_kg: float, isp_s: float) -> float:
    """Compute fuel required for delta-v via Tsiolkovsky."""
    ve = isp_s * G0
    mass_ratio = math.exp(dv_ms / ve)
    return mass_kg * (1 - 1 / mass_ratio)

"""
screening.py — Conjunction screening using RK4 propagation (fast).

Scans the orbital catalog for close approaches to a primary satellite.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np

from engine.config.settings import GM, RE
from engine.physics.state import State
from engine.physics.forces import NewtonianGravity, J2Perturbation, CompositeForce
from engine.physics.solver import RK4Solver

logger = logging.getLogger("detour.tools.screening")


def screen_conjunctions(
    primary_pos: np.ndarray,
    primary_vel: np.ndarray,
    debris_list: List[Dict[str, Any]],
    lookahead_sec: float = 86400.0,
    threshold_km: float = 50.0,
    dt: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Fast conjunction screening using RK4 propagation.

    Args:
        primary_pos: satellite ECI position (m)
        primary_vel: satellite ECI velocity (m/s)
        debris_list: list of dicts with 'position', 'velocity', 'norad_id', 'name'
        lookahead_sec: screening horizon (seconds)
        threshold_km: only report conjunctions closer than this (km)
        dt: propagation timestep (seconds)

    Returns:
        List of conjunction events sorted by miss distance (most dangerous first)
    """
    threshold_m = threshold_km * 1000.0
    steps = int(lookahead_sec / dt)

    force = CompositeForce(NewtonianGravity(), J2Perturbation())
    events = []

    # Pre-propagate satellite trajectory
    sat_state = State(primary_pos.copy(), primary_vel.copy())
    solver = RK4Solver(force)
    sat_trajectory = [sat_state]
    for i in range(steps):
        sat_state = solver.step(sat_state, dt)
        sat_trajectory.append(sat_state)

    # Screen each debris object
    for deb in debris_list:
        deb_pos = np.array(deb["position"], dtype=float)
        deb_vel = np.array(deb["velocity"], dtype=float)
        deb_state = State(deb_pos, deb_vel)
        deb_solver = RK4Solver(force)

        min_dist = float("inf")
        tca_step = 0
        rel_vel_at_tca = 0.0

        for i in range(steps + 1):
            rel = sat_trajectory[i].r - deb_state.r
            dist = float(np.linalg.norm(rel))

            if dist < min_dist:
                min_dist = dist
                tca_step = i
                rel_vel_at_tca = float(np.linalg.norm(sat_trajectory[i].v - deb_state.v))

            if i < steps:
                deb_state = deb_solver.step(deb_state, dt)

        if min_dist <= threshold_m:
            tca_sec = tca_step * dt
            risk_level = _classify_risk(min_dist, rel_vel_at_tca)

            events.append({
                "secondary_id": deb.get("norad_id", 0),
                "secondary_name": deb.get("name", "UNKNOWN"),
                "miss_distance_m": round(min_dist, 1),
                "relative_velocity_ms": round(rel_vel_at_tca, 1),
                "tca_offset_sec": round(tca_sec, 1),
                "risk_level": risk_level,
                "probability_estimate": _quick_probability(min_dist),
            })

    events.sort(key=lambda e: e["miss_distance_m"])
    return events


def _classify_risk(miss_m: float, rel_vel_ms: float) -> str:
    """Classify conjunction risk level."""
    if miss_m < 500:
        return "critical"
    elif miss_m < 2000:
        return "high"
    elif miss_m < 5000:
        return "medium"
    else:
        return "low"


def _quick_probability(miss_m: float) -> float:
    """Quick probability estimate based on miss distance."""
    sigma = 200.0
    return float(np.exp(-0.5 * (miss_m / sigma) ** 2))

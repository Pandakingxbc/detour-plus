"""
propagate.py — Orbit propagation utilities.

Supports RK4 and RK45 propagation with J2 perturbation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np

from engine.config.settings import GM, RE
from engine.physics.state import State
from engine.physics.forces import NewtonianGravity, J2Perturbation, CompositeForce
from engine.physics.solver import RK4Solver

logger = logging.getLogger("detour.tools.propagate")


def propagate_orbit(
    position: np.ndarray,
    velocity: np.ndarray,
    duration_sec: float = 5400.0,
    dt: float = 60.0,
) -> Dict[str, Any]:
    """
    Propagate an orbital object forward in time.

    Args:
        position: ECI position (m)
        velocity: ECI velocity (m/s)
        duration_sec: propagation duration (s)
        dt: timestep (s)

    Returns:
        Trajectory with times, positions, velocities
    """
    force = CompositeForce(NewtonianGravity(), J2Perturbation())
    solver = RK4Solver(force)
    state = State(np.array(position, dtype=float), np.array(velocity, dtype=float))

    steps = int(duration_sec / dt)
    times = [0.0]
    positions = [state.r.tolist()]
    velocities = [state.v.tolist()]
    altitudes = [float(np.linalg.norm(state.r) - RE) / 1000.0]

    for i in range(steps):
        t = i * dt
        state = solver.step(state, dt)
        times.append(round(t + dt, 1))
        positions.append(state.r.tolist())
        velocities.append(state.v.tolist())
        altitudes.append(round(float(np.linalg.norm(state.r) - RE) / 1000.0, 2))

    return {
        "total_points": len(times),
        "duration_sec": duration_sec,
        "dt_sec": dt,
        "times": times,
        "positions": positions,
        "velocities": velocities,
        "altitudes_km": altitudes,
        "start_position": positions[0],
        "end_position": positions[-1],
        "start_altitude_km": altitudes[0],
        "end_altitude_km": altitudes[-1],
    }

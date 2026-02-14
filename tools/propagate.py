"""
propagate_orbits() — propagate orbital objects forward in time.
Supports SGP4 (fast, many objects) and RK4/RK45 (accurate, few objects).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional

import numpy as np
from sgp4.api import Satrec, jday

from engine.data.data_sources import OrbitalObject
from engine.physics.state import State
from engine.physics.forces import NewtonianGravity, J2Perturbation, CompositeForce
from engine.physics.solver import RK4Solver
from engine.physics.solver_rk45 import RK45Solver
from engine.config.settings import GM


def propagate_orbits(
    objects: List[OrbitalObject],
    duration_sec: float = 5400.0,
    dt: float = 60.0,
    fidelity: Literal["sgp4", "rk4", "rk45"] = "sgp4",
) -> Dict[int, Dict]:
    """
    Propagate a list of OrbitalObjects forward in time.

    Args:
        objects: list of OrbitalObject with TLE data
        duration_sec: propagation duration in seconds
        dt: timestep in seconds
        fidelity: "sgp4" (fast), "rk4" (moderate), "rk45" (adaptive high-fidelity)

    Returns:
        dict mapping norad_id -> {times, positions, velocities}
        positions/velocities are lists of [x,y,z] in meters and m/s.
    """
    results: Dict[int, Dict] = {}

    if fidelity == "sgp4":
        results = _propagate_sgp4(objects, duration_sec, dt)
    elif fidelity == "rk4":
        results = _propagate_numerical(objects, duration_sec, dt, adaptive=False)
    elif fidelity == "rk45":
        results = _propagate_numerical(objects, duration_sec, dt, adaptive=True)
    else:
        raise ValueError(f"Unknown fidelity: {fidelity}")

    return results


def _propagate_sgp4(
    objects: List[OrbitalObject], duration_sec: float, dt: float
) -> Dict[int, Dict]:
    """SGP4 propagation using TLE lines (fast, suitable for many objects)."""
    results = {}
    num_steps = int(duration_sec / dt) + 1

    for obj in objects:
        if not obj.tle_line1 or not obj.tle_line2:
            continue

        try:
            sat = Satrec.twoline2rv(obj.tle_line1, obj.tle_line2)
        except Exception:
            continue

        base_epoch = obj.epoch or datetime.now(timezone.utc)
        times = []
        positions = []
        velocities = []

        for i in range(num_steps):
            t_offset = i * dt
            epoch = base_epoch + timedelta(seconds=t_offset)
            jd, fr = jday(
                epoch.year, epoch.month, epoch.day,
                epoch.hour, epoch.minute, epoch.second + epoch.microsecond / 1e6,
            )
            e, r, v = sat.sgp4(jd, fr)
            if e != 0:
                continue
            times.append(t_offset)
            positions.append([r[0] * 1000, r[1] * 1000, r[2] * 1000])
            velocities.append([v[0] * 1000, v[1] * 1000, v[2] * 1000])

        if times:
            results[obj.norad_id] = {
                "times": times,
                "positions": positions,
                "velocities": velocities,
            }

    return results


def _propagate_numerical(
    objects: List[OrbitalObject],
    duration_sec: float,
    dt: float,
    adaptive: bool = False,
) -> Dict[int, Dict]:
    """RK4 or RK45 numerical propagation from current state vectors."""
    force_model = CompositeForce(NewtonianGravity(), J2Perturbation())

    if adaptive:
        solver = RK45Solver(force_model, rtol=1e-9, atol=1e-12)
    else:
        solver = RK4Solver(force_model)

    results = {}
    num_steps = int(duration_sec / dt) + 1

    for obj in objects:
        state = State(obj.position.copy(), obj.velocity.copy())
        times = [0.0]
        positions = [obj.position.tolist()]
        velocities = [obj.velocity.tolist()]

        t = 0.0
        for _ in range(1, num_steps):
            step_dt = min(dt, duration_sec - t)
            if step_dt <= 0:
                break
            if adaptive:
                state = solver.step(state, step_dt, t)
            else:
                state = solver.step(state, step_dt)
            t += step_dt
            times.append(t)
            positions.append(state.r.tolist())
            velocities.append(state.v.tolist())

        results[obj.norad_id] = {
            "times": times,
            "positions": positions,
            "velocities": velocities,
        }

    return results

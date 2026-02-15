"""
refine.py — High-fidelity TCA refinement using Engine2 (RK45).

Runs the full physics engine for accurate miss distance and
relative velocity at closest approach.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np

from engine.physics.entity import Entity
from engine.core.engine2 import Engine2

logger = logging.getLogger("detour.tools.refine")


def refine_conjunction(
    primary_pos: np.ndarray,
    primary_vel: np.ndarray,
    secondary_pos: np.ndarray,
    secondary_vel: np.ndarray,
    window_sec: float = 3600.0,
) -> Dict[str, Any]:
    """
    Run Engine2 high-fidelity propagation for TCA refinement.

    Args:
        primary_pos/vel: satellite state (ECI)
        secondary_pos/vel: debris state (ECI)
        window_sec: propagation window (seconds)

    Returns:
        Refined conjunction parameters
    """
    sat = Entity(
        position=np.array(primary_pos, dtype=float),
        velocity=np.array(primary_vel, dtype=float),
    )
    deb = Entity(
        position=np.array(secondary_pos, dtype=float),
        velocity=np.array(secondary_vel, dtype=float),
    )

    engine = Engine2(dt=1.0, adaptive_threshold=5000.0, enable_drag=True)

    try:
        result = engine.run(
            satellite=sat,
            debris=deb,
            duration=window_sec,
            use_engine1_escalation=False,
        )

        return {
            "refined": True,
            "closest_time_sec": result.get("closest_time"),
            "miss_distance_m": round(result.get("miss_distance", float("inf")), 1),
            "relative_velocity_ms": round(result.get("relative_velocity", 0), 1) if result.get("relative_velocity") else None,
            "collision": result.get("collision", False),
            "conjunction": result.get("conjunction", False),
            "energy_drift_sat_pct": result.get("energy_drift_sat_percent"),
            "energy_drift_deb_pct": result.get("energy_drift_deb_percent"),
            "engine": "Engine2 (RK45 + J2/J3/J4 + drag)",
            "window_sec": window_sec,
        }
    except Exception as e:
        logger.error("Engine2 refinement failed: %s", e)
        return {
            "refined": False,
            "error": str(e),
            "engine": "Engine2",
        }

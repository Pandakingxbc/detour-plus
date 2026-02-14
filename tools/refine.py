"""
refine_tca() — high-fidelity TCA refinement using Engine2 (adaptive RK45).
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from engine.data.data_sources import OrbitalObject
from engine.data.tle_to_state import tle_to_state
from engine.data.tle_entity_factory import entity_from_tle
from engine.engine.engine2 import Engine2


def refine_tca(
    primary: OrbitalObject,
    secondary: OrbitalObject,
    window_sec: float = 3600.0,
    dt: float = 1.0,
    adaptive_threshold: float = 5000.0,
) -> Dict:
    """
    Run Engine2 high-fidelity propagation to refine TCA between two objects.

    Args:
        primary: primary orbital object
        secondary: secondary orbital object
        window_sec: propagation duration (seconds) around expected TCA
        dt: base timestep for Engine2
        adaptive_threshold: distance threshold for adaptive refinement (meters)

    Returns:
        dict with refined TCA, miss distance, relative velocity, collision/conjunction flags
    """
    # Build Entity objects
    sat_entity = entity_from_tle(primary.position, primary.velocity)
    deb_entity = entity_from_tle(secondary.position, secondary.velocity)

    # Run Engine2
    engine = Engine2(
        dt=dt,
        adaptive_threshold=adaptive_threshold,
        enable_drag=True,
        enable_srp=False,
        enable_third_body=True,
    )

    result = engine.run(
        satellite=sat_entity,
        debris=deb_entity,
        duration=window_sec,
        use_engine1_escalation=False,  # skip screening, we want full confirmation
    )

    return {
        "closest_time_sec": result.get("closest_time"),
        "miss_distance_m": result.get("miss_distance"),
        "relative_velocity_mps": result.get("relative_velocity"),
        "collision": result.get("collision", False),
        "conjunction": result.get("conjunction", False),
        "energy_drift_sat_pct": result.get("energy_drift_sat_percent"),
        "energy_drift_deb_pct": result.get("energy_drift_deb_percent"),
        "note": result.get("note", ""),
    }

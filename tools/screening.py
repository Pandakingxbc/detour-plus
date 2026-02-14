"""
screen_conjunctions() — fast conjunction screening using Engine1.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from engine.data.data_sources import OrbitalObject
from engine.engine.engine1 import Engine1
from engine.models.satellite import Satellite
from engine.models.debris import Debris
from engine.config.settings import ENGINE1_DT, STEPS, ESCALATION_THRESHOLD


def screen_conjunctions(
    primary: OrbitalObject,
    catalog_objects: List[OrbitalObject],
    lookahead_sec: float = 86400.0,
    threshold_km: float = 50.0,
    max_objects: int = 500,
) -> List[Dict]:
    """
    Screen a primary object against a list of catalog objects for conjunctions.

    Args:
        primary: the satellite to protect
        catalog_objects: list of other objects to screen against
        lookahead_sec: screening horizon in seconds
        threshold_km: only report conjunctions closer than this (km)
        max_objects: cap on number of objects to screen (for performance)

    Returns:
        list of ConjunctionEvent dicts sorted by risk (highest first)
    """
    engine = Engine1()

    # Build Satellite model from primary
    satellite = Satellite(
        position=primary.position,
        velocity=primary.velocity,
    )

    # Build Debris list from catalog objects (limited)
    debris_list = []
    norad_map = {}
    for i, obj in enumerate(catalog_objects[:max_objects]):
        if obj.norad_id == primary.norad_id:
            continue
        d = Debris(
            position=obj.position,
            velocity=obj.velocity,
            name=f"{obj.norad_id}",
        )
        debris_list.append(d)
        norad_map[i] = obj

    if not debris_list:
        return []

    # Compute steps from lookahead
    dt = ENGINE1_DT
    steps = max(1, int(lookahead_sec / dt))

    # Run Engine1 screening
    result = engine.run(satellite, debris_list, dt=dt, steps=steps)

    # Parse results into conjunction events
    screening_records = result.get("screening", [])
    threshold_m = threshold_km * 1000.0

    # Group by debris and find the minimum miss distance per debris
    debris_best: Dict[str, Dict] = {}
    for rec in screening_records:
        did = rec.get("debris_id", "")
        miss = rec.get("miss_distance")
        if miss is None:
            continue
        if did not in debris_best or (miss < debris_best[did].get("miss_distance", float("inf"))):
            debris_best[did] = rec

    events = []
    for did, rec in debris_best.items():
        miss_m = rec.get("miss_distance", float("inf"))
        if miss_m is None or miss_m > threshold_m:
            continue

        prob = rec.get("probability", 0.0)
        rel_vel = rec.get("relative_velocity", 0.0)
        tca = rec.get("tca", 0.0)

        # Determine risk level
        if prob > 1e-2 or miss_m < 500:
            risk_level = "critical"
        elif prob > 1e-4 or miss_m < 2000:
            risk_level = "high"
        elif prob > 1e-6 or miss_m < 10000:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Resolve NORAD ID from debris_id
        try:
            secondary_norad = int(did)
        except ValueError:
            secondary_norad = 0

        events.append({
            "event_id": str(uuid.uuid4())[:8],
            "primary_id": primary.norad_id,
            "secondary_id": secondary_norad,
            "secondary_name": did,
            "tca_epoch": (primary.epoch + __import__("datetime").timedelta(seconds=tca)).isoformat() if tca else None,
            "tca_offset_sec": float(tca) if tca else 0.0,
            "miss_distance_m": float(miss_m),
            "relative_velocity_mps": float(rel_vel) if rel_vel else 0.0,
            "probability": float(prob),
            "risk_level": risk_level,
            "escalate": rec.get("is_high_risk", False),
        })

    # Sort by probability descending (highest risk first)
    events.sort(key=lambda e: (-e["probability"], e["miss_distance_m"]))

    return events

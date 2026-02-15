"""
Load demo conjunction data into the catalog and CDM inbox.

Generates realistic orbital objects and conjunction events for the demo.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, List

import numpy as np

from engine.config.settings import GM, RE
from engine.physics.entity import Entity
from api.state import (
    OrbitalObject,
    get_catalog,
    get_cdm_inbox,
    get_satellite,
)


def _keplerian_to_eci(a, e, inc_rad, raan_rad, argp_rad, nu_rad):
    """Convert Keplerian elements to ECI position/velocity."""
    p = a * (1 - e**2)
    r_mag = p / (1 + e * math.cos(nu_rad))

    r_pqw = r_mag * np.array([math.cos(nu_rad), math.sin(nu_rad), 0.0])
    v_pqw = math.sqrt(GM / p) * np.array([-math.sin(nu_rad), e + math.cos(nu_rad), 0.0])

    cos_O, sin_O = math.cos(raan_rad), math.sin(raan_rad)
    cos_i, sin_i = math.cos(inc_rad), math.sin(inc_rad)
    cos_w, sin_w = math.cos(argp_rad), math.sin(argp_rad)

    R = np.array([
        [cos_O * cos_w - sin_O * sin_w * cos_i,
         -cos_O * sin_w - sin_O * cos_w * cos_i,
         sin_O * sin_i],
        [sin_O * cos_w + cos_O * sin_w * cos_i,
         -sin_O * sin_w + cos_O * cos_w * cos_i,
         -cos_O * sin_i],
        [sin_w * sin_i, cos_w * sin_i, cos_i],
    ])

    return R @ r_pqw, R @ v_pqw


# ── Demo debris definitions ─────────────────────────────────────────────
DEMO_DEBRIS = [
    {
        "norad_id": 90001,
        "name": "COSMOS 2251 DEB [A]",
        "alt_km": 418,
        "inc_deg": 51.8,
        "raan_deg": 30.5,
        "nu_deg": 5.0,
        "miss_m": 350,
        "tca_offset_sec": 7200,
        "risk": "critical",
    },
    {
        "norad_id": 90002,
        "name": "FENGYUN 1C DEB [B]",
        "alt_km": 422,
        "inc_deg": 51.4,
        "raan_deg": 29.8,
        "nu_deg": 12.0,
        "miss_m": 800,
        "tca_offset_sec": 14400,
        "risk": "high",
    },
    {
        "norad_id": 90003,
        "name": "IRIDIUM 33 DEB [C]",
        "alt_km": 425,
        "inc_deg": 52.0,
        "raan_deg": 31.2,
        "nu_deg": 20.0,
        "miss_m": 2500,
        "tca_offset_sec": 28800,
        "risk": "medium",
    },
    {
        "norad_id": 90004,
        "name": "SL-16 R/B DEB [D]",
        "alt_km": 415,
        "inc_deg": 51.2,
        "raan_deg": 28.5,
        "nu_deg": 355.0,
        "miss_m": 5000,
        "tca_offset_sec": 43200,
        "risk": "low",
    },
    {
        "norad_id": 90005,
        "name": "COSMOS 2251 DEB [E]",
        "alt_km": 419,
        "inc_deg": 51.7,
        "raan_deg": 30.2,
        "nu_deg": 2.0,
        "miss_m": 150,
        "tca_offset_sec": 3600,
        "risk": "critical",
    },
    {
        "norad_id": 90006,
        "name": "FENGYUN 1C DEB [F]",
        "alt_km": 430,
        "inc_deg": 53.0,
        "raan_deg": 32.0,
        "nu_deg": 45.0,
        "miss_m": 8000,
        "tca_offset_sec": 57600,
        "risk": "low",
    },
    {
        "norad_id": 90007,
        "name": "BREEZE-M DEB [G]",
        "alt_km": 421,
        "inc_deg": 51.5,
        "raan_deg": 30.0,
        "nu_deg": 8.0,
        "miss_m": 600,
        "tca_offset_sec": 10800,
        "risk": "high",
    },
    {
        "norad_id": 90008,
        "name": "DELTA 2 DEB [H]",
        "alt_km": 416,
        "inc_deg": 50.8,
        "raan_deg": 29.0,
        "nu_deg": 350.0,
        "miss_m": 1200,
        "tca_offset_sec": 21600,
        "risk": "medium",
    },
]


def load_demo_data() -> Dict[str, Any]:
    """
    Populate the catalog with demo debris objects and generate CDMs.

    Returns:
        Summary of loaded data
    """
    catalog = get_catalog()
    inbox = get_cdm_inbox()
    satellite = get_satellite()

    rng = np.random.default_rng(42)
    loaded_debris = []
    cdm_events = []

    for d in DEMO_DEBRIS:
        a = RE + d["alt_km"] * 1000
        e = 0.0002 + rng.uniform(0, 0.003)
        inc = math.radians(d["inc_deg"])
        raan = math.radians(d["raan_deg"])
        argp = math.radians(rng.uniform(0, 360))
        nu = math.radians(d["nu_deg"])

        pos, vel = _keplerian_to_eci(a, e, inc, raan, argp, nu)

        obj = OrbitalObject(
            norad_id=d["norad_id"],
            name=d["name"],
            position=pos,
            velocity=vel,
            object_type="debris",
            rcs_m2=rng.uniform(0.01, 2.0),
            mass_kg=rng.uniform(0.5, 50.0),
        )
        catalog.add(obj)
        loaded_debris.append(d["norad_id"])

        # Compute relative state for CDM
        rel_pos = pos - satellite.position
        rel_vel = vel - satellite.velocity
        miss_dist = float(np.linalg.norm(rel_pos))
        rel_speed = float(np.linalg.norm(rel_vel))

        # Generate CDM
        cdm = {
            "cdm_id": f"CDM-DEMO-{d['norad_id']}",
            "primary_id": satellite.norad_id,
            "primary_name": satellite.name,
            "secondary_id": d["norad_id"],
            "secondary_name": d["name"],
            "tca_offset_sec": d["tca_offset_sec"],
            "miss_distance_m": d["miss_m"],
            "relative_velocity_ms": round(rel_speed, 1),
            "risk_level": d["risk"],
            "collision_probability": _risk_to_prob(d["risk"], d["miss_m"]),
            "secondary_position": pos.tolist(),
            "secondary_velocity": vel.tolist(),
            "covariance_diagonal_m2": [
                rng.uniform(50, 500) ** 2,
                rng.uniform(50, 500) ** 2,
                rng.uniform(50, 500) ** 2,
            ],
            "processed": False,
            "timestamp": time.time(),
        }
        inbox.add(cdm)
        cdm_events.append(cdm)

    # Also add the satellite itself to the catalog
    sat_obj = OrbitalObject(
        norad_id=satellite.norad_id,
        name=satellite.name,
        position=satellite.position,
        velocity=satellite.velocity,
        object_type="satellite",
    )
    catalog.add(sat_obj)

    return {
        "debris_loaded": len(loaded_debris),
        "debris_ids": loaded_debris,
        "cdm_count": len(cdm_events),
        "satellite": satellite.name,
        "satellite_norad_id": satellite.norad_id,
    }


def _risk_to_prob(risk: str, miss_m: float) -> float:
    """Convert risk level + miss distance to approximate collision probability."""
    base = {
        "critical": 1e-3,
        "high": 1e-4,
        "medium": 1e-5,
        "low": 1e-6,
    }.get(risk, 1e-7)
    # Scale inversely with miss distance
    scale = max(0.1, 1000.0 / max(miss_m, 1.0))
    return min(1.0, base * scale)

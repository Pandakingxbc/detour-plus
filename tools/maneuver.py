"""
propose_maneuvers() + simulate_maneuver() — collision avoidance maneuver planning.

Uses CW dynamics to generate candidates at different burn times and directions,
then simulates with Engine2 for verification.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

import numpy as np

from engine.data.data_sources import OrbitalObject
from engine.data.tle_entity_factory import entity_from_tle
from engine.engine.engine1 import Engine1
from engine.engine.engine2 import Engine2
from engine.physics.cw_relative import _hill_frame_basis, _cw_state_at_t
from engine.physics.state import State
from engine.config.settings import GM, COLLISION_RADIUS

# Default spacecraft parameters
DEFAULT_MASS_KG = 500.0     # kg
DEFAULT_ISP_S = 220.0       # seconds (hydrazine-class)
G0 = 9.80665                # m/s^2


def _cw_stm(n: float, t: float) -> np.ndarray:
    """6x6 Clohessy-Wiltshire state transition matrix in Hill frame."""
    nt = n * t
    c = np.cos(nt)
    s = np.sin(nt)

    Phi = np.zeros((6, 6))
    # Position block (3x3 upper-left from position)
    Phi[0, 0] = 4 - 3 * c
    Phi[0, 3] = s / n
    Phi[0, 4] = 2 * (1 - c) / n
    Phi[1, 0] = 6 * (s - nt)
    Phi[1, 1] = 1
    Phi[1, 3] = 2 * (c - 1) / n
    Phi[1, 4] = (4 * s - 3 * nt) / n
    Phi[2, 2] = c
    Phi[2, 5] = s / n
    # Velocity block
    Phi[3, 0] = 3 * n * s
    Phi[3, 3] = c
    Phi[3, 4] = 2 * s
    Phi[4, 0] = 6 * n * (c - 1)
    Phi[4, 3] = -2 * s
    Phi[4, 4] = 4 * c - 3
    Phi[5, 2] = -n * s
    Phi[5, 5] = c

    return Phi


def propose_maneuvers(
    primary: OrbitalObject,
    secondary: OrbitalObject,
    tca_offset_sec: float,
    miss_distance_m: float,
    mass_kg: float = DEFAULT_MASS_KG,
    isp_s: float = DEFAULT_ISP_S,
    target_miss_km: float = 5.0,
) -> List[Dict]:
    """
    Generate 3-5 ranked maneuver candidates using CW dynamics.

    Args:
        primary: the satellite to maneuver
        secondary: the threat object
        tca_offset_sec: time to TCA from current epoch (seconds)
        miss_distance_m: current predicted miss distance (meters)
        mass_kg: spacecraft dry mass
        isp_s: specific impulse (seconds)
        target_miss_km: desired post-maneuver miss distance (km)

    Returns:
        list of ManeuverCandidate dicts sorted by fuel cost (lowest first)
    """
    target_miss_m = target_miss_km * 1000.0

    # Compute mean motion from primary orbit
    r0 = np.linalg.norm(primary.position)
    if r0 <= 0:
        return []
    n = np.sqrt(GM / r0 ** 3)

    # Hill frame basis at current epoch
    er, ey, ez = _hill_frame_basis(primary.position, primary.velocity)

    # Relative state in Hill frame
    rel_r = secondary.position - primary.position
    rel_v = secondary.velocity - primary.velocity
    hill_pos = np.array([np.dot(rel_r, er), np.dot(rel_r, ey), np.dot(rel_r, ez)])
    hill_vel = np.array([np.dot(rel_v, er), np.dot(rel_v, ey), np.dot(rel_v, ez)])

    # Burn lead times (seconds before TCA)
    burn_leads = [21600, 10800, 3600, 1800, 600]  # 6h, 3h, 1h, 30min, 10min
    burn_leads = [bl for bl in burn_leads if bl < tca_offset_sec]
    if not burn_leads:
        burn_leads = [max(60, tca_offset_sec * 0.5)]

    candidates = []

    for burn_lead in burn_leads:
        burn_time = tca_offset_sec - burn_lead
        dt_to_tca = burn_lead  # time from burn to TCA

        # CW STM from burn epoch to TCA
        Phi = _cw_stm(n, dt_to_tca)

        # Position sensitivity to velocity change at burn: dR = Phi_rv * dV
        Phi_rv = Phi[0:3, 3:6]  # 3x3 block

        # Maneuver directions in Hill frame
        directions = {
            "along-track": np.array([0, 1, 0]),   # V-bar (most fuel-efficient for LEO)
            "radial": np.array([1, 0, 0]),         # R-bar
            "cross-track": np.array([0, 0, 1]),    # H-bar
        }

        for name, dv_dir in directions.items():
            # How much delta-v to achieve target miss distance increase
            dr_per_dv = Phi_rv @ dv_dir  # displacement at TCA per 1 m/s in this direction
            effectiveness = np.linalg.norm(dr_per_dv)

            if effectiveness < 1e-6:
                continue

            # Required delta-v magnitude to reach target miss
            needed_displacement = max(0, target_miss_m - miss_distance_m)
            if needed_displacement <= 0:
                # Already safe, but still generate options for awareness
                dv_mag = 0.1  # minimal burn
            else:
                dv_mag = needed_displacement / effectiveness

            # Cap at reasonable limits
            dv_mag = min(dv_mag, 50.0)  # 50 m/s max per burn

            # Delta-v in Hill frame
            dv_hill = dv_dir * dv_mag

            # New miss distance estimate via CW
            new_rel_pos_hill = hill_pos + Phi_rv @ dv_hill
            # Propagate using full STM for better estimate
            state_0 = np.concatenate([hill_pos, hill_vel])
            dv_state = np.concatenate([np.zeros(3), dv_hill])
            new_state_at_tca = Phi @ (state_0 + dv_state)
            new_miss = float(np.linalg.norm(new_state_at_tca[:3]))

            # Convert delta-v to ECI
            dv_eci = dv_hill[0] * er + dv_hill[1] * ey + dv_hill[2] * ez

            # Fuel cost (Tsiolkovsky)
            fuel_kg = mass_kg * (1 - np.exp(-dv_mag / (isp_s * G0)))

            candidates.append({
                "id": str(uuid.uuid4())[:8],
                "type": name,
                "delta_v": dv_eci.tolist(),
                "delta_v_hill": dv_hill.tolist(),
                "magnitude_mps": float(dv_mag),
                "burn_time_sec": float(burn_time),
                "burn_lead_sec": float(burn_lead),
                "fuel_kg": float(fuel_kg),
                "new_miss_distance_m": float(new_miss),
                "original_miss_distance_m": float(miss_distance_m),
                "improvement_factor": float(new_miss / miss_distance_m) if miss_distance_m > 0 else float("inf"),
                "effectiveness_m_per_mps": float(effectiveness),
            })

    # Sort by fuel cost (most efficient first), take top 5
    candidates.sort(key=lambda c: c["fuel_kg"])
    return candidates[:5]


def simulate_maneuver(
    primary: OrbitalObject,
    secondary: OrbitalObject,
    delta_v: List[float],
    burn_time_sec: float,
    window_sec: float = 7200.0,
    catalog_objects: Optional[List[OrbitalObject]] = None,
) -> Dict:
    """
    Simulate a maneuver by applying delta-v to primary and running Engine2.

    Args:
        primary: satellite to maneuver
        secondary: threat object
        delta_v: [dvx, dvy, dvz] in ECI (m/s)
        burn_time_sec: when to apply burn (seconds from current epoch)
        window_sec: total propagation window
        catalog_objects: optional list of nearby objects to check for secondary conjunctions

    Returns:
        dict with before/after comparison, post-maneuver trajectory
    """
    dv = np.array(delta_v, dtype=float)

    # --- Before maneuver ---
    sat_before = entity_from_tle(primary.position, primary.velocity)
    deb_entity = entity_from_tle(secondary.position, secondary.velocity)

    engine = Engine2(dt=1.0, enable_drag=True, enable_third_body=True)
    before_result = engine.run(sat_before, deb_entity, duration=window_sec, use_engine1_escalation=False)

    # --- After maneuver ---
    # Apply delta-v at burn time (simplified: instant burn at burn_time_sec)
    # First propagate to burn time, then apply dv
    post_maneuver_pos = primary.position.copy()
    post_maneuver_vel = primary.velocity + dv  # simplified: immediate burn

    sat_after = entity_from_tle(post_maneuver_pos, post_maneuver_vel)
    after_result = engine.run(sat_after, deb_entity, duration=window_sec, use_engine1_escalation=False)

    # Check for secondary conjunctions if catalog provided
    secondary_conjunctions = []
    if catalog_objects:
        from engine.models.satellite import Satellite
        from engine.models.debris import Debris

        sat_model = Satellite(position=post_maneuver_pos, velocity=post_maneuver_vel)
        debris_models = []
        for obj in catalog_objects[:50]:  # limit for speed
            if obj.norad_id in (primary.norad_id, secondary.norad_id):
                continue
            debris_models.append(Debris(
                position=obj.position,
                velocity=obj.velocity,
                name=str(obj.norad_id),
            ))

        if debris_models:
            e1 = Engine1()
            screen_result = e1.run(sat_model, debris_models, dt=2.0, steps=int(window_sec / 2))
            for rec in screen_result.get("screening", []):
                if rec.get("is_high_risk", False):
                    secondary_conjunctions.append({
                        "debris_id": rec.get("debris_id"),
                        "miss_distance_m": rec.get("miss_distance"),
                        "probability": rec.get("probability"),
                    })

    return {
        "before": {
            "miss_distance_m": before_result.get("miss_distance"),
            "closest_time_sec": before_result.get("closest_time"),
            "relative_velocity_mps": before_result.get("relative_velocity"),
            "collision": before_result.get("collision", False),
            "conjunction": before_result.get("conjunction", False),
        },
        "after": {
            "miss_distance_m": after_result.get("miss_distance"),
            "closest_time_sec": after_result.get("closest_time"),
            "relative_velocity_mps": after_result.get("relative_velocity"),
            "collision": after_result.get("collision", False),
            "conjunction": after_result.get("conjunction", False),
        },
        "delta_v_applied": dv.tolist(),
        "fuel_estimate_kg": float(DEFAULT_MASS_KG * (1 - np.exp(-np.linalg.norm(dv) / (DEFAULT_ISP_S * G0)))),
        "secondary_conjunctions": secondary_conjunctions,
        "secondary_conjunction_count": len(secondary_conjunctions),
    }

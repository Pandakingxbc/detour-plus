"""
estimate_risk() — composite risk assessment using Chan probability,
Gaussian fallback, and optional Monte Carlo.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from engine.data.data_sources import OrbitalObject
from engine.data.tle_entity_factory import entity_from_tle
from engine.engine.engine2 import Engine2
from engine.physics.probability import collision_probability
from engine.config.settings import COLLISION_RADIUS, MC_DEFAULT_N


def estimate_risk(
    primary: OrbitalObject,
    secondary: OrbitalObject,
    tca_offset_sec: float = 0.0,
    miss_distance_m: Optional[float] = None,
    rel_pos: Optional[np.ndarray] = None,
    rel_vel: Optional[np.ndarray] = None,
    mc_samples: int = 0,
    window_sec: float = 3600.0,
) -> Dict:
    """
    Compute composite risk score for a conjunction event.

    Args:
        primary: primary OrbitalObject
        secondary: secondary OrbitalObject
        tca_offset_sec: TCA offset from current epoch (seconds)
        miss_distance_m: known miss distance (meters), or computed from states
        rel_pos: relative position at TCA (meters), optional
        rel_vel: relative velocity at TCA (m/s), optional
        mc_samples: if > 0, run Monte Carlo with this many samples
        window_sec: propagation window for MC (seconds)

    Returns:
        RiskAssessment dict with score, level, probabilities, recommendation
    """
    # Compute miss distance from states if not provided
    if miss_distance_m is None:
        diff = secondary.position - primary.position
        miss_distance_m = float(np.linalg.norm(diff))

    if rel_pos is None:
        rel_pos = secondary.position - primary.position
    if rel_vel is None:
        rel_vel = secondary.velocity - primary.velocity

    # Build relative covariance (assume diagonal 100m position uncertainty)
    cov_rel = np.eye(3) * (100.0 ** 2) * 2  # combined uncertainty

    # Chan / Gaussian probability
    try:
        chan_prob = float(
            collision_probability(
                miss_distance=miss_distance_m,
                cov_rel=cov_rel,
                rel_pos=rel_pos,
                rel_vel=rel_vel,
                collision_radius=COLLISION_RADIUS,
            )
        )
    except Exception:
        chan_prob = 0.0

    # Simple Gaussian fallback
    sigma = np.sqrt(np.trace(cov_rel) / 3.0)
    gaussian_prob = float(np.exp(-(miss_distance_m ** 2) / (2.0 * sigma ** 2)))

    # Monte Carlo if requested
    mc_results = None
    if mc_samples > 0:
        sat_entity = entity_from_tle(primary.position, primary.velocity)
        deb_entity = entity_from_tle(secondary.position, secondary.velocity)
        engine = Engine2(dt=1.0, enable_drag=True, enable_third_body=True)
        mc_results = engine.run_monte_carlo(
            sat_entity, deb_entity, duration=window_sec,
            N=mc_samples, use_engine1_escalation=False,
        )

    # Composite risk score (weighted blend)
    prob = max(chan_prob, gaussian_prob)
    if mc_results:
        mc_prob = mc_results.get("collision_probability", 0.0)
        prob = max(prob, mc_prob)

    # Distance-based scaling
    if miss_distance_m < 100:
        dist_factor = 1.0
    elif miss_distance_m < 1000:
        dist_factor = 0.8
    elif miss_distance_m < 5000:
        dist_factor = 0.5
    elif miss_distance_m < 20000:
        dist_factor = 0.2
    else:
        dist_factor = 0.05

    risk_score = float(np.clip(prob * 0.7 + dist_factor * 0.3, 0.0, 1.0))

    # Recommendation
    if risk_score > 0.5 or miss_distance_m < 200:
        level = "critical"
        recommendation = "emergency"
    elif risk_score > 0.1 or miss_distance_m < 1000:
        level = "high"
        recommendation = "plan_maneuver"
    elif risk_score > 0.01 or miss_distance_m < 5000:
        level = "medium"
        recommendation = "analyze"
    else:
        level = "low"
        recommendation = "monitor"


    return {
        "risk_score": risk_score,
        "level": level,
        "chan_probability": chan_prob,
        "gaussian_probability": gaussian_prob,
        "mc_results": mc_results,
        "miss_distance_m": miss_distance_m,
        "recommendation": recommendation,
    }

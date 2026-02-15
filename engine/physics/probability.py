
import numpy as np
from engine.config.settings import COLLISION_RADIUS, DEFAULT_POS_STD

def collision_probability_fallback(miss_distance, cov_rel=None):
    """
    Simple fallback scalar Gaussian (kept for speed/backwards compatibility).
    miss_distance: scalar (m)
    """
    miss = float(miss_distance)
    if miss <= COLLISION_RADIUS:
        return 1.0
    if cov_rel is not None:
        sigma = np.sqrt(np.trace(cov_rel) / 3.0)
        sigma = max(sigma, 1.0)
    else:
        sigma = DEFAULT_POS_STD
    return float(np.exp(-(miss ** 2) / (2.0 * sigma ** 2)))

def collision_probability(miss_distance, cov_rel=None, rel_pos=None, rel_vel=None, collision_radius=COLLISION_RADIUS):
    """
    Wrapper: try Chan-style accurate 2D integral if rel_pos & rel_vel provided and cov_rel available.
    Else fallback to simple Gaussian heuristic.
    NOTE: Chan-style code lives in src.physics.chan_probability (unchanged here).
    """
    # If inside collision radius -> certain collision
    if float(miss_distance) <= collision_radius:
        return 1.0

    # Try full Chan if available (import inside to avoid circular imports)
    try:
        if (cov_rel is not None) and (rel_pos is not None) and (rel_vel is not None):
            from engine.physics.chan_probability import chan_collision_probability
            p = chan_collision_probability(rel_pos, rel_vel, cov_rel, collision_radius)
            if np.isfinite(p) and 0.0 <= p <= 1.0:
                return float(p)
    except Exception:
        # fall through to fallback
        pass

    # fallback simple Gaussian
    return collision_probability_fallback(miss_distance, cov_rel=cov_rel)

def collision_probability_screening(miss_distance, cov_rel=None, collision_radius=COLLISION_RADIUS):
    """
    Conservative scalar Gaussian used for screening only.
    Designed to avoid false negatives and execute very fast.
    """
    miss = float(miss_distance)
    if miss <= collision_radius:
        return 1.0
    if cov_rel is not None:
        sigma = np.sqrt(np.trace(cov_rel) / 3.0)
        sigma = max(sigma, 1.0)
    else:
        sigma = DEFAULT_POS_STD
    return float(np.exp(-(miss ** 2) / (2.0 * sigma ** 2)))

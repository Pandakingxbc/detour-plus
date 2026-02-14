import numpy as np
from engine.config.settings import SIGMA, COLLISION_RADIUS

def collision_probability(distance):
    """
    Gaussian probability model for conjunction risk.
    distance: relative distance in meters
    """
    # If within effective collision radius, force high probability
    if distance <= COLLISION_RADIUS:
        return 1.0

    # Gaussian uncertainty model
    prob = np.exp(-(distance ** 2) / (2 * SIGMA ** 2))
    return float(prob)

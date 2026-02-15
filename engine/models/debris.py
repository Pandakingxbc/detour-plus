
# src/models/debris.py
import numpy as np
from engine.config.settings import DEFAULT_POS_STD

class Debris:
    """
    Debris object for screening & high-fidelity engines.
    """
    def __init__(self, position, velocity, name="Debris", cov_pos=None, cov_vel=None):
        self.name = name
        self.position = np.array(position, dtype=float)
        self.velocity = np.array(velocity, dtype=float)

        # --- covariance ---
        self.cov_pos = (
            np.atleast_2d(cov_pos)
            if cov_pos is not None
            else np.eye(3) * DEFAULT_POS_STD**2
        )
        self.cov_vel = (
            np.atleast_2d(cov_vel)
            if cov_vel is not None
            else np.eye(3) * 0.1**2
        )

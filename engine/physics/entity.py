# src/physics/entity.py
import numpy as np
from engine.physics.state import State
DEFAULT_BALLISTIC_COEFF = 2.2 

class Entity:
    """
    Base class for satellites or debris, including position, velocity, ballistic coefficient, and optional covariances for Monte Carlo.
    """
    def __init__(self, position, velocity, ballistic_coeff=DEFAULT_BALLISTIC_COEFF, cov_pos=None, cov_vel=None):
        self.position = np.array(position, dtype=float)
        self.velocity = np.array(velocity, dtype=float)
        self.ballistic_coeff = ballistic_coeff
        self.cov_pos = cov_pos if cov_pos is not None else np.eye(3) * 100.0**2  # Default isotropic 100m std
        self.cov_vel = cov_vel if cov_vel is not None else np.eye(3) * 0.1**2    # Default isotropic 0.1 m/s std``
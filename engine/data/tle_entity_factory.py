import numpy as np
from engine.physics.entity import Entity

def entity_from_tle(r, v, pos_sigma=100.0, vel_sigma=0.1):
    """
    Create Entity with reasonable covariance from TLE.
    """
    cov_pos = np.eye(3) * pos_sigma**2
    cov_vel = np.eye(3) * vel_sigma**2

    return Entity(
        position=r,
        velocity=v,
        cov_pos=cov_pos,
        cov_vel=cov_vel
    )

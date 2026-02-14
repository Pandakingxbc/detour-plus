# src/physics/third_body.py
import numpy as np
from typing import Tuple
from engine.physics.ephemeris import sun_position, moon_position

# Standard gravitational parameters (m^3/s^2)
MU_SUN = 1.32712440018e20
MU_MOON = 4.9048695e12

def third_body_accel_from_positions(r_sc: np.ndarray, r_body: np.ndarray, mu_body: float) -> np.ndarray:
    """
    Compute third-body acceleration on spacecraft at r_sc given third-body position r_body (both ECI).
    a = mu * ( (r_body - r_sc)/|r_body-r_sc|^3  - r_body/|r_body|^3 )
    r_body is position of third body w.r.t Earth.
    """
    r_sc = np.asarray(r_sc, dtype=float)
    r_body = np.asarray(r_body, dtype=float)
    r_sb = r_body - r_sc
    d1 = np.linalg.norm(r_sb)
    d2 = np.linalg.norm(r_body)
    if d1 == 0.0 or d2 == 0.0:
        return np.zeros(3, dtype=float)
    return mu_body * (r_sb / d1**3 - r_body / d2**3)


class ThirdBodyForce:
    """
    Force wrapper that computes Sun+Moon third-body accelerations using the simple ephemeris.
    """
    def __init__(self, include_sun: bool = True, include_moon: bool = True):
        self.include_sun = bool(include_sun)
        self.include_moon = bool(include_moon)

    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        r_sc = state.r
        total = np.zeros(3, dtype=float)
        if self.include_sun:
            r_sun = sun_position(t)
            total += third_body_accel_from_positions(r_sc, r_sun, MU_SUN)
        if self.include_moon:
            r_moon = moon_position(t)
            total += third_body_accel_from_positions(r_sc, r_moon, MU_MOON)
        return total

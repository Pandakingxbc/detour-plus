# src/physics/ephemeris.py
import numpy as np

# Simple analytical approximate ephemerides for Stage-2 use (sufficient for SRP/third-body in demos).
# t is seconds since epoch (UTC). These are *approximations* — replace with real ephemeris for production.

def sun_position(t: float) -> np.ndarray:
    """
    Very simple circular approximation of Sun position in ECI (meters).
    Period = 1 year.
    """
    omega = 2.0 * np.pi / (365.25 * 86400.0)
    R = 1.495978707e11  # 1 AU in meters
    return R * np.array([np.cos(omega * t), np.sin(omega * t), 0.0], dtype=float)


def moon_position(t: float) -> np.ndarray:
    """
    Simple circular approximation of Moon position in ECI (meters).
    Period ~ 27.3 days.
    """
    omega = 2.0 * np.pi / (27.321661 * 86400.0)
    R = 3.844e8  # mean Earth-Moon distance in meters
    return R * np.array([np.cos(omega * t), np.sin(omega * t), 0.0], dtype=float)

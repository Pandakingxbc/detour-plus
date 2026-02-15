

"""
Project-wide configuration constants for the space debris collision engine.
Keep this file simple and deterministic: only constants, small helper functions,
and light validation. Heavy logic belongs in the engines/physics modules.
Units: meters (m), seconds (s), kilograms (kg), meters/second (m/s).
"""
from __future__ import annotations
import os
import numpy as np
from typing import Optional

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# ---------------------------------------------------------------------------
# Physical constants (Earth)
# ---------------------------------------------------------------------------
GM = 3.986004418e14         # Earth's gravitational parameter, m^3 / s^2
RE = 6378137.0              # Earth's equatorial radius, m
EARTH_RADIUS = RE           # alias
J2 = 1.08262668e-3          # Earth's second zonal harmonic (dimensionless)

# Spacecraft / debris physical defaults (meters)
# Typical small-satellite / fragment sizes for screening
SATELLITE_RADIUS = 5.0      # m (typical smallsat)
DEBRIS_RADIUS = 1.0         # m (typical fragment)
COLLISION_RADIUS = SATELLITE_RADIUS + DEBRIS_RADIUS

# Conjunction / alert thresholds
DANGER_RADIUS = 1000.0      # m — 'conjunction' alert threshold (1 km)
ESCALATION_THRESHOLD = 5000.0  # m — when to consider Engine-2 or operator action

# Risk & uncertainty defaults
# Legacy fixed sigma retained for compatibility/backwards-fallback (m)
SIGMA = 50.0

# Default positional 1-sigma (m) used when no covariance is provided
DEFAULT_POS_STD = 100.0

# Risk threshold for marking high-risk (screening uses probability-like metric)
RISK_THRESHOLD = 0.01

# Simulation default parameters
DT = 1.0                    # base time-step (s)
STEPS = 600                 # default number of integration steps
LOOKAHEAD_SEC = 78.0        # screening horizon (s)

# Limits and protections
LOOKAHEAD_MIN = 1.0         # minimum sensible lookahead (s)
LOOKAHEAD_MAX = 3600.0     # maximum lookahead (s) — safety cap

MAX_DEBRIS = 500             # practical upper limit for debris list in CLI
SPREAD = 5000.0             # m — initial position spread used by random generator
REL_VEL_SPREAD = 20.0       # m/s — relative velocity perturbation for random debris

DEFAULT_ALTITUDE = 400000.0 # m (400 km)
SATELLITE_SPEED = 7500.0    # m/s (typical LEO speed used by simple generator)
AVOIDANCE_DELTA_V = 0.05    # km/s (50 m/s) suggested maneuver magnitude

# Atmospheric density model (very simple exponential model for LEO)
RHO0 = 2.4e-12              # kg/m^3 reference density at H0 (example)
H0 = 400000.0               # m, reference altitude for RHO0
SCALE_HEIGHT = 60000.0      # m, scale height approximation

def atmospheric_density(altitude: float) -> float:
    """
    Simple exponential atmospheric density approximation.
    Returns density in kg/m^3. Zero below surface or above 1000 km.
    """
    if altitude <= 0.0 or altitude >= 1_000_000.0:
        return 0.0
    return RHO0 * np.exp(-(altitude - H0) / SCALE_HEIGHT)

# Ballistic coefficient default
# Ballistic coefficient B = mass / (C_d * A) in kg/m^2.
# Typical values vary widely; 50 kg/m^2 is a reasonable default for
# compact satellites/fragments for simple drag modeling in demos.
DEFAULT_BALLISTIC_COEFF = 50.0  # kg/m^2

# Screening (Engine-1) tuning
ENGINE1_DT = 2.0              # seconds (scientifically safe for LEO screening)
ENGINE1_LOOKAHEAD = 2000.0     # seconds
ENGINE1_CW_SAMPLES = 120      # CW sampling (conservative but fast)
ENGINE1_USE_CHAN = False      # IMPORTANT: Chan disabled in screening

# ============================
# Confirmation (Engine-2)
# ============================
ENGINE2_DT = 1.0
ENGINE2_USE_CHAN = True

# ============================
# Monte Carlo
# ============================
MC_DEFAULT_N = 300             # real science starts here

# Helper functions
def clamp_lookahead(val: Optional[float]) -> float:
    """
    Return a sane lookahead value clamped to [LOOKAHEAD_MIN, LOOKAHEAD_MAX].
    If val is None, return LOOKAHEAD_SEC.
    """
    if val is None:
        out = float(LOOKAHEAD_SEC)
    else:
        out = float(val)
    out = max(float(LOOKAHEAD_MIN), min(float(LOOKAHEAD_MAX), out))
    return out

def get_collision_radius(sat_radius: Optional[float] = None, deb_radius: Optional[float] = None) -> float:
    """
    Utility to compute collision radius from provided radii or defaults.
    """
    sr = SATELLITE_RADIUS if sat_radius is None else float(sat_radius)
    dr = DEBRIS_RADIUS if deb_radius is None else float(deb_radius)
    return sr + dr

def validate_settings() -> None:
    """
    Basic sanity checks that raise informative errors if constants are inconsistent.
    Call at program startup if you want strict validation.
    """
    if DT <= 0:
        raise ValueError("DT must be > 0")
    if STEPS <= 0:
        raise ValueError("STEPS must be > 0")
    if LOOKAHEAD_SEC <= 0:
        raise ValueError("LOOKAHEAD_SEC must be > 0")
    if COLLISION_RADIUS <= 0:
        raise ValueError("COLLISION_RADIUS must be > 0")
    if DEFAULT_POS_STD <= 0:
        raise ValueError("DEFAULT_POS_STD must be > 0")
    if DEFAULT_BALLISTIC_COEFF <= 0:
        raise ValueError("DEFAULT_BALLISTIC_COEFF must be > 0")

# Optionally validate on import (disabled by default — uncomment to enforce)
# validate_settings()

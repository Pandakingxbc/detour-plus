"""
Collision simulation: satellite navigates through real LEO debris field
with sharp micro-correction maneuvers, eventually getting trapped and colliding.
"""

from __future__ import annotations

import math
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from api import state

logger = logging.getLogger("detour.simulation")

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

# --- Constants ---
GM = 3.986004418e14       # m^3/s^2
RE = 6378137.0            # Earth equatorial radius (m)
J2 = 1.08263e-3
OMEGA_EARTH = 7.2921159e-5  # rad/s
DEG2RAD = math.pi / 180


# --- Response Models ---

class TrajectoryPoint(BaseModel):
    t: float
    lat: float
    lon: float
    alt_km: float
    nearest_km: Optional[float] = None


class SimulationScenario(BaseModel):
    scenario_id: str
    label: str
    duration_sec: float
    collision_t: float
    collision_lat: float
    collision_lon: float
    collision_alt_km: float
    satellite: List[TrajectoryPoint]


# --- TLE Parsing ---

def _tle_epoch(tle_line1: str) -> Optional[datetime]:
    """Extract epoch from TLE line 1."""
    try:
        epoch_str = tle_line1[18:32].strip()
        year_2d = int(epoch_str[:2])
        day_frac = float(epoch_str[2:])
        year = 2000 + year_2d if year_2d < 57 else 1900 + year_2d
        epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_frac - 1)
        return epoch
    except Exception:
        return None


def _parse_tle_elements(tle_line1: str, tle_line2: str) -> Optional[Dict]:
    """Extract orbital elements from TLE lines."""
    try:
        inc_deg = float(tle_line2[8:16])
        raan_deg = float(tle_line2[17:25])
        ecc = float("0." + tle_line2[26:33].strip())
        argp_deg = float(tle_line2[34:42])
        ma_deg = float(tle_line2[43:51])
        mean_motion_rpd = float(tle_line2[52:63])

        if mean_motion_rpd <= 0 or ecc >= 1:
            return None

        period_sec = 86400.0 / mean_motion_rpd
        a = (GM * (period_sec / (2 * math.pi)) ** 2) ** (1 / 3)
        alt_km = (a - RE) / 1000.0

        if alt_km < 150 or alt_km > 2000:
            return None

        n_rad_s = mean_motion_rpd * 2 * math.pi / 86400.0
        tle_epoch = _tle_epoch(tle_line1)
        now = datetime.now(timezone.utc)
        if tle_epoch:
            dt_sec = (now - tle_epoch).total_seconds()
            ma_now_deg = (ma_deg + math.degrees(n_rad_s * dt_sec)) % 360.0
        else:
            ma_now_deg = ma_deg

        return {
            "alt_km": round(alt_km, 3),
            "inc_deg": round(inc_deg, 4),
            "raan_deg": round(raan_deg, 4),
            "argp_deg": round(argp_deg, 4),
            "ma0_deg": round(ma_now_deg, 4),
        }
    except Exception:
        return None


def _get_catalog_debris_params() -> List[Dict]:
    """Extract orbital params for all LEO objects from the catalog."""
    catalog = state.get_catalog()
    all_objects = catalog.get_all(propagate=False)

    params = []
    for obj in all_objects:
        if not obj.tle_line1 or not obj.tle_line2:
            continue
        elems = _parse_tle_elements(obj.tle_line1, obj.tle_line2)
        if elems:
            params.append(elems)

    logger.info("Extracted orbital params for %d LEO objects from catalog", len(params))
    return params


def _generate_synthetic_debris(count: int, alt_range: Tuple[float, float],
                                inc_range: Tuple[float, float], seed: int) -> List[Dict]:
    """Fallback: generate synthetic debris params if catalog is empty."""
    rng = random.Random(seed)
    params = []
    for _ in range(count):
        params.append({
            "alt_km": round(rng.uniform(*alt_range), 3),
            "inc_deg": round(rng.uniform(*inc_range), 4),
            "raan_deg": round(rng.uniform(0, 360), 4),
            "argp_deg": round(rng.uniform(0, 360), 4),
            "ma0_deg": round(rng.uniform(0, 360), 4),
        })
    return params


# --- Vectorized Debris Field ---

class DebrisField:
    """Precomputed debris orbital elements for vectorized position queries."""

    def __init__(self, params: List[Dict]):
        self.count = len(params)
        self.a = np.array([RE + p["alt_km"] * 1000 for p in params])
        self.n_motion = np.sqrt(GM / self.a**3)
        self.ma0 = np.array([p["ma0_deg"] * DEG2RAD for p in params])

        inc = np.array([p["inc_deg"] * DEG2RAD for p in params])
        raan = np.array([p["raan_deg"] * DEG2RAD for p in params])
        argp = np.array([p["argp_deg"] * DEG2RAD for p in params])

        cw = np.cos(argp); sw = np.sin(argp)
        ci = np.cos(inc); si = np.sin(inc)
        cO = np.cos(raan); sO = np.sin(raan)

        self.rx_x = cO*cw - sO*sw*ci; self.ry_x = -cO*sw - sO*cw*ci
        self.rx_y = sO*cw + cO*sw*ci; self.ry_y = -sO*sw + cO*cw*ci
        self.rx_z = sw*si;             self.ry_z = cw*si

    def positions_at(self, t: float) -> np.ndarray:
        """ECI positions of all debris at time t. Returns (N, 3) array."""
        M = self.ma0 + self.n_motion * t
        cosM = np.cos(M); sinM = np.sin(M)
        x = self.a * (self.rx_x * cosM + self.ry_x * sinM)
        y = self.a * (self.rx_y * cosM + self.ry_y * sinM)
        z = self.a * (self.rx_z * cosM + self.ry_z * sinM)
        return np.column_stack([x, y, z])

    def position_of(self, idx: int, t: float) -> np.ndarray:
        """ECI position of single debris object at time t."""
        M = float(self.ma0[idx] + self.n_motion[idx] * t)
        cosM = math.cos(M); sinM = math.sin(M)
        x = float(self.a[idx]) * (float(self.rx_x[idx]) * cosM + float(self.ry_x[idx]) * sinM)
        y = float(self.a[idx]) * (float(self.rx_y[idx]) * cosM + float(self.ry_y[idx]) * sinM)
        z = float(self.a[idx]) * (float(self.rx_z[idx]) * cosM + float(self.ry_z[idx]) * sinM)
        return np.array([x, y, z])

    def nearest_distance_km(self, pos: np.ndarray, t: float) -> float:
        """Distance in km from pos to nearest debris at time t."""
        all_pos = self.positions_at(t)
        dists = np.linalg.norm(pos - all_pos, axis=1)
        return float(np.min(dists)) / 1000.0


# --- Physics ---

def _accel(pos: np.ndarray) -> np.ndarray:
    """Gravitational acceleration with J2."""
    rr = np.linalg.norm(pos)
    a_newton = -GM / rr**3 * pos
    x, y, z = pos
    r2 = rr * rr
    factor = -1.5 * J2 * GM * RE**2 / rr**5
    zr2 = 5.0 * z * z / r2
    a_j2 = factor * np.array([x * (1 - zr2), y * (1 - zr2), z * (3 - zr2)])
    return a_newton + a_j2


def _rk4_step(r: np.ndarray, v: np.ndarray, dt: float) -> Tuple[np.ndarray, np.ndarray]:
    k1v = _accel(r) * dt;           k1r = v * dt
    k2v = _accel(r + 0.5*k1r) * dt; k2r = (v + 0.5*k1v) * dt
    k3v = _accel(r + 0.5*k2r) * dt; k3r = (v + 0.5*k2v) * dt
    k4v = _accel(r + k3r) * dt;     k4r = (v + k3v) * dt
    return r + (k1r + 2*k2r + 2*k3r + k4r)/6, v + (k1v + 2*k2v + 2*k3v + k4v)/6


def _propagate(r0, v0, dt, steps):
    traj = [(r0.copy(), v0.copy())]
    r, v = r0.copy(), v0.copy()
    for _ in range(steps - 1):
        r, v = _rk4_step(r, v, dt)
        traj.append((r.copy(), v.copy()))
    return traj


def _eci_to_geodetic(r: np.ndarray, gmst: float) -> Tuple[float, float, float]:
    c, s = math.cos(-gmst), math.sin(-gmst)
    x = c * r[0] - s * r[1]
    y = s * r[0] + c * r[1]
    z = r[2]
    rr = math.sqrt(x*x + y*y + z*z)
    lat = math.degrees(math.asin(z / rr)) if rr > 0 else 0.0
    lon = math.degrees(math.atan2(y, x))
    alt_km = (rr - RE) / 1000.0
    return lat, lon, alt_km


# --- Close approach finder ---

def _find_close_approaches(
    base_traj: List[Tuple[np.ndarray, np.ndarray]],
    debris_field: DebrisField,
    dt: float,
    check_interval: int = 30,
    threshold_km: float = 500.0,
) -> List[Tuple[int, int, float]]:
    """
    Find closest approach per debris object.
    Returns list of (step, debris_idx, distance_km) sorted by distance.
    """
    sample_steps = list(range(0, len(base_traj), check_interval))
    sat_positions = np.array([base_traj[s][0] for s in sample_steps])
    times = np.array([s * dt for s in sample_steps])

    best: Dict[int, Tuple[int, int, float]] = {}

    for t_idx, t in enumerate(times):
        debris_pos = debris_field.positions_at(t)
        dists = np.linalg.norm(sat_positions[t_idx] - debris_pos, axis=1) / 1000

        close_mask = dists < threshold_km
        for d_idx in np.where(close_mask)[0]:
            d_idx_int = int(d_idx)
            dist_val = float(dists[d_idx])
            if d_idx_int not in best or dist_val < best[d_idx_int][2]:
                best[d_idx_int] = (sample_steps[t_idx], d_idx_int, dist_val)

    result = sorted(best.values(), key=lambda x: x[2])
    return result


# --- Main Generator ---

_cached_result = None


def _generate_scenario():
    """Generate scenario with sharp micro-correction maneuvers and guaranteed collision."""
    global _cached_result
    if _cached_result is not None:
        return _cached_result

    rng = random.Random(42)
    dt = 1.0
    duration_sec = 75.0 * 60.0  # 75 minutes
    total_steps = int(duration_sec / dt) + 1
    collision_fraction = 0.6

    # --- 1. Base satellite orbit ---
    sat_alt_km = 420.0
    sat_alt = sat_alt_km * 1000.0
    r_orbit = RE + sat_alt
    v_circ = math.sqrt(GM / r_orbit)
    inc = math.radians(51.6)
    r0 = np.array([r_orbit, 0.0, 0.0])
    v0 = np.array([0.0, v_circ * math.cos(inc), v_circ * math.sin(inc)])

    logger.info("Propagating base orbit (%d steps)...", total_steps)
    base_traj = _propagate(r0, v0, dt, total_steps)

    # --- 2. Get debris from catalog ---
    debris_params = _get_catalog_debris_params()
    if len(debris_params) < 100:
        logger.warning("Catalog has few LEO objects (%d), using synthetic fallback", len(debris_params))
        debris_params = _generate_synthetic_debris(2000, (300, 600), (20, 110), 42)

    debris_field = DebrisField(debris_params)
    logger.info("Debris field: %d objects", debris_field.count)

    # --- 3. Find close approaches ---
    logger.info("Finding close approaches...")
    approaches = _find_close_approaches(base_traj, debris_field, dt,
                                         check_interval=30, threshold_km=500)
    if not approaches:
        approaches = _find_close_approaches(base_traj, debris_field, dt,
                                             check_interval=30, threshold_km=2000)

    logger.info("Found %d debris with close approaches", len(approaches))

    # --- 4. Pick collision target (near 60% mark) ---
    target_step = int(total_steps * collision_fraction)
    best_collision = None
    best_score = float("inf")

    for step, d_idx, dist in approaches:
        if 0.4 * total_steps < step < 0.8 * total_steps:
            score = abs(step - target_step) / total_steps + dist / 1000
            if score < best_score:
                best_score = score
                best_collision = (step, d_idx, dist)

    if best_collision is None and approaches:
        best_collision = approaches[0]

    collision_step = best_collision[0] if best_collision else target_step
    collision_idx = best_collision[1] if best_collision else 0
    collision_t = collision_step * dt

    logger.info("Collision: debris #%d at step %d (t=%.0fs), base miss=%.0f km",
                collision_idx, collision_step, collision_t,
                best_collision[2] if best_collision else 0)

    # --- 5. Apply micro-correction maneuvers ---
    # Many sharp, small corrections that look like reactive navigation.
    # Frequency increases as satellite approaches collision (getting trapped).
    modified_positions = [r.copy() for r, v in base_traj]

    maneuver_zone_start = int(total_steps * 0.03)
    maneuver_zone_end = collision_step - 60

    if maneuver_zone_end > maneuver_zone_start:
        # Phase 1: sparse corrections (early flight — calm navigation)
        phase1_end = int(maneuver_zone_start + (maneuver_zone_end - maneuver_zone_start) * 0.4)
        phase1_count = 15
        phase1_spacing = max(1, (phase1_end - maneuver_zone_start) / (phase1_count + 1))
        phase1_steps = [int(maneuver_zone_start + (i + 1) * phase1_spacing) for i in range(phase1_count)]

        # Phase 2: moderate density (getting busier)
        phase2_end = int(maneuver_zone_start + (maneuver_zone_end - maneuver_zone_start) * 0.75)
        phase2_count = 25
        phase2_spacing = max(1, (phase2_end - phase1_end) / (phase2_count + 1))
        phase2_steps = [int(phase1_end + (i + 1) * phase2_spacing) for i in range(phase2_count)]

        # Phase 3: rapid-fire corrections (getting trapped, frantic)
        phase3_count = 30
        phase3_spacing = max(1, (maneuver_zone_end - phase2_end) / (phase3_count + 1))
        phase3_steps = [int(phase2_end + (i + 1) * phase3_spacing) for i in range(phase3_count)]

        all_maneuver_steps = phase1_steps + phase2_steps + phase3_steps
    else:
        all_maneuver_steps = []

    direction = 1
    for m_idx, m_step in enumerate(all_maneuver_steps):
        if m_step < 0 or m_step >= total_steps:
            continue

        r_at = base_traj[m_step][0]
        v_at = base_traj[m_step][1]
        r_hat = r_at / np.linalg.norm(r_at)
        v_hat = v_at / np.linalg.norm(v_at)

        # Cross-track direction
        c_hat = np.cross(v_hat, r_hat)
        c_hat_norm = np.linalg.norm(c_hat)
        if c_hat_norm > 0:
            c_hat = c_hat / c_hat_norm
        else:
            c_hat = np.array([0, 0, 1.0])

        # Radial direction (up/down)
        up_hat = r_hat

        # Mix cross-track and radial for 3D dodging
        mix = rng.uniform(-0.5, 0.5)
        dodge_dir = c_hat * direction + up_hat * mix
        dodge_dir = dodge_dir / np.linalg.norm(dodge_dir)
        direction *= -1  # alternate

        # Progress through maneuver sequence
        progress = m_idx / max(1, len(all_maneuver_steps) - 1)

        # Magnitude: starts moderate, grows, then gets frantic and smaller
        # (satellite running out of options)
        if progress < 0.4:
            # Early: confident corrections
            base_mag = 250_000 * (0.6 + 0.4 * rng.random())  # 150-250 km
            sigma = rng.uniform(10, 18)  # sharp
        elif progress < 0.75:
            # Mid: larger dodges as threats increase
            base_mag = 350_000 * (0.7 + 0.3 * rng.random())  # 245-350 km
            sigma = rng.uniform(7, 14)  # sharper
        else:
            # Late: frantic, smaller, rapid corrections (trapped)
            base_mag = 180_000 * (0.5 + 0.5 * rng.random())  # 90-180 km
            sigma = rng.uniform(4, 9)  # very sharp

        half_width = int(3.5 * sigma)
        for i in range(max(0, m_step - half_width), min(total_steps, m_step + half_width)):
            w = math.exp(-0.5 * ((i - m_step) / sigma) ** 2)
            modified_positions[i] = modified_positions[i] + dodge_dir * base_mag * w

    logger.info("Applied %d micro-correction maneuvers", len(all_maneuver_steps))

    # --- 6. Force collision convergence ---
    collision_eci = debris_field.position_of(collision_idx, collision_t)
    blend_steps = 250
    blend_start = max(0, collision_step - blend_steps)

    for i in range(blend_start, min(total_steps, collision_step + 1)):
        alpha = (i - blend_start) / max(1, collision_step - blend_start)
        alpha = alpha * alpha * (3 - 2 * alpha)  # smoothstep
        modified_positions[i] = (1 - alpha) * modified_positions[i] + alpha * collision_eci

    # After collision: satellite drifts on degraded trajectory
    if collision_step < total_steps - 1:
        post_vel = base_traj[collision_step][1] * 0.3
        for i in range(collision_step + 1, total_steps):
            dt_post = (i - collision_step) * dt
            modified_positions[i] = collision_eci + post_vel * dt_post

    # --- 7. Compute collision geodetic position ---
    collision_gmst = OMEGA_EARTH * collision_t
    c_lat, c_lon, c_alt = _eci_to_geodetic(collision_eci, collision_gmst)

    # --- 8. Compute nearest debris distances ---
    logger.info("Computing nearest debris distances...")
    nearest_km = np.full(total_steps, np.nan)
    sample_rate = 10

    for i in range(0, total_steps, sample_rate):
        t = i * dt
        sat_pos = modified_positions[i]
        all_deb = debris_field.positions_at(t)
        dists = np.linalg.norm(sat_pos - all_deb, axis=1) / 1000
        nearest_km[i] = float(np.min(dists))

    # Interpolate between samples
    for i in range(total_steps):
        if not np.isnan(nearest_km[i]):
            continue
        lo = (i // sample_rate) * sample_rate
        hi = min(lo + sample_rate, total_steps - 1)
        if hi >= total_steps:
            hi = total_steps - 1
        nk_lo = nearest_km[lo] if not np.isnan(nearest_km[lo]) else 999.0
        nk_hi = nearest_km[hi] if not np.isnan(nearest_km[hi]) else nk_lo
        alpha = (i - lo) / max(1, hi - lo)
        nearest_km[i] = (1 - alpha) * nk_lo + alpha * nk_hi

    # --- 9. Convert to geodetic ---
    logger.info("Converting to geodetic...")
    result_points: List[TrajectoryPoint] = []
    for i in range(total_steps):
        t = i * dt
        gmst = OMEGA_EARTH * t
        lat, lon, alt = _eci_to_geodetic(modified_positions[i], gmst)
        result_points.append(TrajectoryPoint(
            t=round(t, 1),
            lat=round(lat, 5),
            lon=round(lon, 5),
            alt_km=round(alt, 3),
            nearest_km=round(float(nearest_km[i]), 2),
        ))

    logger.info("Scenario generation complete: collision at t=%.0fs, pos=(%.2f, %.2f, %.1f km)",
                collision_t, c_lat, c_lon, c_alt)
    _cached_result = (result_points, collision_t, duration_sec, c_lat, c_lon, c_alt)
    return _cached_result


# --- Endpoints ---

@router.get("/scenarios")
async def list_scenarios():
    return [{"id": "collision_course", "label": "LEO Collision Course",
             "description": "Navigate through LEO debris field"}]


@router.get("/run/{scenario_id}", response_model=SimulationScenario)
async def run_scenario(scenario_id: str):
    satellite, collision_t, duration_sec, c_lat, c_lon, c_alt = _generate_scenario()

    return SimulationScenario(
        scenario_id="collision_course",
        label="LEO Collision Course",
        duration_sec=duration_sec,
        collision_t=collision_t,
        collision_lat=c_lat,
        collision_lon=c_lon,
        collision_alt_km=c_alt,
        satellite=satellite,
    )

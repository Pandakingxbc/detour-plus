import numpy as np
from typing import Tuple
from engine.config.settings import GM, ENGINE1_CW_SAMPLES
from engine.physics.geometry import time_of_closest_approach

def _hill_frame_basis(r_sat: np.ndarray, v_sat: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Return local Hill frame basis vectors (er, ey, ez) in ECI:
      er = radial (unit r_sat)
      ez = orbit-normal (unit r x v)
      ey = along-track = ez x er
    """
    r_norm = np.linalg.norm(r_sat)
    if r_norm == 0:
        raise ValueError("Satellite radius vector is zero-length for Hill frame.")
    er = r_sat / r_norm
    h = np.cross(r_sat, v_sat)
    h_norm = np.linalg.norm(h)
    if h_norm == 0:
        # degenerate (co-linear r and v) — choose arbitrary orbit normal
        arb = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(arb, er)) > 0.9:
            arb = np.array([0.0, 1.0, 0.0])
        ez = np.cross(er, arb)
        ez = ez / np.linalg.norm(ez)
    else:
        ez = h / h_norm
    ey = np.cross(ez, er)
    ey = ey / np.linalg.norm(ey)
    return er, ey, ez

def _cw_state_at_t(x0, y0, z0, vx0, vy0, vz0, n, t):
    """
    Standard CW/Hill solution for relative state at time t (in Hill coordinates).
    Returns (x,y,z), (vx,vy,vz).
    """
    nt = n * t
    cosnt = np.cos(nt)
    sinnt = np.sin(nt)

    x = (4.0 - 3.0 * cosnt) * x0 + (1.0 / n) * sinnt * vx0 + (2.0 / n) * (1.0 - cosnt) * vy0
    y = 6.0 * (sinnt - nt) * x0 + y0 + (2.0 / n) * (cosnt - 1.0) * vx0 + (1.0 / n) * (4.0 * sinnt - 3.0 * nt) * vy0
    z = z0 * cosnt + (1.0 / n) * sinnt * vz0

    vx = 3.0 * n * sinnt * x0 + cosnt * vx0 + 2.0 * sinnt * vy0
    vy = 6.0 * n * (cosnt - 1.0) * x0 - 2.0 * sinnt * vx0 + (4.0 * cosnt - 3.0) * vy0
    vz = -n * sinnt * z0 + cosnt * vz0

    return np.array([x, y, z]), np.array([vx, vy, vz])

def cw_time_of_closest_approach(
    r_sat, v_sat, r_deb, v_deb,
    horizon: float = 78.0,
    n_samples: int = ENGINE1_CW_SAMPLES
):
    """
    Compute TCA using Clohessy-Wiltshire relative dynamics around the satellite's circular-like orbit.
    Returns:
      tca (s), miss_distance (m), rel_pos_at_tca (ECI 3-vector), rel_vel_at_tca (ECI 3-vector)

    Notes:
      - Uses vectorized sampling for performance.
      - Includes a validity guard: if result is outside CW domain, fallback to simple linear TCA.
    """
    r_sat = np.asarray(r_sat, dtype=float)
    v_sat = np.asarray(v_sat, dtype=float)
    r_deb = np.asarray(r_deb, dtype=float)
    v_deb = np.asarray(v_deb, dtype=float)

    er, ey, ez = _hill_frame_basis(r_sat, v_sat)

    r0 = np.linalg.norm(r_sat)
    if r0 <= 0:
        # Degenerate: fallback to linear solution
        tca, miss = time_of_closest_approach(r_sat, v_sat, r_deb, v_deb)
        rel_pos_at_tca = (r_deb + v_deb * tca) - (r_sat + v_sat * tca)
        rel_vel_at_tca = v_deb - v_sat
        return float(tca), float(miss), rel_pos_at_tca, rel_vel_at_tca

    # mean motion n (use satellite radius magnitude)
    n = np.sqrt(GM / (r0 ** 3))

    # initial relative state in Hill coords
    rel_r = r_deb - r_sat
    rel_v = v_deb - v_sat

    x0 = float(np.dot(rel_r, er))
    y0 = float(np.dot(rel_r, ey))
    z0 = float(np.dot(rel_r, ez))
    vx0 = float(np.dot(rel_v, er))
    vy0 = float(np.dot(rel_v, ey))
    vz0 = float(np.dot(rel_v, ez))

    # Vectorized sampling of CW analytic solution
    times = np.linspace(0.0, horizon, max(3, int(n_samples)))
    nt = n * times
    cosnt = np.cos(nt)
    sinnt = np.sin(nt)

    x = (4.0 - 3.0 * cosnt) * x0 + (1.0 / n) * sinnt * vx0 + (2.0 / n) * (1.0 - cosnt) * vy0
    y = 6.0 * (sinnt - nt) * x0 + y0 + (2.0 / n) * (cosnt - 1.0) * vx0 + (1.0 / n) * (4.0 * sinnt - 3.0 * nt) * vy0
    z = z0 * cosnt + (1.0 / n) * sinnt * vz0

    # transform back to ECI relative vectors for every sample
    rel = (
        np.outer(x, er) +
        np.outer(y, ey) +
        np.outer(z, ez)
    )

    dvals = np.linalg.norm(rel, axis=1)
    idx_min = int(np.argmin(dvals))
    tca = float(times[idx_min])
    miss = float(dvals[idx_min])

    # Validate CW domain: if miss is huge relative to orbit radius, fallback to linear TCA
    if miss > 0.1 * r0:
        # CW may be invalid here; fallback to linear short-window analytic TCA
        tca_lin, miss_lin = time_of_closest_approach(r_sat, v_sat, r_deb, v_deb)
        rel_pos_at_tca = (r_deb + v_deb * tca_lin) - (r_sat + v_sat * tca_lin)
        rel_vel_at_tca = v_deb - v_sat
        return float(tca_lin), float(miss_lin), rel_pos_at_tca, rel_vel_at_tca

    # Compute relative velocity at TCA using analytic CW velocity
    _, vel_hill = _cw_state_at_t(x0, y0, z0, vx0, vy0, vz0, n, tca)
    rel_vel_at_tca = vel_hill[0] * er + vel_hill[1] * ey + vel_hill[2] * ez
    rel_pos_at_tca = rel[idx_min]

    return float(tca), float(miss), rel_pos_at_tca, rel_vel_at_tca

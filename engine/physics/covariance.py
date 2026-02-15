# # src/physics/covariance.py
# import numpy as np
# from typing import Tuple
# from math import isfinite
# from engine.config.settings import GM

# def _hill_frame_basis(r_sat: np.ndarray, v_sat: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
#     r_norm = np.linalg.norm(r_sat)
#     if r_norm == 0:
#         raise ValueError("Zero satellite radius in hill basis")
#     er = r_sat / r_norm
#     h = np.cross(r_sat, v_sat)
#     h_norm = np.linalg.norm(h)
#     if h_norm == 0:
#         # degenerate: pick arbitrary normal
#         arb = np.array([1.0, 0.0, 0.0])
#         if abs(np.dot(arb, er)) > 0.9:
#             arb = np.array([0.0, 1.0, 0.0])
#         ez = np.cross(er, arb)
#         ez = ez / np.linalg.norm(ez)
#     else:
#         ez = h / h_norm
#     ey = np.cross(ez, er)
#     ey = ey / np.linalg.norm(ey)
#     return er, ey, ez

# def _cw_state_at_t(x0, y0, z0, vx0, vy0, vz0, n, t):
#     nt = n * t
#     cosnt = np.cos(nt)
#     sinnt = np.sin(nt)

#     x = (4.0 - 3.0 * cosnt) * x0 + (1.0 / n) * sinnt * vx0 + (2.0 / n) * (1.0 - cosnt) * vy0
#     y = 6.0 * (sinnt - nt) * x0 + y0 + (2.0 / n) * (cosnt - 1.0) * vx0 + (1.0 / n) * (4.0 * sinnt - 3.0 * nt) * vy0
#     z = z0 * cosnt + (1.0 / n) * sinnt * vz0

#     vx = 3.0 * n * sinnt * x0 + cosnt * vx0 + 2.0 * sinnt * vy0
#     vy = 6.0 * n * (cosnt - 1.0) * x0 - 2.0 * sinnt * vx0 + (4.0 * cosnt - 3.0) * vy0
#     vz = -n * sinnt * z0 + cosnt * vz0

#     return np.array([x, y, z], dtype=float), np.array([vx, vy, vz], dtype=float)

# def _cw_state_transition_matrix(n: float, t: float) -> np.ndarray:
#     """
#     Build 6x6 CW STM Phi(t) mapping [x0; v0] -> [x(t); v(t)] in Hill coords.
#     We'll compute columns by evaluating the analytic solution with basis initial conditions.
#     """
#     # Build matrix by evaluating response to basis initial conditions
#     Phi = np.zeros((6, 6), dtype=float)

#     # For each position unit vector (x0 basis)
#     for i in range(3):
#         x0 = 1.0 if i == 0 else 0.0
#         y0 = 1.0 if i == 1 else 0.0
#         z0 = 1.0 if i == 2 else 0.0
#         # zero initial velocities
#         pos_t, vel_t = _cw_state_at_t(x0, y0, z0, 0.0, 0.0, 0.0, n, t)
#         Phi[0:3, i] = pos_t
#         Phi[3:6, i] = vel_t

#     # For each velocity unit vector (v0 basis)
#     for j in range(3):
#         vx0 = 1.0 if j == 0 else 0.0
#         vy0 = 1.0 if j == 1 else 0.0
#         vz0 = 1.0 if j == 2 else 0.0
#         pos_t, vel_t = _cw_state_at_t(0.0, 0.0, 0.0, vx0, vy0, vz0, n, t)
#         Phi[0:3, 3 + j] = pos_t
#         Phi[3:6, 3 + j] = vel_t

#     return Phi

# def propagate_covariance_cw(
#     r_sat: np.ndarray,
#     v_sat: np.ndarray,
#     P_pos: np.ndarray,
#     P_vel: np.ndarray,
#     dt: float
# ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
#     """
#     Propagate position & velocity covariance using CW analytical STM around a near-circular orbit.
#     Returns (P_pos_t, P_vel_t, P6x6_t)
#     """
#     r_sat = np.asarray(r_sat, dtype=float)
#     v_sat = np.asarray(v_sat, dtype=float)
#     P_pos = np.atleast_2d(np.asarray(P_pos, dtype=float))
#     P_vel = np.atleast_2d(np.asarray(P_vel, dtype=float))

#     r0 = np.linalg.norm(r_sat)
#     if r0 == 0 or not isfinite(r0):
#         raise ValueError("Invalid satellite radius for CW propagation")

#     # mean motion
#     n = np.sqrt(GM / (r0 ** 3))

#     # build Hill frame basis
#     er, ey, ez = _hill_frame_basis(r_sat, v_sat)
#     # assemble rotation matrix from Hill->ECI (columns = er, ey, ez)
#     R_hill2eci = np.column_stack((er, ey, ez))  # 3x3
#     R_eci2hill = R_hill2eci.T

#     # form full 6x6 initial covariance (pos/vel blocks)
#     P0 = np.zeros((6, 6), dtype=float)
#     P0[0:3, 0:3] = P_pos
#     P0[3:6, 3:6] = P_vel

#     # get STM in Hill coordinates
#     Phi_hill = _cw_state_transition_matrix(n, dt)  # 6x6 in Hill coordinates

#     # transform P0 from ECI -> Hill
#     T = np.zeros((6, 6), dtype=float)
#     T[0:3, 0:3] = R_eci2hill
#     T[3:6, 3:6] = R_eci2hill
#     P0_hill = T @ P0 @ T.T

#     # propagate in Hill
#     P_hill_t = Phi_hill @ P0_hill @ Phi_hill.T

#     # transform back to ECI
#     Tinv = np.zeros((6, 6), dtype=float)
#     Tinv[0:3, 0:3] = R_hill2eci
#     Tinv[3:6, 3:6] = R_hill2eci
#     P_t = Tinv @ P_hill_t @ Tinv.T

#     P_pos_t = P_t[0:3, 0:3]
#     P_vel_t = P_t[3:6, 3:6]
#     return P_pos_t, P_vel_t, P_t

# def _build_linearized_A(r: np.ndarray) -> np.ndarray:
#     """
#     Build linearized dynamics matrix A for state [r; v] for central gravity:
#       rdot = v
#       vdot = a(r)  where a(r) = -GM * r / r^3
#     A = [ 0  I
#           dadr  0 ]
#     where dadr = d a / d r (3x3)
#     """
#     r = np.asarray(r, dtype=float)
#     rnorm = np.linalg.norm(r)
#     if rnorm == 0:
#         raise ValueError("Zero radius for linearized A")
#     I3 = np.eye(3)
#     # compute d a / d r
#     mu = GM
#     r_outer = np.outer(r, r)
#     dadr = -mu * (I3 / (rnorm ** 3) - 3.0 * r_outer / (rnorm ** 5))
#     A = np.zeros((6, 6), dtype=float)
#     A[0:3, 3:6] = I3
#     A[3:6, 0:3] = dadr
#     return A

# def _phi_approx_from_A(A: np.ndarray, dt: float) -> np.ndarray:
#     """
#     Second-order Taylor approximation for matrix exponential:
#     Phi ≈ I + A*dt + 0.5*(A*dt)^2
#     Good for small dt (safe fallback).
#     """
#     I6 = np.eye(6)
#     Adt = A * dt
#     Phi = I6 + Adt + 0.5 * (Adt @ Adt)
#     return Phi

# def propagate_covariance_linear_approx(
#     r_sat: np.ndarray,
#     v_sat: np.ndarray,
#     P_pos: np.ndarray,
#     P_vel: np.ndarray,
#     dt: float
# ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
#     """
#     Linearized two-body propagation fallback using matrix Taylor approx for Phi.
#     """
#     P_pos = np.atleast_2d(np.asarray(P_pos, dtype=float))
#     P_vel = np.atleast_2d(np.asarray(P_vel, dtype=float))

#     A = _build_linearized_A(r_sat)
#     Phi = _phi_approx_from_A(A, dt)

#     P0 = np.zeros((6, 6), dtype=float)
#     P0[0:3, 0:3] = P_pos
#     P0[3:6, 3:6] = P_vel

#     P_t = Phi @ P0 @ Phi.T

#     return P_t[0:3, 0:3], P_t[3:6, 3:6], P_t

# def propagate_covariance(
#     r_sat: np.ndarray,
#     v_sat: np.ndarray,
#     P_pos: np.ndarray,
#     P_vel: np.ndarray,
#     dt: float
# ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
#     """
#     Smart wrapper: prefer CW analytic prop if orbit is near-circular (radial velocity small),
#     else use linearized two-body fallback.
#     Returns (P_pos_t, P_vel_t, P_full_t)
#     """
#     rnorm = np.linalg.norm(r_sat)
#     vnorm = np.linalg.norm(v_sat)
#     if rnorm == 0 or vnorm == 0:
#         # degenerate
#         return propagate_covariance_linear_approx(r_sat, v_sat, P_pos, P_vel, dt)

#     radial_vel = float(np.dot(r_sat, v_sat) / rnorm)
#     # heuristic: radial velocity small relative to orbital speed -> near-circular
#     if abs(radial_vel) <= 0.05 * vnorm:
#         try:
#             return propagate_covariance_cw(r_sat, v_sat, P_pos, P_vel, dt)
#         except Exception:
#             # fallback to linear if anything goes wrong
#             return propagate_covariance_linear_approx(r_sat, v_sat, P_pos, P_vel, dt)
#     else:
#         return propagate_covariance_linear_approx(r_sat, v_sat, P_pos, P_vel, dt


# src/physics/covariance.py
"""
Covariance propagation utilities for orbital conjunction assessment.
Supports:
- Clohessy-Wiltshire (CW) analytic propagation for near-circular orbits
- Linearized two-body Taylor approximation as fallback
- Smart switching based on orbit eccentricity heuristic
- Helper to make matrices SPD (symmetric positive definite) for Cholesky stability
"""

import numpy as np
from typing import Tuple
from math import isfinite
from engine.config.settings import GM  # assuming this is Earth's GM constant


def make_spd(A: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """
    Ensure matrix A is symmetric positive definite by eigenvalue clipping.
    Small helper used before Cholesky or other decompositions to avoid LinAlgError
    due to numerical noise or tiny negative eigenvalues.

    Args:
        A: Input matrix (will be symmetrized)
        eps: Minimum eigenvalue floor (default 1e-8)

    Returns:
        Nearest SPD version of A
    """
    A = np.atleast_2d(np.asarray(A, dtype=float))
    # Force symmetry
    A = 0.5 * (A + A.T)
    
    try:
        vals, vecs = np.linalg.eigh(A)
    except Exception:
        # Very ill-conditioned → just add jitter
        return A + np.eye(A.shape[0]) * eps
    
    # Clip negative / tiny eigenvalues
    vals_clipped = np.clip(vals, eps, None)
    
    # Reconstruct
    return vecs @ np.diag(vals_clipped) @ vecs.T


def _hill_frame_basis(r_sat: np.ndarray, v_sat: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute Hill (RSW) frame basis vectors:
      er = radial (r / ||r||)
      ey = along-track (cross product direction)
      ez = cross-track (h / ||h||)
    """
    r_sat = np.asarray(r_sat, dtype=float)
    v_sat = np.asarray(v_sat, dtype=float)

    r_norm = np.linalg.norm(r_sat)
    if r_norm < 1e-10:
        raise ValueError("Zero satellite position vector in Hill basis")

    er = r_sat / r_norm

    h = np.cross(r_sat, v_sat)
    h_norm = np.linalg.norm(h)

    if h_norm < 1e-10:
        # Degenerate angular momentum → pick arbitrary ez
        arb = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(arb, er)) > 0.99:
            arb = np.array([0.0, 1.0, 0.0])
        ez = np.cross(er, arb)
        ez /= np.linalg.norm(ez)
    else:
        ez = h / h_norm

    ey = np.cross(ez, er)
    ey /= np.linalg.norm(ey)

    return er, ey, ez


def _cw_state_at_t(x0, y0, z0, vx0, vy0, vz0, n: float, t: float):
    """
    Analytic Clohessy-Wiltshire solution for position & velocity at time t.
    Used to build STM columns.
    """
    nt = n * t
    cosnt = np.cos(nt)
    sinnt = np.sin(nt)

    x = (4.0 - 3.0 * cosnt) * x0 + (sinnt / n) * vx0 + (2.0 / n) * (1.0 - cosnt) * vy0
    y = 6.0 * (sinnt - nt) * x0 + y0 + (2.0 / n) * (cosnt - 1.0) * vx0 + (1.0 / n) * (4.0 * sinnt - 3.0 * nt) * vy0
    z = z0 * cosnt + (sinnt / n) * vz0

    vx = 3.0 * n * sinnt * x0 + cosnt * vx0 + 2.0 * sinnt * vy0
    vy = 6.0 * n * (cosnt - 1.0) * x0 - 2.0 * sinnt * vx0 + (4.0 * cosnt - 3.0) * vy0
    vz = -n * sinnt * z0 + cosnt * vz0

    return np.array([x, y, z]), np.array([vx, vy, vz])


def _cw_state_transition_matrix(n: float, t: float) -> np.ndarray:
    """
    6×6 Clohessy-Wiltshire state transition matrix Phi(t) in Hill frame.
    Built by evaluating analytic solution for unit basis vectors.
    """
    Phi = np.zeros((6, 6), dtype=float)

    # Position basis (x0, y0, z0 unit vectors)
    for i in range(3):
        init_pos = np.zeros(3)
        init_pos[i] = 1.0
        pos_t, vel_t = _cw_state_at_t(*init_pos, 0.0, 0.0, 0.0, n, t)
        Phi[0:3, i] = pos_t
        Phi[3:6, i] = vel_t

    # Velocity basis (vx0, vy0, vz0 unit vectors)
    for j in range(3):
        init_vel = np.zeros(3)
        init_vel[j] = 1.0
        pos_t, vel_t = _cw_state_at_t(0.0, 0.0, 0.0, *init_vel, n, t)
        Phi[0:3, 3 + j] = pos_t
        Phi[3:6, 3 + j] = vel_t

    return Phi


def propagate_covariance_cw(
    r_sat: np.ndarray,
    v_sat: np.ndarray,
    P_pos: np.ndarray,
    P_vel: np.ndarray,
    dt: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Propagate position & velocity covariance using analytic CW equations
    (valid for near-circular orbits in Hill frame).
    
    Returns: (P_pos_t, P_vel_t, P_full_6x6_t) at time t = dt
    """
    r_sat = np.asarray(r_sat, dtype=float)
    v_sat = np.asarray(v_sat, dtype=float)
    P_pos = make_spd(P_pos)   # ensure SPD
    P_vel = make_spd(P_vel)

    r0 = np.linalg.norm(r_sat)
    if r0 < 1e-6 or not isfinite(r0):
        raise ValueError("Invalid satellite radius for CW propagation")

    n = np.sqrt(GM / r0**3)   # mean motion

    er, ey, ez = _hill_frame_basis(r_sat, v_sat)
    R_hill2eci = np.column_stack((er, ey, ez))   # columns = basis vectors
    R_eci2hill = R_hill2eci.T

    # Initial 6×6 covariance in ECI
    P0 = np.block([
        [P_pos,     np.zeros((3,3))],
        [np.zeros((3,3)), P_vel   ]
    ])

    # Transform to Hill frame
    T = np.block([
        [R_eci2hill, np.zeros((3,3))],
        [np.zeros((3,3)), R_eci2hill]
    ])
    P0_hill = T @ P0 @ T.T

    # Propagate in Hill frame
    Phi_hill = _cw_state_transition_matrix(n, dt)
    P_hill_t = Phi_hill @ P0_hill @ Phi_hill.T

    # Back to ECI
    Tinv = np.block([
        [R_hill2eci, np.zeros((3,3))],
        [np.zeros((3,3)), R_hill2eci]
    ])
    P_t = Tinv @ P_hill_t @ Tinv.T

    return P_t[0:3, 0:3], P_t[3:6, 3:6], P_t


def _build_linearized_A(r: np.ndarray) -> np.ndarray:
    """
    Linearized dynamics matrix A for two-body problem:
      [ 0   I ]
      [ dadr 0 ]
    where dadr = Jacobian of acceleration wrt position
    """
    r = np.asarray(r, dtype=float)
    rnorm = np.linalg.norm(r)
    if rnorm < 1e-10:
        raise ValueError("Zero radius in linearized dynamics matrix")

    I3 = np.eye(3)
    r_outer = np.outer(r, r)

    dadr = -GM * (I3 / rnorm**3 - 3.0 * r_outer / rnorm**5)

    A = np.zeros((6, 6))
    A[0:3, 3:6] = I3
    A[3:6, 0:3] = dadr

    return A


def _phi_approx_from_A(A: np.ndarray, dt: float) -> np.ndarray:
    """
    Second-order Taylor approximation of state transition matrix:
    Φ(t) ≈ I + A t + (1/2) (A t)^2
    Safe for small dt.
    """
    I6 = np.eye(6)
    Adt = A * dt
    return I6 + Adt + 0.5 * (Adt @ Adt)


def propagate_covariance_linear_approx(
    r_sat: np.ndarray,
    v_sat: np.ndarray,
    P_pos: np.ndarray,
    P_vel: np.ndarray,
    dt: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fallback propagation using linearized two-body dynamics.
    """
    P_pos = make_spd(P_pos)
    P_vel = make_spd(P_vel)

    A = _build_linearized_A(r_sat)
    Phi = _phi_approx_from_A(A, dt)

    P0 = np.block([
        [P_pos,     np.zeros((3,3))],
        [np.zeros((3,3)), P_vel   ]
    ])

    P_t = Phi @ P0 @ Phi.T

    return P_t[0:3, 0:3], P_t[3:6, 3:6], P_t


def propagate_covariance(
    r_sat: np.ndarray,
    v_sat: np.ndarray,
    P_pos: np.ndarray,
    P_vel: np.ndarray,
    dt: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Main entry point: attempts CW analytic propagation if orbit appears near-circular,
    falls back to linearized two-body approximation otherwise.

    Returns: (P_pos_t, P_vel_t, P_full_6x6_t)
    """
    r_sat = np.asarray(r_sat, dtype=float)
    v_sat = np.asarray(v_sat, dtype=float)

    r_norm = np.linalg.norm(r_sat)
    v_norm = np.linalg.norm(v_sat)

    if r_norm < 1e-6 or v_norm < 1e-6 or not isfinite(r_norm):
        return propagate_covariance_linear_approx(r_sat, v_sat, P_pos, P_vel, dt)

    # Heuristic: radial velocity fraction small → near-circular → use CW
    radial_vel = np.dot(r_sat, v_sat) / r_norm
    if abs(radial_vel) <= 0.05 * v_norm:
        try:
            return propagate_covariance_cw(r_sat, v_sat, P_pos, P_vel, dt)
        except Exception as e:
            print(f"CW propagation failed: {e}. Falling back to linear approx.")
            return propagate_covariance_linear_approx(r_sat, v_sat, P_pos, P_vel, dt)
    else:
        return propagate_covariance_linear_approx(r_sat, v_sat, P_pos, P_vel, dt)

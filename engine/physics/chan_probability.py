# # src/physics/chan_probability.py  niche wala fully working hai 
# import numpy as np
# from typing import Tuple

# def _plane_basis_from_vector(u: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
#     """
#     Given unit vector u (3,), find two orthonormal basis vectors e1,e2 spanning plane orthogonal to u.
#     """
#     u = np.array(u, dtype=float)
#     if np.linalg.norm(u) == 0:
#         raise ValueError("Zero vector for plane normal")
#     u = u / np.linalg.norm(u)
#     # pick arbitrary vector not parallel to u
#     arb = np.array([1.0, 0.0, 0.0])
#     if abs(np.dot(arb, u)) > 0.9:
#         arb = np.array([0.0, 1.0, 0.0])
#     e1 = np.cross(u, arb)
#     e1 = e1 / np.linalg.norm(e1)
#     e2 = np.cross(u, e1)
#     e2 = e2 / np.linalg.norm(e2)
#     return e1, e2

# def chan_collision_probability(
#     rel_pos: np.ndarray,
#     rel_vel: np.ndarray,
#     cov_rel: np.ndarray,
#     collision_radius: float,
#     n_theta: int = 48,
#     n_r: int = 96
# ) -> float:
#     """
#     Compute approximate Chan-style collision probability by projecting relative position & covariance
#     onto the plane orthogonal to relative velocity (b-plane) and numerically integrating the 2D Gaussian
#     over the disk of radius = collision_radius.

#     rel_pos: full 3D relative position vector (ECI) at tca (m)
#     rel_vel: full 3D relative velocity vector (ECI) at tca (m/s)
#     cov_rel: 3x3 relative position covariance matrix (m^2)
#     collision_radius: scalar radius (m)
#     """
#     rel_pos = np.array(rel_pos, dtype=float)
#     rel_vel = np.array(rel_vel, dtype=float)
#     cov_rel = np.array(cov_rel, dtype=float)

#     vnorm = np.linalg.norm(rel_vel)
#     if vnorm < 1e-8:
#         # fallback: use isotropic projection
#         # project onto plane orthogonal to arbitrary axis
#         rel_vel = np.array([1.0, 0.0, 0.0])
#         vnorm = 1.0

#     u = rel_vel / vnorm
#     e1, e2 = _plane_basis_from_vector(u)

#     # project mean into plane coordinates
#     mu2 = np.array([np.dot(rel_pos, e1), np.dot(rel_pos, e2)], dtype=float)

#     # project covariance into plane: 2x2
#     C11 = float(e1.dot(cov_rel.dot(e1)))
#     C12 = float(e1.dot(cov_rel.dot(e2)))
#     C22 = float(e2.dot(cov_rel.dot(e2)))
#     C2 = np.array([[C11, C12], [C12, C22]], dtype=float)

#     # regularize if necessary
#     eps = 1e-6 * max(np.trace(C2), 1.0)
#     C2 += np.eye(2) * eps

#     detC2 = np.linalg.det(C2)
#     if detC2 <= 0 or not np.isfinite(detC2):
#         # fallback to isotropic sigma from trace
#         sigma = np.sqrt(np.trace(cov_rel) / 3.0)
#         if sigma <= 0:
#             sigma = 100.0
#         # 2D isotropic density integral over disk with center offset mu2
#         # approximate via simple formula using radial Gaussian (crude fallback)
#         d = np.linalg.norm(mu2)
#         return float(np.exp(-(d ** 2) / (2.0 * sigma ** 2)))

#     invC2 = np.linalg.inv(C2)
#     norm_prefactor = 1.0 / (2.0 * np.pi * np.sqrt(detC2))

#     # polar integration grids
#     thetas = np.linspace(0.0, 2.0 * np.pi, n_theta, endpoint=False)
#     rs = np.linspace(0.0, collision_radius, n_r)

#     # precompute r weights for trapezoid (simple)
#     # perform integration: integral = ∫_0^{2π} ∫_0^R r * f(r,theta) dr dtheta
#     total = 0.0
#     for theta in thetas:
#         ux = np.cos(theta)
#         uy = np.sin(theta)
#         # vector of unit direction in 2D plane basis
#         # radial integration values
#         vals = []
#         for r in rs:
#             point = np.array([r * ux, r * uy])  # coordinates in plane
#             dvec = point - mu2
#             exponent = -0.5 * float(dvec.dot(invC2.dot(dvec)))
#             vals.append(np.exp(exponent) * r)
#         # trapezoidal integrate over r
#         vals = np.array(vals, dtype=float)
#         integral_r = 0.0
#         if n_r > 1:
#             integral_r = np.trapz(vals, rs)
#         else:
#             integral_r = vals[0] * collision_radius
#         total += integral_r

#     integral = (2.0 * np.pi / float(len(thetas))) * total
#     prob = norm_prefactor * integral
#     # safety clipping
#     if not np.isfinite(prob):
#         prob = 0.0
#     prob = max(0.0, min(1.0, prob))
#     return float(prob)

# src/physics/chan_probability.py
"""
Chan-style collision probability calculation in the B-plane.

Projects the 3D relative state and covariance into the 2D plane perpendicular
to the relative velocity vector (B-plane), then numerically integrates the
2D Gaussian probability density over a circular disk of given collision radius.

This implementation uses vectorized numpy operations (meshgrid + trapz)
instead of nested Python loops.
"""

import numpy as np
from typing import Tuple


def _plane_basis_from_vector(u: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Given a unit vector u (3,), compute two orthonormal vectors e1, e2
    that span the plane orthogonal to u.

    Used to define the B-plane coordinate system.
    """
    u = np.asarray(u, dtype=float)
    norm_u = np.linalg.norm(u)
    if norm_u < 1e-12:
        raise ValueError("Cannot define plane basis from (near-)zero vector")

    u = u / norm_u

    # Choose an arbitrary vector not (too) parallel to u
    arb = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(arb, u)) > 0.95:
        arb = np.array([0.0, 1.0, 0.0])

    e1 = np.cross(u, arb)
    e1 /= np.linalg.norm(e1)

    e2 = np.cross(u, e1)
    e2 /= np.linalg.norm(e2)

    return e1, e2


def chan_collision_probability(
    rel_pos: np.ndarray,
    rel_vel: np.ndarray,
    cov_rel: np.ndarray,
    collision_radius: float,
    n_theta: int = 64,
    n_r: int = 120
) -> float:
    """
    Approximate collision probability using Chan's method (B-plane projection
    + numerical integration of 2D Gaussian over a disk).

    Parameters
    ----------
    rel_pos : array-like, shape (3,)
        Relative position vector at TCA (m) in ECI
    rel_vel : array-like, shape (3,)
        Relative velocity vector at TCA (m/s) in ECI
    cov_rel : array-like, shape (3,3)
        Relative position covariance matrix at TCA (m²)
    collision_radius : float
        Sum of object radii (hard-body radius) [m]
    n_theta : int, optional
        Number of angular points (default: 64)
    n_r : int, optional
        Number of radial points (default: 120)

    Returns
    -------
    float
        Estimated collision probability (clipped to [0,1])
    """
    rel_pos = np.asarray(rel_pos, dtype=float)
    rel_vel = np.asarray(rel_vel, dtype=float)
    cov_rel = np.asarray(cov_rel, dtype=float)

    if rel_pos.shape != (3,) or rel_vel.shape != (3,) or cov_rel.shape != (3, 3):
        raise ValueError("rel_pos and rel_vel must be (3,), cov_rel must be (3,3)")

    vnorm = np.linalg.norm(rel_vel)
    if vnorm < 1e-6:
        # Very low relative velocity → fallback to isotropic approximation
        sigma = np.sqrt(np.trace(cov_rel) / 3.0)
        sigma = max(sigma, 10.0)  # avoid division by zero or tiny values
        d = np.linalg.norm(rel_pos)
        p = np.exp(-0.5 * (d / sigma) ** 2)
        return float(np.clip(p, 0.0, 1.0))

    # Unit vector along relative velocity (defines normal to B-plane)
    u = rel_vel / vnorm

    # Orthonormal basis in B-plane
    e1, e2 = _plane_basis_from_vector(u)

    # Mean position in 2D B-plane coordinates
    mu_x = np.dot(rel_pos, e1)
    mu_y = np.dot(rel_pos, e2)
    mu2 = np.array([mu_x, mu_y])

    # Project 3×3 covariance into 2×2 B-plane covariance
    C11 = e1 @ cov_rel @ e1
    C12 = e1 @ cov_rel @ e2
    C22 = e2 @ cov_rel @ e2
    C2 = np.array([[C11, C12], [C12, C22]])

    # Regularization (helps when covariance is near-singular)
    trace = np.trace(C2)
    eps = 1e-8 * max(trace, 1.0)
    C2 += eps * np.eye(2)

    detC2 = np.linalg.det(C2)
    if detC2 <= 0 or not np.isfinite(detC2):
        # Fallback — crude isotropic Gaussian
        sigma = np.sqrt(trace / 2.0) if trace > 0 else 100.0
        d = np.linalg.norm(mu2)
        p = np.exp(-0.5 * (d / sigma) ** 2)
        return float(np.clip(p, 0.0, 1.0))

    invC2 = np.linalg.inv(C2)
    a, b, c = invC2[0, 0], invC2[0, 1], invC2[1, 1]

    # Build polar coordinate grid (vectorized)
    thetas = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)
    rs = np.linspace(0, collision_radius, n_r)

    # meshgrid → shapes (n_r, n_theta)
    th_grid, r_grid = np.meshgrid(thetas, rs, indexing='xy')

    # Transpose so integration axes are convenient
    ux = np.cos(th_grid).T      # (n_theta, n_r)
    uy = np.sin(th_grid).T
    rmat = r_grid.T             # (n_theta, n_r)

    # Cartesian coordinates in B-plane (relative to mean)
    x = rmat * ux - mu_x
    y = rmat * uy - mu_y

    # Quadratic form of 2D Gaussian
    exponent = -0.5 * (a * x**2 + 2 * b * x * y + c * y**2)
    density = np.exp(exponent)

    # Integrand for polar coordinates: density * r
    integrand = density * rmat

    # Integrate first along radius (axis=1), then along theta (axis=0)
    int_r = np.trapz(integrand, rs, axis=1)          # shape (n_theta,)
    integral = np.trapz(int_r, thetas)               # scalar

    # Normalization constant of 2D Gaussian
    norm = 1.0 / (2.0 * np.pi * np.sqrt(detC2))

    prob = norm * integral

    # Final safety clipping
    if not np.isfinite(prob):
        prob = 0.0
    prob = max(0.0, min(1.0, prob))

    return float(prob)
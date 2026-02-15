
"""
Engine-2: High-fidelity physics-based collision confirmation engine (Stage-2).

Features:
- RK45 (Dormand-Prince) adaptive integrator for accurate propagation.
- Composite force model with J2/J3/J4, atmospheric drag, SRP, and third-body (Sun/Moon).
- Adaptive timestep refinement near close approach.
- Energy-drift reporting only when the propagation is conservative (no drag/SRP/third-body).
- Covariance-aware Monte Carlo (uses Entity.cov_pos / cov_vel).
"""
from typing import Optional, Dict, Any
import numpy as np

from engine.physics.state import State
from engine.physics.entity import Entity
from engine.physics.forces import (
    NewtonianGravity,
    J2Perturbation,
    J3Perturbation,
    J4Perturbation,
    AtmosphericDrag,
    SolarRadiationPressure,
    ThirdBodyForce,
    CompositeForce,
)
from engine.physics.solver_rk45 import RK45Solver
from engine.physics.utils import specific_energy
from engine.config.settings import COLLISION_RADIUS, DANGER_RADIUS
from engine.core.engine1 import Engine1

# small numeric tolerance
_MIN_DT = 1e-4


def _composite_has_nonconservative(force: CompositeForce) -> bool:
    """
    Heuristic: consider a composite non-conservative if it contains AtmosphericDrag,
    SolarRadiationPressure, or ThirdBodyForce (third-body introduces multi-body energy
    exchange relative to two-body specific energy).
    """
    for m in getattr(force, "models", []):
        if isinstance(m, (AtmosphericDrag, SolarRadiationPressure, ThirdBodyForce)):
            return True
    return False


class Engine2:
    """
    Engine-2: Confirmation engine. Focus on accuracy and diagnostics.
    """
    def __init__(self, dt: float = 1.0, adaptive_threshold: float = 5000.0, enable_drag: bool = True,
                 enable_srp: bool = False, enable_third_body: bool = True):
        """
        dt: base timestep in seconds (used as nominal step)
        adaptive_threshold: refine timestep when relative distance < this (meters)
        enable_drag: include atmospheric drag model
        enable_srp: include solar radiation pressure
        enable_third_body: include Sun/Moon third-body gravity
        """
        self.dt_base = float(dt)
        self.adaptive_threshold = float(adaptive_threshold)
        self.enable_drag = bool(enable_drag)
        self.enable_srp = bool(enable_srp)
        self.enable_third_body = bool(enable_third_body)

        # Engine-1 instance for optional escalation checks (lightweight screening)
        self.engine1 = Engine1()

    def _get_force_model(self, ballistic_coeff: float):
        """
        Build CompositeForce for an object given ballistic coefficient.
        Order: central + J2/J3/J4, optional drag, optional SRP, optional third-body wrapper.
        """
        models = [
            NewtonianGravity(),
            J2Perturbation(),
            J3Perturbation(),
            J4Perturbation(),
        ]
        if self.enable_drag:
            models.append(AtmosphericDrag(ballistic_coeff))
        if self.enable_srp:
            # default Am and Cr are tunable at Engine-2 call-time by replacing this model
            models.append(SolarRadiationPressure(Cr=1.2, area_mass_ratio=getattr(ballistic_coeff, "area_mass_ratio", 0.02) if False else 0.02))
        if self.enable_third_body:
            models.append(ThirdBodyForce(include_sun=True, include_moon=True))
        return CompositeForce(*models)

    def run(self, satellite: Entity, debris: Entity, duration: float, use_engine1_escalation: bool = True) -> Dict[str, Any]:
        """
        Run a single high-fidelity propagation for the given duration (seconds).

        Returns:
          {
            "closest_time": float (seconds from start),
            "miss_distance": float (meters),
            "relative_velocity": float (m/s) at closest approach,
            "collision": bool,
            "conjunction": bool (within DANGER_RADIUS),
            "energy_drift_sat_percent": float | None,
            "energy_drift_deb_percent": float | None,
            "note": optional str
          }
        """
        # Optional quick escalation check using Engine-1 (helps skip unnecessary high-fidelity runs)
        if use_engine1_escalation:
            try:
                screening = self.engine1.run(satellite, [debris], dt=self.dt_base, steps=max(1, int(duration / self.dt_base)))
                # engine1.run returns dict with "screening" list
                if isinstance(screening, dict) and "screening" in screening:
                    recs = screening["screening"]
                    if recs and isinstance(recs, list):
                        # if screening says zero probability, skip confirmation
                        p = float(recs[0].get("probability", recs[0].get("prob", 0.0)))
                        if p <= 0.0:
                            return {
                                "closest_time": None,
                                "miss_distance": float(recs[0].get("miss_distance", float("inf"))),
                                "relative_velocity": None,
                                "collision": False,
                                "conjunction": False,
                                "energy_drift_sat_percent": None,
                                "energy_drift_deb_percent": None,
                                "note": "Skipped by Engine-1 escalation (screening indicated no risk)."
                            }
            except Exception:
                # If Engine-1 fails for some reason, continue to run Engine-2.
                pass

        # Initialize states
        sat_state = State(satellite.position.copy(), satellite.velocity.copy())
        deb_state = State(debris.position.copy(), debris.velocity.copy())

        # Configure force models and RK45 solvers
        force_sat = self._get_force_model(satellite.ballistic_coeff)
        force_deb = self._get_force_model(debris.ballistic_coeff)

        solver_sat = RK45Solver(force_sat, rtol=1e-8, atol=1e-10, dt_min=_MIN_DT, dt_max=10.0)
        solver_deb = RK45Solver(force_deb, rtol=1e-8, atol=1e-10, dt_min=_MIN_DT, dt_max=10.0)

        # Determine whether propagation is conservative for energy-drift reporting
        nonconservative = _composite_has_nonconservative(force_sat) or _composite_has_nonconservative(force_deb)

        init_e_sat = specific_energy(sat_state) if not nonconservative else None
        init_e_deb = specific_energy(deb_state) if not nonconservative else None

        t = 0.0
        min_dist = float("inf")
        t_min: Optional[float] = 0.0
        rel_v_at_min: Optional[float] = None

        # initial distance check
        rel_pos = sat_state.r - deb_state.r
        dist0 = float(np.linalg.norm(rel_pos))
        if dist0 < min_dist:
            min_dist = dist0
            t_min = 0.0
            rel_v_at_min = float(np.linalg.norm(sat_state.v - deb_state.v))

        # Propagation loop with adaptive timestep
        while t < duration:
            rel_pos = sat_state.r - deb_state.r
            dist = float(np.linalg.norm(rel_pos))

            # choose dt: refine when close
            if dist < self.adaptive_threshold:
                current_dt = max(self.dt_base / 10.0, _MIN_DT)
            else:
                current_dt = self.dt_base

            # avoid overshoot
            current_dt = min(current_dt, duration - t)

            # Step both bodies (RK45 accepts (state, dt, t0))
            sat_state = solver_sat.step(sat_state, current_dt, t)
            deb_state = solver_deb.step(deb_state, current_dt, t)

            t += current_dt

            # evaluate miss
            rel_pos = sat_state.r - deb_state.r
            dist = float(np.linalg.norm(rel_pos))
            if dist < min_dist:
                min_dist = dist
                t_min = float(t)
                rel_v_at_min = float(np.linalg.norm(sat_state.v - deb_state.v))

        collision = bool(min_dist <= COLLISION_RADIUS)
        conjunction = bool(min_dist <= DANGER_RADIUS)

        # Energy drift if conservative (no drag/SRP/third-body)
        if not nonconservative:
            final_e_sat = specific_energy(sat_state)
            final_e_deb = specific_energy(deb_state)
            drift_sat = (abs(final_e_sat - init_e_sat) / abs(init_e_sat) * 100.0) if init_e_sat not in (0, None) else 0.0
            drift_deb = (abs(final_e_deb - init_e_deb) / abs(init_e_deb) * 100.0) if init_e_deb not in (0, None) else 0.0
        else:
            drift_sat = None
            drift_deb = None

        return {
            "closest_time": t_min,
            "miss_distance": min_dist,
            "relative_velocity": rel_v_at_min,
            "collision": collision,
            "conjunction": conjunction,
            "energy_drift_sat_percent": drift_sat,
            "energy_drift_deb_percent": drift_deb,
        }

    def run_monte_carlo(self, satellite: Entity, debris: Entity, duration: float, N: int = 500, use_engine1_escalation: bool = False) -> Dict[str, Any]:
        """
        Monte Carlo: perturb initial states using the provided covariance matrices in Entity (pos & vel).
        Vectorized sampling for perturbations, reusing Cholesky factors when possible.
        """
        collisions = 0
        conjunctions = 0
        min_dists = []

        cov_pos_sat = np.atleast_2d(satellite.cov_pos)
        cov_vel_sat = np.atleast_2d(satellite.cov_vel)
        cov_pos_deb = np.atleast_2d(debris.cov_pos)
        cov_vel_deb = np.atleast_2d(debris.cov_vel)

        # Try Cholesky (regularize SPD if necessary) - use make_spd if available
        use_cholesky = False
        try:
            from engine.physics.covariance import make_spd
            cov_pos_sat_spd = make_spd(cov_pos_sat)
            cov_vel_sat_spd = make_spd(cov_vel_sat)
            cov_pos_deb_spd = make_spd(cov_pos_deb)
            cov_vel_deb_spd = make_spd(cov_vel_deb)

            L_pos_sat = np.linalg.cholesky(cov_pos_sat_spd)
            L_vel_sat = np.linalg.cholesky(cov_vel_sat_spd)
            L_pos_deb = np.linalg.cholesky(cov_pos_deb_spd)
            L_vel_deb = np.linalg.cholesky(cov_vel_deb_spd)
            use_cholesky = True
        except Exception:
            # fallback: we'll use numpy multivariate draws per sample
            use_cholesky = False

        if use_cholesky:
            # Vectorized draws: shape (N,3)
            Z_pos_sat = np.random.normal(size=(N, 3))
            Z_vel_sat = np.random.normal(size=(N, 3))
            Z_pos_deb = np.random.normal(size=(N, 3))
            Z_vel_deb = np.random.normal(size=(N, 3))

            pert_pos_sat_all = Z_pos_sat @ L_pos_sat.T
            pert_vel_sat_all = Z_vel_sat @ L_vel_sat.T
            pert_pos_deb_all = Z_pos_deb @ L_pos_deb.T
            pert_vel_deb_all = Z_vel_deb @ L_vel_deb.T

            for i in range(N):
                pert_pos_sat = pert_pos_sat_all[i]
                pert_vel_sat = pert_vel_sat_all[i]
                pert_pos_deb = pert_pos_deb_all[i]
                pert_vel_deb = pert_vel_deb_all[i]

                sat_pert = Entity(
                    position=satellite.position + pert_pos_sat,
                    velocity=satellite.velocity + pert_vel_sat,
                    ballistic_coeff=satellite.ballistic_coeff,
                    cov_pos=cov_pos_sat,
                    cov_vel=cov_vel_sat,
                )
                deb_pert = Entity(
                    position=debris.position + pert_pos_deb,
                    velocity=debris.velocity + pert_vel_deb,
                    ballistic_coeff=debris.ballistic_coeff,
                    cov_pos=cov_pos_deb,
                    cov_vel=cov_vel_deb,
                )

                res = self.run(sat_pert, deb_pert, duration, use_engine1_escalation=use_engine1_escalation)
                min_dist = float(res.get("miss_distance", float("inf")))
                min_dists.append(min_dist)
                if min_dist <= COLLISION_RADIUS:
                    collisions += 1
                if min_dist <= DANGER_RADIUS:
                    conjunctions += 1
        else:
            # Safe fallback (original style but vectorized sampling not available)
            for i in range(N):
                pert_pos_sat = np.random.multivariate_normal(np.zeros(3), cov_pos_sat)
                pert_vel_sat = np.random.multivariate_normal(np.zeros(3), cov_vel_sat)
                pert_pos_deb = np.random.multivariate_normal(np.zeros(3), cov_pos_deb)
                pert_vel_deb = np.random.multivariate_normal(np.zeros(3), cov_vel_deb)

                sat_pert = Entity(
                    position=satellite.position + pert_pos_sat,
                    velocity=satellite.velocity + pert_vel_sat,
                    ballistic_coeff=satellite.ballistic_coeff,
                    cov_pos=cov_pos_sat,
                    cov_vel=cov_vel_sat,
                )
                deb_pert = Entity(
                    position=debris.position + pert_pos_deb,
                    velocity=debris.velocity + pert_vel_deb,
                    ballistic_coeff=debris.ballistic_coeff,
                    cov_pos=cov_pos_deb,
                    cov_vel=cov_vel_deb,
                )

                res = self.run(sat_pert, deb_pert, duration, use_engine1_escalation=use_engine1_escalation)
                min_dist = float(res.get("miss_distance", float("inf")))
                min_dists.append(min_dist)
                if min_dist <= COLLISION_RADIUS:
                    collisions += 1
                if min_dist <= DANGER_RADIUS:
                    conjunctions += 1

        coll_prob = collisions / float(N)
        conj_prob = conjunctions / float(N)
        avg_min = float(np.mean(min_dists)) if min_dists else float("inf")
        std_min = float(np.std(min_dists)) if min_dists else 0.0

        return {
            "collision_probability": coll_prob,
            "conjunction_probability": conj_prob,
            "average_miss_distance": avg_min,
            "std_miss_distance": std_min,
            "num_simulations": int(N),
        }

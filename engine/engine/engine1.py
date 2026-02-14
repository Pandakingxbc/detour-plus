

import numpy as np
from engine.config import settings
from engine.config.settings import (
    ENGINE1_DT,
    STEPS,
    COLLISION_RADIUS,
    RISK_THRESHOLD,
    AVOIDANCE_DELTA_V,
    ENGINE1_LOOKAHEAD,
    ENGINE1_CW_SAMPLES,
    ESCALATION_THRESHOLD,
)
from engine.physics.probability import collision_probability
from engine.physics.cw_relative import cw_time_of_closest_approach
from engine.physics.state import State
from engine.physics.forces import NewtonianGravity, CompositeForce
from engine.physics.solver import RK4Solver
from engine.physics.covariance import propagate_covariance


class Engine1:
    """
    ENGINE-1 (STAGE-1): Fast probabilistic screening engine.

    Design goals:
    - Conservative (avoid false negatives)
    - Physics-aware (CW + covariance propagation to TCA)
    - Probability-based escalation (Chan / B-plane; gaussian fallback)
    - NOT for maneuver decisions (Engine-2 / Engine-3 handle that)
    """

    def __init__(self):
        force_model = CompositeForce(NewtonianGravity())
        self.solver = RK4Solver(force_model)

    def run(self, satellite, debris_list, dt: float = ENGINE1_DT, steps: int = STEPS):
        """
        Run fast screening on a list of debris objects against a single satellite.

        Returns:
          {
            "screening": results_list,
            "summary": { min_miss_distance, max_probability, max_risk, escalate },
            "positions_sat": positions for animation,
            "positions_debris": positions for animation
          }
        """
        results = []
        positions_sat = []
        positions_debris = [[] for _ in debris_list]

        state_sat = State(satellite.position.copy(), satellite.velocity.copy())
        states_deb = [State(d.position.copy(), d.velocity.copy()) for d in debris_list]

        # Respect CLI / runtime override if present; ensure consistent horizon
        # horizon_setting = float(getattr(settings, "LOOKAHEAD_SEC", ENGINE1_LOOKAHEAD))
        # horizon = min(float(horizon_setting), float(ENGINE1_LOOKAHEAD), float(dt * steps))
        horizon_setting = float(getattr(settings, "LOOKAHEAD_SEC", dt * steps))
        horizon = min(horizon_setting, dt * steps)

        print(f"[Engine1] Using horizon: {horizon}s")

        # Phase A — one-time analysis (physics, CW + conservative screening)
        analysis = {}
        for i, debris in enumerate(debris_list):
            # Compute TCA using CW sampling (vectorized analytic CW)
            tca, miss, rel_pos_at_tca, rel_vel_at_tca = cw_time_of_closest_approach(
                satellite.position,
                satellite.velocity,
                debris.position,
                debris.velocity,
                horizon=horizon,
                n_samples=ENGINE1_CW_SAMPLES,
            )

            # If the TCA is in the past or outside our screening horizon, skip (no alert)
            if tca < 0.0 or tca > horizon:
                analysis[i] = {
                    "tca": float(tca),
                    "miss": float(miss),
                    "prob": 0.0,
                    "rel_vel": float(np.linalg.norm(rel_vel_at_tca)),
                    "flag": False,
                }
                continue

            # Propagate covariance forward to TCA (wrapper chooses CW or linear)
            prop_t = float(max(0.0, tca))
            try:
                Ppos_sat_t, Pvel_sat_t, P6_sat_t = propagate_covariance(
                    satellite.position,
                    satellite.velocity,
                    satellite.cov_pos,
                    satellite.cov_vel,
                    prop_t,
                )
            except Exception:
                # Fallback to initial covariances if propagation fails
                Ppos_sat_t = np.atleast_2d(satellite.cov_pos)
                Pvel_sat_t = np.atleast_2d(satellite.cov_vel)
                P6_sat_t = None

            try:
                Ppos_deb_t, Pvel_deb_t, P6_deb_t = propagate_covariance(
                    debris.position,
                    debris.velocity,
                    debris.cov_pos,
                    debris.cov_vel,
                    prop_t,
                )
            except Exception:
                Ppos_deb_t = np.atleast_2d(debris.cov_pos)
                Pvel_deb_t = np.atleast_2d(debris.cov_vel)
                P6_deb_t = None

            # Relative position covariance at TCA (assume independent errors)
            cov_rel = Ppos_sat_t + Ppos_deb_t

            # NOTE: Velocity covariance (Pvel_*) is propagated and available for future
            # B-plane or STM refinements; Stage-1 screening uses position covariance only (conservative).

            # --- screening process noise inflation (conservative) ---
            # accounts for unmodeled drag, SRP, execution uncertainty, and model mismatch.
            # Heuristic: growth proportional to propagation time with sensible floor/ceiling.
            q_sigma = max(1.0, 0.01 * prop_t)  # meters (min 1 m; scales with time)
            Q = np.eye(3) * (q_sigma ** 2)
            cov_rel = cov_rel + Q

            # Compute screening probability using Chan / b-plane if possible (collision_probability handles fallback).
            try:
                p = float(
                    collision_probability(
                        miss_distance=miss,
                        cov_rel=cov_rel,
                        rel_pos=rel_pos_at_tca,
                        rel_vel=rel_vel_at_tca,
                        collision_radius=COLLISION_RADIUS,
                    )
                )
            except Exception:
                # Fallback conservative scalar Gaussian if something goes wrong inside the probability module
                try:
                    # simple isotropic sigma fallback from trace
                    sigma = np.sqrt(np.trace(cov_rel) / 3.0)
                    sigma = max(sigma, 1.0)
                    p = float(np.exp(-(miss ** 2) / (2.0 * sigma ** 2)))
                except Exception:
                    p = 0.0

            # Flagging heuristic: primarily probability-driven; distance used as secondary trigger
            flag = (p > RISK_THRESHOLD) or (miss < ESCALATION_THRESHOLD and p > 1e-7)

            analysis[i] = {
                "tca": float(tca),
                "miss": float(miss),
                "prob": float(p),
                "rel_vel": float(np.linalg.norm(rel_vel_at_tca)),
                "flag": bool(flag),
            }

        # Phase B — propagation (for visualization / distance tracking)
        current_time = 0.0
        positions_sat.append(tuple(state_sat.r))
        for i in range(len(debris_list)):
            positions_debris[i].append(tuple(states_deb[i].r))

        # initial record at t=0
        for i, debris in enumerate(debris_list):
            inst_dist = float(np.linalg.norm(state_sat.r - states_deb[i].r))
            rec = analysis.get(i, {"tca": None, "miss": None, "prob": 0.0, "rel_vel": 0.0, "flag": False})
            results.append(
                {
                    "step": 0,
                    "step_time": current_time,
                    "debris_id": getattr(debris, "name", f"debris_{i}"),
                    "distance": inst_dist,
                    "tca": rec["tca"],
                    "miss_distance": rec["miss"],
                    "inside_horizon": (rec["tca"] is not None and 0 <= rec["tca"] <= horizon),
                    "relative_velocity": rec["rel_vel"],
                    "probability": rec["prob"],
                    "risk": rec["prob"],
                    "is_high_risk": rec["flag"],
                }
            )

        effective_steps = int(max(1, np.floor(horizon / dt)))

        for step in range(1, effective_steps + 1):
            state_sat = self.solver.step(state_sat, dt)
            for i in range(len(debris_list)):
                states_deb[i] = self.solver.step(states_deb[i], dt)

            current_time = step * dt
            positions_sat.append(tuple(state_sat.r))
            for i in range(len(debris_list)):
                positions_debris[i].append(tuple(states_deb[i].r))

            for i, debris in enumerate(debris_list):
                inst_dist = float(np.linalg.norm(state_sat.r - states_deb[i].r))
                rec = analysis.get(i, {"tca": None, "miss": None, "prob": 0.0, "rel_vel": 0.0, "flag": False})
                results.append(
                    {
                        "step": step,
                        "step_time": current_time,
                        "debris_id": getattr(debris, "name", f"debris_{i}"),
                        "distance": inst_dist,
                        "tca": rec["tca"],
                        "miss_distance": rec["miss"],
                        "inside_horizon": (rec["tca"] is not None and 0 <= rec["tca"] <= horizon),
                        "relative_velocity": rec["rel_vel"],
                        "probability": rec["prob"],
                        "risk": rec["prob"],
                        "is_high_risk": rec["flag"],
                    }
                )

        # Summary for escalation: consider only records inside horizon
        try:
            min_miss = min((r["miss_distance"] for r in results if r.get("inside_horizon")), default=float("inf"))
        except Exception:
            min_miss = min((r["miss_distance"] for r in results), default=float("inf"))

        max_prob = max((r["probability"] for r in results), default=0.0)
        max_risk = max((r["risk"] for r in results), default=0.0)

        # Escalate if any object inside distance threshold OR probability exceeds configured threshold
        escalate = (min_miss < float(getattr(settings, "ESCALATION_THRESHOLD", ESCALATION_THRESHOLD))) or (
            max_prob > float(getattr(settings, "RISK_THRESHOLD", RISK_THRESHOLD))
        )

        summary = {
            "min_miss_distance": min_miss,
            "max_probability": max_prob,
            "max_risk": max_risk,
            "escalate": bool(escalate),
        }

        return {
            "screening": results,
            "summary": summary,
            "positions_sat": positions_sat,
            "positions_debris": positions_debris,
        }

    def _compute_risk(self, probability, miss_distance, rel_velocity):
        # stable, interpretable screening risk (kept for future extension)
        return float(np.clip(probability, 0.0, 1.0))

    def get_avoidance_suggestion(self, satellite, debris, delta_v_mag=AVOIDANCE_DELTA_V):
        """
        Simple guidance vector suggestion: returns delta-v vector (m/s) in ECI for collision avoidance.
        Note: This is a suggestion only; Engine-3 should perform optimization & fuel accounting.
        """
        rel_vel = debris.velocity - satellite.velocity
        rel_pos = debris.position - satellite.position
        if np.linalg.norm(rel_vel) < 1e-6:
            rel_vel = satellite.velocity  # Fallback

        cross = np.cross(rel_pos, rel_vel)
        n = np.linalg.norm(cross)
        if n < 1e-6:
            arb = np.array([0, 0, 1])
            if np.dot(rel_vel, arb) > 0.999 * np.linalg.norm(rel_vel):
                arb = np.array([1, 0, 0])
            cross = np.cross(rel_vel, arb)
            n = np.linalg.norm(cross)
            if n < 1e-6:
                return np.zeros(3)

        norm = cross / n
        delta_v_mag_ms = delta_v_mag * 1000.0  # km/s -> m/s
        return delta_v_mag_ms * norm

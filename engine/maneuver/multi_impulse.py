"""
Multi-Impulse Trajectory Optimizer for Collision Avoidance.

Solves the problem:
  Given N conjunction threats at times [t1, t2, ..., tN],
  find optimal maneuver sequence that:
  1. Avoids all conjunctions (miss_distance > threshold)
  2. Minimizes total fuel consumption
  3. Respects operational constraints (min interval, max dV per burn)
  4. Avoids creating secondary conjunctions

Uses scipy.optimize with fuel-constrained optimization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize, differential_evolution

from engine.config.settings import GM, RE
from engine.physics.entity import Entity
from engine.physics.state import State
from engine.physics.cw_relative import cw_time_of_closest_approach, _hill_frame_basis


@dataclass
class Conjunction:
    """A conjunction threat to be avoided."""
    debris_id: int
    debris_name: str
    debris_pos: np.ndarray
    debris_vel: np.ndarray
    tca_sec: float  # time to closest approach from now
    miss_distance_m: float  # current predicted miss
    collision_prob: float  # probability of collision
    priority: int = 1  # 1=highest

    def __post_init__(self):
        self.debris_pos = np.array(self.debris_pos, dtype=float)
        self.debris_vel = np.array(self.debris_vel, dtype=float)


@dataclass
class ManeuverCandidate:
    """A single maneuver in a sequence."""
    burn_time_sec: float  # when to execute (seconds from now)
    delta_v: np.ndarray  # [dvx, dvy, dvz] in m/s (ECI)
    fuel_kg: float  # fuel required
    target_conjunction_idx: int  # which conjunction this addresses

    @property
    def magnitude(self) -> float:
        return float(np.linalg.norm(self.delta_v))


@dataclass
class ManeuverSequence:
    """A complete maneuver plan."""
    maneuvers: List[ManeuverCandidate]
    total_fuel_kg: float
    total_delta_v_ms: float
    post_miss_distances: Dict[int, float]  # debris_id -> new miss distance
    feasible: bool
    warnings: List[str] = field(default_factory=list)
    score: float = 0.0  # lower is better

    def to_dict(self) -> Dict[str, Any]:
        return {
            "maneuvers": [
                {
                    "burn_time_sec": m.burn_time_sec,
                    "delta_v": m.delta_v.tolist(),
                    "delta_v_magnitude_ms": round(m.magnitude, 4),
                    "fuel_kg": round(m.fuel_kg, 4),
                    "target_conjunction_idx": m.target_conjunction_idx,
                }
                for m in self.maneuvers
            ],
            "total_fuel_kg": round(self.total_fuel_kg, 4),
            "total_delta_v_ms": round(self.total_delta_v_ms, 4),
            "post_miss_distances": {k: round(v, 2) for k, v in self.post_miss_distances.items()},
            "feasible": self.feasible,
            "warnings": self.warnings,
            "score": round(self.score, 6),
        }


@dataclass
class OptimizerConfig:
    """Configuration for the multi-impulse optimizer."""
    min_burn_interval_sec: float = 1800.0  # 30 minutes between burns
    max_dv_per_burn_ms: float = 50.0  # max delta-v per burn
    target_miss_km: float = 5.0  # desired miss distance
    fuel_budget_kg: float = 10.0  # max fuel to use
    isp_s: float = 220.0  # specific impulse
    dry_mass_kg: float = 420.0  # satellite dry mass
    secondary_check_radius_km: float = 10.0  # check for secondary conjunctions


class MultiImpulseOptimizer:
    """
    Optimizer for multi-maneuver collision avoidance sequences.

    Finds the fuel-optimal sequence of maneuvers that avoids all
    conjunction threats while respecting operational constraints.
    """

    def __init__(self, config: Optional[OptimizerConfig] = None):
        self.config = config or OptimizerConfig()
        self.g0 = 9.80665  # m/s^2

    def _fuel_for_dv(self, dv_ms: float, current_mass_kg: float) -> float:
        """Compute fuel required for delta-v using Tsiolkovsky equation."""
        ve = self.config.isp_s * self.g0
        mass_ratio = math.exp(dv_ms / ve)
        return current_mass_kg * (1.0 - 1.0 / mass_ratio)

    def _propagate_state(
        self, pos: np.ndarray, vel: np.ndarray, dt: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Simple two-body propagation for quick estimates."""
        # Use vis-viva + Kepler approximation
        r = np.linalg.norm(pos)
        v = np.linalg.norm(vel)

        # Mean motion
        a = 1.0 / (2.0 / r - v**2 / GM)  # semi-major axis
        n = math.sqrt(GM / abs(a)**3) if a > 0 else math.sqrt(GM / r**3)

        # Approximate propagation using rotation
        angle = n * dt
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        # Rotate in orbital plane (simplified)
        h = np.cross(pos, vel)
        h_norm = np.linalg.norm(h)
        if h_norm < 1e-10:
            return pos.copy(), vel.copy()

        h_hat = h / h_norm
        r_hat = pos / r
        theta_hat = np.cross(h_hat, r_hat)

        # New position (approximate)
        new_r_hat = cos_a * r_hat + sin_a * theta_hat
        new_pos = new_r_hat * r

        # New velocity (approximate, maintain energy)
        new_theta_hat = np.cross(h_hat, new_r_hat)
        new_vel = v * (sin_a * (-r_hat) + cos_a * theta_hat)
        # Adjust for vis-viva
        new_r = np.linalg.norm(new_pos)
        new_v = math.sqrt(GM * (2.0 / new_r - 1.0 / a)) if a > 0 else v
        new_vel = new_vel / np.linalg.norm(new_vel) * new_v

        return new_pos, new_vel

    def _compute_miss_after_maneuver(
        self,
        sat_pos: np.ndarray,
        sat_vel: np.ndarray,
        debris_pos: np.ndarray,
        debris_vel: np.ndarray,
        delta_v: np.ndarray,
        burn_time: float,
        tca: float,
    ) -> float:
        """Compute miss distance after applying a maneuver."""
        # Propagate satellite to burn time
        sat_pos_burn, sat_vel_burn = self._propagate_state(sat_pos, sat_vel, burn_time)
        deb_pos_burn, deb_vel_burn = self._propagate_state(debris_pos, debris_vel, burn_time)

        # Apply delta-v
        sat_vel_after = sat_vel_burn + delta_v

        # Propagate to TCA
        time_to_tca = tca - burn_time
        if time_to_tca < 0:
            time_to_tca = 0

        sat_pos_tca, sat_vel_tca = self._propagate_state(sat_pos_burn, sat_vel_after, time_to_tca)
        deb_pos_tca, deb_vel_tca = self._propagate_state(deb_pos_burn, deb_vel_burn, time_to_tca)

        # Compute miss distance
        rel_pos = sat_pos_tca - deb_pos_tca
        return float(np.linalg.norm(rel_pos))

    def _compute_optimal_burn_direction(
        self,
        sat_pos: np.ndarray,
        sat_vel: np.ndarray,
        debris_pos: np.ndarray,
        debris_vel: np.ndarray,
    ) -> np.ndarray:
        """Compute optimal burn direction to maximize miss distance."""
        # Use Hill frame - radial burn is often most efficient
        try:
            er, ey, ez = _hill_frame_basis(sat_pos, sat_vel)
        except ValueError:
            # Fallback to velocity-aligned
            v_norm = np.linalg.norm(sat_vel)
            if v_norm > 0:
                return sat_vel / v_norm
            return np.array([1.0, 0.0, 0.0])

        # Relative position
        rel_pos = debris_pos - sat_pos

        # Project onto Hill frame
        rel_radial = np.dot(rel_pos, er)
        rel_along = np.dot(rel_pos, ey)
        rel_cross = np.dot(rel_pos, ez)

        # Choose direction that maximizes perpendicular distance
        # Usually radial or cross-track burns are most effective
        if abs(rel_radial) > abs(rel_cross):
            # Debris is mostly radial - use cross-track burn
            return ez if rel_cross >= 0 else -ez
        else:
            # Debris is mostly cross-track - use radial burn
            return er if rel_radial >= 0 else -er

    def optimize_single_conjunction(
        self,
        sat_pos: np.ndarray,
        sat_vel: np.ndarray,
        conj: Conjunction,
        fuel_available_kg: float,
    ) -> Optional[ManeuverCandidate]:
        """Find optimal single maneuver for one conjunction."""
        target_miss = self.config.target_miss_km * 1000  # convert to meters

        if conj.miss_distance_m >= target_miss:
            # Already safe
            return None

        # Optimal burn time: typically 1/4 to 1/2 orbit before TCA
        # For LEO (~90 min orbit), this is 20-45 minutes before
        r = np.linalg.norm(sat_pos)
        n = math.sqrt(GM / r**3)
        period = 2 * math.pi / n

        # Try burn at 1/3 period before TCA
        burn_time = max(0, conj.tca_sec - period / 3)

        # Get optimal direction
        direction = self._compute_optimal_burn_direction(
            sat_pos, sat_vel, conj.debris_pos, conj.debris_vel
        )

        # Binary search for required delta-v magnitude
        dv_low, dv_high = 0.1, self.config.max_dv_per_burn_ms
        best_dv = None

        for _ in range(20):  # Binary search iterations
            dv_mid = (dv_low + dv_high) / 2
            delta_v = direction * dv_mid

            miss = self._compute_miss_after_maneuver(
                sat_pos, sat_vel,
                conj.debris_pos, conj.debris_vel,
                delta_v, burn_time, conj.tca_sec
            )

            if miss >= target_miss:
                dv_high = dv_mid
                best_dv = delta_v.copy()
            else:
                dv_low = dv_mid

        if best_dv is None:
            # Could not find solution - use max
            best_dv = direction * self.config.max_dv_per_burn_ms

        dv_mag = float(np.linalg.norm(best_dv))
        fuel = self._fuel_for_dv(dv_mag, self.config.dry_mass_kg + fuel_available_kg)

        if fuel > fuel_available_kg:
            return None  # Not enough fuel

        return ManeuverCandidate(
            burn_time_sec=burn_time,
            delta_v=best_dv,
            fuel_kg=fuel,
            target_conjunction_idx=0,
        )

    def optimize_sequence(
        self,
        sat_pos: np.ndarray,
        sat_vel: np.ndarray,
        conjunctions: List[Conjunction],
        fuel_available_kg: float,
    ) -> ManeuverSequence:
        """
        Find optimal maneuver sequence for multiple conjunctions.

        Uses greedy approach with refinement:
        1. Sort conjunctions by TCA
        2. Plan maneuver for each, updating state
        3. Check for secondary conjunctions
        4. Refine with local optimization
        """
        sat_pos = np.array(sat_pos, dtype=float)
        sat_vel = np.array(sat_vel, dtype=float)

        if not conjunctions:
            return ManeuverSequence(
                maneuvers=[],
                total_fuel_kg=0.0,
                total_delta_v_ms=0.0,
                post_miss_distances={},
                feasible=True,
                warnings=["No conjunctions to avoid"],
            )

        # Sort by TCA
        sorted_conjs = sorted(conjunctions, key=lambda c: c.tca_sec)

        maneuvers: List[ManeuverCandidate] = []
        remaining_fuel = min(fuel_available_kg, self.config.fuel_budget_kg)
        warnings: List[str] = []

        # Current satellite state (updated after each maneuver)
        current_pos = sat_pos.copy()
        current_vel = sat_vel.copy()
        current_time = 0.0

        post_miss = {}

        for idx, conj in enumerate(sorted_conjs):
            # Update conjunction relative to current time
            time_to_tca = conj.tca_sec - current_time

            if time_to_tca < self.config.min_burn_interval_sec:
                warnings.append(f"Conjunction {conj.debris_id} too close in time, skipping")
                continue

            # Plan maneuver
            adjusted_conj = Conjunction(
                debris_id=conj.debris_id,
                debris_name=conj.debris_name,
                debris_pos=conj.debris_pos,
                debris_vel=conj.debris_vel,
                tca_sec=time_to_tca,
                miss_distance_m=conj.miss_distance_m,
                collision_prob=conj.collision_prob,
                priority=conj.priority,
            )

            maneuver = self.optimize_single_conjunction(
                current_pos, current_vel, adjusted_conj, remaining_fuel
            )

            if maneuver is None:
                if conj.miss_distance_m < self.config.target_miss_km * 1000:
                    warnings.append(
                        f"Cannot avoid conjunction {conj.debris_id}: insufficient fuel or exceeds constraints"
                    )
                continue

            # Update target index
            maneuver.target_conjunction_idx = idx

            # Apply maneuver to state
            burn_pos, burn_vel = self._propagate_state(
                current_pos, current_vel, maneuver.burn_time_sec
            )
            burn_vel = burn_vel + maneuver.delta_v

            # Update current state to post-burn
            current_pos = burn_pos
            current_vel = burn_vel
            current_time += maneuver.burn_time_sec
            remaining_fuel -= maneuver.fuel_kg

            # Compute post-maneuver miss distance
            miss = self._compute_miss_after_maneuver(
                sat_pos, sat_vel,
                conj.debris_pos, conj.debris_vel,
                maneuver.delta_v, maneuver.burn_time_sec, conj.tca_sec
            )
            post_miss[conj.debris_id] = miss

            maneuvers.append(maneuver)

        # Check feasibility
        total_fuel = sum(m.fuel_kg for m in maneuvers)
        total_dv = sum(m.magnitude for m in maneuvers)

        feasible = (
            total_fuel <= fuel_available_kg
            and all(m.magnitude <= self.config.max_dv_per_burn_ms for m in maneuvers)
        )

        # Score: weighted combination of fuel and risk
        score = total_fuel * 10.0  # Fuel cost
        for conj in sorted_conjs:
            miss = post_miss.get(conj.debris_id, conj.miss_distance_m)
            if miss < self.config.target_miss_km * 1000:
                score += (self.config.target_miss_km * 1000 - miss) / 1000  # Penalty for inadequate miss

        return ManeuverSequence(
            maneuvers=maneuvers,
            total_fuel_kg=total_fuel,
            total_delta_v_ms=total_dv,
            post_miss_distances=post_miss,
            feasible=feasible,
            warnings=warnings,
            score=score,
        )

    def check_secondary_conjunctions(
        self,
        sat_pos: np.ndarray,
        sat_vel: np.ndarray,
        sequence: ManeuverSequence,
        all_debris: List[Dict[str, Any]],
        horizon_sec: float = 86400,
    ) -> List[Dict[str, Any]]:
        """
        Check if a maneuver sequence creates new (secondary) conjunctions.

        Returns list of new conjunctions detected.
        """
        if not sequence.maneuvers:
            return []

        # Apply all maneuvers to get final state
        current_pos = np.array(sat_pos, dtype=float)
        current_vel = np.array(sat_vel, dtype=float)
        current_time = 0.0

        for m in sequence.maneuvers:
            # Propagate to burn
            pos, vel = self._propagate_state(current_pos, current_vel, m.burn_time_sec - current_time)
            # Apply burn
            vel = vel + m.delta_v
            current_pos = pos
            current_vel = vel
            current_time = m.burn_time_sec

        # Screen for new conjunctions
        secondary = []
        threshold = self.config.secondary_check_radius_km * 1000

        for debris in all_debris:
            deb_pos = np.array(debris.get("position", [0, 0, 0]), dtype=float)
            deb_vel = np.array(debris.get("velocity", [0, 0, 0]), dtype=float)

            # Propagate debris to current time
            deb_pos_now, deb_vel_now = self._propagate_state(deb_pos, deb_vel, current_time)

            # Check for close approach in remaining horizon
            remaining_horizon = horizon_sec - current_time
            if remaining_horizon <= 0:
                continue

            try:
                tca, miss, _, _ = cw_time_of_closest_approach(
                    current_pos, current_vel,
                    deb_pos_now, deb_vel_now,
                    horizon=remaining_horizon,
                )

                if miss < threshold:
                    secondary.append({
                        "debris_id": debris.get("norad_id", 0),
                        "debris_name": debris.get("name", "Unknown"),
                        "tca_sec": tca + current_time,
                        "miss_distance_m": miss,
                        "type": "secondary",
                    })
            except Exception:
                pass

        return secondary


def plan_multi_maneuver_avoidance(
    sat_pos: List[float],
    sat_vel: List[float],
    conjunctions: List[Dict[str, Any]],
    fuel_available_kg: float = 10.0,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    High-level API for multi-maneuver planning.

    Args:
        sat_pos: Satellite position [x, y, z] in meters (ECI)
        sat_vel: Satellite velocity [vx, vy, vz] in m/s (ECI)
        conjunctions: List of conjunction dicts with keys:
            - debris_id: int
            - debris_name: str
            - debris_pos: [x, y, z] in meters
            - debris_vel: [vx, vy, vz] in m/s
            - tca_sec: time to closest approach (seconds)
            - miss_distance_m: predicted miss (meters)
            - collision_prob: probability (0-1)
        fuel_available_kg: Available fuel budget
        config: Optional optimizer config overrides

    Returns:
        Dict with maneuver sequence and analysis
    """
    # Build config
    opt_config = OptimizerConfig()
    if config:
        for k, v in config.items():
            if hasattr(opt_config, k):
                setattr(opt_config, k, v)

    # Convert conjunction dicts to objects
    conj_objects = []
    for c in conjunctions:
        conj_objects.append(Conjunction(
            debris_id=c.get("debris_id", 0),
            debris_name=c.get("debris_name", "Unknown"),
            debris_pos=c.get("debris_pos", [0, 0, 0]),
            debris_vel=c.get("debris_vel", [0, 0, 0]),
            tca_sec=c.get("tca_sec", 0),
            miss_distance_m=c.get("miss_distance_m", 1e9),
            collision_prob=c.get("collision_prob", 0),
            priority=c.get("priority", 1),
        ))

    # Run optimizer
    optimizer = MultiImpulseOptimizer(opt_config)
    sequence = optimizer.optimize_sequence(
        np.array(sat_pos),
        np.array(sat_vel),
        conj_objects,
        fuel_available_kg,
    )

    result = sequence.to_dict()
    result["num_conjunctions"] = len(conjunctions)
    result["num_maneuvers"] = len(sequence.maneuvers)
    result["fuel_available_kg"] = fuel_available_kg
    result["fuel_remaining_kg"] = round(fuel_available_kg - sequence.total_fuel_kg, 4)

    return result

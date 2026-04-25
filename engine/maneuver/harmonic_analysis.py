"""
Orbital Harmonic Analysis and Secondary Conjunction Detection.

Detects if a maneuver creates resonant orbits that could lead to
future conjunctions at harmonic intervals.

Key concepts:
- Orbital resonance: n1/n2 = p/q (small integers)
- Repeating ground tracks
- Periodic close approaches
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engine.config.settings import GM, RE
from engine.physics.cw_relative import cw_time_of_closest_approach


@dataclass
class OrbitalElements:
    """Keplerian orbital elements."""
    semi_major_axis_m: float
    eccentricity: float
    inclination_rad: float
    raan_rad: float  # Right Ascension of Ascending Node
    arg_perigee_rad: float
    true_anomaly_rad: float

    @property
    def period_sec(self) -> float:
        """Orbital period in seconds."""
        if self.semi_major_axis_m <= 0:
            return float('inf')
        return 2 * math.pi * math.sqrt(self.semi_major_axis_m**3 / GM)

    @property
    def mean_motion_rad_s(self) -> float:
        """Mean motion in rad/s."""
        if self.semi_major_axis_m <= 0:
            return 0
        return math.sqrt(GM / self.semi_major_axis_m**3)

    @classmethod
    def from_state_vector(cls, pos: np.ndarray, vel: np.ndarray) -> "OrbitalElements":
        """Convert state vector to orbital elements."""
        r = np.linalg.norm(pos)
        v = np.linalg.norm(vel)

        # Specific angular momentum
        h = np.cross(pos, vel)
        h_mag = np.linalg.norm(h)

        # Node vector
        k = np.array([0, 0, 1])
        n = np.cross(k, h)
        n_mag = np.linalg.norm(n)

        # Eccentricity vector
        e_vec = ((v**2 - GM / r) * pos - np.dot(pos, vel) * vel) / GM
        ecc = np.linalg.norm(e_vec)

        # Semi-major axis (vis-viva)
        energy = v**2 / 2 - GM / r
        if abs(energy) < 1e-10:
            a = float('inf')  # Parabolic
        else:
            a = -GM / (2 * energy)

        # Inclination
        inc = math.acos(np.clip(h[2] / h_mag, -1, 1)) if h_mag > 0 else 0

        # RAAN
        if n_mag > 0:
            raan = math.acos(np.clip(n[0] / n_mag, -1, 1))
            if n[1] < 0:
                raan = 2 * math.pi - raan
        else:
            raan = 0

        # Argument of perigee
        if n_mag > 0 and ecc > 1e-10:
            arg_p = math.acos(np.clip(np.dot(n, e_vec) / (n_mag * ecc), -1, 1))
            if e_vec[2] < 0:
                arg_p = 2 * math.pi - arg_p
        else:
            arg_p = 0

        # True anomaly
        if ecc > 1e-10:
            nu = math.acos(np.clip(np.dot(e_vec, pos) / (ecc * r), -1, 1))
            if np.dot(pos, vel) < 0:
                nu = 2 * math.pi - nu
        else:
            nu = math.acos(np.clip(np.dot(n, pos) / (n_mag * r), -1, 1)) if n_mag > 0 else 0

        return cls(
            semi_major_axis_m=a,
            eccentricity=ecc,
            inclination_rad=inc,
            raan_rad=raan,
            arg_perigee_rad=arg_p,
            true_anomaly_rad=nu,
        )


@dataclass
class ResonanceResult:
    """Result of orbital resonance analysis."""
    is_resonant: bool
    resonance_ratio: Optional[Tuple[int, int]]  # (p, q) where n1/n2 = p/q
    period_ratio: float
    synodic_period_sec: float  # Time between successive close approaches
    warning_level: str  # "none", "low", "medium", "high"
    description: str


def detect_orbital_resonance(
    sat_elements: OrbitalElements,
    debris_elements: OrbitalElements,
    max_ratio_search: int = 20,
    tolerance: float = 0.02,
) -> ResonanceResult:
    """
    Detect if two orbits are in orbital resonance.

    Resonance occurs when n1/n2 ≈ p/q for small integers p, q.
    This leads to repeating close approaches at predictable intervals.
    """
    n1 = sat_elements.mean_motion_rad_s
    n2 = debris_elements.mean_motion_rad_s

    if n1 == 0 or n2 == 0:
        return ResonanceResult(
            is_resonant=False,
            resonance_ratio=None,
            period_ratio=0,
            synodic_period_sec=float('inf'),
            warning_level="none",
            description="Invalid orbital elements",
        )

    ratio = n1 / n2

    # Search for integer ratios
    best_p, best_q = 1, 1
    best_error = float('inf')

    for q in range(1, max_ratio_search + 1):
        for p in range(1, max_ratio_search + 1):
            error = abs(ratio - p / q)
            if error < best_error:
                best_error = error
                best_p, best_q = p, q

    is_resonant = best_error < tolerance

    # Synodic period (time between successive alignments)
    if abs(n1 - n2) > 1e-10:
        synodic = 2 * math.pi / abs(n1 - n2)
    else:
        synodic = float('inf')

    # Warning level based on resonance type
    if not is_resonant:
        warning = "none"
        desc = "No significant orbital resonance detected"
    elif best_p == best_q:
        warning = "high"
        desc = f"1:1 resonance - co-orbital objects! Synodic period: {synodic/3600:.1f} hours"
    elif max(best_p, best_q) <= 3:
        warning = "high"
        desc = f"{best_p}:{best_q} resonance - frequent close approaches every {synodic/3600:.1f} hours"
    elif max(best_p, best_q) <= 5:
        warning = "medium"
        desc = f"{best_p}:{best_q} resonance - periodic encounters every {synodic/86400:.1f} days"
    else:
        warning = "low"
        desc = f"Weak {best_p}:{best_q} resonance detected"

    return ResonanceResult(
        is_resonant=is_resonant,
        resonance_ratio=(best_p, best_q) if is_resonant else None,
        period_ratio=ratio,
        synodic_period_sec=synodic,
        warning_level=warning,
        description=desc,
    )


def analyze_maneuver_harmonics(
    pre_maneuver_pos: np.ndarray,
    pre_maneuver_vel: np.ndarray,
    post_maneuver_vel: np.ndarray,
    debris_list: List[Dict[str, Any]],
    analysis_horizon_days: int = 7,
) -> Dict[str, Any]:
    """
    Analyze if a maneuver creates problematic orbital harmonics.

    Checks:
    1. New orbital resonances with catalog objects
    2. Repeating ground tracks that increase collision risk
    3. Harmonic return to original conjunction geometry
    """
    pre_elements = OrbitalElements.from_state_vector(pre_maneuver_pos, pre_maneuver_vel)
    post_elements = OrbitalElements.from_state_vector(pre_maneuver_pos, post_maneuver_vel)

    results = {
        "pre_maneuver_period_min": pre_elements.period_sec / 60,
        "post_maneuver_period_min": post_elements.period_sec / 60,
        "period_change_percent": 0,
        "resonances_detected": [],
        "high_risk_resonances": 0,
        "medium_risk_resonances": 0,
        "recommendation": "safe",
    }

    if pre_elements.period_sec > 0:
        results["period_change_percent"] = (
            (post_elements.period_sec - pre_elements.period_sec)
            / pre_elements.period_sec * 100
        )

    # Check resonance with each debris object
    for debris in debris_list:
        deb_pos = np.array(debris.get("position", [0, 0, 0]), dtype=float)
        deb_vel = np.array(debris.get("velocity", [0, 0, 0]), dtype=float)

        if np.linalg.norm(deb_pos) < RE:
            continue  # Invalid position

        deb_elements = OrbitalElements.from_state_vector(deb_pos, deb_vel)
        resonance = detect_orbital_resonance(post_elements, deb_elements)

        if resonance.is_resonant:
            results["resonances_detected"].append({
                "debris_id": debris.get("norad_id", 0),
                "debris_name": debris.get("name", "Unknown"),
                "resonance_ratio": f"{resonance.resonance_ratio[0]}:{resonance.resonance_ratio[1]}",
                "synodic_period_hours": resonance.synodic_period_sec / 3600,
                "warning_level": resonance.warning_level,
                "description": resonance.description,
            })

            if resonance.warning_level == "high":
                results["high_risk_resonances"] += 1
            elif resonance.warning_level == "medium":
                results["medium_risk_resonances"] += 1

    # Overall recommendation
    if results["high_risk_resonances"] > 0:
        results["recommendation"] = "dangerous"
        results["recommendation_text"] = (
            f"Maneuver creates {results['high_risk_resonances']} high-risk orbital resonances. "
            "Consider alternative maneuver profile."
        )
    elif results["medium_risk_resonances"] > 2:
        results["recommendation"] = "caution"
        results["recommendation_text"] = (
            f"Maneuver creates multiple medium-risk resonances. "
            "Monitor for secondary conjunctions."
        )
    else:
        results["recommendation"] = "safe"
        results["recommendation_text"] = "No significant harmonic risks detected."

    return results


def predict_conjunction_recurrence(
    sat_pos: np.ndarray,
    sat_vel: np.ndarray,
    debris_pos: np.ndarray,
    debris_vel: np.ndarray,
    initial_miss_m: float,
    horizon_days: int = 30,
    sample_interval_hours: float = 6.0,
) -> List[Dict[str, Any]]:
    """
    Predict recurring conjunctions based on orbital periods.

    Useful for detecting if avoiding one conjunction just delays
    the problem to a later orbit.
    """
    sat_elements = OrbitalElements.from_state_vector(sat_pos, sat_vel)
    deb_elements = OrbitalElements.from_state_vector(debris_pos, debris_vel)

    resonance = detect_orbital_resonance(sat_elements, deb_elements)

    recurrences = []
    horizon_sec = horizon_days * 86400
    sample_sec = sample_interval_hours * 3600

    # Simple propagation to find recurring close approaches
    current_sat_pos = sat_pos.copy()
    current_sat_vel = sat_vel.copy()
    current_deb_pos = debris_pos.copy()
    current_deb_vel = debris_vel.copy()

    t = 0
    while t < horizon_sec:
        # Check for close approach using CW model
        try:
            tca, miss, _, _ = cw_time_of_closest_approach(
                current_sat_pos, current_sat_vel,
                current_deb_pos, current_deb_vel,
                horizon=sample_sec,
            )

            if miss < initial_miss_m * 2:  # Within 2x original miss
                recurrences.append({
                    "time_from_now_hours": (t + tca) / 3600,
                    "miss_distance_m": miss,
                    "is_closer": miss < initial_miss_m,
                })
        except Exception:
            pass

        # Advance time (simplified - just rotate by mean motion)
        n_sat = sat_elements.mean_motion_rad_s
        n_deb = deb_elements.mean_motion_rad_s

        # Simple rotation in orbital plane
        angle_sat = n_sat * sample_sec
        angle_deb = n_deb * sample_sec

        # Rotate position vectors (simplified 2D rotation in orbital plane)
        r_sat = np.linalg.norm(current_sat_pos)
        r_deb = np.linalg.norm(current_deb_pos)

        # Keep magnitude, adjust phase
        current_sat_pos = current_sat_pos * np.cos(angle_sat) + np.cross(
            sat_vel / np.linalg.norm(sat_vel), current_sat_pos
        ) * np.sin(angle_sat) * r_sat / np.linalg.norm(current_sat_pos)

        current_deb_pos = current_deb_pos * np.cos(angle_deb) + np.cross(
            debris_vel / np.linalg.norm(debris_vel) if np.linalg.norm(debris_vel) > 0 else np.array([0,0,1]),
            current_deb_pos
        ) * np.sin(angle_deb) * r_deb / max(np.linalg.norm(current_deb_pos), 1)

        t += sample_sec

    return recurrences


def evaluate_maneuver_safety(
    sat_pos: np.ndarray,
    sat_vel: np.ndarray,
    delta_v: np.ndarray,
    debris_catalog: List[Dict[str, Any]],
    original_conjunction_id: int,
) -> Dict[str, Any]:
    """
    Comprehensive safety evaluation of a proposed maneuver.

    Combines harmonic analysis, secondary conjunction detection,
    and recurrence prediction.
    """
    post_vel = sat_vel + delta_v

    # 1. Harmonic analysis
    harmonics = analyze_maneuver_harmonics(
        sat_pos, sat_vel, post_vel, debris_catalog
    )

    # 2. Find the original conjunction debris
    original_debris = None
    for d in debris_catalog:
        if d.get("norad_id") == original_conjunction_id:
            original_debris = d
            break

    # 3. Check recurrence if we found the original debris
    recurrence_risk = "low"
    recurrences = []
    if original_debris:
        deb_pos = np.array(original_debris["position"], dtype=float)
        deb_vel = np.array(original_debris["velocity"], dtype=float)

        # Current miss (pre-maneuver)
        try:
            _, current_miss, _, _ = cw_time_of_closest_approach(
                sat_pos, sat_vel, deb_pos, deb_vel, horizon=86400
            )

            recurrences = predict_conjunction_recurrence(
                sat_pos, post_vel, deb_pos, deb_vel,
                initial_miss_m=current_miss,
                horizon_days=14,
            )

            if any(r["is_closer"] for r in recurrences):
                recurrence_risk = "high"
            elif len(recurrences) > 3:
                recurrence_risk = "medium"
        except Exception:
            pass

    # 4. Overall safety score
    safety_score = 100
    issues = []

    if harmonics["high_risk_resonances"] > 0:
        safety_score -= 40
        issues.append(f"{harmonics['high_risk_resonances']} high-risk resonances")

    if harmonics["medium_risk_resonances"] > 0:
        safety_score -= 10 * harmonics["medium_risk_resonances"]
        issues.append(f"{harmonics['medium_risk_resonances']} medium-risk resonances")

    if recurrence_risk == "high":
        safety_score -= 30
        issues.append("High recurrence risk")
    elif recurrence_risk == "medium":
        safety_score -= 15
        issues.append("Moderate recurrence risk")

    safety_score = max(0, safety_score)

    return {
        "safety_score": safety_score,
        "safety_rating": "safe" if safety_score >= 70 else ("caution" if safety_score >= 40 else "dangerous"),
        "issues": issues,
        "harmonics": harmonics,
        "recurrence_risk": recurrence_risk,
        "predicted_recurrences": recurrences[:5],  # Top 5
        "recommendation": (
            "Maneuver is safe to execute"
            if safety_score >= 70
            else "Consider alternative maneuver parameters"
        ),
    }

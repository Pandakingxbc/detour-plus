"""
Active satellite model with full resource management.

Tracks fuel, power, battery, maneuver history, and operational constraints.
This is the on-board satellite representation that the agents interact with.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from engine.config.settings import GM, RE


@dataclass
class SatelliteConfig:
    """Configurable satellite parameters."""
    name: str = "DETOUR-SAT-1"
    norad_id: int = 25544

    # Mass properties
    dry_mass_kg: float = 420.0          # kg (without fuel)
    fuel_capacity_kg: float = 50.0      # kg max fuel
    initial_fuel_kg: float = 45.0       # kg starting fuel

    # Propulsion
    isp_s: float = 220.0               # specific impulse (seconds) — typical hydrazine
    max_thrust_n: float = 22.0         # max thrust (Newtons)
    max_dv_per_burn_ms: float = 50.0   # max delta-v per single burn (m/s)

    # Power
    solar_power_w: float = 2400.0      # solar panel output (Watts)
    battery_capacity_wh: float = 4800.0  # battery capacity (Watt-hours)
    initial_battery_wh: float = 4200.0   # starting battery
    maneuver_power_draw_w: float = 800.0  # thruster power draw (Watts)
    baseline_power_draw_w: float = 350.0  # avionics + comms baseline

    # Orbit (initial state — can be overridden)
    altitude_km: float = 420.0
    inclination_deg: float = 51.6


G0 = 9.80665  # m/s²


class Satellite:
    """
    Active satellite with resource tracking and maneuver execution.

    The satellite maintains its own ECI state vector, fuel budget,
    power state, and maneuver history. Agents query and command it.
    """

    def __init__(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        config: Optional[SatelliteConfig] = None,
        name: str = "DETOUR-SAT-1",
    ):
        self.config = config or SatelliteConfig(name=name)
        self.name = self.config.name
        self.norad_id = self.config.norad_id

        # State vector (ECI, meters & m/s)
        self.position = np.array(position, dtype=float)
        self.velocity = np.array(velocity, dtype=float)

        # Resources
        self.fuel_kg = self.config.initial_fuel_kg
        self.battery_wh = self.config.initial_battery_wh
        self.is_operational = True

        # History
        self.maneuver_history: List[Dict[str, Any]] = []
        self.epoch = time.time()  # Unix timestamp of state

    # ── Derived properties ───────────────────────────────────────────
    @property
    def total_mass(self) -> float:
        """Current total mass (dry + fuel) in kg."""
        return self.config.dry_mass_kg + self.fuel_kg

    @property
    def exhaust_velocity(self) -> float:
        """Effective exhaust velocity in m/s."""
        return self.config.isp_s * G0

    @property
    def max_delta_v(self) -> float:
        """Maximum remaining delta-v from Tsiolkovsky (m/s)."""
        if self.fuel_kg <= 0:
            return 0.0
        mass_ratio = self.total_mass / self.config.dry_mass_kg
        return self.exhaust_velocity * math.log(mass_ratio)

    @property
    def altitude_m(self) -> float:
        """Current altitude above Earth surface (meters)."""
        return float(np.linalg.norm(self.position)) - RE

    @property
    def altitude_km(self) -> float:
        return self.altitude_m / 1000.0

    @property
    def speed_ms(self) -> float:
        return float(np.linalg.norm(self.velocity))

    @property
    def fuel_percentage(self) -> float:
        return (self.fuel_kg / self.config.fuel_capacity_kg) * 100.0

    @property
    def battery_percentage(self) -> float:
        return (self.battery_wh / self.config.battery_capacity_wh) * 100.0

    @property
    def power_w(self) -> float:
        """Available power (Watts)."""
        return self.config.solar_power_w  # simplified: assume sunlit

    # ── Resource checks ──────────────────────────────────────────────
    def fuel_required_for_dv(self, delta_v_ms: float) -> float:
        """Fuel required for a given delta-v (kg), via Tsiolkovsky."""
        mass_ratio = math.exp(delta_v_ms / self.exhaust_velocity)
        return self.total_mass * (1.0 - 1.0 / mass_ratio)

    def can_perform_maneuver(
        self, delta_v_ms: float, min_fuel_margin_kg: float = 1.0
    ) -> bool:
        """Check if satellite has enough resources for a maneuver."""
        if not self.is_operational:
            return False
        if delta_v_ms > self.config.max_dv_per_burn_ms:
            return False
        fuel_needed = self.fuel_required_for_dv(delta_v_ms)
        if fuel_needed > (self.fuel_kg - min_fuel_margin_kg):
            return False
        # Check power (assume 60s burn minimum)
        burn_energy_wh = self.config.maneuver_power_draw_w * (60.0 / 3600.0)
        if self.battery_wh < burn_energy_wh:
            return False
        return True

    # ── Maneuver execution ───────────────────────────────────────────
    def apply_maneuver(self, delta_v: np.ndarray) -> Dict[str, Any]:
        """
        Execute a maneuver: apply delta-v, consume fuel and power.

        Args:
            delta_v: [dvx, dvy, dvz] in m/s (ECI frame)

        Returns:
            Execution result dict
        """
        dv = np.array(delta_v, dtype=float)
        dv_mag = float(np.linalg.norm(dv))

        if not self.can_perform_maneuver(dv_mag):
            return {
                "executed": False,
                "reason": "Insufficient resources or exceeds limits",
            }

        # Consume fuel
        fuel_used = self.fuel_required_for_dv(dv_mag)
        self.fuel_kg -= fuel_used

        # Consume power
        burn_energy_wh = self.config.maneuver_power_draw_w * (60.0 / 3600.0)
        self.battery_wh = max(0, self.battery_wh - burn_energy_wh)

        # Apply delta-v to velocity
        self.velocity = self.velocity + dv

        # Record
        record = {
            "timestamp": time.time(),
            "delta_v": dv.tolist(),
            "delta_v_magnitude_ms": round(dv_mag, 4),
            "fuel_used_kg": round(fuel_used, 4),
            "fuel_remaining_kg": round(self.fuel_kg, 4),
            "battery_after_wh": round(self.battery_wh, 2),
            "new_velocity": self.velocity.tolist(),
            "executed": True,
        }
        self.maneuver_history.append(record)
        return record

    # ── Status telemetry ─────────────────────────────────────────────
    def get_status(self) -> Dict[str, Any]:
        """Full satellite telemetry snapshot."""
        return {
            "name": self.name,
            "norad_id": self.norad_id,
            "operational": self.is_operational,
            "position_eci_m": self.position.tolist(),
            "velocity_eci_ms": self.velocity.tolist(),
            "altitude_km": round(self.altitude_km, 2),
            "speed_ms": round(self.speed_ms, 2),
            "fuel_kg": round(self.fuel_kg, 3),
            "fuel_percentage": round(self.fuel_percentage, 1),
            "fuel_capacity_kg": self.config.fuel_capacity_kg,
            "max_delta_v_ms": round(self.max_delta_v, 2),
            "battery_wh": round(self.battery_wh, 2),
            "battery_percentage": round(self.battery_percentage, 1),
            "power_w": round(self.power_w, 1),
            "dry_mass_kg": self.config.dry_mass_kg,
            "total_mass_kg": round(self.total_mass, 2),
            "isp_s": self.config.isp_s,
            "max_thrust_n": self.config.max_thrust_n,
            "max_dv_per_burn_ms": self.config.max_dv_per_burn_ms,
            "maneuver_count": len(self.maneuver_history),
            "maneuver_history": self.maneuver_history[-5:],  # last 5
        }

    # ── Orbital elements (approximate) ───────────────────────────────
    def get_orbital_elements(self) -> Dict[str, float]:
        """Compute approximate Keplerian elements from state vector."""
        r = self.position
        v = self.velocity
        r_mag = np.linalg.norm(r)
        v_mag = np.linalg.norm(v)

        # Specific angular momentum
        h = np.cross(r, v)
        h_mag = np.linalg.norm(h)

        # Semi-major axis (vis-viva)
        energy = 0.5 * v_mag**2 - GM / r_mag
        a = -GM / (2 * energy) if energy < 0 else float("inf")

        # Eccentricity vector
        e_vec = (np.cross(v, h) / GM) - (r / r_mag)
        e = float(np.linalg.norm(e_vec))

        # Inclination
        inc = math.degrees(math.acos(np.clip(h[2] / h_mag, -1, 1)))

        # Perigee/apogee
        if e < 1.0 and a > 0:
            perigee_alt_km = (a * (1 - e) - RE) / 1000.0
            apogee_alt_km = (a * (1 + e) - RE) / 1000.0
        else:
            perigee_alt_km = self.altitude_km
            apogee_alt_km = self.altitude_km

        # Period
        period_min = (2 * math.pi * math.sqrt(a**3 / GM) / 60.0) if a > 0 else 0

        return {
            "semi_major_axis_km": round(a / 1000.0, 2),
            "eccentricity": round(e, 6),
            "inclination_deg": round(inc, 2),
            "perigee_alt_km": round(perigee_alt_km, 2),
            "apogee_alt_km": round(apogee_alt_km, 2),
            "period_min": round(period_min, 2),
        }


def create_default_satellite() -> Satellite:
    """Create a default ISS-like satellite for demo purposes."""
    # ISS-like orbit: ~420 km altitude, 51.6° inclination
    alt = 420_000  # meters
    r = RE + alt
    # Circular velocity
    v_circ = math.sqrt(GM / r)
    # Position & velocity for ~51.6° inclination
    inc = math.radians(51.6)
    position = np.array([r, 0.0, 0.0])
    velocity = np.array([0.0, v_circ * math.cos(inc), v_circ * math.sin(inc)])

    return Satellite(
        position=position,
        velocity=velocity,
        config=SatelliteConfig(
            name="ISS (ZARYA)",
            norad_id=25544,
            altitude_km=420.0,
            inclination_deg=51.6,
        ),
    )

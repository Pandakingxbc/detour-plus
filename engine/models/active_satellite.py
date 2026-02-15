"""
Satellite class for orbital debris avoidance simulation.
Uses ECI coordinates and two-body orbital mechanics.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# Physical constants
MU_EARTH = 398600.4418  # Earth's gravitational parameter (km^3/s^2)
G0 = 9.80665e-3  # Standard gravity (km/s^2)


@dataclass
class ManeuverRecord:
    """Record of a single maneuver execution."""
    timestamp: float  # Mission elapsed time (seconds)
    delta_v: np.ndarray  # Delta-v vector (km/s)
    magnitude: float  # Delta-v magnitude (m/s)
    fuel_used: float  # Fuel consumed (kg)
    reason: str = ""  # Why this maneuver was performed


@dataclass
class SatelliteState:
    """Snapshot of satellite state at a given time."""
    time: float  # Mission elapsed time (seconds)
    position: np.ndarray  # ECI position (km)
    velocity: np.ndarray  # ECI velocity (km/s)
    mass: float  # Total mass (kg)
    fuel: float  # Remaining fuel (kg)
    power: float  # Battery charge (Wh)


class Satellite:
    """
    Satellite with orbital dynamics, resource management, and maneuver capabilities.

    Designed for multi-agent control system with:
    - Conjunction/Risk Assessment agent
    - Trajectory Optimization agent
    - Resource Guardian agent
    - Execution and Feedback agent
    """

    def __init__(
        self,
        position: np.ndarray,  # Initial position in ECI (km)
        velocity: np.ndarray,  # Initial velocity in ECI (km/s)
        dry_mass: float = 500.0,  # Satellite mass without fuel (kg)
        fuel_capacity: float = 100.0,  # Maximum fuel (kg)
        initial_fuel: Optional[float] = None,  # Starting fuel (kg), defaults to full
        isp: float = 300.0,  # Specific impulse (seconds)
        battery_capacity: float = 5000.0,  # Battery capacity (Wh)
        initial_charge: Optional[float] = None,  # Starting charge (Wh), defaults to full
        solar_panel_power: float = 200.0,  # Solar power generation (W)
        idle_power_draw: float = 50.0,  # Idle power consumption (W)
        maneuver_power_draw: float = 150.0,  # Power during maneuver (W)
        name: str = "SAT-1"
    ):
        """Initialize satellite with state and configuration."""

        # Identity
        self.name = name

        # State vectors (ECI coordinates)
        self.position = np.array(position, dtype=np.float64)  # km
        self.velocity = np.array(velocity, dtype=np.float64)  # km/s

        # Mass properties
        self.dry_mass = dry_mass  # kg
        self.fuel_capacity = fuel_capacity  # kg
        self.fuel = initial_fuel if initial_fuel is not None else fuel_capacity  # kg

        # Propulsion
        self.isp = isp  # seconds
        self.exhaust_velocity = isp * G0  # km/s

        # Power system
        self.battery_capacity = battery_capacity  # Wh
        self.power = initial_charge if initial_charge is not None else battery_capacity  # Wh
        self.solar_panel_power = solar_panel_power  # W
        self.idle_power_draw = idle_power_draw  # W
        self.maneuver_power_draw = maneuver_power_draw  # W

        # Mission clock
        self.mission_time = 0.0  # seconds

        # History
        self.maneuver_history: List[ManeuverRecord] = []
        self.state_history: List[SatelliteState] = []

        # Status flags
        self.is_operational = True
        self.last_maneuver_time = 0.0

        # Save initial state
        self._record_state()

    @property
    def total_mass(self) -> float:
        """Current total mass including remaining fuel."""
        return self.dry_mass + self.fuel

    @property
    def fuel_percentage(self) -> float:
        """Remaining fuel as percentage of capacity."""
        return (self.fuel / self.fuel_capacity) * 100.0

    @property
    def power_percentage(self) -> float:
        """Battery charge as percentage of capacity."""
        return (self.power / self.battery_capacity) * 100.0

    @property
    def max_delta_v(self) -> float:
        """Maximum delta-v available with current fuel (m/s)."""
        if self.fuel <= 0:
            return 0.0
        final_mass = self.dry_mass
        return self.exhaust_velocity * np.log(self.total_mass / final_mass) * 1000.0  # m/s

    def get_orbital_elements(self) -> Dict[str, float]:
        """
        Convert state vectors to Keplerian orbital elements.

        Returns:
            Dictionary with orbital elements:
            - a: semi-major axis (km)
            - e: eccentricity
            - i: inclination (degrees)
            - omega: argument of periapsis (degrees)
            - Omega: right ascension of ascending node (degrees)
            - nu: true anomaly (degrees)
            - period: orbital period (seconds)
            - apoapsis: apoapsis altitude (km)
            - periapsis: periapsis altitude (km)
        """
        r = self.position
        v = self.velocity

        r_mag = np.linalg.norm(r)
        v_mag = np.linalg.norm(v)

        # Specific orbital energy
        energy = (v_mag**2) / 2 - MU_EARTH / r_mag

        # Semi-major axis
        a = -MU_EARTH / (2 * energy)

        # Angular momentum vector
        h = np.cross(r, v)
        h_mag = np.linalg.norm(h)

        # Eccentricity vector
        e_vec = np.cross(v, h) / MU_EARTH - r / r_mag
        e = np.linalg.norm(e_vec)

        # Inclination
        i = np.arccos(h[2] / h_mag)

        # Node vector (points to ascending node)
        n = np.array([-h[1], h[0], 0])
        n_mag = np.linalg.norm(n)

        # Right ascension of ascending node
        if n_mag > 1e-10:
            Omega = np.arccos(n[0] / n_mag)
            if n[1] < 0:
                Omega = 2 * np.pi - Omega
        else:
            Omega = 0.0

        # Argument of periapsis
        if n_mag > 1e-10 and e > 1e-10:
            omega = np.arccos(np.dot(n, e_vec) / (n_mag * e))
            if e_vec[2] < 0:
                omega = 2 * np.pi - omega
        else:
            omega = 0.0

        # True anomaly
        if e > 1e-10:
            nu = np.arccos(np.dot(e_vec, r) / (e * r_mag))
            if np.dot(r, v) < 0:
                nu = 2 * np.pi - nu
        else:
            nu = 0.0

        # Orbital period
        if a > 0:
            period = 2 * np.pi * np.sqrt(a**3 / MU_EARTH)
        else:
            period = float('inf')

        # Apoapsis and periapsis altitudes (assuming Earth radius 6378 km)
        R_EARTH = 6378.0
        apoapsis = a * (1 + e) - R_EARTH
        periapsis = a * (1 - e) - R_EARTH

        return {
            'a': a,
            'e': e,
            'i': np.degrees(i),
            'omega': np.degrees(omega),
            'Omega': np.degrees(Omega),
            'nu': np.degrees(nu),
            'period': period,
            'apoapsis': apoapsis,
            'periapsis': periapsis
        }

    def propagate(self, dt: float, power_mode: str = 'idle') -> None:
        """
        Propagate satellite state forward using two-body orbital mechanics.

        Args:
            dt: Time step (seconds)
            power_mode: 'idle' or 'active' (affects power consumption)
        """
        if not self.is_operational:
            return

        # Use RK4 integration for orbital dynamics
        def acceleration(pos: np.ndarray) -> np.ndarray:
            """Gravitational acceleration in two-body problem."""
            r = np.linalg.norm(pos)
            return -MU_EARTH * pos / (r**3)

        # RK4 integration
        k1_v = acceleration(self.position)
        k1_r = self.velocity

        k2_v = acceleration(self.position + 0.5 * dt * k1_r)
        k2_r = self.velocity + 0.5 * dt * k1_v

        k3_v = acceleration(self.position + 0.5 * dt * k2_r)
        k3_r = self.velocity + 0.5 * dt * k2_v

        k4_v = acceleration(self.position + dt * k3_r)
        k4_r = self.velocity + dt * k3_v

        # Update state
        self.position += (dt / 6.0) * (k1_r + 2*k2_r + 2*k3_r + k4_r)
        self.velocity += (dt / 6.0) * (k1_v + 2*k2_v + 2*k3_v + k4_v)

        # Update power
        power_draw = self.idle_power_draw if power_mode == 'idle' else self.maneuver_power_draw
        power_consumed = power_draw * (dt / 3600.0)  # Convert W*s to Wh
        power_generated = self.solar_panel_power * (dt / 3600.0)

        self.power += power_generated - power_consumed
        self.power = np.clip(self.power, 0.0, self.battery_capacity)

        # Update mission time
        self.mission_time += dt

        # Check operational status
        if self.power <= 0:
            self.is_operational = False

        # Record state periodically (every 60 seconds)
        if len(self.state_history) == 0 or self.mission_time - self.state_history[-1].time >= 60.0:
            self._record_state()

    def apply_delta_v(self, dv: np.ndarray, reason: str = "") -> bool:
        """
        Apply an impulsive delta-v maneuver.

        Args:
            dv: Delta-v vector in ECI frame (km/s)
            reason: Description of why this maneuver is performed

        Returns:
            True if maneuver successful, False if insufficient resources
        """
        dv = np.array(dv, dtype=np.float64)
        dv_magnitude = np.linalg.norm(dv) * 1000.0  # Convert to m/s for fuel calculation

        # Check if maneuver is feasible
        if not self.can_perform_maneuver(dv_magnitude):
            return False

        # Calculate fuel required using Tsiolkovsky rocket equation
        # Δv = v_e * ln(m0 / m1)
        # m1 = m0 / exp(Δv / v_e)
        mass_ratio = np.exp(dv_magnitude / (self.exhaust_velocity * 1000.0))
        fuel_required = self.total_mass * (1 - 1/mass_ratio)

        # Apply the maneuver
        self.velocity += dv
        self.fuel -= fuel_required
        self.last_maneuver_time = self.mission_time

        # Record maneuver
        record = ManeuverRecord(
            timestamp=self.mission_time,
            delta_v=dv.copy(),
            magnitude=dv_magnitude,
            fuel_used=fuel_required,
            reason=reason
        )
        self.maneuver_history.append(record)
        self._record_state()

        return True

    def can_perform_maneuver(self, dv_magnitude: float, min_fuel_margin: float = 5.0) -> bool:
        """
        Check if satellite has resources to perform a maneuver.

        Args:
            dv_magnitude: Delta-v magnitude (m/s)
            min_fuel_margin: Minimum fuel to keep in reserve (kg)

        Returns:
            True if maneuver is feasible
        """
        if not self.is_operational:
            return False

        # Check fuel
        mass_ratio = np.exp(dv_magnitude / (self.exhaust_velocity * 1000.0))
        fuel_required = self.total_mass * (1 - 1/mass_ratio)

        if fuel_required > (self.fuel - min_fuel_margin):
            return False

        # Check power (assume maneuver takes 60 seconds at high power draw)
        maneuver_power_needed = self.maneuver_power_draw * (60.0 / 3600.0)  # Wh
        if self.power < maneuver_power_needed:
            return False

        return True

    def distance_to(self, position: np.ndarray) -> float:
        """
        Calculate distance to another position.

        Args:
            position: Position vector in ECI (km)

        Returns:
            Distance (km)
        """
        return np.linalg.norm(self.position - np.array(position))

    def relative_velocity_to(self, position: np.ndarray, velocity: np.ndarray) -> Tuple[float, np.ndarray]:
        """
        Calculate relative velocity to another object.

        Args:
            position: Other object's position in ECI (km)
            velocity: Other object's velocity in ECI (km/s)

        Returns:
            Tuple of (relative speed in km/s, relative velocity vector)
        """
        rel_vel = self.velocity - np.array(velocity)
        return np.linalg.norm(rel_vel), rel_vel

    def get_status(self) -> Dict:
        """
        Get comprehensive status report for monitoring agents.

        Returns:
            Dictionary with current satellite status
        """
        orbital_elements = self.get_orbital_elements()

        return {
            'name': self.name,
            'operational': self.is_operational,
            'mission_time': self.mission_time,
            'position': self.position.tolist(),
            'velocity': self.velocity.tolist(),
            'altitude': np.linalg.norm(self.position) - 6378.0,  # km above Earth surface
            'speed': np.linalg.norm(self.velocity),  # km/s
            'mass': {
                'total': self.total_mass,
                'dry': self.dry_mass,
                'fuel': self.fuel,
                'fuel_percentage': self.fuel_percentage
            },
            'power': {
                'current': self.power,
                'capacity': self.battery_capacity,
                'percentage': self.power_percentage,
                'generation_rate': self.solar_panel_power,
                'consumption_rate': self.idle_power_draw
            },
            'propulsion': {
                'isp': self.isp,
                'max_delta_v': self.max_delta_v,
                'maneuver_count': len(self.maneuver_history)
            },
            'orbital_elements': orbital_elements,
            'last_maneuver': self.mission_time - self.last_maneuver_time
        }

    def _record_state(self) -> None:
        """Record current state for history."""
        state = SatelliteState(
            time=self.mission_time,
            position=self.position.copy(),
            velocity=self.velocity.copy(),
            mass=self.total_mass,
            fuel=self.fuel,
            power=self.power
        )
        self.state_history.append(state)

    def __repr__(self) -> str:
        """String representation of satellite."""
        status = "OPERATIONAL" if self.is_operational else "OFFLINE"
        return (f"Satellite(name={self.name}, status={status}, "
                f"fuel={self.fuel_percentage:.1f}%, power={self.power_percentage:.1f}%, "
                f"maneuvers={len(self.maneuver_history)})")

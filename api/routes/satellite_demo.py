"""Demo endpoint to showcase Satellite class with moving visualization."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Query

from engine.models.active_satellite import Satellite

router = APIRouter(prefix="/api/satellite-demo", tags=["satellite-demo"])


@router.get("/iss-trajectory")
async def get_iss_trajectory(
    duration: float = Query(5400, description="Duration in seconds"),
    dt: float = Query(60, description="Time step in seconds"),
):
    """
    Return a simple propagated trajectory for ISS using the Satellite class.
    This is a demo showing the Satellite model in action.
    """
    # ISS-like initial conditions (approximate ECI position/velocity in meters, m/s)
    # ISS orbits at ~420 km altitude = 6378 + 420 = 6798 km from Earth center
    EARTH_RADIUS_M = 6_378_137
    ALTITUDE_M = 420_000  # 420 km altitude
    ORBITAL_RADIUS_M = EARTH_RADIUS_M + ALTITUDE_M  # ~6.798 million meters

    # Place satellite at an angle for better visibility
    position = np.array([
        ORBITAL_RADIUS_M * 0.8,   # X component
        ORBITAL_RADIUS_M * 0.5,   # Y component
        ORBITAL_RADIUS_M * 0.3    # Z component (inclined orbit)
    ])

    # Orbital velocity at ISS altitude is ~7.66 km/s
    # Set velocity perpendicular to position for circular orbit
    velocity = np.array([-5500.0, 6000.0, 2000.0])  # ~7.8 km/s total

    # Create Satellite instance
    sat = Satellite(position=position, velocity=velocity)

    # Generate trajectory by simple propagation
    times = []
    positions = []
    velocities = []

    t = 0.0
    pos = sat.position.copy()
    vel = sat.velocity.copy()

    while t <= duration:
        times.append(t)
        positions.append(pos.tolist())
        velocities.append(vel.tolist())

        # Simple propagation (you can replace with more sophisticated methods)
        # For now, just use basic kinematics
        pos, vel = _simple_propagate_step(pos, vel, dt)
        t += dt

    return {
        "satellite_type": "iss_demo",
        "times": times,
        "positions": positions,
        "velocities": velocities,
        "has_covariance": True,
    }


def _simple_propagate_step(pos: np.ndarray, vel: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Simplified propagation using two-body dynamics.
    For production, use your existing propagation tools.
    """
    GM = 3.986004418e14  # Earth's gravitational parameter (m^3/s^2)

    # Current radius
    r = np.linalg.norm(pos)

    # Acceleration (two-body only)
    acc = -GM * pos / (r ** 3)

    # Simple Euler integration (replace with RK4 for better accuracy)
    new_vel = vel + acc * dt
    new_pos = pos + new_vel * dt

    return new_pos, new_vel

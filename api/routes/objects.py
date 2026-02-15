"""Routes for orbital objects: list, detail, trajectory."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from api import state
from api.schemas import OrbitalObjectResponse, TrajectoryResponse, ManualSatelliteRequest
from engine.models.satellite import Satellite
from tools.propagate import propagate_orbits

router = APIRouter(prefix="/api/objects", tags=["objects"])


@router.get("", response_model=list[OrbitalObjectResponse])
async def list_objects(
    group: str = Query("active", description="CelesTrak group filter"),
    limit: int = Query(5000, ge=1, le=50000),
    search: str = Query("", description="Name or NORAD ID search"),
):
    catalog = state.get_catalog()
    if search:
        objects = catalog.search(search)
    else:
        objects = catalog.get_all(propagate=False)

    results = []
    for obj in objects[:limit]:
        results.append(OrbitalObjectResponse(
            norad_id=obj.norad_id,
            name=obj.name,
            position=obj.position.tolist(),
            velocity=obj.velocity.tolist(),
            epoch=obj.epoch.isoformat() if obj.epoch else None,
            lat=obj.lat,
            lon=obj.lon,
            alt_km=obj.alt_km,
            object_type=obj.object_type,
            source=obj.source,
        ))
    return results


@router.get("/{norad_id}", response_model=OrbitalObjectResponse)
async def get_object(norad_id: int):
    catalog = state.get_catalog()
    obj = catalog.get_object(norad_id, propagate=True)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Object {norad_id} not found")
    return OrbitalObjectResponse(
        norad_id=obj.norad_id,
        name=obj.name,
        position=obj.position.tolist(),
        velocity=obj.velocity.tolist(),
        epoch=obj.epoch.isoformat() if obj.epoch else None,
        lat=obj.lat,
        lon=obj.lon,
        alt_km=obj.alt_km,
        object_type=obj.object_type,
        source=obj.source,
    )


@router.get("/{norad_id}/trajectory", response_model=TrajectoryResponse)
async def get_trajectory(
    norad_id: int,
    duration: float = Query(5400, description="Duration in seconds"),
    dt: float = Query(60, description="Timestep in seconds"),
    fidelity: str = Query("sgp4", description="sgp4, rk4, or rk45"),
):
    catalog = state.get_catalog()
    obj = catalog.get_object(norad_id, propagate=True)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Object {norad_id} not found")

    trajectories = propagate_orbits([obj], duration_sec=duration, dt=dt, fidelity=fidelity)

    if norad_id not in trajectories:
        raise HTTPException(status_code=500, detail="Propagation failed")

    traj = trajectories[norad_id]
    return TrajectoryResponse(
        norad_id=norad_id,
        times=traj["times"],
        positions=traj["positions"],
        velocities=traj["velocities"],
    )


@router.post("/manual/trajectory")
async def get_manual_trajectory(request: ManualSatelliteRequest):
    """
    Generate a circular orbit with specified 3D orientation.
    Returns initial state vectors + trajectory for visualization.
    """
    import numpy as np
    import math

    # Constants
    EARTH_RADIUS = 6371000.0  # meters

    # Convert to radians
    inclination = math.radians(request.inclination_deg)
    raan = math.radians(request.raan_deg)

    # Orbital radius
    radius_m = EARTH_RADIUS + request.altitude_km * 1000.0

    # Initial position in orbital plane (at ascending node)
    # Start at ascending node: where orbit crosses equator going north
    pos_orbital = np.array([radius_m, 0.0, 0.0])

    # Initial velocity in orbital plane (perpendicular to position)
    vel_orbital = np.array([0.0, request.speed_mps, 0.0])

    # Rotation matrices to convert from orbital plane to ECI
    # 1. Rotate by inclination around x-axis
    R_i = np.array([
        [1, 0, 0],
        [0, math.cos(inclination), -math.sin(inclination)],
        [0, math.sin(inclination), math.cos(inclination)]
    ])

    # 2. Rotate by RAAN around z-axis
    R_raan = np.array([
        [math.cos(raan), -math.sin(raan), 0],
        [math.sin(raan), math.cos(raan), 0],
        [0, 0, 1]
    ])

    # Combined rotation: first inclination, then RAAN
    R_total = R_raan @ R_i

    # Transform to ECI coordinates
    initial_position = (R_total @ pos_orbital).tolist()
    initial_velocity = (R_total @ vel_orbital).tolist()
    epoch = datetime.now(timezone.utc)

    # Calculate orbital period
    circumference = 2 * math.pi * radius_m
    period_sec = circumference / request.speed_mps if request.speed_mps > 0 else 5400.0

    # Generate trajectory points for visualization (2 complete orbits)
    num_orbits = 2
    total_time = period_sec * num_orbits
    num_points = int(total_time / request.dt)

    times = []
    positions = []
    velocities = []

    for i in range(num_points):
        t = i * request.dt
        angle = (t / period_sec) * 2 * math.pi

        # Position in orbital plane
        x_orb = radius_m * math.cos(angle)
        y_orb = radius_m * math.sin(angle)
        z_orb = 0.0
        pos_orb = np.array([x_orb, y_orb, z_orb])

        # Velocity in orbital plane
        vx_orb = -request.speed_mps * math.sin(angle)
        vy_orb = request.speed_mps * math.cos(angle)
        vz_orb = 0.0
        vel_orb = np.array([vx_orb, vy_orb, vz_orb])

        # Transform to ECI
        pos_eci = R_total @ pos_orb
        vel_eci = R_total @ vel_orb

        times.append(t)
        positions.append(pos_eci.tolist())
        velocities.append(vel_eci.tolist())

    return {
        "norad_id": -1,
        "initial_state": {
            "position": initial_position,
            "velocity": initial_velocity,
            "epoch": epoch.isoformat(),
        },
        "trajectory": {
            "times": times,
            "positions": positions,
            "velocities": velocities,
        },
    }

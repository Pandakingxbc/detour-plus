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


@router.post("/manual/trajectory", response_model=TrajectoryResponse)
async def get_manual_trajectory(request: ManualSatelliteRequest):
    """
    Generate a perfect circular orbit at the given radius.
    Speed parameter controls the orbital period.
    """
    import numpy as np
    import math

    radius_m = request.radius_km * 1000.0

    # Calculate orbital period from speed: T = 2πr/v
    circumference = 2 * math.pi * radius_m
    period_sec = circumference / request.speed_mps if request.speed_mps > 0 else 5400.0

    # Generate points for 2 complete orbits
    num_orbits = 2
    total_time = period_sec * num_orbits
    num_points = int(total_time / request.dt)

    times = []
    positions = []
    velocities = []

    for i in range(num_points):
        t = i * request.dt
        angle = (t / period_sec) * 2 * math.pi  # radians

        # Circular orbit in equatorial plane
        x = radius_m * math.cos(angle)
        y = radius_m * math.sin(angle)
        z = 0.0

        # Tangential velocity
        vx = -request.speed_mps * math.sin(angle)
        vy = request.speed_mps * math.cos(angle)
        vz = 0.0

        times.append(t)
        positions.append([x, y, z])
        velocities.append([vx, vy, vz])

    return TrajectoryResponse(
        norad_id=-1,
        times=times,
        positions=positions,
        velocities=velocities,
    )

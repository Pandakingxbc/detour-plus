"""Routes for maneuver planning and simulation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api import state
from api.schemas import (
    ManeuverCandidate,
    ManeuverProposeRequest,
    ManeuverSimulateRequest,
    ManeuverSimulationResult,
    ConstraintCheckResult,
)
from tools.maneuver import propose_maneuvers, simulate_maneuver
from tools.constraints import check_constraints

router = APIRouter(prefix="/api/maneuvers", tags=["maneuvers"])


@router.post("/propose", response_model=list[ManeuverCandidate])
async def propose(req: ManeuverProposeRequest):
    catalog = state.get_catalog()
    primary = catalog.get_object(req.primary_id, propagate=True)
    secondary = catalog.get_object(req.secondary_id, propagate=True)

    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary {req.primary_id} not found")
    if secondary is None:
        raise HTTPException(status_code=404, detail=f"Secondary {req.secondary_id} not found")

    candidates = propose_maneuvers(
        primary=primary,
        secondary=secondary,
        tca_offset_sec=req.tca_offset_sec,
        miss_distance_m=req.miss_distance_m,
        mass_kg=req.mass_kg,
        isp_s=req.isp_s,
        target_miss_km=req.target_miss_km,
    )

    return [ManeuverCandidate(**c) for c in candidates]


@router.post("/simulate", response_model=ManeuverSimulationResult)
async def simulate(req: ManeuverSimulateRequest):
    catalog = state.get_catalog()
    primary = catalog.get_object(req.primary_id, propagate=True)
    secondary = catalog.get_object(req.secondary_id, propagate=True)

    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary {req.primary_id} not found")
    if secondary is None:
        raise HTTPException(status_code=404, detail=f"Secondary {req.secondary_id} not found")

    # Get nearby catalog objects for secondary conjunction check if requested
    nearby_objects = None
    if req.check_secondary:
        nearby_objects = catalog.get_all(propagate=False)

    result = simulate_maneuver(
        primary=primary,
        secondary=secondary,
        delta_v=req.delta_v,
        burn_time_sec=req.burn_time_sec,
        window_sec=req.window_sec,
        catalog_objects=nearby_objects,
    )

    return ManeuverSimulationResult(**result)


@router.post("/check-constraints", response_model=ConstraintCheckResult)
async def check(
    primary_id: int,
    delta_v: list[float],
    remaining_fuel_kg: float = 50.0,
    burn_time_sec: float = 0.0,
    secondary_conjunction_count: int = 0,
):
    catalog = state.get_catalog()
    primary = catalog.get_object(primary_id, propagate=True)

    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary {primary_id} not found")

    result = check_constraints(
        delta_v=delta_v,
        primary_position=primary.position,
        primary_velocity=primary.velocity,
        remaining_fuel_kg=remaining_fuel_kg,
        burn_time_sec=burn_time_sec,
        secondary_conjunction_count=secondary_conjunction_count,
    )

    return ConstraintCheckResult(**result)

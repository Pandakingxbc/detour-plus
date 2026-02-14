"""Routes for conjunction screening and refinement."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api import state
from api.schemas import ConjunctionEvent, RefinementResult, RiskAssessment
from tools.screening import screen_conjunctions
from tools.refine import refine_tca
from tools.risk import estimate_risk

router = APIRouter(prefix="/api/conjunctions", tags=["conjunctions"])


@router.get("", response_model=list[ConjunctionEvent])
async def get_conjunctions(
    primary_id: int = Query(..., description="NORAD ID of primary object"),
    lookahead: float = Query(86400, description="Screening horizon in seconds"),
    threshold_km: float = Query(50, description="Max miss distance to report (km)"),
    max_objects: int = Query(200, description="Max catalog objects to screen"),
):
    catalog = state.get_catalog()
    primary = catalog.get_object(primary_id, propagate=True)
    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary object {primary_id} not found")

    # Get catalog objects for screening
    catalog_objects = catalog.get_all(propagate=False)

    events = screen_conjunctions(
        primary=primary,
        catalog_objects=catalog_objects,
        lookahead_sec=lookahead,
        threshold_km=threshold_km,
        max_objects=max_objects,
    )

    # Cache results
    cache_key = f"{primary_id}_{lookahead}"
    state.conjunction_cache[cache_key] = events

    return [ConjunctionEvent(**e) for e in events]


@router.post("/{event_id}/refine", response_model=RefinementResult)
async def refine_conjunction(
    event_id: str,
    primary_id: int = Query(...),
    secondary_id: int = Query(...),
    window_sec: float = Query(3600, description="Refinement window in seconds"),
):
    catalog = state.get_catalog()
    primary = catalog.get_object(primary_id, propagate=True)
    secondary = catalog.get_object(secondary_id, propagate=True)

    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary {primary_id} not found")
    if secondary is None:
        raise HTTPException(status_code=404, detail=f"Secondary {secondary_id} not found")

    result = refine_tca(primary, secondary, window_sec=window_sec)
    return RefinementResult(**result)


@router.get("/{event_id}/risk", response_model=RiskAssessment)
async def get_risk(
    event_id: str,
    primary_id: int = Query(...),
    secondary_id: int = Query(...),
    mc_samples: int = Query(0, description="Monte Carlo samples (0 = skip MC)"),
):
    catalog = state.get_catalog()
    primary = catalog.get_object(primary_id, propagate=True)
    secondary = catalog.get_object(secondary_id, propagate=True)

    if primary is None:
        raise HTTPException(status_code=404, detail=f"Primary {primary_id} not found")
    if secondary is None:
        raise HTTPException(status_code=404, detail=f"Secondary {secondary_id} not found")

    result = estimate_risk(primary, secondary, mc_samples=mc_samples)
    return RiskAssessment(**result)

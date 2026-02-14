"""Routes for catalog management."""

from __future__ import annotations

from fastapi import APIRouter

from api import state
from api.schemas import CatalogStatus

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/status", response_model=CatalogStatus)
async def catalog_status():
    catalog = state.get_catalog()
    status = catalog.status()
    return CatalogStatus(**status)


@router.post("/refresh")
async def catalog_refresh():
    catalog = state.get_catalog()
    count = catalog.refresh()
    return {
        "message": f"Catalog refreshed, {count} new objects loaded",
        "total_objects": catalog.count,
    }

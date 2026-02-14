"""
Detour API — FastAPI server for the Space Debris Collision Avoidance Copilot.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import state
from api.routes import objects, conjunctions, maneuvers, catalog

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

logger = logging.getLogger("detour")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize catalog on startup in background."""
    logger.info("Starting Detour API...")
    # Initialize catalog in background to not block startup
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _init_catalog_background)
    yield
    logger.info("Shutting down Detour API.")


def _init_catalog_background():
    """Load catalog from CelesTrak (runs in thread pool)."""
    try:
        logger.info("Loading orbital catalog from CelesTrak...")
        cat = state.init_catalog(groups=["active", "stations", "visual"])
        logger.info("Catalog loaded: %d objects", cat.count)
    except Exception as e:
        logger.error("Failed to load catalog: %s", e)
        # Create empty catalog so endpoints still work
        state.get_catalog()


app = FastAPI(
    title="Detour — Space Debris Collision Avoidance Copilot",
    description="Edge-deployable agentic collision-avoidance copilot API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(objects.router)
app.include_router(conjunctions.router)
app.include_router(maneuvers.router)
app.include_router(catalog.router)


@app.get("/api/health")
async def health():
    cat = state.get_catalog()
    return {
        "status": "ok",
        "catalog_objects": cat.count,
        "catalog_loaded": cat.last_refresh is not None,
    }

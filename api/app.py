"""
FastAPI backend for the Detour agent system.

Provides SSE streaming of agent pipeline events to the frontend.
The frontend's physics/visualization stays in TypeScript — this API
only exposes the LLM agent pipeline for the terminal drawer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agents.config import LLMConfig
from agents.graph import run_avoidance_pipeline, stream_avoidance_pipeline
from api.demo_data import load_demo_data
from api.state import get_satellite, reset_state

logger = logging.getLogger("detour.api")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load demo data on startup."""
    logger.info("Loading demo data...")
    load_demo_data()
    logger.info("Demo data loaded. Agent API ready.")
    yield


app = FastAPI(
    title="Detour Agent API",
    description="Internal API for the Detour collision avoidance agent system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_config() -> LLMConfig:
    """Build LLM config from environment."""
    return LLMConfig.from_env()


# ─────────────────────────────────────────────────────────────────────────
# Health / status
# ─────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "detour-agent-api"}


@app.get("/status")
def status():
    sat = get_satellite()
    config = _get_config()
    return {
        "satellite": {
            "norad_id": sat.norad_id,
            "name": sat.name,
            "fuel_pct": round(sat.fuel_kg / sat.config.fuel_capacity * 100, 1),
        },
        "llm": {
            "model": config.model,
            "base_url": config.base_url,
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# Agent pipeline — synchronous (returns full result)
# ─────────────────────────────────────────────────────────────────────────

@app.post("/agent/run")
def agent_run(
    prompt: str = "Scan for conjunction threats against the ISS in the next 24 hours. If any are high risk, propose avoidance maneuvers and check constraints. Use the demo dataset.",
    mode: str = "multi",
):
    """
    Run the agent pipeline synchronously and return the full result.
    Use /agent/stream for real-time SSE updates.
    """
    config = _get_config()
    result = run_avoidance_pipeline(prompt, config=config, mode=mode)
    return result


# ─────────────────────────────────────────────────────────────────────────
# Agent pipeline — SSE streaming (real-time events for terminal drawer)
# ─────────────────────────────────────────────────────────────────────────

@app.get("/agent/stream")
async def agent_stream(
    prompt: str = Query(
        default="Scan for conjunction threats against the ISS in the next 24 hours. If any are high risk, propose avoidance maneuvers and check constraints. Use the demo dataset.",
        description="Natural language request for the agent",
    ),
    mode: str = Query(default="multi", description="Agent mode: multi or single"),
):
    """
    Stream agent pipeline events via Server-Sent Events (SSE).
    The frontend terminal drawer connects to this endpoint.
    """
    config = _get_config()

    async def event_generator():
        try:
            async for event in stream_avoidance_pipeline(prompt, config=config, mode=mode):
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done', 'timestamp': time.time()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# Demo data management
# ─────────────────────────────────────────────────────────────────────────

@app.post("/demo/reload")
def demo_reload():
    """Reset state and reload demo data."""
    reset_state()
    summary = load_demo_data()
    return {"ok": True, "summary": summary}

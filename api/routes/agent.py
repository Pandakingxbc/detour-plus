"""
API routes for the Detour agent pipeline.

Provides:
  POST /api/agent/run      — run the full pipeline (blocking)
  GET  /api/agent/stream   — SSE stream of agent events (real-time)
  POST /api/agent/chat     — single-turn chat with the agent
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("detour.api.agent")

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    """Request body for agent endpoints."""
    prompt: str = Field(..., description="Natural language request for the agent")
    primary_id: Optional[int] = Field(None, description="NORAD ID of the primary satellite")
    mode: str = Field("multi", description="Agent mode: 'multi' (5-agent pipeline) or 'single'")
    demo: bool = Field(True, description="Use demo data instead of live catalog")


class AgentResponse(BaseModel):
    """Response from the agent pipeline."""
    ops_brief: Optional[str] = None
    scout_output: Optional[str] = None
    analyst_output: Optional[str] = None
    planner_output: Optional[str] = None
    safety_output: Optional[str] = None
    events: list = Field(default_factory=list)
    elapsed_sec: float = 0.0


def _build_prompt(req: AgentRequest) -> str:
    """Build the full prompt from the request."""
    parts = [req.prompt]
    if req.primary_id:
        parts.append(f"\nPrimary satellite NORAD ID: {req.primary_id}")
    if req.demo:
        parts.append("\nUse the demo dataset (scan_demo_conjunctions tool).")
    return "\n".join(parts)


@router.post("/run", response_model=AgentResponse)
async def run_agent(req: AgentRequest):
    """
    Run the full agent pipeline (blocking).
    Returns the complete result including ops brief and all intermediate outputs.
    """
    from agents.config import LLMConfig
    from agents.graph import run_avoidance_pipeline

    config = LLMConfig.from_env()
    prompt = _build_prompt(req)

    t0 = time.time()

    # Run in executor to not block the event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_avoidance_pipeline(prompt, config=config, mode=req.mode),
    )

    elapsed = time.time() - t0

    return AgentResponse(
        ops_brief=result.get("ops_brief"),
        scout_output=result.get("scout_output"),
        analyst_output=result.get("analyst_output"),
        planner_output=result.get("planner_output"),
        safety_output=result.get("safety_output"),
        events=result.get("events", []),
        elapsed_sec=round(elapsed, 2),
    )


@router.get("/stream")
async def stream_agent(
    prompt: str = Query(..., description="Natural language request"),
    primary_id: Optional[int] = Query(None, description="NORAD ID of primary satellite"),
    mode: str = Query("multi", description="Agent mode: multi or single"),
    demo: bool = Query(True, description="Use demo data"),
):
    """
    SSE stream of agent events for real-time UI updates.

    Event types:
      - agent_start: agent begins processing
      - tool_calls: agent is calling tools
      - tool_result: tool returned a result
      - agent_complete: agent finished
      - agent_output: agent produced output text
      - pipeline_complete: entire pipeline done
    """
    from agents.config import LLMConfig
    from agents.graph import stream_avoidance_pipeline

    config = LLMConfig.from_env()

    req = AgentRequest(prompt=prompt, primary_id=primary_id, mode=mode, demo=demo)
    full_prompt = _build_prompt(req)

    async def event_generator():
        try:
            async for event in stream_avoidance_pipeline(
                full_prompt, config=config, mode=mode
            ):
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat_with_agent(req: AgentRequest):
    """
    Single-turn chat with the agent (always uses single-agent mode).
    Lighter weight than the full pipeline.
    """
    from agents.config import LLMConfig
    from agents.graph import run_avoidance_pipeline

    config = LLMConfig.from_env()
    prompt = _build_prompt(req)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_avoidance_pipeline(prompt, config=config, mode="single"),
    )

    return {
        "response": result.get("ops_brief", ""),
        "events": result.get("events", []),
    }


@router.get("/status")
async def agent_status():
    """Check if the LLM backend (Nemotron on GX10) is reachable."""
    import httpx
    from agents.config import LLMConfig

    config = LLMConfig.from_env()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{config.base_url}/models")
            models = resp.json()
            return {
                "status": "online",
                "base_url": config.base_url,
                "model": config.model,
                "available_models": [m["id"] for m in models.get("data", [])],
            }
    except Exception as e:
        return {
            "status": "offline",
            "base_url": config.base_url,
            "model": config.model,
            "error": str(e),
        }

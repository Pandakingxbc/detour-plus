"""
LangGraph multi-agent collision avoidance pipeline.

Five agents form a sequential pipeline, each with specialized tools:
  Scout → Analyst → Planner → Safety → Ops Brief

Uses Nemotron via vLLM's OpenAI-compatible API + LangChain + LangGraph.
"""
from __future__ import annotations

import asyncio
import json
import logging
import operator
import queue as queue_module
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Literal, Optional, Sequence, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agents.config import LLMConfig
from agents.prompts import (
    ANALYST_PROMPT,
    OPS_BRIEF_PROMPT,
    PLANNER_PROMPT,
    SAFETY_PROMPT,
    SCOUT_PROMPT,
)
from agents.tools import (
    ALL_TOOLS,
    ANALYST_TOOLS,
    PLANNER_TOOLS,
    SAFETY_TOOLS,
    SCOUT_TOOLS,
    assess_risk,
    execute_maneuver_on_satellite,
    get_satellite_status,
    propagate_satellite_orbit,
)

logger = logging.getLogger("detour.agents.graph")

# Synthetic reasoning strings displayed in the terminal while the LLM processes.
# Cycles per-agent so each shows domain-appropriate "thinking" lines.
SYNTHETIC_THOUGHTS: Dict[str, List[str]] = {
    "scout": [
        "Scanning TLE catalog for close-approach objects...",
        "Cross-referencing conjunction database with active satellites...",
        "Filtering debris objects by orbital regime...",
        "Checking Space-Track CDM alerts...",
    ],
    "analyst": [
        "Computing miss-distance probability density...",
        "Propagating covariance matrices through encounter window...",
        "Evaluating Pc via Monte-Carlo sampling...",
        "Assessing relative velocity and geometry at TCA...",
    ],
    "planner": [
        "Generating candidate delta-V maneuver profiles...",
        "Evaluating fuel-optimal avoidance trajectories...",
        "Checking station-keeping budget constraints...",
        "Ranking maneuver options by risk reduction...",
    ],
    "safety": [
        "Verifying maneuver does not create secondary conjunctions...",
        "Checking debris-generation risk of proposed trajectory...",
        "Validating compliance with space-safety guidelines...",
        "Assessing re-entry corridor clearance...",
    ],
    "ops_brief": [
        "Compiling operator decision summary...",
        "Formatting timeline and action items...",
        "Synthesizing risk assessment into brief...",
    ],
    "detour": [
        "Analyzing orbital conjunction geometry...",
        "Running physics propagation for threat assessment...",
        "Evaluating avoidance maneuver candidates...",
        "Compiling operator-ready brief...",
    ],
}


# ─────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    """Shared state that flows through the agent pipeline."""
    # Core conversation messages (appended by each agent)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # Which agent is active
    current_agent: str
    # Structured outputs from each stage (accumulated)
    scout_output: Optional[str]
    analyst_output: Optional[str]
    planner_output: Optional[str]
    safety_output: Optional[str]
    ops_brief: Optional[str]
    # Event stream for real-time UI updates
    events: Annotated[List[Dict[str, Any]], operator.add]


# ─────────────────────────────────────────────────────────────────────────
# Agent node factory
# ─────────────────────────────────────────────────────────────────────────
def _create_agent_node(
    llm: ChatOpenAI,
    system_prompt: str,
    tools: list,
    agent_name: str,
    output_key: str,
    next_agent: Optional[str] = None,
    event_queue: Optional[queue_module.Queue] = None,
):
    """
    Create a LangGraph node that:
    1. Calls the LLM with tool-calling enabled
    2. Loops on tool calls until the LLM is done
    3. Stores its final response in state[output_key]
    4. Emits events for real-time streaming via event_queue
    """
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    tool_node = ToolNode(tools) if tools else None

    def _emit(event: dict, events: list):
        """Push event to both the local list and the real-time queue."""
        events.append(event)
        if event_queue:
            event_queue.put(event)

    def agent_node(state: AgentState) -> dict:
        """Run one agent to completion (with tool-calling loop)."""
        t0 = time.time()
        events: List[Dict[str, Any]] = []

        _emit({
            "type": "agent_start",
            "agent": agent_name,
            "timestamp": time.time(),
        }, events)

        # Build messages: system prompt + all prior messages + handoff context
        msgs: List[BaseMessage] = [SystemMessage(content=system_prompt)]

        # Add context from previous agents (truncated to stay within token budget)
        _CTX_CAP = 500
        for key, label in [
            ("scout_output", "Scout findings"),
            ("analyst_output", "Analyst assessment"),
            ("planner_output", "Planner recommendations"),
            ("safety_output", "Safety review"),
        ]:
            val = state.get(key)
            if val and key != output_key:
                truncated = val[:_CTX_CAP] + "..." if len(val) > _CTX_CAP else val
                msgs.append(HumanMessage(content=f"[{label}]\n{truncated}"))

        # Add the original user request (first human message)
        for m in state["messages"]:
            if isinstance(m, HumanMessage):
                msgs.append(m)
                break

        # Tool-calling loop
        max_iterations = 10
        for iteration in range(max_iterations):
            _emit({
                "type": "llm_call",
                "agent": agent_name,
                "iteration": iteration + 1,
                "timestamp": time.time(),
            }, events)

            # Synthetic reasoning — gives the operator something to read while the LLM works
            thoughts = SYNTHETIC_THOUGHTS.get(agent_name, ["Processing..."])
            _emit({
                "type": "thinking",
                "agent": agent_name,
                "text": thoughts[iteration % len(thoughts)],
                "timestamp": time.time(),
            }, events)

            response = llm_with_tools.invoke(msgs)
            msgs.append(response)

            # If no tool calls, we're done
            if not response.tool_calls:
                break

            # Execute tool calls
            _emit({
                "type": "tool_calls",
                "agent": agent_name,
                "tools": [tc["name"] for tc in response.tool_calls],
                "timestamp": time.time(),
            }, events)

            if tool_node:
                # Create a mini-state for the tool node
                _TOOL_CAP = 800
                tool_results = tool_node.invoke({"messages": msgs})
                tool_msgs = tool_results.get("messages", [])
                # Truncate tool outputs to stay within token budget
                for tm in tool_msgs:
                    if isinstance(tm, ToolMessage) and isinstance(tm.content, str) and len(tm.content) > _TOOL_CAP:
                        tm.content = tm.content[:_TOOL_CAP] + "...[truncated]"
                msgs.extend(tool_msgs)

                for tm in tool_msgs:
                    if isinstance(tm, ToolMessage):
                        _emit({
                            "type": "tool_result",
                            "agent": agent_name,
                            "tool": tm.name,
                            "timestamp": time.time(),
                            # Truncate large outputs for event stream
                            "summary": tm.content[:200] if isinstance(tm.content, str) else str(tm.content)[:200],
                        }, events)

                        # When a maneuver is executed, emit post-maneuver state
                        # so the frontend can update the globe visualization.
                        if tm.name == "execute_maneuver_on_satellite":
                            try:
                                from api.state import get_satellite as _get_sat
                                _sat = _get_sat()
                                # Parse delta_v from the tool result
                                _dv = [0.0, 0.0, 0.0]
                                try:
                                    _res = json.loads(tm.content) if isinstance(tm.content, str) else {}
                                    if "delta_v" in _res:
                                        _dv = _res["delta_v"]
                                except Exception:
                                    pass
                                _emit({
                                    "type": "maneuver_executed",
                                    "agent": agent_name,
                                    "timestamp": time.time(),
                                    "position": _sat.position.tolist(),
                                    "velocity": _sat.velocity.tolist(),
                                    "delta_v": _dv,
                                }, events)
                            except Exception:
                                pass

        # Extract final response
        final_content = msgs[-1].content if msgs else ""

        elapsed = time.time() - t0
        _emit({
            "type": "agent_complete",
            "agent": agent_name,
            "elapsed_sec": round(elapsed, 2),
            "timestamp": time.time(),
        }, events)

        # Emit agent output for real-time display
        if final_content:
            _emit({
                "type": "agent_output",
                "agent": agent_name,
                "content": final_content,
                "timestamp": time.time(),
            }, events)

        logger.info(f"[{agent_name}] completed in {elapsed:.1f}s")

        return {
            "messages": [AIMessage(content=f"[{agent_name}] {final_content}", name=agent_name)],
            output_key: final_content,
            "current_agent": next_agent or agent_name,
            "events": events,
        }

    return agent_node


# ─────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────
def build_avoidance_graph(
    config: Optional[LLMConfig] = None,
    event_queue: Optional[queue_module.Queue] = None,
) -> StateGraph:
    """
    Build the multi-agent LangGraph for collision avoidance.

    Pipeline:
      scout → analyst → planner → safety → ops_brief → END
    """
    if config is None:
        config = LLMConfig.from_env()

    llm = ChatOpenAI(**config.to_llm_kwargs())

    # Create agent nodes
    scout_node = _create_agent_node(
        llm, SCOUT_PROMPT, SCOUT_TOOLS, "scout", "scout_output", "analyst",
        event_queue=event_queue,
    )
    analyst_node = _create_agent_node(
        llm, ANALYST_PROMPT, ANALYST_TOOLS, "analyst", "analyst_output", "planner",
        event_queue=event_queue,
    )
    planner_node = _create_agent_node(
        llm, PLANNER_PROMPT, PLANNER_TOOLS, "planner", "planner_output", "safety",
        event_queue=event_queue,
    )
    safety_node = _create_agent_node(
        llm, SAFETY_PROMPT, SAFETY_TOOLS, "safety", "safety_output", "ops_brief",
        event_queue=event_queue,
    )
    OPS_BRIEF_TOOLS = [assess_risk, execute_maneuver_on_satellite, get_satellite_status, propagate_satellite_orbit]
    ops_brief_node = _create_agent_node(
        llm, OPS_BRIEF_PROMPT, OPS_BRIEF_TOOLS, "ops_brief", "ops_brief", None,
        event_queue=event_queue,
    )

    # Build graph
    graph = StateGraph(AgentState)

    graph.add_node("scout", scout_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("planner", planner_node)
    graph.add_node("safety", safety_node)
    graph.add_node("ops_brief", ops_brief_node)

    # Linear pipeline
    graph.set_entry_point("scout")
    graph.add_edge("scout", "analyst")
    graph.add_edge("analyst", "planner")
    graph.add_edge("planner", "safety")
    graph.add_edge("safety", "ops_brief")
    graph.add_edge("ops_brief", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────
# Single-agent mode (simpler, for quick testing)
# ─────────────────────────────────────────────────────────────────────────
def build_single_agent_graph(
    config: Optional[LLMConfig] = None,
    event_queue: Optional[queue_module.Queue] = None,
) -> StateGraph:
    """
    Build a single-agent graph with all tools available.
    Simpler than the multi-agent pipeline, good for testing.
    """
    if config is None:
        config = LLMConfig.from_env()

    llm = ChatOpenAI(**config.to_llm_kwargs())

    SINGLE_AGENT_PROMPT = """You are Detour, an AI collision avoidance copilot for satellites.
You run on an NVIDIA edge AI device providing low-latency, local collision avoidance planning.

You have access to physics tools that compute real orbital mechanics. NEVER guess numbers.
Always call tools to get actual data.

When asked to analyze threats or plan avoidance:
1. Scan for conjunctions using scan_conjunctions or scan_demo_conjunctions
2. Assess risk for the most dangerous events
3. If risk is high, propose avoidance maneuvers
4. Check constraints on the best maneuver candidates
5. Present a clear recommendation to the operator

Be concise and actionable. Satellite operators need clear decisions, not essays."""

    agent_node = _create_agent_node(
        llm, SINGLE_AGENT_PROMPT, ALL_TOOLS, "detour", "ops_brief", None,
        event_queue=event_queue,
    )

    graph = StateGraph(AgentState)
    graph.add_node("detour", agent_node)
    graph.set_entry_point("detour")
    graph.add_edge("detour", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────
def run_avoidance_pipeline(
    request: str,
    config: Optional[LLMConfig] = None,
    mode: Literal["multi", "single"] = "multi",
) -> Dict[str, Any]:
    """
    Run the collision avoidance agent pipeline.

    Args:
        request: natural language request from the operator
        config: LLM configuration (defaults to env vars)
        mode: "multi" for 5-agent pipeline, "single" for single agent

    Returns:
        dict with ops_brief, events, and intermediate outputs
    """
    if mode == "multi":
        graph = build_avoidance_graph(config)
    else:
        graph = build_single_agent_graph(config)

    initial_state: AgentState = {
        "messages": [HumanMessage(content=request)],
        "current_agent": "scout" if mode == "multi" else "detour",
        "scout_output": None,
        "analyst_output": None,
        "planner_output": None,
        "safety_output": None,
        "ops_brief": None,
        "events": [],
    }

    result = graph.invoke(initial_state, {"recursion_limit": 50})

    return {
        "ops_brief": result.get("ops_brief", ""),
        "scout_output": result.get("scout_output"),
        "analyst_output": result.get("analyst_output"),
        "planner_output": result.get("planner_output"),
        "safety_output": result.get("safety_output"),
        "events": result.get("events", []),
    }


async def stream_avoidance_pipeline(
    request: str,
    config: Optional[LLMConfig] = None,
    mode: Literal["multi", "single"] = "multi",
):
    """
    Async generator that streams agent events as they happen.

    Uses a thread-safe queue so events from synchronous agent nodes
    (which LangGraph runs in a thread pool) are delivered to the
    async SSE generator in real time, instead of batching per-node.
    """
    eq: queue_module.Queue = queue_module.Queue()

    if mode == "multi":
        graph = build_avoidance_graph(config, event_queue=eq)
    else:
        graph = build_single_agent_graph(config, event_queue=eq)

    initial_state: AgentState = {
        "messages": [HumanMessage(content=request)],
        "current_agent": "scout" if mode == "multi" else "detour",
        "scout_output": None,
        "analyst_output": None,
        "planner_output": None,
        "safety_output": None,
        "ops_brief": None,
        "events": [],
    }

    done = asyncio.Event()

    async def _run_graph():
        try:
            async for _chunk in graph.astream(initial_state, {"recursion_limit": 50}):
                pass  # events are pushed to the queue from inside nodes
        except Exception as e:
            eq.put({"type": "error", "message": str(e), "timestamp": time.time()})
        finally:
            done.set()

    task = asyncio.create_task(_run_graph())

    # Poll the queue, yielding events as they arrive
    while not done.is_set() or not eq.empty():
        try:
            event = eq.get_nowait()
            yield event
        except queue_module.Empty:
            await asyncio.sleep(0.1)

    # Drain any remaining events
    while not eq.empty():
        yield eq.get_nowait()

    yield {"type": "pipeline_complete", "timestamp": time.time()}

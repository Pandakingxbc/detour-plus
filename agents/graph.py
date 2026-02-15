"""
LangGraph multi-agent collision avoidance pipeline.

Five agents form a sequential pipeline, each with specialized tools:
  Scout → Analyst → Planner → Safety → Ops Brief

Uses Nemotron via vLLM's OpenAI-compatible API + LangChain + LangGraph.
"""
from __future__ import annotations

import json
import logging
import operator
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
)

logger = logging.getLogger("detour.agents.graph")


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
):
    """
    Create a LangGraph node that:
    1. Calls the LLM with tool-calling enabled
    2. Loops on tool calls until the LLM is done
    3. Stores its final response in state[output_key]
    4. Emits events for real-time streaming
    """
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    tool_node = ToolNode(tools) if tools else None

    def agent_node(state: AgentState) -> dict:
        """Run one agent to completion (with tool-calling loop)."""
        t0 = time.time()
        events = [{
            "type": "agent_start",
            "agent": agent_name,
            "timestamp": time.time(),
        }]

        # Build messages: system prompt + all prior messages + handoff context
        msgs: List[BaseMessage] = [SystemMessage(content=system_prompt)]

        # Add context from previous agents
        for key, label in [
            ("scout_output", "Scout findings"),
            ("analyst_output", "Analyst assessment"),
            ("planner_output", "Planner recommendations"),
            ("safety_output", "Safety review"),
        ]:
            val = state.get(key)
            if val and key != output_key:
                msgs.append(HumanMessage(content=f"[{label}]\n{val}"))

        # Add the original user request (first human message)
        for m in state["messages"]:
            if isinstance(m, HumanMessage):
                msgs.append(m)
                break

        # Tool-calling loop
        max_iterations = 10
        for iteration in range(max_iterations):
            response = llm_with_tools.invoke(msgs)
            msgs.append(response)

            # If no tool calls, we're done
            if not response.tool_calls:
                break

            # Execute tool calls
            events.append({
                "type": "tool_calls",
                "agent": agent_name,
                "tools": [tc["name"] for tc in response.tool_calls],
                "timestamp": time.time(),
            })

            if tool_node:
                # Create a mini-state for the tool node
                tool_results = tool_node.invoke({"messages": msgs})
                tool_msgs = tool_results.get("messages", [])
                msgs.extend(tool_msgs)

                for tm in tool_msgs:
                    if isinstance(tm, ToolMessage):
                        events.append({
                            "type": "tool_result",
                            "agent": agent_name,
                            "tool": tm.name,
                            "timestamp": time.time(),
                            # Truncate large outputs for event stream
                            "summary": tm.content[:200] if isinstance(tm.content, str) else str(tm.content)[:200],
                        })

        # Extract final response
        final_content = msgs[-1].content if msgs else ""

        elapsed = time.time() - t0
        events.append({
            "type": "agent_complete",
            "agent": agent_name,
            "elapsed_sec": round(elapsed, 2),
            "timestamp": time.time(),
        })

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
def build_avoidance_graph(config: Optional[LLMConfig] = None) -> StateGraph:
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
        llm, SCOUT_PROMPT, SCOUT_TOOLS, "scout", "scout_output", "analyst"
    )
    analyst_node = _create_agent_node(
        llm, ANALYST_PROMPT, ANALYST_TOOLS, "analyst", "analyst_output", "planner"
    )
    planner_node = _create_agent_node(
        llm, PLANNER_PROMPT, PLANNER_TOOLS, "planner", "planner_output", "safety"
    )
    safety_node = _create_agent_node(
        llm, SAFETY_PROMPT, SAFETY_TOOLS, "safety", "safety_output", "ops_brief"
    )
    ops_brief_node = _create_agent_node(
        llm, OPS_BRIEF_PROMPT, [], "ops_brief", "ops_brief", None
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
def build_single_agent_graph(config: Optional[LLMConfig] = None) -> StateGraph:
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
        llm, SINGLE_AGENT_PROMPT, ALL_TOOLS, "detour", "ops_brief", None
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
    Use with SSE endpoint for real-time frontend updates.
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

    # Stream updates as the graph executes
    seen_events = 0
    async for chunk in graph.astream(initial_state, {"recursion_limit": 50}):
        # Each chunk is a dict with the node name as key
        for node_name, node_output in chunk.items():
            if node_name == "__end__":
                yield {"type": "pipeline_complete", "timestamp": time.time()}
                return

            events = node_output.get("events", [])
            for event in events[seen_events:]:
                yield event
            seen_events = 0  # reset for next node

            # Yield intermediate outputs
            for key in ["scout_output", "analyst_output", "planner_output", "safety_output", "ops_brief"]:
                val = node_output.get(key)
                if val:
                    yield {
                        "type": "agent_output",
                        "agent": key.replace("_output", ""),
                        "content": val,
                        "timestamp": time.time(),
                    }

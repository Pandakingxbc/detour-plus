"""
Detour Agents — Multi-agent collision avoidance orchestrator.

Uses NVIDIA Nemotron (served via vLLM on the GX10) with LangGraph
for multi-agent tool-calling workflows.

Architecture:
  ┌─────────┐     ┌──────────┐     ┌─────────┐     ┌────────┐     ┌───────┐
  │  Scout  │ ──▶ │ Analyst  │ ──▶ │ Planner │ ──▶ │ Safety │ ──▶ │  Ops  │
  └─────────┘     └──────────┘     └─────────┘     └────────┘     └───────┘
     scan &          assess           propose         check          produce
     triage          risk             maneuvers       constraints    brief
"""

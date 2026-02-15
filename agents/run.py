#!/usr/bin/env python3
"""
CLI for testing the Detour agent pipeline.

Usage:
    # Full 5-agent pipeline
    python -m agents.run "Scan ISS for conjunction threats in the next 24 hours"

    # Single-agent mode
    python -m agents.run --mode single "What threats does satellite 25544 face?"

    # With demo data
    python -m agents.run --demo "Analyze threats for ISS and recommend avoidance maneuvers"

    # Custom Nemotron endpoint
    python -m agents.run --base-url http://gx10:8001/v1 "Scan for threats"
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from agents.config import LLMConfig
from agents.graph import run_avoidance_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Detour Agent CLI — collision avoidance copilot"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Scan for conjunction threats against the ISS (NORAD 25544) in the next 24 hours. "
                "If any are high risk, propose avoidance maneuvers and check constraints. "
                "Use the demo dataset.",
        help="Natural language request for the agent",
    )
    parser.add_argument(
        "--mode", choices=["multi", "single"], default="multi",
        help="Agent mode: multi (5-agent pipeline) or single",
    )
    parser.add_argument("--demo", action="store_true", default=True, help="Use demo data")
    parser.add_argument("--base-url", type=str, default=None, help="LLM API base URL")
    parser.add_argument("--model", type=str, default=None, help="Model name")
    parser.add_argument("--api-key", type=str, default=None, help="API key")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show events")
    args = parser.parse_args()

    # Build config
    config = LLMConfig.from_env()
    if args.base_url:
        config.base_url = args.base_url
    if args.model:
        config.model = args.model
    if args.api_key:
        config.api_key = args.api_key

    # Append demo instruction if needed
    prompt = args.prompt
    if args.demo and "demo" not in prompt.lower():
        prompt += "\nUse the demo dataset (scan_demo_conjunctions tool)."

    print(f"{'='*60}")
    print(f"  Detour Agent Pipeline")
    print(f"  Mode: {args.mode}")
    print(f"  LLM:  {config.model}")
    print(f"  URL:  {config.base_url}")
    print(f"{'='*60}")
    print(f"\n  Prompt: {prompt}\n")
    print(f"{'='*60}")

    t0 = time.time()

    try:
        result = run_avoidance_pipeline(prompt, config=config, mode=args.mode)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"\nIs vLLM running at {config.base_url}?")
        print(f"  Start with: ./scripts/setup_gx10.sh")
        print(f"  Or set NEMOTRON_BASE_URL in .env")
        sys.exit(1)

    elapsed = time.time() - t0

    # Show events if verbose
    if args.verbose:
        print(f"\n{'─'*60}")
        print("  Events:")
        for event in result.get("events", []):
            print(f"    [{event.get('type'):>16s}] {event.get('agent', '')}: "
                  f"{event.get('tools', event.get('summary', ''))}")

    # Show intermediate outputs
    for key, label in [
        ("scout_output", "SCOUT"),
        ("analyst_output", "ANALYST"),
        ("planner_output", "PLANNER"),
        ("safety_output", "SAFETY"),
    ]:
        val = result.get(key)
        if val:
            print(f"\n{'─'*60}")
            print(f"  [{label}]")
            print(f"{'─'*60}")
            # Truncate long outputs
            if len(val) > 1000:
                print(val[:1000] + "\n... (truncated)")
            else:
                print(val)

    # Show final brief
    brief = result.get("ops_brief", "")
    if brief:
        print(f"\n{'═'*60}")
        print(f"  OPERATOR BRIEF")
        print(f"{'═'*60}")
        print(brief)

    print(f"\n{'═'*60}")
    print(f"  Completed in {elapsed:.1f}s")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()

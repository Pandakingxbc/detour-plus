# Detour — On-Board AI Agents Saving Satellites from Orbital Debris

**TreeHacks 2026 | NVIDIA Edge AI Track**

Detour is an autonomous collision-avoidance system that runs **on-board** a satellite using NVIDIA's Nemotron LLM on the ASUS Ascent GX10 (Grace Blackwell). A multi-agent LangGraph pipeline detects debris threats, assesses risk, plans maneuvers, validates safety constraints, and executes avoidance burns — all locally with zero ground-station latency.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    ASUS Ascent GX10 (On-Board)                   │
│                                                                  │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────┐ │
│  │  SCOUT  │→ │ ANALYST  │→ │ PLANNER  │→ │ SAFETY │→ │ OPS  │ │
│  │ scan &  │  │ risk &   │  │ maneuver │  │ verify │  │BRIEF │ │
│  │ triage  │  │ refine   │  │ design   │  │& exec  │  │      │ │
│  └─────────┘  └──────────┘  └──────────┘  └────────┘  └──────┘ │
│       ↕             ↕             ↕             ↕               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Physics Engine (deterministic)               │   │
│  │  screening · risk · CW dynamics · RK4 · SGP4 · Chan Pc   │   │
│  └──────────────────────────────────────────────────────────┘   │
│       ↕                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          Satellite Model (fuel, power, dynamics)          │   │
│  └──────────────────────────────────────────────────────────┘   │
│       ↕                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Nemotron 3 Nano 30B (BF16) via vLLM — local inference   │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## Key Components

| Component | Path | Description |
|-----------|------|-------------|
| **Agent Pipeline** | `agents/` | LangGraph 5-agent pipeline with tool-calling |
| **Physics Engine** | `engine/` | RK4 solver, J2 perturbation, CW dynamics, Chan collision probability |
| **Satellite Model** | `engine/models/active_satellite.py` | Full orbital dynamics with resource management (fuel, power, battery) |
| **Tool Wrappers** | `agents/tools.py` | 11 LangChain tools wrapping the physics engine |
| **API** | `api/` | FastAPI server with agent, catalog, conjunction, and satellite endpoints |
| **Frontend** | `frontend2/` | Next.js + React Three Fiber 3D globe with live satellite tracking |
| **GX10 Setup** | `scripts/setup_gx10.sh` | One-command setup for the ASUS Ascent GX10 |

## Agent Pipeline

| Agent | Role | Tools |
|-------|------|-------|
| **Scout** | Scan catalog for upcoming conjunctions, triage by severity | `scan_conjunctions`, `scan_demo_conjunctions` |
| **Analyst** | Deep risk assessment — Chan probability, high-fidelity TCA refinement | `assess_risk`, `refine_conjunction`, `propagate_orbit` |
| **Planner** | Design avoidance maneuvers considering satellite resources | `propose_avoidance_maneuvers`, `simulate_maneuver`, `get_satellite_status`, `check_maneuver_feasibility` |
| **Safety** | Validate constraints, approve or reject, execute approved burns | `check_maneuver_constraints`, `get_satellite_status`, `check_maneuver_feasibility`, `execute_maneuver_on_satellite` |
| **Ops Brief** | Generate human-readable summary for operators | _(synthesis only)_ |

## Quick Start

### 1. Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.app:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend2
npm install
npm run dev  # localhost:3000
```

### 3. Agent System (with GX10)

```bash
# Start Nemotron on the GX10
chmod +x scripts/setup_gx10.sh
./scripts/setup_gx10.sh

# Run agent pipeline
python -m agents.run "Scan for conjunction threats to satellite 25544 in the next 48 hours" --demo
```

### 4. Agent System (without GPU — dev mode)

```bash
# Set OPENAI fallback in .env
NEMOTRON_BASE_URL=https://api.openai.com/v1
NEMOTRON_API_KEY=sk-...
NEMOTRON_MODEL=gpt-4o-mini

python -m agents.run "Scan for threats" --demo
```

## Model

**nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4** — 4-bit quantized (NVFP4) for fast edge inference on the Ascent GX10. ~15GB model weight footprint, leaving ample memory for KV cache and concurrent requests on the 128GB unified memory Grace Blackwell SoC.

Served locally via NGC vLLM container with tool-calling (`--enable-auto-tool-choice --tool-call-parser hermes --enable-chunked-prefill`).

## Why Edge AI?

| Ground Station | On-Board (Detour) |
|---------------|-------------------|
| 5-15 min communication delay | **< 1 sec** decision |
| Limited pass windows | **24/7** monitoring |
| Single point of failure | **Autonomous** operation |
| Manual operator in the loop | **Agent-validated** decisions |

In LEO, a debris collision can happen in minutes. You can't wait for the next ground station pass.

## Team

- **Keanu** — Backend, AI Inference, Agent System
- **Adit** — Data Science, Satellite Model, Agent Design
- **Justyna** — Edge AI, Satellite Systems
- **Ethan** — Edge AI, Simulator, 3D Visualization

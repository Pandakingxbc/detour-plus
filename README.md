# DETOUR-Plus — Multi-Maneuver Satellite Collision Avoidance System

> **Extended from [DETOUR](https://github.com/keanucz/detour)** — TreeHacks 2026 Winner (NVIDIA Edge AI Track)
>
> **Extended by**: Yang Zhi (杨植) | Beijing Institute of Technology

[![Demo Video](https://img.shields.io/badge/Demo-Video-red?style=for-the-badge&logo=youtube)](assets/demo.mp4)
[![GitHub](https://img.shields.io/badge/GitHub-Pandakingxbc-blue?style=for-the-badge&logo=github)](https://github.com/Pandakingxbc/detour-plus)

## What's New in DETOUR-Plus

| Feature | Original DETOUR | DETOUR-Plus |
|---------|----------------|-------------|
| **Maneuver Planning** | Single threat, single burn | **Multi-threat, optimal sequence** |
| **Secondary Detection** | No | **Yes** - Check for new conjunctions |
| **Harmonic Analysis** | No | **Yes** - Orbital resonance detection |
| **Agent Pipeline** | 5 agents | **6 agents** (+ Strategist) |
| **Optimization** | Heuristic | **Fuel-constrained optimization** |

---

DETOUR-Plus is an autonomous collision-avoidance system that runs **on-board** a satellite. The multi-agent LangGraph pipeline detects debris threats, assesses risk, **plans optimal multi-maneuver sequences**, validates safety constraints, and executes avoidance burns.

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
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Physics Engine (deterministic)               │   │
│  │  screening · risk · CW dynamics · RK4 · SGP4 · Chan Pc   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       ↕                                                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │          Satellite Model (fuel, power, dynamics)          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│       ↕                                                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Nemotron 3 Nano 30B (NVFP4) via vLLM — local inference  │   │
│  └──────────────────────────────────────────────────────────────┘   │
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
| **Frontend** | `frontend/` | Next.js + React Three Fiber 3D globe with live satellite tracking |
| **Ascent GX10 Setup** | `scripts/setup_gx10.sh` | One-command setup for the ASUS Ascent GX10 |

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
cd frontend
npm install
npm run dev  # localhost:3000
```

### 3. Agent System (with Ascent GX10)

```bash
# Start Nemotron on the Ascent GX10
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

## DETOUR-Plus New Components

### Multi-Impulse Optimizer (`engine/maneuver/multi_impulse.py`)

Solves the multi-conjunction avoidance problem with fuel constraints:

```
Given: N conjunction threats at times [t1, t2, ..., tN]
       Fuel budget F_max
       Target miss distance D_target

Find:  Optimal maneuver sequence [(t_burn_1, Δv_1), (t_burn_2, Δv_2), ...]

Subject to:
       Σ fuel_i ≤ F_max
       |Δv_i| ≤ max_dv_per_burn
       No secondary conjunctions created
```

### Harmonic Analysis (`engine/maneuver/harmonic_analysis.py`)

Detects problematic orbital resonances:
- **Orbital resonance detection**: n1/n2 = p/q for small integers
- **Synodic period calculation**: Time between successive close approaches
- **Recurrence prediction**: Will the conjunction geometry repeat?

### Strategist Agent (NEW)

```python
STRATEGIST_TOOLS = [
    plan_multi_maneuver_sequence,    # Optimal sequence planning
    check_secondary_conjunctions,     # Safety verification
    analyze_orbital_harmonics,        # Resonance detection
    evaluate_maneuver_safety_score,   # Comprehensive scoring
    get_multi_threat_summary,         # Threat overview
]
```

## Quick Demo

```bash
# Activate environment
conda activate detour
cd /path/to/detour

# Run core algorithm demo
python demo_test.py

# Run full agent pipeline
python -m agents.run --demo "Scan for threats to ISS"
```

## Team

**Original DETOUR Team (TreeHacks 2026):**
- **Justyna** — Frontend, 3D Visualization, UI/UX
- **Ethan** — ASUS Ascent GX10 Setup, Simulation Logic
- **Adit** — Satellite Data Feed, Simulation Logic
- **Keanu** — Ascent GX10 vLLM Setup, LangChain NVIDIA Nemotron Agent System

**DETOUR-Plus Extension:**
- **Yang Zhi (杨植)** — Multi-maneuver optimization, Harmonic analysis, Strategist Agent
  - M.S. in Artificial Intelligence, Beijing Institute of Technology
  - Email: yangzhi0776@163.com

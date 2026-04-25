# DETOUR-Plus: Multi-Maneuver Satellite Collision Avoidance System

> **Extended from [DETOUR](https://github.com/keanucz/detour)** - TreeHacks 2026 Winner (NVIDIA Edge AI Track)
>
> **Author**: Yang Zhi (杨植) | Beijing Institute of Technology

## Overview

DETOUR-Plus extends the original DETOUR project with **multi-maneuver trajectory planning** capabilities. When a satellite faces multiple collision threats within a short time window, this system can plan an optimal sequence of maneuvers while respecting fuel constraints and avoiding secondary conjunctions.

### Key Innovations

| Feature | Original DETOUR | DETOUR-Plus |
|---------|----------------|-------------|
| **Maneuver Planning** | Single threat, single burn | Multi-threat, optimal sequence |
| **Secondary Detection** | ❌ | ✅ Check for new conjunctions |
| **Harmonic Analysis** | ❌ | ✅ Orbital resonance detection |
| **Agent Pipeline** | 5 agents | 6 agents (+ Strategist) |
| **Optimization** | Heuristic | Fuel-constrained optimization |

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    DETOUR-Plus Agent Pipeline                   │
│                                                                │
│  ┌────────┐   ┌─────────┐   ┌────────────┐   ┌─────────┐      │
│  │ SCOUT  │ → │ ANALYST │ → │ STRATEGIST │ → │ PLANNER │      │
│  │ scan   │   │ assess  │   │ multi-man  │   │ single  │      │
│  │threats │   │ risk    │   │ sequence   │   │ design  │      │
│  └────────┘   └─────────┘   └────────────┘   └─────────┘      │
│                                                    ↓           │
│  ┌──────────┐   ┌────────┐                  ┌──────────┐      │
│  │ OPS BRIEF│ ← │ SAFETY │ ←────────────────│ validate │      │
│  │ report   │   │ verify │                  │constraints│     │
│  └──────────┘   └────────┘                  └──────────┘      │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              Multi-Impulse Optimizer                    │   │
│  │  • Fuel-constrained trajectory optimization             │   │
│  │  • Secondary conjunction detection                      │   │
│  │  • Orbital harmonic/resonance analysis                  │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

## New Components

### 1. Multi-Impulse Optimizer (`engine/maneuver/multi_impulse.py`)

Solves the multi-conjunction avoidance problem:

```
Given: N conjunction threats at times [t1, t2, ..., tN]
       Fuel budget F_max
       Target miss distance D_target

Find:  Optimal maneuver sequence [(t_burn_1, Δv_1), (t_burn_2, Δv_2), ...]

Subject to:
       • Σ fuel_i ≤ F_max
       • |Δv_i| ≤ max_dv_per_burn
       • t_burn_{i+1} - t_burn_i ≥ min_interval (thermal recovery)
       • No secondary conjunctions created
```

### 2. Harmonic Analysis (`engine/maneuver/harmonic_analysis.py`)

Detects problematic orbital resonances:

- **Orbital resonance detection**: n1/n2 = p/q for small integers
- **Synodic period calculation**: Time between successive close approaches
- **Recurrence prediction**: Will the conjunction geometry repeat?

### 3. Strategist Agent

New agent role that handles multi-threat scenarios:

```python
STRATEGIST_TOOLS = [
    plan_multi_maneuver_sequence,    # Optimal sequence planning
    check_secondary_conjunctions,     # Safety verification
    analyze_orbital_harmonics,        # Resonance detection
    evaluate_maneuver_safety_score,   # Comprehensive scoring
    get_multi_threat_summary,         # Threat overview
]
```

## Quick Start

### Prerequisites

```bash
# Create conda environment
conda create -n detour python=3.11 -y
conda activate detour

# Install dependencies
pip install -r requirements.txt
pip install scipy
```

### Configuration

Create `.env` file with your API key:

```bash
# Using DeepSeek API
NEMOTRON_BASE_URL=https://api.deepseek.com/v1
NEMOTRON_API_KEY=your_api_key
NEMOTRON_MODEL=deepseek-chat
```

### Running

```bash
# Standard 5-agent pipeline
python -m agents.run --demo "Scan for threats to ISS"

# Strategic mode with multi-maneuver planning
python -m agents.run --mode strategic --demo "Plan multi-maneuver avoidance"

# Start full system (API + Frontend)
./run.sh
```

## Demo Scenarios

### Scenario 1: Multiple Critical Threats

```bash
python -m agents.run --demo "ISS faces 3 critical conjunctions in next 12 hours.
Plan optimal avoidance sequence with 10kg fuel budget."
```

### Scenario 2: Secondary Conjunction Detection

```bash
python -m agents.run --demo "Check if avoiding COSMOS 2251 DEB creates
new conjunctions with other debris."
```

## Technical Highlights

### Fuel Optimization

Uses Tsiolkovsky rocket equation for accurate fuel consumption:

```python
def _fuel_for_dv(self, dv_ms: float, current_mass_kg: float) -> float:
    ve = self.config.isp_s * G0  # Exhaust velocity
    mass_ratio = math.exp(dv_ms / ve)
    return current_mass_kg * (1.0 - 1.0 / mass_ratio)
```

### Resonance Detection

Identifies orbital resonances that could cause recurring encounters:

```python
def detect_orbital_resonance(sat_elements, debris_elements):
    ratio = n1 / n2  # Mean motion ratio
    # Search for p/q where ratio ≈ p/q
    # Warning levels: 1:1 (co-orbital), 2:1, 3:2, etc.
```

## File Structure

```
detour/
├── agents/
│   ├── graph.py          # Agent pipeline (+ strategic mode)
│   ├── prompts.py        # System prompts (+ STRATEGIST_PROMPT)
│   └── tools.py          # LangChain tools (+ 5 new tools)
├── engine/
│   ├── maneuver/
│   │   ├── multi_impulse.py      # NEW: Multi-maneuver optimizer
│   │   └── harmonic_analysis.py  # NEW: Orbital harmonics
│   ├── core/
│   │   ├── engine1.py    # Fast screening
│   │   └── engine2.py    # High-fidelity propagation
│   └── physics/
│       └── cw_relative.py # Clohessy-Wiltshire dynamics
└── frontend/             # React Three Fiber visualization
```

## Performance

| Metric | Value |
|--------|-------|
| Multi-maneuver planning | < 30 seconds for 3+ threats |
| Secondary conjunction check | < 5 seconds |
| Harmonic analysis | < 2 seconds |
| Full pipeline (strategic) | ~120 seconds |

## Future Work

- [ ] GPU-accelerated Monte Carlo for probability estimation
- [ ] Real-time TLE data integration (Space-Track API)
- [ ] Multi-satellite constellation coordination
- [ ] Reinforcement learning for maneuver policy

## References

- Original DETOUR: https://github.com/keanucz/detour
- LangGraph: https://github.com/langchain-ai/langgraph
- Clohessy-Wiltshire equations for relative motion
- Chan collision probability method

## Author

**Yang Zhi (杨植)**
- M.S. in Artificial Intelligence, Beijing Institute of Technology
- Email: yangzhi0776@163.com

---

*Extended as part of aerospace interview preparation, April 2025*

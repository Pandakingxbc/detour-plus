# Detour Agent Pipeline

Sequential 5-agent collision avoidance pipeline running on-board via LangGraph.

```
Scout → Analyst → Planner → Safety → Ops Brief → END
```

---

## Agent 0 — Scout

**Role:** Conjunction scanner — first line of defense.

**Tools:**
| Tool | Description |
|------|-------------|
| `get_pending_cdms` | Retrieve incoming Conjunction Data Messages |
| `scan_conjunctions` | Screen orbital catalog for close approaches |
| `scan_demo_conjunctions` | Load demo debris data and scan |

**Steps:**
1. `scan_demo_conjunctions` or `scan_conjunctions` to find close approaches
2. `get_pending_cdms` to check for pending CDMs
3. Summarize threats: total screened, top 5 ranked by miss distance

---

## Agent 1 — Analyst

**Role:** Deep risk assessment — collision probability and HiFi refinement.

**Tools:**
| Tool | Description |
|------|-------------|
| `get_pending_cdms` | Retrieve incoming CDMs |
| `scan_conjunctions` | Re-scan catalog if needed |
| `scan_demo_conjunctions` | Re-scan demo data if needed |
| `assess_risk` | Compute collision probability (Chan method) for an event |
| `refine_conjunction_hifi` | HiFi propagation (RK45 + J2/J3/J4 + drag) for TCA refinement |

**Steps:**
1. Review Scout findings
2. `assess_risk` for each flagged event → collision probability + risk level
3. `refine_conjunction_hifi` for critical/high events → refined TCA and miss distance
4. Rank by urgency, flag events needing maneuvers

---

## Agent 2 — Planner

**Role:** Trajectory optimization — designs avoidance maneuvers using CW dynamics.

**Tools:**
| Tool | Description |
|------|-------------|
| `propose_avoidance_maneuvers` | Generate candidate delta-V profiles (along-track, radial, cross-track) |
| `simulate_maneuver_effect` | Simulate a candidate to verify miss distance improvement |
| `assess_risk` | Re-assess risk with maneuver applied |

**Steps:**
1. `propose_avoidance_maneuvers` for each high-risk event
2. `simulate_maneuver_effect` for top 1-2 candidates
3. Select best maneuver: minimize fuel, maximize risk reduction
4. Output ranked candidates with delta-v, fuel cost, predicted miss distance

---

## Agent 3 — Safety

**Role:** Resource guardian — enforces constraints, protects satellite resources.

**Tools:**
| Tool | Description |
|------|-------------|
| `get_satellite_status` | Current telemetry: fuel, power, delta-v budget |
| `check_maneuver_constraints` | Validate fuel budget, max delta-v, min altitude, blackout windows |
| `check_maneuver_feasibility` | Verify maneuver is physically executable |
| `propagate_satellite_orbit` | Propagate trajectory to verify post-maneuver orbit |

**Steps:**
1. `get_satellite_status` → fuel %, power %, operational status
2. `check_maneuver_feasibility` for each proposed maneuver
3. `check_maneuver_constraints` → pass/fail per constraint
4. `propagate_satellite_orbit` to verify trajectory
5. Verdict: APPROVED / CONDITIONAL / REJECTED

---

## Agent 4 — Ops Brief

**Role:** Execution and operator briefing — applies burns and reports results.

**Tools:**
| Tool | Description |
|------|-------------|
| `assess_risk` | Final risk check |
| `execute_maneuver_on_satellite` | Apply delta-v vector to satellite thrusters |
| `get_satellite_status` | Post-execution verification |
| `propagate_satellite_orbit` | Verify new trajectory |

**Steps:**
1. `execute_maneuver_on_satellite` with approved delta-v vector
2. `get_satellite_status` → confirm velocity change, fuel consumption
3. `propagate_satellite_orbit` → verify post-maneuver trajectory
4. Generate structured operator brief with threat summary, maneuver details, and satellite status

---

## SSE Events

The pipeline streams events in real-time via Server-Sent Events:

| Event | When |
|-------|------|
| `agent_start` | Agent begins processing |
| `llm_call` | LLM invocation (with iteration count) |
| `thinking` | Synthetic reasoning text for operator display |
| `tool_calls` | Tool invocations (lists tool names) |
| `tool_result` | Tool output (truncated summary) |
| `maneuver_executed` | Post-maneuver state (position, velocity, delta_v) — triggers globe update |
| `agent_complete` | Agent finished (with elapsed time) |
| `agent_output` | Final agent response text |
| `pipeline_complete` | All agents done |

## Data Flow: Maneuver → Globe

```
execute_maneuver_on_satellite(delta_v)
  → Python Satellite.apply_maneuver() updates velocity
  → graph.py emits SSE { type: "maneuver_executed", position, velocity, delta_v }
  → terminal-drawer.tsx receives event, calls onManeuverExecuted()
  → dashboard-shell.tsx passes maneuverEvent to GlobeView
  → globe-view.tsx perturbs current orbit points by delta_v direction
  → OrbitTrack + TargetMarker animate red flash (3.5s)
  → Globe renders updated orbit
```

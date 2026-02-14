

# src/simulation/runner.py
from typing import List, Tuple, Any, Dict
from engine.engine.engine1 import Engine1
from engine.engine.engine2 import Engine2
from engine.config import settings
from engine.physics.entity import Entity
def _normalize_engine1_output(raw, debris_list):
    """
    Engine-1 may return:
      - a list of result dicts,
      - a tuple (results, positions_sat, positions_debris),
      - a tuple (results, positions_debris),
      - a single dict (rare)
    This helper coaxes those shapes into (results, positions_sat, positions_debris).
    """
    results = []
    positions_sat = []
    positions_debris = [[] for _ in debris_list]
    # Tuple outputs
    if isinstance(raw, tuple):
        if len(raw) == 3:
            results = raw[0] or []
            positions_sat = raw[1] or []
            positions_debris = raw[2] or [[] for _ in debris_list]
        elif len(raw) == 2:
            results = raw[0] or []
            positions_debris = raw[1] or [[] for _ in debris_list]
        else:
            # Unexpected tuple shape — try to flatten
            results = list(raw)
    elif isinstance(raw, list):
        results = raw
    elif isinstance(raw, dict):
        results = [raw]
    else:
        # Unknown shape — attempt best-effort conversion
        try:
            results = list(raw)
        except Exception:
            results = []
    # Ensure results is a list of dicts
    normalized = []
    for r in results:
        if not isinstance(r, dict):
            # Try to coerce (skip if impossible)
            try:
                r = dict(r)
            except Exception:
                r = {"raw": repr(r)}
        # ensure debris id exists in some form
        r.setdefault("debris_id", r.get("name", r.get("debris", "debris")))
        normalized.append(r)
    return normalized, positions_sat, positions_debris
def run_simulation(engine_name: str, satellite: Any, debris_list: List[Any], dt: float, steps: int) -> Tuple[List[Dict], List, List]:
    """
    Engine selector and simulation runner.
    engine1 → fast analytical screening (vectorized; expects debris_list)
    engine2 → high-fidelity physics propagation (pairwise; expects Entities)
    """
    engine_name = engine_name.lower()
    # =========================
    # ENGINE 1: FAST SCREENING
    # =========================
    if engine_name == "engine1":
        engine = Engine1()
        # Engine-1 is vectorized: pass the whole debris_list (positional arg)
        raw = engine.run(
            satellite,
            debris_list,
            dt=dt,
            steps=steps
        )

        if isinstance(raw, dict) and "screening" in raw:
            results = raw["screening"]
            positions_sat = raw.get("positions_sat", [])
            positions_debris = raw.get("positions_debris", [])
        else:
            results, positions_sat, positions_debris = _normalize_engine1_output(raw, debris_list)

        return results, positions_sat, positions_debris
    # =========================
    # ENGINE 2: HIGH FIDELITY
    # =========================
    elif engine_name == "engine2":
        engine = Engine2(
            dt=dt,
            adaptive_threshold=5000.0,
            enable_drag=True
        )
        results = []
        # Convert Satellite -> Entity (Engine-2 requires full physics Entities)
        sat_entity = Entity(
            position=satellite.position,
            velocity=satellite.velocity
        )
        for debris in debris_list:
            # Convert each debris to an Entity too
            deb_entity = Entity(
                position=debris.position,
                velocity=debris.velocity
            )
            r = engine.run(
                sat_entity,
                deb_entity,
                getattr(settings, "LOOKAHEAD_SEC", steps * dt),
                use_engine1_escalation=False # FORCE ENGINE-2 behavior
            )
            # Ensure we store a dict and add debris id
            if not isinstance(r, dict):
                try:
                    r = dict(r)
                except Exception:
                    r = {"raw": repr(r)}
            r.setdefault("debris_id", getattr(debris, "name", getattr(debris, "id", "debris")))
            results.append(r)
        # Engine-2 does not produce animation trajectories via runner
        return results, [], []
    # =========================
    else:
        raise ValueError(f"Unknown engine: {engine_name}")
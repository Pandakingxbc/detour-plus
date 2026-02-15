#!/usr/bin/env python3
"""
Generate a week of simulated satellite + debris conjunction data for the Detour demo.

Outputs two JSON files into frontend/public/:
  1. demo_satellites.json  — satellite positions sampled every 60s for 7 days
  2. demo_conjunctions.json — debris positions + CDM-like conjunction events

Usage:
    python -m tools.generate_demo_data [--days 7] [--dt 60] [--out-dir frontend/public]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple

import numpy as np

# ── project imports ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.config.settings import GM, RE
from engine.physics.state import State
from engine.physics.forces import NewtonianGravity, J2Perturbation, CompositeForce
from engine.physics.solver import RK4Solver

# ── constants ────────────────────────────────────────────────────────────
WEEK_SECONDS = 7 * 86400
DEFAULT_DT = 60  # seconds between samples


# ── helper: orbital elements → ECI state ─────────────────────────────────
def keplerian_to_eci(
    a: float,          # semi-major axis (m)
    e: float,          # eccentricity
    inc: float,        # inclination (rad)
    raan: float,       # right ascension of ascending node (rad)
    argp: float,       # argument of perigee (rad)
    nu: float,         # true anomaly (rad)
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert classical orbital elements to ECI position & velocity."""
    p = a * (1 - e**2)
    r_mag = p / (1 + e * math.cos(nu))

    # Perifocal frame
    r_pqw = r_mag * np.array([math.cos(nu), math.sin(nu), 0.0])
    v_pqw = math.sqrt(GM / p) * np.array([-math.sin(nu), e + math.cos(nu), 0.0])

    # Rotation matrix PQW → ECI
    cos_O, sin_O = math.cos(raan), math.sin(raan)
    cos_i, sin_i = math.cos(inc), math.sin(inc)
    cos_w, sin_w = math.cos(argp), math.sin(argp)

    R = np.array([
        [cos_O * cos_w - sin_O * sin_w * cos_i,
         -cos_O * sin_w - sin_O * cos_w * cos_i,
         sin_O * sin_i],
        [sin_O * cos_w + cos_O * sin_w * cos_i,
         -sin_O * sin_w + cos_O * cos_w * cos_i,
         -cos_O * sin_i],
        [sin_w * sin_i,
         cos_w * sin_i,
         cos_i],
    ])

    return R @ r_pqw, R @ v_pqw


# ── helper: ECI → lat/lon/alt ────────────────────────────────────────────
def gmst(epoch: datetime) -> float:
    """Approximate GMST angle (radians) at *epoch*."""
    j2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    d = (epoch - j2000).total_seconds() / 86400.0
    # Earth rotation: 360.985 deg/day from J2000
    return math.radians((280.46061837 + 360.98564736629 * d) % 360)


def eci_to_lla(r_eci: np.ndarray, epoch: datetime) -> Tuple[float, float, float]:
    """ECI → (lat_deg, lon_deg, alt_km)."""
    theta = gmst(epoch)
    c, s = math.cos(-theta), math.sin(-theta)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    ecef = R @ r_eci
    x, y, z = ecef
    r = np.linalg.norm(ecef)
    lat = math.degrees(math.asin(z / r)) if r > 0 else 0.0
    lon = math.degrees(math.atan2(y, x))
    alt_km = (r - RE) / 1000.0
    return lat, lon, alt_km


# ── satellite definitions ────────────────────────────────────────────────
# Realistic LEO orbits at different altitudes/inclinations
SATELLITES = [
    {
        "norad_id": 25544,
        "name": "ISS (ZARYA)",
        "object_type": "satellite",
        "a": RE + 420_000,      # 420 km altitude
        "e": 0.0002,
        "inc_deg": 51.6,
        "raan_deg": 30.0,
        "argp_deg": 0.0,
        "nu_deg": 0.0,
    },
    {
        "norad_id": 48274,
        "name": "STARLINK-2305",
        "object_type": "satellite",
        "a": RE + 550_000,      # 550 km altitude
        "e": 0.0001,
        "inc_deg": 53.0,
        "raan_deg": 120.0,
        "argp_deg": 10.0,
        "nu_deg": 45.0,
    },
    {
        "norad_id": 43013,
        "name": "NOAA-20",
        "object_type": "satellite",
        "a": RE + 830_000,      # 830 km altitude — sun-sync
        "e": 0.001,
        "inc_deg": 98.7,
        "raan_deg": 200.0,
        "argp_deg": 90.0,
        "nu_deg": 120.0,
    },
    {
        "norad_id": 36516,
        "name": "COSMOS 2251 DEB",
        "object_type": "satellite",
        "a": RE + 780_000,
        "e": 0.005,
        "inc_deg": 74.0,
        "raan_deg": 270.0,
        "argp_deg": 45.0,
        "nu_deg": 200.0,
    },
    {
        "norad_id": 39084,
        "name": "SENTINEL-1A",
        "object_type": "satellite",
        "a": RE + 693_000,
        "e": 0.0001,
        "inc_deg": 98.18,
        "raan_deg": 75.0,
        "argp_deg": 0.0,
        "nu_deg": 300.0,
    },
]


# ── debris that will create close approaches ─────────────────────────────
def make_conjunction_debris(
    sat_def: dict,
    debris_id: int,
    debris_name: str,
    encounter_time_sec: float,
    miss_offset_m: float = 500.0,
    raan_offset_deg: float = 0.0,
    nu_offset_deg: float = 0.0,
) -> dict:
    """
    Create a debris object in a similar orbit to *sat_def* but with slight
    offsets so that a close approach happens around *encounter_time_sec* into
    the simulation.  The orbital period determines how much true-anomaly to
    offset for the encounter timing.
    """
    a = sat_def["a"]
    period = 2 * math.pi * math.sqrt(a**3 / GM)

    # Shift true anomaly so debris arrives at ~encounter_time_sec
    nu_shift = (encounter_time_sec / period) * 360.0  # degrees of orbit covered
    # Small RAAN separation + anomaly offset → near-miss geometry
    return {
        "norad_id": debris_id,
        "name": debris_name,
        "object_type": "debris",
        "a": a + np.random.uniform(-2000, 2000),  # slight altitude diff
        "e": sat_def["e"] + np.random.uniform(0, 0.005),
        "inc_deg": sat_def["inc_deg"] + np.random.uniform(-0.5, 0.5),
        "raan_deg": sat_def["raan_deg"] + raan_offset_deg + np.random.uniform(-0.1, 0.1),
        "argp_deg": sat_def["argp_deg"] + np.random.uniform(-2, 2),
        "nu_deg": (sat_def["nu_deg"] + nu_offset_deg + np.random.uniform(-0.5, 0.5)) % 360,
        # link back to which satellite this targets
        "_target_sat": sat_def["norad_id"],
        "_encounter_time": encounter_time_sec,
        "_miss_offset_m": miss_offset_m,
    }


def build_debris_catalog(rng: np.random.Generator) -> List[dict]:
    """Generate 15-25 debris objects that create conjunction events throughout the week."""
    debris_list = []
    debris_id_start = 90001
    idx = 0

    for sat in SATELLITES:
        # 3-5 conjunction events per satellite over the week
        n_events = rng.integers(3, 6)
        for j in range(n_events):
            # Spread encounters throughout the week
            encounter_time = rng.uniform(3600, WEEK_SECONDS - 3600)
            miss_km = rng.choice([0.2, 0.5, 1.0, 2.0, 5.0, 8.0, 15.0])
            raan_off = rng.uniform(-0.3, 0.3)
            nu_off = rng.uniform(-1.0, 1.0)

            debris_list.append(make_conjunction_debris(
                sat,
                debris_id=debris_id_start + idx,
                debris_name=f"DEB-{debris_id_start + idx}",
                encounter_time_sec=encounter_time,
                miss_offset_m=miss_km * 1000,
                raan_offset_deg=raan_off,
                nu_offset_deg=nu_off,
            ))
            idx += 1

    return debris_list


# ── propagation ──────────────────────────────────────────────────────────
def propagate_orbit(
    r0: np.ndarray,
    v0: np.ndarray,
    dt: float,
    total_sec: float,
    solver: RK4Solver,
) -> Tuple[List[float], List[List[float]], List[List[float]]]:
    """
    Propagate an orbit and return (times, positions, velocities).
    Positions and velocities are lists of [x,y,z].
    """
    state = State(r0.copy(), v0.copy())
    n_steps = int(total_sec / dt)

    times = [0.0]
    positions = [state.r.tolist()]
    velocities = [state.v.tolist()]

    for i in range(1, n_steps + 1):
        state = solver.step(state, dt)
        t = i * dt
        times.append(t)
        positions.append(state.r.tolist())
        velocities.append(state.v.tolist())

    return times, positions, velocities


# ── conjunction detection ────────────────────────────────────────────────
def detect_conjunctions(
    sat_times: List[float],
    sat_positions: List[List[float]],
    sat_velocities: List[List[float]],
    sat_info: dict,
    deb_times: List[float],
    deb_positions: List[List[float]],
    deb_velocities: List[List[float]],
    deb_info: dict,
    threshold_m: float = 50_000,  # 50 km threshold for CDM
    epoch: datetime = datetime(2026, 2, 14, 0, 0, 0, tzinfo=timezone.utc),
) -> List[dict]:
    """Find all close approaches below threshold and generate CDM-like events."""
    events = []
    n = min(len(sat_positions), len(deb_positions))

    # Find local minima in distance
    distances = []
    for i in range(n):
        sp = np.array(sat_positions[i])
        dp = np.array(deb_positions[i])
        d = float(np.linalg.norm(sp - dp))
        distances.append(d)

    # Scan for local minima below threshold
    for i in range(1, n - 1):
        if distances[i] < threshold_m and distances[i] < distances[i - 1] and distances[i] < distances[i + 1]:
            t = sat_times[i]
            miss_m = distances[i]
            tca_epoch = epoch + timedelta(seconds=t)

            sv = np.array(sat_velocities[i])
            dv = np.array(deb_velocities[i])
            rel_vel = float(np.linalg.norm(sv - dv))

            # Simple probability estimate (conservative Gaussian)
            sigma = 500.0  # m positional uncertainty
            prob = float(np.exp(-(miss_m**2) / (2 * sigma**2)))
            prob = min(prob, 1.0)

            if miss_m < 1000:
                risk_level = "critical"
            elif miss_m < 5000:
                risk_level = "high"
            elif miss_m < 20000:
                risk_level = "medium"
            else:
                risk_level = "low"

            events.append({
                "event_id": str(uuid.uuid4())[:8],
                "primary_id": sat_info["norad_id"],
                "primary_name": sat_info["name"],
                "secondary_id": deb_info["norad_id"],
                "secondary_name": deb_info["name"],
                "tca_epoch": tca_epoch.isoformat(),
                "tca_offset_sec": t,
                "miss_distance_m": round(miss_m, 1),
                "relative_velocity_mps": round(rel_vel, 1),
                "probability": round(prob, 8),
                "risk_level": risk_level,
                "escalate": miss_m < 5000,
            })

    return events


# ── main ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate demo conjunction data")
    parser.add_argument("--days", type=int, default=7, help="Simulation duration (days)")
    parser.add_argument("--dt", type=int, default=60, help="Time step (seconds)")
    parser.add_argument("--out-dir", type=str, default="frontend/public", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    total_sec = args.days * 86400
    dt = args.dt
    epoch = datetime(2026, 2, 14, 0, 0, 0, tzinfo=timezone.utc)

    # Set up force model + solver (J2 for realistic precession)
    force = CompositeForce(NewtonianGravity(), J2Perturbation())
    solver = RK4Solver(force)

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        args.out_dir,
    )
    os.makedirs(out_dir, exist_ok=True)

    print(f"Generating {args.days}-day simulation  (dt={dt}s, seed={args.seed})")
    print(f"Output → {out_dir}/")

    # ── 1. Propagate satellites ──────────────────────────────────────────
    sat_data: List[Dict[str, Any]] = []
    sat_trajectories: Dict[int, dict] = {}  # norad_id → {times, positions, velocities}

    for sat_def in SATELLITES:
        r0, v0 = keplerian_to_eci(
            a=sat_def["a"],
            e=sat_def["e"],
            inc=math.radians(sat_def["inc_deg"]),
            raan=math.radians(sat_def["raan_deg"]),
            argp=math.radians(sat_def["argp_deg"]),
            nu=math.radians(sat_def["nu_deg"]),
        )
        print(f"  Propagating {sat_def['name']} (alt ~{(sat_def['a'] - RE)/1000:.0f} km) …")
        times, positions, velocities = propagate_orbit(r0, v0, dt, total_sec, solver)

        # Compute lat/lon/alt at each step
        llas = []
        for i, t in enumerate(times):
            ep = epoch + timedelta(seconds=t)
            lat, lon, alt_km = eci_to_lla(np.array(positions[i]), ep)
            llas.append({"lat": round(lat, 4), "lon": round(lon, 4), "alt_km": round(alt_km, 2)})

        sat_trajectories[sat_def["norad_id"]] = {
            "times": times,
            "positions": positions,
            "velocities": velocities,
        }

        sat_data.append({
            "norad_id": sat_def["norad_id"],
            "name": sat_def["name"],
            "object_type": sat_def["object_type"],
            "epoch": epoch.isoformat(),
            "trajectory": {
                "times": times,
                "positions": positions,
                "velocities": velocities,
                "lla": llas,
            },
        })

    # Write satellite file
    sat_file = os.path.join(out_dir, "demo_satellites.json")
    with open(sat_file, "w") as f:
        json.dump({
            "generated": datetime.now(timezone.utc).isoformat(),
            "epoch": epoch.isoformat(),
            "duration_sec": total_sec,
            "dt_sec": dt,
            "satellites": sat_data,
        }, f, separators=(",", ":"))  # compact JSON
    size_mb = os.path.getsize(sat_file) / 1e6
    print(f"  ✓ Wrote {sat_file} ({size_mb:.1f} MB)")

    # ── 2. Generate debris + conjunctions ────────────────────────────────
    debris_catalog = build_debris_catalog(rng)
    debris_data: List[Dict[str, Any]] = []
    all_conjunctions: List[dict] = []

    for deb_def in debris_catalog:
        r0, v0 = keplerian_to_eci(
            a=deb_def["a"],
            e=deb_def["e"],
            inc=math.radians(deb_def["inc_deg"]),
            raan=math.radians(deb_def["raan_deg"]),
            argp=math.radians(deb_def["argp_deg"]),
            nu=math.radians(deb_def["nu_deg"]),
        )
        print(f"  Propagating debris {deb_def['name']} …")
        times, positions, velocities = propagate_orbit(r0, v0, dt, total_sec, solver)

        # Compute LLA
        llas = []
        for i, t in enumerate(times):
            ep = epoch + timedelta(seconds=t)
            lat, lon, alt_km = eci_to_lla(np.array(positions[i]), ep)
            llas.append({"lat": round(lat, 4), "lon": round(lon, 4), "alt_km": round(alt_km, 2)})

        debris_data.append({
            "norad_id": deb_def["norad_id"],
            "name": deb_def["name"],
            "object_type": "debris",
            "epoch": epoch.isoformat(),
            "target_satellite": deb_def["_target_sat"],
            "trajectory": {
                "times": times,
                "positions": positions,
                "velocities": velocities,
                "lla": llas,
            },
        })

        # Check conjunctions against the target satellite
        target_id = deb_def["_target_sat"]
        if target_id in sat_trajectories:
            st = sat_trajectories[target_id]
            sat_info = next(s for s in SATELLITES if s["norad_id"] == target_id)
            events = detect_conjunctions(
                st["times"], st["positions"], st["velocities"], sat_info,
                times, positions, velocities, deb_def,
                threshold_m=50_000,
                epoch=epoch,
            )
            all_conjunctions.extend(events)

    # Sort conjunctions by time
    all_conjunctions.sort(key=lambda e: e["tca_offset_sec"])

    # Write debris + conjunctions file
    conj_file = os.path.join(out_dir, "demo_conjunctions.json")
    with open(conj_file, "w") as f:
        json.dump({
            "generated": datetime.now(timezone.utc).isoformat(),
            "epoch": epoch.isoformat(),
            "duration_sec": total_sec,
            "dt_sec": dt,
            "debris": debris_data,
            "conjunction_events": all_conjunctions,
        }, f, separators=(",", ":"))
    size_mb = os.path.getsize(conj_file) / 1e6
    print(f"  ✓ Wrote {conj_file} ({size_mb:.1f} MB)")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Satellites:    {len(SATELLITES)}")
    print(f"  Debris:        {len(debris_catalog)}")
    print(f"  Conjunctions:  {len(all_conjunctions)}")
    risk_counts = {}
    for e in all_conjunctions:
        risk_counts[e["risk_level"]] = risk_counts.get(e["risk_level"], 0) + 1
    for level in ["critical", "high", "medium", "low"]:
        if level in risk_counts:
            print(f"    {level:>10s}: {risk_counts[level]}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

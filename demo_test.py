#!/usr/bin/env python3
"""
DETOUR-Plus Demo Script
Run this to demonstrate the multi-maneuver optimization system.
"""
import math
import numpy as np

def demo_multi_impulse():
    """Demo 1: Multi-Impulse Optimizer"""
    print("=" * 60)
    print("DEMO 1: Multi-Impulse Trajectory Optimizer")
    print("=" * 60)

    from engine.maneuver.multi_impulse import plan_multi_maneuver_avoidance
    from engine.config.settings import RE

    # ISS-like orbit
    alt_km = 420
    r = RE + alt_km * 1000
    v_circ = math.sqrt(3.986e14 / r)

    sat_pos = [r, 0, 0]
    sat_vel = [0, v_circ * math.cos(math.radians(51.6)), v_circ * math.sin(math.radians(51.6))]

    print(f"\nSatellite: ISS (ZARYA)")
    print(f"  Altitude: {alt_km} km")
    print(f"  Velocity: {v_circ:.1f} m/s")

    # Three conjunction threats
    conjunctions = [
        {
            "debris_id": 90001,
            "debris_name": "COSMOS 2251 DEB",
            "debris_pos": [r + 500, 1000, 200],
            "debris_vel": [100, v_circ * 0.99, 50],
            "tca_sec": 7200,  # 2 hours
            "miss_distance_m": 350,
            "collision_prob": 0.005,
        },
        {
            "debris_id": 90002,
            "debris_name": "FENGYUN 1C DEB",
            "debris_pos": [r - 300, 2000, -100],
            "debris_vel": [-80, v_circ * 1.01, -30],
            "tca_sec": 14400,  # 4 hours
            "miss_distance_m": 800,
            "collision_prob": 0.002,
        },
        {
            "debris_id": 90003,
            "debris_name": "IRIDIUM 33 DEB",
            "debris_pos": [r + 200, -1500, 500],
            "debris_vel": [50, v_circ * 0.98, 80],
            "tca_sec": 28800,  # 8 hours
            "miss_distance_m": 2500,
            "collision_prob": 0.0005,
        },
    ]

    print(f"\n{len(conjunctions)} Conjunction Threats Detected:")
    print("-" * 50)
    for i, c in enumerate(conjunctions, 1):
        print(f"  [{i}] {c['debris_name']}")
        print(f"      TCA: {c['tca_sec']/3600:.1f}h, Miss: {c['miss_distance_m']}m")

    print(f"\nPlanning optimal maneuver sequence...")
    print(f"  Fuel Budget: 10.0 kg")
    print(f"  Target Miss Distance: 1.0 km")

    result = plan_multi_maneuver_avoidance(
        sat_pos=sat_pos,
        sat_vel=sat_vel,
        conjunctions=conjunctions,
        fuel_available_kg=10.0,
        config={"target_miss_km": 1.0}
    )

    print("\n" + "=" * 60)
    print("OPTIMIZATION RESULT")
    print("=" * 60)

    if result.get("feasible", False) or result.get("num_maneuvers", 0) > 0:
        print(f"\n✓ Solution Found!")
        print(f"  Total Maneuvers: {result.get('num_maneuvers', 0)}")
        print(f"  Total Fuel: {result.get('total_fuel_kg', 0):.2f} kg")
        print(f"  Total Delta-V: {result.get('total_delta_v_ms', 0):.2f} m/s")
        print(f"  Fuel Remaining: {result.get('fuel_remaining_kg', 0):.2f} kg")
        print(f"  Feasible: {'Yes' if result.get('feasible') else 'No'}")

        maneuvers = result.get("maneuvers", [])
        if maneuvers:
            print("\nManeuver Sequence:")
            print("-" * 50)
            for i, m in enumerate(maneuvers, 1):
                print(f"  Burn #{i}:")
                print(f"    Time: T-{m['burn_time_sec']/3600:.1f}h before TCA")
                print(f"    Delta-V: {m['delta_v_magnitude_ms']:.3f} m/s")
                print(f"    Fuel: {m['fuel_kg']:.3f} kg")
                dv = m.get('delta_v', [0,0,0])
                print(f"    Direction: [{dv[0]:.2f}, {dv[1]:.2f}, {dv[2]:.2f}] m/s")

        # Show post-miss distances
        post_miss = result.get("post_miss_distances", {})
        if post_miss:
            print("\nPost-Maneuver Miss Distances:")
            print("-" * 50)
            for debris_id, miss in post_miss.items():
                status = "SAFE" if miss > 1000 else "CLOSE"
                print(f"  Debris {debris_id}: {miss:.0f}m [{status}]")
    else:
        print(f"\n[!] No maneuvers planned (threats may already be safe)")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  Warning: {w}")

    return result


def demo_harmonic_analysis():
    """Demo 2: Orbital Harmonic Analysis"""
    print("\n" + "=" * 60)
    print("DEMO 2: Orbital Resonance Detection")
    print("=" * 60)

    from engine.maneuver.harmonic_analysis import detect_orbital_resonance, OrbitalElements
    import math

    # ISS orbit
    iss = OrbitalElements(
        semi_major_axis_m=6.798e6,
        eccentricity=0.0002,
        inclination_rad=math.radians(51.6),
        raan_rad=0,
        arg_perigee_rad=0,
        true_anomaly_rad=0
    )

    print(f"\nISS Orbital Period: {iss.period_sec/60:.1f} minutes")

    # Test different resonance scenarios
    scenarios = [
        ("Co-orbital (1:1)", 6.798e6),      # Same altitude = dangerous!
        ("2:1 Resonance", 6.798e6 * 1.587), # 2:1 period ratio
        ("Non-resonant", 7.2e6),            # Different orbit
    ]

    print("\nResonance Analysis:")
    print("-" * 50)

    for name, sma in scenarios:
        debris = OrbitalElements(
            semi_major_axis_m=sma,
            eccentricity=0.001,
            inclination_rad=math.radians(51.5),
            raan_rad=0.1,
            arg_perigee_rad=0,
            true_anomaly_rad=0.05
        )

        result = detect_orbital_resonance(iss, debris)

        status = "⚠️ " if result.warning_level in ["high", "medium"] else "✓ "
        print(f"\n  {status}{name}:")
        print(f"     Debris Period: {debris.period_sec/60:.1f} min")
        print(f"     Resonant: {result.is_resonant}")
        if result.resonance_ratio:
            print(f"     Ratio: {result.resonance_ratio[0]}:{result.resonance_ratio[1]}")
        print(f"     Warning: {result.warning_level.upper()}")
        print(f"     {result.description}")


def demo_agent_pipeline():
    """Demo 3: Full Agent Pipeline (requires API key)"""
    print("\n" + "=" * 60)
    print("DEMO 3: Multi-Agent Pipeline")
    print("=" * 60)
    print("\nTo run the full agent pipeline, use:")
    print("  python -m agents.run --demo \"Scan for threats to ISS\"")
    print("\nFor strategic mode with multi-maneuver planning:")
    print("  python -m agents.run --mode strategic --demo \"Plan multi-maneuver avoidance\"")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("    DETOUR-Plus: Multi-Maneuver Collision Avoidance")
    print("    Author: Yang Zhi (杨植) - Beijing Institute of Technology")
    print("=" * 60)

    # Run demos
    demo_multi_impulse()
    demo_harmonic_analysis()
    demo_agent_pipeline()

    print("\n" + "=" * 60)
    print("Demo completed!")
    print("=" * 60 + "\n")

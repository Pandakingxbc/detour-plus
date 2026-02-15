import * as THREE from "three"
import { geodeticToUnitVector } from "@/lib/geo"
import type { TrajectoryPoint } from "@/lib/simulation-types"

// --- Geodetic helpers ---

export function geoToVec3(lat: number, lon: number, altKm: number): THREE.Vector3 {
  const p = geodeticToUnitVector(lat, lon, altKm)
  return new THREE.Vector3(p.x, p.y, p.z)
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function lerpPoint(
  a: TrajectoryPoint,
  b: TrajectoryPoint,
  fraction: number
): THREE.Vector3 {
  const lat = lerp(a.lat, b.lat, fraction)
  const lon = lerp(a.lon, b.lon, fraction)
  const alt = lerp(a.alt_km, b.alt_km, fraction)
  return geoToVec3(lat, lon, alt)
}

export function getPositionAtTime(
  trajectory: TrajectoryPoint[],
  simTime: number
): THREE.Vector3 | null {
  if (trajectory.length === 0) return null
  if (simTime <= trajectory[0].t)
    return geoToVec3(trajectory[0].lat, trajectory[0].lon, trajectory[0].alt_km)
  if (simTime >= trajectory[trajectory.length - 1].t)
    return geoToVec3(
      trajectory[trajectory.length - 1].lat,
      trajectory[trajectory.length - 1].lon,
      trajectory[trajectory.length - 1].alt_km
    )

  let lo = 0
  let hi = trajectory.length - 1
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1
    if (trajectory[mid].t <= simTime) lo = mid
    else hi = mid
  }

  const fraction = (simTime - trajectory[lo].t) / (trajectory[hi].t - trajectory[lo].t)
  return lerpPoint(trajectory[lo], trajectory[hi], fraction)
}

// --- Nearest distance interpolation ---

export function getNearestKmAtTime(
  trajectory: TrajectoryPoint[],
  simTime: number
): number | null {
  if (trajectory.length === 0) return null
  if (simTime <= trajectory[0].t) return trajectory[0].nearest_km ?? null
  if (simTime >= trajectory[trajectory.length - 1].t)
    return trajectory[trajectory.length - 1].nearest_km ?? null

  let lo = 0
  let hi = trajectory.length - 1
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1
    if (trajectory[mid].t <= simTime) lo = mid
    else hi = mid
  }

  const a = trajectory[lo].nearest_km
  const b = trajectory[hi].nearest_km
  if (a == null || b == null) return a ?? b ?? null

  const fraction = (simTime - trajectory[lo].t) / (trajectory[hi].t - trajectory[lo].t)
  return a + (b - a) * fraction
}

// --- Formatting ---

export function formatDistance(km: number): string {
  if (km < 0.001) return `${(km * 1_000_000).toFixed(0)} m`
  if (km < 1) return `${(km * 1000).toFixed(0)} m`
  if (km < 100) return `${km.toFixed(1)} km`
  return `${km.toFixed(0)} km`
}

export function formatCountdown(seconds: number): string {
  const abs = Math.abs(seconds)
  const sign = seconds < 0 ? "T-" : "T+"
  const h = Math.floor(abs / 3600)
  const m = Math.floor((abs % 3600) / 60)
  const s = Math.floor(abs % 60)
  if (h > 0) return `${sign}${h}h ${m.toString().padStart(2, "0")}m`
  if (m > 0) return `${sign}${m}m ${s.toString().padStart(2, "0")}s`
  return `${sign}${s}s`
}

export function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
}

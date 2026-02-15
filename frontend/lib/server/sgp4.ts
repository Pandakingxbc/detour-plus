import * as satellite from "satellite.js"

import type { PropagatedPoint, TleObject } from "@/lib/server/types"

interface EciPosition {
  x: number
  y: number
  z: number
}

interface PropagatedState {
  eci: EciPosition
  lat: number
  lon: number
  altKm: number
}

export function satrecFromTle(tle: TleObject) {
  return satellite.twoline2satrec(tle.line1, tle.line2)
}

function propagateSatrec(satrec: satellite.SatRec, when: Date): PropagatedState | null {
  const propagated = satellite.propagate(satrec, when)
  if (!propagated || !propagated.position) return null
  const position = propagated.position

  if (![position.x, position.y, position.z].every(Number.isFinite)) {
    return null
  }

  const gmst = satellite.gstime(when)
  const geo = satellite.eciToGeodetic(position, gmst)

  const lat = satellite.degreesLat(geo.latitude)
  const lon = satellite.degreesLong(geo.longitude)

  if (![lat, lon, geo.height].every(Number.isFinite)) return null

  return {
    eci: {
      x: position.x,
      y: position.y,
      z: position.z,
    },
    lat,
    lon,
    altKm: geo.height,
  }
}

export function propagateAt(tle: TleObject, when: Date): PropagatedPoint | null {
  const satrec = satrecFromTle(tle)
  const state = propagateSatrec(satrec, when)
  if (!state) return null

  return {
    tUtc: when.toISOString(),
    x: state.eci.x,
    y: state.eci.y,
    z: state.eci.z,
    lat: state.lat,
    lon: state.lon,
    altKm: state.altKm,
  }
}

export function propagateRange(tle: TleObject, minutes: number, stepSec: number, start = new Date()): PropagatedPoint[] {
  const satrec = satrecFromTle(tle)
  const points: PropagatedPoint[] = []

  const startMs = start.getTime()
  const durationSec = Math.max(60, Math.round(minutes * 60))
  const step = Math.max(10, Math.round(stepSec))

  for (let offsetSec = 0; offsetSec <= durationSec; offsetSec += step) {
    const when = new Date(startMs + offsetSec * 1000)
    const state = propagateSatrec(satrec, when)
    if (!state) continue

    points.push({
      tUtc: when.toISOString(),
      x: state.eci.x,
      y: state.eci.y,
      z: state.eci.z,
      lat: state.lat,
      lon: state.lon,
      altKm: state.altKm,
    })
  }

  return points
}

export function estimateInclinationDeg(tle: TleObject): number | null {
  const satrec = satrecFromTle(tle)
  const inclo = satrec.inclo
  if (!Number.isFinite(inclo)) return null
  return (inclo * 180) / Math.PI
}

export function orbitClassForAltitude(altKm: number): "LEO" | "MEO" | "GEO" {
  if (!Number.isFinite(altKm)) return "LEO"
  if (altKm < 2000) return "LEO"
  if (altKm < 35786) return "MEO"
  return "GEO"
}

export function distanceKm(a: EciPosition, b: EciPosition): number {
  const dx = a.x - b.x
  const dy = a.y - b.y
  const dz = a.z - b.z
  return Math.sqrt(dx * dx + dy * dy + dz * dz)
}

export function propagateStateAt(satrec: satellite.SatRec, when: Date): PropagatedState | null {
  return propagateSatrec(satrec, when)
}

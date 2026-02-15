export interface TleObject {
  noradId: number
  name: string
  line1: string
  line2: string
}

export interface TleCacheEntry {
  fetchedAtUtc: string
  fetchedAtMs: number
  rawText: string
  objects: TleObject[]
  source: string
}

export interface ConstraintsState {
  maxTotalDeltaV: number
  maxBurns: 1 | 2
  preferredAxis: "along" | "radial" | "cross"
  horizonHours: number
  updatedAtUtc: string
}

export interface PropagatedPoint {
  tUtc: string
  x: number
  y: number
  z: number
  lat: number
  lon: number
  altKm: number
}

export type RiskLabel = "LOW" | "MED" | "HIGH"

export interface ConjunctionEvent {
  eventId: string
  tcaUtc: string
  tcaInMinutes: number
  missKm: number
  risk: RiskLabel
  secondaryNorad: number
}

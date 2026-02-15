export interface TrajectoryPoint {
  t: number
  lat: number
  lon: number
  alt_km: number
  nearest_km?: number
}

export interface ScenarioData {
  scenario_id: string
  label: string
  duration_sec: number
  collision_t: number
  collision_lat: number
  collision_lon: number
  collision_alt_km: number
  satellite: TrajectoryPoint[]
}

// --- Real-time simulation types ---

export type CardinalDirection = "N" | "S" | "E" | "W" | "NE" | "NW" | "SE" | "SW" | "HOLD"

export interface DebrisParticle {
  id: number
  lat: number
  lon: number
  altKm: number
  vLat: number // degrees per tick
  vLon: number // degrees per tick
}

export interface MoveRecord {
  tick: number
  direction: CardinalDirection
  fromLat: number
  fromLon: number
  toLat: number
  toLon: number
}

export interface SimConfig {
  ticksPerSecond: number
  moveIntervalTicks: number
  maxTicks: number
  startLat: number
  startLon: number
  startAltKm: number
  moveStepDeg: number
  debrisCount: number
  collisionThreshold: number // scene-unit distance for collision
  seed: number
}

export interface SimState {
  satLat: number
  satLon: number
  satAltKm: number
  debris: DebrisParticle[]
  moveHistory: MoveRecord[]
  dangerTargetId: number | null
  dangerDistance: number | null
  collided: boolean
  collisionTick: number | null
  tickCount: number
  lastDirection: CardinalDirection
  finished: boolean
}

export type MoveDecider = (state: Readonly<SimState>) => CardinalDirection

import { geodeticToUnitVector, EARTH_RADIUS_KM } from "@/lib/geo"
import type {
  CardinalDirection,
  DebrisParticle,
  MoveDecider,
  MoveRecord,
  SimConfig,
  SimState,
} from "@/lib/simulation-types"

// --- Seeded PRNG ---
interface SeededRng {
  (): number
}

function mulberry32(seed: number): SeededRng {
  let s = seed | 0
  return () => {
    s = (s + 0x6d2b79f5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// --- Defaults ---
export const DEFAULT_SIM_CONFIG: SimConfig = {
  ticksPerSecond: 30,
  moveIntervalTicks: 15,
  maxTicks: 300, // 10s demo
  startLat: 10,
  startLon: -60,
  startAltKm: 400,
  moveStepDeg: 0.2,
  debrisCount: 0,
  collisionThreshold: 0.035,
  seed: 0, // 0 = random seed each run
}

// Straight-line satellite motion (no maneuvers).
const SAT_V_LAT_DEG_PER_TICK = 0.004
const SAT_V_LON_DEG_PER_TICK = 0.032
const GUARANTEED_COLLISION_TICK = 300 // ~10 seconds at 30 tps
const MIN_AMBIENT_DEBRIS = 1200
const MAX_AMBIENT_DEBRIS = 2400

function wrapLon(lon: number): number {
  let value = lon
  while (value > 180) value -= 360
  while (value < -180) value += 360
  return value
}

function clampLat(lat: number): number {
  return Math.max(-85, Math.min(85, lat))
}

function sceneDistance3D(
  lat1: number, lon1: number, alt1: number,
  lat2: number, lon2: number, alt2: number
): number {
  const p1 = geodeticToUnitVector(lat1, lon1, alt1)
  const p2 = geodeticToUnitVector(lat2, lon2, alt2)
  const dx = p1.x - p2.x
  const dy = p1.y - p2.y
  const dz = p1.z - p2.z
  return Math.sqrt(dx * dx + dy * dy + dz * dz)
}

function ambientDebrisVelocity(rng: SeededRng): { vLat: number; vLon: number } {
  // Linear orbital drift with varied heading/speed so debris doesn't look synchronized.
  // Keep deterministic and physically plausible (constant angular rates).
  const alongSign = rng() < 0.68 ? 1 : -1
  const alongScale = 0.45 + rng() * 1.25
  const crossSign = rng() < 0.5 ? 1 : -1
  const crossScale = 0.1 + rng() * 1.2

  return {
    vLat: SAT_V_LAT_DEG_PER_TICK * crossSign * crossScale, // mixed north/south drift
    vLon: SAT_V_LON_DEG_PER_TICK * alongSign * alongScale, // mixed prograde/retrograde
  }
}

// No-maneuver baseline behavior for this demo mode.
export function naiveDecider(): CardinalDirection {
  return "HOLD"
}

export interface InitialDebrisPos {
  lat: number
  lon: number
  altKm: number
}

export class SimEngine {
  state: SimState
  config: SimConfig
  decider: MoveDecider
  private rng: SeededRng
  private initialDebris: InitialDebrisPos[] = []
  private guaranteedDebrisId: number | null = null
  private showcaseDebrisId: number | null = null

  constructor(config: SimConfig = DEFAULT_SIM_CONFIG, decider: MoveDecider = naiveDecider) {
    this.config = config
    this.decider = decider
    this.rng = mulberry32(config.seed)
    this.state = this.createInitialState()
  }

  private createInitialState(): SimState {
    return {
      satLat: this.config.startLat,
      satLon: this.config.startLon,
      satAltKm: this.config.startAltKm,
      debris: [],
      moveHistory: [],
      dangerTargetId: -1,
      dangerDistance: null,
      collided: false,
      collisionTick: null,
      tickCount: 0,
      lastDirection: "HOLD",
      finished: false,
    }
  }

  private predictSatellitePositionAtTick(tick: number): { lat: number; lon: number } {
    return {
      lat: clampLat(this.config.startLat + SAT_V_LAT_DEG_PER_TICK * tick),
      lon: wrapLon(this.config.startLon + SAT_V_LON_DEG_PER_TICK * tick),
    }
  }

  private minDistanceToEarlyPath(
    lat: number,
    lon: number,
    altKm: number,
    vLat = 0,
    vLon = 0
  ): number {
    let minDist = Number.POSITIVE_INFINITY

    // Keep full pre-impact corridor clear so the guaranteed hit occurs near 10s.
    for (let tick = 0; tick < GUARANTEED_COLLISION_TICK; tick += 1) {
      const sat = this.predictSatellitePositionAtTick(tick)
      const debrisLat = clampLat(lat + vLat * tick)
      const debrisLon = wrapLon(lon + vLon * tick)
      const dist = sceneDistance3D(sat.lat, sat.lon, this.config.startAltKm, debrisLat, debrisLon, altKm)
      if (dist < minDist) minDist = dist
    }

    return minDist
  }

  private initDebrisFromPositions(positions: InitialDebrisPos[]): void {
    const debris: DebrisParticle[] = []

    // Ambient debris: keep only objects that are not on the immediate path.
    for (let i = 0; i < positions.length; i += 1) {
      const p = positions[i]
      if (![p.lat, p.lon, p.altKm].every(Number.isFinite)) continue
      if (Math.abs(p.lat) > 90 || Math.abs(p.lon) > 360) continue

      const velocity = ambientDebrisVelocity(this.rng)
      const nearPath = this.minDistanceToEarlyPath(p.lat, p.lon, p.altKm, velocity.vLat, velocity.vLon)
      if (nearPath < this.config.collisionThreshold * 4) continue

      debris.push({
        id: debris.length,
        lat: p.lat,
        lon: wrapLon(p.lon),
        altKm: p.altKm,
        vLat: velocity.vLat,
        vLon: velocity.vLon,
      })

      // Keep count reasonable for frame rate.
      if (debris.length >= MAX_AMBIENT_DEBRIS) break
    }

    // If live sample is sparse, add synthetic ambient debris so space doesn't look empty.
    while (debris.length < MIN_AMBIENT_DEBRIS) {
      const lat = clampLat(-70 + this.rng() * 140)
      const lon = wrapLon(-180 + this.rng() * 360)
      const altKm = this.config.startAltKm + (this.rng() - 0.5) * 220
      const velocity = ambientDebrisVelocity(this.rng)
      const nearPath = this.minDistanceToEarlyPath(lat, lon, altKm, velocity.vLat, velocity.vLon)
      if (nearPath < this.config.collisionThreshold * 4) continue

      debris.push({
        id: debris.length,
        lat,
        lon,
        altKm,
        vLat: velocity.vLat,
        vLon: velocity.vLon,
      })
    }

    // Showcase debris for the danger arrow: starts above satellite, drifts left.
    const satStart = this.predictSatellitePositionAtTick(0)
    this.showcaseDebrisId = debris.length
    debris.push({
      id: this.showcaseDebrisId,
      lat: clampLat(satStart.lat + 4.5),
      lon: wrapLon(satStart.lon),
      altKm: this.config.startAltKm + 60,
      vLat: 0,
      vLon: -SAT_V_LON_DEG_PER_TICK * 0.35,
    })

    // Guaranteed collision debris: counter-orbiting (opposite along-track direction)
    // and linearly intersecting the satellite near 10 seconds.
    const hit = this.predictSatellitePositionAtTick(GUARANTEED_COLLISION_TICK)
    const guaranteedVLat = SAT_V_LAT_DEG_PER_TICK // same plane drift for clean intercept
    const guaranteedVLon = -SAT_V_LON_DEG_PER_TICK * 0.95 // opposite orbital direction
    const guaranteedStartLat = clampLat(hit.lat - guaranteedVLat * GUARANTEED_COLLISION_TICK)
    const guaranteedStartLon = wrapLon(hit.lon - guaranteedVLon * GUARANTEED_COLLISION_TICK)
    this.guaranteedDebrisId = debris.length
    debris.push({
      id: this.guaranteedDebrisId,
      lat: guaranteedStartLat,
      lon: guaranteedStartLon,
      altKm: this.config.startAltKm,
      vLat: guaranteedVLat,
      vLon: guaranteedVLon,
    })

    this.state.debris = debris
    this.config.debrisCount = debris.length
  }

  init(debrisPositions?: InitialDebrisPos[]): void {
    const seed = this.config.seed || ((Math.random() * 0xffffffff) >>> 0)
    this.rng = mulberry32(seed)
    this.state = this.createInitialState()
    this.initialDebris = debrisPositions ?? []
    this.guaranteedDebrisId = null
    this.showcaseDebrisId = null
    this.initDebrisFromPositions(this.initialDebris)
  }

  tick(): void {
    if (this.state.finished || this.state.collided) return

    const s = this.state
    const nextTick = s.tickCount + 1

    // 1) Straight-line satellite propagation (no maneuvers).
    const sat = this.predictSatellitePositionAtTick(nextTick)
    s.satLat = sat.lat
    s.satLon = sat.lon
    s.satAltKm = this.config.startAltKm
    s.lastDirection = "HOLD"

    // 2) Debris drift: deterministic linear motion (no stochastic jitter).
    for (const d of s.debris) {
      d.lat = clampLat(d.lat + d.vLat)
      d.lon = wrapLon(d.lon + d.vLon)
    }

    // 3) Nearest threat + collision check.
    let nearestDist = Number.POSITIVE_INFINITY
    let nearestId = -1

    for (const d of s.debris) {
      const dist = sceneDistance3D(s.satLat, s.satLon, s.satAltKm, d.lat, d.lon, d.altKm)
      if (dist < nearestDist) {
        nearestDist = dist
        nearestId = d.id
      }
    }

    s.dangerTargetId = nearestId
    s.dangerDistance = Number.isFinite(nearestDist) ? nearestDist : null

    // Do not allow early collision events before the 10s target.
    if (nextTick >= GUARANTEED_COLLISION_TICK && nearestDist < this.config.collisionThreshold) {
      s.collided = true
      s.collisionTick = nextTick
    }

    s.tickCount = nextTick
    if (s.tickCount >= this.config.maxTicks) {
      s.finished = true
    }
  }

  reset(): void {
    this.init(this.initialDebris)
  }

  getSatelliteVec3(): { x: number; y: number; z: number } {
    return geodeticToUnitVector(this.state.satLat, this.state.satLon, this.state.satAltKm)
  }

  getDebrisVec3(index: number): { x: number; y: number; z: number } {
    const d = this.state.debris[index]
    return geodeticToUnitVector(d.lat, d.lon, d.altKm)
  }

  getDangerTargetVec3(): { x: number; y: number; z: number } | null {
    const id = this.state.dangerTargetId
    if (id === null || id < 0) return null
    const d = this.state.debris[id]
    if (!d) return null
    return geodeticToUnitVector(d.lat, d.lon, d.altKm)
  }

  getMoveVec3(record: MoveRecord): { x: number; y: number; z: number } {
    return geodeticToUnitVector(record.toLat, record.toLon, this.state.satAltKm)
  }

  getNearestDistKm(): number | null {
    if (this.state.dangerDistance === null) return null
    return this.state.dangerDistance * EARTH_RADIUS_KM
  }

  getElapsedSec(): number {
    return this.state.tickCount / this.config.ticksPerSecond
  }
}

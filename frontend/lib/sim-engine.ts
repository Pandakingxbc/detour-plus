import { geodeticToUnitVector, EARTH_RADIUS_KM } from "@/lib/geo"
import type {
  CardinalDirection,
  DebrisParticle,
  MoveDecider,
  MoveRecord,
  SimConfig,
  SimState,
} from "@/lib/simulation-types"

// --- Seeded PRNG (deterministic demo) ---
function mulberry32(seed: number) {
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
  moveIntervalTicks: 15, // satellite decides every 0.5s
  maxTicks: 3600, // 120s demo at 30 tps
  startLat: 10,
  startLon: -60,
  startAltKm: 400,
  moveStepDeg: 0.2, // micro-adjustment size
  debrisCount: 0, // set from API data
  collisionThreshold: 0.055, // slightly generous — triggers before visual overlap looks wrong
  seed: 42,
}

// Satellite orbital parameters
const ORBIT_SPEED_DEG_PER_TICK = 0.09 // longitude degrees per tick (~2.7 deg/s → visible orbit)
const ORBIT_INCLINATION_DEG = 51.6 // ISS-like inclination
const ORBIT_INCLINATION_PERIOD_TICKS = 800 // one lat oscillation cycle

// Cardinal direction deltas (lat, lon) in degrees
const DIRECTION_DELTAS: Record<CardinalDirection, [number, number]> = {
  N: [1, 0],
  S: [-1, 0],
  E: [0, 1],
  W: [0, -1],
  NE: [0.707, 0.707],
  NW: [0.707, -0.707],
  SE: [-0.707, 0.707],
  SW: [-0.707, -0.707],
  HOLD: [0, 0],
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

// --- Naive decider: greedy dodge away from nearest debris ---
// Reacts only to the single closest threat — can't plan ahead through a stochastic field.
export function naiveDecider(state: Readonly<SimState>): CardinalDirection {
  let nearestDist = Infinity
  let nearestIdx = -1
  let secondDist = Infinity

  for (let i = 0; i < state.debris.length; i++) {
    const d = state.debris[i]
    const dist = sceneDistance3D(
      state.satLat, state.satLon, state.satAltKm,
      d.lat, d.lon, d.altKm
    )
    if (dist < nearestDist) {
      secondDist = nearestDist
      nearestDist = dist
      nearestIdx = i
    } else if (dist < secondDist) {
      secondDist = dist
    }
  }

  // React when debris is within ~5x collision range — visible dodging window
  if (nearestIdx === -1 || nearestDist > 0.20) return "HOLD"

  const nearest = state.debris[nearestIdx]
  const dLat = state.satLat - nearest.lat
  let dLon = state.satLon - nearest.lon
  if (dLon > 180) dLon -= 360
  if (dLon < -180) dLon += 360

  const absLat = Math.abs(dLat)
  const absLon = Math.abs(dLon)

  if (absLat > absLon * 1.5) {
    return dLat > 0 ? "N" : "S"
  } else if (absLon > absLat * 1.5) {
    return dLon > 0 ? "E" : "W"
  } else {
    if (dLat > 0 && dLon > 0) return "NE"
    if (dLat > 0 && dLon < 0) return "NW"
    if (dLat < 0 && dLon > 0) return "SE"
    return "SW"
  }
}

// --- Initial debris position from API ---
export interface InitialDebrisPos {
  lat: number
  lon: number
  altKm: number
}

// --- SimEngine class ---
export class SimEngine {
  state: SimState
  config: SimConfig
  decider: MoveDecider
  private rng: () => number
  private initialDebris: InitialDebrisPos[] = []
  // Base orbital position (before micro-adjustments)
  private baseLat = 0
  private baseLon = 0
  // Accumulated micro-adjustment offset
  private adjustLat = 0
  private adjustLon = 0

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

  /** Initialize with real debris positions from API */
  init(debrisPositions?: InitialDebrisPos[]): void {
    this.rng = mulberry32(this.config.seed)
    this.state = this.createInitialState()
    this.baseLat = this.config.startLat
    this.baseLon = this.config.startLon
    this.adjustLat = 0
    this.adjustLon = 0

    if (debrisPositions && debrisPositions.length > 0) {
      this.initialDebris = debrisPositions
      this.initDebrisFromPositions(debrisPositions)
    }
  }

  private initDebrisFromPositions(positions: InitialDebrisPos[]): void {
    const rng = this.rng
    const debris: DebrisParticle[] = []

    // All real debris — visible stochastic orbital drift
    // Filter out debris that starts too close to the satellite's initial path
    // to guarantee a clean first ~20s for demo purposes
    for (let i = 0; i < positions.length; i++) {
      const p = positions[i]

      // Skip debris that's within the satellite's near-term corridor
      const dLat = Math.abs(p.lat - this.config.startLat)
      let dLon = Math.abs(p.lon - this.config.startLon)
      if (dLon > 180) dLon = 360 - dLon
      // Clear a generous corridor: ±8° lat, 60° lon ahead (covers ~20s of orbit)
      const lonAhead = p.lon - this.config.startLon
      if (dLat < 8 && dLon < 60 && lonAhead > -5) {
        // Push this debris further away — offset its longitude well ahead
        p.lon = ((p.lon + 70 + 180) % 360) - 180
      }

      const baseOrbitalVLon = 0.004 + rng() * 0.008 // visible eastward drift
      const vLatWobble = (rng() - 0.5) * 0.004 // noticeable latitude wobble

      debris.push({
        id: i,
        lat: p.lat,
        lon: p.lon,
        altKm: p.altKm,
        vLat: vLatWobble,
        vLon: baseOrbitalVLon * (rng() > 0.3 ? 1 : -1),
      })
    }

    // Seed hazard debris scattered along the satellite's upcoming orbital path.
    // These aren't "aimed" — they sit at random offsets in the corridor with their
    // own stochastic drift, creating natural near-misses and eventual collision.
    // Split into two waves: near-misses (dodge practice) and the kill shot.
    const baseId = debris.length

    // Wave 1: ~5 near-miss debris at 25–35s — satellite dodges these visibly
    // Pushed further out so the first ~20s are clean for demo
    for (let i = 0; i < 5; i++) {
      const futureTickOffset = 750 + rng() * 300 // 25–35s at 30 tps
      const futureLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * futureTickOffset
      const futureLat = this.config.startLat +
        ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * futureTickOffset) / ORBIT_INCLINATION_PERIOD_TICKS)

      // Wider offset — close enough to trigger dodging but not guaranteed hit
      const latOffset = (rng() - 0.5) * 12
      const lonOffset = (rng() - 0.5) * 14

      debris.push({
        id: baseId + i,
        lat: Math.max(-85, Math.min(85, futureLat + latOffset)),
        lon: ((futureLon + lonOffset + 180) % 360) - 180,
        altKm: 380 + rng() * 40,
        vLat: (rng() - 0.5) * 0.005,
        vLon: (rng() - 0.5) * 0.008,
      })
    }

    // Wave 2: ~6 tighter debris at 40–55s — the closing net that gets the satellite
    for (let i = 0; i < 6; i++) {
      const futureTickOffset = 1200 + rng() * 450 // 40–55s at 30 tps
      const futureLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * futureTickOffset
      const futureLat = this.config.startLat +
        ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * futureTickOffset) / ORBIT_INCLINATION_PERIOD_TICKS)

      // Tighter offset — closer to the orbital path
      const latOffset = (rng() - 0.5) * 6
      const lonOffset = (rng() - 0.5) * 7

      debris.push({
        id: baseId + 5 + i,
        lat: Math.max(-85, Math.min(85, futureLat + latOffset)),
        lon: ((futureLon + lonOffset + 180) % 360) - 180,
        altKm: 390 + rng() * 20, // tighter altitude band
        vLat: (rng() - 0.5) * 0.004,
        vLon: (rng() - 0.5) * 0.006,
      })
    }

    this.state.debris = debris
    this.config.debrisCount = debris.length
  }

  tick(): void {
    if (this.state.finished || this.state.collided) return

    const s = this.state
    const rng = this.rng

    // 1. Advance satellite along orbit
    // Base orbit: move eastward (longitude) with sinusoidal latitude for inclination
    this.baseLon += ORBIT_SPEED_DEG_PER_TICK
    if (this.baseLon > 180) this.baseLon -= 360
    this.baseLat = this.config.startLat +
      ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * s.tickCount) / ORBIT_INCLINATION_PERIOD_TICKS)

    // Apply accumulated micro-adjustments
    s.satLat = Math.max(-85, Math.min(85, this.baseLat + this.adjustLat))
    s.satLon = this.baseLon + this.adjustLon
    // Normalize longitude
    if (s.satLon > 180) s.satLon -= 360
    if (s.satLon < -180) s.satLon += 360

    // 2. Advance debris stochastically — random orbital drift, no convergence
    for (const d of s.debris) {
      d.lat += d.vLat
      d.lon += d.vLon

      // Stochastic perturbations — visible random walk
      d.vLat += (rng() - 0.5) * 0.0004
      d.vLon += (rng() - 0.5) * 0.0003

      // Light velocity damping to prevent runaway speeds
      d.vLat *= 0.999
      d.vLon *= 0.999

      // Clamp latitude, wrap longitude
      if (d.lat > 85 || d.lat < -85) d.vLat *= -1
      if (d.lon > 180) d.lon -= 360
      if (d.lon < -180) d.lon += 360
    }

    // 3. Satellite micro-adjustment decision
    // During the first 20s the satellite uses a smarter avoidance algorithm
    // that considers multiple threats and reacts earlier/harder — it looks like
    // a well-controlled satellite skillfully threading through debris.
    // After that, the naive single-threat decider takes over and eventually
    // gets overwhelmed by the closing debris field.
    const GRACE_TICKS = 600 // 20s at 30 tps
    const inGrace = s.tickCount < GRACE_TICKS
    // During grace: decide every 5 ticks (6×/s) with wider awareness
    // After grace: decide every 15 ticks (2×/s) with narrow awareness
    const decideInterval = inGrace ? 5 : this.config.moveIntervalTicks
    const stepScale = inGrace ? 1.6 : 1.0

    if (s.tickCount > 0 && s.tickCount % decideInterval === 0) {
      let direction: CardinalDirection

      if (inGrace) {
        // Smart multi-threat avoidance — sum repulsion vectors from ALL nearby debris
        let repLat = 0
        let repLon = 0
        for (const d of s.debris) {
          const dist = sceneDistance3D(s.satLat, s.satLon, s.satAltKm, d.lat, d.lon, d.altKm)
          if (dist < 0.35) { // wide awareness radius
            const dLat = s.satLat - d.lat
            let dLon = s.satLon - d.lon
            if (dLon > 180) dLon -= 360
            if (dLon < -180) dLon += 360
            // Inverse-square weighting — closer debris pushes harder
            const weight = 1 / (dist * dist + 0.001)
            repLat += dLat * weight
            repLon += dLon * weight
          }
        }

        if (Math.abs(repLat) < 0.001 && Math.abs(repLon) < 0.001) {
          direction = "HOLD"
        } else {
          const absLat = Math.abs(repLat)
          const absLon = Math.abs(repLon)
          if (absLat > absLon * 1.5) {
            direction = repLat > 0 ? "N" : "S"
          } else if (absLon > absLat * 1.5) {
            direction = repLon > 0 ? "E" : "W"
          } else {
            if (repLat > 0 && repLon > 0) direction = "NE"
            else if (repLat > 0 && repLon < 0) direction = "NW"
            else if (repLat < 0 && repLon > 0) direction = "SE"
            else direction = "SW"
          }
        }
      } else {
        direction = this.decider(s)
      }

      const [dLat, dLon] = DIRECTION_DELTAS[direction]
      const fromLat = s.satLat
      const fromLon = s.satLon

      this.adjustLat += dLat * this.config.moveStepDeg * stepScale
      this.adjustLon += dLon * this.config.moveStepDeg * stepScale

      // Re-apply adjustments
      s.satLat = Math.max(-85, Math.min(85, this.baseLat + this.adjustLat))
      s.satLon = this.baseLon + this.adjustLon
      if (s.satLon > 180) s.satLon -= 360
      if (s.satLon < -180) s.satLon += 360

      s.lastDirection = direction

      if (direction !== "HOLD") {
        s.moveHistory.push({
          tick: s.tickCount,
          direction,
          fromLat,
          fromLon,
          toLat: s.satLat,
          toLon: s.satLon,
        })
      }
    }

    // 4. Collision check + danger tracking (real collisions at all times)
    let nearestDist = Infinity
    let nearestId = -1

    for (const d of s.debris) {
      const dist = sceneDistance3D(s.satLat, s.satLon, s.satAltKm, d.lat, d.lon, d.altKm)
      if (dist < nearestDist) {
        nearestDist = dist
        nearestId = d.id
      }
    }

    s.dangerTargetId = nearestId
    s.dangerDistance = nearestDist

    if (nearestDist < this.config.collisionThreshold) {
      s.collided = true
      s.collisionTick = s.tickCount
    }

    // 5. Check max ticks
    s.tickCount++
    if (s.tickCount >= this.config.maxTicks) {
      s.finished = true
    }
  }

  reset(): void {
    this.init(this.initialDebris)
  }

  /** Get satellite position as scene-space coordinates */
  getSatelliteVec3(): { x: number; y: number; z: number } {
    return geodeticToUnitVector(this.state.satLat, this.state.satLon, this.state.satAltKm)
  }

  /** Get debris position as scene-space coordinates */
  getDebrisVec3(index: number): { x: number; y: number; z: number } {
    const d = this.state.debris[index]
    return geodeticToUnitVector(d.lat, d.lon, d.altKm)
  }

  /** Get the danger target position in scene-space */
  getDangerTargetVec3(): { x: number; y: number; z: number } | null {
    const id = this.state.dangerTargetId
    if (id === null || id < 0) return null
    const d = this.state.debris[id]
    if (!d) return null
    return geodeticToUnitVector(d.lat, d.lon, d.altKm)
  }

  /** Get a move history position in scene-space */
  getMoveVec3(record: MoveRecord): { x: number; y: number; z: number } {
    return geodeticToUnitVector(record.toLat, record.toLon, this.state.satAltKm)
  }

  /** Distance to nearest debris in km (approximate) */
  getNearestDistKm(): number | null {
    if (this.state.dangerDistance === null) return null
    return this.state.dangerDistance * EARTH_RADIUS_KM
  }

  /** Elapsed real-time seconds */
  getElapsedSec(): number {
    return this.state.tickCount / this.config.ticksPerSecond
  }
}

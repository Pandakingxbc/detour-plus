import { geodeticToUnitVector, EARTH_RADIUS_KM } from "@/lib/geo"
import type {
  CardinalDirection,
  DebrisParticle,
  MoveDecider,
  MoveRecord,
  SimConfig,
  SimState,
} from "@/lib/simulation-types"

// --- Seeded PRNG (deterministic demo) with save/restore ---
interface SeededRng {
  (): number
  save(): number
  restore(state: number): void
}

function mulberry32(seed: number): SeededRng {
  let s = seed | 0
  const fn = (() => {
    s = (s + 0x6d2b79f5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }) as SeededRng
  fn.save = () => s
  fn.restore = (newS: number) => { s = newS }
  return fn
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
  collisionThreshold: 0.035, // matches visual overlap of smaller satellite + debris meshes
  seed: 0, // 0 = random seed each run
}

// Satellite orbital parameters — realistic relative speeds
// All LEO objects orbit at ~7.5 km/s. The satellite is slightly faster than
// debris due to altitude differences, not dramatically faster.
const ORBIT_SPEED_DEG_PER_TICK = 0.05 // visible but not video-game fast
const ORBIT_INCLINATION_DEG = 51.6 // ISS-like inclination
const ORBIT_INCLINATION_PERIOD_TICKS = 1500 // smooth sinusoidal path

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
  private rng: SeededRng
  private initialDebris: InitialDebrisPos[] = []
  // Base orbital position (before micro-adjustments)
  private baseLat = 0
  private baseLon = 0
  // Accumulated micro-adjustment offset (position drift from burns)
  private adjustLat = 0
  private adjustLon = 0
  // Adjustment velocity — smooth drift rate from orbital burns (deg/tick)
  private vAdjustLat = 0
  private vAdjustLon = 0
  // Pre-computed safe path for the first SAFE_PATH_TICKS ticks.
  // Each entry stores [adjustLat, adjustLon, vAdjustLat, vAdjustLon] at that tick.
  private safePath: [number, number, number, number][] = []

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
    // Random seed each run unless a fixed seed is specified
    const seed = this.config.seed || (Math.random() * 0xffffffff) >>> 0
    this.rng = mulberry32(seed)
    this.state = this.createInitialState()
    this.baseLat = this.config.startLat
    this.baseLon = this.config.startLon
    this.adjustLat = 0
    this.adjustLon = 0
    this.vAdjustLat = 0
    this.vAdjustLon = 0
    this.safePath = []

    if (debrisPositions && debrisPositions.length > 0) {
      this.initialDebris = debrisPositions
      this.initDebrisFromPositions(debrisPositions)
      this.preComputeSafePath()
    }
  }

  /**
   * Pre-compute a collision-free trajectory for the first 15 seconds.
   *
   * Models realistic satellite collision avoidance:
   *
   *   1. CONJUNCTION ASSESSMENT (every BURN_INTERVAL ticks ≈ 1 second):
   *      Project the satellite's trajectory and every debris piece forward
   *      LOOKAHEAD ticks (~6 seconds). Find the Closest Point of Approach
   *      (CPA) with each debris piece. Rank threats by urgency (closer in
   *      distance AND sooner in time = more urgent).
   *
   *   2. AVOIDANCE MANEUVER:
   *      Compute a single velocity delta (burn) that steers the satellite
   *      away from the CPA geometry. Burns are proportional to threat
   *      urgency — gentle nudges for distant threats, stronger for close ones.
   *
   *   3. COAST PHASE (between burns):
   *      The satellite coasts on its new trajectory. Very low drag (0.999)
   *      so velocity persists, creating smooth orbital arcs — just like a
   *      real satellite after a thruster firing.
   *
   * This produces a path with ~10 planned maneuvers over 15 seconds,
   * with smooth arcs between them. No per-tick reactive dodging.
   *
   * Debris simulation uses the exact same RNG sequence as tick() will at
   * runtime, so positions match perfectly.
   *
   * Retries with 2x stronger burns if any tick collides (up to 5 attempts).
   */
  private preComputeSafePath(): void {
    const SAFE_TICKS = 450 // 15s at 30 tps
    const MAX_ATTEMPTS = 5
    const ct = this.config.collisionThreshold
    const ROUGH_DEG_LIMIT = 25

    // --- Realistic maneuver parameters ---
    const BURN_INTERVAL = 30          // assess & burn every 1s (not every tick)
    const LOOKAHEAD = 180             // project 6s ahead for conjunction assessment
    const LOOKAHEAD_STEP = 6          // sample every 0.2s in the lookahead window
    const DETECTION_RADIUS = 0.35     // scene-space detection range
    const DRAG = 0.999                // very low drag — burns coast smoothly

    // Save RNG state — we'll restore it after so tick() replays the same sequence
    const rngState = this.rng.save()

    let bestPath: [number, number, number, number][] = []

    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      const burnScale = Math.pow(2, attempt) // 1, 2, 4, 8, 16
      const path: [number, number, number, number][] = []

      // Reset RNG and debris snapshot for each attempt
      this.rng.restore(rngState)
      const simDebris = this.state.debris.map(d => ({
        lat: d.lat, lon: d.lon, altKm: d.altKm,
        vLat: d.vLat, vLon: d.vLon,
      }))

      let adjLat = 0
      let adjLon = 0
      let vLat = 0
      let vLon = 0
      let safe = true

      for (let t = 0; t < SAFE_TICKS; t++) {
        // Step 1: Advance base orbit (matches tick() exactly)
        const bLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * (t + 1)
        const bLat = this.config.startLat +
          ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * t) / ORBIT_INCLINATION_PERIOD_TICKS)

        // Step 2: Advance debris with EXACT same stochastic perturbations as tick()
        for (const d of simDebris) {
          d.lat += d.vLat
          d.lon += d.vLon
          d.vLat += (this.rng() - 0.5) * 0.0004
          d.vLon += (this.rng() - 0.5) * 0.0003
          d.vLat *= 0.999
          d.vLon *= 0.999
          if (d.lat > 85 || d.lat < -85) d.vLat *= -1
          if (d.lon > 180) d.lon -= 360
          if (d.lon < -180) d.lon += 360
        }

        // Step 3: Conjunction assessment & burn (only at intervals — coast otherwise)
        if (t % BURN_INTERVAL === 0) {
          const satLat = bLat + adjLat
          const satLon = bLon + adjLon

          // Project satellite and debris forward to find CPAs
          let avoidLat = 0
          let avoidLon = 0

          for (const d of simDebris) {
            // Quick pre-filter on current position
            const curLatDiff = Math.abs(satLat - d.lat)
            if (curLatDiff > ROUGH_DEG_LIMIT) continue
            let curLonDiff = satLon - d.lon
            if (curLonDiff > 180) curLonDiff -= 360
            if (curLonDiff < -180) curLonDiff += 360
            if (Math.abs(curLonDiff) > ROUGH_DEG_LIMIT) continue

            // Find Closest Point of Approach over lookahead window
            let cpaDist = Infinity
            let cpaLook = 0
            let cpaSatLat = satLat
            let cpaSatLon = satLon
            let cpaDLat = d.lat
            let cpaDLon = d.lon

            for (let look = 1; look <= LOOKAHEAD; look += LOOKAHEAD_STEP) {
              // Project satellite: base orbit + current velocity adjustment
              const futBLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * (t + look + 1)
              const futBLat = this.config.startLat +
                ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * (t + look)) / ORBIT_INCLINATION_PERIOD_TICKS)
              const futSatLat = futBLat + adjLat + vLat * look
              const futSatLon = futBLon + adjLon + vLon * look

              // Project debris linearly from current simulated position
              const futDLat = d.lat + d.vLat * look
              let futDLon = d.lon + d.vLon * look
              if (futDLon > 180) futDLon -= 360
              if (futDLon < -180) futDLon += 360

              const dist = sceneDistance3D(
                futSatLat, futSatLon, this.config.startAltKm,
                futDLat, futDLon, d.altKm
              )

              if (dist < cpaDist) {
                cpaDist = dist
                cpaLook = look
                cpaSatLat = futSatLat
                cpaSatLon = futSatLon
                cpaDLat = futDLat
                cpaDLon = futDLon
              }
            }

            // If CPA is within detection range, add avoidance vector
            if (cpaDist < DETECTION_RADIUS) {
              // Urgency: inverse-square of distance, decays with time
              // Imminent close approaches get much more weight
              const distWeight = 1 / (cpaDist * cpaDist + 0.0001)
              const timeWeight = 1 / (1 + cpaLook / 60) // closer in time = more urgent
              const weight = distWeight * timeWeight

              // Avoidance direction: away from debris AT the CPA point
              let dLon = cpaSatLon - cpaDLon
              if (dLon > 180) dLon -= 360
              if (dLon < -180) dLon += 360
              avoidLat += (cpaSatLat - cpaDLat) * weight
              avoidLon += dLon * weight
            }
          }

          // Execute avoidance burn
          const mag = Math.sqrt(avoidLat * avoidLat + avoidLon * avoidLon)
          if (mag > 0.001) {
            const burnStrength = 0.004 * burnScale
            vLat += (avoidLat / mag) * burnStrength
            vLon += (avoidLon / mag) * burnStrength
          }
        }

        // Coast: very gentle drag so burns persist as smooth arcs
        vLat *= DRAG
        vLon *= DRAG

        // Integrate velocity → position offset
        adjLat += vLat
        adjLon += vLon

        path.push([adjLat, adjLon, vLat, vLon])

        // Step 4: Check collision at POST-integration position (matches runtime)
        const finalLat = Math.max(-85, Math.min(85, bLat + adjLat))
        let finalLon = bLon + adjLon
        if (finalLon > 180) finalLon -= 360
        if (finalLon < -180) finalLon += 360

        let minDist = Infinity
        for (const d of simDebris) {
          const fdLatDiff = Math.abs(finalLat - d.lat)
          if (fdLatDiff > ROUGH_DEG_LIMIT) continue
          let fdLonDiff = finalLon - d.lon
          if (fdLonDiff > 180) fdLonDiff -= 360
          if (fdLonDiff < -180) fdLonDiff += 360
          if (Math.abs(fdLonDiff) > ROUGH_DEG_LIMIT) continue

          const dist = sceneDistance3D(finalLat, finalLon, this.config.startAltKm, d.lat, d.lon, d.altKm)
          if (dist < minDist) minDist = dist
        }

        if (minDist < ct * 1.5) {
          safe = false
          break
        }
      }

      bestPath = path
      if (safe) break
    }

    this.safePath = bestPath

    // Restore RNG so tick() replays the exact same debris perturbation sequence
    this.rng.restore(rngState)
  }

  private initDebrisFromPositions(positions: InitialDebrisPos[]): void {
    const rng = this.rng
    const debris: DebrisParticle[] = []

    // All real debris with stochastic orbital drift.
    // The pre-computed safe path handles avoidance — no filtering needed
    // except debris literally overlapping the spawn point.
    for (let i = 0; i < positions.length; i++) {
      const p = positions[i]
      const spawnDist = sceneDistance3D(
        this.config.startLat, this.config.startLon, this.config.startAltKm,
        p.lat, p.lon, p.altKm
      )
      if (spawnDist < this.config.collisionThreshold) continue // only skip exact spawn overlap

      // Debris orbits at roughly similar speed to satellite with some variation
      const baseOrbitalVLon = 0.020 + rng() * 0.015 // ~60-100% of satellite speed
      const vLatWobble = (rng() - 0.5) * 0.006 // latitude drift from inclination differences

      debris.push({
        id: debris.length,
        lat: p.lat,
        lon: p.lon,
        altKm: p.altKm,
        vLat: vLatWobble,
        vLon: baseOrbitalVLon * (rng() > 0.3 ? 1 : -1),
      })
    }

    // Seed hazard debris along the satellite's upcoming orbital path.
    // Waves are timed so nothing appears in the first 20s corridor.

    // Wave 1: ~8 near-miss debris at 20–30s — satellite dodges skillfully
    for (let i = 0; i < 8; i++) {
      const futureTickOffset = 600 + rng() * 300 // 20–30s at 30 tps
      const futureLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * futureTickOffset
      const futureLat = this.config.startLat +
        ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * futureTickOffset) / ORBIT_INCLINATION_PERIOD_TICKS)

      const latOffset = (rng() - 0.5) * 6
      const lonOffset = (rng() - 0.5) * 8

      debris.push({
        id: debris.length,
        lat: Math.max(-85, Math.min(85, futureLat + latOffset)),
        lon: ((futureLon + lonOffset + 180) % 360) - 180,
        altKm: 385 + rng() * 30,
        vLat: (rng() - 0.5) * 0.006,
        vLon: 0.018 + rng() * 0.012,
      })
    }

    // Wave 2: ~8 tighter debris at 28–38s — avoidance is degrading
    for (let i = 0; i < 8; i++) {
      const futureTickOffset = 840 + rng() * 300 // 28–38s at 30 tps
      const futureLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * futureTickOffset
      const futureLat = this.config.startLat +
        ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * futureTickOffset) / ORBIT_INCLINATION_PERIOD_TICKS)

      const latOffset = (rng() - 0.5) * 3.5
      const lonOffset = (rng() - 0.5) * 4

      debris.push({
        id: debris.length,
        lat: Math.max(-85, Math.min(85, futureLat + latOffset)),
        lon: ((futureLon + lonOffset + 180) % 360) - 180,
        altKm: 393 + rng() * 14,
        vLat: (rng() - 0.5) * 0.004,
        vLon: 0.020 + rng() * 0.010,
      })
    }

    // Wave 3: ~5 kill-shot debris at 35–48s — the closing net
    for (let i = 0; i < 5; i++) {
      const futureTickOffset = 1050 + rng() * 390 // 35–48s at 30 tps
      const futureLon = this.config.startLon + ORBIT_SPEED_DEG_PER_TICK * futureTickOffset
      const futureLat = this.config.startLat +
        ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * futureTickOffset) / ORBIT_INCLINATION_PERIOD_TICKS)

      const latOffset = (rng() - 0.5) * 2
      const lonOffset = (rng() - 0.5) * 2.5

      debris.push({
        id: debris.length,
        lat: Math.max(-85, Math.min(85, futureLat + latOffset)),
        lon: ((futureLon + lonOffset + 180) % 360) - 180,
        altKm: 396 + rng() * 8,
        vLat: (rng() - 0.5) * 0.003,
        vLon: 0.022 + rng() * 0.010,
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

    // 2. Advance debris stochastically — pure random orbital drift, no tricks
    // Avoidance skill: 1.0 for first 20s, smoothly degrades to 0 by 40s.
    // This controls lookahead range, detection radius, burn strength, and
    // emergency dodge effectiveness — everything gets worse together.
    const FULL_SKILL_TICKS = 600 // 20s at 30 tps
    const ZERO_SKILL_TICKS = 1200 // 40s — fully degraded
    const avoidanceSkill = s.tickCount < FULL_SKILL_TICKS ? 1.0
      : s.tickCount < ZERO_SKILL_TICKS ? 1.0 - (s.tickCount - FULL_SKILL_TICKS) / (ZERO_SKILL_TICKS - FULL_SKILL_TICKS)
      : 0

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

    // 3. Satellite orbital adjustment
    if (s.tickCount < this.safePath.length) {
      // --- Phase 1: Follow pre-computed safe path (first 15s) ---
      // The path was calculated at init by projecting all debris forward
      // and computing smooth avoidance burns. Guaranteed collision-free.
      const [pAdjLat, pAdjLon, pVLat, pVLon] = this.safePath[s.tickCount]
      this.adjustLat = pAdjLat
      this.adjustLon = pAdjLon
      this.vAdjustLat = pVLat
      this.vAdjustLon = pVLon
    } else {
      // --- Phase 2: Live CPA-based avoidance with degrading skill (after 15s) ---
      // Same realistic approach as pre-computed path: conjunction assessment
      // at intervals, CPA-based burns, coast between maneuvers.
      // Skill degrades from 1.0 at 20s to 0 at 40s, affecting:
      //   - Burn interval (slower decisions as skill drops)
      //   - Lookahead range (shorter horizon)
      //   - Detection radius (narrower awareness)
      //   - Burn strength (weaker corrections)

      // Coast: integrate velocity → position (low drag like pre-computed path)
      this.adjustLat += this.vAdjustLat
      this.adjustLon += this.vAdjustLon
      this.vAdjustLat *= 0.999
      this.vAdjustLon *= 0.999

      // Burn decision interval: 30 ticks at full skill → 90 ticks at low skill
      const burnInterval = Math.round(30 + 60 * (1 - avoidanceSkill))

      if (burnInterval > 0 && s.tickCount % burnInterval === 0 && avoidanceSkill > 0) {
        const lookahead = Math.round(60 + 120 * avoidanceSkill) // 60-180 ticks
        const detectRadius = 0.08 + 0.27 * avoidanceSkill       // 0.08-0.35

        let avoidLat = 0
        let avoidLon = 0

        for (const d of s.debris) {
          // Find CPA over lookahead window
          let cpaDist = Infinity
          let cpaLook = 0
          let cpaSatLat = 0
          let cpaSatLon = 0
          let cpaDLat = 0
          let cpaDLon = 0

          for (let look = 1; look <= lookahead; look += 6) {
            const futBLon = this.baseLon + ORBIT_SPEED_DEG_PER_TICK * look
            const futTick = s.tickCount + look
            const futBLat = this.config.startLat +
              ORBIT_INCLINATION_DEG * 0.4 * Math.sin((2 * Math.PI * futTick) / ORBIT_INCLINATION_PERIOD_TICKS)
            const futSatLat = futBLat + this.adjustLat + this.vAdjustLat * look
            const futSatLon = futBLon + this.adjustLon + this.vAdjustLon * look

            const futDLat = d.lat + d.vLat * look
            let futDLon = d.lon + d.vLon * look
            if (futDLon > 180) futDLon -= 360
            if (futDLon < -180) futDLon += 360

            const dist = sceneDistance3D(futSatLat, futSatLon, s.satAltKm, futDLat, futDLon, d.altKm)
            if (dist < cpaDist) {
              cpaDist = dist
              cpaLook = look
              cpaSatLat = futSatLat
              cpaSatLon = futSatLon
              cpaDLat = futDLat
              cpaDLon = futDLon
            }
          }

          if (cpaDist < detectRadius) {
            const distWeight = 1 / (cpaDist * cpaDist + 0.0001)
            const timeWeight = 1 / (1 + cpaLook / 60)
            const weight = distWeight * timeWeight

            let dLon = cpaSatLon - cpaDLon
            if (dLon > 180) dLon -= 360
            if (dLon < -180) dLon += 360
            avoidLat += (cpaSatLat - cpaDLat) * weight
            avoidLon += dLon * weight
          }
        }

        const mag = Math.sqrt(avoidLat * avoidLat + avoidLon * avoidLon)
        if (mag > 0.001) {
          const burnStrength = 0.001 + 0.003 * avoidanceSkill
          this.vAdjustLat += (avoidLat / mag) * burnStrength
          this.vAdjustLon += (avoidLon / mag) * burnStrength
        }
      }
    }

    s.lastDirection = "HOLD"

    // Apply final position
    s.satLat = Math.max(-85, Math.min(85, this.baseLat + this.adjustLat))
    s.satLon = this.baseLon + this.adjustLon
    if (s.satLon > 180) s.satLon -= 360
    if (s.satLon < -180) s.satLon += 360

    // 4. Collision check — always real, no suppression
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

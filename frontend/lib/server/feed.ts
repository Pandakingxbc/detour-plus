import {
  DEFAULT_FEED_HORIZON_HOURS,
  DEFAULT_FEED_MAX_EVENTS,
  DEFAULT_FEED_STEP_SEC,
  DEFAULT_ORBIT_CLASSES,
  FEED_CACHE_MS,
  HIGH_RISK_KM,
  MAX_DEBRIS_OBJECTS,
  MED_RISK_KM,
} from "@/lib/server/config"
import { getConstraints, getServerState, getManualSatellite } from "@/lib/server/state"
import { distanceKm, orbitClassForAltitude, propagateStateAt, satrecFromTle } from "@/lib/server/sgp4"
import { getDebrisTles, getTargetTle } from "@/lib/server/tle"
import type { ConjunctionEvent, OrbitClass } from "@/lib/server/types"

// Simple RK4 propagator for manual satellite
function propagateManualSatellite(
  position: number[],
  velocity: number[],
  dt: number
): { position: number[]; velocity: number[] } {
  const GM = 398600.4418e9 // Earth gravitational parameter (m^3/s^2)

  // Compute acceleration due to gravity
  function acceleration(pos: number[]): number[] {
    const r = Math.sqrt(pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2)
    const factor = -GM / (r ** 3)
    return [pos[0] * factor, pos[1] * factor, pos[2] * factor]
  }

  // RK4 integration
  const p0 = position
  const v0 = velocity
  const a0 = acceleration(p0)

  const p1 = [p0[0] + v0[0] * dt / 2, p0[1] + v0[1] * dt / 2, p0[2] + v0[2] * dt / 2]
  const v1 = [v0[0] + a0[0] * dt / 2, v0[1] + a0[1] * dt / 2, v0[2] + a0[2] * dt / 2]
  const a1 = acceleration(p1)

  const p2 = [p0[0] + v1[0] * dt / 2, p0[1] + v1[1] * dt / 2, p0[2] + v1[2] * dt / 2]
  const v2 = [v0[0] + a1[0] * dt / 2, v0[1] + a1[1] * dt / 2, v0[2] + a1[2] * dt / 2]
  const a2 = acceleration(p2)

  const p3 = [p0[0] + v2[0] * dt, p0[1] + v2[1] * dt, p0[2] + v2[2] * dt]
  const v3 = [v0[0] + a2[0] * dt, v0[1] + a2[1] * dt, v0[2] + a2[2] * dt]
  const a3 = acceleration(p3)

  const newPosition = [
    p0[0] + (dt / 6) * (v0[0] + 2 * v1[0] + 2 * v2[0] + v3[0]),
    p0[1] + (dt / 6) * (v0[1] + 2 * v1[1] + 2 * v2[1] + v3[1]),
    p0[2] + (dt / 6) * (v0[2] + 2 * v1[2] + 2 * v2[2] + v3[2]),
  ]

  const newVelocity = [
    v0[0] + (dt / 6) * (a0[0] + 2 * a1[0] + 2 * a2[0] + a3[0]),
    v0[1] + (dt / 6) * (a0[1] + 2 * a1[1] + 2 * a2[1] + a3[1]),
    v0[2] + (dt / 6) * (a0[2] + 2 * a1[2] + 2 * a2[2] + a3[2]),
  ]

  return { position: newPosition, velocity: newVelocity }
}

interface FeedOptions {
  noradId: number
  horizonHours?: number
  stepSec?: number
  maxEvents?: number
  debrisLimit?: number
  orbitClasses?: OrbitClass[]
}

export interface FeedResponse {
  generatedAtUtc: string
  horizonHours: number
  stepSec: number
  events: ConjunctionEvent[]
}

function riskFromMissKm(missKm: number): "LOW" | "MED" | "HIGH" {
  if (missKm < HIGH_RISK_KM) return "HIGH"
  if (missKm < MED_RISK_KM) return "MED"
  return "LOW"
}

function riskScore(risk: "LOW" | "MED" | "HIGH"): number {
  if (risk === "HIGH") return 3
  if (risk === "MED") return 2
  return 1
}

function chooseActiveThreat(events: ConjunctionEvent[]): ConjunctionEvent | null {
  if (events.length === 0) return null

  return [...events].sort((a, b) => {
    const scoreDiff = riskScore(b.risk) - riskScore(a.risk)
    if (scoreDiff !== 0) return scoreDiff
    if (a.tcaInMinutes !== b.tcaInMinutes) return a.tcaInMinutes - b.tcaInMinutes
    return a.missKm - b.missKm
  })[0]
}

function clampPositiveInt(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value)) return fallback
  return Math.max(1, Math.floor(value as number))
}

function cacheKey(options: Required<FeedOptions>): string {
  return [
    options.noradId,
    options.horizonHours,
    options.stepSec,
    options.maxEvents,
    options.debrisLimit,
    options.orbitClasses.join(","),
  ].join(":")
}

export async function buildConjunctionFeed(options: FeedOptions): Promise<FeedResponse> {
  const constraints = getConstraints()

  const normalized: Required<FeedOptions> = {
    noradId: options.noradId,
    horizonHours: clampPositiveInt(options.horizonHours, constraints.horizonHours || DEFAULT_FEED_HORIZON_HOURS),
    stepSec: clampPositiveInt(options.stepSec, DEFAULT_FEED_STEP_SEC),
    maxEvents: clampPositiveInt(options.maxEvents, DEFAULT_FEED_MAX_EVENTS),
    debrisLimit: Math.min(clampPositiveInt(options.debrisLimit, MAX_DEBRIS_OBJECTS), MAX_DEBRIS_OBJECTS),
    orbitClasses: options.orbitClasses?.length ? Array.from(new Set(options.orbitClasses)) : DEFAULT_ORBIT_CLASSES,
  }

  const state = getServerState()
  const key = cacheKey(normalized)
  const nowMs = Date.now()
  const cached = state.feedByKey.get(key)
  if (cached && nowMs - cached.generatedAtMs < FEED_CACHE_MS) {
    return cached.data
  }

  const generatedAt = new Date()
  const generatedAtMs = generatedAt.getTime()
  const totalSteps = Math.floor((normalized.horizonHours * 3600) / normalized.stepSec)

  const sampleTimes: Date[] = []
  const targetSeries: Array<{ x: number; y: number; z: number } | null> = []

  // Handle manual satellite (NORAD ID = -1)
  if (normalized.noradId === -1) {
    const manualSat = getManualSatellite()
    if (!manualSat) {
      throw new Error("Manual satellite not loaded")
    }

    const debrisEntry = await getDebrisTles()

    // Propagate manual satellite in real-time from initial state vectors
    const satelliteAgeMs = generatedAtMs - manualSat.epochMs
    const satelliteAgeSec = satelliteAgeMs / 1000

    // Propagate from epoch to current time
    let currentPos = [...manualSat.position]
    let currentVel = [...manualSat.velocity]
    const propagationDt = 10 // 10 second steps for propagation

    const numPropSteps = Math.floor(satelliteAgeSec / propagationDt)
    for (let i = 0; i < numPropSteps; i++) {
      const state = propagateManualSatellite(currentPos, currentVel, propagationDt)
      currentPos = state.position
      currentVel = state.velocity
    }

    // Handle remaining fractional time
    const remainingTime = satelliteAgeSec - numPropSteps * propagationDt
    if (remainingTime > 0) {
      const state = propagateManualSatellite(currentPos, currentVel, remainingTime)
      currentPos = state.position
      currentVel = state.velocity
    }

    // Now propagate into the future for conjunction screening
    for (let step = 0; step <= totalSteps; step += 1) {
      const when = new Date(generatedAtMs + step * normalized.stepSec * 1000)
      sampleTimes.push(when)

      // Propagate forward from current state
      let futurePos = [...currentPos]
      let futureVel = [...currentVel]

      const futureTimeSec = step * normalized.stepSec
      const numFutureSteps = Math.floor(futureTimeSec / propagationDt)

      for (let i = 0; i < numFutureSteps; i++) {
        const state = propagateManualSatellite(futurePos, futureVel, propagationDt)
        futurePos = state.position
        futureVel = state.velocity
      }

      const remainingFuture = futureTimeSec - numFutureSteps * propagationDt
      if (remainingFuture > 0) {
        const state = propagateManualSatellite(futurePos, futureVel, remainingFuture)
        futurePos = state.position
        futureVel = state.velocity
      }

      targetSeries.push({ x: futurePos[0] / 1000, y: futurePos[1] / 1000, z: futurePos[2] / 1000 }) // Convert m to km
    }

    // Continue with conjunction detection using debrisEntry
    const allowedClasses = new Set(normalized.orbitClasses)
    const debrisPool: Array<{ noradId: number; satrec: ReturnType<typeof satrecFromTle> }> = []

    for (let idx = 0; idx < debrisEntry.objects.length; idx += 1) {
      if (debrisPool.length >= normalized.debrisLimit) break

      const candidate = debrisEntry.objects[idx]
      const satrec = satrecFromTle(candidate)
      const currentState = propagateStateAt(satrec, generatedAt)
      if (!currentState) continue

      const orbitClass = orbitClassForAltitude(currentState.altKm)
      if (!allowedClasses.has(orbitClass)) continue

      debrisPool.push({ noradId: candidate.noradId, satrec })
    }

    const events: ConjunctionEvent[] = []

    for (let idx = 0; idx < debrisPool.length; idx += 1) {
      const debris = debrisPool[idx]

      let bestDistanceKm = Number.POSITIVE_INFINITY
      let bestStep = -1

      for (let step = 0; step < sampleTimes.length; step += 1) {
        const targetPos = targetSeries[step]
        if (!targetPos) continue

        const debrisState = propagateStateAt(debris.satrec, sampleTimes[step])
        if (!debrisState) continue

        const missKm = distanceKm(targetPos, debrisState.eci)
        if (missKm < bestDistanceKm) {
          bestDistanceKm = missKm
          bestStep = step
        }
      }

      if (!Number.isFinite(bestDistanceKm) || bestStep < 0) continue

      const tcaTime = sampleTimes[bestStep]
      const tcaInMinutes = Math.round((tcaTime.getTime() - generatedAtMs) / 60000)
      const risk = riskFromMissKm(bestDistanceKm)

      events.push({
        eventId: `evt_${debris.noradId}_${bestStep}`,
        tcaUtc: tcaTime.toISOString(),
        tcaInMinutes,
        missKm: Number(bestDistanceKm.toFixed(3)),
        risk,
        secondaryNorad: debris.noradId,
      })
    }

    events.sort((a, b) => {
      if (a.missKm !== b.missKm) return a.missKm - b.missKm
      return a.tcaInMinutes - b.tcaInMinutes
    })

    const response: FeedResponse = {
      generatedAtUtc: generatedAt.toISOString(),
      horizonHours: normalized.horizonHours,
      stepSec: normalized.stepSec,
      events: events.slice(0, normalized.maxEvents),
    }

    state.feedByKey.set(key, {
      generatedAtMs,
      data: response,
    })

    return response
  }

  // Regular satellite (existing code)
  const [targetTleEntry, debrisEntry] = await Promise.all([
    getTargetTle(normalized.noradId),
    getDebrisTles(),
  ])

  const target = targetTleEntry.objects[0]
  if (!target) {
    throw new Error(`Target TLE missing for NORAD ${normalized.noradId}`)
  }

  const targetSatrec = satrecFromTle(target)

  for (let step = 0; step <= totalSteps; step += 1) {
    const when = new Date(generatedAtMs + step * normalized.stepSec * 1000)
    sampleTimes.push(when)
    const stateAt = propagateStateAt(targetSatrec, when)
    targetSeries.push(stateAt ? stateAt.eci : null)
  }

  const allowedClasses = new Set(normalized.orbitClasses)
  const debrisPool: Array<{ noradId: number; satrec: ReturnType<typeof satrecFromTle> }> = []

  for (let idx = 0; idx < debrisEntry.objects.length; idx += 1) {
    if (debrisPool.length >= normalized.debrisLimit) break

    const candidate = debrisEntry.objects[idx]
    if (candidate.noradId === normalized.noradId) continue

    const satrec = satrecFromTle(candidate)
    const currentState = propagateStateAt(satrec, generatedAt)
    if (!currentState) continue

    const orbitClass = orbitClassForAltitude(currentState.altKm)
    if (!allowedClasses.has(orbitClass)) continue

    debrisPool.push({ noradId: candidate.noradId, satrec })
  }

  const events: ConjunctionEvent[] = []

  for (let idx = 0; idx < debrisPool.length; idx += 1) {
    const debris = debrisPool[idx]

    let bestDistanceKm = Number.POSITIVE_INFINITY
    let bestStep = -1

    for (let step = 0; step < sampleTimes.length; step += 1) {
      const targetPos = targetSeries[step]
      if (!targetPos) continue

      const debrisState = propagateStateAt(debris.satrec, sampleTimes[step])
      if (!debrisState) continue

      const missKm = distanceKm(targetPos, debrisState.eci)
      if (missKm < bestDistanceKm) {
        bestDistanceKm = missKm
        bestStep = step
      }
    }

    if (!Number.isFinite(bestDistanceKm) || bestStep < 0) continue

    const tcaTime = sampleTimes[bestStep]
    const tcaInMinutes = Math.round((tcaTime.getTime() - generatedAtMs) / 60000)
    const risk = riskFromMissKm(bestDistanceKm)

    events.push({
      eventId: `evt_${debris.noradId}_${bestStep}`,
      tcaUtc: tcaTime.toISOString(),
      tcaInMinutes,
      missKm: Number(bestDistanceKm.toFixed(3)),
      risk,
      secondaryNorad: debris.noradId,
    })
  }

  events.sort((a, b) => {
    if (a.missKm !== b.missKm) return a.missKm - b.missKm
    return a.tcaInMinutes - b.tcaInMinutes
  })

  const response: FeedResponse = {
    generatedAtUtc: generatedAt.toISOString(),
    horizonHours: normalized.horizonHours,
    stepSec: normalized.stepSec,
    events: events.slice(0, normalized.maxEvents),
  }

  state.feedByKey.set(key, {
    generatedAtMs,
    data: response,
  })

  return response
}

export async function getActiveThreat(options: FeedOptions): Promise<ConjunctionEvent | null> {
  const feed = await buildConjunctionFeed(options)
  return chooseActiveThreat(feed.events)
}

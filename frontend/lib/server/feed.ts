import {
  DEFAULT_FEED_HORIZON_HOURS,
  DEFAULT_FEED_MAX_EVENTS,
  DEFAULT_FEED_STEP_SEC,
  FEED_CACHE_MS,
  HIGH_RISK_KM,
  MAX_DEBRIS_OBJECTS,
  MED_RISK_KM,
} from "@/lib/server/config"
import { getConstraints, getServerState } from "@/lib/server/state"
import { distanceKm, propagateStateAt, satrecFromTle } from "@/lib/server/sgp4"
import { getDebrisTles, getTargetTle } from "@/lib/server/tle"
import type { ConjunctionEvent, RiskLabel, TleObject } from "@/lib/server/types"

interface FeedOptions {
  noradId: number
  horizonHours?: number
  stepSec?: number
  maxEvents?: number
  debrisLimit?: number
}

export interface FeedResponse {
  generatedAtUtc: string
  horizonHours: number
  stepSec: number
  events: ConjunctionEvent[]
}

function riskFromMissKm(missKm: number): RiskLabel {
  if (missKm < HIGH_RISK_KM) return "HIGH"
  if (missKm < MED_RISK_KM) return "MED"
  return "LOW"
}

function riskScore(risk: RiskLabel): number {
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
  }

  const state = getServerState()
  const key = cacheKey(normalized)
  const nowMs = Date.now()
  const cached = state.feedByKey.get(key)
  if (cached && nowMs - cached.generatedAtMs < FEED_CACHE_MS) {
    return cached.data
  }

  const [targetTleEntry, debrisEntry] = await Promise.all([
    getTargetTle(normalized.noradId),
    getDebrisTles(),
  ])

  const target = targetTleEntry.objects[0]
  if (!target) {
    throw new Error(`Target TLE missing for NORAD ${normalized.noradId}`)
  }

  const debrisPool = debrisEntry.objects
    .filter((obj) => obj.noradId !== normalized.noradId)
    .slice(0, normalized.debrisLimit)

  const generatedAt = new Date()
  const generatedAtMs = generatedAt.getTime()
  const totalSteps = Math.floor((normalized.horizonHours * 3600) / normalized.stepSec)

  const sampleTimes: Date[] = []
  const targetSeries: Array<{ x: number; y: number; z: number } | null> = []
  const targetSatrec = satrecFromTle(target)

  for (let step = 0; step <= totalSteps; step += 1) {
    const when = new Date(generatedAtMs + step * normalized.stepSec * 1000)
    sampleTimes.push(when)
    const stateAt = propagateStateAt(targetSatrec, when)
    targetSeries.push(stateAt ? stateAt.eci : null)
  }

  const events: ConjunctionEvent[] = []

  for (let idx = 0; idx < debrisPool.length; idx += 1) {
    const debris = debrisPool[idx]
    const debrisSatrec = satrecFromTle(debris)

    let bestDistanceKm = Number.POSITIVE_INFINITY
    let bestStep = -1

    for (let step = 0; step < sampleTimes.length; step += 1) {
      const targetPos = targetSeries[step]
      if (!targetPos) continue

      const debrisState = propagateStateAt(debrisSatrec, sampleTimes[step])
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

export function pickDebrisSubset(objects: TleObject[], limit: number): TleObject[] {
  return objects.slice(0, Math.min(limit, MAX_DEBRIS_OBJECTS))
}

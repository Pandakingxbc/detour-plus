import type { ConjunctionEvent, ConstraintsState, TleCacheEntry } from "@/lib/server/types"

interface FeedCacheEntry {
  generatedAtMs: number
  data: {
    generatedAtUtc: string
    horizonHours: number
    stepSec: number
    events: ConjunctionEvent[]
  }
}

interface ManualSatelliteTrajectory {
  times: number[]
  positions: number[][]
  velocities: number[][]
  loadedAtMs: number
}

interface DetourServerState {
  targetTles: Map<number, TleCacheEntry>
  debrisByGroup: Map<string, TleCacheEntry>
  feedByKey: Map<string, FeedCacheEntry>
  constraints: ConstraintsState
  manualSatellite: ManualSatelliteTrajectory | null
}

declare global {
  // eslint-disable-next-line no-var
  var __detourServerState: DetourServerState | undefined
}

function buildInitialConstraints(): ConstraintsState {
  return {
    maxTotalDeltaV: 0.35,
    maxBurns: 1,
    preferredAxis: "along",
    horizonHours: 24,
    updatedAtUtc: new Date().toISOString(),
  }
}

function createState(): DetourServerState {
  return {
    targetTles: new Map<number, TleCacheEntry>(),
    debrisByGroup: new Map<string, TleCacheEntry>(),
    feedByKey: new Map<string, FeedCacheEntry>(),
    constraints: buildInitialConstraints(),
    manualSatellite: null,
  }
}

export function getServerState(): DetourServerState {
  if (!globalThis.__detourServerState) {
    globalThis.__detourServerState = createState()
  }
  return globalThis.__detourServerState
}

export function getConstraints(): ConstraintsState {
  return getServerState().constraints
}

export function updateConstraints(next: Omit<ConstraintsState, "updatedAtUtc">): ConstraintsState {
  const state = getServerState()
  state.constraints = {
    ...next,
    updatedAtUtc: new Date().toISOString(),
  }
  state.feedByKey.clear()
  return state.constraints
}

export function setManualSatellite(trajectory: ManualSatelliteTrajectory | null): void {
  const state = getServerState()
  state.manualSatellite = trajectory
  state.feedByKey.clear()
}

export function getManualSatellite(): ManualSatelliteTrajectory | null {
  return getServerState().manualSatellite
}

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

interface ManualSatelliteState {
  position: number[]  // ECI [x,y,z] in meters
  velocity: number[]  // ECI [vx,vy,vz] in m/s
  epoch: string       // ISO timestamp when state was defined
  epochMs: number     // Epoch in milliseconds
  // Keep trajectory for visualization
  trajectory: {
    times: number[]
    positions: number[][]
    velocities: number[][]
  }
}

interface DetourServerState {
  targetTles: Map<number, TleCacheEntry>
  debrisByGroup: Map<string, TleCacheEntry>
  feedByKey: Map<string, FeedCacheEntry>
  constraints: ConstraintsState
  manualSatellite: ManualSatelliteState | null
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

export function setManualSatellite(satellite: ManualSatelliteState | null): void {
  const state = getServerState()
  state.manualSatellite = satellite
  state.feedByKey.clear()
}

export function getManualSatellite(): ManualSatelliteState | null {
  return getServerState().manualSatellite
}

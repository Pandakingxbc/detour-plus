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

interface DetourServerState {
  targetTles: Map<number, TleCacheEntry>
  debrisByGroup: Map<string, TleCacheEntry>
  feedByKey: Map<string, FeedCacheEntry>
  constraints: ConstraintsState
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

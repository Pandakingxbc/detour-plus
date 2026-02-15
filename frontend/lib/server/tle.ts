import {
  CELESTRAK_GROUP_URL,
  CELESTRAK_TARGET_URL,
  DEFAULT_DEBRIS_GROUP,
  MAX_DEBRIS_OBJECTS,
  TARGET_TLE_CACHE_MS,
} from "@/lib/server/config"
import { getServerState } from "@/lib/server/state"
import type { TleCacheEntry, TleObject } from "@/lib/server/types"

function parseNoradFromLine1(line1: string): number | null {
  const value = Number.parseInt(line1.slice(2, 7).trim(), 10)
  return Number.isFinite(value) ? value : null
}

function normalizeName(name: string | undefined, noradId: number): string {
  const trimmed = (name ?? "").trim()
  return trimmed.length > 0 ? trimmed : `NORAD-${noradId}`
}

export function parseTleText(rawText: string): TleObject[] {
  const lines = rawText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  const objects: TleObject[] = []

  for (let i = 0; i < lines.length; i += 1) {
    const current = lines[i]
    const next = lines[i + 1]
    const nextNext = lines[i + 2]

    if (current.startsWith("1 ") && next?.startsWith("2 ")) {
      const noradId = parseNoradFromLine1(current)
      if (!noradId) continue

      const prev = lines[i - 1]
      const hasName = prev && !prev.startsWith("1 ") && !prev.startsWith("2 ")
      objects.push({
        noradId,
        name: normalizeName(hasName ? prev : undefined, noradId),
        line1: current,
        line2: next,
      })
      continue
    }

    if (next?.startsWith("1 ") && nextNext?.startsWith("2 ")) {
      const noradId = parseNoradFromLine1(next)
      if (!noradId) continue
      objects.push({
        noradId,
        name: normalizeName(current, noradId),
        line1: next,
        line2: nextNext,
      })
      i += 2
    }
  }

  return objects
}

async function fetchTleText(url: string): Promise<string> {
  const response = await fetch(url, {
    method: "GET",
    headers: {
      "User-Agent": "detour-nextjs/0.1",
      Accept: "text/plain",
    },
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Failed TLE fetch: HTTP ${response.status}`)
  }

  return response.text()
}

export async function getTargetTle(noradId: number): Promise<TleCacheEntry> {
  const state = getServerState()
  const cached = state.targetTles.get(noradId)
  const now = Date.now()

  if (cached && now - cached.fetchedAtMs < TARGET_TLE_CACHE_MS) {
    return cached
  }

  const url = `${CELESTRAK_TARGET_URL}?CATNR=${noradId}&FORMAT=tle`
  const rawText = await fetchTleText(url)
  const parsed = parseTleText(rawText)

  if (parsed.length === 0) {
    throw new Error(`No parseable TLE found for NORAD ${noradId}`)
  }

  const entry: TleCacheEntry = {
    fetchedAtUtc: new Date(now).toISOString(),
    fetchedAtMs: now,
    rawText,
    objects: [parsed[0]],
    source: "celestrak:CATNR",
  }

  state.targetTles.set(noradId, entry)
  return entry
}

export async function getDebrisTles(group = DEFAULT_DEBRIS_GROUP): Promise<TleCacheEntry> {
  const state = getServerState()
  const cacheKey = group.toLowerCase()
  const cached = state.debrisByGroup.get(cacheKey)
  const now = Date.now()

  if (cached && now - cached.fetchedAtMs < TARGET_TLE_CACHE_MS) {
    return cached
  }

  const url = `${CELESTRAK_GROUP_URL}?GROUP=${encodeURIComponent(group)}&FORMAT=tle`
  const rawText = await fetchTleText(url)
  const parsed = parseTleText(rawText).slice(0, MAX_DEBRIS_OBJECTS)

  if (parsed.length === 0) {
    throw new Error(`No parseable TLE objects found for group ${group}`)
  }

  const entry: TleCacheEntry = {
    fetchedAtUtc: new Date(now).toISOString(),
    fetchedAtMs: now,
    rawText,
    objects: parsed,
    source: `celestrak:${group}`,
  }

  state.debrisByGroup.set(cacheKey, entry)
  return entry
}

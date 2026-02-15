import type { OrbitClass } from "@/lib/server/types"

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback
  return Math.floor(parsed)
}

function parseOrbitClassToken(token: string): OrbitClass | null {
  const normalized = token.trim().toUpperCase()
  if (normalized === "LEO" || normalized === "MEO" || normalized === "GEO") {
    return normalized
  }
  return null
}

export function parseOrbitClasses(value: string | undefined, fallback: OrbitClass[]): OrbitClass[] {
  if (!value) return fallback

  const parsed = value
    .split(",")
    .map(parseOrbitClassToken)
    .filter((token): token is OrbitClass => token !== null)

  if (parsed.length === 0) return fallback

  return Array.from(new Set(parsed))
}

export const TARGET_TLE_CACHE_MS = parsePositiveInt(process.env.TLE_CACHE_MS, 10 * 60 * 1000)
export const FEED_CACHE_MS = parsePositiveInt(process.env.FEED_CACHE_MS, 45 * 1000)
export const DEFAULT_DEBRIS_GROUP = process.env.TLE_DEBRIS_GROUP ?? "active"
export const MAX_DEBRIS_OBJECTS = parsePositiveInt(process.env.MAX_DEBRIS_OBJECTS, 3000)
export const DEFAULT_DEBRIS_LIMIT = parsePositiveInt(process.env.DEFAULT_DEBRIS_LIMIT, 1500)

export const DEFAULT_FEED_HORIZON_HOURS = parsePositiveInt(process.env.DEFAULT_FEED_HOURS, 24)
export const DEFAULT_FEED_STEP_SEC = parsePositiveInt(process.env.DEFAULT_FEED_STEP_SEC, 120)
export const DEFAULT_FEED_MAX_EVENTS = parsePositiveInt(process.env.DEFAULT_FEED_MAX_EVENTS, 8)
export const DEFAULT_ORBIT_CLASSES = parseOrbitClasses(process.env.DEFAULT_ORBIT_CLASSES, ["LEO", "MEO"])

export const HIGH_RISK_KM = Number(process.env.HIGH_RISK_KM ?? 3)
export const MED_RISK_KM = Number(process.env.MED_RISK_KM ?? 10)

export const CELESTRAK_TARGET_URL = "https://celestrak.org/NORAD/elements/gp.php"
export const CELESTRAK_GROUP_URL = "https://celestrak.org/NORAD/elements/gp.php"

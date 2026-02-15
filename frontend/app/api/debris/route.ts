import { NextRequest, NextResponse } from "next/server"

import {
  DEFAULT_DEBRIS_GROUP,
  DEFAULT_DEBRIS_LIMIT,
  DEFAULT_ORBIT_CLASSES,
  MAX_DEBRIS_OBJECTS,
  parseOrbitClasses,
} from "@/lib/server/config"
import { orbitClassForAltitude, propagateAt } from "@/lib/server/sgp4"
import { getDebrisTles } from "@/lib/server/tle"
import type { OrbitClass } from "@/lib/server/types"

export const runtime = "nodejs"

function parseLimit(raw: string | null): number {
  if (!raw) return DEFAULT_DEBRIS_LIMIT
  const parsed = Number.parseInt(raw, 10)
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_DEBRIS_LIMIT
  return Math.min(parsed, MAX_DEBRIS_OBJECTS)
}

export async function GET(request: NextRequest) {
  const limit = parseLimit(request.nextUrl.searchParams.get("limit"))
  const group = request.nextUrl.searchParams.get("group") ?? DEFAULT_DEBRIS_GROUP
  const orbitClasses = parseOrbitClasses(request.nextUrl.searchParams.get("orbitClasses") ?? undefined, DEFAULT_ORBIT_CLASSES)
  const allowedClasses = new Set<OrbitClass>(orbitClasses)

  try {
    const debrisEntry = await getDebrisTles(group)
    const now = new Date()
    const objects: Array<{
      noradId: number
      name: string
      x: number
      y: number
      z: number
      lat: number
      lon: number
      altKm: number
    }> = []

    for (let idx = 0; idx < debrisEntry.objects.length; idx += 1) {
      if (objects.length >= limit) break

      const obj = debrisEntry.objects[idx]
      const state = propagateAt(obj, now)
      if (!state) continue

      const orbitClass = orbitClassForAltitude(state.altKm)
      if (!allowedClasses.has(orbitClass)) continue

      objects.push({
        noradId: obj.noradId,
        name: obj.name,
        x: state.x,
        y: state.y,
        z: state.z,
        lat: state.lat,
        lon: state.lon,
        altKm: state.altKm,
      })
    }

    return NextResponse.json({
      timeUtc: now.toISOString(),
      source: debrisEntry.source,
      orbitClasses,
      objects,
    })
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to load debris sample",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 }
    )
  }
}

import { NextRequest, NextResponse } from "next/server"

import { DEFAULT_DEBRIS_GROUP, DEFAULT_DEBRIS_LIMIT, MAX_DEBRIS_OBJECTS } from "@/lib/server/config"
import { propagateAt } from "@/lib/server/sgp4"
import { getDebrisTles } from "@/lib/server/tle"

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

  try {
    const debrisEntry = await getDebrisTles(group)
    const sample = debrisEntry.objects.slice(0, limit)
    const now = new Date()

    const objects = sample
      .map((obj) => {
        const state = propagateAt(obj, now)
        if (!state) return null

        return {
          noradId: obj.noradId,
          name: obj.name,
          x: state.x,
          y: state.y,
          z: state.z,
          lat: state.lat,
          lon: state.lon,
          altKm: state.altKm,
        }
      })
      .filter((value): value is NonNullable<typeof value> => value !== null)

    return NextResponse.json({
      timeUtc: now.toISOString(),
      source: debrisEntry.source,
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

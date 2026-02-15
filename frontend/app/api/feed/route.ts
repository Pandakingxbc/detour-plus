import { NextRequest, NextResponse } from "next/server"

import {
  DEFAULT_FEED_HORIZON_HOURS,
  DEFAULT_FEED_MAX_EVENTS,
  DEFAULT_ORBIT_CLASSES,
  DEFAULT_FEED_STEP_SEC,
  MAX_DEBRIS_OBJECTS,
  parseOrbitClasses,
} from "@/lib/server/config"
import { buildConjunctionFeed } from "@/lib/server/feed"

export const runtime = "nodejs"

function parsePositive(raw: string | null, fallback: number): number {
  if (!raw) return fallback
  const parsed = Number(raw)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback
  return Math.floor(parsed)
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams
  const noradRaw = params.get("norad")

  if (!noradRaw) {
    return NextResponse.json({ error: "Missing query parameter: norad" }, { status: 400 })
  }

  const noradId = Number.parseInt(noradRaw, 10)
  if (!Number.isInteger(noradId) || (noradId <= 0 && noradId !== -1)) {
    return NextResponse.json({ error: "Invalid NORAD ID" }, { status: 400 })
  }

  const horizonHours = parsePositive(params.get("horizonHours"), DEFAULT_FEED_HORIZON_HOURS)
  const stepSec = parsePositive(params.get("stepSec"), DEFAULT_FEED_STEP_SEC)
  const maxEvents = parsePositive(params.get("maxEvents"), DEFAULT_FEED_MAX_EVENTS)
  const debrisLimit = parsePositive(params.get("debrisLimit"), MAX_DEBRIS_OBJECTS)
  const orbitClasses = parseOrbitClasses(params.get("orbitClasses") ?? undefined, DEFAULT_ORBIT_CLASSES)
  const forceRaw = params.get("force")
  const forceRefresh = forceRaw === "1" || forceRaw?.toLowerCase() === "true"

  try {
    const feed = await buildConjunctionFeed({
      noradId,
      horizonHours,
      stepSec,
      maxEvents,
      debrisLimit,
      orbitClasses,
      forceRefresh,
    })

    return NextResponse.json(feed)
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to generate conjunction feed",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 }
    )
  }
}

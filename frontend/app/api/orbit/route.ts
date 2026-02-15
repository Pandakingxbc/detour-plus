import { NextRequest, NextResponse } from "next/server"

import { propagateRange } from "@/lib/server/sgp4"
import { getTargetTle } from "@/lib/server/tle"

export const runtime = "nodejs"

function parsePositive(value: string | null, fallback: number): number {
  if (!value) return fallback
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback
  return parsed
}

export async function GET(request: NextRequest) {
  const noradRaw = request.nextUrl.searchParams.get("norad")
  if (!noradRaw) {
    return NextResponse.json({ error: "Missing query parameter: norad" }, { status: 400 })
  }

  const norad = Number.parseInt(noradRaw, 10)
  if (!Number.isInteger(norad) || norad <= 0) {
    return NextResponse.json({ error: "Invalid NORAD ID" }, { status: 400 })
  }

  const minutes = parsePositive(request.nextUrl.searchParams.get("minutes"), 180)
  const stepSec = parsePositive(request.nextUrl.searchParams.get("stepSec"), 60)

  try {
    const tleEntry = await getTargetTle(norad)
    const target = tleEntry.objects[0]
    if (!target) {
      return NextResponse.json({ error: "No target TLE found" }, { status: 404 })
    }

    const start = new Date()
    const points = propagateRange(target, minutes, stepSec, start)

    return NextResponse.json({
      noradId: norad,
      timeStartUtc: start.toISOString(),
      stepSec: Math.round(stepSec),
      points,
    })
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to generate orbit track",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 }
    )
  }
}

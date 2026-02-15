import { NextRequest, NextResponse } from "next/server"

import { estimateInclinationDeg, orbitClassForAltitude, propagateAt } from "@/lib/server/sgp4"
import { getTargetTle } from "@/lib/server/tle"

export const runtime = "nodejs"

function inferObjectType(name: string): string {
  const value = name.toLowerCase()
  if (value.includes("debris")) return "debris"
  if (value.includes("rocket")) return "rocket_body"
  return "satellite"
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

  try {
    const targetEntry = await getTargetTle(norad)
    const target = targetEntry.objects[0]
    if (!target) {
      return NextResponse.json({ error: "No TLE found for target" }, { status: 404 })
    }

    const now = new Date()
    const state = propagateAt(target, now)

    if (!state) {
      return NextResponse.json({ error: "Unable to propagate target orbit" }, { status: 500 })
    }

    const inclinationDeg = estimateInclinationDeg(target)
    const orbitClass = orbitClassForAltitude(state.altKm)

    return NextResponse.json({
      noradId: target.noradId,
      name: target.name,
      objectType: inferObjectType(target.name),
      orbitClass,
      altitudeKm: Number(state.altKm.toFixed(3)),
      inclinationDeg: inclinationDeg !== null ? Number(inclinationDeg.toFixed(3)) : null,
      lastUpdatedUtc: now.toISOString(),
      tleUpdatedUtc: targetEntry.fetchedAtUtc,
      tle: {
        line1: target.line1,
        line2: target.line2,
      },
    })
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to load target",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 }
    )
  }
}

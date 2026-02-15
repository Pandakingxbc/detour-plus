import { NextRequest, NextResponse } from "next/server"

import { DEFAULT_DEBRIS_GROUP } from "@/lib/server/config"
import { getDebrisTles, getTargetTle } from "@/lib/server/tle"

export const runtime = "nodejs"

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const noradRaw = searchParams.get("norad")
  const group = searchParams.get("group") ?? DEFAULT_DEBRIS_GROUP

  if (!noradRaw) {
    return NextResponse.json({ error: "Missing query parameter: norad" }, { status: 400 })
  }

  const norad = Number.parseInt(noradRaw, 10)
  if (!Number.isInteger(norad) || norad <= 0) {
    return NextResponse.json({ error: "Invalid NORAD ID" }, { status: 400 })
  }

  try {
    const [target, debris] = await Promise.all([getTargetTle(norad), getDebrisTles(group)])

    return NextResponse.json({
      fetchedAtUtc: new Date().toISOString(),
      targetFetchedAtUtc: target.fetchedAtUtc,
      debrisFetchedAtUtc: debris.fetchedAtUtc,
      targetTleText: target.rawText,
      debrisTleText: debris.rawText,
      source: {
        target: target.source,
        debris: debris.source,
      },
    })
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to fetch TLE data",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 }
    )
  }
}

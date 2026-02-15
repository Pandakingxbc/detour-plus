import { NextRequest, NextResponse } from "next/server"

import { buildManualManeuverTrajectory } from "@/lib/server/manual-orbit"

export const runtime = "nodejs"

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      position: number[]
      velocity: number[]
      direction: "radial-out" | "radial-in" | "prograde" | "retrograde"
      delta_v_magnitude: number
    }

    const result = buildManualManeuverTrajectory(body)
    return NextResponse.json(result)
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to apply manual maneuver",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 400 }
    )
  }
}

import { NextRequest, NextResponse } from "next/server"

import { buildManualTrajectory } from "@/lib/server/manual-orbit"

export const runtime = "nodejs"

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      altitude_km: number
      speed_mps: number
      inclination_deg?: number
      raan_deg?: number
      duration_sec?: number
      dt?: number
    }

    const result = buildManualTrajectory(body)
    return NextResponse.json(result)
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to generate manual trajectory",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 400 }
    )
  }
}

import { NextRequest, NextResponse } from "next/server"
import { setManualSatellite } from "@/lib/server/state"

export const runtime = "nodejs"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    if (!body.times || !body.positions || !body.velocities) {
      return NextResponse.json({ error: "Missing trajectory data" }, { status: 400 })
    }

    setManualSatellite({
      times: body.times,
      positions: body.positions,
      velocities: body.velocities,
      loadedAtMs: Date.now(),
    })

    return NextResponse.json({ ok: true })
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to store manual satellite", detail: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    )
  }
}

export async function DELETE() {
  setManualSatellite(null)
  return NextResponse.json({ ok: true })
}

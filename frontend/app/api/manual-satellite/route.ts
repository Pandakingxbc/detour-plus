import { NextRequest, NextResponse } from "next/server"
import { setManualSatellite } from "@/lib/server/state"

export const runtime = "nodejs"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    if (!body.position || !body.velocity || !body.epoch || !body.trajectory) {
      return NextResponse.json({ error: "Missing state vector or trajectory data" }, { status: 400 })
    }

    const epochDate = new Date(body.epoch)
    setManualSatellite({
      position: body.position,
      velocity: body.velocity,
      epoch: body.epoch,
      epochMs: epochDate.getTime(),
      trajectory: body.trajectory,
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

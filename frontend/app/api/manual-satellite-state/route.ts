import { NextResponse } from "next/server"
import { getManualSatellite } from "@/lib/server/state"

export const runtime = "nodejs"

export async function GET() {
  const manualSat = getManualSatellite()

  if (!manualSat) {
    return NextResponse.json({ error: "No manual satellite loaded" }, { status: 404 })
  }

  return NextResponse.json({
    position: manualSat.position,
    velocity: manualSat.velocity,
    epoch: manualSat.epoch,
  })
}

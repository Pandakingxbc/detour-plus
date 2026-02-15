import { NextRequest, NextResponse } from "next/server"

import { getConstraints, updateConstraints } from "@/lib/server/state"

export const runtime = "nodejs"

interface ConstraintsBody {
  maxTotalDeltaV?: number
  maxBurns?: 1 | 2
  preferredAxis?: "along" | "radial" | "cross"
  horizonHours?: number
}

export async function GET() {
  return NextResponse.json({ constraints: getConstraints() })
}

export async function POST(request: NextRequest) {
  let body: ConstraintsBody

  try {
    body = (await request.json()) as ConstraintsBody
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 })
  }

  const maxTotalDeltaV = Number(body.maxTotalDeltaV)
  const maxBurns = body.maxBurns === 2 ? 2 : 1
  const preferredAxis =
    body.preferredAxis === "radial" || body.preferredAxis === "cross" || body.preferredAxis === "along"
      ? body.preferredAxis
      : "along"
  const horizonHours = Math.max(1, Math.floor(Number(body.horizonHours)))

  if (!Number.isFinite(maxTotalDeltaV) || maxTotalDeltaV < 0) {
    return NextResponse.json({ error: "maxTotalDeltaV must be a non-negative number" }, { status: 400 })
  }

  if (!Number.isFinite(horizonHours)) {
    return NextResponse.json({ error: "horizonHours must be a positive number" }, { status: 400 })
  }

  const constraints = updateConstraints({
    maxTotalDeltaV,
    maxBurns,
    preferredAxis,
    horizonHours,
  })

  return NextResponse.json({
    ok: true,
    message: "Constraints applied. Feed cache cleared.",
    constraints,
  })
}

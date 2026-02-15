"use client"

import { FormEvent, useMemo, useState } from "react"
import { Loader2 } from "lucide-react"

export type ManeuverAxis = "along" | "radial" | "cross"

export interface PlannerConstraints {
  maxTotalDeltaV: number
  maxBurns: 1 | 2
  preferredAxis: ManeuverAxis
  horizonHours: number
}

export interface ApplyConstraintsResult {
  ok: boolean
  message: string
  appliedAt: string
}

export interface ManualSatelliteData {
  norad_id: number
  times: number[]
  positions: number[][]
  velocities: number[][]
}

interface ConstraintsPanelProps {
  appliedConstraints: PlannerConstraints
  onApply: (next: PlannerConstraints) => Promise<ApplyConstraintsResult>
  onManualSatelliteLoad?: (data: ManualSatelliteData) => void
}

function constraintsEqual(a: PlannerConstraints, b: PlannerConstraints): boolean {
  return (
    a.maxTotalDeltaV === b.maxTotalDeltaV &&
    a.maxBurns === b.maxBurns &&
    a.preferredAxis === b.preferredAxis &&
    a.horizonHours === b.horizonHours
  )
}

export function ConstraintsPanel({ appliedConstraints, onApply, onManualSatelliteLoad }: ConstraintsPanelProps) {
  const [draft, setDraft] = useState<PlannerConstraints>(appliedConstraints)
  const [applying, setApplying] = useState(false)
  const [feedback, setFeedback] = useState<ApplyConstraintsResult | null>(null)

  const isDirty = useMemo(() => !constraintsEqual(draft, appliedConstraints), [draft, appliedConstraints])

  // Manual satellite state (defaults: 400km altitude LEO)
  const [manualRadius, setManualRadius] = useState("6771") // Earth radius + 400km
  const [manualSpeed, setManualSpeed] = useState("7670") // Circular orbit speed at 400km
  const [manualLoading, setManualLoading] = useState(false)
  const [manualFeedback, setManualFeedback] = useState<string | null>(null)

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const normalized: PlannerConstraints = {
      maxTotalDeltaV: Math.max(0, Number(draft.maxTotalDeltaV) || 0),
      maxBurns: draft.maxBurns === 2 ? 2 : 1,
      preferredAxis: draft.preferredAxis,
      horizonHours: Math.max(1, Math.round(Number(draft.horizonHours) || 1)),
    }

    setApplying(true)
    try {
      const result = await onApply(normalized)
      setDraft(normalized)
      setFeedback(result)
    } finally {
      setApplying(false)
    }
  }

  const onManualSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setManualLoading(true)
    setManualFeedback(null)

    try {
      const radiusKm = parseFloat(manualRadius)
      const speedMps = parseFloat(manualSpeed)

      if (isNaN(radiusKm) || isNaN(speedMps)) {
        setManualFeedback("Invalid radius or speed value")
        return
      }

      if (radiusKm < 6371 || radiusKm > 50000) {
        setManualFeedback("Radius must be between 6371 km (Earth surface) and 50000 km")
        return
      }

      const response = await fetch("http://localhost:8000/api/objects/manual/trajectory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          radius_km: radiusKm,
          speed_mps: speedMps,
          dt: 1 // 1 second timestep for smooth real-time animation
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      // Store trajectory in server state for conjunction detection
      await fetch("/api/manual-satellite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          times: data.times,
          positions: data.positions,
          velocities: data.velocities,
        }),
      })

      onManualSatelliteLoad?.(data)
      setManualFeedback("Manual satellite loaded!")
    } catch (error) {
      setManualFeedback("Failed to load manual satellite")
      console.error(error)
    } finally {
      setManualLoading(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto">
      <form className="space-y-3 rounded-md border border-border/70 bg-background/45 p-3" onSubmit={onSubmit}>
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Planner Constraints</p>

        <div className="space-y-1.5">
          <label htmlFor="max-dv" className="text-xs text-muted-foreground">Max total Δv (m/s)</label>
          <input
            id="max-dv"
            type="number"
            min={0}
            step="0.05"
            value={draft.maxTotalDeltaV}
            onChange={(event) => setDraft((prev) => ({ ...prev, maxTotalDeltaV: Number(event.target.value) }))}
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-primary/60"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="max-burns" className="text-xs text-muted-foreground">Max burns</label>
          <select
            id="max-burns"
            value={draft.maxBurns}
            onChange={(event) => setDraft((prev) => ({ ...prev, maxBurns: event.target.value === "2" ? 2 : 1 }))}
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-primary/60"
          >
            <option value="1">1</option>
            <option value="2">2</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="axis" className="text-xs text-muted-foreground">Preferred maneuver axis</label>
          <select
            id="axis"
            value={draft.preferredAxis}
            onChange={(event) =>
              setDraft((prev) => ({
                ...prev,
                preferredAxis: event.target.value as ManeuverAxis,
              }))
            }
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-primary/60"
          >
            <option value="along">Along-track</option>
            <option value="radial">Radial</option>
            <option value="cross">Cross-track</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="horizon" className="text-xs text-muted-foreground">Horizon hours</label>
          <input
            id="horizon"
            type="number"
            min={1}
            step={1}
            value={draft.horizonHours}
            onChange={(event) => setDraft((prev) => ({ ...prev, horizonHours: Number(event.target.value) }))}
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-primary/60"
          />
        </div>

        <button
          type="submit"
          disabled={applying || !isDirty}
          className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-emerald-500/45 bg-emerald-500/15 px-3 text-sm font-semibold text-emerald-300 transition-colors hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-55"
        >
          {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Apply
        </button>

        <p className="text-xs text-muted-foreground">
          {isDirty ? "Constraints changed. Replan occurs only after Apply." : "No pending changes."}
        </p>

        {feedback ? (
          <p className={`text-xs ${feedback.ok ? "text-emerald-300" : "text-amber-300"}`}>
            {feedback.message}
          </p>
        ) : null}
      </form>

      <form className="space-y-3 rounded-md border border-cyan-500/40 bg-cyan-500/5 p-3" onSubmit={onManualSubmit}>
        <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">Manual Satellite</p>

        <div className="space-y-1.5">
          <label htmlFor="manual-radius" className="text-xs text-muted-foreground">
            Radius (km from Earth center)
          </label>
          <input
            id="manual-radius"
            type="number"
            step="1"
            value={manualRadius}
            onChange={(e) => setManualRadius(e.target.value)}
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-cyan-500/60"
            placeholder="6771"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="manual-speed" className="text-xs text-muted-foreground">
            Speed (m/s)
          </label>
          <input
            id="manual-speed"
            type="number"
            step="1"
            value={manualSpeed}
            onChange={(e) => setManualSpeed(e.target.value)}
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-cyan-500/60"
            placeholder="7670"
          />
        </div>

        <button
          type="submit"
          disabled={manualLoading}
          className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-cyan-500/60 bg-cyan-500/20 text-sm font-semibold text-cyan-200 transition-colors hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-55"
        >
          {manualLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Load Manual Satellite
        </button>

        {manualFeedback ? <p className="text-xs text-cyan-300">{manualFeedback}</p> : null}
      </form>
    </div>
  )
}

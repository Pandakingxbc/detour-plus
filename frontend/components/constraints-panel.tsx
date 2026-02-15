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

  // Manual satellite state (defaults: 400km altitude LEO, equatorial)
  const [manualAltitude, setManualAltitude] = useState("400") // km above surface
  const [manualSpeed, setManualSpeed] = useState("7670") // m/s
  const [manualInclination, setManualInclination] = useState("0") // degrees
  const [manualRaan, setManualRaan] = useState("0") // degrees
  const [manualLoading, setManualLoading] = useState(false)
  const [manualFeedback, setManualFeedback] = useState<string | null>(null)
  const [manualSatelliteActive, setManualSatelliteActive] = useState(false)
  const [maneuvering, setManeuvering] = useState(false)

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
      const altitudeKm = parseFloat(manualAltitude)
      const speedMps = parseFloat(manualSpeed)
      const inclinationDeg = parseFloat(manualInclination)
      const raanDeg = parseFloat(manualRaan)

      if (isNaN(altitudeKm) || isNaN(speedMps) || isNaN(inclinationDeg) || isNaN(raanDeg)) {
        setManualFeedback("Invalid orbital parameter values")
        return
      }

      if (altitudeKm < 200 || altitudeKm > 40000) {
        setManualFeedback("Altitude must be between 200 km and 40,000 km")
        return
      }

      if (inclinationDeg < 0 || inclinationDeg > 180) {
        setManualFeedback("Inclination must be between 0° and 180°")
        return
      }

      const response = await fetch("/api/manual/trajectory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          altitude_km: altitudeKm,
          speed_mps: speedMps,
          inclination_deg: inclinationDeg,
          raan_deg: raanDeg % 360, // Normalize to 0-360
          dt: 1 // 1 second timestep for smooth real-time animation
        })
      })

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(errorBody?.detail ?? `HTTP ${response.status}`)
      }

      const data = await response.json()

      // Store state vectors + trajectory in server state for conjunction detection
      const persistResponse = await fetch("/api/manual-satellite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          position: data.initial_state.position,
          velocity: data.initial_state.velocity,
          epoch: data.initial_state.epoch,
          trajectory: data.trajectory,
        }),
      })
      if (!persistResponse.ok) {
        const errorBody = (await persistResponse.json().catch(() => null)) as { detail?: string } | null
        throw new Error(errorBody?.detail ?? "Failed to persist manual satellite state")
      }

      onManualSatelliteLoad?.(data.trajectory)
      setManualFeedback("Manual satellite loaded!")
      setManualSatelliteActive(true)
    } catch (error) {
      setManualFeedback(error instanceof Error ? error.message : "Failed to load manual satellite")
      console.error(error)
    } finally {
      setManualLoading(false)
    }
  }

  const applyManeuver = async (direction: "radial-out" | "radial-in" | "prograde" | "retrograde") => {
    setManeuvering(true)
    setManualFeedback(null)

    try {
      // Get current satellite state
      const stateResponse = await fetch("/api/manual-satellite-state")
      if (!stateResponse.ok) {
        throw new Error("Failed to get current satellite state")
      }
      const currentState = await stateResponse.json()

      // Apply maneuver with current state
      const response = await fetch("/api/manual/maneuver-from-state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          position: currentState.position,
          velocity: currentState.velocity,
          direction,
          delta_v_magnitude: 500.0, // 5 m/s per click
        }),
      })

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(errorBody?.detail ?? `HTTP ${response.status}`)
      }

      const data = await response.json()

      // Update server state with new trajectory
      const persistResponse = await fetch("/api/manual-satellite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          position: data.initial_state.position,
          velocity: data.initial_state.velocity,
          epoch: data.initial_state.epoch,
          trajectory: data.trajectory,
        }),
      })
      if (!persistResponse.ok) {
        const errorBody = (await persistResponse.json().catch(() => null)) as { detail?: string } | null
        throw new Error(errorBody?.detail ?? "Failed to persist manual satellite state")
      }

      // Update visualization
      onManualSatelliteLoad?.(data.trajectory)
      setManualFeedback(`Maneuver applied: ${direction}`)
    } catch (error) {
      setManualFeedback(error instanceof Error ? error.message : "Maneuver failed")
      console.error(error)
    } finally {
      setManeuvering(false)
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
        <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">Manual Satellite (3D Orbit)</p>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1.5">
            <label htmlFor="manual-altitude" className="text-xs text-muted-foreground">
              Altitude (km)
            </label>
            <input
              id="manual-altitude"
              type="number"
              step="10"
              value={manualAltitude}
              onChange={(e) => setManualAltitude(e.target.value)}
              className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-cyan-500/60"
              placeholder="400"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="manual-speed" className="text-xs text-muted-foreground">
              Speed (m/s)
            </label>
            <input
              id="manual-speed"
              type="number"
              step="10"
              value={manualSpeed}
              onChange={(e) => setManualSpeed(e.target.value)}
              className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-cyan-500/60"
              placeholder="7670"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1.5">
            <label htmlFor="manual-inclination" className="text-xs text-muted-foreground">
              Inclination (°)
            </label>
            <input
              id="manual-inclination"
              type="number"
              step="5"
              value={manualInclination}
              onChange={(e) => setManualInclination(e.target.value)}
              className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-cyan-500/60"
              placeholder="0"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="manual-raan" className="text-xs text-muted-foreground">
              RAAN (°)
            </label>
            <input
              id="manual-raan"
              type="number"
              step="15"
              value={manualRaan}
              onChange={(e) => setManualRaan(e.target.value)}
              className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm outline-none transition-colors focus:border-cyan-500/60"
              placeholder="0"
            />
          </div>
        </div>

        <p className="text-[10px] text-muted-foreground">
          Inclination: 0°=equatorial, 90°=polar • RAAN: orbit orientation (0-360°)
        </p>

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

      {manualSatelliteActive && (
        <div className="space-y-3 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300">Maneuver Controls</p>
          <p className="text-[10px] text-muted-foreground">
            Apply delta-v to change orbit (5 m/s per click)
          </p>

          <div className="flex flex-col items-center gap-2">
            {/* Up: Radial Out */}
            <button
              type="button"
              onClick={() => applyManeuver("radial-out")}
              disabled={maneuvering}
              className="flex h-10 w-10 items-center justify-center rounded-md border border-emerald-500/60 bg-emerald-500/20 text-emerald-200 transition-colors hover:bg-emerald-500/30 disabled:opacity-50"
              title="Radial Out (away from Earth)"
            >
              ↑
            </button>

            <div className="flex gap-2">
              {/* Left: Retrograde */}
              <button
                type="button"
                onClick={() => applyManeuver("retrograde")}
                disabled={maneuvering}
                className="flex h-10 w-10 items-center justify-center rounded-md border border-emerald-500/60 bg-emerald-500/20 text-emerald-200 transition-colors hover:bg-emerald-500/30 disabled:opacity-50"
                title="Retrograde (slow down)"
              >
                ←
              </button>

              <div className="flex h-10 w-10 items-center justify-center text-xs text-muted-foreground">
                {maneuvering ? "..." : "Δv"}
              </div>

              {/* Right: Prograde */}
              <button
                type="button"
                onClick={() => applyManeuver("prograde")}
                disabled={maneuvering}
                className="flex h-10 w-10 items-center justify-center rounded-md border border-emerald-500/60 bg-emerald-500/20 text-emerald-200 transition-colors hover:bg-emerald-500/30 disabled:opacity-50"
                title="Prograde (speed up)"
              >
                →
              </button>
            </div>

            {/* Down: Radial In */}
            <button
              type="button"
              onClick={() => applyManeuver("radial-in")}
              disabled={maneuvering}
              className="flex h-10 w-10 items-center justify-center rounded-md border border-emerald-500/60 bg-emerald-500/20 text-emerald-200 transition-colors hover:bg-emerald-500/30 disabled:opacity-50"
              title="Radial In (toward Earth)"
            >
              ↓
            </button>
          </div>

          <div className="text-[10px] text-muted-foreground space-y-0.5">
            <p>↑ Radial+ (away) • ↓ Radial- (toward)</p>
            <p>→ Prograde (speed up) • ← Retrograde (slow down)</p>
          </div>
        </div>
      )}
    </div>
  )
}

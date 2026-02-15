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

interface ConstraintsPanelProps {
  appliedConstraints: PlannerConstraints
  onApply: (next: PlannerConstraints) => Promise<ApplyConstraintsResult>
}

function constraintsEqual(a: PlannerConstraints, b: PlannerConstraints): boolean {
  return (
    a.maxTotalDeltaV === b.maxTotalDeltaV &&
    a.maxBurns === b.maxBurns &&
    a.preferredAxis === b.preferredAxis &&
    a.horizonHours === b.horizonHours
  )
}

export function ConstraintsPanel({ appliedConstraints, onApply }: ConstraintsPanelProps) {
  const [draft, setDraft] = useState<PlannerConstraints>(appliedConstraints)
  const [applying, setApplying] = useState(false)
  const [feedback, setFeedback] = useState<ApplyConstraintsResult | null>(null)

  const isDirty = useMemo(() => !constraintsEqual(draft, appliedConstraints), [draft, appliedConstraints])

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

  return (
    <form className="flex h-full min-h-0 flex-col gap-4" onSubmit={onSubmit}>
      <div className="space-y-3 rounded-md border border-border/70 bg-background/45 p-3">
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
      </div>

      <div className="mt-auto rounded-md border border-border/70 bg-background/45 p-3">
        <button
          type="submit"
          disabled={applying || !isDirty}
          className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-emerald-500/45 bg-emerald-500/15 px-3 text-sm font-semibold text-emerald-300 transition-colors hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-55"
        >
          {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Apply
        </button>

        <p className="mt-2 text-xs text-muted-foreground">
          {isDirty
            ? "Constraints changed. Replan occurs only after Apply."
            : "No pending changes."}
        </p>

        {feedback ? (
          <p className={`mt-2 text-xs ${feedback.ok ? "text-emerald-300" : "text-amber-300"}`}>
            {feedback.message}
          </p>
        ) : null}
      </div>
    </form>
  )
}

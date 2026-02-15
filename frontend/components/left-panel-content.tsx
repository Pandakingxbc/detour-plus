"use client"

import { FormEvent, useCallback, useEffect, useRef, useState } from "react"
import { Loader2, RefreshCw, Search } from "lucide-react"

const DEFAULT_NORAD = "25544"
const DEFAULT_MAX_ROWS = 8
const DEFAULT_FEED_POLL_MS = 5_000
const MANUAL_FEED_POLL_MS = 5_000

interface TargetResponse {
  noradId: number
  name: string
  objectType: string
  orbitClass: "LEO" | "MEO" | "GEO"
  altitudeKm: number
  inclinationDeg: number | null
  lastUpdatedUtc: string
  tleUpdatedUtc?: string
  tle: {
    line1: string
    line2: string
  }
}

export interface FeedEvent {
  eventId: string
  tcaUtc: string
  tcaInMinutes: number
  missKm: number
  risk: "LOW" | "MED" | "HIGH"
  secondaryNorad: number
}

interface FeedResponse {
  generatedAtUtc: string
  horizonHours: number
  stepSec: number
  events: FeedEvent[]
}

interface LeftPanelContentProps {
  onPrimaryIdChange?: (id: number) => void
  activePrimaryId?: number | null
  onRiskChange?: (risk: FeedEvent["risk"]) => void
  onFeedUpdate?: (events: FeedEvent[]) => void
}

function formatUtc(isoValue?: string | null): string {
  if (!isoValue) return "--"
  const date = new Date(isoValue)
  if (Number.isNaN(date.getTime())) return "--"

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

function formatRelativeMinutes(minutes: number): string {
  if (!Number.isFinite(minutes)) return "n/a"
  if (minutes <= 0) return "now"
  if (minutes < 60) return `in ${Math.round(minutes)}m`

  const hours = Math.floor(minutes / 60)
  const rem = Math.round(minutes % 60)
  return `in ${hours}h ${rem}m`
}

function riskClassName(risk: FeedEvent["risk"]): string {
  if (risk === "HIGH") return "border-red-500/50 bg-red-500/15 text-red-300"
  if (risk === "MED") return "border-amber-500/50 bg-amber-500/15 text-amber-200"
  return "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
}

function highestRiskFromEvents(events: FeedEvent[]): FeedEvent["risk"] {
  if (events.some((event) => event.risk === "HIGH")) return "HIGH"
  if (events.some((event) => event.risk === "MED")) return "MED"
  return "LOW"
}

export function LeftPanelContent({ onPrimaryIdChange, activePrimaryId, onRiskChange, onFeedUpdate }: LeftPanelContentProps) {
  const [inputNorad, setInputNorad] = useState(DEFAULT_NORAD)
  const [activeNorad, setActiveNorad] = useState<number | null>(null)

  // Sync internal state with prop
  useEffect(() => {
    if (activePrimaryId !== undefined) {
      setActiveNorad(activePrimaryId)
    }
  }, [activePrimaryId])

  const [target, setTarget] = useState<TargetResponse | null>(null)
  const [feed, setFeed] = useState<FeedResponse | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [feedLoading, setFeedLoading] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!toastMessage) return

    const timer = window.setTimeout(() => setToastMessage(null), 2800)
    return () => window.clearTimeout(timer)
  }, [toastMessage])

  const loadFeed = useCallback(async (noradId: number, options?: { forceRefresh?: boolean }) => {
    setFeedLoading(true)

    try {
      const query = new URLSearchParams({
        norad: String(noradId),
        maxEvents: String(DEFAULT_MAX_ROWS),
      })
      if (options?.forceRefresh) {
        query.set("force", "1")
      }

      const response = await fetch(`/api/feed?${query.toString()}`, {
        cache: "no-store",
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `Feed request failed (${response.status})`)
      }

      const data = (await response.json()) as FeedResponse
      setFeed(data)
      onRiskChange?.(highestRiskFromEvents(data.events))
      onFeedUpdate?.(data.events)
      if (!data.events.length) {
        setToastMessage(noradId === -1
          ? "No debris threats detected for manual satellite."
          : "No conjunction events found in the selected horizon.")
      }
    } catch (err) {
      setFeed(null)
      onRiskChange?.("LOW")
      setToastMessage(err instanceof Error ? err.message : "Live conjunction feed unavailable.")
    } finally {
      setFeedLoading(false)
    }
  }, [onRiskChange, onFeedUpdate])

  const loadTarget = useCallback(
    async (noradId: number) => {
      setDetailsLoading(true)
      setActiveNorad(noradId)
      onPrimaryIdChange?.(noradId)

      try {
        const response = await fetch(`/api/target?norad=${noradId}`)
        if (!response.ok) {
          throw new Error(`Target request failed (${response.status})`)
        }

        const data = (await response.json()) as TargetResponse
        setTarget(data)
      } catch {
        setTarget(null)
        setToastMessage("Unable to load target details.")
      } finally {
        setDetailsLoading(false)
      }

      void loadFeed(noradId)
    },
    [loadFeed, onPrimaryIdChange]
  )

  // Keep a ref so the mount effect always calls the latest loadTarget
  // without depending on its identity (avoids re-fires from callback churn).
  const loadTargetRef = useRef(loadTarget)
  loadTargetRef.current = loadTarget

  useEffect(() => {
    const defaultId = Number(DEFAULT_NORAD)
    void loadTargetRef.current(defaultId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load feed when activeNorad changes (including manual satellite)
  useEffect(() => {
    if (activeNorad !== null && activeNorad !== Number(DEFAULT_NORAD)) {
      void loadFeed(activeNorad)
    }
  }, [activeNorad, loadFeed])

  useEffect(() => {
    if (!activeNorad) return

    const pollMs = activeNorad === -1 ? MANUAL_FEED_POLL_MS : DEFAULT_FEED_POLL_MS
    const interval = window.setInterval(() => {
      void loadFeed(activeNorad)
    }, pollMs)

    return () => window.clearInterval(interval)
  }, [activeNorad, loadFeed])

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const parsed = Number(inputNorad.trim())
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setToastMessage("Enter a valid NORAD ID.")
      return
    }

    void loadTarget(parsed)
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col gap-4">
      {toastMessage ? (
        <div className="pointer-events-none absolute right-0 top-0 z-20 rounded-md border border-amber-500/45 bg-black/85 px-3 py-2 text-xs text-amber-200 shadow-lg backdrop-blur-sm">
          {toastMessage}
        </div>
      ) : null}

      <form className="space-y-2" onSubmit={onSubmit}>
        <label htmlFor="norad-id" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          NORAD ID
        </label>
        <div className="flex items-center gap-2">
          <input
            id="norad-id"
            type="text"
            inputMode="numeric"
            value={inputNorad}
            onChange={(event) => setInputNorad(event.target.value)}
            className="h-9 w-full rounded-md border border-border/80 bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus:border-primary/60"
            placeholder="e.g. 25544"
          />
          <button
            type="submit"
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border/80 bg-background/70 px-3 text-xs font-semibold uppercase tracking-wide text-foreground transition-colors hover:bg-accent/60"
          >
            {detailsLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            Load
          </button>
        </div>
      </form>

      {activeNorad !== -1 ? (
        <section className="rounded-md border border-border/70 bg-background/45 p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Live Target Details</p>

          <dl className="space-y-2 text-sm">
            <div className="flex items-start justify-between gap-3">
              <dt className="text-muted-foreground">Name / Type</dt>
              <dd className="text-right text-foreground">
                {target ? `${target.name || "Unknown"} (${target.objectType || "unknown"})` : "--"}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted-foreground">Orbit Class</dt>
              <dd>{target?.orbitClass ?? "--"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted-foreground">Altitude Estimate</dt>
              <dd>{target ? `${target.altitudeKm.toFixed(2)} km` : "--"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted-foreground">Inclination Estimate</dt>
              <dd>{target?.inclinationDeg !== null && target?.inclinationDeg !== undefined ? `${target.inclinationDeg.toFixed(2)}°` : "--"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted-foreground">Last Updated</dt>
              <dd>{formatUtc(target?.lastUpdatedUtc)}</dd>
            </div>
          </dl>
        </section>
      ) : (
        <section className="rounded-md border border-cyan-500/40 bg-cyan-500/5 p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-cyan-300">Manual Satellite Active</p>
          <p className="text-xs text-muted-foreground">
            Conjunction feed shows real debris threats to your manual satellite.
          </p>
        </section>
      )}

      <section className="min-h-0 flex flex-1 flex-col rounded-md border border-border/70 bg-background/45 p-3">
        <div className="mb-2 shrink-0 flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Live Conjunction Feed</p>
          <button
            type="button"
            onClick={() => {
              if (activeNorad) {
                void loadFeed(activeNorad, { forceRefresh: true })
              }
            }}
            className="inline-flex h-7 items-center gap-1 rounded-md border border-border/70 px-2 text-[11px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
          >
            <RefreshCw className={feedLoading ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
            Refresh
          </button>
        </div>

        <div className="scrollbar-hidden min-h-0 flex-1 overflow-auto rounded-md border border-border/60">
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 bg-black text-muted-foreground">
              <tr>
                <th className="px-2.5 py-2 text-left font-medium">TCA</th>
                <th className="px-2.5 py-2 text-left font-medium">Miss</th>
                <th className="px-2.5 py-2 text-left font-medium">Risk</th>
                <th className="px-2.5 py-2 text-left font-medium">Secondary</th>
              </tr>
            </thead>
            <tbody>
              {(feed?.events ?? []).slice(0, DEFAULT_MAX_ROWS).map((event) => (
                <tr key={event.eventId} className="border-t border-border/50">
                  <td className="px-2.5 py-2 text-foreground">{formatRelativeMinutes(event.tcaInMinutes)}</td>
                  <td className="px-2.5 py-2 text-foreground">{event.missKm.toFixed(2)} km</td>
                  <td className="px-2.5 py-2">
                    <span className={`rounded-md border px-1.5 py-0.5 font-semibold uppercase ${riskClassName(event.risk)}`}>
                      {event.risk}
                    </span>
                  </td>
                  <td className="px-2.5 py-2 text-foreground">{event.secondaryNorad}</td>
                </tr>
              ))}
              {!feed?.events?.length ? (
                <tr className="border-t border-border/50">
                  <td className="px-2.5 py-3 text-muted-foreground" colSpan={4}>
                    Feed not available yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

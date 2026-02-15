"use client"

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react"
import { Loader2, RefreshCw, Search } from "lucide-react"

const DEFAULT_NORAD = "25544"
const DEFAULT_FEED_ROWS = 8

interface OrbitalObjectResponse {
  norad_id: number
  name: string
  position: number[]
  velocity: number[]
  epoch?: string | null
  alt_km: number
  object_type: string
}

interface ConjunctionEventResponse {
  event_id: string
  secondary_id: number
  tca_epoch?: string | null
  tca_offset_sec: number
  miss_distance_m: number
  risk_level: string
}

interface LeftPanelContentProps {
  onPrimaryIdChange?: (id: number) => void
}

const MOCK_FEED: ConjunctionEventResponse[] = [
  {
    event_id: "mock-1",
    secondary_id: 52731,
    tca_offset_sec: 1980,
    miss_distance_m: 1520,
    risk_level: "medium",
  },
  {
    event_id: "mock-2",
    secondary_id: 43417,
    tca_offset_sec: 3410,
    miss_distance_m: 2640,
    risk_level: "low",
  },
  {
    event_id: "mock-3",
    secondary_id: 38104,
    tca_offset_sec: 5150,
    miss_distance_m: 880,
    risk_level: "high",
  },
  {
    event_id: "mock-4",
    secondary_id: 56121,
    tca_offset_sec: 7290,
    miss_distance_m: 4100,
    risk_level: "low",
  },
  {
    event_id: "mock-5",
    secondary_id: 25987,
    tca_offset_sec: 10160,
    miss_distance_m: 1360,
    risk_level: "medium",
  },
]

function classifyOrbit(altKm: number): "LEO" | "MEO" | "GEO" {
  if (!Number.isFinite(altKm)) return "LEO"
  if (altKm < 2000) return "LEO"
  if (altKm < 35_786) return "MEO"
  return "GEO"
}

function estimateInclinationDeg(position: number[], velocity: number[]): number | null {
  if (position.length !== 3 || velocity.length !== 3) return null
  const [rx, ry, rz] = position
  const [vx, vy, vz] = velocity
  if (![rx, ry, rz, vx, vy, vz].every(Number.isFinite)) return null

  const hx = ry * vz - rz * vy
  const hy = rz * vx - rx * vz
  const hz = rx * vy - ry * vx
  const hNorm = Math.sqrt(hx * hx + hy * hy + hz * hz)
  if (!Number.isFinite(hNorm) || hNorm === 0) return null

  const cosI = Math.min(1, Math.max(-1, hz / hNorm))
  return (Math.acos(cosI) * 180) / Math.PI
}

function formatLastUpdated(isoValue?: string | null): string {
  const date = isoValue ? new Date(isoValue) : new Date()
  if (Number.isNaN(date.getTime())) return "Unavailable"

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return "n/a"
  if (seconds <= 0) return "now"

  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)

  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m`
  return `${total}s`
}

function tcaLabel(event: ConjunctionEventResponse): string {
  if (Number.isFinite(event.tca_offset_sec)) {
    return `in ${formatDuration(event.tca_offset_sec)}`
  }

  if (event.tca_epoch) {
    const date = new Date(event.tca_epoch)
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(date)
    }
  }

  return "n/a"
}

function riskClassName(risk: string): string {
  const key = risk.toLowerCase()
  if (key === "high") return "border-red-500/50 bg-red-500/15 text-red-300"
  if (key === "medium") return "border-amber-500/50 bg-amber-500/15 text-amber-200"
  return "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
}

export function LeftPanelContent({ onPrimaryIdChange }: LeftPanelContentProps) {
  const [inputNorad, setInputNorad] = useState(DEFAULT_NORAD)
  const [activeNorad, setActiveNorad] = useState<number | null>(null)
  const [details, setDetails] = useState<OrbitalObjectResponse | null>(null)
  const [feed, setFeed] = useState<ConjunctionEventResponse[]>(MOCK_FEED)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [feedLoading, setFeedLoading] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"

  useEffect(() => {
    if (!toastMessage) return

    const timer = window.setTimeout(() => {
      setToastMessage(null)
    }, 2800)

    return () => window.clearTimeout(timer)
  }, [toastMessage])

  const loadFeed = useCallback(
    async (primaryId: number) => {
      setFeedLoading(true)

      try {
        const response = await fetch(
          `${apiBase}/conjunctions?primary_id=${primaryId}&lookahead=86400&threshold_km=50&max_objects=250`
        )

        if (!response.ok) {
          throw new Error(`Feed request failed (${response.status})`)
        }

        const events = (await response.json()) as ConjunctionEventResponse[]
        if (events.length > 0) {
          setFeed(events.slice(0, DEFAULT_FEED_ROWS))
        } else {
          setFeed(MOCK_FEED)
          setToastMessage("No conjunctions returned yet. Showing demo feed.")
        }
      } catch {
        setFeed(MOCK_FEED)
        setToastMessage("Live feed unavailable. Showing demo feed.")
      } finally {
        setFeedLoading(false)
      }
    },
    [apiBase]
  )

  const loadTarget = useCallback(
    async (noradId: number) => {
      setDetailsLoading(true)
      setActiveNorad(noradId)
      onPrimaryIdChange?.(noradId)

      try {
        const response = await fetch(`${apiBase}/objects/${noradId}`)
        if (!response.ok) {
          throw new Error(`Object request failed (${response.status})`)
        }

        const data = (await response.json()) as OrbitalObjectResponse
        setDetails(data)
      } catch {
        setDetails(null)
        setToastMessage("Unable to load object details from backend.")
      } finally {
        setDetailsLoading(false)
      }

      void loadFeed(noradId)
    },
    [apiBase, loadFeed, onPrimaryIdChange]
  )

  useEffect(() => {
    const defaultId = Number(DEFAULT_NORAD)
    void loadTarget(defaultId)
  }, [loadTarget])

  useEffect(() => {
    if (!activeNorad) return

    const interval = window.setInterval(() => {
      void loadFeed(activeNorad)
    }, 30_000)

    return () => window.clearInterval(interval)
  }, [activeNorad, loadFeed])

  const inclination = useMemo(() => {
    if (!details) return null
    return estimateInclinationDeg(details.position, details.velocity)
  }, [details])

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

      <section className="rounded-md border border-border/70 bg-background/45 p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Live Target Details</p>

        <dl className="space-y-2 text-sm">
          <div className="flex items-start justify-between gap-3">
            <dt className="text-muted-foreground">Name / Type</dt>
            <dd className="text-right text-foreground">
              {details ? `${details.name || "Unknown"} (${details.object_type || "unknown"})` : "--"}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Orbit Class</dt>
            <dd>{details ? classifyOrbit(details.alt_km) : "--"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Altitude Estimate</dt>
            <dd>{details ? `${details.alt_km.toFixed(1)} km` : "--"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Inclination Estimate</dt>
            <dd>{inclination !== null ? `${inclination.toFixed(2)}°` : "--"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Last Updated</dt>
            <dd>{details ? formatLastUpdated(details.epoch) : "--"}</dd>
          </div>
        </dl>
      </section>

      <section className="min-h-0 flex-1 rounded-md border border-border/70 bg-background/45 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Live CDM / Conjunction Feed</p>
          <button
            type="button"
            onClick={() => {
              if (activeNorad) {
                void loadFeed(activeNorad)
              }
            }}
            className="inline-flex h-7 items-center gap-1 rounded-md border border-border/70 px-2 text-[11px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
          >
            <RefreshCw className={feedLoading ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
            Refresh
          </button>
        </div>

        <div className="max-h-[46vh] overflow-auto rounded-md border border-border/60">
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 bg-black/60 text-muted-foreground">
              <tr>
                <th className="px-2.5 py-2 text-left font-medium">TCA</th>
                <th className="px-2.5 py-2 text-left font-medium">Miss</th>
                <th className="px-2.5 py-2 text-left font-medium">Risk</th>
                <th className="px-2.5 py-2 text-left font-medium">Secondary</th>
              </tr>
            </thead>
            <tbody>
              {feed.slice(0, DEFAULT_FEED_ROWS).map((event) => (
                <tr key={event.event_id} className="border-t border-border/50">
                  <td className="px-2.5 py-2 text-foreground">{tcaLabel(event)}</td>
                  <td className="px-2.5 py-2 text-foreground">{(event.miss_distance_m / 1000).toFixed(2)} km</td>
                  <td className="px-2.5 py-2">
                    <span className={`rounded-md border px-1.5 py-0.5 font-semibold uppercase ${riskClassName(event.risk_level)}`}>
                      {event.risk_level}
                    </span>
                  </td>
                  <td className="px-2.5 py-2 text-foreground">{event.secondary_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </section>
    </div>
  )
}

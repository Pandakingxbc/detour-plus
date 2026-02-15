"use client"

import Image from "next/image"
import { useEffect, useState } from "react"
import { Crosshair, Loader2, X } from "lucide-react"

import { Badge } from "@/components/ui/badge"

type RiskLevel = "LOW" | "MED" | "HIGH"

function formatTimestamp(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

interface DashboardHeaderProps {
  riskLevel?: RiskLevel
  onRunScenario?: () => void
  simLoading?: boolean
  simActive?: boolean
  onExitSimulation?: () => void
}

function riskBadgeClassName(riskLevel: RiskLevel): string {
  if (riskLevel === "HIGH") {
    return "border-red-500/55 bg-red-500/20 text-red-300"
  }
  if (riskLevel === "MED") {
    return "border-amber-500/55 bg-amber-500/20 text-amber-200"
  }
  return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
}

export function DashboardHeader({
  riskLevel = "LOW",
  onRunScenario,
  simLoading = false,
  simActive = false,
  onExitSimulation,
}: DashboardHeaderProps) {
  const [timestamp, setTimestamp] = useState("--:--:--")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    const tick = () => setTimestamp(formatTimestamp(new Date()))
    tick()

    const interval = window.setInterval(() => {
      tick()
    }, 1000)

    return () => window.clearInterval(interval)
  }, [])

  return (
    <header className="w-full rounded-xl border border-border/80 bg-card/80 px-6 py-3 shadow-sm backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Image
          src="/de.png"
          alt="Detour logo"
          width={180}
          height={56}
          priority
          className="h-10 w-auto"
        />
        <div className="flex items-center gap-5">
          {simActive ? (
            <button
              onClick={onExitSimulation}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-500/45 bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-300 transition hover:bg-red-500/25"
            >
              <X className="h-3.5 w-3.5" />
              Exit Simulation
            </button>
          ) : (
            <button
              onClick={() => onRunScenario?.()}
              disabled={simLoading}
              className="inline-flex items-center gap-1.5 rounded-md border border-cyan-500/45 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {simLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Crosshair className="h-3.5 w-3.5" />
              )}
              {simLoading ? "Loading..." : "Run Simulation"}
            </button>
          )}

          <Badge variant="outline" className={`rounded-md px-3 py-1 ${riskBadgeClassName(riskLevel)}`}>
            RISK: {riskLevel}
          </Badge>
          <p className="text-sm text-muted-foreground">
            Last updated:{" "}
            <span className="font-mono text-foreground">
              {mounted ? timestamp : "--:--:--"}
            </span>
          </p>
        </div>
      </div>
    </header>
  )
}

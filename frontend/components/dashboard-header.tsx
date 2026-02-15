"use client"

import Image from "next/image"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"

function formatTimestamp(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

export function DashboardHeader() {
  const [timestamp, setTimestamp] = useState("--:--:--")

  useEffect(() => {
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
          <Badge variant="success" className="rounded-md px-3 py-1">
            RISK: LOW
          </Badge>
          <p className="text-sm text-muted-foreground">
            Last updated:{" "}
            <span className="font-mono text-foreground">{timestamp}</span>
          </p>
        </div>
      </div>
    </header>
  )
}

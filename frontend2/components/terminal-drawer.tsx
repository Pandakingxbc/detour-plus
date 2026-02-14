"use client"

import { ChevronUp } from "lucide-react"

import { cn } from "@/lib/utils"

interface TerminalDrawerProps {
  isOpen: boolean
  onToggle: () => void
}

const MOCK_LOGS = [
  "[13:14:08] agent.monitor: scanning conjunction feed...",
  "[13:14:10] tool.screen: 42 events in horizon, highest risk=HIGH",
  "[13:14:11] planner: evaluating candidate maneuvers",
  "[13:14:12] planner: selected plan burn-03 (delta-v 0.18 m/s)",
  "[13:14:13] sim: post-maneuver miss distance +1.27 km",
]

export function TerminalDrawer({ isOpen, onToggle }: TerminalDrawerProps) {
  return (
    <div className="pointer-events-auto mx-auto w-full max-w-[1600px]">
      <div
        className={cn(
          "overflow-hidden rounded-t-xl border border-border/80 bg-black/85 shadow-2xl transition-[max-height] duration-500 ease-in-out",
          isOpen ? "max-h-72" : "max-h-11"
        )}
      >
        <button
          type="button"
          onClick={onToggle}
          className="flex h-11 w-full items-center justify-between px-4 text-xs font-semibold uppercase tracking-wide text-gray-300 hover:bg-white/5"
        >
          <span>Agent Terminal</span>
          <ChevronUp className={cn("h-4 w-4 transition-transform duration-300", isOpen && "rotate-180")} />
        </button>

        <div className="h-60 border-t border-border/70 px-4 py-3">
          <div className="h-full overflow-auto rounded-md bg-black/50 p-3 font-mono text-xs text-emerald-300">
            {MOCK_LOGS.map((log) => (
              <div key={log} className="mb-1 last:mb-0">
                <span className="text-gray-500">$</span> {log}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

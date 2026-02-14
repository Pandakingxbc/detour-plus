"use client"

import { useState } from "react"

import { DashboardHeader } from "@/components/dashboard-header"
import { GlobeView } from "@/components/globe-view"
import { SidePanel } from "@/components/side-panel"
import { TerminalDrawer } from "@/components/terminal-drawer"
import { cn } from "@/lib/utils"

export function DashboardShell() {
  const [terminalOpen, setTerminalOpen] = useState(false)

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-background text-foreground">
      <GlobeView compacted={terminalOpen} />

      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 p-6">
        <div className="pointer-events-auto mx-auto w-full max-w-[1600px]">
          <DashboardHeader />
        </div>
      </div>

      <div
        className={cn(
          "pointer-events-none absolute inset-0 z-10 p-6 pt-28 transition-[padding-bottom] duration-500 ease-in-out",
          terminalOpen ? "pb-72" : "pb-16"
        )}
      >
        <div className="mx-auto grid h-full w-full max-w-[1600px] grid-cols-1 gap-4 lg:grid-cols-[22rem_1fr_22rem]">
          <SidePanel title="Left Panel" subtitle="Placeholder panel for controls and context.">
            <p className="text-sm text-muted-foreground">
              This panel is floating above the globe.
            </p>
          </SidePanel>

          <div className="hidden lg:block" />

          <SidePanel title="Right Panel" subtitle="Placeholder panel for feed and planning.">
            <p className="text-sm text-muted-foreground">
              This panel is floating above the globe.
            </p>
          </SidePanel>
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 px-6">
        <TerminalDrawer isOpen={terminalOpen} onToggle={() => setTerminalOpen((open) => !open)} />
      </div>
    </main>
  )
}

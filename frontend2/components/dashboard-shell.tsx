"use client"

import { type CSSProperties, useMemo, useState } from "react"
import { Activity, SlidersHorizontal } from "lucide-react"

import { DashboardHeader } from "@/components/dashboard-header"
import { GlobeView } from "@/components/globe-view"
import { SidePanel } from "@/components/side-panel"
import { TerminalDrawer } from "@/components/terminal-drawer"

export function DashboardShell() {
  const [terminalOpen, setTerminalOpen] = useState(false)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)

  const panelColumns = useMemo(() => {
    const leftWidth = leftCollapsed ? "4.75rem" : "22rem"
    const rightWidth = rightCollapsed ? "4.75rem" : "22rem"
    return `${leftWidth} minmax(0, 1fr) ${rightWidth}`
  }, [leftCollapsed, rightCollapsed])

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-background text-foreground">
      <GlobeView compacted={terminalOpen} />

      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 p-6">
        <div className="pointer-events-auto mx-auto w-full max-w-[1600px]">
          <DashboardHeader />
        </div>
      </div>

      <div className="pointer-events-none absolute inset-0 z-10 p-6 pt-28 pb-[3.25rem]">
        <div
          className="mx-auto grid h-full w-full max-w-[1600px] grid-cols-1 gap-4 transition-[grid-template-columns] duration-500 ease-in-out lg:[grid-template-columns:var(--panel-cols)]"
          style={{ "--panel-cols": panelColumns } as CSSProperties}
        >
          <SidePanel
            side="left"
            collapsed={leftCollapsed}
            onToggle={() => setLeftCollapsed((value) => !value)}
            icon={Activity}
            title="Left Panel"
            subtitle="Placeholder panel for controls and context."
          >
            <p className="text-sm text-muted-foreground">
              This panel is floating above the globe.
            </p>
          </SidePanel>

          <div className="hidden lg:block" />

          <SidePanel
            side="right"
            collapsed={rightCollapsed}
            onToggle={() => setRightCollapsed((value) => !value)}
            icon={SlidersHorizontal}
            title="Right Panel"
            subtitle="Placeholder panel for feed and planning."
          >
            <p className="text-sm text-muted-foreground">
              This panel is floating above the globe.
            </p>
          </SidePanel>
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 px-6">
        <div
          className="mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-4 transition-[grid-template-columns] duration-500 ease-in-out lg:[grid-template-columns:var(--panel-cols)]"
          style={{ "--panel-cols": panelColumns } as CSSProperties}
        >
          <div className="hidden lg:block" />
          <TerminalDrawer
            className="mx-auto w-full"
            isOpen={terminalOpen}
            onToggle={() => setTerminalOpen((open) => !open)}
          />
          <div className="hidden lg:block" />
        </div>
      </div>
    </main>
  )
}

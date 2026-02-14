import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

interface SidePanelProps {
  title: string
  subtitle?: string
  children?: ReactNode
  className?: string
}

export function SidePanel({ title, subtitle, children, className }: SidePanelProps) {
  return (
    <section
      className={cn(
        "pointer-events-auto flex h-full min-h-[300px] flex-col rounded-xl border border-border/80 bg-card/70 p-4 shadow-sm backdrop-blur-md",
        className
      )}
    >
      <header className="mb-3 border-b border-border/70 pb-3">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
      </header>

      <div className="min-h-0 flex-1">{children}</div>
    </section>
  )
}

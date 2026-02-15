import type { ReactNode } from "react"
import { ChevronLeft, ChevronRight, type LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

interface SidePanelProps {
  side: "left" | "right"
  collapsed?: boolean
  onToggle: () => void
  icon: LucideIcon
  title: string
  subtitle?: string
  children?: ReactNode
  className?: string
}

export function SidePanel({
  side,
  collapsed = false,
  onToggle,
  icon: PanelIcon,
  title,
  subtitle,
  children,
  className,
}: SidePanelProps) {
  const isLeft = side === "left"
  const ToggleIcon = isLeft
    ? (collapsed ? ChevronRight : ChevronLeft)
    : (collapsed ? ChevronLeft : ChevronRight)
  const edgeCornerClass = isLeft
    ? "rounded-l-sm rounded-r-xl"
    : "rounded-r-sm rounded-l-xl"
  const expandLabel = isLeft ? "Expand left panel" : "Expand right panel"
  const collapseLabel = isLeft ? "Collapse left panel" : "Collapse right panel"

  return (
    <section
      className={cn(
        "pointer-events-auto relative flex h-full min-h-[300px] flex-col overflow-hidden border border-border/80 bg-card/70 shadow-sm backdrop-blur-md transition-all duration-500 ease-in-out",
        edgeCornerClass,
        className
      )}
    >
      <header className={cn("border-b border-border/70", collapsed ? "px-2.5 py-2.5" : "px-4 py-3.5")}>
        {collapsed ? (
          isLeft ? (
            <div className="flex items-center justify-start gap-2.5">
              <PanelIcon className="h-4 w-4 shrink-0 text-foreground/90" />
              <button
                type="button"
                onClick={onToggle}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border/80 bg-background/60 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
                aria-label={expandLabel}
              >
                <ToggleIcon className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={onToggle}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border/80 bg-background/60 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
                aria-label={expandLabel}
              >
                <ToggleIcon className="h-4 w-4" />
              </button>
              <PanelIcon className="h-4 w-4 shrink-0 text-foreground/90" />
            </div>
          )
        ) : isLeft ? (
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-2.5">
              <PanelIcon className="h-4 w-4 shrink-0 text-foreground/90" />
              <h2 className="truncate text-lg font-semibold text-foreground">{title}</h2>
            </div>
            <button
              type="button"
              onClick={onToggle}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border/80 bg-background/60 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
              aria-label={collapseLabel}
            >
              <ToggleIcon className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex w-full items-center justify-between gap-4">
            <button
              type="button"
              onClick={onToggle}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border/80 bg-background/60 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
              aria-label={collapseLabel}
            >
              <ToggleIcon className="h-4 w-4" />
            </button>
            <div className="flex min-w-0 items-center gap-2.5">
              <h2 className="truncate text-lg font-semibold text-foreground">{title}</h2>
              <PanelIcon className="h-4 w-4 shrink-0 text-foreground/90" />
            </div>
          </div>
        )}
      </header>

      {!collapsed ? (
        <div className="min-h-0 flex-1 p-4">
          {subtitle ? <p className="mb-4 text-sm text-muted-foreground">{subtitle}</p> : null}
          {children}
        </div>
      ) : null}
    </section>
  )
}

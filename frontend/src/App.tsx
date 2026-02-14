import { useEffect, useMemo, useState } from 'react'
import Globe from './components/Globe'
import ConjunctionPanel from './components/ConjunctionPanel'
import ManeuverPanel from './components/ManeuverPanel'
import { useStore, type ConjunctionEvent } from './store/useStore'
import { useApi } from './hooks/useApi'
import { Badge } from '@/components/ui/badge'

function riskRank(level: string): number {
  switch (level.toLowerCase()) {
    case 'critical': return 4
    case 'high': return 3
    case 'medium': return 2
    default: return 1
  }
}

function sortByPriority(a: ConjunctionEvent, b: ConjunctionEvent): number {
  const riskDelta = riskRank(b.risk_level) - riskRank(a.risk_level)
  if (riskDelta !== 0) return riskDelta
  return a.tca_offset_sec - b.tca_offset_sec
}

function riskDisplay(level: string | null): 'LOW' | 'MED' | 'HIGH' {
  if (!level) return 'LOW'
  const normalized = level.toLowerCase()
  if (normalized === 'critical' || normalized === 'high') return 'HIGH'
  if (normalized === 'medium') return 'MED'
  return 'LOW'
}

function riskClass(label: 'LOW' | 'MED' | 'HIGH'): string {
  switch (label) {
    case 'HIGH': return 'border-red-500/50 bg-red-500/15 text-red-300'
    case 'MED': return 'border-yellow-500/50 bg-yellow-500/15 text-yellow-300'
    default: return 'border-green-500/50 bg-green-500/15 text-green-300'
  }
}

export default function App() {
  const loading = useStore(s => s.loading)
  const catalogStatus = useStore(s => s.catalogStatus)
  const conjunctions = useStore(s => s.conjunctions)
  const selectedEvent = useStore(s => s.selectedEvent)
  const planRiskLevel = useStore(s => s.planRiskLevel)
  const setSelectedEvent = useStore(s => s.setSelectedEvent)
  const setPlanRiskLevel = useStore(s => s.setPlanRiskLevel)
  const { loadObjects, loadCatalogStatus } = useApi()
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    loadCatalogStatus()
    loadObjects(10000)

    const interval = setInterval(loadCatalogStatus, 30000)
    return () => clearInterval(interval)
  }, [loadCatalogStatus, loadObjects])

  useEffect(() => {
    if (conjunctions.length === 0) {
      setSelectedEvent(null)
      return
    }

    const nextThreat = [...conjunctions].sort(sortByPriority)[0]
    if (selectedEvent?.event_id !== nextThreat.event_id) {
      setSelectedEvent(nextThreat)
      setPlanRiskLevel(null)
    }
    setLastUpdate(new Date())
  }, [conjunctions, selectedEvent?.event_id, setPlanRiskLevel, setSelectedEvent])

  const topRisk = riskDisplay(planRiskLevel ?? selectedEvent?.risk_level ?? null)

  const activeThreatLabel = useMemo(() => {
    if (!selectedEvent) return 'None'
    return `${selectedEvent.event_id} | TCA ${selectedEvent.tca_offset_sec.toFixed(0)}s`
  }, [selectedEvent])

  const updatedLabel = useMemo(() => {
    if (lastUpdate) return lastUpdate.toLocaleTimeString()
    if (catalogStatus?.last_refresh) return new Date(catalogStatus.last_refresh).toLocaleTimeString()
    return '---'
  }, [catalogStatus?.last_refresh, lastUpdate])

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b bg-card/90 px-4 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold tracking-tight text-primary">DETOUR</h1>
          <Badge variant="outline" className={riskClass(topRisk)}>
            RISK: {topRisk}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-mono text-foreground">
            Active Threat: {activeThreatLabel}
          </Badge>
          <Badge variant="outline" className="font-mono">
            Last update: {updatedLabel}
          </Badge>
          {loading && (
            <Badge variant="secondary" className="gap-1 text-primary">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
              Processing
            </Badge>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[23rem_1fr_36rem] lg:grid-cols-[23rem_1fr_28rem] lg:grid-rows-1">
        <aside className="min-h-0 overflow-y-auto border-b bg-card/40 lg:border-b-0 lg:border-r">
          <ConjunctionPanel />
        </aside>

        <main className="relative min-h-0">
          <Globe />
        </main>

        <aside className="min-h-0 overflow-hidden border-t bg-card/40 lg:border-l lg:border-t-0">
          <ManeuverPanel />
        </aside>
      </div>
    </div>
  )
}

import { useEffect } from 'react'
import Globe from './components/Globe'
import ConjunctionPanel from './components/ConjunctionPanel'
import EventDetail from './components/EventDetail'
import ManeuverPanel from './components/ManeuverPanel'
import { useStore } from './store/useStore'
import { useApi } from './hooks/useApi'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

export default function App() {
  const loading = useStore(s => s.loading)
  const catalogStatus = useStore(s => s.catalogStatus)
  const objects = useStore(s => s.objects)
  const { loadObjects, loadCatalogStatus } = useApi()

  useEffect(() => {
    // Initial load
    loadCatalogStatus()
    loadObjects(10000)

    // Poll catalog status
    const interval = setInterval(loadCatalogStatus, 30000)
    return () => clearInterval(interval)
  }, [loadCatalogStatus, loadObjects])

  return (
    <div className="flex h-screen w-screen flex-col bg-background text-foreground">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b bg-card/90 px-4 py-3 backdrop-blur-sm">
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="text-lg font-bold tracking-tight text-primary">
            DETOUR
          </h1>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Space Debris Collision Avoidance Copilot
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {loading && (
            <Badge variant="secondary" className="gap-1 text-primary">
              <span className="inline-block h-2 w-2 rounded-full bg-primary animate-pulse" />
              Processing
            </Badge>
          )}
          <Badge variant="outline" className="font-mono text-foreground">
            Objects: {objects.length || catalogStatus?.object_count || '---'}
          </Badge>
          {catalogStatus?.last_refresh && (
            <span className="hidden md:inline">
              Updated: {new Date(catalogStatus.last_refresh).toLocaleTimeString()}
            </span>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[18rem_1fr_24rem] lg:grid-cols-[20rem_1fr_23rem] lg:grid-rows-1">
        <aside className="min-h-0 overflow-hidden border-b bg-card/40 lg:border-b-0 lg:border-r">
          <ConjunctionPanel />
        </aside>

        <main className="relative min-h-0">
          <Globe />
        </main>

        <aside className="flex min-h-0 flex-col overflow-hidden border-t bg-card/40 lg:border-l lg:border-t-0">
          <div className="min-h-0 flex-1">
            <EventDetail />
          </div>
          <Separator />
          <div className="min-h-0 flex-1">
            <ManeuverPanel />
          </div>
        </aside>
      </div>
    </div>
  )
}

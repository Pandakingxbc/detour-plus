import { useEffect } from 'react'
import Globe from './components/Globe'
import ConjunctionPanel from './components/ConjunctionPanel'
import EventDetail from './components/EventDetail'
import ManeuverPanel from './components/ManeuverPanel'
import { useStore } from './store/useStore'
import { useApi } from './hooks/useApi'

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
    <div className="h-screen w-screen flex flex-col bg-[#0a0e1a]">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 bg-[#111827] border-b border-gray-700/50 shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white tracking-tight">
            DETOUR
          </h1>
          <span className="text-xs text-gray-400 hidden sm:inline">
            Space Debris Collision Avoidance Copilot
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-400">
          {loading && (
            <span className="flex items-center gap-1 text-blue-400">
              <span className="inline-block w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
              Processing...
            </span>
          )}
          <span>
            Objects: <span className="text-white font-mono">{objects.length || catalogStatus?.object_count || '---'}</span>
          </span>
          {catalogStatus?.last_refresh && (
            <span className="hidden md:inline">
              Updated: {new Date(catalogStatus.last_refresh).toLocaleTimeString()}
            </span>
          )}
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        {/* Left panel: Conjunctions */}
        <aside className="w-72 bg-[#111827] border-r border-gray-700/50 flex flex-col shrink-0 overflow-hidden">
          <ConjunctionPanel />
        </aside>

        {/* Center: Globe */}
        <main className="flex-1 relative">
          <Globe />
        </main>

        {/* Right panel: Detail + Maneuvers */}
        <aside className="w-80 bg-[#111827] border-l border-gray-700/50 flex flex-col shrink-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto border-b border-gray-700/50">
            <EventDetail />
          </div>
          <div className="flex-1 overflow-y-auto">
            <ManeuverPanel />
          </div>
        </aside>
      </div>
    </div>
  )
}

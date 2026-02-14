import { useEffect, useState } from 'react'
import { useStore } from '../store/useStore'
import { useApi } from '../hooks/useApi'

function riskBadge(level: string) {
  const colors: Record<string, string> = {
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
    high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    low: 'bg-green-500/20 text-green-400 border-green-500/30',
  }
  return (
    <span className={`px-2 py-0.5 text-xs font-semibold rounded border ${colors[level] || colors.low}`}>
      {level.toUpperCase()}
    </span>
  )
}

function formatDistance(m: number): string {
  if (m < 1000) return `${m.toFixed(0)} m`
  return `${(m / 1000).toFixed(2)} km`
}

export default function ConjunctionPanel() {
  const conjunctions = useStore(s => s.conjunctions)
  const loading = useStore(s => s.loading)
  const primaryId = useStore(s => s.primaryId)
  const setPrimaryId = useStore(s => s.setPrimaryId)
  const setSelectedEvent = useStore(s => s.setSelectedEvent)
  const { screenConjunctions, loadTrajectory } = useApi()
  const [inputId, setInputId] = useState(String(primaryId))

  const handleScreen = () => {
    const id = parseInt(inputId)
    if (!isNaN(id)) {
      setPrimaryId(id)
      screenConjunctions(id, 86400, 50, 200)
      loadTrajectory(id)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-700">
        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider mb-2">
          Conjunction Screening
        </h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={inputId}
            onChange={e => setInputId(e.target.value)}
            placeholder="NORAD ID"
            className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
            onKeyDown={e => e.key === 'Enter' && handleScreen()}
          />
          <button
            onClick={handleScreen}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white text-sm px-3 py-1 rounded font-medium transition-colors"
          >
            {loading ? 'Scanning...' : 'Screen'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conjunctions.length === 0 && !loading && (
          <div className="p-4 text-center text-gray-500 text-sm">
            Enter a NORAD ID and click Screen to find conjunctions.
            <br />
            <span className="text-xs text-gray-600 mt-1 block">
              Try 25544 (ISS) or 48274 (Starlink)
            </span>
          </div>
        )}

        {conjunctions.map((event) => (
          <button
            key={event.event_id}
            onClick={() => setSelectedEvent(event)}
            className="w-full text-left p-3 border-b border-gray-700/50 hover:bg-gray-800/50 transition-colors"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white">
                #{event.secondary_id}
              </span>
              {riskBadge(event.risk_level)}
            </div>
            <div className="grid grid-cols-2 gap-x-4 text-xs text-gray-400">
              <div>
                Miss: <span className="text-white">{formatDistance(event.miss_distance_m)}</span>
              </div>
              <div>
                Prob: <span className="text-white">{event.probability.toExponential(2)}</span>
              </div>
              <div>
                TCA: <span className="text-white">{event.tca_offset_sec.toFixed(0)}s</span>
              </div>
              <div>
                Vel: <span className="text-white">{event.relative_velocity_mps.toFixed(0)} m/s</span>
              </div>
            </div>
          </button>
        ))}
      </div>

      {conjunctions.length > 0 && (
        <div className="p-2 border-t border-gray-700 text-xs text-gray-500 text-center">
          {conjunctions.length} conjunction{conjunctions.length !== 1 ? 's' : ''} found
        </div>
      )}
    </div>
  )
}

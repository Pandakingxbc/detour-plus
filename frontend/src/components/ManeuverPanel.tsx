import { useState } from 'react'
import { useStore } from '../store/useStore'
import { useApi } from '../hooks/useApi'

function formatDistance(m: number): string {
  if (m < 1000) return `${m.toFixed(0)} m`
  return `${(m / 1000).toFixed(2)} km`
}

export default function ManeuverPanel() {
  const event = useStore(s => s.selectedEvent)
  const maneuvers = useStore(s => s.maneuvers)
  const loading = useStore(s => s.loading)
  const { proposeManeuvers, simulateManeuver } = useApi()
  const [simResult, setSimResult] = useState<any>(null)

  const handlePropose = async () => {
    if (!event) return
    await proposeManeuvers(
      event.primary_id,
      event.secondary_id,
      event.tca_offset_sec,
      event.miss_distance_m,
    )
  }

  const handleSimulate = async (maneuver: any) => {
    if (!event) return
    const result = await simulateManeuver(
      event.primary_id,
      event.secondary_id,
      maneuver.delta_v,
      maneuver.burn_time_sec,
    )
    setSimResult(result)
  }

  if (!event) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm h-full flex items-center justify-center">
        Select a conjunction event to plan maneuvers
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-700">
        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider mb-2">
          Maneuver Planning
        </h2>
        <div className="text-xs text-gray-400 mb-2">
          Event: #{event.primary_id} vs #{event.secondary_id}
          <br />
          Miss: {formatDistance(event.miss_distance_m)} | TCA: {event.tca_offset_sec.toFixed(0)}s
        </div>
        <button
          onClick={handlePropose}
          disabled={loading}
          className="w-full bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
        >
          {loading ? 'Computing...' : 'Generate Maneuver Plan'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {maneuvers.map((m) => (
          <div
            key={m.id}
            className="p-3 border-b border-gray-700/50 hover:bg-gray-800/30"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-white capitalize">
                {m.type}
              </span>
              <span className="text-xs text-amber-400 font-mono">
                {m.fuel_kg.toFixed(3)} kg
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-3 text-xs text-gray-400 mb-2">
              <div>
                dV: <span className="text-white">{m.magnitude_mps.toFixed(3)} m/s</span>
              </div>
              <div>
                Lead: <span className="text-white">{(m.burn_lead_sec / 3600).toFixed(1)} hr</span>
              </div>
              <div>
                New miss: <span className="text-green-400">{formatDistance(m.new_miss_distance_m)}</span>
              </div>
              <div>
                Factor: <span className="text-white">{m.improvement_factor.toFixed(1)}x</span>
              </div>
            </div>
            <button
              onClick={() => handleSimulate(m)}
              disabled={loading}
              className="w-full bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 text-white text-xs px-2 py-1 rounded transition-colors"
            >
              Simulate
            </button>
          </div>
        ))}

        {simResult && (
          <div className="p-3 bg-gray-800/80 border-t border-green-500/30">
            <h3 className="text-xs font-bold text-green-400 uppercase mb-2">
              Simulation Result
            </h3>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-gray-900/50 rounded p-2">
                <div className="text-gray-400 mb-1">Before</div>
                <div className="text-red-400 font-mono">
                  {formatDistance(simResult.before?.miss_distance_m ?? 0)}
                </div>
              </div>
              <div className="bg-gray-900/50 rounded p-2">
                <div className="text-gray-400 mb-1">After</div>
                <div className="text-green-400 font-mono">
                  {formatDistance(simResult.after?.miss_distance_m ?? 0)}
                </div>
              </div>
            </div>
            <div className="mt-2 text-xs text-gray-400">
              Fuel: {simResult.fuel_estimate_kg?.toFixed(3)} kg |
              {' '}Collision: {simResult.after?.collision ? 'YES' : 'No'}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

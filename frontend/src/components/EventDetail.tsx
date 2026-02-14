import { useStore } from '../store/useStore'

function formatDistance(m: number): string {
  if (m < 1000) return `${m.toFixed(1)} m`
  return `${(m / 1000).toFixed(3)} km`
}

function riskColorClass(level: string): string {
  switch (level) {
    case 'critical': return 'text-red-400'
    case 'high': return 'text-orange-400'
    case 'medium': return 'text-yellow-400'
    default: return 'text-green-400'
  }
}

export default function EventDetail() {
  const event = useStore(s => s.selectedEvent)
  const selectedObject = useStore(s => s.selectedObject)
  const setSelectedEvent = useStore(s => s.setSelectedEvent)

  if (!event && !selectedObject) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm h-full flex items-center justify-center">
        <div>
          <div className="text-2xl mb-2">&#127760;</div>
          <div>Select a conjunction event or object to view details</div>
        </div>
      </div>
    )
  }

  if (selectedObject && !event) {
    return (
      <div className="p-3">
        <h3 className="text-sm font-bold text-blue-400 uppercase tracking-wider mb-3">
          Object Details
        </h3>
        <div className="space-y-2 text-sm">
          <Row label="Name" value={selectedObject.name} />
          <Row label="NORAD ID" value={String(selectedObject.norad_id)} />
          <Row label="Altitude" value={`${selectedObject.alt_km.toFixed(1)} km`} />
          <Row label="Latitude" value={`${selectedObject.lat.toFixed(2)}°`} />
          <Row label="Longitude" value={`${selectedObject.lon.toFixed(2)}°`} />
          <Row label="Source" value={selectedObject.source} />
        </div>
      </div>
    )
  }

  if (!event) return null

  return (
    <div className="p-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-blue-400 uppercase tracking-wider">
          Event Detail
        </h3>
        <button
          onClick={() => setSelectedEvent(null)}
          className="text-gray-400 hover:text-white text-xs"
        >
          Close
        </button>
      </div>

      <div className="space-y-2 text-sm">
        <Row label="Event ID" value={event.event_id} />
        <Row label="Primary" value={`#${event.primary_id}`} />
        <Row label="Secondary" value={`#${event.secondary_id}`} />
        <Row
          label="Risk Level"
          value={event.risk_level.toUpperCase()}
          valueClass={riskColorClass(event.risk_level)}
        />
        <Row label="Miss Distance" value={formatDistance(event.miss_distance_m)} />
        <Row label="Probability" value={event.probability.toExponential(3)} />
        <Row label="Rel. Velocity" value={`${event.relative_velocity_mps.toFixed(1)} m/s`} />
        <Row label="TCA Offset" value={`${event.tca_offset_sec.toFixed(0)} s`} />
        {event.tca_epoch && <Row label="TCA Epoch" value={event.tca_epoch} />}
        <Row
          label="Escalate"
          value={event.escalate ? 'YES' : 'No'}
          valueClass={event.escalate ? 'text-red-400 font-bold' : 'text-green-400'}
        />
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  valueClass = 'text-white',
}: {
  label: string
  value: string
  valueClass?: string
}) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-gray-700/30">
      <span className="text-gray-400">{label}</span>
      <span className={`font-mono ${valueClass}`}>{value}</span>
    </div>
  )
}

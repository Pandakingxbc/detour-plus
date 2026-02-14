import type { ReactNode } from 'react'
import { useStore } from '../store/useStore'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

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
      <div className="flex h-full items-center justify-center p-4 text-center text-sm text-muted-foreground">
        <div>
          <div className="mb-2 text-2xl">&#127760;</div>
          <div>Select a conjunction event or object to view details</div>
        </div>
      </div>
    )
  }

  if (selectedObject && !event) {
    return (
      <ScrollArea className="h-full p-3">
        <Card className="border-border/70 bg-card/70">
          <CardHeader>
            <CardTitle className="text-primary">Object Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Name" value={selectedObject.name} />
            <Row label="NORAD ID" value={String(selectedObject.norad_id)} />
            <Row label="Altitude" value={`${selectedObject.alt_km.toFixed(1)} km`} />
            <Row label="Latitude" value={`${selectedObject.lat.toFixed(2)}°`} />
            <Row label="Longitude" value={`${selectedObject.lon.toFixed(2)}°`} />
            <Row label="Source" value={selectedObject.source} />
          </CardContent>
        </Card>
      </ScrollArea>
    )
  }

  if (!event) return null

  return (
    <ScrollArea className="h-full p-3">
      <Card className="border-border/70 bg-card/70">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-primary">Event Detail</CardTitle>
          <Button onClick={() => setSelectedEvent(null)} variant="ghost" size="sm">
            Close
          </Button>
        </CardHeader>

        <CardContent className="space-y-2 text-sm">
          <Row label="Event ID" value={event.event_id} />
          <Row label="Primary" value={`#${event.primary_id}`} />
          <Row label="Secondary" value={`#${event.secondary_id}`} />
          <Row
            label="Risk Level"
            value={
              <Badge variant="outline" className={cn('font-semibold', riskColorClass(event.risk_level))}>
                {event.risk_level.toUpperCase()}
              </Badge>
            }
          />
          <Row label="Miss Distance" value={formatDistance(event.miss_distance_m)} />
          <Row label="Probability" value={event.probability.toExponential(3)} />
          <Row label="Rel. Velocity" value={`${event.relative_velocity_mps.toFixed(1)} m/s`} />
          <Row label="TCA Offset" value={`${event.tca_offset_sec.toFixed(0)} s`} />
          {event.tca_epoch && <Row label="TCA Epoch" value={event.tca_epoch} />}
          <Row
            label="Escalate"
            value={
              <Badge variant="outline" className={event.escalate ? 'border-red-500/50 text-red-400' : 'border-green-500/50 text-green-400'}>
                {event.escalate ? 'YES' : 'No'}
              </Badge>
            }
          />
        </CardContent>
      </Card>
    </ScrollArea>
  )
}

function Row({
  label,
  value,
}: {
  label: string
  value: ReactNode
}) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 py-1">
      <span className="text-muted-foreground">{label}</span>
      <div className="font-mono text-foreground">{value}</div>
    </div>
  )
}

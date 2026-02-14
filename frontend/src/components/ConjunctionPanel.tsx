import { useState } from 'react'
import { useStore } from '../store/useStore'
import { useApi } from '../hooks/useApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

function riskBadge(level: string) {
  const colors: Record<string, string> = {
    critical: 'border-red-500/40 bg-red-500/20 text-red-300',
    high: 'border-orange-500/40 bg-orange-500/20 text-orange-300',
    medium: 'border-yellow-500/40 bg-yellow-500/20 text-yellow-300',
    low: 'border-green-500/40 bg-green-500/20 text-green-300',
  }
  return (
    <Badge variant="outline" className={cn('font-semibold tracking-wide', colors[level] || colors.low)}>
      {level.toUpperCase()}
    </Badge>
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
  const selectedEvent = useStore(s => s.selectedEvent)
  const setPrimaryId = useStore(s => s.setPrimaryId)
  const setSelectedEvent = useStore(s => s.setSelectedEvent)
  const { screenConjunctions, loadTrajectory } = useApi()
  const [inputId, setInputId] = useState(String(primaryId))

  const handleScreen = () => {
    const id = parseInt(inputId, 10)
    if (!isNaN(id)) {
      setPrimaryId(id)
      screenConjunctions(id, 86400, 50, 200)
      loadTrajectory(id)
    }
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <Card className="border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Conjunction Screening</CardTitle>
          <CardDescription>Enter a NORAD ID to scan nearby conjunction events.</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input
            type="text"
            value={inputId}
            onChange={e => setInputId(e.target.value)}
            placeholder="NORAD ID"
            onKeyDown={e => e.key === 'Enter' && handleScreen()}
          />
          <Button onClick={handleScreen} disabled={loading}>
            {loading ? 'Scanning...' : 'Screen'}
          </Button>
        </CardContent>
      </Card>

      <ScrollArea className="min-h-0 flex-1 rounded-xl border border-border/70 bg-card/50">
        <div className="space-y-2 p-2">
          {conjunctions.length === 0 && !loading && (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Enter a NORAD ID and click Screen to find conjunctions.
              <br />
              <span className="mt-1 block text-xs">Try `25544` (ISS) or `48274` (Starlink)</span>
            </div>
          )}

          {conjunctions.map((event) => (
            <button
              key={event.event_id}
              onClick={() => setSelectedEvent(event)}
              className={cn(
                'w-full text-left rounded-lg border border-border/60 bg-background/70 p-3 transition-colors hover:bg-accent/40',
                selectedEvent?.event_id === event.event_id && 'ring-1 ring-ring'
              )}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-foreground">#{event.secondary_id}</span>
                {riskBadge(event.risk_level)}
              </div>
              <div className="grid grid-cols-2 gap-x-4 text-xs text-muted-foreground">
                <div>
                  Miss: <span className="text-foreground">{formatDistance(event.miss_distance_m)}</span>
                </div>
                <div>
                  Prob: <span className="text-foreground">{event.probability.toExponential(2)}</span>
                </div>
                <div>
                  TCA: <span className="text-foreground">{event.tca_offset_sec.toFixed(0)}s</span>
                </div>
                <div>
                  Vel: <span className="text-foreground">{event.relative_velocity_mps.toFixed(0)} m/s</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>

      {conjunctions.length > 0 && (
        <div className="text-center text-xs text-muted-foreground">
          {conjunctions.length} conjunction{conjunctions.length !== 1 ? 's' : ''} found
        </div>
      )}
    </div>
  )
}

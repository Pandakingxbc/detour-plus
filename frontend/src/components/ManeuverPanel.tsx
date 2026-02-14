import { useState } from 'react'
import { useStore } from '../store/useStore'
import { useApi } from '../hooks/useApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'

interface SimulationResult {
  before?: { miss_distance_m: number }
  after?: { miss_distance_m: number; collision: boolean }
  fuel_estimate_kg?: number
}

function formatDistance(m: number): string {
  if (m < 1000) return `${m.toFixed(0)} m`
  return `${(m / 1000).toFixed(2)} km`
}

export default function ManeuverPanel() {
  const event = useStore(s => s.selectedEvent)
  const maneuvers = useStore(s => s.maneuvers)
  const loading = useStore(s => s.loading)
  const { proposeManeuvers, simulateManeuver } = useApi()
  const [simResult, setSimResult] = useState<SimulationResult | null>(null)

  const handlePropose = async () => {
    if (!event) return
    setSimResult(null)
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
    setSimResult(result as SimulationResult | null)
  }

  if (!event) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-center text-sm text-muted-foreground">
        Select a conjunction event to plan maneuvers
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <Card className="border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Maneuver Planning</CardTitle>
          <CardDescription>
            Event #{event.primary_id} vs #{event.secondary_id}
          </CardDescription>
          <CardDescription>
            Miss {formatDistance(event.miss_distance_m)} | TCA {event.tca_offset_sec.toFixed(0)}s
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <Button onClick={handlePropose} disabled={loading} className="w-full bg-warning text-warning-foreground hover:bg-warning/90">
            {loading ? 'Computing...' : 'Generate Maneuver Plan'}
          </Button>
        </CardContent>
      </Card>

      <ScrollArea className="min-h-0 flex-1 rounded-xl border border-border/70 bg-card/50">
        <div className="space-y-2 p-2">
          {maneuvers.map((m) => (
            <Card key={m.id} className="border-border/60 bg-background/70">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="capitalize text-foreground">{m.type}</CardTitle>
                  <Badge variant="outline" className="border-warning/50 text-warning">
                    {m.fuel_kg.toFixed(3)} kg
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="grid grid-cols-2 gap-x-3 text-xs text-muted-foreground">
                  <div>
                    dV: <span className="text-foreground">{m.magnitude_mps.toFixed(3)} m/s</span>
                  </div>
                  <div>
                    Lead: <span className="text-foreground">{(m.burn_lead_sec / 3600).toFixed(1)} hr</span>
                  </div>
                  <div>
                    New miss: <span className="text-green-400">{formatDistance(m.new_miss_distance_m)}</span>
                  </div>
                  <div>
                    Factor: <span className="text-foreground">{m.improvement_factor.toFixed(1)}x</span>
                  </div>
                </div>
                <Button onClick={() => handleSimulate(m)} disabled={loading} variant="secondary" className="w-full">
                  Simulate
                </Button>
              </CardContent>
            </Card>
          ))}

          {simResult && (
            <Card className="border-green-500/40 bg-green-500/10">
              <CardHeader className="pb-3">
                <CardTitle className="text-green-400">Simulation Result</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-md bg-background/80 p-2">
                    <div className="mb-1 text-muted-foreground">Before</div>
                    <div className="font-mono text-red-400">
                      {formatDistance(simResult.before?.miss_distance_m ?? 0)}
                    </div>
                  </div>
                  <div className="rounded-md bg-background/80 p-2">
                    <div className="mb-1 text-muted-foreground">After</div>
                    <div className="font-mono text-green-400">
                      {formatDistance(simResult.after?.miss_distance_m ?? 0)}
                    </div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  Fuel: {simResult.fuel_estimate_kg?.toFixed(3)} kg | Collision: {simResult.after?.collision ? 'YES' : 'No'}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </ScrollArea>

      {maneuvers.length === 0 && !loading && (
        <div className="text-center text-xs text-muted-foreground">
          Select an event and generate a plan to see maneuver options.
        </div>
      )}
    </div>
  )
}

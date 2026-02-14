import { useMemo, useState } from 'react'
import { useStore, type ConjunctionEvent, type ManeuverCandidate } from '../store/useStore'
import { useApi } from '../hooks/useApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

interface PlanningConstraints {
  targetMissKm: number
  massKg: number
  ispS: number
  maxFuelKg: number
  maxDeltaVMps: number
}

interface SimulationResult {
  before?: { miss_distance_m: number }
  after?: { miss_distance_m: number; collision: boolean }
  fuel_estimate_kg?: number
}

const DEFAULT_CONSTRAINTS: PlanningConstraints = {
  targetMissKm: 5,
  massKg: 500,
  ispS: 220,
  maxFuelKg: 8,
  maxDeltaVMps: 1.2,
}

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

function formatDistance(m: number): string {
  if (m < 1000) return `${m.toFixed(0)} m`
  return `${(m / 1000).toFixed(2)} km`
}

function nowStamp(): string {
  return new Date().toLocaleTimeString()
}

function riskBadgeClass(level: string): string {
  switch (level.toLowerCase()) {
    case 'critical': return 'border-red-500/50 text-red-400'
    case 'high': return 'border-orange-500/50 text-orange-400'
    case 'medium': return 'border-yellow-500/50 text-yellow-400'
    default: return 'border-green-500/50 text-green-400'
  }
}

function sameConstraints(a: PlanningConstraints, b: PlanningConstraints): boolean {
  return (
    a.targetMissKm === b.targetMissKm &&
    a.massKg === b.massKg &&
    a.ispS === b.ispS &&
    a.maxFuelKg === b.maxFuelKg &&
    a.maxDeltaVMps === b.maxDeltaVMps
  )
}

function projectedRisk(afterMissM: number, collision: boolean): string {
  if (collision || afterMissM < 800) return 'high'
  if (afterMissM < 2500) return 'medium'
  return 'low'
}

export default function ManeuverPanel() {
  const event = useStore(s => s.selectedEvent)
  const conjunctions = useStore(s => s.conjunctions)
  const loading = useStore(s => s.loading)
  const setPlanRiskLevel = useStore(s => s.setPlanRiskLevel)
  const { proposeManeuvers, simulateManeuver } = useApi()

  const [constraints, setConstraints] = useState<PlanningConstraints>(DEFAULT_CONSTRAINTS)
  const [appliedConstraints, setAppliedConstraints] = useState<PlanningConstraints>(DEFAULT_CONSTRAINTS)
  const [logs, setLogs] = useState<string[]>(['Agent ready. Waiting for Apply & Replan.'])
  const [simResult, setSimResult] = useState<SimulationResult | null>(null)
  const [selectedPlan, setSelectedPlan] = useState<ManeuverCandidate | null>(null)

  const upcomingFeed = useMemo(
    () => [...conjunctions].sort(sortByPriority).slice(0, 8),
    [conjunctions]
  )
  const pendingApply = !sameConstraints(constraints, appliedConstraints)

  const appendLog = (message: string) => {
    setLogs(prev => [...prev, `[${nowStamp()}] ${message}`])
  }

  const handleConstraintChange = (key: keyof PlanningConstraints, value: string) => {
    const numeric = Number(value)
    if (Number.isNaN(numeric)) return
    setConstraints(prev => ({ ...prev, [key]: numeric }))
  }

  const handleApplyAndReplan = async () => {
    if (!event) return

    setLogs([])
    setSimResult(null)
    setSelectedPlan(null)
    setAppliedConstraints(constraints)
    appendLog(`Planner starting for active threat ${event.event_id}.`)
    appendLog(`Tool call: propose_maneuvers(primary=${event.primary_id}, secondary=${event.secondary_id}).`)

    const candidates = await proposeManeuvers(
      event.primary_id,
      event.secondary_id,
      event.tca_offset_sec,
      event.miss_distance_m,
      {
        massKg: constraints.massKg,
        ispS: constraints.ispS,
        targetMissKm: constraints.targetMissKm,
      }
    )

    appendLog(`Received ${candidates.length} maneuver candidates.`)

    const accepted = candidates.filter(candidate => {
      if (candidate.fuel_kg > constraints.maxFuelKg) {
        appendLog(`Rejected ${candidate.id}: fuel ${candidate.fuel_kg.toFixed(3)}kg > ${constraints.maxFuelKg.toFixed(3)}kg.`)
        return false
      }
      if (candidate.magnitude_mps > constraints.maxDeltaVMps) {
        appendLog(`Rejected ${candidate.id}: dV ${candidate.magnitude_mps.toFixed(3)}m/s > ${constraints.maxDeltaVMps.toFixed(3)}m/s.`)
        return false
      }
      return true
    })

    if (accepted.length === 0) {
      appendLog('No candidates satisfy current constraints. Risk remains unchanged.')
      setPlanRiskLevel(event.risk_level)
      return
    }

    const best = [...accepted].sort((a, b) => {
      if (b.new_miss_distance_m !== a.new_miss_distance_m) {
        return b.new_miss_distance_m - a.new_miss_distance_m
      }
      return a.fuel_kg - b.fuel_kg
    })[0]

    setSelectedPlan(best)
    appendLog(`Selected ${best.id} (${best.type}) with projected miss ${formatDistance(best.new_miss_distance_m)}.`)
    appendLog(`Tool call: simulate_maneuver(delta_v=[${best.delta_v.map(v => v.toFixed(4)).join(', ')}]).`)

    const simulation = await simulateManeuver(
      event.primary_id,
      event.secondary_id,
      best.delta_v,
      best.burn_time_sec,
    )

    const typedSimulation = simulation as SimulationResult | null
    setSimResult(typedSimulation)

    if (!typedSimulation?.after) {
      appendLog('Simulation did not return a valid post-maneuver state.')
      setPlanRiskLevel(event.risk_level)
      return
    }

    const newRisk = projectedRisk(
      typedSimulation.after.miss_distance_m,
      typedSimulation.after.collision
    )
    setPlanRiskLevel(newRisk)

    appendLog(`Simulation complete. After-miss ${formatDistance(typedSimulation.after.miss_distance_m)}.`)
    appendLog(`Updated risk estimate => ${newRisk.toUpperCase()}.`)
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <Card className="border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Autonomous Feed</CardTitle>
          <CardDescription>Active threat is selected automatically by risk then nearest TCA.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {event ? (
            <div className="rounded-lg border border-border/70 bg-background/70 p-3 text-sm">
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-foreground">{event.event_id}</span>
                <Badge variant="outline" className={cn('uppercase', riskBadgeClass(event.risk_level))}>
                  {event.risk_level}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground">
                Secondary #{event.secondary_id} | TCA {event.tca_offset_sec.toFixed(0)}s | Miss {formatDistance(event.miss_distance_m)}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-border/70 bg-background/60 p-3 text-sm text-muted-foreground">
              No active threat yet. Start screening from the left panel.
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Upcoming Events Feed</CardTitle>
          <CardDescription>Read-only feed. Agent controls active threat selection.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-40 px-3 pb-3">
            <div className="space-y-2">
              {upcomingFeed.map(feedEvent => (
                <div key={feedEvent.event_id} className="rounded-md border border-border/60 bg-background/70 p-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-mono">{feedEvent.event_id}</span>
                    <Badge variant="outline" className={riskBadgeClass(feedEvent.risk_level)}>
                      {feedEvent.risk_level.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="mt-1 text-muted-foreground">
                    TCA {feedEvent.tca_offset_sec.toFixed(0)}s | Miss {formatDistance(feedEvent.miss_distance_m)}
                  </div>
                </div>
              ))}
              {upcomingFeed.length === 0 && (
                <div className="rounded-md border border-border/60 bg-background/70 p-3 text-xs text-muted-foreground">
                  Feed empty until screening produces conjunction events.
                </div>
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <Card className="min-h-0 flex-1 border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Constraints & Replan</CardTitle>
          <CardDescription>Option B flow: edit constraints, then apply to trigger replanning.</CardDescription>
        </CardHeader>
        <CardContent className="min-h-0 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <ConstraintInput
              label="Target Miss (km)"
              value={constraints.targetMissKm}
              onChange={value => handleConstraintChange('targetMissKm', value)}
            />
            <ConstraintInput
              label="Mass (kg)"
              value={constraints.massKg}
              onChange={value => handleConstraintChange('massKg', value)}
            />
            <ConstraintInput
              label="Isp (s)"
              value={constraints.ispS}
              onChange={value => handleConstraintChange('ispS', value)}
            />
            <ConstraintInput
              label="Max Fuel (kg)"
              value={constraints.maxFuelKg}
              onChange={value => handleConstraintChange('maxFuelKg', value)}
            />
            <ConstraintInput
              label="Max dV (m/s)"
              value={constraints.maxDeltaVMps}
              onChange={value => handleConstraintChange('maxDeltaVMps', value)}
            />
          </div>

          {pendingApply && (
            <Badge variant="outline" className="border-warning/50 text-warning">
              Constraints changed (pending apply)
            </Badge>
          )}

          <Button
            onClick={() => void handleApplyAndReplan()}
            disabled={loading || !event}
            className="w-full bg-warning text-warning-foreground hover:bg-warning/90"
          >
            {loading ? 'Replanning...' : 'Apply & Replan'}
          </Button>

          {selectedPlan && (
            <div className="rounded-md border border-border/70 bg-background/70 p-2 text-xs text-muted-foreground">
              Selected plan: <span className="font-mono text-foreground">{selectedPlan.id}</span> ({selectedPlan.type}) | dV {selectedPlan.magnitude_mps.toFixed(3)} m/s | Fuel {selectedPlan.fuel_kg.toFixed(3)} kg
            </div>
          )}

          {simResult?.after && (
            <div className="rounded-md border border-green-500/40 bg-green-500/10 p-2 text-xs text-muted-foreground">
              Result: Before {formatDistance(simResult.before?.miss_distance_m ?? 0)} -&gt; After {formatDistance(simResult.after.miss_distance_m)} | Collision {simResult.after.collision ? 'YES' : 'No'}
            </div>
          )}

          <div className="min-h-0 flex-1 rounded-md border border-border/70 bg-black/80">
            <div className="border-b border-border/70 px-2 py-1 text-xs uppercase tracking-wide text-muted-foreground">
              Agent Console
            </div>
            <ScrollArea className="h-40 p-2">
              <div className="space-y-1 font-mono text-xs text-foreground">
                {logs.map((line, index) => (
                  <div key={`${line}-${index}`}>{line}</div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function ConstraintInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: string) => void
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Input value={value} onChange={e => onChange(e.target.value)} type="number" step="0.1" />
    </label>
  )
}

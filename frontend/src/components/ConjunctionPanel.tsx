import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../store/useStore'
import { useApi } from '../hooks/useApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

type MonitorStatus = 'idle' | 'screening' | 'monitoring'

function orbitClass(altKm: number): 'LEO' | 'MEO' | 'GEO' | 'HEO' {
  if (altKm < 2000) return 'LEO'
  if (altKm < 33000) return 'MEO'
  if (altKm <= 42000) return 'GEO'
  return 'HEO'
}

function estimateInclinationDeg(position: number[], velocity: number[]): number | null {
  if (position.length < 3 || velocity.length < 3) return null
  const hx = position[1] * velocity[2] - position[2] * velocity[1]
  const hy = position[2] * velocity[0] - position[0] * velocity[2]
  const hz = position[0] * velocity[1] - position[1] * velocity[0]
  const hNorm = Math.sqrt(hx * hx + hy * hy + hz * hz)
  if (hNorm === 0) return null
  const cosI = Math.max(-1, Math.min(1, hz / hNorm))
  return Math.acos(cosI) * (180 / Math.PI)
}

function statusVariant(status: MonitorStatus): 'secondary' | 'outline' {
  return status === 'monitoring' ? 'secondary' : 'outline'
}

export default function ConjunctionPanel() {
  const primaryId = useStore(s => s.primaryId)
  const objects = useStore(s => s.objects)
  const loading = useStore(s => s.loading)
  const catalogStatus = useStore(s => s.catalogStatus)
  const conjunctions = useStore(s => s.conjunctions)
  const setPrimaryId = useStore(s => s.setPrimaryId)
  const setPlanRiskLevel = useStore(s => s.setPlanRiskLevel)
  const { screenConjunctions, loadTrajectory } = useApi()

  const [inputId, setInputId] = useState(String(primaryId))
  const [status, setStatus] = useState<MonitorStatus>('idle')

  const selectedSatellite = useMemo(
    () => objects.find(obj => obj.norad_id === primaryId) ?? null,
    [objects, primaryId]
  )

  const dataMode = useMemo(() => {
    const sources = catalogStatus?.sources?.map(source => source.toLowerCase()) ?? []
    return sources.some(source => source.includes('cdm')) ? 'CDM Ingest Ready' : 'TLE Demo'
  }, [catalogStatus])

  const runScreening = async (id: number) => {
    setStatus('screening')
    setPrimaryId(id)
    setPlanRiskLevel(null)
    await Promise.all([
      screenConjunctions(id, 86400, 50, 200),
      loadTrajectory(id),
    ])
    setStatus('monitoring')
  }

  const handleStart = async () => {
    const id = parseInt(inputId, 10)
    if (Number.isNaN(id)) return
    await runScreening(id)
  }

  useEffect(() => {
    if (status !== 'monitoring') return
    const interval = setInterval(() => {
      void screenConjunctions(primaryId, 86400, 50, 200)
    }, 30000)
    return () => clearInterval(interval)
  }, [primaryId, screenConjunctions, status])

  const inclination = selectedSatellite ? estimateInclinationDeg(selectedSatellite.position, selectedSatellite.velocity) : null

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <Card className="border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Target & Satellite Context</CardTitle>
          <CardDescription>Autonomous conjunction monitoring target</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              type="text"
              value={inputId}
              onChange={e => setInputId(e.target.value)}
              placeholder="NORAD ID"
              onKeyDown={e => e.key === 'Enter' && void handleStart()}
            />
            <Button onClick={() => void handleStart()} disabled={loading}>
              {loading ? 'Screening...' : 'Screen / Start'}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={statusVariant(status)} className="uppercase tracking-wide">
              Status: {status}
            </Badge>
            <Badge variant="outline">Data Mode: {dataMode}</Badge>
            <Badge variant="outline">Events: {conjunctions.length}</Badge>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/70">
        <CardHeader className="pb-3">
          <CardTitle className="text-primary">Satellite Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <FieldRow label="NORAD ID" value={String(primaryId)} mono />
          <FieldRow label="Name" value={selectedSatellite?.name || 'Unknown'} />
          <FieldRow label="Orbit Class" value={selectedSatellite ? orbitClass(selectedSatellite.alt_km) : '---'} mono />
          <FieldRow
            label="Altitude Estimate"
            value={selectedSatellite ? `${selectedSatellite.alt_km.toFixed(1)} km` : '---'}
            mono
          />
          <FieldRow
            label="Inclination Estimate"
            value={inclination !== null ? `${inclination.toFixed(2)}°` : '---'}
            mono
          />
        </CardContent>
      </Card>
    </div>
  )
}

function FieldRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 py-1">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono text-foreground' : 'text-foreground'}>{value}</span>
    </div>
  )
}

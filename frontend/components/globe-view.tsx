"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { Line, OrbitControls, Stars } from "@react-three/drei"
import * as THREE from "three"

import { geodeticToUnitVector } from "@/lib/geo"
import { cn } from "@/lib/utils"
import { SimulationOverlayV2 } from "@/components/simulation-overlay-v2"
import type { SimEngine } from "@/lib/sim-engine"

declare global {
  interface Window {
    __DETOUR_SPEED__?: number
  }
}

const TEXTURE_PATH = "/textures/earth/blue-marble-day.jpg"
const DISPLAY_OBJECT_LIMIT = 2500
const DEBRIS_REFRESH_MS = 15_000
const DEBRIS_ORBIT_CLASSES = "LEO"
const ORBIT_REFRESH_MS = 30_000
const TARGET_TICK_MS = 1000
const TRAIL_FRACTION = 0.20 // Show ~20% of orbit as visible trail arc
const MIN_TRAIL_POINTS = 10

interface DebrisObject {
  noradId: number
  lat: number
  lon: number
  altKm: number
}

interface DebrisResponse {
  timeUtc: string
  objects: DebrisObject[]
}

interface OrbitPoint {
  tUtc: string
  lat: number
  lon: number
  altKm: number
}

interface OrbitResponse {
  noradId: number
  timeStartUtc: string
  stepSec: number
  points: OrbitPoint[]
}

interface OrbitTrackState {
  points: THREE.Vector3[]
  timeStartMs: number
  stepSec: number
}

function toVectorFromGeodetic(lat: number, lon: number, altKm: number): THREE.Vector3 | null {
  if (![lat, lon, altKm].every(Number.isFinite)) return null
  if (Math.abs(lat) > 90 || Math.abs(lon) > 360) return null

  const p = geodeticToUnitVector(lat, lon, altKm)
  const magnitude = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z)
  if (magnitude < 0.9 || magnitude > 10) return null

  return new THREE.Vector3(p.x, p.y, p.z)
}

function Earth() {
  const { gl } = useThree()
  const [surfaceMap, setSurfaceMap] = useState<THREE.Texture | null>(null)

  useEffect(() => {
    let active = true
    const loader = new THREE.TextureLoader()

    loader.load(
      TEXTURE_PATH,
      (texture) => {
        if (!active) {
          texture.dispose()
          return
        }

        texture.colorSpace = THREE.SRGBColorSpace
        texture.anisotropy = Math.min(8, gl.capabilities.getMaxAnisotropy())
        texture.minFilter = THREE.LinearMipmapLinearFilter
        texture.magFilter = THREE.LinearFilter
        texture.needsUpdate = true

        setSurfaceMap((previous) => {
          previous?.dispose()
          return texture
        })
      },
      undefined,
      () => {
        // If the local texture is not present yet, keep fallback material.
      }
    )

    return () => {
      active = false
    }
  }, [gl])

  useEffect(() => {
    return () => {
      surfaceMap?.dispose()
    }
  }, [surfaceMap])

  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        map: surfaceMap ?? undefined,
        color: surfaceMap ? "#ffffff" : "#173b5f",
        toneMapped: false,
      }),
    [surfaceMap]
  )

  useEffect(() => {
    return () => {
      material.dispose()
    }
  }, [material])

  return (
    <mesh material={material}>
      <sphereGeometry args={[1, 64, 64]} />
    </mesh>
  )
}

function Graticule() {
  const latLines = useMemo(() => {
    const latitudes = [-60, -30, 0, 30, 60]
    return latitudes.map((lat) => {
      const points: [number, number, number][] = []
      for (let lon = -180; lon <= 180; lon += 2) {
        const p = geodeticToUnitVector(lat, lon, 0)
        points.push([p.x * 1.002, p.y * 1.002, p.z * 1.002])
      }
      return points
    })
  }, [])

  const lonLines = useMemo(() => {
    const longitudes = [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150]
    return longitudes.map((lon) => {
      const points: [number, number, number][] = []
      for (let lat = -90; lat <= 90; lat += 2) {
        const p = geodeticToUnitVector(lat, lon, 0)
        points.push([p.x * 1.002, p.y * 1.002, p.z * 1.002])
      }
      return points
    })
  }, [])

  return (
    <group>
      {latLines.map((points, index) => (
        <Line key={`lat-${index}`} points={points} color="#ffffff" transparent opacity={0.28} lineWidth={0.6} />
      ))}
      {lonLines.map((points, index) => (
        <Line key={`lon-${index}`} points={points} color="#ffffff" transparent opacity={0.25} lineWidth={0.6} />
      ))}
    </group>
  )
}

function Atmosphere() {
  return (
    <mesh>
      <sphereGeometry args={[1.015, 64, 64]} />
      <meshBasicMaterial color="#73a5ff" transparent opacity={0.1} side={THREE.BackSide} />
    </mesh>
  )
}

function StaticObjects({
  positions,
  simTimeRef,
}: {
  positions: THREE.Vector3[]
  simTimeRef?: React.RefObject<number>
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const wasSimulating = useRef(false)

  // Precompute per-debris drift: slow linear drift + oscillation
  const driftData = useMemo(() => {
    return positions.map((_pos, i) => {
      const phi = i * 2.39996322  // golden angle
      const theta = ((i * 1.61803) % 1.0) * Math.PI
      // Linear drift speed — visible in short demo
      const speed = 0.00004 + (i % 60) * 0.0000008
      // Oscillation — large enough to see wobble
      const oscAmp = 0.008 + (i % 40) * 0.0003
      const oscFreq = 0.005 + (i % 50) * 0.00006
      return {
        dx: Math.cos(phi) * Math.sin(theta) * speed,
        dy: Math.cos(theta) * speed * 0.4,
        dz: Math.sin(phi) * Math.sin(theta) * speed,
        ox: Math.cos(phi + 1.0) * oscAmp,
        oy: Math.sin(theta + 1.0) * oscAmp * 0.4,
        oz: Math.sin(phi + 2.0) * oscAmp,
        freq: oscFreq,
      }
    })
  }, [positions])

  // Set initial positions
  useEffect(() => {
    const mesh = meshRef.current
    if (!mesh || positions.length === 0) return

    positions.forEach((position, index) => {
      dummy.position.copy(position)
      dummy.scale.setScalar(0.0063)
      dummy.updateMatrix()
      mesh.setMatrixAt(index, dummy.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  }, [dummy, positions])

  // Per-frame drift during simulation
  useFrame(() => {
    const mesh = meshRef.current
    if (!mesh || positions.length === 0) return

    const isSimulating = !!simTimeRef

    // Reset positions when simulation ends
    if (!isSimulating && wasSimulating.current) {
      for (let i = 0; i < positions.length; i++) {
        dummy.position.copy(positions[i])
        dummy.scale.setScalar(0.0063)
        dummy.updateMatrix()
        mesh.setMatrixAt(i, dummy.matrix)
      }
      mesh.instanceMatrix.needsUpdate = true
      wasSimulating.current = false
      return
    }

    if (!isSimulating) return
    wasSimulating.current = true

    const t = simTimeRef.current
    for (let i = 0; i < positions.length; i++) {
      const pos = positions[i]
      const d = driftData[i]
      const osc = Math.sin(d.freq * t)
      dummy.position.set(
        pos.x + d.dx * t + d.ox * osc,
        pos.y + d.dy * t + d.oy * osc,
        pos.z + d.dz * t + d.oz * osc
      )
      dummy.scale.setScalar(0.0063)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true
  })

  if (positions.length === 0) return null

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, positions.length]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color="#f59e0b" transparent opacity={0.9} />
    </instancedMesh>
  )
}

const MANEUVER_ANIM_SEC = 3.5

function OrbitTrack({ points, isManual, maneuverStartMs }: { points: THREE.Vector3[]; isManual?: boolean; maneuverStartMs: number }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lineRef = useRef<any>(null)
  const normalColor = useMemo(() => new THREE.Color(isManual ? "#10b981" : "#7dd3fc"), [isManual])
  const redColor = useMemo(() => new THREE.Color("#ef4444"), [])
  const tempColor = useMemo(() => new THREE.Color(), [])

  useFrame(() => {
    const mat = lineRef.current?.material
    if (!mat) return

    if (maneuverStartMs > 0) {
      const t = (Date.now() - maneuverStartMs) / 1000
      if (t < MANEUVER_ANIM_SEC) {
        // 0→0.3 ramp to red, 0.3→2.5 hold red, 2.5→3.5 fade back
        let blend: number
        if (t < 0.3) blend = t / 0.3
        else if (t < 2.5) blend = 1
        else blend = 1 - (t - 2.5) / 1.0
        blend = Math.max(0, Math.min(1, blend))

        tempColor.copy(normalColor).lerp(redColor, blend)
        mat.color.copy(tempColor)
        mat.linewidth = 1.4 + 1.0 * blend
        return
      }
    }
    mat.color.copy(normalColor)
    mat.linewidth = 1.4
  })

  if (points.length < 2) return null
  const linePoints = points.map((p) => [p.x, p.y, p.z] as [number, number, number])

  return <Line ref={lineRef} points={linePoints} color={normalColor} transparent opacity={0.95} lineWidth={1.4} />
}

const MARKER_DAMPING = 0.08

function TargetMarker({ orbitTrack, isManual, maneuverStartMs }: { orbitTrack: OrbitTrackState; isManual?: boolean; maneuverStartMs: number }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const matRef = useRef<THREE.MeshBasicMaterial>(null)
  const targetPos = useRef(new THREE.Vector3())
  const initialized = useRef(false)
  const normalColor = useMemo(() => new THREE.Color(isManual ? "#10b981" : "#22d3ee"), [isManual])
  const redColor = useMemo(() => new THREE.Color("#ef4444"), [])
  const tempColor = useMemo(() => new THREE.Color(), [])

  useFrame(() => {
    if (!meshRef.current || orbitTrack.points.length < 2) return

    // --- position ---
    const stepMs = orbitTrack.stepSec * 1000
    if (!Number.isFinite(stepMs) || stepMs <= 0) {
      targetPos.current.copy(orbitTrack.points[0])
      if (!initialized.current) { meshRef.current.position.copy(targetPos.current); initialized.current = true }
      else meshRef.current.position.lerp(targetPos.current, MARKER_DAMPING)
    } else {
      const speed = window.__DETOUR_SPEED__ || 1
      const elapsedMs = Math.max(0, Date.now() - orbitTrack.timeStartMs) * speed
      const totalDurationMs = (orbitTrack.points.length - 1) * stepMs
      const loopedMs = totalDurationMs > 0 ? elapsedMs % totalDurationMs : 0
      const rawIndex = loopedMs / stepMs
      const index = Math.min(Math.floor(rawIndex), orbitTrack.points.length - 2)
      const alpha = rawIndex - index
      targetPos.current.lerpVectors(orbitTrack.points[index], orbitTrack.points[index + 1], alpha)

      if (!initialized.current) { meshRef.current.position.copy(targetPos.current); initialized.current = true }
      else meshRef.current.position.lerp(targetPos.current, MARKER_DAMPING)
    }

    // --- color + scale animation ---
    if (matRef.current && maneuverStartMs > 0) {
      const t = (Date.now() - maneuverStartMs) / 1000
      if (t < MANEUVER_ANIM_SEC) {
        let blend: number
        if (t < 0.3) blend = t / 0.3
        else if (t < 2.5) blend = 1
        else blend = 1 - (t - 2.5) / 1.0
        blend = Math.max(0, Math.min(1, blend))

        tempColor.copy(normalColor).lerp(redColor, blend)
        matRef.current.color.copy(tempColor)
        meshRef.current.scale.setScalar(1 + 0.5 * blend)
        return
      }
    }
    if (matRef.current) matRef.current.color.copy(normalColor)
    meshRef.current.scale.setScalar(1)
  })

  if (orbitTrack.points.length === 0) return null

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[0.012, 14, 14]} />
      <meshBasicMaterial ref={matRef} color={normalColor} />
    </mesh>
  )
}

function Scene({
  debrisPositions,
  trailPoints,
  orbitTrack,
  isManualSatellite,
  simEngine,
  maneuverStartMs,
}: {
  debrisPositions: THREE.Vector3[]
  trailPoints: THREE.Vector3[]
  orbitTrack: OrbitTrackState
  isManualSatellite: boolean
  simEngine?: SimEngine | null
  maneuverStartMs: number
}) {
  const { camera } = useThree()

  useEffect(() => {
    camera.position.set(0, 0, 4)
  }, [camera])

  const isRealtimeSim = !!simEngine

  return (
    <>
      <Stars radius={110} depth={70} count={2600} factor={13.8} saturation={0} fade speed={0.15} />
      <Stars radius={112} depth={75} count={1400} factor={20.4} saturation={0} fade speed={0.18} />
      <Stars radius={115} depth={80} count={650} factor={25.8} saturation={0} fade speed={0.12} />
      <Earth />
      <Graticule />
      <Atmosphere />
      {!isRealtimeSim && <OrbitTrack points={trailPoints} isManual={isManualSatellite} maneuverStartMs={maneuverStartMs} />}
      {!isRealtimeSim && <TargetMarker orbitTrack={orbitTrack} isManual={isManualSatellite} maneuverStartMs={maneuverStartMs} />}
      {debrisPositions.length > 0 && !isRealtimeSim ? <StaticObjects positions={debrisPositions} /> : null}
      {simEngine && <SimulationOverlayV2 engine={simEngine} />}
      <OrbitControls enablePan enableZoom minDistance={1.5} maxDistance={20} enableDamping dampingFactor={0.05} />
    </>
  )
}

interface ManualSatelliteData {
  times: number[]
  positions: number[][]
  velocities: number[][]
}

interface ManeuverEventData {
  position: number[]
  velocity: number[]
  delta_v: number[]
}

interface GlobeViewProps {
  compacted?: boolean
  noradId?: number | null
  manualSatelliteData?: ManualSatelliteData | null
  simEngine?: SimEngine | null
  maneuverEvent?: ManeuverEventData | null
}

const SPEED_STEPS = [1, 2, 5, 10, 25, 50, 100]

export function GlobeView({ compacted = false, noradId, manualSatelliteData, simEngine, maneuverEvent }: GlobeViewProps) {
  const [speed, setSpeed] = useState(1)
  const [maneuverStartMs, setManeuverStartMs] = useState(0)
  const orbitTrackRef = useRef<OrbitTrackState>({ points: [], timeStartMs: Date.now(), stepSec: 60 })

  const handleSpeedChange = useCallback((value: number) => {
    setSpeed(value)
    window.__DETOUR_SPEED__ = value
  }, [])

  const [debrisPositions, setDebrisPositions] = useState<THREE.Vector3[]>([])
  const [orbitTrack, setOrbitTrack] = useState<OrbitTrackState>({
    points: [],
    timeStartMs: Date.now(),
    stepSec: 60,
  })
  const [currentTimeMs, setCurrentTimeMs] = useState(() => Date.now())

  useEffect(() => {
    const interval = window.setInterval(() => {
      setCurrentTimeMs(Date.now())
    }, TARGET_TICK_MS)

    return () => window.clearInterval(interval)
  }, [])

  // Debris loading — paused during simulation to avoid fighting with drift
  useEffect(() => {
    if (simEngine) return // Freeze debris positions during simulation

    const controller = new AbortController()
    let cancelled = false
    let inFlight = false

    const loadDebris = async () => {
      if (cancelled || inFlight) return
      inFlight = true

      try {
        const response = await fetch(`/api/debris?limit=${DISPLAY_OBJECT_LIMIT}&orbitClasses=${DEBRIS_ORBIT_CLASSES}`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const payload = (await response.json()) as DebrisResponse
        const points = payload.objects
          .map((entry) => toVectorFromGeodetic(entry.lat, entry.lon, entry.altKm))
          .filter((value): value is THREE.Vector3 => value !== null)

        if (!cancelled) {
          setDebrisPositions(points)
        }
      } catch {
        // Keep previous frame on transient failures.
      } finally {
        inFlight = false
      }
    }

    void loadDebris()

    const interval = window.setInterval(() => {
      void loadDebris()
    }, DEBRIS_REFRESH_MS)

    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(interval)
    }
  }, [simEngine])

  useEffect(() => {
    if (!noradId) {
      setOrbitTrack({
        points: [],
        timeStartMs: Date.now(),
        stepSec: 60,
      })
      return
    }

    // Handle manual satellite
    if (noradId === -1 && manualSatelliteData) {
      const convertPositionToGeodetic = (pos: number[]) => {
        const x = pos[0]
        const y = pos[1]
        const z = pos[2]
        const r = Math.sqrt(x * x + y * y + z * z)
        const lat = (Math.asin(z / r) * 180) / Math.PI
        const lon = (Math.atan2(y, x) * 180) / Math.PI
        const altKm = (r - 6371000) / 1000
        return { lat, lon, altKm }
      }

      try {
        const points = manualSatelliteData.positions
          .map((pos: number[]) => {
            const geodetic = convertPositionToGeodetic(pos)
            return toVectorFromGeodetic(geodetic.lat, geodetic.lon, geodetic.altKm)
          })
          .filter((value: THREE.Vector3 | null): value is THREE.Vector3 => value !== null)

        // Calculate proper timestep from trajectory data
        const times = manualSatelliteData.times
        const avgStep = times.length > 1 ? (times[times.length - 1] - times[0]) / (times.length - 1) : 30

        setOrbitTrack({
          points,
          timeStartMs: Date.now(),
          stepSec: avgStep,
        })
      } catch (error) {
        console.error("Failed to process manual satellite:", error)
      }
      return
    }

    const controller = new AbortController()
    let cancelled = false
    let inFlight = false

    const loadOrbit = async () => {
      if (cancelled || inFlight) return
      inFlight = true

      try {
        const response = await fetch(`/api/orbit?norad=${noradId}&minutes=180&stepSec=60`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const payload = (await response.json()) as OrbitResponse
        const points = payload.points
          .map((point) => toVectorFromGeodetic(point.lat, point.lon, point.altKm))
          .filter((value): value is THREE.Vector3 => value !== null)

        const parsedStartMs = Date.parse(payload.timeStartUtc)
        const startMs = Number.isFinite(parsedStartMs) ? parsedStartMs : Date.now()

        if (!cancelled) {
          const newStepSec = Math.max(10, Math.round(payload.stepSec || 60))

          setOrbitTrack((prev) => {
            // If we have a previous track, compute where the marker currently
            // is (as a fraction of the loop) and offset the new timeStartMs so
            // the marker continues from roughly the same fractional position.
            if (prev.points.length >= 2 && points.length >= 2) {
              const prevStepMs = prev.stepSec * 1000
              const prevTotal = (prev.points.length - 1) * prevStepMs
              if (prevTotal > 0) {
                const speedMul = window.__DETOUR_SPEED__ || 1
                const elapsed = Math.max(0, Date.now() - prev.timeStartMs) * speedMul
                const fraction = (elapsed % prevTotal) / prevTotal

                const newStepMs = newStepSec * 1000
                const newTotal = (points.length - 1) * newStepMs
                // Shift timeStartMs back so the same fraction is current
                const adjustedStart = Date.now() - fraction * newTotal

                return {
                  points,
                  timeStartMs: adjustedStart,
                  stepSec: newStepSec,
                }
              }
            }

            return {
              points,
              timeStartMs: startMs,
              stepSec: newStepSec,
            }
          })
        }
      } catch {
        if (!cancelled) {
          setOrbitTrack((previous) => ({ ...previous, points: [] }))
        }
      } finally {
        inFlight = false
      }
    }

    void loadOrbit()
    const interval = window.setInterval(() => {
      void loadOrbit()
    }, ORBIT_REFRESH_MS)

    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(interval)
    }
  }, [noradId, manualSatelliteData])

  // Keep a ref to current orbit so the maneuver effect can read it without
  // depending on it (which would cause re-fires on every orbit refresh).
  useEffect(() => { orbitTrackRef.current = orbitTrack }, [orbitTrack])

  // Apply a subtle visual perturbation when the agent executes a maneuver.
  // Instead of re-propagating from the backend state (which is in a different
  // orbit), we shift the current displayed orbit points by a tiny amount in
  // the delta-v direction. This keeps the orbit in the same region.
  useEffect(() => {
    if (!maneuverEvent) return

    const dv = maneuverEvent.delta_v
    const dvMag = Math.sqrt(dv[0] ** 2 + dv[1] ** 2 + dv[2] ** 2)

    console.log("[DETOUR] Orbit perturbation from maneuver:", {
      delta_v: dv,
      magnitude_ms: dvMag.toFixed(4),
      backend_position_eci_m: maneuverEvent.position,
      backend_velocity_eci_ms: maneuverEvent.velocity,
    })

    const current = orbitTrackRef.current
    if (dvMag === 0 || current.points.length < 2) {
      setManeuverStartMs(Date.now())
      const t = setTimeout(() => setManeuverStartMs(0), MANEUVER_ANIM_SEC * 1000 + 500)
      return () => clearTimeout(t)
    }

    // Direction of the delta-v in scene space (scene ≈ ECI, Earth radius = 1)
    const dir = new THREE.Vector3(dv[0], dv[1], dv[2]).normalize()

    // Visual perturbation magnitude — enough to see but not enough to look wrong.
    // 0.002 scene units ≈ 12.7 km, 0.008 ≈ 51 km.
    const vizMag = Math.max(0.002, Math.min(0.008, dvMag * 0.004))

    console.log("[DETOUR] Applying orbit shift:", {
      direction: [dir.x.toFixed(4), dir.y.toFixed(4), dir.z.toFixed(4)],
      magnitude_scene_units: vizMag.toFixed(6),
      approx_km: (vizMag * 6371).toFixed(2),
    })

    // Shift every orbit point by the perturbation vector
    const newPoints = current.points.map((p) => p.clone().addScaledVector(dir, vizMag))

    if (newPoints.length > 0) {
      const first = newPoints[0]
      const last = newPoints[newPoints.length - 1]
      console.log("[DETOUR] Post-maneuver orbit:", {
        pointCount: newPoints.length,
        firstPoint: [first.x.toFixed(4), first.y.toFixed(4), first.z.toFixed(4)],
        lastPoint: [last.x.toFixed(4), last.y.toFixed(4), last.z.toFixed(4)],
      })
    }

    setOrbitTrack((prev) => ({ ...prev, points: newPoints }))
    setManeuverStartMs(Date.now())

    const t = setTimeout(() => setManeuverStartMs(0), MANEUVER_ANIM_SEC * 1000 + 500)
    return () => clearTimeout(t)
  }, [maneuverEvent]) // eslint-disable-line react-hooks/exhaustive-deps

  const currentIndex = useMemo(() => {
    if (orbitTrack.points.length === 0) return 0

    const stepMs = orbitTrack.stepSec * 1000
    if (!Number.isFinite(stepMs) || stepMs <= 0) return 0

    const speed = window.__DETOUR_SPEED__ || 1
    const elapsedMs = Math.max(0, currentTimeMs - orbitTrack.timeStartMs) * speed
    const totalDurationMs = (orbitTrack.points.length - 1) * stepMs
    if (totalDurationMs <= 0) return 0

    const loopedMs = elapsedMs % totalDurationMs
    return Math.min(Math.floor(loopedMs / stepMs), orbitTrack.points.length - 1)
  }, [currentTimeMs, orbitTrack])

  const trailPoints = useMemo(() => {
    const points = orbitTrack.points
    if (points.length < 2) return points

    const trailLength = Math.max(MIN_TRAIL_POINTS, Math.floor(points.length * TRAIL_FRACTION))
    // Show a segment: some points behind the satellite, rest ahead
    const behindCount = Math.max(2, Math.floor(trailLength * 0.3))
    const aheadCount = trailLength - behindCount
    const startIndex = Math.max(0, currentIndex - behindCount)
    const endIndex = Math.min(points.length, currentIndex + aheadCount + 1)

    return points.slice(startIndex, endIndex)
  }, [orbitTrack.points, currentIndex])

  return (
    <div
      className={cn(
        "absolute inset-0 h-full w-full origin-center overflow-hidden transition-transform duration-500 ease-in-out",
        compacted ? "-translate-y-16 scale-[0.7]" : "translate-y-0 scale-100"
      )}
    >
      <Canvas
        camera={{ fov: 45, near: 0.1, far: 1000, position: [0, 0, 4] }}
        gl={{ antialias: true, alpha: false }}
        resize={{ offsetSize: true }}
        style={{ position: "absolute", inset: 0, background: "#030303" }}
      >
        <Scene
          debrisPositions={debrisPositions}
          trailPoints={trailPoints}
          orbitTrack={orbitTrack}
          isManualSatellite={noradId === -1}
          simEngine={simEngine}
          maneuverStartMs={maneuverStartMs}
        />
      </Canvas>

      {/* Speed control overlay */}
      <div className="pointer-events-auto absolute bottom-4 left-4 flex items-center gap-2 rounded-full border border-white/10 bg-black/70 px-3 py-1.5 text-[10px] font-mono text-gray-300 backdrop-blur-sm">
        <span className="select-none text-gray-500">SPD</span>
        <input
          type="range"
          min={0}
          max={SPEED_STEPS.length - 1}
          step={1}
          value={SPEED_STEPS.indexOf(speed)}
          onChange={(e) => handleSpeedChange(SPEED_STEPS[Number(e.target.value)])}
          className="h-1 w-20 cursor-pointer appearance-none rounded-full bg-white/20 accent-cyan-400 [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:w-2.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400"
        />
        <span className={cn("min-w-[3ch] text-right tabular-nums", speed > 1 ? "text-cyan-400" : "text-gray-500")}>
          {speed}x
        </span>
      </div>
    </div>
  )
}

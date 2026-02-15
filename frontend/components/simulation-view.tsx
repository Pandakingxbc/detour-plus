"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { Line, OrbitControls, Stars } from "@react-three/drei"
import * as THREE from "three"
import { Play, Pause, RotateCcw } from "lucide-react"

import { geodeticToUnitVector, EARTH_RADIUS_KM } from "@/lib/geo"

// --- Types ---

interface TrajectoryPoint {
  t: number
  lat: number
  lon: number
  alt_km: number
}

interface ScenarioData {
  duration_sec: number
  dt_sec: number
  collision_t: number
  miss_distance_m: number
  satellite: TrajectoryPoint[]
  debris: TrajectoryPoint[]
}

// --- Helpers ---

function geoToVec3(lat: number, lon: number, altKm: number): THREE.Vector3 {
  const p = geodeticToUnitVector(lat, lon, altKm)
  return new THREE.Vector3(p.x, p.y, p.z)
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function lerpPoint(
  a: TrajectoryPoint,
  b: TrajectoryPoint,
  fraction: number
): THREE.Vector3 {
  const lat = lerp(a.lat, b.lat, fraction)
  const lon = lerp(a.lon, b.lon, fraction)
  const alt = lerp(a.alt_km, b.alt_km, fraction)
  return geoToVec3(lat, lon, alt)
}

function getPositionAtTime(
  trajectory: TrajectoryPoint[],
  simTime: number
): THREE.Vector3 | null {
  if (trajectory.length === 0) return null
  if (simTime <= trajectory[0].t) return geoToVec3(trajectory[0].lat, trajectory[0].lon, trajectory[0].alt_km)
  if (simTime >= trajectory[trajectory.length - 1].t)
    return geoToVec3(
      trajectory[trajectory.length - 1].lat,
      trajectory[trajectory.length - 1].lon,
      trajectory[trajectory.length - 1].alt_km
    )

  // Binary search for the right interval
  let lo = 0
  let hi = trajectory.length - 1
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1
    if (trajectory[mid].t <= simTime) lo = mid
    else hi = mid
  }

  const fraction = (simTime - trajectory[lo].t) / (trajectory[hi].t - trajectory[lo].t)
  return lerpPoint(trajectory[lo], trajectory[hi], fraction)
}

/** Compute approximate real-world distance (km) between two trajectory positions at a given time */
function getDistanceKm(
  trajA: TrajectoryPoint[],
  trajB: TrajectoryPoint[],
  simTime: number
): number | null {
  const posA = getPositionAtTime(trajA, simTime)
  const posB = getPositionAtTime(trajB, simTime)
  if (!posA || !posB) return null
  // Positions are in unit-sphere scale, multiply by Earth radius to get km
  const dx = (posA.x - posB.x) * EARTH_RADIUS_KM
  const dy = (posA.y - posB.y) * EARTH_RADIUS_KM
  const dz = (posA.z - posB.z) * EARTH_RADIUS_KM
  return Math.sqrt(dx * dx + dy * dy + dz * dz)
}

function formatDistance(km: number): string {
  if (km < 0.001) return `${(km * 1_000_000).toFixed(0)} m`
  if (km < 1) return `${(km * 1000).toFixed(0)} m`
  if (km < 100) return `${km.toFixed(1)} km`
  return `${km.toFixed(0)} km`
}

function formatCountdown(seconds: number): string {
  const abs = Math.abs(seconds)
  const sign = seconds < 0 ? "T-" : "T+"
  const h = Math.floor(abs / 3600)
  const m = Math.floor((abs % 3600) / 60)
  const s = Math.floor(abs % 60)
  if (h > 0) return `${sign}${h}h ${m.toString().padStart(2, "0")}m`
  if (m > 0) return `${sign}${m}m ${s.toString().padStart(2, "0")}s`
  return `${sign}${s}s`
}

// --- 3D Components ---

const TEXTURE_PATH = "/textures/earth/blue-marble-day.jpg"

function Earth() {
  const { gl } = useThree()
  const [surfaceMap, setSurfaceMap] = useState<THREE.Texture | null>(null)

  useEffect(() => {
    let active = true
    const loader = new THREE.TextureLoader()
    loader.load(
      TEXTURE_PATH,
      (texture) => {
        if (!active) { texture.dispose(); return }
        texture.colorSpace = THREE.SRGBColorSpace
        texture.anisotropy = Math.min(8, gl.capabilities.getMaxAnisotropy())
        texture.minFilter = THREE.LinearMipmapLinearFilter
        texture.magFilter = THREE.LinearFilter
        texture.needsUpdate = true
        setSurfaceMap((prev) => { prev?.dispose(); return texture })
      },
    )
    return () => { active = false }
  }, [gl])

  useEffect(() => { return () => { surfaceMap?.dispose() } }, [surfaceMap])

  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        map: surfaceMap ?? undefined,
        color: surfaceMap ? "#ffffff" : "#173b5f",
        toneMapped: false,
      }),
    [surfaceMap]
  )

  useEffect(() => { return () => { material.dispose() } }, [material])

  return (
    <mesh material={material}>
      <sphereGeometry args={[1, 64, 64]} />
    </mesh>
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

/** Animated satellite dot with glow */
function AnimatedObject({
  trajectory,
  simTimeRef,
  color,
  glowColor,
  size = 0.012,
}: {
  trajectory: TrajectoryPoint[]
  simTimeRef: React.RefObject<number>
  color: string
  glowColor: string
  size?: number
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)

  useFrame(() => {
    const pos = getPositionAtTime(trajectory, simTimeRef.current)
    if (!pos) return
    if (meshRef.current) meshRef.current.position.copy(pos)
    if (glowRef.current) glowRef.current.position.copy(pos)
  })

  return (
    <group>
      <mesh ref={meshRef}>
        <sphereGeometry args={[size, 14, 14]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh ref={glowRef}>
        <sphereGeometry args={[size * 2.5, 14, 14]} />
        <meshBasicMaterial color={glowColor} transparent opacity={0.3} />
      </mesh>
    </group>
  )
}

/** Orbit trail line that shows the full trajectory */
function OrbitTrail({
  trajectory,
  color,
  opacity = 0.6,
}: {
  trajectory: TrajectoryPoint[]
  color: string
  opacity?: number
}) {
  const points = useMemo(() => {
    // Sample every N points to keep it performant
    const step = Math.max(1, Math.floor(trajectory.length / 800))
    const pts: [number, number, number][] = []
    for (let i = 0; i < trajectory.length; i += step) {
      const p = trajectory[i]
      const v = geoToVec3(p.lat, p.lon, p.alt_km)
      pts.push([v.x, v.y, v.z])
    }
    return pts
  }, [trajectory])

  if (points.length < 2) return null
  return <Line points={points} color={color} transparent opacity={opacity} lineWidth={1.2} />
}

/** Collision flash effect at impact point */
function CollisionEffect({
  trajectory,
  collisionT,
  simTimeRef,
}: {
  trajectory: TrajectoryPoint[]
  collisionT: number
  simTimeRef: React.RefObject<number>
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const ringRef = useRef<THREE.Mesh>(null)

  useFrame(() => {
    const simTime = simTimeRef.current
    const dt = simTime - collisionT

    // Show effect for 60 seconds around collision
    const visible = dt >= -2 && dt <= 60
    if (meshRef.current) meshRef.current.visible = visible
    if (ringRef.current) ringRef.current.visible = visible

    if (!visible) return

    const pos = getPositionAtTime(trajectory, collisionT)
    if (!pos) return

    if (meshRef.current) {
      meshRef.current.position.copy(pos)
      // Pulsing scale
      const pulse = dt < 0 ? 1 : 1 + Math.sin(dt * 3) * 0.5 * Math.max(0, 1 - dt / 60)
      const baseScale = dt < 0 ? 0.02 : 0.02 + 0.04 * Math.min(1, dt / 5)
      meshRef.current.scale.setScalar(baseScale * pulse)
    }

    if (ringRef.current) {
      ringRef.current.position.copy(pos)
      const expand = dt < 0 ? 0.03 : 0.03 + 0.15 * Math.min(1, dt / 10)
      ringRef.current.scale.setScalar(expand)
      const mat = ringRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = Math.max(0, 0.6 * (1 - dt / 60))
    }
  })

  return (
    <group>
      <mesh ref={meshRef} visible={false}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color="#ff3333" transparent opacity={0.9} />
      </mesh>
      <mesh ref={ringRef} visible={false}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color="#ff6644" transparent opacity={0.6} side={THREE.BackSide} />
      </mesh>
    </group>
  )
}

function SimulationScene({
  scenario,
  simTimeRef,
}: {
  scenario: ScenarioData
  simTimeRef: React.RefObject<number>
}) {
  const { camera } = useThree()

  useEffect(() => {
    camera.position.set(0, 0, 3.5)
  }, [camera])

  return (
    <>
      <Stars radius={110} depth={70} count={2600} factor={13.8} saturation={0} fade speed={0.15} />
      <Stars radius={112} depth={75} count={1400} factor={20.4} saturation={0} fade speed={0.18} />
      <Earth />
      <Graticule />
      <Atmosphere />

      {/* Satellite orbit trail */}
      <OrbitTrail trajectory={scenario.satellite} color="#22d3ee" opacity={0.4} />
      {/* Debris orbit trail */}
      <OrbitTrail trajectory={scenario.debris} color="#f59e0b" opacity={0.4} />

      {/* Animated satellite */}
      <AnimatedObject
        trajectory={scenario.satellite}
        simTimeRef={simTimeRef}
        color="#22d3ee"
        glowColor="#22d3ee"
        size={0.014}
      />

      {/* Animated debris */}
      <AnimatedObject
        trajectory={scenario.debris}
        simTimeRef={simTimeRef}
        color="#f59e0b"
        glowColor="#f59e0b"
        size={0.010}
      />

      {/* Collision flash */}
      <CollisionEffect
        trajectory={scenario.satellite}
        collisionT={scenario.collision_t}
        simTimeRef={simTimeRef}
      />

      <OrbitControls enablePan enableZoom minDistance={1.5} maxDistance={20} enableDamping dampingFactor={0.05} />
    </>
  )
}

// --- Timeline UI ---

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
}

// --- Main Component ---

export function SimulationView() {
  const [scenario, setScenario] = useState<ScenarioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(5)
  const [displayTime, setDisplayTime] = useState(0)

  // Use a ref for simTime so the 3D scene can read it every frame without re-renders
  const simTimeRef = useRef(0)
  const lastFrameRef = useRef<number | null>(null)
  const lastDisplayUpdateRef = useRef(0)
  const speedRef = useRef(speed)
  speedRef.current = speed

  // Fetch scenario data
  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        setLoading(true)
        const res = await fetch(
          "/api/simulation/collision?duration_hours=12&dt_sec=30&collision_hour=6",
          { signal: controller.signal }
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: ScenarioData = await res.json()
        setScenario(data)
        setError(null)
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "Failed to load scenario")
        }
      } finally {
        setLoading(false)
      }
    }

    void load()
    return () => controller.abort()
  }, [])

  // Animation loop (runs outside React render cycle for performance)
  useEffect(() => {
    if (!playing || !scenario) {
      lastFrameRef.current = null
      return
    }

    let rafId: number

    function tick(now: number) {
      if (lastFrameRef.current !== null) {
        const dt = (now - lastFrameRef.current) / 1000 // real seconds elapsed
        simTimeRef.current = Math.min(
          simTimeRef.current + dt * speedRef.current,
          scenario!.duration_sec
        )

        // Update display time ~4 times per second to avoid excessive re-renders
        if (now - lastDisplayUpdateRef.current > 250) {
          lastDisplayUpdateRef.current = now
          setDisplayTime(simTimeRef.current)
        }

        // Stop at end
        if (simTimeRef.current >= scenario!.duration_sec) {
          setDisplayTime(simTimeRef.current)
          setPlaying(false)
          return
        }
      }
      lastFrameRef.current = now
      rafId = requestAnimationFrame(tick)
    }

    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [playing, scenario])

  const handleSeek = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = parseFloat(e.target.value)
      simTimeRef.current = val
      setDisplayTime(val)
    },
    []
  )

  const handleReset = useCallback(() => {
    simTimeRef.current = 0
    setDisplayTime(0)
    setPlaying(false)
  }, [])

  const togglePlay = useCallback(() => {
    if (!scenario) return
    // If at end, reset first
    if (simTimeRef.current >= scenario.duration_sec) {
      simTimeRef.current = 0
      setDisplayTime(0)
    }
    setPlaying((p) => !p)
  }, [scenario])

  const cycleSpeed = useCallback(() => {
    setSpeed((s) => {
      if (s === 1) return 5
      if (s === 5) return 10
      if (s === 10) return 25
      if (s === 25) return 50
      return 1
    })
  }, [])

  // Collision proximity indicator
  const isNearCollision = scenario
    ? Math.abs(displayTime - scenario.collision_t) < 120
    : false
  const isAtCollision = scenario
    ? Math.abs(displayTime - scenario.collision_t) < 5
    : false

  // Distance and countdown
  const distanceKm = scenario
    ? getDistanceKm(scenario.satellite, scenario.debris, displayTime)
    : null
  const countdown = scenario ? displayTime - scenario.collision_t : 0

  if (loading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-black text-white">
        <div className="text-center">
          <div className="mb-4 text-lg font-medium">Computing collision scenario...</div>
          <div className="text-sm text-gray-400">Propagating orbits over 12 hours</div>
        </div>
      </div>
    )
  }

  if (error || !scenario) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-black text-white">
        <div className="text-center">
          <div className="mb-2 text-lg text-red-400">Failed to load scenario</div>
          <div className="text-sm text-gray-400">{error}</div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-black">
      {/* 3D Globe */}
      <Canvas
        className="h-full w-full"
        camera={{ fov: 45, near: 0.1, far: 1000, position: [0, 0, 3.5] }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: "#030303", width: "100%", height: "100%" }}
      >
        <SimulationScene scenario={scenario} simTimeRef={simTimeRef} />
      </Canvas>

      {/* Top info bar */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center justify-between p-6">
        <div className="pointer-events-auto">
          <h1 className="text-lg font-semibold text-white">Collision Simulation</h1>
          <p className="text-xs text-gray-400">
            12-hour window &middot; {scenario.miss_distance_m.toFixed(1)}m closest approach
          </p>
        </div>
        <div className="pointer-events-auto flex items-center gap-3">
          {/* Distance & Countdown HUD */}
          <div className="rounded-lg bg-black/70 px-4 py-2.5 backdrop-blur">
            <div className="mb-1.5 flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-cyan-400" />
                <span className="text-[10px] uppercase tracking-wider text-gray-400">Satellite</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
                <span className="text-[10px] uppercase tracking-wider text-gray-400">Debris</span>
              </div>
            </div>
            <div className="flex items-baseline gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-500">Distance</div>
                <div className={`font-mono text-sm font-semibold ${
                  distanceKm !== null && distanceKm < 1 ? "text-red-400" :
                  distanceKm !== null && distanceKm < 50 ? "text-amber-400" :
                  "text-white"
                }`}>
                  {distanceKm !== null ? formatDistance(distanceKm) : "---"}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-500">TCA</div>
                <div className={`font-mono text-sm font-semibold ${
                  Math.abs(countdown) < 60 ? "text-red-400" :
                  Math.abs(countdown) < 600 ? "text-amber-400" :
                  "text-white"
                }`}>
                  {formatCountdown(countdown)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Collision warning overlay */}
      {isNearCollision && (
        <div
          className={`pointer-events-none absolute inset-x-0 top-20 z-30 text-center transition-opacity duration-300 ${
            isAtCollision ? "opacity-100" : "opacity-70"
          }`}
        >
          <span
            className={`inline-block rounded-lg px-4 py-2 text-sm font-bold uppercase tracking-wider ${
              isAtCollision
                ? "animate-pulse bg-red-600/90 text-white"
                : "bg-red-600/50 text-red-200"
            }`}
          >
            {isAtCollision ? "COLLISION" : "COLLISION IMMINENT"}
          </span>
        </div>
      )}

      {/* Bottom playback controls */}
      <div className="absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/80 to-transparent px-6 pb-6 pt-12">
        {/* Timeline bar */}
        <div className="mx-auto max-w-4xl">
          {/* Collision marker on timeline */}
          <div className="relative mb-1 h-1">
            <div
              className="absolute top-0 h-full w-0.5 bg-red-500"
              style={{
                left: `${(scenario.collision_t / scenario.duration_sec) * 100}%`,
              }}
            />
          </div>

          {/* Seek slider */}
          <input
            type="range"
            min={0}
            max={scenario.duration_sec}
            step={1}
            value={displayTime}
            onChange={handleSeek}
            className="mb-3 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/20 accent-cyan-400 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-cyan-400"
          />

          {/* Controls row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {/* Play/Pause */}
              <button
                onClick={togglePlay}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
              >
                {playing ? <Pause size={16} /> : <Play size={16} />}
              </button>

              {/* Reset */}
              <button
                onClick={handleReset}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
              >
                <RotateCcw size={14} />
              </button>

              {/* Speed */}
              <button
                onClick={cycleSpeed}
                className="rounded-md bg-white/10 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-white/20"
              >
                {speed}x
              </button>
            </div>

            {/* Time display */}
            <div className="font-mono text-sm text-white">
              <span>{formatTime(displayTime)}</span>
              <span className="mx-1 text-gray-500">/</span>
              <span className="text-gray-400">{formatTime(scenario.duration_sec)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

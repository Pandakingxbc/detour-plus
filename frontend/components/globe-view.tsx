"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useThree } from "@react-three/fiber"
import { Line, OrbitControls, Stars } from "@react-three/drei"
import * as THREE from "three"

import { geodeticToUnitVector } from "@/lib/geo"
import { cn } from "@/lib/utils"

const TEXTURE_PATH = "/textures/earth/blue-marble-day.jpg"
const DISPLAY_OBJECT_LIMIT = 900
const DEBRIS_REFRESH_MS = 1000
const DEBRIS_ORBIT_CLASSES = "LEO"

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

function StaticObjects({ positions }: { positions: THREE.Vector3[] }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])

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

  if (positions.length === 0) return null

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, positions.length]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color="#f59e0b" transparent opacity={0.9} />
    </instancedMesh>
  )
}

function OrbitTrack({ points }: { points: THREE.Vector3[] }) {
  if (points.length < 2) return null

  const linePoints = points.map((point) => [point.x, point.y, point.z] as [number, number, number])

  return <Line points={linePoints} color="#7dd3fc" transparent opacity={0.95} lineWidth={1.4} />
}

function TargetMarker({ point }: { point: THREE.Vector3 | null }) {
  if (!point) return null

  return (
    <mesh position={point}>
      <sphereGeometry args={[0.012, 14, 14]} />
      <meshBasicMaterial color="#22d3ee" />
    </mesh>
  )
}

function Scene({ debrisPositions, orbitPoints }: { debrisPositions: THREE.Vector3[]; orbitPoints: THREE.Vector3[] }) {
  const { camera } = useThree()

  useEffect(() => {
    camera.position.set(0, 0, 4)
  }, [camera])

  const currentTargetPoint = orbitPoints[0] ?? null

  return (
    <>
      <Stars radius={110} depth={70} count={2600} factor={13.8} saturation={0} fade speed={0.15} />
      <Stars radius={112} depth={75} count={1400} factor={20.4} saturation={0} fade speed={0.18} />
      <Stars radius={115} depth={80} count={650} factor={25.8} saturation={0} fade speed={0.12} />
      <Earth />
      <Graticule />
      <Atmosphere />
      <OrbitTrack points={orbitPoints} />
      <TargetMarker point={currentTargetPoint} />
      {debrisPositions.length > 0 ? <StaticObjects positions={debrisPositions} /> : null}
      <OrbitControls enablePan enableZoom minDistance={1.5} maxDistance={20} enableDamping dampingFactor={0.05} />
    </>
  )
}

interface GlobeViewProps {
  compacted?: boolean
  noradId?: number | null
}

export function GlobeView({ compacted = false, noradId }: GlobeViewProps) {
  const [debrisPositions, setDebrisPositions] = useState<THREE.Vector3[]>([])
  const [orbitPoints, setOrbitPoints] = useState<THREE.Vector3[]>([])

  useEffect(() => {
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
  }, [])

  useEffect(() => {
    if (!noradId) {
      setOrbitPoints([])
      return
    }

    const controller = new AbortController()

    const loadOrbit = async () => {
      try {
        const response = await fetch(`/api/orbit?norad=${noradId}&minutes=180&stepSec=60`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const payload = (await response.json()) as OrbitResponse
        const points = payload.points
          .map((point) => toVectorFromGeodetic(point.lat, point.lon, point.altKm))
          .filter((value): value is THREE.Vector3 => value !== null)

        setOrbitPoints(points)
      } catch {
        setOrbitPoints([])
      }
    }

    void loadOrbit()

    return () => {
      controller.abort()
    }
  }, [noradId])

  return (
    <div
      className={cn(
        "absolute inset-0 h-full w-full origin-center overflow-hidden transition-transform duration-500 ease-in-out",
        compacted ? "-translate-y-16 scale-[0.7]" : "translate-y-0 scale-100"
      )}
    >
      <Canvas
        className="h-full w-full"
        camera={{ fov: 45, near: 0.1, far: 1000, position: [0, 0, 4] }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: "#030303", width: "100%", height: "100%" }}
      >
        <Scene debrisPositions={debrisPositions} orbitPoints={orbitPoints} />
      </Canvas>
    </div>
  )
}

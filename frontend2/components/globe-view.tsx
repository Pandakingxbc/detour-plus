"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { OrbitControls, Stars } from "@react-three/drei"
import * as THREE from "three"

import { geodeticToUnitVector } from "@/lib/geo"
import { cn } from "@/lib/utils"

const EARTH_RADIUS_M = 6_378_137
const SCALE = 1 / EARTH_RADIUS_M
const TEXTURE_PATH = "/textures/earth/blue-marble-day.jpg"

interface ApiOrbitalObject {
  position?: [number, number, number]
  lat?: number
  lon?: number
  alt_km?: number
  epoch?: string
}

interface MockOrbit {
  radius: number
  inclination: number
  ascendingNode: number
  argumentOfPerigee: number
  phaseAtEpoch: number
  speed: number
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
        // If the local texture is not present yet, keep the fallback material.
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

  const material = useMemo(() => {
    return new THREE.MeshBasicMaterial({
      map: surfaceMap ?? undefined,
      color: surfaceMap ? "#ffffff" : "#173b5f",
      toneMapped: false,
    })
  }, [surfaceMap])

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
      dummy.scale.setScalar(0.0045)
      dummy.updateMatrix()
      mesh.setMatrixAt(index, dummy.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  }, [dummy, positions])

  if (positions.length === 0) return null

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, positions.length]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color="#87bfff" transparent opacity={0.86} />
    </instancedMesh>
  )
}

function MockObjects({ count = 2400 }: { count?: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])

  const orbits = useMemo<MockOrbit[]>(() => {
    return Array.from({ length: count }, () => ({
      radius: 1.04 + Math.random() * 0.32,
      inclination: Math.random() * Math.PI,
      ascendingNode: Math.random() * Math.PI * 2,
      argumentOfPerigee: Math.random() * Math.PI * 2,
      phaseAtEpoch: Math.random() * Math.PI * 2,
      speed: 0.04 + Math.random() * 0.2,
    }))
  }, [count])

  useFrame(({ clock }) => {
    const mesh = meshRef.current
    if (!mesh) return

    const t = clock.elapsedTime
    orbits.forEach((orbit, index) => {
      const u = orbit.phaseAtEpoch + orbit.argumentOfPerigee + t * orbit.speed
      const xOrb = orbit.radius * Math.cos(u)
      const yOrb = orbit.radius * Math.sin(u)

      const cosI = Math.cos(orbit.inclination)
      const sinI = Math.sin(orbit.inclination)
      const cosO = Math.cos(orbit.ascendingNode)
      const sinO = Math.sin(orbit.ascendingNode)

      const x = xOrb * cosO - yOrb * cosI * sinO
      const y = xOrb * sinO + yOrb * cosI * cosO
      const z = yOrb * sinI

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.0043)
      dummy.updateMatrix()
      mesh.setMatrixAt(index, dummy.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, orbits.length]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color="#87bfff" transparent opacity={0.85} />
    </instancedMesh>
  )
}

function Scene({ positions }: { positions: THREE.Vector3[] }) {
  const { camera } = useThree()

  useEffect(() => {
    camera.position.set(0, 0, 4)
  }, [camera])

  return (
    <>
      <Stars radius={100} depth={60} count={4200} factor={3.6} saturation={0} />
      <Earth />
      <Atmosphere />
      {positions.length > 0 ? <StaticObjects positions={positions} /> : <MockObjects />}
      <OrbitControls
        enablePan
        enableZoom
        minDistance={1.5}
        maxDistance={20}
        enableDamping
        dampingFactor={0.05}
      />
    </>
  )
}

function toScaledVector(position: [number, number, number] | undefined): THREE.Vector3 | null {
  if (!position) return null
  const [x, y, z] = position
  if (![x, y, z].every(Number.isFinite)) return null
  const magnitude = Math.sqrt(x * x + y * y + z * z)
  if (magnitude < EARTH_RADIUS_M * 0.9 || magnitude > EARTH_RADIUS_M * 10) return null
  return new THREE.Vector3(x * SCALE, y * SCALE, z * SCALE)
}

function toGeodeticVector(entry: ApiOrbitalObject): THREE.Vector3 | null {
  const lat = entry.lat
  const lon = entry.lon
  const altKm = entry.alt_km ?? 0

  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(altKm)) return null

  const latValue = lat as number
  const lonValue = lon as number
  if (Math.abs(latValue) > 90 || Math.abs(lonValue) > 360) return null

  const cartesian = geodeticToUnitVector(latValue, lonValue, altKm)
  const magnitude = Math.sqrt(
    cartesian.x * cartesian.x +
    cartesian.y * cartesian.y +
    cartesian.z * cartesian.z
  )

  if (magnitude < 0.9 || magnitude > 10) return null

  return new THREE.Vector3(cartesian.x, cartesian.y, cartesian.z)
}

interface GlobeViewProps {
  compacted?: boolean
}

export function GlobeView({ compacted = false }: GlobeViewProps) {
  const [positions, setPositions] = useState<THREE.Vector3[]>([])

  useEffect(() => {
    const controller = new AbortController()
    const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"

    const load = async () => {
      try {
        const response = await fetch(`${apiBase}/objects?limit=3500`, { signal: controller.signal })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const objects = (await response.json()) as ApiOrbitalObject[]
        const scaled = objects
          .map((entry) => toGeodeticVector(entry) ?? toScaledVector(entry.position))
          .filter((value): value is THREE.Vector3 => value !== null)

        if (scaled.length > 0) {
          setPositions(scaled)
          return
        }
      } catch {
        // Keep rendering mock objects when backend data is unavailable.
      }
    }

    void load()
    return () => controller.abort()
  }, [])

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
        <Scene positions={positions} />
      </Canvas>
    </div>
  )
}

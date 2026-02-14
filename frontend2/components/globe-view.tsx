"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { OrbitControls, Stars } from "@react-three/drei"
import * as THREE from "three"

import { cn } from "@/lib/utils"

const EARTH_RADIUS_M = 6_378_137
const SCALE = 1 / EARTH_RADIUS_M

interface ApiOrbitalObject {
  position: [number, number, number]
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
  const meshRef = useRef<THREE.Mesh>(null)

  const material = useMemo(() => {
    const canvas = document.createElement("canvas")
    canvas.width = 1024
    canvas.height = 512
    const ctx = canvas.getContext("2d")
    if (!ctx) {
      return new THREE.MeshPhongMaterial({ color: "#2a4f72" })
    }

    ctx.fillStyle = "#173b5f"
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    ctx.fillStyle = "#375f38"
    ctx.beginPath()
    ctx.ellipse(250, 160, 80, 60, -0.3, 0, Math.PI * 2)
    ctx.fill()
    ctx.beginPath()
    ctx.ellipse(310, 310, 42, 72, 0.2, 0, Math.PI * 2)
    ctx.fill()
    ctx.beginPath()
    ctx.ellipse(520, 200, 52, 82, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.beginPath()
    ctx.ellipse(680, 160, 100, 62, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.beginPath()
    ctx.ellipse(780, 340, 36, 26, 0, 0, Math.PI * 2)
    ctx.fill()

    ctx.strokeStyle = "rgba(150, 190, 220, 0.14)"
    ctx.lineWidth = 0.5
    for (let i = 0; i < 36; i += 1) {
      ctx.beginPath()
      ctx.moveTo((i / 36) * canvas.width, 0)
      ctx.lineTo((i / 36) * canvas.width, canvas.height)
      ctx.stroke()
    }
    for (let i = 0; i < 18; i += 1) {
      ctx.beginPath()
      ctx.moveTo(0, (i / 18) * canvas.height)
      ctx.lineTo(canvas.width, (i / 18) * canvas.height)
      ctx.stroke()
    }

    const texture = new THREE.CanvasTexture(canvas)
    return new THREE.MeshPhongMaterial({
      map: texture,
      specular: new THREE.Color(0x2f2f2f),
      shininess: 14,
    })
  }, [])

  useFrame(() => {
    if (meshRef.current) meshRef.current.rotation.y += 0.0002
  })

  return (
    <mesh ref={meshRef} material={material}>
      <sphereGeometry args={[1, 64, 64]} />
    </mesh>
  )
}

function Atmosphere() {
  return (
    <mesh>
      <sphereGeometry args={[1.015, 64, 64]} />
      <meshPhongMaterial color="#73a5ff" transparent opacity={0.08} side={THREE.BackSide} />
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
      // Orbital-plane angle.
      const u = orbit.phaseAtEpoch + orbit.argumentOfPerigee + t * orbit.speed
      const xOrb = orbit.radius * Math.cos(u)
      const yOrb = orbit.radius * Math.sin(u)

      // Rotate from orbital plane into ECI-like frame by inclination + RAAN.
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
      <ambientLight intensity={0.35} />
      <directionalLight position={[5, 3, 5]} intensity={1.2} />
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

function toScaledVector(position: [number, number, number]): THREE.Vector3 | null {
  const [x, y, z] = position
  if (![x, y, z].every(Number.isFinite)) return null
  const magnitude = Math.sqrt(x * x + y * y + z * z)
  if (magnitude < EARTH_RADIUS_M * 0.9 || magnitude > EARTH_RADIUS_M * 10) return null
  return new THREE.Vector3(x * SCALE, y * SCALE, z * SCALE)
}

interface GlobeViewProps {
  compacted?: boolean
}

export function GlobeView({ compacted = false }: GlobeViewProps) {
  const [positions, setPositions] = useState<THREE.Vector3[]>([])
  const [mode, setMode] = useState<"live" | "mock">("mock")

  useEffect(() => {
    const controller = new AbortController()
    const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"

    const load = async () => {
      try {
        const response = await fetch(`${apiBase}/objects?limit=3500`, { signal: controller.signal })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)

        const objects = (await response.json()) as ApiOrbitalObject[]
        const scaled = objects
          .map((entry) => toScaledVector(entry.position))
          .filter((value): value is THREE.Vector3 => value !== null)

        if (scaled.length > 0) {
          setPositions(scaled)
          setMode("live")
          return
        }
        setMode("mock")
      } catch {
        setMode("mock")
      }
    }

    void load()
    return () => controller.abort()
  }, [])

  return (
    <div
      className={cn(
        "absolute inset-0 origin-center transition-transform duration-500 ease-in-out",
        compacted ? "-translate-y-10 scale-95" : "translate-y-0 scale-100"
      )}
    >
      <Canvas
        camera={{ fov: 45, near: 0.1, far: 1000, position: [0, 0, 4] }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: "#030303" }}
      >
        <Scene positions={positions} />
      </Canvas>
      <div
        className={cn(
          "pointer-events-none absolute left-3 rounded-md bg-black/55 px-2 py-1 text-xs text-gray-400 transition-[bottom] duration-500 ease-in-out",
          compacted ? "bottom-64" : "bottom-3"
        )}
      >
        Orbit objects: {mode === "live" ? "Live backend feed" : "Mock mode fallback"}
      </div>
    </div>
  )
}

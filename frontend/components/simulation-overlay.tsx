"use client"

import { useMemo, useRef } from "react"
import { useFrame } from "@react-three/fiber"
import { Line } from "@react-three/drei"
import * as THREE from "three"

import {
  geoToVec3,
  getPositionAtTime,
} from "@/lib/simulation-helpers"
import type { ScenarioData, TrajectoryPoint } from "@/lib/simulation-types"

/** Animated satellite — large bright core + pulsing cyan glow + outer halo */
function AnimatedSatellite({
  trajectory,
  simTimeRef,
}: {
  trajectory: TrajectoryPoint[]
  simTimeRef: React.RefObject<number>
}) {
  const coreRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)
  const outerRef = useRef<THREE.Mesh>(null)

  useFrame(({ clock }) => {
    const pos = getPositionAtTime(trajectory, simTimeRef.current)
    if (!pos) return

    if (coreRef.current) coreRef.current.position.copy(pos)

    if (glowRef.current) {
      glowRef.current.position.copy(pos)
      const pulse = 1 + Math.sin(clock.elapsedTime * 3) * 0.15
      glowRef.current.scale.setScalar(pulse)
    }

    if (outerRef.current) {
      outerRef.current.position.copy(pos)
      const pulse = 1 + Math.sin(clock.elapsedTime * 2) * 0.1
      outerRef.current.scale.setScalar(pulse)
    }
  })

  return (
    <group>
      {/* Bright white core */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.022, 14, 14]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
      {/* Inner cyan glow */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[0.06, 14, 14]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.4} />
      </mesh>
      {/* Outer halo */}
      <mesh ref={outerRef}>
        <sphereGeometry args={[0.12, 14, 14]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.12} />
      </mesh>
    </group>
  )
}

/** Static orbit trail line for satellite */
function OrbitTrail({
  trajectory,
  color,
  opacity = 0.5,
}: {
  trajectory: TrajectoryPoint[]
  color: string
  opacity?: number
}) {
  const points = useMemo(() => {
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

/** Red danger line from satellite to collision point — appears before collision */
function DangerLine({
  trajectory,
  collisionLat,
  collisionLon,
  collisionAltKm,
  collisionT,
  simTimeRef,
}: {
  trajectory: TrajectoryPoint[]
  collisionLat: number
  collisionLon: number
  collisionAltKm: number
  collisionT: number
  simTimeRef: React.RefObject<number>
}) {
  const lineRef = useRef<THREE.Group>(null)
  const collisionPos = useMemo(
    () => geoToVec3(collisionLat, collisionLon, collisionAltKm),
    [collisionLat, collisionLon, collisionAltKm]
  )

  // We draw this imperatively since both endpoints move
  const geomRef = useRef<THREE.BufferGeometry>(null)
  const matRef = useRef<THREE.LineBasicMaterial>(null)

  useFrame(({ clock }) => {
    const simTime = simTimeRef.current
    const timeToCollision = collisionT - simTime

    // Show the danger line starting 300s before collision
    const visible = timeToCollision > -5 && timeToCollision < 300
    if (lineRef.current) lineRef.current.visible = visible
    if (!visible) return

    const satPos = getPositionAtTime(trajectory, simTime)
    if (!satPos || !geomRef.current || !matRef.current) return

    // Update line endpoints
    const positions = geomRef.current.attributes.position as THREE.BufferAttribute
    positions.setXYZ(0, satPos.x, satPos.y, satPos.z)
    positions.setXYZ(1, collisionPos.x, collisionPos.y, collisionPos.z)
    positions.needsUpdate = true

    // Pulsing opacity — faster as collision approaches
    const urgency = Math.max(0, 1 - timeToCollision / 300)
    const pulseSpeed = 2 + urgency * 6
    const baseOpacity = 0.3 + urgency * 0.5
    const pulse = baseOpacity + Math.sin(clock.elapsedTime * pulseSpeed) * 0.15
    matRef.current.opacity = Math.min(1, pulse)
  })

  return (
    <group ref={lineRef} visible={false}>
      <line>
        <bufferGeometry ref={geomRef}>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array(6), 3]}
          />
        </bufferGeometry>
        <lineBasicMaterial ref={matRef} color="#ff3333" transparent opacity={0.5} linewidth={1} />
      </line>
      {/* Collision target marker (red dot at debris position) */}
      <mesh position={collisionPos}>
        <sphereGeometry args={[0.015, 12, 12]} />
        <meshBasicMaterial color="#ff3333" transparent opacity={0.8} />
      </mesh>
    </group>
  )
}

/** Collision flash + expanding ring at impact point */
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

    const visible = dt >= -2 && dt <= 60
    if (meshRef.current) meshRef.current.visible = visible
    if (ringRef.current) ringRef.current.visible = visible
    if (!visible) return

    const pos = getPositionAtTime(trajectory, collisionT)
    if (!pos) return

    if (meshRef.current) {
      meshRef.current.position.copy(pos)
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

/** Top-level overlay group — renders inside the existing Canvas/Scene */
export function SimulationOverlay({
  scenario,
  simTimeRef,
}: {
  scenario: ScenarioData
  simTimeRef: React.RefObject<number>
}) {
  return (
    <group>
      <OrbitTrail trajectory={scenario.satellite} color="#22d3ee" opacity={0.4} />

      <AnimatedSatellite
        trajectory={scenario.satellite}
        simTimeRef={simTimeRef}
      />

      <DangerLine
        trajectory={scenario.satellite}
        collisionLat={scenario.collision_lat}
        collisionLon={scenario.collision_lon}
        collisionAltKm={scenario.collision_alt_km}
        collisionT={scenario.collision_t}
        simTimeRef={simTimeRef}
      />

      <CollisionEffect
        trajectory={scenario.satellite}
        collisionT={scenario.collision_t}
        simTimeRef={simTimeRef}
      />
    </group>
  )
}

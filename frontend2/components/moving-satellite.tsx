"use client"

import { useEffect, useMemo, useRef } from "react"
import { useFrame } from "@react-three/fiber"
import * as THREE from "three"

const EARTH_RADIUS_M = 6_378_137
const SCALE = 1 / EARTH_RADIUS_M

interface TrajectoryData {
  times: number[]
  positions: number[][]
  velocities: number[][]
}

interface MovingSatelliteProps {
  trajectory: TrajectoryData | null
  color?: string
  size?: number
  speed?: number // Speed multiplier (default 10x)
}

export function MovingSatellite({
  trajectory,
  color = "#ff6b6b",
  size = 0.012,
  speed = 10, // 10x speed by default
}: MovingSatelliteProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const trailRef = useRef<THREE.Line>(null)
  const startTimeRef = useRef<number>(0)

  // Convert trajectory positions to Three.js vectors
  const scaledPositions = useMemo(() => {
    if (!trajectory) return []
    console.log(`🛰️ Trajectory loaded: ${trajectory.positions.length} points`)
    const positions = trajectory.positions.map(([x, y, z]) => {
      return new THREE.Vector3(x * SCALE, y * SCALE, z * SCALE)
    })
    console.log(`📍 First position:`, positions[0])
    console.log(`📍 Last position:`, positions[positions.length - 1])
    return positions
  }, [trajectory])

  // Create trail geometry
  const trailGeometry = useMemo(() => {
    if (scaledPositions.length === 0) return null
    const geometry = new THREE.BufferGeometry()
    const positions = new Float32Array(scaledPositions.length * 3)
    scaledPositions.forEach((pos, i) => {
      positions[i * 3] = pos.x
      positions[i * 3 + 1] = pos.y
      positions[i * 3 + 2] = pos.z
    })
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
    return geometry
  }, [scaledPositions])

  useEffect(() => {
    startTimeRef.current = Date.now() / 1000
  }, [trajectory])

  useFrame(({ clock }) => {
    if (!trajectory || scaledPositions.length === 0 || !meshRef.current) return

    // Calculate current position index based on elapsed time (with speed multiplier)
    const elapsedTime = clock.elapsedTime * speed
    const totalDuration = trajectory.times[trajectory.times.length - 1]
    const loopTime = elapsedTime % totalDuration

    // Find the two closest time points
    let index = 0
    for (let i = 0; i < trajectory.times.length - 1; i++) {
      if (loopTime >= trajectory.times[i] && loopTime <= trajectory.times[i + 1]) {
        index = i
        break
      }
    }

    // Interpolate between positions
    if (index < trajectory.times.length - 1) {
      const t0 = trajectory.times[index]
      const t1 = trajectory.times[index + 1]
      const alpha = (loopTime - t0) / (t1 - t0)

      const pos0 = scaledPositions[index]
      const pos1 = scaledPositions[index + 1]

      meshRef.current.position.lerpVectors(pos0, pos1, alpha)
    } else {
      meshRef.current.position.copy(scaledPositions[index])
    }
  })

  if (!trajectory || scaledPositions.length === 0) return null

  return (
    <group>
      {/* Moving satellite */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[size, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>

      {/* Orbital trail */}
      {trailGeometry && (
        <line ref={trailRef} geometry={trailGeometry}>
          <lineBasicMaterial color={color} opacity={0.3} transparent linewidth={1} />
        </line>
      )}
    </group>
  )
}

"use client"

import { useEffect, useMemo, useRef, useState } from "react"
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
  const trailRef = useRef<THREE.Mesh>(null)
  const startTimeRef = useRef<number>(0)
  const [isHovered, setIsHovered] = useState(false)

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

  // Create trail geometry as a tube for thickness
  const trailGeometry = useMemo(() => {
    if (scaledPositions.length < 2) return null

    // Use the positions as-is without forcing closure
    // CatmullRomCurve3 with 'centripetal' for better orbital shapes
    const curve = new THREE.CatmullRomCurve3(scaledPositions, false, 'centripetal')

    // Create tube geometry along the curve with dynamic thickness
    const tubeGeometry = new THREE.TubeGeometry(
      curve,
      scaledPositions.length * 2, // segments
      isHovered ? 0.006 : 0.003, // radius (thicker when hovered)
      8, // radial segments
      false // not closed
    )

    return tubeGeometry
  }, [scaledPositions, isHovered])

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
    <group
      onPointerEnter={() => setIsHovered(true)}
      onPointerLeave={() => setIsHovered(false)}
    >
      {/* Moving satellite */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[isHovered ? size * 1.3 : size, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>

      {/* Orbital trail as tube */}
      {trailGeometry && (
        <mesh ref={trailRef} geometry={trailGeometry}>
          <meshBasicMaterial
            color={color}
            opacity={isHovered ? 0.7 : 0.4}
            transparent
          />
        </mesh>
      )}
    </group>
  )
}

"use client"

import { useMemo, useRef } from "react"
import { useFrame, useThree } from "@react-three/fiber"
import * as THREE from "three"

import type { SimEngine } from "@/lib/sim-engine"

// --- Animated satellite with cyan glow ---
function AnimatedSatelliteV2({ engine }: { engine: SimEngine }) {
  const coreRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)
  const outerRef = useRef<THREE.Mesh>(null)
  const flashRef = useRef<THREE.Mesh>(null)
  const lastMoveCount = useRef(0)
  const flashTimer = useRef(0)

  useFrame(({ clock }) => {
    const p = engine.getSatelliteVec3()

    if (coreRef.current) coreRef.current.position.set(p.x, p.y, p.z)

    if (glowRef.current) {
      glowRef.current.position.set(p.x, p.y, p.z)
      const pulse = 1 + Math.sin(clock.elapsedTime * 3) * 0.15
      glowRef.current.scale.setScalar(pulse)
    }

    if (outerRef.current) {
      outerRef.current.position.set(p.x, p.y, p.z)
      const pulse = 1 + Math.sin(clock.elapsedTime * 2) * 0.1
      outerRef.current.scale.setScalar(pulse)
    }

    // Flash on new move
    const moveCount = engine.state.moveHistory.length
    if (moveCount > lastMoveCount.current && moveCount > 0) {
      lastMoveCount.current = moveCount
      flashTimer.current = 0.3 // flash duration in seconds
      if (flashRef.current) {
        const lastMove = engine.state.moveHistory[moveCount - 1]
        const from = engine.getMoveVec3({
          ...lastMove,
          toLat: lastMove.fromLat,
          toLon: lastMove.fromLon,
        })
        flashRef.current.position.set(from.x, from.y, from.z)
      }
    }

    if (flashRef.current) {
      if (flashTimer.current > 0) {
        flashTimer.current -= 1 / 60
        flashRef.current.visible = true
        const mat = flashRef.current.material as THREE.MeshBasicMaterial
        mat.opacity = flashTimer.current / 0.3
        const scale = 0.04 + (1 - flashTimer.current / 0.3) * 0.06
        flashRef.current.scale.setScalar(scale)
      } else {
        flashRef.current.visible = false
      }
    }
  })

  return (
    <group>
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.012, 14, 14]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
      <mesh ref={glowRef}>
        <sphereGeometry args={[0.032, 14, 14]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.45} />
      </mesh>
      <mesh ref={outerRef}>
        <sphereGeometry args={[0.06, 14, 14]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.15} />
      </mesh>
      {/* Move flash */}
      <mesh ref={flashRef} visible={false}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.6} />
      </mesh>
    </group>
  )
}

// --- Debris cluster: fast-moving orange particles ---
function DebrisCluster({ engine }: { engine: SimEngine }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const count = engine.config.debrisCount

  useFrame(() => {
    const mesh = meshRef.current
    if (!mesh) return

    for (let i = 0; i < engine.state.debris.length; i++) {
      const p = engine.getDebrisVec3(i)

      dummy.position.set(p.x, p.y, p.z)
      dummy.scale.setScalar(0.0063) // match static debris size
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color="#f59e0b" transparent opacity={0.95} />
    </instancedMesh>
  )
}

// --- Danger line: red line from satellite to nearest threat ---
function DangerLineV2({ engine }: { engine: SimEngine }) {
  const lineRef = useRef<THREE.Group>(null)
  const geomRef = useRef<THREE.BufferGeometry>(null)
  const matRef = useRef<THREE.LineBasicMaterial>(null)
  const dotRef = useRef<THREE.Mesh>(null)

  useFrame(({ clock }) => {
    const target = engine.getDangerTargetVec3()
    const satPos = engine.getSatelliteVec3()
    const dist = engine.state.dangerDistance

    // Only show when danger is somewhat close
    const visible = target !== null && dist !== null && dist < 0.2
    if (lineRef.current) lineRef.current.visible = visible
    if (!visible || !target || !geomRef.current || !matRef.current) return

    // Update line endpoints
    const positions = geomRef.current.attributes.position as THREE.BufferAttribute
    positions.setXYZ(0, satPos.x, satPos.y, satPos.z)
    positions.setXYZ(1, target.x, target.y, target.z)
    positions.needsUpdate = true

    // Pulsing — faster as closer
    const urgency = Math.max(0, 1 - (dist ?? 1) / 0.2)
    const pulseSpeed = 2 + urgency * 8
    const baseOpacity = 0.3 + urgency * 0.5
    const pulse = baseOpacity + Math.sin(clock.elapsedTime * pulseSpeed) * 0.2
    matRef.current.opacity = Math.min(1, pulse)

    // Danger dot at target
    if (dotRef.current) {
      dotRef.current.position.set(target.x, target.y, target.z)
      dotRef.current.visible = true
    }
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
      <mesh ref={dotRef} visible={false}>
        <sphereGeometry args={[0.015, 12, 12]} />
        <meshBasicMaterial color="#ff3333" transparent opacity={0.9} />
      </mesh>
    </group>
  )
}

// --- Cardinal move trail: staircase path ---
function CardinalMoveTrail({ engine }: { engine: SimEngine }) {
  const groupRef = useRef<THREE.Group>(null)
  const lineObjRef = useRef<THREE.Line | null>(null)
  const MAX_TRAIL_POINTS = 200

  // Pre-allocate buffer
  const positionArray = useMemo(() => new Float32Array(MAX_TRAIL_POINTS * 3), [])

  // Create line object imperatively to avoid SVG line type conflict
  useMemo(() => {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute("position", new THREE.BufferAttribute(positionArray, 3))
    geometry.setDrawRange(0, 0)
    const material = new THREE.LineBasicMaterial({ color: "#22d3ee", transparent: true, opacity: 0.5 })
    lineObjRef.current = new THREE.Line(geometry, material)
  }, [positionArray])

  useFrame(() => {
    const group = groupRef.current
    const lineObj = lineObjRef.current
    if (!group || !lineObj) return

    // Ensure line is added to group
    if (!lineObj.parent) {
      group.add(lineObj)
    }

    const history = engine.state.moveHistory
    const n = Math.min(history.length, MAX_TRAIL_POINTS - 1)

    if (n < 1) {
      lineObj.geometry.setDrawRange(0, 0)
      return
    }

    // Build trail: start from first move's fromPos, then each move's toPos
    const first = history[history.length - n]
    const startVec = engine.getMoveVec3({
      ...first,
      toLat: first.fromLat,
      toLon: first.fromLon,
    })
    positionArray[0] = startVec.x
    positionArray[1] = startVec.y
    positionArray[2] = startVec.z

    for (let i = 0; i < n; i++) {
      const move = history[history.length - n + i]
      const p = engine.getMoveVec3(move)
      positionArray[(i + 1) * 3] = p.x
      positionArray[(i + 1) * 3 + 1] = p.y
      positionArray[(i + 1) * 3 + 2] = p.z
    }

    const attr = lineObj.geometry.attributes.position as THREE.BufferAttribute
    attr.needsUpdate = true
    lineObj.geometry.setDrawRange(0, n + 1)
  })

  return <group ref={groupRef} />
}

// --- Collision effect: sharp flash → clean fade ---
function CollisionEffectV2({ engine }: { engine: SimEngine }) {
  const coreRef = useRef<THREE.Mesh>(null)
  const ringRef = useRef<THREE.Mesh>(null)
  const startTime = useRef<number | null>(null)

  useFrame(({ clock }) => {
    if (!engine.state.collided) {
      if (coreRef.current) coreRef.current.visible = false
      if (ringRef.current) ringRef.current.visible = false
      startTime.current = null
      return
    }

    if (startTime.current === null) {
      startTime.current = clock.elapsedTime
    }

    const dt = clock.elapsedTime - startTime.current

    // Quick 4-second effect: sharp flash then clean fade
    if (dt > 4) {
      if (coreRef.current) coreRef.current.visible = false
      if (ringRef.current) ringRef.current.visible = false
      return
    }

    const pos = engine.getSatelliteVec3()

    // Core: bright initial flash, quickly shrinks and fades
    if (coreRef.current) {
      coreRef.current.visible = true
      coreRef.current.position.set(pos.x, pos.y, pos.z)
      const t = Math.min(1, dt / 0.3) // ramp up in 0.3s
      const fadeOut = Math.max(0, 1 - (dt - 0.3) / 3.7)
      const scale = 0.02 + 0.05 * t * fadeOut
      coreRef.current.scale.setScalar(scale)
      const mat = coreRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.95 * fadeOut
    }

    // Ring: expands outward, fades
    if (ringRef.current) {
      ringRef.current.visible = true
      ringRef.current.position.set(pos.x, pos.y, pos.z)
      const expand = 0.02 + 0.12 * Math.min(1, dt / 1.5)
      ringRef.current.scale.setScalar(expand)
      const mat = ringRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = Math.max(0, 0.5 * (1 - dt / 4))
    }
  })

  return (
    <group>
      <mesh ref={coreRef} visible={false}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color="#ef4444" transparent opacity={0.95} />
      </mesh>
      <mesh ref={ringRef} visible={false}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color="#f87171" transparent opacity={0.5} side={THREE.BackSide} />
      </mesh>
    </group>
  )
}

// --- Camera follow: smoothly track satellite ---
function CameraFollow({ engine }: { engine: SimEngine }) {
  const { camera } = useThree()
  const initialized = useRef(false)

  useFrame(() => {
    const p = engine.getSatelliteVec3()
    const target = new THREE.Vector3(p.x, p.y, p.z)

    if (!initialized.current) {
      // On first frame, snap camera to satellite at a close zoom
      const dir = target.clone().normalize()
      camera.position.copy(dir.multiplyScalar(2.8))
      camera.lookAt(target)
      initialized.current = true
      return
    }

    // Smoothly follow — camera looks at satellite, gently drifts position
    const dir = target.clone().normalize()
    const desiredPos = dir.clone().multiplyScalar(camera.position.length())
    camera.position.lerp(desiredPos, 0.02)
    camera.lookAt(0, 0, 0) // always look at Earth center so globe stays oriented
  })

  return null
}

// --- Top-level overlay ---
export function SimulationOverlayV2({ engine }: { engine: SimEngine }) {
  return (
    <group>
      <CameraFollow engine={engine} />
      <DebrisCluster engine={engine} />
      <AnimatedSatelliteV2 engine={engine} />
      <DangerLineV2 engine={engine} />
      <CardinalMoveTrail engine={engine} />
      <CollisionEffectV2 engine={engine} />
    </group>
  )
}

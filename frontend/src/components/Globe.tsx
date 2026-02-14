import { useRef, useMemo, useEffect } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Stars } from '@react-three/drei'
import * as THREE from 'three'
import { useStore, type OrbitalObject, type Trajectory } from '../store/useStore'

const EARTH_RADIUS = 6378137.0 // meters
const SCALE = 1 / EARTH_RADIUS // normalize so Earth radius = 1

function riskColor(level: string): string {
  switch (level) {
    case 'critical': return '#ef4444'
    case 'high': return '#f97316'
    case 'medium': return '#eab308'
    default: return '#22c55e'
  }
}

function Earth() {
  const meshRef = useRef<THREE.Mesh>(null)

  // Create Earth with a procedural texture
  const earthMaterial = useMemo(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 1024
    canvas.height = 512
    const ctx = canvas.getContext('2d')!

    // Ocean base
    ctx.fillStyle = '#1a3a5c'
    ctx.fillRect(0, 0, 1024, 512)

    // Simple continents (very approximate shapes for visual effect)
    ctx.fillStyle = '#2d5a27'
    // North America
    ctx.beginPath()
    ctx.ellipse(250, 160, 80, 60, -0.3, 0, Math.PI * 2)
    ctx.fill()
    // South America
    ctx.beginPath()
    ctx.ellipse(310, 310, 40, 70, 0.2, 0, Math.PI * 2)
    ctx.fill()
    // Europe/Africa
    ctx.beginPath()
    ctx.ellipse(520, 200, 50, 80, 0, 0, Math.PI * 2)
    ctx.fill()
    // Asia
    ctx.beginPath()
    ctx.ellipse(680, 160, 100, 60, 0, 0, Math.PI * 2)
    ctx.fill()
    // Australia
    ctx.beginPath()
    ctx.ellipse(780, 340, 35, 25, 0, 0, Math.PI * 2)
    ctx.fill()

    // Grid lines
    ctx.strokeStyle = 'rgba(100, 150, 200, 0.15)'
    ctx.lineWidth = 0.5
    for (let i = 0; i < 36; i++) {
      ctx.beginPath()
      ctx.moveTo((i / 36) * 1024, 0)
      ctx.lineTo((i / 36) * 1024, 512)
      ctx.stroke()
    }
    for (let i = 0; i < 18; i++) {
      ctx.beginPath()
      ctx.moveTo(0, (i / 18) * 512)
      ctx.lineTo(1024, (i / 18) * 512)
      ctx.stroke()
    }

    const texture = new THREE.CanvasTexture(canvas)
    return new THREE.MeshPhongMaterial({
      map: texture,
      specular: new THREE.Color(0x333333),
      shininess: 15,
    })
  }, [])

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.rotation.y += 0.0002
    }
  })

  return (
    <mesh ref={meshRef} material={earthMaterial}>
      <sphereGeometry args={[1, 64, 64]} />
    </mesh>
  )
}

function Atmosphere() {
  return (
    <mesh>
      <sphereGeometry args={[1.015, 64, 64]} />
      <meshPhongMaterial
        color="#4488ff"
        transparent
        opacity={0.08}
        side={THREE.BackSide}
      />
    </mesh>
  )
}

interface SatelliteDotsProps {
  objects: OrbitalObject[]
  onSelect: (obj: OrbitalObject) => void
}

function SatelliteDots({ objects, onSelect }: SatelliteDotsProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const colorRef = useRef<Float32Array>()
  const dummy = useMemo(() => new THREE.Object3D(), [])

  const validObjects = useMemo(
    () => objects.filter(o => {
      const r = Math.sqrt(o.position[0] ** 2 + o.position[1] ** 2 + o.position[2] ** 2)
      return r > EARTH_RADIUS * 0.9 && r < EARTH_RADIUS * 10
    }),
    [objects]
  )

  useEffect(() => {
    if (!meshRef.current || validObjects.length === 0) return

    const colors = new Float32Array(validObjects.length * 3)
    const dotColor = new THREE.Color('#60a5fa')

    validObjects.forEach((obj, i) => {
      const x = obj.position[0] * SCALE
      const y = obj.position[1] * SCALE
      const z = obj.position[2] * SCALE

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.008) // exaggerated for visibility
      dummy.updateMatrix()
      meshRef.current!.setMatrixAt(i, dummy.matrix)

      dotColor.toArray(colors, i * 3)
    })

    colorRef.current = colors
    meshRef.current.instanceMatrix.needsUpdate = true
    meshRef.current.geometry.setAttribute(
      'color',
      new THREE.InstancedBufferAttribute(colors, 3)
    )
  }, [validObjects, dummy])

  if (validObjects.length === 0) return null

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, validObjects.length]}
      onClick={(e) => {
        if (e.instanceId !== undefined && e.instanceId < validObjects.length) {
          onSelect(validObjects[e.instanceId])
        }
      }}
    >
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color="#60a5fa" transparent opacity={0.9} />
    </instancedMesh>
  )
}

function OrbitLine({ trajectory }: { trajectory: Trajectory }) {
  const points = useMemo(() => {
    return trajectory.positions.map(
      p => new THREE.Vector3(p[0] * SCALE, p[1] * SCALE, p[2] * SCALE)
    )
  }, [trajectory])

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    return geo
  }, [points])

  return (
    <line geometry={geometry}>
      <lineBasicMaterial color="#fbbf24" linewidth={2} transparent opacity={0.7} />
    </line>
  )
}

function PostManeuverLine({ trajectory }: { trajectory: Trajectory }) {
  const points = useMemo(() => {
    return trajectory.positions.map(
      p => new THREE.Vector3(p[0] * SCALE, p[1] * SCALE, p[2] * SCALE)
    )
  }, [trajectory])

  const geometry = useMemo(() => {
    return new THREE.BufferGeometry().setFromPoints(points)
  }, [points])

  return (
    <line geometry={geometry}>
      <lineBasicMaterial color="#22c55e" linewidth={2} transparent opacity={0.7} />
    </line>
  )
}

function ConjunctionMarkers() {
  const conjunctions = useStore(s => s.conjunctions)
  const objects = useStore(s => s.objects)
  const meshRef = useRef<THREE.Group>(null)

  useFrame(({ clock }) => {
    if (meshRef.current) {
      meshRef.current.children.forEach((child, i) => {
        const scale = 0.015 + Math.sin(clock.elapsedTime * 3 + i) * 0.005
        child.scale.setScalar(scale)
      })
    }
  })

  const markers = useMemo(() => {
    return conjunctions.slice(0, 20).map(event => {
      const secondary = objects.find(o => o.norad_id === event.secondary_id)
      if (!secondary) return null
      return {
        ...event,
        position: secondary.position.map(p => p * SCALE) as [number, number, number],
      }
    }).filter(Boolean)
  }, [conjunctions, objects])

  return (
    <group ref={meshRef}>
      {markers.map((marker) => marker && (
        <mesh key={marker.event_id} position={marker.position}>
          <sphereGeometry args={[1, 12, 12]} />
          <meshBasicMaterial
            color={riskColor(marker.risk_level)}
            transparent
            opacity={0.8}
          />
        </mesh>
      ))}
    </group>
  )
}

function Scene() {
  const objects = useStore(s => s.objects)
  const selectedTrajectory = useStore(s => s.selectedTrajectory)
  const postManeuverTrajectory = useStore(s => s.postManeuverTrajectory)
  const setSelectedObject = useStore(s => s.setSelectedObject)
  const { camera } = useThree()

  useEffect(() => {
    camera.position.set(0, 0, 4)
  }, [camera])

  return (
    <>
      <ambientLight intensity={0.3} />
      <directionalLight position={[5, 3, 5]} intensity={1.2} />
      <Stars radius={100} depth={50} count={3000} factor={3} saturation={0} />
      <Earth />
      <Atmosphere />
      <SatelliteDots objects={objects} onSelect={setSelectedObject} />
      <ConjunctionMarkers />
      {selectedTrajectory && <OrbitLine trajectory={selectedTrajectory} />}
      {postManeuverTrajectory && <PostManeuverLine trajectory={postManeuverTrajectory} />}
      <OrbitControls
        enablePan={true}
        enableZoom={true}
        minDistance={1.5}
        maxDistance={20}
        enableDamping
        dampingFactor={0.05}
      />
    </>
  )
}

export default function Globe() {
  return (
    <div className="relative w-full h-full">
      <Canvas
        camera={{ fov: 45, near: 0.1, far: 1000, position: [0, 0, 4] }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: '#0a0e1a' }}
      >
        <Scene />
      </Canvas>
      {/* Scale disclaimer */}
      <div className="absolute bottom-2 left-2 text-xs text-gray-500 bg-black/50 px-2 py-1 rounded max-w-sm">
        Object sizes exaggerated for visibility. Actual objects are &lt;10m in a 6,371km radius Earth.
      </div>
    </div>
  )
}

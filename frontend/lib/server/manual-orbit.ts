type Vec3 = [number, number, number]

const EARTH_RADIUS_M = 6_371_000
const EARTH_GM_M3_S2 = 398_600.4418e9

interface ManualTrajectoryInput {
  altitude_km: number
  speed_mps: number
  inclination_deg?: number
  raan_deg?: number
  duration_sec?: number
  dt?: number
}

interface ManualManeuverInput {
  position: number[]
  velocity: number[]
  direction: "radial-out" | "radial-in" | "prograde" | "retrograde"
  delta_v_magnitude: number
}

function assertFinite(value: number, label: string): void {
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`)
  }
}

function norm(v: Vec3): number {
  return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
}

function normalize(v: Vec3, label: string): Vec3 {
  const n = norm(v)
  if (n <= 0) throw new Error(`Cannot normalize ${label}`)
  return [v[0] / n, v[1] / n, v[2] / n]
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ]
}

function add(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}

function scale(v: Vec3, s: number): Vec3 {
  return [v[0] * s, v[1] * s, v[2] * s]
}

function rotateOrbitalToEci(vector: Vec3, inclinationRad: number, raanRad: number): Vec3 {
  const cosI = Math.cos(inclinationRad)
  const sinI = Math.sin(inclinationRad)
  const cosRaan = Math.cos(raanRad)
  const sinRaan = Math.sin(raanRad)

  // Inclination rotation around X
  const x1 = vector[0]
  const y1 = vector[1] * cosI - vector[2] * sinI
  const z1 = vector[1] * sinI + vector[2] * cosI

  // RAAN rotation around Z
  const x2 = x1 * cosRaan - y1 * sinRaan
  const y2 = x1 * sinRaan + y1 * cosRaan
  const z2 = z1

  return [x2, y2, z2]
}

function accelerationGravity(position: Vec3): Vec3 {
  const r = norm(position)
  if (r <= 0) throw new Error("Invalid position norm")
  const factor = -EARTH_GM_M3_S2 / (r * r * r)
  return [position[0] * factor, position[1] * factor, position[2] * factor]
}

function rk4Step(position: Vec3, velocity: Vec3, dt: number): { position: Vec3; velocity: Vec3 } {
  const p0 = position
  const v0 = velocity
  const a0 = accelerationGravity(p0)

  const p1 = add(p0, scale(v0, dt / 2))
  const v1 = add(v0, scale(a0, dt / 2))
  const a1 = accelerationGravity(p1)

  const p2 = add(p0, scale(v1, dt / 2))
  const v2 = add(v0, scale(a1, dt / 2))
  const a2 = accelerationGravity(p2)

  const p3 = add(p0, scale(v2, dt))
  const v3 = add(v0, scale(a2, dt))
  const a3 = accelerationGravity(p3)

  const newPosition: Vec3 = [
    p0[0] + (dt / 6) * (v0[0] + 2 * v1[0] + 2 * v2[0] + v3[0]),
    p0[1] + (dt / 6) * (v0[1] + 2 * v1[1] + 2 * v2[1] + v3[1]),
    p0[2] + (dt / 6) * (v0[2] + 2 * v1[2] + 2 * v2[2] + v3[2]),
  ]

  const newVelocity: Vec3 = [
    v0[0] + (dt / 6) * (a0[0] + 2 * a1[0] + 2 * a2[0] + a3[0]),
    v0[1] + (dt / 6) * (a0[1] + 2 * a1[1] + 2 * a2[1] + a3[1]),
    v0[2] + (dt / 6) * (a0[2] + 2 * a1[2] + 2 * a2[2] + a3[2]),
  ]

  return { position: newPosition, velocity: newVelocity }
}

function coerceVec3(value: number[], label: string): Vec3 {
  if (!Array.isArray(value) || value.length !== 3) {
    throw new Error(`${label} must be a 3-element array`)
  }
  const vec: Vec3 = [Number(value[0]), Number(value[1]), Number(value[2])]
  assertFinite(vec[0], `${label}[0]`)
  assertFinite(vec[1], `${label}[1]`)
  assertFinite(vec[2], `${label}[2]`)
  return vec
}

export function buildManualTrajectory(input: ManualTrajectoryInput) {
  const altitudeKm = Number(input.altitude_km)
  const speedMps = Number(input.speed_mps)
  const inclinationDeg = Number(input.inclination_deg ?? 0)
  const raanDeg = Number(input.raan_deg ?? 0)
  const dt = Math.max(0.1, Number(input.dt ?? 60))

  assertFinite(altitudeKm, "altitude_km")
  assertFinite(speedMps, "speed_mps")
  assertFinite(inclinationDeg, "inclination_deg")
  assertFinite(raanDeg, "raan_deg")
  assertFinite(dt, "dt")

  if (altitudeKm < 100 || altitudeKm > 100_000) throw new Error("altitude_km out of range")
  if (speedMps <= 0) throw new Error("speed_mps must be > 0")

  const inclinationRad = (inclinationDeg * Math.PI) / 180
  const raanRad = (raanDeg * Math.PI) / 180
  const radiusM = EARTH_RADIUS_M + altitudeKm * 1000

  const periodSec = (2 * Math.PI * radiusM) / speedMps
  const durationSec = Number.isFinite(Number(input.duration_sec))
    ? Math.max(dt, Number(input.duration_sec))
    : periodSec * 2

  const numPoints = Math.max(2, Math.floor(durationSec / dt))

  const times: number[] = []
  const positions: number[][] = []
  const velocities: number[][] = []

  for (let i = 0; i < numPoints; i += 1) {
    const t = i * dt
    const angle = (t / periodSec) * 2 * Math.PI

    const posOrbital: Vec3 = [radiusM * Math.cos(angle), radiusM * Math.sin(angle), 0]
    const velOrbital: Vec3 = [-speedMps * Math.sin(angle), speedMps * Math.cos(angle), 0]

    const posEci = rotateOrbitalToEci(posOrbital, inclinationRad, raanRad)
    const velEci = rotateOrbitalToEci(velOrbital, inclinationRad, raanRad)

    times.push(t)
    positions.push([posEci[0], posEci[1], posEci[2]])
    velocities.push([velEci[0], velEci[1], velEci[2]])
  }

  const epoch = new Date().toISOString()

  return {
    norad_id: -1,
    initial_state: {
      position: positions[0],
      velocity: velocities[0],
      epoch,
    },
    trajectory: {
      times,
      positions,
      velocities,
    },
  }
}

export function buildManualManeuverTrajectory(input: ManualManeuverInput) {
  const currentPos = coerceVec3(input.position, "position")
  const currentVel = coerceVec3(input.velocity, "velocity")
  const direction = input.direction
  const deltaVMagnitude = Number(input.delta_v_magnitude)
  assertFinite(deltaVMagnitude, "delta_v_magnitude")
  if (deltaVMagnitude < 0) throw new Error("delta_v_magnitude must be >= 0")

  const rHat = normalize(currentPos, "position")
  const hVec = cross(currentPos, currentVel)
  const nHat = normalize(hVec, "angular momentum")
  const tHat = normalize(cross(nHat, rHat), "tangent direction")

  let deltaV: Vec3
  switch (direction) {
    case "radial-out":
      deltaV = scale(rHat, deltaVMagnitude)
      break
    case "radial-in":
      deltaV = scale(rHat, -deltaVMagnitude)
      break
    case "prograde":
      deltaV = scale(tHat, deltaVMagnitude)
      break
    case "retrograde":
      deltaV = scale(tHat, -deltaVMagnitude)
      break
    default:
      throw new Error(`Unknown direction: ${direction}`)
  }

  const newPosition = currentPos
  const newVelocity = add(currentVel, deltaV)

  const r = norm(newPosition)
  const v = norm(newVelocity)
  const specificEnergy = (v * v) / 2 - EARTH_GM_M3_S2 / r
  const semiMajorAxis = specificEnergy < 0 ? -EARTH_GM_M3_S2 / (2 * specificEnergy) : r
  const periodSec = semiMajorAxis > 0 ? 2 * Math.PI * Math.sqrt((semiMajorAxis ** 3) / EARTH_GM_M3_S2) : 5400
  const durationSec = Math.min(periodSec * 2, 10_800)
  const dt = 10
  const numSteps = Math.max(2, Math.floor(durationSec / dt))

  const times: number[] = []
  const positions: number[][] = []
  const velocities: number[][] = []

  let pos = newPosition
  let vel = newVelocity

  for (let i = 0; i < numSteps; i += 1) {
    times.push(i * dt)
    positions.push([pos[0], pos[1], pos[2]])
    velocities.push([vel[0], vel[1], vel[2]])
    if (i < numSteps - 1) {
      const next = rk4Step(pos, vel, dt)
      pos = next.position
      vel = next.velocity
    }
  }

  return {
    norad_id: -1,
    initial_state: {
      position: [newPosition[0], newPosition[1], newPosition[2]],
      velocity: [newVelocity[0], newVelocity[1], newVelocity[2]],
      epoch: new Date().toISOString(),
    },
    trajectory: {
      times,
      positions,
      velocities,
    },
  }
}

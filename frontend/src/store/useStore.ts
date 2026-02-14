import { create } from 'zustand'

export interface OrbitalObject {
  norad_id: number
  name: string
  position: number[]
  velocity: number[]
  epoch: string | null
  lat: number
  lon: number
  alt_km: number
  object_type: string
  source: string
}

export interface ConjunctionEvent {
  event_id: string
  primary_id: number
  secondary_id: number
  secondary_name: string
  tca_epoch: string | null
  tca_offset_sec: number
  miss_distance_m: number
  relative_velocity_mps: number
  probability: number
  risk_level: string
  escalate: boolean
}

export interface ManeuverCandidate {
  id: string
  type: string
  delta_v: number[]
  delta_v_hill: number[]
  magnitude_mps: number
  burn_time_sec: number
  burn_lead_sec: number
  fuel_kg: number
  new_miss_distance_m: number
  original_miss_distance_m: number
  improvement_factor: number
  effectiveness_m_per_mps: number
}

export interface Trajectory {
  norad_id: number
  times: number[]
  positions: number[][]
  velocities: number[][]
}

interface AppState {
  // Data
  objects: OrbitalObject[]
  conjunctions: ConjunctionEvent[]
  maneuvers: ManeuverCandidate[]
  selectedTrajectory: Trajectory | null
  postManeuverTrajectory: Trajectory | null

  // UI state
  selectedObject: OrbitalObject | null
  selectedEvent: ConjunctionEvent | null
  primaryId: number
  planRiskLevel: string | null
  loading: boolean
  catalogStatus: {
    object_count: number
    last_refresh: string | null
    groups?: string[]
    sources?: string[]
  } | null

  // Actions
  setObjects: (objects: OrbitalObject[]) => void
  setConjunctions: (conjunctions: ConjunctionEvent[]) => void
  setManeuvers: (maneuvers: ManeuverCandidate[]) => void
  setSelectedObject: (obj: OrbitalObject | null) => void
  setSelectedEvent: (event: ConjunctionEvent | null) => void
  setSelectedTrajectory: (traj: Trajectory | null) => void
  setPostManeuverTrajectory: (traj: Trajectory | null) => void
  setPrimaryId: (id: number) => void
  setPlanRiskLevel: (level: string | null) => void
  setLoading: (loading: boolean) => void
  setCatalogStatus: (status: {
    object_count: number
    last_refresh: string | null
    groups?: string[]
    sources?: string[]
  } | null) => void
}

export const useStore = create<AppState>((set) => ({
  objects: [],
  conjunctions: [],
  maneuvers: [],
  selectedTrajectory: null,
  postManeuverTrajectory: null,
  selectedObject: null,
  selectedEvent: null,
  primaryId: 25544, // ISS by default
  planRiskLevel: null,
  loading: false,
  catalogStatus: null,

  setObjects: (objects) => set({ objects }),
  setConjunctions: (conjunctions) => set({ conjunctions }),
  setManeuvers: (maneuvers) => set({ maneuvers }),
  setSelectedObject: (selectedObject) => set({ selectedObject }),
  setSelectedEvent: (selectedEvent) => set({ selectedEvent }),
  setSelectedTrajectory: (selectedTrajectory) => set({ selectedTrajectory }),
  setPostManeuverTrajectory: (postManeuverTrajectory) => set({ postManeuverTrajectory }),
  setPrimaryId: (primaryId) => set({ primaryId }),
  setPlanRiskLevel: (planRiskLevel) => set({ planRiskLevel }),
  setLoading: (loading) => set({ loading }),
  setCatalogStatus: (catalogStatus) => set({ catalogStatus }),
}))

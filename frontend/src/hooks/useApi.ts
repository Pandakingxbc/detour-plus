import { useCallback } from 'react'
import { useStore, type OrbitalObject, type ConjunctionEvent, type ManeuverCandidate, type Trajectory } from '../store/useStore'

const API_BASE = '/api'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`API error ${resp.status}: ${text}`)
  }
  return resp.json()
}

export function useApi() {
  const {
    setObjects, setConjunctions, setManeuvers, setLoading,
    setCatalogStatus, setSelectedTrajectory, primaryId,
  } = useStore()

  const loadObjects = useCallback(async (limit = 5000) => {
    setLoading(true)
    try {
      const data = await fetchJson<OrbitalObject[]>(
        `${API_BASE}/objects?limit=${limit}`
      )
      setObjects(data)
    } catch (err) {
      console.error('Failed to load objects:', err)
    } finally {
      setLoading(false)
    }
  }, [setObjects, setLoading])

  const loadCatalogStatus = useCallback(async () => {
    try {
      const data = await fetchJson<{ object_count: number; last_refresh: string | null }>(
        `${API_BASE}/catalog/status`
      )
      setCatalogStatus(data)
    } catch (err) {
      console.error('Failed to load catalog status:', err)
    }
  }, [setCatalogStatus])

  const refreshCatalog = useCallback(async () => {
    setLoading(true)
    try {
      await fetchJson(`${API_BASE}/catalog/refresh`, { method: 'POST' })
      await loadCatalogStatus()
      await loadObjects()
    } catch (err) {
      console.error('Failed to refresh catalog:', err)
    } finally {
      setLoading(false)
    }
  }, [setLoading, loadCatalogStatus, loadObjects])

  const screenConjunctions = useCallback(async (
    primaryIdOverride?: number,
    lookahead = 86400,
    thresholdKm = 50,
    maxObjects = 200,
  ) => {
    const pid = primaryIdOverride ?? primaryId
    setLoading(true)
    try {
      const data = await fetchJson<ConjunctionEvent[]>(
        `${API_BASE}/conjunctions?primary_id=${pid}&lookahead=${lookahead}&threshold_km=${thresholdKm}&max_objects=${maxObjects}`
      )
      setConjunctions(data)
      return data
    } catch (err) {
      console.error('Failed to screen conjunctions:', err)
      return []
    } finally {
      setLoading(false)
    }
  }, [primaryId, setConjunctions, setLoading])

  const loadTrajectory = useCallback(async (noradId: number, duration = 5400, dt = 60) => {
    try {
      const data = await fetchJson<Trajectory>(
        `${API_BASE}/objects/${noradId}/trajectory?duration=${duration}&dt=${dt}`
      )
      setSelectedTrajectory(data)
      return data
    } catch (err) {
      console.error('Failed to load trajectory:', err)
      return null
    }
  }, [setSelectedTrajectory])

  const proposeManeuvers = useCallback(async (
    primaryIdVal: number,
    secondaryId: number,
    tcaOffsetSec: number,
    missDistanceM: number,
  ) => {
    setLoading(true)
    try {
      const data = await fetchJson<ManeuverCandidate[]>(
        `${API_BASE}/maneuvers/propose`,
        {
          method: 'POST',
          body: JSON.stringify({
            primary_id: primaryIdVal,
            secondary_id: secondaryId,
            tca_offset_sec: tcaOffsetSec,
            miss_distance_m: missDistanceM,
          }),
        }
      )
      setManeuvers(data)
      return data
    } catch (err) {
      console.error('Failed to propose maneuvers:', err)
      return []
    } finally {
      setLoading(false)
    }
  }, [setManeuvers, setLoading])

  const simulateManeuver = useCallback(async (
    primaryIdVal: number,
    secondaryId: number,
    deltaV: number[],
    burnTimeSec = 0,
  ) => {
    setLoading(true)
    try {
      const data = await fetchJson(
        `${API_BASE}/maneuvers/simulate`,
        {
          method: 'POST',
          body: JSON.stringify({
            primary_id: primaryIdVal,
            secondary_id: secondaryId,
            delta_v: deltaV,
            burn_time_sec: burnTimeSec,
          }),
        }
      )
      return data
    } catch (err) {
      console.error('Failed to simulate maneuver:', err)
      return null
    } finally {
      setLoading(false)
    }
  }, [setLoading])

  return {
    loadObjects,
    loadCatalogStatus,
    refreshCatalog,
    screenConjunctions,
    loadTrajectory,
    proposeManeuvers,
    simulateManeuver,
  }
}

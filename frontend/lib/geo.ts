const DEG_TO_RAD = Math.PI / 180

export const EARTH_RADIUS_KM = 6378.137

export interface Cartesian3 {
  x: number
  y: number
  z: number
}

export function geodeticToUnitVector(latDeg: number, lonDeg: number, altKm = 0): Cartesian3 {
  const latRad = latDeg * DEG_TO_RAD
  const lonRad = lonDeg * DEG_TO_RAD
  const radiusScale = 1 + altKm / EARTH_RADIUS_KM

  return {
    x: radiusScale * Math.cos(latRad) * Math.cos(lonRad),
    y: radiusScale * Math.sin(latRad),
    z: -radiusScale * Math.cos(latRad) * Math.sin(lonRad),
  }
}

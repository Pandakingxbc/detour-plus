"""
N2YO REST API client.
Docs: https://www.n2yo.com/api/
Free tier: 1000 transactions/hour.
"""

from __future__ import annotations

import os
import time
import math
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import numpy as np
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.n2yo.com/rest/v1/satellite"

# WGS84 ellipsoid
_A_WGS84 = 6378137.0          # semi-major axis (m)
_F_WGS84 = 1.0 / 298.257223563
_B_WGS84 = _A_WGS84 * (1 - _F_WGS84)
_E2_WGS84 = 1 - (_B_WGS84 / _A_WGS84) ** 2

# Earth rotation rate (rad/s)
_OMEGA_EARTH = 7.2921159e-5


def _geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> np.ndarray:
    """Convert WGS84 geodetic (lat, lon, alt) to ECEF (x, y, z) in meters."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    N = _A_WGS84 / math.sqrt(1 - _E2_WGS84 * sin_lat ** 2)
    x = (N + alt_m) * cos_lat * cos_lon
    y = (N + alt_m) * cos_lat * sin_lon
    z = (N * (1 - _E2_WGS84) + alt_m) * sin_lat
    return np.array([x, y, z], dtype=float)


def _gmst(dt: datetime) -> float:
    """Greenwich Mean Sidereal Time in radians for a UTC datetime."""
    # Julian date
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    jd = jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0
    # centuries since J2000
    T = (jd - 2451545.0) / 36525.0
    gmst_deg = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T ** 2
    return math.radians(gmst_deg % 360)


def _ecef_to_eci(ecef: np.ndarray, dt: datetime) -> np.ndarray:
    """Rotate ECEF to ECI (approximate, ignoring polar motion/nutation)."""
    theta = _gmst(dt)
    c, s = math.cos(theta), math.sin(theta)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)
    return R @ ecef


class N2YOClient:
    """Thin wrapper around the N2YO satellite REST API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("N2YO_API_KEY", "")
        self._request_count = 0
        self._hour_start = time.monotonic()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Detour/1.0 SpaceDebrisCopilot",
        })

    def _check_rate_limit(self):
        now = time.monotonic()
        if now - self._hour_start > 3600:
            self._request_count = 0
            self._hour_start = now
        if self._request_count >= 950:  # leave margin
            raise RuntimeError("N2YO rate limit approaching (1000/hr free tier)")
        self._request_count += 1

    def _get(self, path: str) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("N2YO_API_KEY env var not set")
        self._check_rate_limit()
        url = f"{BASE_URL}/{path}&apiKey={self.api_key}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_tle(self, norad_id: int) -> Dict[str, Any]:
        """Fetch TLE for a single NORAD ID.
        Returns dict with keys: info, tle (with line1, line2).
        """
        data = self._get(f"tle/{norad_id}?")
        return data

    def get_positions(
        self,
        norad_id: int,
        lat: float = 0.0,
        lng: float = 0.0,
        alt: float = 0.0,
        seconds: int = 300,
    ) -> List[Dict[str, Any]]:
        """Fetch predicted positions for the next `seconds` seconds.
        Observer location is (lat, lng, alt_km).
        Returns list of position dicts.
        """
        data = self._get(
            f"positions/{norad_id}/{lat}/{lng}/{alt}/{seconds}?"
        )
        return data.get("positions", [])

    def get_above(
        self,
        lat: float = 0.0,
        lng: float = 0.0,
        alt: float = 0.0,
        radius: int = 70,
        category: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get satellites above observer.
        category 0 = all, see N2YO docs for other categories.
        """
        data = self._get(
            f"above/{lat}/{lng}/{alt}/{radius}/{category}?"
        )
        return data.get("above", [])

    def get_positions_eci(
        self,
        norad_id: int,
        lat: float = 0.0,
        lng: float = 0.0,
        alt: float = 0.0,
        seconds: int = 300,
    ) -> List[Dict[str, Any]]:
        """Like get_positions but also converts to ECI coordinates (meters)."""
        positions = self.get_positions(norad_id, lat, lng, alt, seconds)
        results = []
        for p in positions:
            sat_lat = p.get("satlatitude", 0)
            sat_lng = p.get("satlongitude", 0)
            sat_alt_km = p.get("sataltitude", 400)
            ts = p.get("timestamp", 0)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            ecef = _geodetic_to_ecef(sat_lat, sat_lng, sat_alt_km * 1000)
            eci = _ecef_to_eci(ecef, dt)
            results.append({
                **p,
                "eci_x": eci[0],
                "eci_y": eci[1],
                "eci_z": eci[2],
            })
        return results

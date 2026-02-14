"""
Unified data layer: OrbitalObject dataclass + source abstractions for
CelesTrak, Space-Track, and N2YO.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
from sgp4.api import Satrec, jday

from engine.data.tle_fetcher import fetch_tle
from engine.data.tle_to_state import tle_to_state
from engine.data.n2yo_client import N2YOClient, _geodetic_to_ecef, _gmst

logger = logging.getLogger(__name__)

# Earth radius for altitude calc
_RE = 6378137.0  # m


def _eci_to_geodetic(r_eci: np.ndarray, epoch: datetime) -> Tuple[float, float, float]:
    """Approximate ECI -> (lat_deg, lon_deg, alt_km)."""
    theta = _gmst(epoch)
    c, s = math.cos(-theta), math.sin(-theta)
    R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    ecef = R @ r_eci
    x, y, z = ecef
    r = np.linalg.norm(ecef)
    lat = math.degrees(math.asin(z / r)) if r > 0 else 0.0
    lon = math.degrees(math.atan2(y, x))
    alt_km = (r - _RE) / 1000.0
    return lat, lon, alt_km


@dataclass
class OrbitalObject:
    """Unified orbital object representation from any source."""
    norad_id: int
    name: str = ""
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    epoch: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    tle_line1: str = ""
    tle_line2: str = ""
    lat: float = 0.0
    lon: float = 0.0
    alt_km: float = 0.0
    object_type: str = "unknown"  # satellite, debris, rocket_body, unknown

    def propagate_to(self, target_epoch: datetime) -> "OrbitalObject":
        """Use SGP4 to propagate to a new epoch, returning a new OrbitalObject."""
        if not self.tle_line1 or not self.tle_line2:
            return self
        try:
            r, v = tle_to_state(self.tle_line1, self.tle_line2, epoch=target_epoch)
            lat, lon, alt_km = _eci_to_geodetic(r, target_epoch)
            return OrbitalObject(
                norad_id=self.norad_id,
                name=self.name,
                position=r,
                velocity=v,
                epoch=target_epoch,
                source=self.source,
                tle_line1=self.tle_line1,
                tle_line2=self.tle_line2,
                lat=lat,
                lon=lon,
                alt_km=alt_km,
                object_type=self.object_type,
            )
        except Exception as e:
            logger.warning("SGP4 propagation failed for %s: %s", self.norad_id, e)
            return self


class CelesTrakSource:
    """Fetch TLEs from CelesTrak (single + bulk group endpoints)."""

    GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
    BULK_3LE_URL = "https://celestrak.org/NORAD/elements/gp.php"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Detour/1.0 SpaceDebrisCopilot",
            "Accept": "text/plain",
        })

    def fetch_single(self, norad_id: int) -> Optional[OrbitalObject]:
        """Fetch TLE for a single object from CelesTrak."""
        try:
            resp = self.session.get(
                self.GP_URL,
                params={"CATNR": str(norad_id), "FORMAT": "3le"},
                timeout=15,
            )
            resp.raise_for_status()
            return self._parse_3le_response(resp.text, source="celestrak")
        except Exception as e:
            logger.warning("CelesTrak single fetch failed for %d: %s", norad_id, e)
            return None

    def fetch_group(self, group: str) -> List[OrbitalObject]:
        """Bulk fetch a CelesTrak group (e.g., 'active', 'stations', 'visual')."""
        try:
            resp = self.session.get(
                self.BULK_3LE_URL,
                params={"GROUP": group, "FORMAT": "3le"},
                timeout=60,
            )
            resp.raise_for_status()
            return self._parse_3le_bulk(resp.text, source=f"celestrak:{group}")
        except Exception as e:
            logger.warning("CelesTrak group fetch failed for '%s': %s", group, e)
            return []

    def _parse_3le_bulk(self, text: str, source: str = "celestrak") -> List[OrbitalObject]:
        """Parse multi-object 3-line-element text."""
        lines = [l.rstrip() for l in text.strip().splitlines() if l.strip()]
        objects = []
        i = 0
        while i < len(lines) - 2:
            if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
                name = lines[i].strip()
                l1 = lines[i + 1]
                l2 = lines[i + 2]
                obj = self._tle_to_object(name, l1, l2, source)
                if obj:
                    objects.append(obj)
                i += 3
            elif lines[i].startswith("1 ") and lines[i + 1].startswith("2 "):
                l1 = lines[i]
                l2 = lines[i + 1]
                obj = self._tle_to_object("", l1, l2, source)
                if obj:
                    objects.append(obj)
                i += 2
            else:
                i += 1
        return objects

    def _parse_3le_response(self, text: str, source: str = "celestrak") -> Optional[OrbitalObject]:
        """Parse single-object 3LE response."""
        objs = self._parse_3le_bulk(text, source)
        return objs[0] if objs else None

    def _tle_to_object(
        self, name: str, l1: str, l2: str, source: str
    ) -> Optional[OrbitalObject]:
        try:
            norad_id = int(l1[2:7].strip())
            if not name:
                name = f"NORAD-{norad_id}"
            now = datetime.now(timezone.utc)
            r, v = tle_to_state(l1, l2, epoch=now)
            lat, lon, alt_km = _eci_to_geodetic(r, now)
            return OrbitalObject(
                norad_id=norad_id,
                name=name,
                position=r,
                velocity=v,
                epoch=now,
                source=source,
                tle_line1=l1,
                tle_line2=l2,
                lat=lat,
                lon=lon,
                alt_km=alt_km,
            )
        except Exception as e:
            logger.debug("Failed to parse TLE: %s", e)
            return None


class SpaceTrackSource:
    """Wraps the existing tle_fetcher for Space-Track access."""

    def fetch_single(self, norad_id: int) -> Optional[OrbitalObject]:
        try:
            name, l1, l2 = fetch_tle(norad_id)
            now = datetime.now(timezone.utc)
            r, v = tle_to_state(l1, l2, epoch=now)
            lat, lon, alt_km = _eci_to_geodetic(r, now)
            return OrbitalObject(
                norad_id=norad_id,
                name=name,
                position=r,
                velocity=v,
                epoch=now,
                source="spacetrack",
                tle_line1=l1,
                tle_line2=l2,
                lat=lat,
                lon=lon,
                alt_km=alt_km,
            )
        except Exception as e:
            logger.warning("Space-Track fetch failed for %d: %s", norad_id, e)
            return None


class N2YOSource:
    """Wraps N2YOClient for satellite data."""

    def __init__(self):
        self.client = N2YOClient()

    def fetch_single(self, norad_id: int) -> Optional[OrbitalObject]:
        try:
            data = self.client.get_tle(norad_id)
            tle_str = data.get("tle", "")
            if not tle_str:
                return None
            lines = [l.strip() for l in tle_str.strip().splitlines() if l.strip()]
            if len(lines) < 2:
                return None
            l1, l2 = lines[0], lines[1]
            info = data.get("info", {})
            name = info.get("satname", f"NORAD-{norad_id}")
            now = datetime.now(timezone.utc)
            r, v = tle_to_state(l1, l2, epoch=now)
            lat, lon, alt_km = _eci_to_geodetic(r, now)
            return OrbitalObject(
                norad_id=norad_id,
                name=name,
                position=r,
                velocity=v,
                epoch=now,
                source="n2yo",
                tle_line1=l1,
                tle_line2=l2,
                lat=lat,
                lon=lon,
                alt_km=alt_km,
            )
        except Exception as e:
            logger.warning("N2YO fetch failed for %d: %s", norad_id, e)
            return None

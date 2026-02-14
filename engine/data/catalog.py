"""
In-memory orbital object catalog.
Bulk-fetches from CelesTrak groups, stores OrbitalObject instances,
and falls through multiple sources for individual lookups.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from engine.data.data_sources import (
    OrbitalObject,
    CelesTrakSource,
    SpaceTrackSource,
    N2YOSource,
)

logger = logging.getLogger(__name__)

DEFAULT_GROUPS = ["active", "stations", "visual"]


class Catalog:
    """Manages an in-memory store of orbital objects from multiple sources."""

    def __init__(self, groups: Optional[List[str]] = None, auto_load: bool = False):
        self.objects: Dict[int, OrbitalObject] = {}
        self.groups = groups or DEFAULT_GROUPS
        self.last_refresh: Optional[datetime] = None
        self._celestrak = CelesTrakSource()
        self._spacetrack = SpaceTrackSource()
        self._n2yo = N2YOSource()
        if auto_load:
            self.refresh()

    @property
    def count(self) -> int:
        return len(self.objects)

    def refresh(self) -> int:
        """Bulk-fetch from CelesTrak groups. Returns number of objects loaded."""
        total = 0
        for group in self.groups:
            try:
                objs = self._celestrak.fetch_group(group)
                for obj in objs:
                    if obj.norad_id not in self.objects:
                        self.objects[obj.norad_id] = obj
                        total += 1
                logger.info(
                    "Loaded %d objects from CelesTrak group '%s' (%d new)",
                    len(objs),
                    group,
                    total,
                )
            except Exception as e:
                logger.warning("Failed to load group '%s': %s", group, e)
        self.last_refresh = datetime.now(timezone.utc)
        logger.info("Catalog now has %d objects total", len(self.objects))
        return total

    def get_all(self, propagate: bool = False) -> List[OrbitalObject]:
        """Return all objects. If propagate=True, SGP4-propagate to current epoch."""
        if not propagate:
            return list(self.objects.values())
        now = datetime.now(timezone.utc)
        return [obj.propagate_to(now) for obj in self.objects.values()]

    def get_object(self, norad_id: int, propagate: bool = True) -> Optional[OrbitalObject]:
        """
        Look up a single object. Falls through: cache -> CelesTrak -> Space-Track -> N2YO.
        """
        # Try cache first
        if norad_id in self.objects:
            obj = self.objects[norad_id]
            if propagate:
                obj = obj.propagate_to(datetime.now(timezone.utc))
            return obj

        # Try CelesTrak
        obj = self._celestrak.fetch_single(norad_id)
        if obj:
            self.objects[norad_id] = obj
            return obj

        # Try Space-Track
        obj = self._spacetrack.fetch_single(norad_id)
        if obj:
            self.objects[norad_id] = obj
            return obj

        # Try N2YO
        obj = self._n2yo.fetch_single(norad_id)
        if obj:
            self.objects[norad_id] = obj
            return obj

        return None

    def search(self, query: str) -> List[OrbitalObject]:
        """Simple name search across catalog."""
        q = query.lower()
        return [
            obj
            for obj in self.objects.values()
            if q in obj.name.lower() or q in str(obj.norad_id)
        ]

    def status(self) -> Dict:
        """Return catalog status info."""
        return {
            "object_count": len(self.objects),
            "groups": self.groups,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "sources": ["celestrak", "spacetrack", "n2yo"],
        }

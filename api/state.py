"""Server state: catalog instance, caches, and shared resources."""

from __future__ import annotations

from typing import Dict, List, Optional

from engine.data.catalog import Catalog

# Global catalog instance (initialized on startup)
catalog: Optional[Catalog] = None

# Cache for conjunction screening results
conjunction_cache: Dict[str, List[Dict]] = {}


def get_catalog() -> Catalog:
    global catalog
    if catalog is None:
        catalog = Catalog(auto_load=False)
    return catalog


def init_catalog(groups: Optional[List[str]] = None) -> Catalog:
    global catalog
    catalog = Catalog(groups=groups, auto_load=True)
    return catalog

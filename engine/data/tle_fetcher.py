
"""
Robust TLE fetcher (Space-Track primary, CelesTrak fallback, disk cache).
Features:
 - Disk cache (TTL configurable)
 - Space-Track cookie-based login (one prompt per run)
 - Detects non-TLE HTML/redirects and disables Space-Track for the run
 - Robust parser that finds consecutive "1 " / "2 " TLE lines anywhere in response
 - Graceful fallback when endpoints fail; clear exceptions when data unavailable
"""

from __future__ import annotations

import os
import requests
import json
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
import logging

# -----------------------
# Logging
# -----------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# -----------------------
# Config
# -----------------------
CACHE_FILE = Path("tle_cache.json")      # local project cache
CACHE_TTL = timedelta(hours=6)

CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"

SPACE_TRACK_LOGIN_URL = "https://www.space-track.org/ajaxauth/login"
SPACE_TRACK_TLE_URL = (
    "https://www.space-track.org/basicspacedata/query/"
    "class/gp_latest/"
    "NORAD_CAT_ID/{norad}/"
    "orderby/EPOCH desc/limit/1/format/tle"
)

# -----------------------
# Globals controlling Space-Track behavior during this process run
# -----------------------
_SPACE_TRACK_SESSION: Optional[requests.Session] = None
_SPACE_TRACK_DISABLED: bool = False  # set True if HTML/redirect/rate-limit seen

# -----------------------
# Cache helpers
# -----------------------
def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        txt = CACHE_FILE.read_text(encoding="utf-8")
        return json.loads(txt)
    except Exception:
        logger.warning("TLE cache file unreadable or corrupt, starting fresh.")
        return {}

def _save_cache(cache: dict):
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write TLE cache: %s", e)

# -----------------------
# Space-Track login manager (cookie-based)
# -----------------------
def _get_space_track_session() -> requests.Session:
    """
    Return an authenticated requests.Session for Space-Track.
    Prompts for username/password once per process run.
    Checks presence of cookies to confirm success (cookie-based auth).
    """
    global _SPACE_TRACK_SESSION, _SPACE_TRACK_DISABLED

    if _SPACE_TRACK_DISABLED:
        raise RuntimeError("Space-Track disabled for this run due to previous non-TLE responses.")

    if _SPACE_TRACK_SESSION is not None:
        return _SPACE_TRACK_SESSION

    username = os.environ.get("SPACE_TRACK_USER", "").strip()
    password = os.environ.get("SPACE_TRACK_PASS", "").strip()
    if not username or not password:
        _SPACE_TRACK_DISABLED = True
        raise RuntimeError("SPACE_TRACK_USER and SPACE_TRACK_PASS env vars required for Space-Track access")

    session = requests.Session()
    # helpful headers to mimic a browser
    session.headers.update({
        "User-Agent": "SpaceDebrisEngine/1.0 (+https://example.invalid)",
        "Accept": "text/plain, */*; q=0.01",
    })

    try:
        resp = session.post(
            SPACE_TRACK_LOGIN_URL,
            data={"identity": username, "password": password},
            timeout=20,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Space-Track login network error: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"Space-Track login HTTP error: {resp.status_code}")

    # Real success is cookie-based; verify session has cookies for domain
    if not session.cookies:
        # No cookies -> treat as login failure
        raise RuntimeError("Space-Track login failed (no session cookies received)")

    logger.info("Space-Track login succeeded (cookies present).")
    _SPACE_TRACK_SESSION = session
    return session

# -----------------------
# Robust TLE parser
# -----------------------
def _parse_tle(text: str, norad_id: int) -> Tuple[str, str, str]:
    """
    Find consecutive '1 ' and '2 ' lines anywhere in the response.
    If a name line exists immediately before the '1' line, use it as name.
    Returns (name, line1, line2).
    Raises ValueError if no valid pair found.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # look for direct pair: lines[i] starts with '1 ' and lines[i+1] starts with '2 '
    for i in range(len(lines) - 1):
        if lines[i].startswith("1 ") and lines[i + 1].startswith("2 "):
            # no explicit name line -> fabricate NORAD name
            return f"NORAD-{norad_id}", lines[i], lines[i + 1]
        # name line followed by 1/2
        if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name = lines[i]
            return name, lines[i + 1], lines[i + 2]
    raise ValueError("Invalid TLE response (no '1 '/'2 ' pair found)")

# -----------------------
# Space-Track fetch with protective checks
# -----------------------
def _fetch_space_track(norad_id: int) -> Tuple[str, str, str]:
    """
    Fetch latest TLE from Space-Track for norad_id.
    If the response is HTML, or lacks TLE markers, disable Space-Track for the run and raise.
    """
    global _SPACE_TRACK_DISABLED
    if _SPACE_TRACK_DISABLED:
        raise RuntimeError("Space-Track disabled for this run")

    session = _get_space_track_session()
    url = SPACE_TRACK_TLE_URL.format(norad=norad_id)

    try:
        resp = session.get(url, timeout=20)
    except requests.RequestException as e:
        raise RuntimeError(f"Space-Track GET failed: {e}") from e

    # If endpoint returns HTML (login page / redirect / rate-limit), disable for this run
    ct = resp.headers.get("Content-Type", "").lower()
    if "text/html" in ct or "<html" in resp.text.lower():
        _SPACE_TRACK_DISABLED = True
        raise RuntimeError("Space-Track returned HTML (likely redirect/login/rate-limit); disabling Space-Track for this run")

    # ensure TLE-like content present
    text = resp.text or ""
    if "1 " not in text or "2 " not in text:
        _SPACE_TRACK_DISABLED = True
        raise RuntimeError("Space-Track did not return TLE lines; disabling Space-Track for this run")

    # parse and return
    return _parse_tle(text, norad_id)

# -----------------------
# CelesTrak fetch (best-effort mirror)
# -----------------------
def _fetch_celestrak(norad_id: int) -> Tuple[str, str, str]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/plain",
    })
    params = {"CATNR": str(norad_id), "FORMAT": "TLE"}
    try:
        resp = session.get(CELESTRAK_GP_URL, params=params, timeout=15)
    except requests.RequestException as e:
        raise RuntimeError(f"CelesTrak network error: {e}") from e

    # surface HTTP error
    try:
        resp.raise_for_status()
    except requests.HTTPError as he:
        # surface 403 clearly
        raise

    # parse
    return _parse_tle(resp.text, norad_id)

# Public API
@lru_cache(maxsize=512)
def fetch_tle(norad_id: int) -> Tuple[str, str, str]:
    """
    Public fetcher:
      - checks disk cache (TTL)
      - tries Space-Track (if not disabled)
      - falls back to CelesTrak
    Raises a RuntimeError if both fail.
    """
    global _SPACE_TRACK_DISABLED
    norad_str = str(norad_id)
    now = datetime.now(timezone.utc)

    # load cache
    cache = _load_cache()
    if norad_str in cache:
        try:
            ts = datetime.fromisoformat(cache[norad_str]["timestamp"])
            if now - ts < CACHE_TTL:
                logger.info("TLE cache hit for NORAD %s", norad_str)
                return cache[norad_str]["name"], cache[norad_str]["line1"], cache[norad_str]["line2"]
        except Exception:
            # fall through to refetch if cache entry malformed
            pass

    # Try primary: Space-Track (if not disabled)
    last_exc: Optional[Exception] = None
    if not _SPACE_TRACK_DISABLED:
        try:
            name, l1, l2 = _fetch_space_track(norad_id)
            source = "Space-Track"
            # save cache
            cache[norad_str] = {
                "timestamp": now.isoformat(),
                "name": name,
                "line1": l1,
                "line2": l2,
                "source": source,
            }
            _save_cache(cache)
            logger.info("Fetched TLE for NORAD %s from Space-Track", norad_str)
            return name, l1, l2
        except Exception as st_e:
            last_exc = st_e
            logger.warning("Space-Track failed: %s", st_e)
            # If Space-Track produced HTML or non-TLE, it sets _SPACE_TRACK_DISABLED inside _fetch_space_track.
            # Continue to fallback below.

    # Fallback to CelesTrak
    try:
        name, l1, l2 = _fetch_celestrak(norad_id)
        source = "CelesTrak"
        cache[norad_str] = {
            "timestamp": now.isoformat(),
            "name": name,
            "line1": l1,
            "line2": l2,
            "source": source,
        }
        _save_cache(cache)
        logger.info("Fetched TLE for NORAD %s from CelesTrak", norad_str)
        return name, l1, l2
    except requests.HTTPError as cel_he:
        # if CelesTrak specifically returned 403 (common block), try Space-Track once more if not disabled
        try:
            status = cel_he.response.status_code if cel_he.response is not None else None
            logger.warning("CelesTrak HTTP error: %s", status)
        except Exception:
            pass

        if not _SPACE_TRACK_DISABLED:
            # try space-track again (maybe login wasn't done earlier)
            try:
                name, l1, l2 = _fetch_space_track(norad_id)
                source = "Space-Track (after CelesTrak 403)"
                cache[norad_str] = {
                    "timestamp": now.isoformat(),
                    "name": name,
                    "line1": l1,
                    "line2": l2,
                    "source": source,
                }
                _save_cache(cache)
                logger.info("Fetched TLE for NORAD %s from Space-Track (after CelesTrak 403)", norad_str)
                return name, l1, l2
            except Exception as st_e2:
                last_exc = st_e2
                logger.warning("Space-Track retry after CelesTrak 403 failed: %s", st_e2)

        # final failure
        raise RuntimeError(f"CelesTrak returned HTTP error and Space-Track unavailable for NORAD {norad_id}") from cel_he

    except Exception as cel_e:
        # general fallback fail
        last_exc = cel_e
        logger.warning("CelesTrak failed: %s", cel_e)

    # If we get here, both providers failed
    raise RuntimeError(f"TLE unavailable for NORAD {norad_id}") from last_exc

# -----------------------
# Quick test when run directly
# -----------------------
if __name__ == "__main__":
    try:
        print(fetch_tle(25544))  # ISS
    except Exception as e:
        print("Test failed:", e)

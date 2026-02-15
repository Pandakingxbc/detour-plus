"""Pydantic request/response models for the Detour API."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# --- Response Models ---

class OrbitalObjectResponse(BaseModel):
    norad_id: int
    name: str = ""
    position: List[float] = Field(default_factory=list, description="ECI position [x,y,z] in meters")
    velocity: List[float] = Field(default_factory=list, description="ECI velocity [vx,vy,vz] in m/s")
    epoch: Optional[str] = None
    lat: float = 0.0
    lon: float = 0.0
    alt_km: float = 0.0
    object_type: str = "unknown"
    source: str = ""


class TrajectoryResponse(BaseModel):
    norad_id: int
    times: List[float]
    positions: List[List[float]]
    velocities: List[List[float]]


class ConjunctionEvent(BaseModel):
    event_id: str
    primary_id: int
    secondary_id: int
    secondary_name: str = ""
    tca_epoch: Optional[str] = None
    tca_offset_sec: float = 0.0
    miss_distance_m: float
    relative_velocity_mps: float = 0.0
    probability: float = 0.0
    risk_level: str = "low"
    escalate: bool = False


class RefinementResult(BaseModel):
    closest_time_sec: Optional[float] = None
    miss_distance_m: Optional[float] = None
    relative_velocity_mps: Optional[float] = None
    collision: bool = False
    conjunction: bool = False
    energy_drift_sat_pct: Optional[float] = None
    energy_drift_deb_pct: Optional[float] = None
    note: str = ""


class RiskAssessment(BaseModel):
    risk_score: float
    level: str
    chan_probability: float = 0.0
    gaussian_probability: float = 0.0
    mc_results: Optional[Dict] = None
    miss_distance_m: float = 0.0
    recommendation: str = "monitor"


class ManeuverCandidate(BaseModel):
    id: str
    type: str
    delta_v: List[float]
    delta_v_hill: List[float] = Field(default_factory=list)
    magnitude_mps: float
    burn_time_sec: float
    burn_lead_sec: float = 0.0
    fuel_kg: float
    new_miss_distance_m: float
    original_miss_distance_m: float = 0.0
    improvement_factor: float = 0.0
    effectiveness_m_per_mps: float = 0.0


class ManeuverSimulationResult(BaseModel):
    before: Dict
    after: Dict
    delta_v_applied: List[float]
    fuel_estimate_kg: float
    secondary_conjunctions: List[Dict] = Field(default_factory=list)
    secondary_conjunction_count: int = 0


class ConstraintCheckResult(BaseModel):
    overall_pass: bool
    constraints: Dict


class CatalogStatus(BaseModel):
    object_count: int
    groups: List[str]
    last_refresh: Optional[str] = None
    sources: List[str]


# --- Request Models ---

class ScreeningRequest(BaseModel):
    primary_id: int
    lookahead_sec: float = 86400.0
    threshold_km: float = 50.0
    max_objects: int = 500


class ManeuverProposeRequest(BaseModel):
    primary_id: int
    secondary_id: int
    tca_offset_sec: float
    miss_distance_m: float
    mass_kg: float = 500.0
    isp_s: float = 220.0
    target_miss_km: float = 5.0


class ManeuverSimulateRequest(BaseModel):
    primary_id: int
    secondary_id: int
    delta_v: List[float]
    burn_time_sec: float = 0.0
    window_sec: float = 7200.0
    check_secondary: bool = False


class ManualSatelliteRequest(BaseModel):
    radius_km: float = Field(description="Orbital radius from Earth center in km")
    speed_mps: float = Field(description="Orbital speed in m/s")
    duration_sec: float = Field(default=5400, description="Trajectory duration in seconds")
    dt: float = Field(default=60, description="Timestep in seconds")

"""Schemas for compressor assets and readings."""

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Any, Optional


# ── Compressor CRUD ──────────────────────────────
class CompressorCreate(BaseModel):
    name: str
    tag: Optional[str] = None
    manufacturer: Optional[str] = None  # Frick, Vilter, Mycom, GEA
    model: Optional[str] = None
    serial_number: Optional[str] = None
    compressor_type: str = "screw"
    refrigerant: str = "NH3"
    refrigerant_charge_lbs: Optional[float] = None
    hp: Optional[float] = None
    capacity_tons: Optional[float] = None
    design_suction_psi: Optional[float] = None
    design_discharge_psi: Optional[float] = None
    max_discharge_temp_f: Optional[float] = None
    # Alarm thresholds
    alarm_discharge_psi_high: Optional[float] = None
    alarm_suction_psi_low: Optional[float] = None
    alarm_oil_temp_high: Optional[float] = None
    alarm_bearing_temp_high: Optional[float] = None
    alarm_vibration_high: Optional[float] = None
    alarm_amp_draw_high: Optional[float] = None
    # Maintenance
    commissioned_at: Optional[datetime] = None
    last_overhaul_at: Optional[datetime] = None
    run_hours: Optional[int] = None
    next_maintenance_hours: Optional[int] = None
    rack_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class CompressorUpdate(BaseModel):
    name: Optional[str] = None
    tag: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    compressor_type: Optional[str] = None
    refrigerant: Optional[str] = None
    refrigerant_charge_lbs: Optional[float] = None
    hp: Optional[float] = None
    capacity_tons: Optional[float] = None
    design_suction_psi: Optional[float] = None
    design_discharge_psi: Optional[float] = None
    max_discharge_temp_f: Optional[float] = None
    alarm_discharge_psi_high: Optional[float] = None
    alarm_suction_psi_low: Optional[float] = None
    alarm_oil_temp_high: Optional[float] = None
    alarm_bearing_temp_high: Optional[float] = None
    alarm_vibration_high: Optional[float] = None
    alarm_amp_draw_high: Optional[float] = None
    commissioned_at: Optional[datetime] = None
    last_overhaul_at: Optional[datetime] = None
    run_hours: Optional[int] = None
    next_maintenance_hours: Optional[int] = None
    rack_name: Optional[str] = None
    portal_url: Optional[str] = None
    state: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class CompressorResponse(BaseModel):
    id: UUID
    facility_id: UUID
    name: str
    tag: Optional[str]
    manufacturer: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    compressor_type: str
    refrigerant: str
    refrigerant_charge_lbs: Optional[float]
    hp: Optional[float]
    capacity_tons: Optional[float]
    design_suction_psi: Optional[float]
    design_discharge_psi: Optional[float]
    max_discharge_temp_f: Optional[float]
    alarm_discharge_psi_high: Optional[float]
    alarm_suction_psi_low: Optional[float]
    alarm_oil_temp_high: Optional[float]
    alarm_bearing_temp_high: Optional[float]
    alarm_vibration_high: Optional[float]
    alarm_amp_draw_high: Optional[float]
    commissioned_at: Optional[datetime]
    last_overhaul_at: Optional[datetime]
    run_hours: Optional[int]
    next_maintenance_hours: Optional[int]
    state: str
    health_score: Optional[float]
    last_reading_at: Optional[datetime]
    rack_name: Optional[str]
    portal_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompressorListResponse(BaseModel):
    compressors: list[CompressorResponse]
    total: int


# ── Compressor Readings ──────────────────────────
class ReadingCreate(BaseModel):
    """Ingest a compressor telemetry snapshot."""
    discharge_pressure_psi: Optional[float] = None
    suction_pressure_psi: Optional[float] = None
    discharge_temp_f: Optional[float] = None
    suction_temp_f: Optional[float] = None
    oil_pressure_psi: Optional[float] = None
    oil_temp_f: Optional[float] = None
    bearing_temp_f: Optional[float] = None
    amp_draw: Optional[float] = None
    kw: Optional[float] = None
    power_factor: Optional[float] = None
    vibration_ips: Optional[float] = None
    slide_valve_pct: Optional[float] = None
    rpm: Optional[float] = None
    superheat_f: Optional[float] = None
    subcooling_f: Optional[float] = None
    compression_ratio: Optional[float] = None
    efficiency_pct: Optional[float] = None
    running: Optional[bool] = None
    alarm_active: bool = False
    alarm_codes: Optional[list[str]] = None
    recorded_at: Optional[datetime] = None


class ReadingResponse(BaseModel):
    id: UUID
    compressor_id: UUID
    discharge_pressure_psi: Optional[float]
    suction_pressure_psi: Optional[float]
    discharge_temp_f: Optional[float]
    suction_temp_f: Optional[float]
    oil_pressure_psi: Optional[float]
    oil_temp_f: Optional[float]
    bearing_temp_f: Optional[float]
    amp_draw: Optional[float]
    kw: Optional[float]
    power_factor: Optional[float]
    vibration_ips: Optional[float]
    slide_valve_pct: Optional[float]
    rpm: Optional[float]
    superheat_f: Optional[float]
    subcooling_f: Optional[float]
    compression_ratio: Optional[float]
    efficiency_pct: Optional[float]
    running: Optional[bool]
    alarm_active: bool
    alarm_codes: Optional[list[str]]
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ReadingListResponse(BaseModel):
    readings: list[ReadingResponse]
    total: int


# ── Health Summary ───────────────────────────────
class CompressorHealthSummary(BaseModel):
    """Aggregated health data for dashboard display."""
    compressor_id: UUID
    name: str
    tag: Optional[str]
    manufacturer: Optional[str]
    model: Optional[str]
    state: str
    health_score: Optional[float]
    refrigerant: str
    hp: Optional[float]
    rack_name: Optional[str]
    portal_url: Optional[str] = None
    # Latest reading snapshot
    discharge_pressure_psi: Optional[float] = None
    suction_pressure_psi: Optional[float] = None
    oil_temp_f: Optional[float] = None
    bearing_temp_f: Optional[float] = None
    vibration_ips: Optional[float] = None
    amp_draw: Optional[float] = None
    kw: Optional[float] = None
    slide_valve_pct: Optional[float] = None
    running: Optional[bool] = None
    last_reading_at: Optional[datetime] = None
    # Anomaly flags
    anomalies: list[str] = []


class FacilityCompressorSummary(BaseModel):
    """Fleet-level compressor summary for a facility."""
    facility_id: UUID
    total_compressors: int
    running: int
    in_alarm: int
    avg_health_score: Optional[float]
    total_kw: Optional[float]
    total_capacity_tons: Optional[float]
    compressors: list[CompressorHealthSummary]

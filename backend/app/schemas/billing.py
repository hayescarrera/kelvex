from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional


# ── Utility Bills ────────────────────────────────
class BillCreate(BaseModel):
    """Manual bill entry (for when there's no file upload)."""
    period_start: date
    period_end: date
    total_kwh: Optional[float] = None
    total_cost: Optional[Decimal] = None
    peak_demand_kw: Optional[float] = None
    demand_charge: Optional[Decimal] = None
    energy_charge: Optional[Decimal] = None


class BillUpdate(BaseModel):
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    total_kwh: Optional[float] = None
    total_cost: Optional[Decimal] = None
    peak_demand_kw: Optional[float] = None
    demand_charge: Optional[Decimal] = None
    energy_charge: Optional[Decimal] = None


class BillResponse(BaseModel):
    id: UUID
    facility_id: UUID
    period_start: date
    period_end: date
    total_kwh: Optional[float]
    total_cost: Optional[Decimal]
    peak_demand_kw: Optional[float]
    demand_charge: Optional[Decimal]
    energy_charge: Optional[Decimal]
    source_file: Optional[str]
    parsed_at: Optional[datetime]
    raw_data: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class BillListResponse(BaseModel):
    bills: list[BillResponse]
    total: int


# ── Demand Analysis ──────────────────────────────
class DemandAnalysisResponse(BaseModel):
    id: UUID
    facility_id: UUID
    period_start: date
    period_end: date
    peak_demand_kw: Optional[float]
    peak_demand_time: Optional[datetime]
    ratchet_demand_kw: Optional[float]
    demand_charge_actual: Optional[Decimal]
    demand_charge_optimized: Optional[Decimal]
    savings_potential: Optional[Decimal]
    peak_events: Optional[Any]  # list from demand engine, stored as JSONB
    load_profile: Optional[Any]  # dict from demand engine, stored as JSONB
    created_at: datetime

    model_config = {"from_attributes": True}


class DemandAnalysisListResponse(BaseModel):
    analyses: list[DemandAnalysisResponse]
    total: int


# ── Facility Summary (enriched response) ────────
class FacilitySummary(BaseModel):
    """Aggregated facility stats for the dashboard."""
    facility_id: UUID
    facility_name: str
    total_bills: int
    latest_bill_period: Optional[str]
    avg_monthly_cost: Optional[float]
    avg_demand_charge: Optional[float]
    peak_demand_kw: Optional[float]
    total_savings_potential: Optional[float]

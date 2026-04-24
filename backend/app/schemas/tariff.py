"""Schemas for rate schedule and utility CRUD."""

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date
from typing import Any, Optional


# ── Utilities ────────────────────────────────────
class UtilityCreate(BaseModel):
    name: str
    state: Optional[str] = None
    iso_region: Optional[str] = None
    regulated: bool = True


class UtilityResponse(BaseModel):
    id: UUID
    name: str
    state: Optional[str]
    iso_region: Optional[str]
    regulated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UtilityListResponse(BaseModel):
    utilities: list[UtilityResponse]
    total: int


# ── Rate Schedules ───────────────────────────────
class RateScheduleCreate(BaseModel):
    """
    Create a rate schedule with TOU energy/demand rates.

    demand_rates example:
    {
      "tou": [
        {"period": "on_peak", "rate": 23.40, "months": [6,7,8,9], "hours": [12,20]},
        {"period": "mid_peak", "rate": 15.00, "months": [6,7,8,9], "hours": [8,12]},
        {"period": "off_peak", "rate": 8.50}
      ],
      "ratchet": {"pct": 0.80, "lookback_months": 11},
      "minimum_demand_kw": 50
    }

    energy_rates example:
    {
      "tou": [
        {"period": "on_peak", "rate": 0.1842, "months": [6,7,8,9], "hours": [12,20]},
        {"period": "off_peak", "rate": 0.0923}
      ]
    }
    """
    utility_id: UUID
    schedule_name: str
    description: Optional[str] = None
    sector: str = "commercial"
    effective_date: date
    end_date: Optional[date] = None
    demand_rates: dict[str, Any] = {}
    energy_rates: dict[str, Any] = {}
    fixed_charges: Optional[dict[str, Any]] = None


class RateScheduleUpdate(BaseModel):
    schedule_name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    effective_date: Optional[date] = None
    end_date: Optional[date] = None
    demand_rates: Optional[dict[str, Any]] = None
    energy_rates: Optional[dict[str, Any]] = None
    fixed_charges: Optional[dict[str, Any]] = None


class RateScheduleResponse(BaseModel):
    id: UUID
    utility_id: UUID
    openei_rate_id: Optional[str]
    schedule_name: str
    description: Optional[str]
    sector: str
    effective_date: date
    end_date: Optional[date]
    demand_rates: dict[str, Any]
    energy_rates: dict[str, Any]
    fixed_charges: Optional[dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class RateScheduleListResponse(BaseModel):
    rate_schedules: list[RateScheduleResponse]
    total: int

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class FacilityCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    sqft: Optional[int] = None
    zone_types: Optional[list[str]] = None


class FacilityUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    sqft: Optional[int] = None
    zone_types: Optional[list[str]] = None
    utility_id: Optional[UUID] = None
    rate_schedule_id: Optional[UUID] = None


class FacilityResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    sqft: Optional[int]
    zone_types: Optional[list[str]]
    utility_id: Optional[UUID]
    rate_schedule_id: Optional[UUID]
    iso_region: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class FacilityListResponse(BaseModel):
    facilities: list[FacilityResponse]
    total: int

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ZoneCreate(BaseModel):
    name: str
    zone_type: str  # freezer, cooler, dock, machine_room, blast_freezer, staging
    area_sqft: int | None = None
    position_x: float | None = None
    position_y: float | None = None
    width: float | None = None
    height: float | None = None
    temp_setpoint: float | None = None
    temp_unit: str = "F"
    temp_tolerance: float = 2.0
    temp_alarm_high: float | None = None
    temp_alarm_low: float | None = None
    humidity_setpoint: float | None = None
    humidity_alarm_high: float | None = None


class ZoneUpdate(BaseModel):
    name: str | None = None
    zone_type: str | None = None
    area_sqft: int | None = None
    position_x: float | None = None
    position_y: float | None = None
    width: float | None = None
    height: float | None = None
    temp_setpoint: float | None = None
    temp_unit: str | None = None
    temp_tolerance: float | None = None
    temp_alarm_high: float | None = None
    temp_alarm_low: float | None = None
    humidity_setpoint: float | None = None
    humidity_alarm_high: float | None = None


class ZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    name: str
    zone_type: str
    area_sqft: int | None = None
    position_x: float | None = None
    position_y: float | None = None
    width: float | None = None
    height: float | None = None
    temp_setpoint: float | None = None
    temp_unit: str = "F"
    temp_tolerance: float = 2.0
    temp_alarm_high: float | None = None
    temp_alarm_low: float | None = None
    humidity_setpoint: float | None = None
    humidity_alarm_high: float | None = None
    current_temp: float | None = None
    current_humidity: float | None = None
    door_open: bool = False
    state: str = "normal"
    last_reading_at: datetime | None = None
    created_at: datetime


class ZoneListResponse(BaseModel):
    zones: list[ZoneResponse]
    total: int


class ZoneEquipmentCreate(BaseModel):
    equipment_id: UUID
    role: str | None = None  # primary, backup, shared


class ZoneEquipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    zone_id: UUID
    equipment_id: UUID
    role: str | None = None
    created_at: datetime

from datetime import datetime
from uuid import UUID
from typing import Any
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


class ZoneSensorCreate(BaseModel):
    name: str
    sensor_type: str  # temperature, humidity, door_contact, ammonia, pressure_differential, glycol_temp
    unit: str | None = None
    location_desc: str | None = None
    alarm_high: float | None = None
    alarm_low: float | None = None
    warn_high: float | None = None
    warn_low: float | None = None
    poll_interval_sec: int = 30
    enabled: bool = True
    # Modbus connection config
    host: str | None = None
    port: int = 502
    slave_id: int = 1
    register_address: int | None = None
    register_type: str = "holding"
    data_type: str = "uint16"
    scale: float = 1.0
    offset: float = 0.0


class ZoneSensorUpdate(BaseModel):
    name: str | None = None
    sensor_type: str | None = None
    unit: str | None = None
    location_desc: str | None = None
    alarm_high: float | None = None
    alarm_low: float | None = None
    warn_high: float | None = None
    warn_low: float | None = None
    poll_interval_sec: int | None = None
    enabled: bool | None = None
    host: str | None = None
    port: int | None = None
    slave_id: int | None = None
    register_address: int | None = None
    register_type: str | None = None
    data_type: str | None = None
    scale: float | None = None
    offset: float | None = None


class ZoneSensorResponse(BaseModel):
    id: UUID
    zone_id: UUID
    name: str
    sensor_type: str
    unit: str | None = None
    location_desc: str | None = None
    alarm_high: float | None = None
    alarm_low: float | None = None
    warn_high: float | None = None
    warn_low: float | None = None
    current_value: float | None = None
    current_state: str = "normal"
    last_reading_at: datetime | None = None
    poll_interval_sec: int = 30
    enabled: bool = True
    created_at: datetime
    host: str | None = None
    port: int = 502
    slave_id: int = 1
    register_address: int | None = None
    register_type: str = "holding"
    data_type: str = "uint16"
    scale: float = 1.0
    offset: float = 0.0


class ZoneSensorListResponse(BaseModel):
    sensors: list[ZoneSensorResponse]
    total: int

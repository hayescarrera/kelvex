from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class EquipmentCreate(BaseModel):
    name: str
    equipment_type: str  # compressor, evaporator, condenser, controller, etc.
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    controller_type: Optional[str] = None  # copeland, danfoss, allen_bradley
    protocol: Optional[str] = None  # bacnet, modbus, ethernet_ip
    portal_url: Optional[str] = None


class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    equipment_type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    controller_type: Optional[str] = None
    protocol: Optional[str] = None
    portal_url: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: UUID
    facility_id: UUID
    name: str
    equipment_type: str
    manufacturer: Optional[str]
    model: Optional[str]
    controller_type: Optional[str]
    protocol: Optional[str]
    portal_url: Optional[str]
    commissioned_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class EquipmentListResponse(BaseModel):
    equipment: list[EquipmentResponse]
    total: int

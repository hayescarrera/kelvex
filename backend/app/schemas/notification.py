"""Pydantic schemas for notification channels and logs."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class NotificationChannelCreate(BaseModel):
    name: str
    channel_type: str  # email, webhook, slack
    config: dict = {}
    enabled: bool = True
    # Routing filters
    facility_ids: list[UUID] | None = None
    min_severity: str | None = None
    categories: list[str] | None = None


class NotificationChannelUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    # Routing filters
    facility_ids: list[UUID] | None = None
    min_severity: str | None = None
    categories: list[str] | None = None


class NotificationChannelResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    channel_type: str
    config: dict
    enabled: bool
    facility_ids: list[UUID] | None = None
    min_severity: str | None = None
    categories: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationChannelListResponse(BaseModel):
    channels: list[NotificationChannelResponse]
    total: int


class NotificationLogResponse(BaseModel):
    id: UUID
    org_id: UUID
    channel_id: UUID | None
    facility_id: UUID | None
    subject: str
    body: str
    channel_type: str
    status: str
    error_message: str | None
    sent_at: datetime

    model_config = {"from_attributes": True}


class NotificationLogListResponse(BaseModel):
    logs: list[NotificationLogResponse]
    total: int


class NotificationTestRequest(BaseModel):
    subject: str = "Kelvex Test Notification"
    body: str = "This is a test notification from Kelvex. If you received this, your channel is configured correctly."

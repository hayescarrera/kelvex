"""
HACCP/FDA Compliance Models — temperature logging, excursion tracking,
critical control points, and audit-ready compliance records.

Cold storage facilities must comply with:
  - FDA Food Safety Modernization Act (FSMA)
  - HACCP (Hazard Analysis Critical Control Points)
  - 21 CFR Part 110 (cGMP for food storage)

Key concepts:
  - CriticalControlPoint (CCP): a zone/equipment with defined temp limits
  - ComplianceLog: periodic temperature readings with pass/fail status
  - TempExcursion: any period where temp went out of range
  - ComplianceReport: generated reports for audits with sign-off
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class CriticalControlPoint(Base):
    """A monitored point (zone or equipment) with defined temperature limits."""
    __tablename__ = "critical_control_points"
    __table_args__ = (
        Index("ix_ccp_facility", "facility_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    # What is being monitored
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True
    )
    metric_name: Mapped[str] = mapped_column(String(50), default="temperature")

    # Temperature limits (in facility's configured unit)
    temp_min: Mapped[float] = mapped_column(Float, nullable=False)  # Lower critical limit
    temp_max: Mapped[float] = mapped_column(Float, nullable=False)  # Upper critical limit
    temp_unit: Mapped[str] = mapped_column(String(10), default="degF")  # degF or degC
    warning_offset: Mapped[float] = mapped_column(Float, default=2.0)  # Warning before critical

    # Monitoring config
    check_interval_min: Mapped[int] = mapped_column(Integer, default=15)  # How often to check
    excursion_threshold_min: Mapped[int] = mapped_column(Integer, default=30)  # How long out-of-range before excursion

    # HACCP fields
    hazard_type: Mapped[str | None] = mapped_column(String(100), nullable=True)  # biological, chemical, physical
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)  # What to do on excursion
    verification_method: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<CCP {self.name} [{self.temp_min}-{self.temp_max}{self.temp_unit}]>"


class ComplianceLog(Base):
    """Individual temperature compliance check — one row per CCP per check interval."""
    __tablename__ = "compliance_logs"
    __table_args__ = (
        Index("ix_compliance_log_ccp_time", "ccp_id", "checked_at"),
        Index("ix_compliance_log_facility_time", "facility_id", "checked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ccp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("critical_control_points.id", ondelete="CASCADE"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )

    # Reading
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    temp_unit: Mapped[str] = mapped_column(String(10), default="degF")
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pass, warning, critical, no_data

    # Limits at time of check (frozen for audit trail)
    limit_min: Mapped[float] = mapped_column(Float, nullable=False)
    limit_max: Mapped[float] = mapped_column(Float, nullable=False)

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    source: Mapped[str] = mapped_column(String(50), default="auto")  # auto, manual


class TempExcursion(Base):
    """A temperature excursion event — contiguous period where a CCP was out of range."""
    __tablename__ = "temp_excursions"
    __table_args__ = (
        Index("ix_excursion_facility_time", "facility_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ccp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("critical_control_points.id", ondelete="CASCADE"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    # Excursion details
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # warning, critical
    peak_temp: Mapped[float] = mapped_column(Float, nullable=False)  # Worst temp during excursion
    avg_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_breached: Mapped[str] = mapped_column(String(10), nullable=False)  # high, low

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Resolution
    state: Mapped[str] = mapped_column(String(20), default="active")  # active, resolved, acknowledged
    corrective_action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ComplianceReport(Base):
    """Generated compliance report for FDA/HACCP audits."""
    __tablename__ = "compliance_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    # Report config
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)  # daily, weekly, monthly, custom
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Summary stats (denormalized for quick access)
    total_checks: Mapped[int] = mapped_column(Integer, default=0)
    passed_checks: Mapped[int] = mapped_column(Integer, default=0)
    failed_checks: Mapped[int] = mapped_column(Integer, default=0)
    excursion_count: Mapped[int] = mapped_column(Integer, default=0)
    compliance_pct: Mapped[float] = mapped_column(Float, default=100.0)

    # Full report data (JSONB for flexibility)
    report_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Sign-off
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sign_off_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    state: Mapped[str] = mapped_column(String(20), default="draft")  # draft, pending_review, signed_off
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MaintenanceTask(Base):
    """Preventive maintenance task template and work order."""
    __tablename__ = "maintenance_tasks"
    __table_args__ = (
        Index("ix_maintenance_facility", "facility_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    # What
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(50), default="preventive"
    )  # preventive, corrective, inspection, calibration
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low, medium, high, critical
    # Provenance: the alert this work order was generated from, if any —
    # lets the alert inbox show the WO lifecycle inline
    source_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Equipment target
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True
    )
    compressor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compressors.id", ondelete="SET NULL"), nullable=True
    )

    # Schedule
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Every N days
    recurrence_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Or every N operating hours

    # Status
    state: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled, in_progress, completed, overdue, cancelled
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Assignment
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Completion
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    parts_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # [{"part": "oil filter", "qty": 1}]
    labor_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    checklist: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # [{"item": "Check oil level", "done": true}]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EscalationPolicy(Base):
    """Alert escalation policy — defines who gets notified at each escalation level."""
    __tablename__ = "escalation_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Escalation levels — ordered array of notification targets
    levels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    """
    [
      {"level": 1, "delay_minutes": 0, "notify": ["channel:<uuid>"], "label": "On-call technician"},
      {"level": 2, "delay_minutes": 15, "notify": ["channel:<uuid>", "user:<uuid>"], "label": "Plant manager"},
      {"level": 3, "delay_minutes": 60, "notify": ["channel:<uuid>"], "label": "Operations director"}
    ]
    """

    # Which alerts use this policy
    min_severity: Mapped[str] = mapped_column(String(20), default="high")  # Only escalate high+ alerts
    facility_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # null = all facilities

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class EscalationEvent(Base):
    """Tracks individual escalation actions taken on alerts."""
    __tablename__ = "escalation_events"
    __table_args__ = (
        Index("ix_escalation_alert", "alert_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation_policies.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    notified_targets: Mapped[list] = mapped_column(JSONB, default=list)
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

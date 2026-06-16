"""
Detection & Forecasting Settings API.

Endpoints:
  GET    /detection/settings    — Return org's feature flag state
  PATCH  /detection/settings    — Enable/disable auto_detection and/or forecasting
  GET    /detection/forecasts   — List circuit forecasts for the org
  GET    /detection/insights    — Summary of auto-detected events + forecast status
"""

import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.org_feature import OrgFeature
from app.models.circuit_forecast import CircuitForecast
from app.models.refrigerant import RefrigerantCircuit, LeakEvent

router = APIRouter(prefix="/detection", tags=["detection"])
logger = logging.getLogger(__name__)

ALLOWED_FEATURES = {"auto_detection", "forecasting"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class DetectionSettings(BaseModel):
    auto_detection: bool
    forecasting: bool


class DetectionSettingsPatch(BaseModel):
    auto_detection: Optional[bool] = None
    forecasting: Optional[bool] = None


class CircuitForecastOut(BaseModel):
    circuit_id: UUID
    circuit_name: Optional[str] = None
    org_id: UUID
    method: str
    projected_adds_lbs: Optional[float]
    projected_adds_lbs_low: Optional[float]
    projected_adds_lbs_high: Optional[float]
    lbs_per_day: Optional[float]
    days_to_aim_threshold: Optional[int]
    days_to_aim_warning: Optional[int]
    current_annual_leak_rate_pct: Optional[float]
    confidence: Optional[str]
    horizon_days: int
    computed_at: datetime

    class Config:
        from_attributes = True


class DetectionInsights(BaseModel):
    auto_detected_events: int
    manual_events: int
    detection_breakdown: dict
    circuits_forecasted: int
    circuits_approaching_threshold: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user: User) -> None:
    if user.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner or admin role required.",
        )


async def _get_feature_flags(org_id: UUID, db: AsyncSession) -> dict[str, bool]:
    result = await db.execute(
        select(OrgFeature).where(
            and_(
                OrgFeature.org_id == org_id,
                OrgFeature.feature_key.in_(list(ALLOWED_FEATURES)),
            )
        )
    )
    rows = result.scalars().all()
    flags: dict[str, bool] = {k: False for k in ALLOWED_FEATURES}
    for row in rows:
        flags[row.feature_key] = row.enabled
    return flags


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=DetectionSettings)
async def get_detection_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectionSettings:
    """Return the org's current feature flag state for detection and forecasting."""
    flags = await _get_feature_flags(current_user.org_id, db)
    return DetectionSettings(
        auto_detection=flags["auto_detection"],
        forecasting=flags["forecasting"],
    )


@router.patch("/settings", response_model=DetectionSettings)
async def update_detection_settings(
    body: DetectionSettingsPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectionSettings:
    """
    Upsert org-level feature flags.
    Requires owner or admin role.
    """
    _require_admin(current_user)

    updates: dict[str, bool] = {}
    if body.auto_detection is not None:
        updates["auto_detection"] = body.auto_detection
    if body.forecasting is not None:
        updates["forecasting"] = body.forecasting

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one feature flag must be specified.",
        )

    now = datetime.now(timezone.utc)

    for feature_key, enabled in updates.items():
        existing_result = await db.execute(
            select(OrgFeature).where(
                and_(
                    OrgFeature.org_id == current_user.org_id,
                    OrgFeature.feature_key == feature_key,
                )
            )
        )
        row = existing_result.scalar_one_or_none()

        if row is None:
            row = OrgFeature(
                org_id=current_user.org_id,
                feature_key=feature_key,
                enabled=enabled,
            )
            db.add(row)
        else:
            row.enabled = enabled
            row.updated_at = now

    await db.commit()

    # Return refreshed state
    flags = await _get_feature_flags(current_user.org_id, db)
    return DetectionSettings(
        auto_detection=flags["auto_detection"],
        forecasting=flags["forecasting"],
    )


@router.get("/forecasts", response_model=list[CircuitForecastOut])
async def get_forecasts(
    facility_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CircuitForecastOut]:
    """
    List all CircuitForecast rows for the org (optionally filtered by facility).
    Joins circuit name from refrigerant_circuits.
    """
    # Build the base query joining circuit for the name
    query = (
        select(CircuitForecast, RefrigerantCircuit.name.label("circuit_name"))
        .join(
            RefrigerantCircuit,
            RefrigerantCircuit.id == CircuitForecast.circuit_id,
            isouter=True,
        )
        .where(CircuitForecast.org_id == current_user.org_id)
    )

    if facility_id is not None:
        query = query.where(RefrigerantCircuit.facility_id == facility_id)

    result = await db.execute(query)
    rows = result.all()

    output = []
    for forecast_row, circuit_name in rows:
        d = CircuitForecastOut(
            circuit_id=forecast_row.circuit_id,
            circuit_name=circuit_name,
            org_id=forecast_row.org_id,
            method=forecast_row.method,
            projected_adds_lbs=forecast_row.projected_adds_lbs,
            projected_adds_lbs_low=forecast_row.projected_adds_lbs_low,
            projected_adds_lbs_high=forecast_row.projected_adds_lbs_high,
            lbs_per_day=forecast_row.lbs_per_day,
            days_to_aim_threshold=forecast_row.days_to_aim_threshold,
            days_to_aim_warning=forecast_row.days_to_aim_warning,
            current_annual_leak_rate_pct=forecast_row.current_annual_leak_rate_pct,
            confidence=forecast_row.confidence,
            horizon_days=forecast_row.horizon_days,
            computed_at=forecast_row.computed_at,
        )
        output.append(d)

    return output


@router.get("/insights", response_model=DetectionInsights)
async def get_detection_insights(
    facility_id: Optional[UUID] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectionInsights:
    """
    Summary of auto-detected events in the last N days and forecast status.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # ── Leak events query ──────────────────────────────────────────────────────
    events_query = select(LeakEvent).where(
        and_(
            LeakEvent.org_id == current_user.org_id,
            LeakEvent.detected_at >= cutoff,
        )
    )
    if facility_id is not None:
        events_query = events_query.where(LeakEvent.facility_id == facility_id)

    events_result = await db.execute(events_query)
    events = events_result.scalars().all()

    auto_methods = {"pressure_trend", "refrigerant_add_pattern", "multi_signal"}
    manual_methods = {"manual", "technician_reported"}

    auto_detected_events = 0
    manual_events = 0
    detection_breakdown: dict[str, int] = {
        "pressure_trend": 0,
        "refrigerant_add_pattern": 0,
        "multi_signal": 0,
    }

    for event in events:
        if event.detection_method in auto_methods:
            auto_detected_events += 1
            if event.detection_method in detection_breakdown:
                detection_breakdown[event.detection_method] += 1
        elif event.detection_method in manual_methods:
            manual_events += 1

    # ── Forecast counts ────────────────────────────────────────────────────────
    forecasts_query = (
        select(CircuitForecast)
        .join(
            RefrigerantCircuit,
            RefrigerantCircuit.id == CircuitForecast.circuit_id,
            isouter=True,
        )
        .where(CircuitForecast.org_id == current_user.org_id)
    )
    if facility_id is not None:
        forecasts_query = forecasts_query.where(
            RefrigerantCircuit.facility_id == facility_id
        )

    forecasts_result = await db.execute(forecasts_query)
    forecasts = forecasts_result.scalars().all()

    circuits_forecasted = len(forecasts)
    circuits_approaching_threshold = sum(
        1
        for f in forecasts
        if f.days_to_aim_threshold is not None and f.days_to_aim_threshold < 90
    )

    return DetectionInsights(
        auto_detected_events=auto_detected_events,
        manual_events=manual_events,
        detection_breakdown=detection_breakdown,
        circuits_forecasted=circuits_forecasted,
        circuits_approaching_threshold=circuits_approaching_threshold,
    )

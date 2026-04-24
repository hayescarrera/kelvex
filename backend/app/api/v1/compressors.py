"""
Compressor API — ammonia compressor asset management and telemetry.

Endpoints:
  POST   /facilities/{id}/compressors                         — Add compressor
  GET    /facilities/{id}/compressors                          — List compressors
  GET    /facilities/{id}/compressors/summary                  — Fleet health summary
  GET    /facilities/{id}/compressors/{cid}                    — Get compressor
  PATCH  /facilities/{id}/compressors/{cid}                    — Update compressor
  DELETE /facilities/{id}/compressors/{cid}                    — Delete compressor
  POST   /facilities/{id}/compressors/{cid}/readings           — Ingest reading
  POST   /facilities/{id}/compressors/{cid}/readings/batch     — Ingest batch
  GET    /facilities/{id}/compressors/{cid}/readings           — List readings
  POST   /facilities/{id}/compressors/{cid}/health-check       — Trigger health check
"""

from uuid import UUID
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.compressor import Compressor, CompressorReading
from app.schemas.compressor import (
    CompressorCreate, CompressorUpdate, CompressorResponse, CompressorListResponse,
    ReadingCreate, ReadingResponse, ReadingListResponse,
    CompressorHealthSummary, FacilityCompressorSummary,
)

router = APIRouter(prefix="/facilities/{facility_id}/compressors", tags=["compressors"])


async def _get_facility(facility_id: UUID, user: User, db: AsyncSession) -> Facility:
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


async def _get_compressor(compressor_id: UUID, facility_id: UUID, db: AsyncSession) -> Compressor:
    result = await db.execute(
        select(Compressor).where(
            Compressor.id == compressor_id,
            Compressor.facility_id == facility_id,
        )
    )
    comp = result.scalar_one_or_none()
    if not comp:
        raise HTTPException(status_code=404, detail="Compressor not found")
    return comp


# ── CRUD ─────────────────────────────────────────

@router.post("", response_model=CompressorResponse, status_code=status.HTTP_201_CREATED)
async def create_compressor(
    facility_id: UUID,
    data: CompressorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a compressor to a facility's refrigeration plant."""
    await _get_facility(facility_id, current_user, db)

    comp = Compressor(facility_id=facility_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "metadata":
            setattr(comp, "metadata_", value)
        else:
            setattr(comp, field, value)

    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@router.get("", response_model=CompressorListResponse)
async def list_compressors(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all compressors for a facility."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(Compressor)
        .where(Compressor.facility_id == facility_id)
        .order_by(Compressor.rack_name, Compressor.name)
    )
    comps = list(result.scalars().all())
    return CompressorListResponse(compressors=comps, total=len(comps))


@router.get("/summary", response_model=FacilityCompressorSummary)
async def compressor_summary(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get fleet-level compressor health summary for a facility."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(Compressor)
        .where(Compressor.facility_id == facility_id)
        .order_by(Compressor.rack_name, Compressor.name)
    )
    comps = list(result.scalars().all())

    summaries = []
    total_kw = 0.0
    running_count = 0
    alarm_count = 0
    health_scores = []

    for comp in comps:
        # Get latest reading
        reading_result = await db.execute(
            select(CompressorReading)
            .where(CompressorReading.compressor_id == comp.id)
            .order_by(desc(CompressorReading.recorded_at))
            .limit(1)
        )
        latest = reading_result.scalar_one_or_none()

        anomalies = _detect_anomalies(comp, latest) if latest else []

        summary = CompressorHealthSummary(
            compressor_id=comp.id,
            name=comp.name,
            tag=comp.tag,
            manufacturer=comp.manufacturer,
            model=comp.model,
            state=comp.state,
            health_score=comp.health_score,
            refrigerant=comp.refrigerant,
            hp=comp.hp,
            rack_name=comp.rack_name,
            discharge_pressure_psi=latest.discharge_pressure_psi if latest else None,
            suction_pressure_psi=latest.suction_pressure_psi if latest else None,
            oil_temp_f=latest.oil_temp_f if latest else None,
            bearing_temp_f=latest.bearing_temp_f if latest else None,
            vibration_ips=latest.vibration_ips if latest else None,
            amp_draw=latest.amp_draw if latest else None,
            kw=latest.kw if latest else None,
            slide_valve_pct=latest.slide_valve_pct if latest else None,
            running=latest.running if latest else None,
            last_reading_at=comp.last_reading_at,
            anomalies=anomalies,
        )
        summaries.append(summary)

        if comp.state == "running":
            running_count += 1
        if comp.state == "alarm" or (latest and latest.alarm_active):
            alarm_count += 1
        if comp.health_score is not None:
            health_scores.append(comp.health_score)
        if latest and latest.kw:
            total_kw += latest.kw

    return FacilityCompressorSummary(
        facility_id=facility_id,
        total_compressors=len(comps),
        running=running_count,
        in_alarm=alarm_count,
        avg_health_score=round(sum(health_scores) / len(health_scores), 1) if health_scores else None,
        total_kw=round(total_kw, 1) if total_kw > 0 else None,
        total_capacity_tons=sum(c.capacity_tons for c in comps if c.capacity_tons) or None,
        compressors=summaries,
    )


@router.get("/{compressor_id}", response_model=CompressorResponse)
async def get_compressor(
    facility_id: UUID,
    compressor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single compressor."""
    await _get_facility(facility_id, current_user, db)
    return await _get_compressor(compressor_id, facility_id, db)


@router.patch("/{compressor_id}", response_model=CompressorResponse)
async def update_compressor(
    facility_id: UUID,
    compressor_id: UUID,
    data: CompressorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update compressor details or alarm thresholds."""
    await _get_facility(facility_id, current_user, db)
    comp = await _get_compressor(compressor_id, facility_id, db)

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "metadata":
            setattr(comp, "metadata_", value)
        else:
            setattr(comp, field, value)

    await db.commit()
    await db.refresh(comp)
    return comp


@router.delete("/{compressor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_compressor(
    facility_id: UUID,
    compressor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a compressor and all its readings."""
    await _get_facility(facility_id, current_user, db)
    comp = await _get_compressor(compressor_id, facility_id, db)
    await db.delete(comp)
    await db.commit()


# ── Readings / Telemetry ─────────────────────────

@router.post("/{compressor_id}/readings", response_model=ReadingResponse, status_code=status.HTTP_201_CREATED)
async def ingest_reading(
    facility_id: UUID,
    compressor_id: UUID,
    data: ReadingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a single compressor telemetry reading."""
    await _get_facility(facility_id, current_user, db)
    comp = await _get_compressor(compressor_id, facility_id, db)

    reading = CompressorReading(
        compressor_id=compressor_id,
        **data.model_dump(exclude_unset=True),
    )
    if reading.recorded_at is None:
        reading.recorded_at = datetime.now(timezone.utc)

    db.add(reading)

    # Update compressor last_reading_at and state
    comp.last_reading_at = reading.recorded_at
    if reading.running is True:
        comp.state = "running"
    elif reading.running is False and comp.state == "running":
        comp.state = "standby"
    if reading.alarm_active:
        comp.state = "alarm"

    await db.commit()
    await db.refresh(reading)
    return reading


@router.post("/{compressor_id}/readings/batch", status_code=status.HTTP_201_CREATED)
async def ingest_readings_batch(
    facility_id: UUID,
    compressor_id: UUID,
    readings: list[ReadingCreate],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a batch of compressor telemetry readings."""
    await _get_facility(facility_id, current_user, db)
    comp = await _get_compressor(compressor_id, facility_id, db)

    created = []
    latest_time = comp.last_reading_at
    for data in readings:
        reading = CompressorReading(
            compressor_id=compressor_id,
            **data.model_dump(exclude_unset=True),
        )
        if reading.recorded_at is None:
            reading.recorded_at = datetime.now(timezone.utc)
        db.add(reading)
        created.append(reading)
        if latest_time is None or reading.recorded_at > latest_time:
            latest_time = reading.recorded_at

    comp.last_reading_at = latest_time
    await db.commit()
    return {"status": "ok", "count": len(created)}


@router.get("/{compressor_id}/readings", response_model=ReadingListResponse)
async def list_readings(
    facility_id: UUID,
    compressor_id: UUID,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent readings for a compressor. Default: last 24 hours."""
    await _get_facility(facility_id, current_user, db)
    await _get_compressor(compressor_id, facility_id, db)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(CompressorReading)
        .where(
            CompressorReading.compressor_id == compressor_id,
            CompressorReading.recorded_at >= since,
        )
        .order_by(CompressorReading.recorded_at)
        .limit(limit)
    )
    readings = list(result.scalars().all())
    return ReadingListResponse(readings=readings, total=len(readings))


# ── Health check trigger ─────────────────────────

@router.post("/{compressor_id}/health-check")
async def trigger_health_check(
    facility_id: UUID,
    compressor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate health score recalculation."""
    await _get_facility(facility_id, current_user, db)
    comp = await _get_compressor(compressor_id, facility_id, db)

    from app.services.compressor_health import compute_health_score
    score, anomalies = await compute_health_score(comp.id, db)

    comp.health_score = score
    if anomalies and comp.state != "maintenance":
        comp.state = "alarm" if score is not None and score < 50 else comp.state
    await db.commit()

    return {
        "compressor_id": str(comp.id),
        "health_score": score,
        "anomalies": anomalies,
    }


# ── Anomaly detection helper ────────────────────

def _detect_anomalies(comp: Compressor, reading: CompressorReading) -> list[str]:
    """Quick anomaly check against compressor alarm thresholds."""
    anomalies = []
    if comp.alarm_discharge_psi_high and reading.discharge_pressure_psi:
        if reading.discharge_pressure_psi > comp.alarm_discharge_psi_high:
            anomalies.append(f"High discharge pressure: {reading.discharge_pressure_psi} psi")
    if comp.alarm_suction_psi_low and reading.suction_pressure_psi:
        if reading.suction_pressure_psi < comp.alarm_suction_psi_low:
            anomalies.append(f"Low suction pressure: {reading.suction_pressure_psi} psi")
    if comp.alarm_oil_temp_high and reading.oil_temp_f:
        if reading.oil_temp_f > comp.alarm_oil_temp_high:
            anomalies.append(f"High oil temp: {reading.oil_temp_f}°F")
    if comp.alarm_bearing_temp_high and reading.bearing_temp_f:
        if reading.bearing_temp_f > comp.alarm_bearing_temp_high:
            anomalies.append(f"High bearing temp: {reading.bearing_temp_f}°F")
    if comp.alarm_vibration_high and reading.vibration_ips:
        if reading.vibration_ips > comp.alarm_vibration_high:
            anomalies.append(f"High vibration: {reading.vibration_ips} in/s")
    if comp.alarm_amp_draw_high and reading.amp_draw:
        if reading.amp_draw > comp.alarm_amp_draw_high:
            anomalies.append(f"High amp draw: {reading.amp_draw}A")
    return anomalies

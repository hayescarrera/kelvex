"""
Reports API — power consumption, audit logs, and facility summaries.

Endpoints:
  GET  /facilities/{id}/reports/power        — Power consumption over time
  GET  /facilities/{id}/reports/power-summary — Aggregated power stats
  GET  /facilities/{id}/reports/audit-log     — Control action audit log
  GET  /reports/digest-preview                — Preview email digest content
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, text

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.telemetry import Telemetry
from app.models.facility import Facility, Equipment
from app.models.control import CommandQueue, AutomationRule, ControlSequence
from app.models.alert import Alert, Event
from app.models.notification import NotificationLog

router = APIRouter(tags=["reports"])


async def _verify_facility_access(facility_id: UUID, user: User, db: AsyncSession):
    """Verify the facility belongs to the current user's org. Raises 404 if not."""
    from fastapi import HTTPException
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Facility not found")


# ── Power Consumption ────────────────────────────────

@router.get("/facilities/{facility_id}/reports/power")
async def power_consumption(
    facility_id: UUID,
    start: datetime = Query(None, description="Start of range (ISO). Defaults to 7 days ago"),
    end: datetime = Query(None, description="End of range (ISO). Defaults to now"),
    interval: str = Query("1h", description="Bucket interval: 5m, 15m, 1h, 1d"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return time-bucketed power consumption from equipment telemetry."""
    await _verify_facility_access(facility_id, current_user, db)
    now = datetime.now(timezone.utc)
    if not start:
        start = now - timedelta(days=7)
    if not end:
        end = now

    # Validate interval
    valid_intervals = {"5m": "5 minutes", "15m": "15 minutes", "1h": "1 hour", "1d": "1 day"}
    pg_interval = valid_intervals.get(interval, "1 hour")

    # Query kw_demand telemetry bucketed by time
    query = text("""
        SELECT
            time_bucket(:interval, t.time) AS bucket,
            SUM(t.value) AS total_kw,
            AVG(t.value) AS avg_kw,
            MAX(t.value) AS peak_kw,
            COUNT(DISTINCT t.equipment_id) AS equipment_count
        FROM telemetry t
        JOIN equipment e ON e.id = t.equipment_id
        WHERE e.facility_id = :facility_id
          AND t.metric_name = 'kw_demand'
          AND t.time >= :start_time
          AND t.time <= :end_time
        GROUP BY bucket
        ORDER BY bucket
    """)

    result = await db.execute(query, {
        "interval": pg_interval,
        "facility_id": str(facility_id),
        "start_time": start,
        "end_time": end,
    })
    rows = result.fetchall()

    # Also get energy consumption (kWh estimate) from power readings
    # kWh = sum of (kW * hours_per_interval)
    hours_map = {"5m": 1 / 12, "15m": 0.25, "1h": 1.0, "1d": 24.0}
    hours_per_bucket = hours_map.get(interval, 1.0)

    data_points = []
    total_kwh = 0.0
    peak_demand = 0.0
    for row in rows:
        bucket_kw = float(row.total_kw or 0)
        avg_kw = float(row.avg_kw or 0)
        pk = float(row.peak_kw or 0)
        kwh = avg_kw * hours_per_bucket
        total_kwh += kwh
        if pk > peak_demand:
            peak_demand = pk
        data_points.append({
            "time": row.bucket.isoformat() if row.bucket else None,
            "total_kw": round(bucket_kw, 2),
            "avg_kw": round(avg_kw, 2),
            "peak_kw": round(pk, 2),
            "kwh_estimate": round(kwh, 2),
            "equipment_count": row.equipment_count,
        })

    return {
        "facility_id": str(facility_id),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "interval": interval,
        "total_kwh": round(total_kwh, 2),
        "peak_demand_kw": round(peak_demand, 2),
        "data_points": data_points,
        "count": len(data_points),
    }


@router.get("/facilities/{facility_id}/reports/power-summary")
async def power_summary(
    facility_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Number of days to summarize"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated power statistics for a facility over N days."""
    await _verify_facility_access(facility_id, current_user, db)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total and avg power
    result = await db.execute(
        select(
            func.sum(Telemetry.value).label("total_kw_readings"),
            func.avg(Telemetry.value).label("avg_kw"),
            func.max(Telemetry.value).label("peak_kw"),
            func.min(Telemetry.value).label("min_kw"),
            func.count().label("reading_count"),
        )
        .join(Equipment, Equipment.id == Telemetry.equipment_id)
        .where(
            Equipment.facility_id == facility_id,
            Telemetry.metric_name == "kw_demand",
            Telemetry.time >= since,
        )
    )
    row = result.one()

    # Per-equipment breakdown
    eq_result = await db.execute(
        select(
            Equipment.id,
            Equipment.name,
            Equipment.equipment_type,
            func.avg(Telemetry.value).label("avg_kw"),
            func.max(Telemetry.value).label("peak_kw"),
            func.count().label("readings"),
        )
        .join(Telemetry, Telemetry.equipment_id == Equipment.id)
        .where(
            Equipment.facility_id == facility_id,
            Telemetry.metric_name == "kw_demand",
            Telemetry.time >= since,
        )
        .group_by(Equipment.id, Equipment.name, Equipment.equipment_type)
        .order_by(func.avg(Telemetry.value).desc())
    )
    equipment_breakdown = [
        {
            "equipment_id": str(r.id),
            "name": r.name,
            "equipment_type": r.equipment_type,
            "avg_kw": round(float(r.avg_kw or 0), 2),
            "peak_kw": round(float(r.peak_kw or 0), 2),
            "readings": r.readings,
        }
        for r in eq_result.all()
    ]

    # Estimated kWh (readings come roughly every minute for 5m aggregates)
    avg_kw = float(row.avg_kw or 0)
    hours = days * 24
    estimated_kwh = avg_kw * hours

    return {
        "facility_id": str(facility_id),
        "days": days,
        "avg_kw": round(avg_kw, 2),
        "peak_kw": round(float(row.peak_kw or 0), 2),
        "min_kw": round(float(row.min_kw or 0), 2),
        "estimated_kwh": round(estimated_kwh, 2),
        "reading_count": row.reading_count or 0,
        "equipment_breakdown": equipment_breakdown,
    }


# ── Audit Log ────────────────────────────────────────

@router.get("/facilities/{facility_id}/reports/audit-log")
async def audit_log(
    facility_id: UUID,
    start: datetime = Query(None),
    end: datetime = Query(None),
    action_type: str = Query(None, description="Filter by command_type"),
    state: str = Query(None, description="Filter by command state"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return control command history with full audit details."""
    await _verify_facility_access(facility_id, current_user, db)
    now = datetime.now(timezone.utc)
    if not start:
        start = now - timedelta(days=30)
    if not end:
        end = now

    # Build query
    base = (
        select(CommandQueue)
        .where(
            CommandQueue.facility_id == facility_id,
            CommandQueue.issued_at >= start,
            CommandQueue.issued_at <= end,
        )
    )
    if action_type:
        base = base.where(CommandQueue.command_type == action_type)
    if state:
        base = base.where(CommandQueue.state == state)

    # Count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    result = await db.execute(
        base.order_by(CommandQueue.issued_at.desc())
        .limit(limit)
        .offset(offset)
    )
    commands = result.scalars().all()

    # Also get stats
    stats_result = await db.execute(
        select(
            CommandQueue.state,
            func.count().label("count"),
        )
        .where(
            CommandQueue.facility_id == facility_id,
            CommandQueue.issued_at >= start,
            CommandQueue.issued_at <= end,
        )
        .group_by(CommandQueue.state)
    )
    state_counts = {r.state: r.count for r in stats_result.all()}

    # Command type breakdown
    type_result = await db.execute(
        select(
            CommandQueue.command_type,
            func.count().label("count"),
        )
        .where(
            CommandQueue.facility_id == facility_id,
            CommandQueue.issued_at >= start,
            CommandQueue.issued_at <= end,
        )
        .group_by(CommandQueue.command_type)
        .order_by(func.count().desc())
    )
    type_counts = {r.command_type: r.count for r in type_result.all()}

    return {
        "facility_id": str(facility_id),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": total,
        "by_state": state_counts,
        "by_type": type_counts,
        "commands": [
            {
                "id": str(cmd.id),
                "command_type": cmd.command_type,
                "state": cmd.state,
                "parameters": cmd.parameters,
                "priority": cmd.priority,
                "target_equipment_id": str(cmd.target_equipment_id) if cmd.target_equipment_id else None,
                "target_zone_id": str(cmd.target_zone_id) if cmd.target_zone_id else None,
                "agent_id": str(cmd.agent_id),
                "issued_by": str(cmd.issued_by) if cmd.issued_by else None,
                "issued_at": cmd.issued_at.isoformat() if cmd.issued_at else None,
                "sent_at": cmd.sent_at.isoformat() if cmd.sent_at else None,
                "completed_at": cmd.completed_at.isoformat() if cmd.completed_at else None,
                "error_message": cmd.error_message,
                "result": cmd.result,
            }
            for cmd in commands
        ],
    }


# ── Digest Preview ───────────────────────────────────

@router.get("/reports/digest-preview")
async def digest_preview(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview the email digest content for the current user's org."""
    org_id = current_user.org_id
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Facility list
    fac_result = await db.execute(
        select(Facility.id, Facility.name).where(
            Facility.org_id == org_id,
            Facility.deleted_at == None,
        )
    )
    facilities = fac_result.all()

    # Alerts summary
    alert_result = await db.execute(
        select(
            Alert.severity,
            Alert.state,
            func.count().label("count"),
        )
        .join(Facility, Facility.id == Alert.facility_id)
        .where(
            Facility.org_id == org_id,
            Alert.created_at >= since,
        )
        .group_by(Alert.severity, Alert.state)
    )
    alert_stats = {}
    total_new_alerts = 0
    for r in alert_result.all():
        key = f"{r.severity}_{r.state}"
        alert_stats[key] = r.count
        if r.state == "active":
            total_new_alerts += r.count

    # Active alerts by severity
    active_by_severity = {}
    for sev in ["critical", "high", "medium", "low", "info"]:
        active_by_severity[sev] = alert_stats.get(f"{sev}_active", 0)

    # Commands executed
    cmd_result = await db.execute(
        select(func.count()).where(
            CommandQueue.facility_id.in_([f.id for f in facilities]),
            CommandQueue.issued_at >= since,
        )
    )
    commands_total = cmd_result.scalar() or 0

    cmd_completed = (await db.execute(
        select(func.count()).where(
            CommandQueue.facility_id.in_([f.id for f in facilities]),
            CommandQueue.issued_at >= since,
            CommandQueue.state == "completed",
        )
    )).scalar() or 0

    cmd_failed = (await db.execute(
        select(func.count()).where(
            CommandQueue.facility_id.in_([f.id for f in facilities]),
            CommandQueue.issued_at >= since,
            CommandQueue.state == "failed",
        )
    )).scalar() or 0

    # Automation rule fires
    rule_result = await db.execute(
        select(func.sum(AutomationRule.execution_count_today)).where(
            AutomationRule.facility_id.in_([f.id for f in facilities]),
        )
    )
    rule_fires = rule_result.scalar() or 0

    # Notification deliveries
    notif_result = await db.execute(
        select(
            NotificationLog.status,
            func.count().label("count"),
        )
        .where(
            NotificationLog.org_id == org_id,
            NotificationLog.sent_at >= since,
        )
        .group_by(NotificationLog.status)
    )
    notif_stats = {r.status: r.count for r in notif_result.all()}

    return {
        "period_hours": hours,
        "since": since.isoformat(),
        "facilities_count": len(facilities),
        "facilities": [{"id": str(f.id), "name": f.name} for f in facilities],
        "alerts": {
            "new_total": total_new_alerts,
            "active_by_severity": active_by_severity,
        },
        "commands": {
            "total": commands_total,
            "completed": cmd_completed,
            "failed": cmd_failed,
        },
        "automation": {
            "rule_fires_today": rule_fires,
        },
        "notifications": notif_stats,
    }


# ── CSV Exports ─────────────────────────────────────

def _csv_response(filename: str, rows: list[dict]) -> StreamingResponse:
    """Build a streaming CSV response from a list of dicts."""
    if not rows:
        return StreamingResponse(
            iter(["No data\n"]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/facilities/{facility_id}/reports/power/export")
async def export_power_csv(
    facility_id: UUID,
    start: datetime = Query(None),
    end: datetime = Query(None),
    interval: str = Query("1h"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export power consumption data as CSV."""
    await _verify_facility_access(facility_id, current_user, db)
    now = datetime.now(timezone.utc)
    if not start:
        start = now - timedelta(days=7)
    if not end:
        end = now

    valid_intervals = {"5m": "5 minutes", "15m": "15 minutes", "1h": "1 hour", "1d": "1 day"}
    pg_interval = valid_intervals.get(interval, "1 hour")

    query = text("""
        SELECT
            time_bucket(:interval, t.time) AS bucket,
            SUM(t.value) AS total_kw,
            AVG(t.value) AS avg_kw,
            MAX(t.value) AS peak_kw,
            COUNT(DISTINCT t.equipment_id) AS equipment_count
        FROM telemetry t
        JOIN equipment e ON e.id = t.equipment_id
        WHERE e.facility_id = :facility_id
          AND t.metric_name = 'kw_demand'
          AND t.time >= :start_time
          AND t.time <= :end_time
        GROUP BY bucket
        ORDER BY bucket
    """)

    result = await db.execute(query, {
        "interval": pg_interval,
        "facility_id": str(facility_id),
        "start_time": start,
        "end_time": end,
    })

    rows = [
        {
            "timestamp": row.bucket.isoformat() if row.bucket else "",
            "total_kw": round(float(row.total_kw or 0), 2),
            "avg_kw": round(float(row.avg_kw or 0), 2),
            "peak_kw": round(float(row.peak_kw or 0), 2),
            "equipment_count": row.equipment_count,
        }
        for row in result.fetchall()
    ]

    return _csv_response(f"power_report_{facility_id}_{interval}.csv", rows)


@router.get("/facilities/{facility_id}/reports/audit-log/export")
async def export_audit_csv(
    facility_id: UUID,
    start: datetime = Query(None),
    end: datetime = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export control command audit log as CSV."""
    await _verify_facility_access(facility_id, current_user, db)
    now = datetime.now(timezone.utc)
    if not start:
        start = now - timedelta(days=30)
    if not end:
        end = now

    result = await db.execute(
        select(CommandQueue)
        .where(
            CommandQueue.facility_id == facility_id,
            CommandQueue.issued_at >= start,
            CommandQueue.issued_at <= end,
        )
        .order_by(CommandQueue.issued_at.desc())
        .limit(5000)
    )
    commands = result.scalars().all()

    rows = [
        {
            "id": str(cmd.id),
            "command_type": cmd.command_type,
            "state": cmd.state,
            "priority": cmd.priority,
            "agent_id": str(cmd.agent_id),
            "issued_at": cmd.issued_at.isoformat() if cmd.issued_at else "",
            "sent_at": cmd.sent_at.isoformat() if cmd.sent_at else "",
            "completed_at": cmd.completed_at.isoformat() if cmd.completed_at else "",
            "error_message": cmd.error_message or "",
        }
        for cmd in commands
    ]

    return _csv_response(f"audit_log_{facility_id}.csv", rows)


@router.get("/facilities/{facility_id}/alerts/export")
async def export_alerts_csv(
    facility_id: UUID,
    state: str = Query(None),
    severity: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export alerts as CSV."""
    await _verify_facility_access(facility_id, current_user, db)
    q = select(Alert).where(Alert.facility_id == facility_id)
    if state:
        q = q.where(Alert.state == state)
    if severity:
        q = q.where(Alert.severity == severity)
    q = q.order_by(Alert.triggered_at.desc()).limit(5000)

    result = await db.execute(q)
    alerts = result.scalars().all()

    rows = [
        {
            "id": str(a.id),
            "title": a.title,
            "severity": a.severity,
            "category": a.category or "",
            "state": a.state,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else "",
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else "",
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else "",
            "description": a.description or "",
        }
        for a in alerts
    ]

    return _csv_response(f"alerts_{facility_id}.csv", rows)

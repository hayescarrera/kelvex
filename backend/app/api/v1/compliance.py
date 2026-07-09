"""
HACCP/FDA Compliance API — critical control points, compliance logs,
excursions, reports, and sign-off workflow.

Endpoints:
  POST   /compliance/ccps                   — Create CCP
  GET    /compliance/ccps                   — List CCPs (filterable by facility)
  GET    /compliance/ccps/{id}              — Get CCP detail
  PATCH  /compliance/ccps/{id}              — Update CCP
  DELETE /compliance/ccps/{id}              — Deactivate CCP

  GET    /compliance/logs                   — List compliance check logs
  POST   /compliance/logs                   — Record manual compliance check

  GET    /compliance/excursions             — List temp excursions
  PATCH  /compliance/excursions/{id}        — Resolve / acknowledge excursion

  POST   /compliance/reports/generate       — Generate compliance report
  GET    /compliance/reports                — List reports
  GET    /compliance/reports/{id}           — Get report detail
  PATCH  /compliance/reports/{id}/sign-off  — Sign off report

  GET    /compliance/dashboard              — Summary stats for compliance dashboard
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped
from app.models.user import User
from app.models.facility import Facility
from app.models.compliance import (
    CriticalControlPoint, ComplianceLog, TempExcursion, ComplianceReport,
)
from app.services.audit_service import log_activity

router = APIRouter(prefix="/compliance", tags=["compliance"])


# ── Schemas ──────────────────────────────────────

class CCPCreate(BaseModel):
    facility_id: UUID
    name: str
    description: str | None = None
    zone_id: UUID | None = None
    equipment_id: UUID | None = None
    metric_name: str = "temperature"
    temp_min: float
    temp_max: float
    temp_unit: str = "degF"
    warning_offset: float = 2.0
    check_interval_min: int = 15
    excursion_threshold_min: int = 30
    hazard_type: str | None = None
    corrective_action: str | None = None
    verification_method: str | None = None


class CCPUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    temp_min: float | None = None
    temp_max: float | None = None
    warning_offset: float | None = None
    check_interval_min: int | None = None
    excursion_threshold_min: int | None = None
    hazard_type: str | None = None
    corrective_action: str | None = None
    verification_method: str | None = None
    is_active: bool | None = None


class ManualCheckCreate(BaseModel):
    ccp_id: UUID
    facility_id: UUID
    temperature: float
    temp_unit: str = "degF"


class ExcursionResolve(BaseModel):
    state: str = "resolved"  # resolved or acknowledged
    corrective_action_taken: str | None = None
    notes: str | None = None


class ReportGenerate(BaseModel):
    facility_id: UUID
    report_type: str = "weekly"  # daily, weekly, monthly, custom
    title: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


class ReportSignOff(BaseModel):
    sign_off_notes: str | None = None


# ── Helpers ──────────────────────────────────────

async def _verify_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


def _ccp_to_dict(ccp: CriticalControlPoint) -> dict:
    return {
        "id": str(ccp.id),
        "facility_id": str(ccp.facility_id),
        "org_id": str(ccp.org_id),
        "name": ccp.name,
        "description": ccp.description,
        "zone_id": str(ccp.zone_id) if ccp.zone_id else None,
        "equipment_id": str(ccp.equipment_id) if ccp.equipment_id else None,
        "metric_name": ccp.metric_name,
        "temp_min": ccp.temp_min,
        "temp_max": ccp.temp_max,
        "temp_unit": ccp.temp_unit,
        "warning_offset": ccp.warning_offset,
        "check_interval_min": ccp.check_interval_min,
        "excursion_threshold_min": ccp.excursion_threshold_min,
        "hazard_type": ccp.hazard_type,
        "corrective_action": ccp.corrective_action,
        "verification_method": ccp.verification_method,
        "is_active": ccp.is_active,
        "created_at": ccp.created_at.isoformat() if ccp.created_at else None,
    }


def _log_to_dict(log: ComplianceLog) -> dict:
    return {
        "id": str(log.id),
        "ccp_id": str(log.ccp_id),
        "facility_id": str(log.facility_id),
        "temperature": log.temperature,
        "temp_unit": log.temp_unit,
        "status": log.status,
        "limit_min": log.limit_min,
        "limit_max": log.limit_max,
        "checked_at": log.checked_at.isoformat() if log.checked_at else None,
        "source": log.source,
    }


def _excursion_to_dict(exc: TempExcursion) -> dict:
    return {
        "id": str(exc.id),
        "ccp_id": str(exc.ccp_id),
        "facility_id": str(exc.facility_id),
        "org_id": str(exc.org_id),
        "severity": exc.severity,
        "peak_temp": exc.peak_temp,
        "avg_temp": exc.avg_temp,
        "limit_breached": exc.limit_breached,
        "started_at": exc.started_at.isoformat() if exc.started_at else None,
        "ended_at": exc.ended_at.isoformat() if exc.ended_at else None,
        "duration_minutes": exc.duration_minutes,
        "state": exc.state,
        "corrective_action_taken": exc.corrective_action_taken,
        "resolved_by": str(exc.resolved_by) if exc.resolved_by else None,
        "resolved_at": exc.resolved_at.isoformat() if exc.resolved_at else None,
        "notes": exc.notes,
        "created_at": exc.created_at.isoformat() if exc.created_at else None,
    }


def _report_to_dict(rpt: ComplianceReport) -> dict:
    return {
        "id": str(rpt.id),
        "facility_id": str(rpt.facility_id),
        "org_id": str(rpt.org_id),
        "report_type": rpt.report_type,
        "title": rpt.title,
        "period_start": rpt.period_start.isoformat() if rpt.period_start else None,
        "period_end": rpt.period_end.isoformat() if rpt.period_end else None,
        "total_checks": rpt.total_checks,
        "passed_checks": rpt.passed_checks,
        "failed_checks": rpt.failed_checks,
        "excursion_count": rpt.excursion_count,
        "compliance_pct": rpt.compliance_pct,
        "report_data": rpt.report_data,
        "generated_by": str(rpt.generated_by) if rpt.generated_by else None,
        "signed_off_by": str(rpt.signed_off_by) if rpt.signed_off_by else None,
        "signed_off_at": rpt.signed_off_at.isoformat() if rpt.signed_off_at else None,
        "sign_off_notes": rpt.sign_off_notes,
        "state": rpt.state,
        "created_at": rpt.created_at.isoformat() if rpt.created_at else None,
    }


# ── Critical Control Points ─────────────────────

@router.post("/ccps", status_code=status.HTTP_201_CREATED)
async def create_ccp(
    data: CCPCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)
    ccp = CriticalControlPoint(
        **data.model_dump(),
        org_id=current_user.org_id,
    )
    db.add(ccp)
    await db.commit()
    await db.refresh(ccp)
    await log_activity(db, user=current_user, org_id=current_user.org_id, action="create",
                       resource_type="ccp", resource_id=str(ccp.id), resource_name=ccp.name,
                       facility_id=data.facility_id,
                       summary=f"Created CCP: {ccp.name} [{ccp.temp_min}-{ccp.temp_max}{ccp.temp_unit}]")
    return _ccp_to_dict(ccp)


@router.get("/ccps")
async def list_ccps(
    facility_id: UUID | None = Query(None),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(CriticalControlPoint).where(
        CriticalControlPoint.org_id == current_user.org_id
    )
    if facility_id:
        q = q.where(CriticalControlPoint.facility_id == facility_id)
    if active_only:
        q = q.where(CriticalControlPoint.is_active == True)
    q = q.order_by(CriticalControlPoint.name)
    result = await db.execute(q)
    ccps = result.scalars().all()
    return {"ccps": [_ccp_to_dict(c) for c in ccps], "total": len(ccps)}


@router.get("/ccps/{ccp_id}")
async def get_ccp(
    ccp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CriticalControlPoint).where(
            CriticalControlPoint.id == ccp_id,
            CriticalControlPoint.org_id == current_user.org_id,
        )
    )
    ccp = result.scalar_one_or_none()
    if not ccp:
        raise HTTPException(status_code=404, detail="CCP not found")
    return _ccp_to_dict(ccp)


@router.patch("/ccps/{ccp_id}")
async def update_ccp(
    ccp_id: UUID,
    data: CCPUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CriticalControlPoint).where(
            CriticalControlPoint.id == ccp_id,
            CriticalControlPoint.org_id == current_user.org_id,
        )
    )
    ccp = result.scalar_one_or_none()
    if not ccp:
        raise HTTPException(status_code=404, detail="CCP not found")
    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(ccp, k, v)
    await db.commit()
    await db.refresh(ccp)
    return _ccp_to_dict(ccp)


@router.delete("/ccps/{ccp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_ccp(
    ccp_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CriticalControlPoint).where(
            CriticalControlPoint.id == ccp_id,
            CriticalControlPoint.org_id == current_user.org_id,
        )
    )
    ccp = result.scalar_one_or_none()
    if not ccp:
        raise HTTPException(status_code=404, detail="CCP not found")
    ccp.is_active = False
    await db.commit()


# ── Compliance Logs ──────────────────────────────

@router.get("/logs")
async def list_compliance_logs(
    facility_id: UUID | None = Query(None),
    ccp_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    hours: int = Query(24),
    limit: int = Query(200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = (
        select(ComplianceLog)
        .join(CriticalControlPoint, ComplianceLog.ccp_id == CriticalControlPoint.id)
        .where(
            CriticalControlPoint.org_id == current_user.org_id,
            ComplianceLog.checked_at >= cutoff,
        )
    )
    if facility_id:
        q = q.where(ComplianceLog.facility_id == facility_id)
    if ccp_id:
        q = q.where(ComplianceLog.ccp_id == ccp_id)
    if status_filter:
        q = q.where(ComplianceLog.status == status_filter)
    q = q.order_by(ComplianceLog.checked_at.desc()).limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()
    return {"logs": [_log_to_dict(l) for l in logs], "total": len(logs)}


@router.post("/logs", status_code=status.HTTP_201_CREATED)
async def create_manual_check(
    data: ManualCheckCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a manual temperature compliance check."""
    await _verify_facility(data.facility_id, current_user, db)
    # Get CCP to determine limits
    result = await db.execute(
        select(CriticalControlPoint).where(
            CriticalControlPoint.id == data.ccp_id,
            CriticalControlPoint.org_id == current_user.org_id,
        )
    )
    ccp = result.scalar_one_or_none()
    if not ccp:
        raise HTTPException(status_code=404, detail="CCP not found")

    # Determine status
    temp = data.temperature
    if temp < ccp.temp_min or temp > ccp.temp_max:
        check_status = "critical"
    elif temp < (ccp.temp_min + ccp.warning_offset) or temp > (ccp.temp_max - ccp.warning_offset):
        check_status = "warning"
    else:
        check_status = "pass"

    log = ComplianceLog(
        ccp_id=ccp.id,
        facility_id=data.facility_id,
        temperature=temp,
        temp_unit=data.temp_unit,
        status=check_status,
        limit_min=ccp.temp_min,
        limit_max=ccp.temp_max,
        source="manual",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return _log_to_dict(log)


# ── Temperature Excursions ───────────────────────

@router.get("/excursions")
async def list_excursions(
    facility_id: UUID | None = Query(None),
    state: str | None = Query(None),
    severity: str | None = Query(None),
    days: int = Query(30),
    limit: int = Query(100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(TempExcursion).where(
        TempExcursion.org_id == current_user.org_id,
        TempExcursion.started_at >= cutoff,
    )
    if facility_id:
        q = q.where(TempExcursion.facility_id == facility_id)
    if state:
        q = q.where(TempExcursion.state == state)
    if severity:
        q = q.where(TempExcursion.severity == severity)
    q = q.order_by(TempExcursion.started_at.desc()).limit(limit)
    result = await db.execute(q)
    excursions = result.scalars().all()
    return {"excursions": [_excursion_to_dict(e) for e in excursions], "total": len(excursions)}


@router.patch("/excursions/{excursion_id}")
async def resolve_excursion(
    excursion_id: UUID,
    data: ExcursionResolve,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TempExcursion).where(
            TempExcursion.id == excursion_id,
            TempExcursion.org_id == current_user.org_id,
        )
    )
    exc = result.scalar_one_or_none()
    if not exc:
        raise HTTPException(status_code=404, detail="Excursion not found")

    exc.state = data.state
    if data.corrective_action_taken:
        exc.corrective_action_taken = data.corrective_action_taken
    if data.notes:
        exc.notes = data.notes
    if data.state == "resolved":
        exc.resolved_by = current_user.id
        exc.resolved_at = datetime.now(timezone.utc)
        if not exc.ended_at:
            exc.ended_at = datetime.now(timezone.utc)
            if exc.started_at:
                exc.duration_minutes = int((exc.ended_at - exc.started_at).total_seconds() / 60)

    await db.commit()
    await db.refresh(exc)
    return _excursion_to_dict(exc)


# ── Compliance Reports ───────────────────────────

@router.post("/reports/generate", status_code=status.HTTP_201_CREATED)
async def generate_report(
    data: ReportGenerate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a compliance report for a facility over a date range."""
    fac = await _verify_facility(data.facility_id, current_user, db)

    # Default period
    now = datetime.now(timezone.utc)
    if data.period_end:
        period_end = data.period_end
    else:
        period_end = now

    if data.period_start:
        period_start = data.period_start
    else:
        days_map = {"daily": 1, "weekly": 7, "monthly": 30}
        period_start = period_end - timedelta(days=days_map.get(data.report_type, 7))

    title = data.title or f"{data.report_type.title()} Compliance Report — {fac.name}"

    # Query compliance logs in period
    logs_q = select(ComplianceLog).where(
        ComplianceLog.facility_id == data.facility_id,
        ComplianceLog.checked_at >= period_start,
        ComplianceLog.checked_at <= period_end,
    )
    logs_result = await db.execute(logs_q)
    logs = logs_result.scalars().all()

    total = len(logs)
    passed = sum(1 for l in logs if l.status == "pass")
    warning = sum(1 for l in logs if l.status == "warning")
    critical = sum(1 for l in logs if l.status == "critical")
    failed = warning + critical
    compliance_pct = (passed / total * 100) if total > 0 else 100.0

    # Query excursions in period
    exc_q = select(TempExcursion).where(
        TempExcursion.facility_id == data.facility_id,
        TempExcursion.started_at >= period_start,
        TempExcursion.started_at <= period_end,
    )
    exc_result = await db.execute(exc_q)
    excursions = exc_result.scalars().all()

    # Build detailed report data
    report_data = {
        "facility_name": fac.name,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "checks": {
            "total": total,
            "passed": passed,
            "warning": warning,
            "critical": critical,
        },
        "compliance_pct": round(compliance_pct, 2),
        "excursions": [
            {
                "id": str(e.id),
                "severity": e.severity,
                "peak_temp": e.peak_temp,
                "duration_minutes": e.duration_minutes,
                "state": e.state,
                "started_at": e.started_at.isoformat() if e.started_at else None,
            }
            for e in excursions
        ],
        "generated_at": now.isoformat(),
    }

    report = ComplianceReport(
        facility_id=data.facility_id,
        org_id=current_user.org_id,
        report_type=data.report_type,
        title=title,
        period_start=period_start,
        period_end=period_end,
        total_checks=total,
        passed_checks=passed,
        failed_checks=failed,
        excursion_count=len(excursions),
        compliance_pct=round(compliance_pct, 2),
        report_data=report_data,
        generated_by=current_user.id,
        state="draft",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await log_activity(db, user=current_user, org_id=current_user.org_id, action="create",
                       resource_type="compliance_report", resource_id=str(report.id),
                       resource_name=title, facility_id=data.facility_id,
                       summary=f"Generated {data.report_type} compliance report: {compliance_pct:.1f}% compliance")
    return _report_to_dict(report)


@router.get("/reports")
async def list_reports(
    facility_id: UUID | None = Query(None),
    report_type: str | None = Query(None),
    state: str | None = Query(None),
    limit: int = Query(50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceReport).where(
        ComplianceReport.org_id == current_user.org_id,
    )
    if facility_id:
        q = q.where(ComplianceReport.facility_id == facility_id)
    if report_type:
        q = q.where(ComplianceReport.report_type == report_type)
    if state:
        q = q.where(ComplianceReport.state == state)
    q = q.order_by(ComplianceReport.created_at.desc()).limit(limit)
    result = await db.execute(q)
    reports = result.scalars().all()
    return {"reports": [_report_to_dict(r) for r in reports], "total": len(reports)}


@router.get("/reports/{report_id}")
async def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ComplianceReport).where(
            ComplianceReport.id == report_id,
            ComplianceReport.org_id == current_user.org_id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_to_dict(report)


@router.patch("/reports/{report_id}/sign-off")
async def sign_off_report(
    report_id: UUID,
    data: ReportSignOff,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ComplianceReport).where(
            ComplianceReport.id == report_id,
            ComplianceReport.org_id == current_user.org_id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.state = "signed_off"
    report.signed_off_by = current_user.id
    report.signed_off_at = datetime.now(timezone.utc)
    if data.sign_off_notes:
        report.sign_off_notes = data.sign_off_notes

    await db.commit()
    await db.refresh(report)

    await log_activity(db, user=current_user, org_id=current_user.org_id, action="update",
                       resource_type="compliance_report", resource_id=str(report.id),
                       resource_name=report.title, facility_id=report.facility_id,
                       summary=f"Signed off compliance report: {report.title}")
    return _report_to_dict(report)


# ── Dashboard Stats ──────────────────────────────

@router.get("/dashboard")
async def compliance_dashboard(
    facility_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary statistics for the compliance dashboard."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    # Active CCPs
    ccp_q = select(func.count(CriticalControlPoint.id)).where(
        CriticalControlPoint.org_id == current_user.org_id,
        CriticalControlPoint.is_active == True,
    )
    if facility_id:
        ccp_q = ccp_q.where(CriticalControlPoint.facility_id == facility_id)
    ccp_count = (await db.execute(ccp_q)).scalar() or 0

    # Checks last 24h
    checks_q = (
        select(func.count(ComplianceLog.id))
        .join(CriticalControlPoint, ComplianceLog.ccp_id == CriticalControlPoint.id)
        .where(
            CriticalControlPoint.org_id == current_user.org_id,
            ComplianceLog.checked_at >= day_ago,
        )
    )
    if facility_id:
        checks_q = checks_q.where(ComplianceLog.facility_id == facility_id)
    checks_24h = (await db.execute(checks_q)).scalar() or 0

    # Pass rate last 24h
    passed_q = (
        select(func.count(ComplianceLog.id))
        .join(CriticalControlPoint, ComplianceLog.ccp_id == CriticalControlPoint.id)
        .where(
            CriticalControlPoint.org_id == current_user.org_id,
            ComplianceLog.checked_at >= day_ago,
            ComplianceLog.status == "pass",
        )
    )
    if facility_id:
        passed_q = passed_q.where(ComplianceLog.facility_id == facility_id)
    passed_24h = (await db.execute(passed_q)).scalar() or 0
    pass_rate = (passed_24h / checks_24h * 100) if checks_24h > 0 else 100.0

    # Active excursions
    active_exc_q = select(func.count(TempExcursion.id)).where(
        TempExcursion.org_id == current_user.org_id,
        TempExcursion.state == "active",
    )
    if facility_id:
        active_exc_q = active_exc_q.where(TempExcursion.facility_id == facility_id)
    active_excursions = (await db.execute(active_exc_q)).scalar() or 0

    # Excursions this week
    week_exc_q = select(func.count(TempExcursion.id)).where(
        TempExcursion.org_id == current_user.org_id,
        TempExcursion.started_at >= week_ago,
    )
    if facility_id:
        week_exc_q = week_exc_q.where(TempExcursion.facility_id == facility_id)
    week_excursions = (await db.execute(week_exc_q)).scalar() or 0

    # Pending reports
    pending_q = select(func.count(ComplianceReport.id)).where(
        ComplianceReport.org_id == current_user.org_id,
        ComplianceReport.state.in_(["draft", "pending_review"]),
    )
    if facility_id:
        pending_q = pending_q.where(ComplianceReport.facility_id == facility_id)
    pending_reports = (await db.execute(pending_q)).scalar() or 0

    return {
        "active_ccps": ccp_count,
        "checks_24h": checks_24h,
        "pass_rate_24h": round(pass_rate, 1),
        "active_excursions": active_excursions,
        "excursions_this_week": week_excursions,
        "pending_reports": pending_reports,
    }

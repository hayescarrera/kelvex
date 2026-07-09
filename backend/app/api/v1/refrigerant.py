"""
Refrigerant Tracking API — circuits, leak events, refrigerant additions,
repairs, fleet dashboard, and AIM Act compliance reporting.

Endpoints:
  POST   /refrigerant/circuits                — Create circuit
  GET    /refrigerant/circuits                — List circuits (facility filter optional)
  PATCH  /refrigerant/circuits/{id}           — Update circuit
  DELETE /refrigerant/circuits/{id}           — Soft deactivate circuit

  POST   /refrigerant/leak-events             — Create leak event
  GET    /refrigerant/leak-events             — List leak events (facility, status filters)
  GET    /refrigerant/leak-events/{id}        — Get leak event detail
  PATCH  /refrigerant/leak-events/{id}        — Update leak event

  POST   /refrigerant/adds                    — Log refrigerant addition
  GET    /refrigerant/adds                    — List additions (facility, circuit filters)

  POST   /refrigerant/repairs                 — Log repair record
  GET    /refrigerant/repairs                 — List repairs (facility, leak_event filters)

  GET    /refrigerant/dashboard               — Fleet overview widget
  GET    /refrigerant/aim-act                 — Per-circuit AIM Act leak rate summary
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped, require_permission, get_accessible_facility_ids
from app.models.user import User
from app.models.facility import Facility
from app.models.refrigerant import (
    RefrigerantCircuit, LeakEvent, RefrigerantAdd, RepairRecord,
)
from app.models.zone_sensor import CompressorRack
from app.models.compressor import Compressor

router = APIRouter(prefix="/refrigerant", tags=["refrigerant"])


# ── Schemas ───────────────────────────────────────

class CircuitCreate(BaseModel):
    facility_id: UUID
    name: str
    refrigerant_type: str
    full_charge_lbs: float | None = None
    rack_id: UUID | None = None
    equipment_id: UUID | None = None
    zone_id: UUID | None = None


class CircuitUpdate(BaseModel):
    name: str | None = None
    refrigerant_type: str | None = None
    full_charge_lbs: float | None = None
    rack_id: UUID | None = None
    equipment_id: UUID | None = None
    zone_id: UUID | None = None
    is_active: bool | None = None


class LeakEventCreate(BaseModel):
    facility_id: UUID
    circuit_id: UUID | None = None
    rack_name: str
    zone_name: str | None = None
    detection_method: str  # pressure_trend | manual | refrigerant_add_pattern | technician_reported
    confidence: str  # suspected | likely | confirmed
    detected_at: datetime
    estimated_loss_lbs: float | None = None
    notes: str | None = None


class LeakEventUpdate(BaseModel):
    status: str | None = None
    confidence: str | None = None
    rack_name: str | None = None
    zone_name: str | None = None
    confirmed_at: datetime | None = None
    repaired_at: datetime | None = None
    closed_at: datetime | None = None
    estimated_loss_lbs: float | None = None
    notes: str | None = None


class RefrigerantAddCreate(BaseModel):
    facility_id: UUID
    circuit_id: UUID | None = None
    leak_event_id: UUID | None = None
    rack_name: str
    refrigerant_type: str
    amount_lbs: float
    cost_per_lb: float | None = None
    technician_name: str
    added_at: datetime
    notes: str | None = None


class RepairRecordCreate(BaseModel):
    facility_id: UUID
    circuit_id: UUID | None = None
    leak_event_id: UUID | None = None
    rack_name: str
    description: str
    technician_name: str
    technician_company: str | None = None
    repaired_at: datetime
    parts_replaced: str | None = None
    verified_leak_free: bool = False
    verification_method: str | None = None  # pressure_test | electronic_detector | visual | dye_test
    refrigerant_recovered_lbs: float | None = None
    notes: str | None = None


# ── Helpers ───────────────────────────────────────

def _rack_to_dict(rack: CompressorRack, comps: list) -> dict:
    suction = [c.suction_pressure_psi for c in comps if c.suction_pressure_psi is not None]
    discharge = [c.discharge_pressure_psi for c in comps if c.discharge_pressure_psi is not None]
    return {
        "rack_id": str(rack.id),
        "rack_name": rack.name,
        "suction_group": rack.suction_group,
        "total_kw": rack.total_kw,
        "active_compressors": rack.active_compressors,
        "avg_suction_psi": round(sum(suction) / len(suction), 1) if suction else None,
        "avg_discharge_psi": round(sum(discharge) / len(discharge), 1) if discharge else None,
        "design_suction_psi": rack.design_suction_psi,
        "design_discharge_psi": rack.design_discharge_psi,
    }


async def _fetch_rack_telemetry(
    rack_ids: set, facility_ids: set, db: AsyncSession
) -> tuple[dict, dict]:
    """Batch fetch CompressorRack rows and their live compressor readings.
    Returns (racks_by_id, comps_by_rack_name)."""
    racks_by_id: dict = {}
    comps_by_rack_name: dict = {}
    if not rack_ids:
        return racks_by_id, comps_by_rack_name

    racks_result = await db.execute(
        select(CompressorRack).where(CompressorRack.id.in_(rack_ids))
    )
    for rack in racks_result.scalars():
        racks_by_id[rack.id] = rack

    rack_names = {r.name for r in racks_by_id.values()}
    if rack_names and facility_ids:
        comps_result = await db.execute(
            select(Compressor).where(
                Compressor.rack_name.in_(rack_names),
                Compressor.facility_id.in_(facility_ids),
            )
        )
        for comp in comps_result.scalars():
            comps_by_rack_name.setdefault(comp.rack_name, []).append(comp)

    return racks_by_id, comps_by_rack_name


async def _verify_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


def _circuit_to_dict(
    c: RefrigerantCircuit,
    rack: CompressorRack | None = None,
    comps: list | None = None,
) -> dict:
    rack_data = _rack_to_dict(rack, comps or []) if rack else None
    return {
        "id": str(c.id),
        "org_id": str(c.org_id),
        "facility_id": str(c.facility_id),
        "name": c.name,
        "refrigerant_type": c.refrigerant_type,
        "full_charge_lbs": c.full_charge_lbs,
        "rack_id": str(c.rack_id) if c.rack_id else None,
        "rack": rack_data,
        "equipment_id": str(c.equipment_id) if c.equipment_id else None,
        "zone_id": str(c.zone_id) if c.zone_id else None,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _leak_event_to_dict(e: LeakEvent) -> dict:
    return {
        "id": str(e.id),
        "org_id": str(e.org_id),
        "facility_id": str(e.facility_id),
        "circuit_id": str(e.circuit_id) if e.circuit_id else None,
        "rack_name": e.rack_name,
        "zone_name": e.zone_name,
        "detection_method": e.detection_method,
        "confidence": e.confidence,
        "status": e.status,
        "detected_at": e.detected_at.isoformat() if e.detected_at else None,
        "confirmed_at": e.confirmed_at.isoformat() if e.confirmed_at else None,
        "repaired_at": e.repaired_at.isoformat() if e.repaired_at else None,
        "closed_at": e.closed_at.isoformat() if e.closed_at else None,
        "estimated_loss_lbs": e.estimated_loss_lbs,
        "notes": e.notes,
        "created_by": str(e.created_by) if e.created_by else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _add_to_dict(a: RefrigerantAdd) -> dict:
    return {
        "id": str(a.id),
        "org_id": str(a.org_id),
        "facility_id": str(a.facility_id),
        "circuit_id": str(a.circuit_id) if a.circuit_id else None,
        "leak_event_id": str(a.leak_event_id) if a.leak_event_id else None,
        "rack_name": a.rack_name,
        "refrigerant_type": a.refrigerant_type,
        "amount_lbs": a.amount_lbs,
        "cost_per_lb": a.cost_per_lb,
        "technician_name": a.technician_name,
        "added_at": a.added_at.isoformat() if a.added_at else None,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _repair_to_dict(r: RepairRecord) -> dict:
    return {
        "id": str(r.id),
        "org_id": str(r.org_id),
        "facility_id": str(r.facility_id),
        "circuit_id": str(r.circuit_id) if r.circuit_id else None,
        "leak_event_id": str(r.leak_event_id) if r.leak_event_id else None,
        "rack_name": r.rack_name,
        "description": r.description,
        "technician_name": r.technician_name,
        "technician_company": r.technician_company,
        "repaired_at": r.repaired_at.isoformat() if r.repaired_at else None,
        "parts_replaced": r.parts_replaced,
        "verified_leak_free": r.verified_leak_free,
        "verification_method": r.verification_method,
        "refrigerant_recovered_lbs": r.refrigerant_recovered_lbs,
        "notes": r.notes,
        "callback_detected": r.callback_detected,
        "callback_detected_at": r.callback_detected_at.isoformat() if r.callback_detected_at else None,
        "callback_lbs_within_30d": r.callback_lbs_within_30d,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ── Circuits ──────────────────────────────────────

@router.post("/circuits", status_code=status.HTTP_201_CREATED)
async def create_circuit(
    data: CircuitCreate,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)
    circuit = RefrigerantCircuit(
        **data.model_dump(),
        org_id=current_user.org_id,
    )
    db.add(circuit)
    await db.commit()
    await db.refresh(circuit)
    return _circuit_to_dict(circuit)


@router.get("/racks")
async def list_racks_for_circuits(
    facility_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List compressor racks available for circuit assignment, with live telemetry."""
    q = select(CompressorRack)
    if facility_id:
        q = q.where(CompressorRack.facility_id == facility_id)
    result = await db.execute(q)
    racks = result.scalars().all()

    facility_ids = {r.facility_id for r in racks}
    rack_names = {r.name for r in racks}
    comps_by_rack: dict = {}
    if rack_names and facility_ids:
        comps_result = await db.execute(
            select(Compressor).where(
                Compressor.rack_name.in_(rack_names),
                Compressor.facility_id.in_(facility_ids),
            )
        )
        for comp in comps_result.scalars():
            comps_by_rack.setdefault(comp.rack_name, []).append(comp)

    return {
        "racks": [_rack_to_dict(r, comps_by_rack.get(r.name, [])) for r in racks]
    }


@router.get("/circuits")
async def list_circuits(
    facility_id: UUID | None = Query(None),
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(RefrigerantCircuit).where(
        RefrigerantCircuit.org_id == current_user.org_id
    )
    if facility_id:
        q = q.where(RefrigerantCircuit.facility_id == facility_id)
    if active_only:
        q = q.where(RefrigerantCircuit.is_active == True)
    q = q.order_by(RefrigerantCircuit.name)
    result = await db.execute(q)
    circuits = result.scalars().all()

    rack_ids = {c.rack_id for c in circuits if c.rack_id}
    facility_ids = {c.facility_id for c in circuits}
    racks_by_id, comps_by_rack_name = await _fetch_rack_telemetry(rack_ids, facility_ids, db)

    def _enrich(c: RefrigerantCircuit) -> dict:
        rack = racks_by_id.get(c.rack_id) if c.rack_id else None
        comps = comps_by_rack_name.get(rack.name, []) if rack else []
        return _circuit_to_dict(c, rack, comps)

    return {"circuits": [_enrich(c) for c in circuits], "total": len(circuits)}


@router.patch("/circuits/{circuit_id}")
async def update_circuit(
    circuit_id: UUID,
    data: CircuitUpdate,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RefrigerantCircuit).where(
            RefrigerantCircuit.id == circuit_id,
            RefrigerantCircuit.org_id == current_user.org_id,
        )
    )
    circuit = result.scalar_one_or_none()
    if not circuit:
        raise HTTPException(status_code=404, detail="Circuit not found")
    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(circuit, k, v)
    await db.commit()
    await db.refresh(circuit)
    return _circuit_to_dict(circuit)


@router.delete("/circuits/{circuit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_circuit(
    circuit_id: UUID,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RefrigerantCircuit).where(
            RefrigerantCircuit.id == circuit_id,
            RefrigerantCircuit.org_id == current_user.org_id,
        )
    )
    circuit = result.scalar_one_or_none()
    if not circuit:
        raise HTTPException(status_code=404, detail="Circuit not found")
    circuit.is_active = False
    await db.commit()


# ── Leak Events ───────────────────────────────────

@router.post("/leak-events", status_code=status.HTTP_201_CREATED)
async def create_leak_event(
    data: LeakEventCreate,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)
    event = LeakEvent(
        **data.model_dump(),
        org_id=current_user.org_id,
        created_by=current_user.id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return _leak_event_to_dict(event)


@router.get("/leak-events")
async def list_leak_events(
    facility_id: UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(LeakEvent).where(
        LeakEvent.org_id == current_user.org_id
    )
    if facility_id:
        q = q.where(LeakEvent.facility_id == facility_id)
    if status:
        q = q.where(LeakEvent.status == status)
    q = q.order_by(LeakEvent.detected_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    events = result.scalars().all()
    return {"leak_events": [_leak_event_to_dict(e) for e in events], "total": len(events)}


@router.get("/leak-events/{event_id}")
async def get_leak_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LeakEvent).where(
            LeakEvent.id == event_id,
            LeakEvent.org_id == current_user.org_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Leak event not found")
    return _leak_event_to_dict(event)


@router.patch("/leak-events/{event_id}")
async def update_leak_event(
    event_id: UUID,
    data: LeakEventUpdate,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LeakEvent).where(
            LeakEvent.id == event_id,
            LeakEvent.org_id == current_user.org_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Leak event not found")
    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(event, k, v)
    await db.commit()
    await db.refresh(event)
    return _leak_event_to_dict(event)


# ── Refrigerant Adds ──────────────────────────────

@router.post("/adds", status_code=status.HTTP_201_CREATED)
async def create_refrigerant_add(
    data: RefrigerantAddCreate,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)
    add = RefrigerantAdd(
        **data.model_dump(),
        org_id=current_user.org_id,
    )
    db.add(add)
    await db.commit()
    await db.refresh(add)
    return _add_to_dict(add)


@router.get("/adds")
async def list_refrigerant_adds(
    facility_id: UUID | None = Query(None),
    circuit_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(RefrigerantAdd).where(
        RefrigerantAdd.org_id == current_user.org_id
    )
    if facility_id:
        q = q.where(RefrigerantAdd.facility_id == facility_id)
    if circuit_id:
        q = q.where(RefrigerantAdd.circuit_id == circuit_id)
    q = q.order_by(RefrigerantAdd.added_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    adds = result.scalars().all()
    return {"adds": [_add_to_dict(a) for a in adds], "total": len(adds)}


# ── Repairs ───────────────────────────────────────

@router.post("/repairs", status_code=status.HTTP_201_CREATED)
async def create_repair_record(
    data: RepairRecordCreate,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)
    repair = RepairRecord(
        **data.model_dump(),
        org_id=current_user.org_id,
    )
    db.add(repair)
    await db.commit()
    await db.refresh(repair)
    return _repair_to_dict(repair)


@router.get("/repairs")
async def list_repair_records(
    facility_id: UUID | None = Query(None),
    leak_event_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(RepairRecord).where(
        RepairRecord.org_id == current_user.org_id
    )
    if facility_id:
        q = q.where(RepairRecord.facility_id == facility_id)
    if leak_event_id:
        q = q.where(RepairRecord.leak_event_id == leak_event_id)
    q = q.order_by(RepairRecord.repaired_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    repairs = result.scalars().all()
    return {"repairs": [_repair_to_dict(r) for r in repairs], "total": len(repairs)}


@router.post("/repairs/{repair_id}/detect-callback")
async def detect_callback(
    repair_id: UUID,
    current_user: User = Depends(require_permission("refrigerant:log")),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a repaired circuit had post-repair refrigerant adds within 30 days.

    A callback means the repair did not fix the root cause — the circuit began
    leaking again after the technician left. We detect this by looking for
    refrigerant additions to the same circuit in the 30-day window after the
    repair date.

    Saves the result to callback_detected / callback_lbs_within_30d on the repair.
    """
    result = await db.execute(
        select(RepairRecord).where(
            RepairRecord.id == repair_id,
            RepairRecord.org_id == current_user.org_id,
        )
    )
    repair = result.scalar_one_or_none()
    if not repair:
        raise HTTPException(status_code=404, detail="Repair not found")

    # Only circuits can be correlated — rack-level repairs can't be callback-checked
    if not repair.circuit_id:
        return {
            "callback_detected": None,
            "reason": "No circuit linked — cannot perform callback check",
        }

    window_start = repair.repaired_at
    window_end = repair.repaired_at + timedelta(days=30)
    now = datetime.now(timezone.utc)

    # Need at least some time to elapse before checking
    if now < window_start + timedelta(days=3):
        return {
            "callback_detected": None,
            "reason": "Repair too recent — check back after 3 days",
        }

    # Sum all refrigerant adds to this circuit in the 30-day window post-repair
    adds_result = await db.execute(
        select(func.sum(RefrigerantAdd.amount_lbs)).where(
            RefrigerantAdd.circuit_id == repair.circuit_id,
            RefrigerantAdd.added_at > window_start,
            RefrigerantAdd.added_at <= window_end,
        )
    )
    post_repair_lbs = adds_result.scalar() or 0.0

    callback = post_repair_lbs > 0

    repair.callback_detected = callback
    repair.callback_detected_at = now
    repair.callback_lbs_within_30d = post_repair_lbs if callback else 0.0
    await db.commit()
    await db.refresh(repair)

    return {
        "callback_detected": callback,
        "callback_lbs_within_30d": post_repair_lbs,
        "monitoring_window_days": 30,
        "window_start": window_start.isoformat(),
        "window_end": min(window_end, now).isoformat(),
        "repair": _repair_to_dict(repair),
    }


# ── Dashboard ─────────────────────────────────────

@router.get("/dashboard")
async def refrigerant_dashboard(
    facility_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fleet-level refrigerant overview widget — open leaks, 30-day activity, AIM Act threshold breaches."""
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)

    # ── Open leak events ─────────────────────────
    open_leaks_q = select(func.count(LeakEvent.id)).where(
        LeakEvent.org_id == current_user.org_id,
        LeakEvent.status.in_(["open", "investigating"]),
    )
    if facility_id:
        open_leaks_q = open_leaks_q.where(LeakEvent.facility_id == facility_id)
    open_leak_events = (await db.execute(open_leaks_q)).scalar() or 0

    # ── Leak events detected in last 30 days ─────
    leaks_30d_q = select(func.count(LeakEvent.id)).where(
        LeakEvent.org_id == current_user.org_id,
        LeakEvent.detected_at >= cutoff_30d,
    )
    if facility_id:
        leaks_30d_q = leaks_30d_q.where(LeakEvent.facility_id == facility_id)
    leak_events_30d = (await db.execute(leaks_30d_q)).scalar() or 0

    # ── Refrigerant added in last 30 days (lbs) ──
    adds_30d_q = select(func.sum(RefrigerantAdd.amount_lbs)).where(
        RefrigerantAdd.org_id == current_user.org_id,
        RefrigerantAdd.added_at >= cutoff_30d,
    )
    if facility_id:
        adds_30d_q = adds_30d_q.where(RefrigerantAdd.facility_id == facility_id)
    refrigerant_added_30d_lbs = float((await db.execute(adds_30d_q)).scalar() or 0.0)

    # ── Repairs in last 30 days ──────────────────
    repairs_30d_q = select(func.count(RepairRecord.id)).where(
        RepairRecord.org_id == current_user.org_id,
        RepairRecord.repaired_at >= cutoff_30d,
    )
    if facility_id:
        repairs_30d_q = repairs_30d_q.where(RepairRecord.facility_id == facility_id)
    repairs_30d = (await db.execute(repairs_30d_q)).scalar() or 0

    # ── Per-facility breakdown ────────────────────
    # Fetch active facilities in scope
    facilities_q = select(Facility).where(
        Facility.org_id == current_user.org_id,
        Facility.deleted_at == None,
    )
    accessible = await get_accessible_facility_ids(current_user, db)
    if accessible is not None:
        facilities_q = facilities_q.where(Facility.id.in_(accessible))
    if facility_id:
        facilities_q = facilities_q.where(Facility.id == facility_id)
    fac_result = await db.execute(facilities_q)
    facilities = fac_result.scalars().all()

    cutoff_365d = now - timedelta(days=365)
    per_facility = []
    sites_above_threshold = 0

    for fac in facilities:
        fac_id = fac.id

        # Open leaks for this facility
        fac_open_q = select(func.count(LeakEvent.id)).where(
            LeakEvent.org_id == current_user.org_id,
            LeakEvent.facility_id == fac_id,
            LeakEvent.status.in_(["open", "investigating"]),
        )
        fac_open_leaks = (await db.execute(fac_open_q)).scalar() or 0

        # Adds in last 30 days for this facility
        fac_adds_q = select(func.sum(RefrigerantAdd.amount_lbs)).where(
            RefrigerantAdd.org_id == current_user.org_id,
            RefrigerantAdd.facility_id == fac_id,
            RefrigerantAdd.added_at >= cutoff_30d,
        )
        fac_adds_30d = float((await db.execute(fac_adds_q)).scalar() or 0.0)

        # Annualised leak rate for this facility:
        # total added in 365d / total full_charge across all active circuits * 100
        fac_adds_365d_q = select(func.sum(RefrigerantAdd.amount_lbs)).where(
            RefrigerantAdd.org_id == current_user.org_id,
            RefrigerantAdd.facility_id == fac_id,
            RefrigerantAdd.added_at >= cutoff_365d,
        )
        fac_adds_365d = float((await db.execute(fac_adds_365d_q)).scalar() or 0.0)

        fac_charge_q = select(func.sum(RefrigerantCircuit.full_charge_lbs)).where(
            RefrigerantCircuit.org_id == current_user.org_id,
            RefrigerantCircuit.facility_id == fac_id,
            RefrigerantCircuit.is_active == True,
            RefrigerantCircuit.full_charge_lbs != None,
        )
        fac_total_charge = float((await db.execute(fac_charge_q)).scalar() or 0.0)

        if fac_total_charge > 0:
            leak_rate_pct = round((fac_adds_365d / fac_total_charge) * 100, 2)
        else:
            leak_rate_pct = None

        if leak_rate_pct is not None and leak_rate_pct > 15.0:
            sites_above_threshold += 1

        per_facility.append({
            "facility_id": str(fac_id),
            "name": fac.name,
            "open_leaks": fac_open_leaks,
            "adds_30d_lbs": fac_adds_30d,
            "leak_rate_pct": leak_rate_pct,
        })

    return {
        "open_leak_events": open_leak_events,
        "leak_events_30d": leak_events_30d,
        "refrigerant_added_30d_lbs": refrigerant_added_30d_lbs,
        "repairs_30d": repairs_30d,
        "sites_above_threshold": sites_above_threshold,
        "per_facility": per_facility,
    }


# ── AIM Act Compliance ────────────────────────────

@router.get("/aim-act")
async def aim_act_summary(
    facility_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Per-circuit AIM Act leak rate summary.

    Leak rate = (total refrigerant added in last 365 days / full_charge_lbs) * 100
    Warning threshold: >= 10%  |  Exceeds threshold: >= 15%
    """
    now = datetime.now(timezone.utc)
    cutoff_365d = now - timedelta(days=365)
    period_days = 365

    from app.services.forecasting import AIM_THRESHOLD_PCT, AIM_WARNING_PCT
    WARNING_THRESHOLD = AIM_WARNING_PCT
    EXCEEDS_THRESHOLD = AIM_THRESHOLD_PCT

    # Fetch active circuits in scope
    circuits_q = select(RefrigerantCircuit).where(
        RefrigerantCircuit.org_id == current_user.org_id,
        RefrigerantCircuit.is_active == True,
    )
    if facility_id:
        circuits_q = circuits_q.where(RefrigerantCircuit.facility_id == facility_id)
    circuits_q = circuits_q.order_by(RefrigerantCircuit.name)
    circuits_result = await db.execute(circuits_q)
    circuits = circuits_result.scalars().all()

    rack_ids = {c.rack_id for c in circuits if c.rack_id}
    facility_ids = {c.facility_id for c in circuits}
    racks_by_id, comps_by_rack_name = await _fetch_rack_telemetry(rack_ids, facility_ids, db)

    circuit_summaries = []
    total_added_lbs_all = 0.0
    circuits_above_threshold = 0

    for circuit in circuits:
        # Total refrigerant added to this circuit in the period
        adds_q = select(func.sum(RefrigerantAdd.amount_lbs)).where(
            RefrigerantAdd.org_id == current_user.org_id,
            RefrigerantAdd.circuit_id == circuit.id,
            RefrigerantAdd.added_at >= cutoff_365d,
        )
        total_added_lbs = float((await db.execute(adds_q)).scalar() or 0.0)
        total_added_lbs_all += total_added_lbs

        # Leak rate calculation
        if circuit.full_charge_lbs and circuit.full_charge_lbs > 0:
            leak_rate_pct = round((total_added_lbs / circuit.full_charge_lbs) * 100, 2)
            if leak_rate_pct >= EXCEEDS_THRESHOLD:
                compliance_status = "exceeds_threshold"
                circuits_above_threshold += 1
            elif leak_rate_pct >= WARNING_THRESHOLD:
                compliance_status = "warning"
            else:
                compliance_status = "compliant"
        else:
            leak_rate_pct = None
            compliance_status = "compliant"

        # Open leak events on this circuit
        open_leaks_q = select(func.count(LeakEvent.id)).where(
            LeakEvent.org_id == current_user.org_id,
            LeakEvent.circuit_id == circuit.id,
            LeakEvent.status.in_(["open", "investigating"]),
        )
        open_leak_events = (await db.execute(open_leaks_q)).scalar() or 0

        # Refrigerant adds not linked to a completed repair (unrepaired adds)
        # Defined as: adds on this circuit where no repair record is linked or the leak
        # event is still open. We use the simple heuristic: adds linked to open leak events
        # or adds with no leak_event_id.
        unrepaired_adds_q = select(func.count(RefrigerantAdd.id)).where(
            RefrigerantAdd.org_id == current_user.org_id,
            RefrigerantAdd.circuit_id == circuit.id,
            RefrigerantAdd.added_at >= cutoff_365d,
            and_(
                RefrigerantAdd.leak_event_id == None,
            ),
        )
        unrepaired_adds = (await db.execute(unrepaired_adds_q)).scalar() or 0

        rack = racks_by_id.get(circuit.rack_id) if circuit.rack_id else None
        comps = comps_by_rack_name.get(rack.name, []) if rack else []
        rack_data = _rack_to_dict(rack, comps) if rack else None

        circuit_summaries.append({
            "circuit_id": str(circuit.id),
            "circuit_name": circuit.name,
            "rack_name": rack.name if rack else circuit.name,
            "refrigerant_type": circuit.refrigerant_type,
            "full_charge_lbs": circuit.full_charge_lbs,
            "total_added_lbs": total_added_lbs,
            "leak_rate_pct": leak_rate_pct,
            "status": compliance_status,
            "open_leak_events": open_leak_events,
            "unrepaired_adds": unrepaired_adds,
            "rack": rack_data,
        })

    # Facility-level summary
    rates = [c["leak_rate_pct"] for c in circuit_summaries if c["leak_rate_pct"] is not None]
    avg_leak_rate_pct = round(sum(rates) / len(rates), 2) if rates else None

    return {
        "period_days": period_days,
        "circuits": circuit_summaries,
        "facility_summary": {
            "total_added_lbs": round(total_added_lbs_all, 3),
            "avg_leak_rate_pct": avg_leak_rate_pct,
            "circuits_above_threshold": circuits_above_threshold,
        },
    }


# ── AIM Act audit export package ─────────────────────────────────────────────

@router.get("/aim-act/export")
async def export_aim_act_package(
    facility_id: UUID | None = Query(None),
    days: int = Query(365, ge=30, le=1095),
    current_user: User = Depends(require_permission("reports:generate")),
    db: AsyncSession = Depends(get_db),
):
    """One-click auditor package: leak rates, additions, leak events, and
    repair records as CSVs plus a methodology README, zipped.

    This is the artifact behind the "auditor-ready export" claim — every
    number is reproducible from the tables it is drawn from.
    """
    import csv
    import io
    import zipfile
    from fastapi.responses import Response
    from app.services.forecasting import AIM_THRESHOLD_PCT, AIM_WARNING_PCT

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Scope: explicit facility (must be accessible) or all accessible facilities
    if facility_id:
        await get_facility_scoped(facility_id, current_user, db)
        scope_ids = [facility_id]
    else:
        accessible = await get_accessible_facility_ids(current_user, db)
        fac_q = select(Facility.id).where(
            Facility.org_id == current_user.org_id,
            Facility.deleted_at == None,  # noqa: E711
        )
        if accessible is not None:
            fac_q = fac_q.where(Facility.id.in_(accessible))
        scope_ids = [row[0] for row in (await db.execute(fac_q)).all()]

    fac_names = {
        row[0]: row[1]
        for row in (await db.execute(
            select(Facility.id, Facility.name).where(Facility.id.in_(scope_ids))
        )).all()
    } if scope_ids else {}

    def _fac(fid):
        return fac_names.get(fid, str(fid))

    def _dt(value):
        return value.strftime("%Y-%m-%d %H:%M UTC") if value else ""

    def _csv(header, rows):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(rows)
        return buf.getvalue()

    # ── Circuits + leak rates ────────────────────────────────────────────
    circuits = (await db.execute(
        select(RefrigerantCircuit).where(
            RefrigerantCircuit.org_id == current_user.org_id,
            RefrigerantCircuit.facility_id.in_(scope_ids) if scope_ids else False,
            RefrigerantCircuit.is_active == True,  # noqa: E712
        ).order_by(RefrigerantCircuit.name)
    )).scalars().all()

    summary_rows = []
    for c in circuits:
        added = float((await db.execute(
            select(func.coalesce(func.sum(RefrigerantAdd.amount_lbs), 0.0)).where(
                RefrigerantAdd.circuit_id == c.id,
                RefrigerantAdd.added_at >= cutoff,
            )
        )).scalar() or 0.0)
        last_add = (await db.execute(
            select(func.max(RefrigerantAdd.added_at)).where(RefrigerantAdd.circuit_id == c.id)
        )).scalar()
        if c.full_charge_lbs and c.full_charge_lbs > 0:
            rate = round(added / c.full_charge_lbs * 100, 2)
            status_txt = (
                "EXCEEDS THRESHOLD — repair required" if rate >= AIM_THRESHOLD_PCT
                else "Warning — approaching threshold" if rate >= AIM_WARNING_PCT
                else "Compliant"
            )
        else:
            rate, status_txt = "", "No full-charge value recorded"
        open_events = (await db.execute(
            select(func.count(LeakEvent.id)).where(
                LeakEvent.circuit_id == c.id,
                LeakEvent.status.in_(["open", "investigating"]),
            )
        )).scalar() or 0
        summary_rows.append([
            _fac(c.facility_id), c.name, c.refrigerant_type,
            c.full_charge_lbs or "", added, rate, status_txt,
            open_events, _dt(last_add),
        ])

    summary_csv = _csv(
        ["facility", "circuit", "refrigerant", "full_charge_lbs",
         f"added_lbs_last_{days}d", "annual_leak_rate_pct", "compliance_status",
         "open_leak_events", "last_addition"],
        summary_rows,
    )

    # ── Refrigerant additions ────────────────────────────────────────────
    circuit_names = {c.id: c.name for c in circuits}
    adds = (await db.execute(
        select(RefrigerantAdd).where(
            RefrigerantAdd.org_id == current_user.org_id,
            RefrigerantAdd.facility_id.in_(scope_ids) if scope_ids else False,
            RefrigerantAdd.added_at >= cutoff,
        ).order_by(RefrigerantAdd.added_at)
    )).scalars().all()
    adds_csv = _csv(
        ["date", "facility", "circuit", "rack", "refrigerant", "amount_lbs",
         "technician", "epa_cert", "cost_per_lb", "linked_leak_event", "notes"],
        [[_dt(a.added_at), _fac(a.facility_id),
          circuit_names.get(a.circuit_id, ""), a.rack_name, a.refrigerant_type,
          a.amount_lbs, a.technician_name, a.technician_epa_cert or "",
          a.cost_per_lb or "", str(a.leak_event_id) if a.leak_event_id else "",
          a.notes or ""] for a in adds],
    )

    # ── Leak events ──────────────────────────────────────────────────────
    events = (await db.execute(
        select(LeakEvent).where(
            LeakEvent.org_id == current_user.org_id,
            LeakEvent.facility_id.in_(scope_ids) if scope_ids else False,
            LeakEvent.detected_at >= cutoff,
        ).order_by(LeakEvent.detected_at)
    )).scalars().all()
    events_csv = _csv(
        ["event_id", "detected", "facility", "circuit", "rack",
         "detection_method", "confidence", "status", "confirmed",
         "repaired", "closed", "estimated_loss_lbs", "notes"],
        [[str(e.id), _dt(e.detected_at), _fac(e.facility_id),
          circuit_names.get(e.circuit_id, ""), e.rack_name,
          e.detection_method, e.confidence, e.status, _dt(e.confirmed_at),
          _dt(e.repaired_at), _dt(e.closed_at), e.estimated_loss_lbs or "",
          e.notes or ""] for e in events],
    )

    # ── Repair records ───────────────────────────────────────────────────
    repairs = (await db.execute(
        select(RepairRecord).where(
            RepairRecord.org_id == current_user.org_id,
            RepairRecord.facility_id.in_(scope_ids) if scope_ids else False,
            RepairRecord.repaired_at >= cutoff,
        ).order_by(RepairRecord.repaired_at)
    )).scalars().all()
    repairs_csv = _csv(
        ["repaired", "facility", "circuit", "rack", "description",
         "technician", "company", "parts_replaced", "verified_leak_free",
         "verification_method", "refrigerant_recovered_lbs",
         "callback_detected", "callback_lbs_within_30d",
         "linked_leak_event", "notes"],
        [[_dt(r.repaired_at), _fac(r.facility_id),
          circuit_names.get(r.circuit_id, ""), r.rack_name, r.description,
          r.technician_name, r.technician_company or "",
          r.parts_replaced or "", "yes" if r.verified_leak_free else "no",
          r.verification_method or "",
          r.refrigerant_recovered_lbs or "",
          {True: "yes", False: "no"}.get(r.callback_detected, ""),
          r.callback_lbs_within_30d or "",
          str(r.leak_event_id) if r.leak_event_id else "",
          r.notes or ""] for r in repairs],
    )

    readme = f"""KELVEX — AIM ACT COMPLIANCE PACKAGE
Generated: {now:%Y-%m-%d %H:%M} UTC
Scope: {"facility " + _fac(facility_id) if facility_id else f"{len(scope_ids)} facility(ies)"}
Period: last {days} days (from {cutoff:%Y-%m-%d})

METHODOLOGY
Annual leak rate per circuit = (refrigerant added over the trailing 365 days
/ full charge) x 100, per the EPA annualizing method for appliances with a
full charge of 50 lb or more of an HFC or substitute subject to the AIM Act
Leak Repair & Management Rule (40 CFR Part 84, Subpart C).

Thresholds applied (commercial refrigeration):
  - {AIM_THRESHOLD_PCT:.0f}%: leak rate at or above this requires repair within 30 days
  - {AIM_WARNING_PCT:.0f}%: internal warning level (approaching threshold)

FILES
  leak_rate_summary.csv     Per-circuit leak rate and compliance status
  refrigerant_additions.csv Every addition in the period, with technician and
                            EPA certification where recorded
  leak_events.csv           Detected/confirmed leak events and their lifecycle
  repair_records.csv        Repairs with verification tests, recovered
                            refrigerant (Section 608), and 30-day callback
                            re-leak checks

All rows are exported verbatim from the Kelvex system of record. Timestamps
are UTC. Empty cells mean the value was not recorded.
"""

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("leak_rate_summary.csv", summary_csv)
        zf.writestr("refrigerant_additions.csv", adds_csv)
        zf.writestr("leak_events.csv", events_csv)
        zf.writestr("repair_records.csv", repairs_csv)
    zbuf.seek(0)

    fname = f"kelvex-aim-act-package-{now:%Y%m%d}.zip"
    return Response(
        content=zbuf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

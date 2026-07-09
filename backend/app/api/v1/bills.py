"""
Utility Bills API

Endpoints:
  POST   /facilities/{id}/bills          — Create bill (manual entry)
  POST   /facilities/{id}/bills/upload    — Upload bill file (CSV/PDF)
  GET    /facilities/{id}/bills           — List bills for a facility
  GET    /facilities/{id}/bills/{bill_id} — Get single bill
  DELETE /facilities/{id}/bills/{bill_id} — Delete a bill
  POST   /facilities/{id}/bills/{bill_id}/analyze — Run demand analysis on a bill
"""

import csv
import io
import uuid as uuid_mod
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped, require_permission
from app.models.user import User
from app.models.facility import Facility
from app.models.billing import UtilityBill, DemandAnalysis
from app.schemas.billing import (
    BillCreate, BillUpdate, BillResponse, BillListResponse,
    DemandAnalysisResponse, DemandAnalysisListResponse,
)
from app.services.demand_engine import DemandChargeCalculator

router = APIRouter(prefix="/facilities/{facility_id}/bills", tags=["bills"])


# ── Helpers ──────────────────────────────────────
async def _get_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


async def _get_bill(bill_id: UUID, facility_id: UUID, db: AsyncSession) -> UtilityBill:
    result = await db.execute(
        select(UtilityBill).where(
            UtilityBill.id == bill_id,
            UtilityBill.facility_id == facility_id,
        )
    )
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


def _safe_decimal(val) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _safe_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None


def _parse_date(val: str) -> date | None:
    """Try common date formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ── CSV Parser ───────────────────────────────────
def parse_bill_csv(content: str) -> list[dict]:
    """
    Parse a CSV of utility bills. Flexible column matching.

    Expected columns (case-insensitive, partial match):
      period_start / start_date / billing_start
      period_end / end_date / billing_end
      total_kwh / kwh / energy_kwh
      total_cost / total / amount
      peak_demand_kw / demand_kw / peak_kw
      demand_charge / demand_cost
      energy_charge / energy_cost
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    # Build column mapping
    col_map = {}
    targets = {
        "period_start": ["period_start", "start_date", "billing_start", "start"],
        "period_end": ["period_end", "end_date", "billing_end", "end"],
        "total_kwh": ["total_kwh", "kwh", "energy_kwh", "usage_kwh", "consumption"],
        "total_cost": ["total_cost", "total", "amount", "bill_amount", "total_amount"],
        "peak_demand_kw": ["peak_demand_kw", "demand_kw", "peak_kw", "peak_demand", "demand"],
        "demand_charge": ["demand_charge", "demand_cost", "demand_amount"],
        "energy_charge": ["energy_charge", "energy_cost", "energy_amount"],
    }

    lower_fields = {f.lower().strip(): f for f in reader.fieldnames}

    for target, candidates in targets.items():
        for candidate in candidates:
            if candidate in lower_fields:
                col_map[target] = lower_fields[candidate]
                break

    if "period_start" not in col_map or "period_end" not in col_map:
        raise ValueError(
            "CSV must have period_start and period_end columns "
            "(or start_date/end_date, billing_start/billing_end)"
        )

    bills = []
    for row_num, row in enumerate(reader, start=2):
        start = _parse_date(row.get(col_map.get("period_start", ""), ""))
        end = _parse_date(row.get(col_map.get("period_end", ""), ""))

        if not start or not end:
            continue  # Skip rows with bad dates

        bills.append({
            "period_start": start,
            "period_end": end,
            "total_kwh": _safe_float(row.get(col_map.get("total_kwh", ""))),
            "total_cost": _safe_decimal(row.get(col_map.get("total_cost", ""))),
            "peak_demand_kw": _safe_float(row.get(col_map.get("peak_demand_kw", ""))),
            "demand_charge": _safe_decimal(row.get(col_map.get("demand_charge", ""))),
            "energy_charge": _safe_decimal(row.get(col_map.get("energy_charge", ""))),
        })

    return bills


# ── Endpoints ────────────────────────────────────

@router.post("", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create_bill(
    facility_id: UUID,
    data: BillCreate,
    current_user: User = Depends(require_permission("bills:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a utility bill."""
    await _get_facility(facility_id, current_user, db)

    bill = UtilityBill(
        facility_id=facility_id,
        period_start=data.period_start,
        period_end=data.period_end,
        total_kwh=data.total_kwh,
        total_cost=data.total_cost,
        peak_demand_kw=data.peak_demand_kw,
        demand_charge=data.demand_charge,
        energy_charge=data.energy_charge,
    )
    db.add(bill)
    await db.flush()
    await db.refresh(bill)
    return bill


@router.post("/upload", response_model=BillListResponse, status_code=status.HTTP_201_CREATED)
async def upload_bills(
    facility_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("bills:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV of utility bills. Returns all created bills."""
    await _get_facility(facility_id, current_user, db)

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename_lower = file.filename.lower()
    if not filename_lower.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported currently. PDF parsing coming soon."
        )

    # Read and parse
    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            decoded = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode file")

    try:
        parsed_bills = parse_bill_csv(decoded)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not parsed_bills:
        raise HTTPException(status_code=400, detail="No valid bill rows found in CSV")

    # Create bill records
    created = []
    for bill_data in parsed_bills:
        bill = UtilityBill(
            facility_id=facility_id,
            period_start=bill_data["period_start"],
            period_end=bill_data["period_end"],
            total_kwh=bill_data["total_kwh"],
            total_cost=bill_data["total_cost"],
            peak_demand_kw=bill_data["peak_demand_kw"],
            demand_charge=bill_data["demand_charge"],
            energy_charge=bill_data["energy_charge"],
            source_file=file.filename,
            parsed_at=datetime.now(timezone.utc),
            raw_data={
                k: str(v) if isinstance(v, (date, Decimal)) else v
                for k, v in bill_data.items()
            },
        )
        db.add(bill)
        created.append(bill)

    await db.flush()
    for bill in created:
        await db.refresh(bill)

    return BillListResponse(bills=created, total=len(created))


@router.get("", response_model=BillListResponse)
async def list_bills(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all bills for a facility."""
    await _get_facility(facility_id, current_user, db)

    count_result = await db.execute(
        select(func.count(UtilityBill.id)).where(UtilityBill.facility_id == facility_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(UtilityBill)
        .where(UtilityBill.facility_id == facility_id)
        .order_by(UtilityBill.period_start.desc())
    )
    bills = result.scalars().all()

    return BillListResponse(bills=bills, total=total)


@router.get("/{bill_id}", response_model=BillResponse)
async def get_bill(
    facility_id: UUID,
    bill_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single bill."""
    await _get_facility(facility_id, current_user, db)
    return await _get_bill(bill_id, facility_id, db)


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(
    facility_id: UUID,
    bill_id: UUID,
    current_user: User = Depends(require_permission("bills:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a bill."""
    await _get_facility(facility_id, current_user, db)
    bill = await _get_bill(bill_id, facility_id, db)
    await db.delete(bill)
    await db.commit()


@router.post("/{bill_id}/analyze", response_model=DemandAnalysisResponse)
async def analyze_bill(
    facility_id: UUID,
    bill_id: UUID,
    current_user: User = Depends(require_permission("bills:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Run demand charge analysis on a single bill."""
    await _get_facility(facility_id, current_user, db)
    bill = await _get_bill(bill_id, facility_id, db)

    if not bill.peak_demand_kw or not bill.demand_charge:
        raise HTTPException(
            status_code=400,
            detail="Bill must have peak_demand_kw and demand_charge to run analysis"
        )

    calc = DemandChargeCalculator()
    result = calc.analyze_bill(
        period_start=bill.period_start,
        period_end=bill.period_end,
        peak_demand_kw=float(bill.peak_demand_kw),
        demand_charge=Decimal(str(bill.demand_charge)),
        total_kwh=float(bill.total_kwh) if bill.total_kwh else None,
        total_cost=Decimal(str(bill.total_cost)) if bill.total_cost else None,
    )

    analysis = DemandAnalysis(
        facility_id=facility_id,
        period_start=result.period_start,
        period_end=result.period_end,
        peak_demand_kw=result.peak_demand_kw,
        ratchet_demand_kw=result.ratchet_demand_kw,
        demand_charge_actual=result.demand_charge_actual,
        demand_charge_optimized=result.demand_charge_optimized,
        savings_potential=result.savings_potential,
        peak_events=result.peak_events,
        load_profile={
            "recommendations": result.recommendations,
            "savings_pct": result.savings_pct,
        },
    )
    db.add(analysis)
    await db.flush()
    await db.refresh(analysis)
    return analysis


# ── Demand analyses for a facility ───────────────

@router.get("/analyses", response_model=DemandAnalysisListResponse,
            name="list_demand_analyses")
async def list_analyses(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all demand analyses for a facility."""
    await _get_facility(facility_id, current_user, db)

    count_result = await db.execute(
        select(func.count(DemandAnalysis.id)).where(
            DemandAnalysis.facility_id == facility_id
        )
    )
    total = count_result.scalar()

    result = await db.execute(
        select(DemandAnalysis)
        .where(DemandAnalysis.facility_id == facility_id)
        .order_by(DemandAnalysis.period_start.desc())
    )
    analyses = result.scalars().all()

    return DemandAnalysisListResponse(analyses=analyses, total=total)

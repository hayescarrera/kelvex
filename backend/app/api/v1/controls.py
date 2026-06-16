"""
Controls & Automation API.

Endpoints:
  POST   /facilities/{id}/controls/sequences          — Create control sequence
  GET    /facilities/{id}/controls/sequences          — List sequences
  GET    /facilities/{id}/controls/sequences/{sid}    — Get sequence
  PATCH  /facilities/{id}/controls/sequences/{sid}    — Update sequence
  DELETE /facilities/{id}/controls/sequences/{sid}    — Delete sequence
  POST   /facilities/{id}/controls/sequences/{sid}/run — Execute sequence now

  POST   /facilities/{id}/controls/schedules          — Create schedule
  GET    /facilities/{id}/controls/schedules          — List schedules
  DELETE /facilities/{id}/controls/schedules/{sid}    — Delete schedule

  POST   /facilities/{id}/controls/rules              — Create automation rule
  GET    /facilities/{id}/controls/rules              — List rules
  PATCH  /facilities/{id}/controls/rules/{rid}        — Update rule
  DELETE /facilities/{id}/controls/rules/{rid}        — Delete rule

  POST   /facilities/{id}/controls/commands           — Queue a command
  GET    /facilities/{id}/controls/commands           — List commands
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.agent import EdgeAgent
from app.models.control import ControlSequence, Schedule, AutomationRule, CommandQueue
from app.schemas.control import (
    ControlSequenceCreate, ControlSequenceUpdate, ControlSequenceResponse, ControlSequenceListResponse,
    ScheduleCreate, ScheduleResponse, ScheduleListResponse,
    AutomationRuleCreate, AutomationRuleUpdate, AutomationRuleResponse, AutomationRuleListResponse,
    CommandCreate, CommandResponse, CommandListResponse,
)

router = APIRouter(prefix="/facilities/{facility_id}/controls", tags=["controls"])


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


# ── Control Sequences ──────────────────────────────

@router.post("/sequences", response_model=ControlSequenceResponse,
             status_code=status.HTTP_201_CREATED)
async def create_sequence(
    facility_id: UUID,
    data: ControlSequenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new control sequence for a facility."""
    await _get_facility(facility_id, current_user, db)
    seq = ControlSequence(
        facility_id=facility_id,
        created_by=current_user.id,
        **data.model_dump(),
    )
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return seq


@router.get("/sequences", response_model=ControlSequenceListResponse)
async def list_sequences(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all control sequences for a facility."""
    await _get_facility(facility_id, current_user, db)
    total = (await db.execute(
        select(func.count(ControlSequence.id)).where(ControlSequence.facility_id == facility_id)
    )).scalar()
    result = await db.execute(
        select(ControlSequence)
        .where(ControlSequence.facility_id == facility_id)
        .order_by(ControlSequence.priority, ControlSequence.name)
    )
    return ControlSequenceListResponse(sequences=result.scalars().all(), total=total)


@router.get("/sequences/{sequence_id}", response_model=ControlSequenceResponse)
async def get_sequence(
    facility_id: UUID, sequence_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific control sequence."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(ControlSequence).where(
            ControlSequence.id == sequence_id, ControlSequence.facility_id == facility_id
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(status_code=404, detail="Control sequence not found")
    return seq


@router.patch("/sequences/{sequence_id}", response_model=ControlSequenceResponse)
async def update_sequence(
    facility_id: UUID, sequence_id: UUID,
    data: ControlSequenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a control sequence's definition."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(ControlSequence).where(
            ControlSequence.id == sequence_id, ControlSequence.facility_id == facility_id
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(status_code=404, detail="Control sequence not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(seq, field, value)
    await db.flush()
    await db.refresh(seq)
    return seq


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sequence(
    facility_id: UUID, sequence_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a control sequence."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(ControlSequence).where(
            ControlSequence.id == sequence_id, ControlSequence.facility_id == facility_id
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(status_code=404, detail="Control sequence not found")
    await db.delete(seq)
    await db.commit()


@router.post("/sequences/{sequence_id}/run", response_model=ControlSequenceResponse)
async def run_sequence(
    facility_id: UUID, sequence_id: UUID,
    body: dict = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a control sequence — creates CommandQueue entries for each step.

    Pass {"require_approval": true} in the body to hold commands in pending_approval
    state until an operator explicitly approves each one. Use this for high-risk
    sequences or automated triggers that should not fire without human review.
    """
    body = body or {}
    logger = logging.getLogger("coldgrid.controls")
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(ControlSequence).where(
            ControlSequence.id == sequence_id, ControlSequence.facility_id == facility_id
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(status_code=404, detail="Control sequence not found")
    if not seq.enabled:
        raise HTTPException(status_code=400, detail="Sequence is disabled")

    steps = seq.steps or []
    if not steps:
        raise HTTPException(status_code=400, detail="Sequence has no steps to execute")

    # Find available agents for this facility
    agents_result = await db.execute(
        select(EdgeAgent).where(
            EdgeAgent.facility_id == facility_id,
            EdgeAgent.enabled == True,
        )
    )
    agents = agents_result.scalars().all()
    if not agents:
        raise HTTPException(
            status_code=400,
            detail="No enabled edge agents for this facility. Cannot dispatch commands."
        )

    # Prefer connected agents, fall back to any enabled agent
    connected_agents = [a for a in agents if a.connection_state == "connected"]
    target_agent = connected_agents[0] if connected_agents else agents[0]

    now = datetime.now(timezone.utc)
    commands_created = 0
    require_approval = bool(body.get("require_approval", False))
    initial_state = "pending_approval" if require_approval else "pending"

    # Sort steps by order field (if present), then iterate
    sorted_steps = sorted(steps, key=lambda s: s.get("order", 0))

    for step in sorted_steps:
        action = step.get("action")
        if not action:
            continue

        # Skip "wait" steps — those are timing hints, not hardware commands
        if action == "wait":
            continue

        target_equipment_id = None
        target_zone_id = None
        target = step.get("target")

        if target:
            # Steps can target a zone or equipment by UUID
            try:
                target_uuid = UUID(target)
                # Determine if target is a zone or equipment based on action type
                zone_actions = {"set_setpoint", "adjust_setpoint", "set_humidity"}
                if action in zone_actions:
                    target_zone_id = target_uuid
                else:
                    target_equipment_id = target_uuid
            except (ValueError, AttributeError):
                logger.warning(f"Invalid target UUID in step: {target}")

        cmd = CommandQueue(
            facility_id=facility_id,
            agent_id=target_agent.id,
            command_type=action,
            target_equipment_id=target_equipment_id,
            target_zone_id=target_zone_id,
            parameters=step.get("params", {}),
            state=initial_state,
            priority=seq.priority,
            source="automation" if require_approval else "user",
            issued_by=current_user.id,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(cmd)
        commands_created += 1

    # Update the sequence execution state
    seq.last_run_at = now
    seq.run_count = (seq.run_count or 0) + 1
    seq.last_result = "pending"
    await db.flush()

    # Update agent pending command count
    target_agent.pending_commands = (target_agent.pending_commands or 0) + commands_created
    await db.flush()

    await db.refresh(seq)
    logger.info(
        f"Sequence '{seq.name}' triggered: {commands_created} commands queued "
        f"to agent '{target_agent.name}'"
    )
    return seq


# ── Schedules ──────────────────────────────────────

@router.post("/schedules", response_model=ScheduleResponse,
             status_code=status.HTTP_201_CREATED)
async def create_schedule(
    facility_id: UUID,
    data: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new schedule for a facility."""
    await _get_facility(facility_id, current_user, db)
    schedule = Schedule(facility_id=facility_id, **data.model_dump())
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    return schedule


@router.get("/schedules", response_model=ScheduleListResponse)
async def list_schedules(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all schedules for a facility."""
    await _get_facility(facility_id, current_user, db)
    total = (await db.execute(
        select(func.count(Schedule.id)).where(Schedule.facility_id == facility_id)
    )).scalar()
    result = await db.execute(
        select(Schedule).where(Schedule.facility_id == facility_id)
    )
    return ScheduleListResponse(schedules=result.scalars().all(), total=total)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    facility_id: UUID, schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a schedule."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(Schedule).where(Schedule.id == schedule_id, Schedule.facility_id == facility_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(schedule)
    await db.commit()


# ── Automation Rules ───────────────────────────────

@router.post("/rules", response_model=AutomationRuleResponse,
             status_code=status.HTTP_201_CREATED)
async def create_rule(
    facility_id: UUID,
    data: AutomationRuleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new automation rule for a facility."""
    await _get_facility(facility_id, current_user, db)
    rule = AutomationRule(
        facility_id=facility_id,
        created_by=current_user.id,
        **data.model_dump(),
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.get("/rules", response_model=AutomationRuleListResponse)
async def list_rules(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all automation rules for a facility."""
    await _get_facility(facility_id, current_user, db)
    total = (await db.execute(
        select(func.count(AutomationRule.id)).where(AutomationRule.facility_id == facility_id)
    )).scalar()
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.facility_id == facility_id)
    )
    return AutomationRuleListResponse(rules=result.scalars().all(), total=total)


@router.patch("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    facility_id: UUID, rule_id: UUID,
    data: AutomationRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an automation rule."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(AutomationRule).where(
            AutomationRule.id == rule_id, AutomationRule.facility_id == facility_id
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    facility_id: UUID, rule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an automation rule."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(AutomationRule).where(
            AutomationRule.id == rule_id, AutomationRule.facility_id == facility_id
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    await db.delete(rule)
    await db.commit()


# ── Command Queue ──────────────────────────────────

@router.post("/commands", response_model=CommandResponse,
             status_code=status.HTTP_201_CREATED)
async def queue_command(
    facility_id: UUID,
    data: CommandCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a command for execution by an edge agent."""
    await _get_facility(facility_id, current_user, db)
    cmd = CommandQueue(
        facility_id=facility_id,
        issued_by=current_user.id,
        **data.model_dump(),
    )
    db.add(cmd)
    await db.flush()
    await db.refresh(cmd)
    return cmd


@router.get("/commands", response_model=CommandListResponse)
async def list_commands(
    facility_id: UUID,
    state: str | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List commands for a facility with optional state filter."""
    await _get_facility(facility_id, current_user, db)
    query = select(CommandQueue).where(CommandQueue.facility_id == facility_id)
    count_query = select(func.count(CommandQueue.id)).where(CommandQueue.facility_id == facility_id)
    if state:
        query = query.where(CommandQueue.state == state)
        count_query = count_query.where(CommandQueue.state == state)
    total = (await db.execute(count_query)).scalar()
    result = await db.execute(query.order_by(CommandQueue.issued_at.desc()).limit(limit))
    return CommandListResponse(commands=result.scalars().all(), total=total)

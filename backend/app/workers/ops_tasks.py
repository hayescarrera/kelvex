"""
Operational Celery tasks — retention maintenance and the internal ops digest.

These are for Kelvex (the operator of the platform), not for customers:
  - run_retention_maintenance: daily Timescale policies + reading-table pruning
  - send_ops_digest: daily email to OPS_ALERT_EMAIL summarizing fleet health,
    so a customer's silent data outage is noticed by us before they notice.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.workers.celery_app import celery_app
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.ops_tasks.run_retention_maintenance")
def run_retention_maintenance():
    """Daily: ensure Timescale policies exist and prune reading tables."""
    asyncio.run(_async_retention_maintenance())


@celery_app.task(name="app.workers.ops_tasks.send_ops_digest")
def send_ops_digest():
    """Daily: email fleet-health summary to OPS_ALERT_EMAIL."""
    asyncio.run(_async_ops_digest())


async def _async_retention_maintenance() -> None:
    from app.services.data_retention import apply_retention_policies, prune_reading_tables, get_retention_stats

    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    try:
        policies = await apply_retention_policies(engine)
        pruned = await prune_reading_tables(engine)
        stats = await get_retention_stats(engine)
        logger.info(
            "Retention maintenance: policies=%s pruned=%s stats=%s",
            policies, pruned, stats,
        )
    finally:
        await engine.dispose()


async def _async_ops_digest() -> None:
    settings = get_settings()
    ops_email = settings.OPS_ALERT_EMAIL
    if not ops_email:
        logger.info("OPS_ALERT_EMAIL not set; skipping ops digest.")
        return

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.agent import EdgeAgent
    from app.models.facility import Facility
    from app.models.user import Organization
    from app.models.control import CommandQueue
    from app.models.refrigerant import LeakEvent

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    try:
        async with session_factory() as db:
            # Agents not connected (enabled, has heartbeated at least once)
            res = await db.execute(
                select(EdgeAgent.name, EdgeAgent.connection_state, EdgeAgent.last_heartbeat,
                       Facility.name, Organization.name)
                .join(Facility, EdgeAgent.facility_id == Facility.id)
                .join(Organization, Facility.org_id == Organization.id)
                .where(
                    EdgeAgent.enabled == True,  # noqa: E712
                    EdgeAgent.last_heartbeat.isnot(None),
                    EdgeAgent.connection_state != "connected",
                )
            )
            offline_agents = res.all()

            # Facilities whose agents exist but sent no telemetry in 24h
            res = await db.execute(
                select(Facility.name, Organization.name, func.max(EdgeAgent.last_telemetry_at))
                .join(Organization, Facility.org_id == Organization.id)
                .join(EdgeAgent, EdgeAgent.facility_id == Facility.id)
                .where(EdgeAgent.enabled == True, Facility.deleted_at == None)  # noqa: E711,E712
                .group_by(Facility.name, Organization.name)
                .having(func.max(EdgeAgent.last_telemetry_at) < day_ago)
            )
            silent_facilities = res.all()

            failed_cmds = (await db.execute(
                select(func.count(CommandQueue.id)).where(
                    and_(CommandQueue.state == "failed", CommandQueue.completed_at >= day_ago)
                )
            )).scalar() or 0

            new_leaks = (await db.execute(
                select(func.count(LeakEvent.id)).where(LeakEvent.detected_at >= day_ago)
            )).scalar() or 0

        all_clear = not offline_agents and not silent_facilities and failed_cmds == 0

        lines_txt = [f"Kelvex ops digest — {now:%Y-%m-%d %H:%M} UTC", ""]
        lines_html = []

        if offline_agents:
            lines_txt.append(f"AGENTS OFFLINE ({len(offline_agents)}):")
            lines_html.append(f"<h3 style='color:#DC2626'>Agents offline ({len(offline_agents)})</h3><ul>")
            for name, state, hb, fac, org in offline_agents:
                mins = int((now - hb).total_seconds() / 60) if hb else "?"
                lines_txt.append(f"  - {org} / {fac} / {name}: {state}, last heartbeat {mins}m ago")
                lines_html.append(f"<li><b>{org} / {fac} / {name}</b> — {state}, last heartbeat {mins}m ago</li>")
            lines_html.append("</ul>")

        if silent_facilities:
            lines_txt.append(f"NO TELEMETRY IN 24H ({len(silent_facilities)}):")
            lines_html.append(f"<h3 style='color:#D97706'>No telemetry in 24h ({len(silent_facilities)})</h3><ul>")
            for fac, org, last in silent_facilities:
                lines_txt.append(f"  - {org} / {fac}: last data {last:%Y-%m-%d %H:%M} UTC" if last else f"  - {org} / {fac}: never")
                lines_html.append(f"<li><b>{org} / {fac}</b> — last data {last:%Y-%m-%d %H:%M} UTC</li>" if last else f"<li><b>{org} / {fac}</b> — never</li>")
            lines_html.append("</ul>")

        lines_txt.append(f"Failed commands (24h): {failed_cmds}")
        lines_txt.append(f"New leak events (24h): {new_leaks}")
        lines_html.append(f"<p>Failed commands (24h): <b>{failed_cmds}</b><br>New leak events (24h): <b>{new_leaks}</b></p>")

        subject = (
            "Kelvex ops: all clear"
            if all_clear
            else f"Kelvex ops: {len(offline_agents)} offline, {len(silent_facilities)} silent, {failed_cmds} failed cmds"
        )

        from app.services.notification_service import send_transactional_email
        await send_transactional_email(
            to_email=ops_email,
            subject=subject,
            html_body="".join(lines_html) or "<p>All systems reporting normally.</p>",
            text_body="\n".join(lines_txt),
        )
        logger.info("Ops digest sent to %s (%s)", ops_email, subject)
    except Exception:
        logger.exception("Ops digest failed")
    finally:
        await engine.dispose()

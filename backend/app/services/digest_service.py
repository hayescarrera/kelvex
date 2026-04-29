"""
Email Digest Service — automated facility summary emails.

Generates HTML email digests with:
  - Alert summary (new, active, resolved by severity)
  - Power consumption highlights (peak demand, estimated kWh)
  - Control action summary (commands issued, success rate)
  - Automation rule activity

Usage:
    from app.services.digest_service import send_digest
    await send_digest(db, org_id, hours=24)

The digest runs as a scheduled background task (see main.py lifespan).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.facility import Facility, Equipment
from app.models.alert import Alert
from app.models.control import CommandQueue, AutomationRule
from app.models.telemetry import Telemetry
from app.models.notification import NotificationChannel
from app.models.user import Organization
from app.services.notification_service import send_notification

logger = logging.getLogger("coldgrid.digest")


async def build_digest_html(db: AsyncSession, org_id: UUID, hours: int = 24) -> tuple[str, str]:
    """
    Build a digest email subject + HTML body for an organization.
    Returns (subject, html_body).
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    period = f"Last {hours}h" if hours < 48 else f"Last {hours // 24}d"

    # ── Gather data ──────────────────────────────
    # Facilities
    fac_result = await db.execute(
        select(Facility.id, Facility.name).where(
            Facility.org_id == org_id,
            Facility.deleted_at == None,
        )
    )
    facilities = fac_result.all()
    fac_ids = [f.id for f in facilities]

    if not fac_ids:
        return (
            f"Kelvex Digest — {period}",
            "<p>No facilities configured.</p>",
        )

    # Alerts
    alert_counts = {}
    for sev in ["critical", "high", "medium", "low", "info"]:
        r = await db.execute(
            select(func.count()).where(
                Alert.facility_id.in_(fac_ids),
                Alert.severity == sev,
                Alert.state == "active",
                Alert.created_at >= since,
            )
        )
        alert_counts[sev] = r.scalar() or 0

    total_new = sum(alert_counts.values())
    resolved = (await db.execute(
        select(func.count()).where(
            Alert.facility_id.in_(fac_ids),
            Alert.state == "resolved",
            Alert.resolved_at >= since,
        )
    )).scalar() or 0

    # Power (avg and peak across all facilities)
    power_result = await db.execute(
        select(
            func.avg(Telemetry.value).label("avg_kw"),
            func.max(Telemetry.value).label("peak_kw"),
        )
        .join(Equipment, Equipment.id == Telemetry.equipment_id)
        .where(
            Equipment.facility_id.in_(fac_ids),
            Telemetry.metric_name == "kw_demand",
            Telemetry.time >= since,
        )
    )
    prow = power_result.one()
    avg_kw = float(prow.avg_kw or 0)
    peak_kw = float(prow.peak_kw or 0)
    est_kwh = avg_kw * hours

    # Commands
    cmd_total = (await db.execute(
        select(func.count()).where(
            CommandQueue.facility_id.in_(fac_ids),
            CommandQueue.issued_at >= since,
        )
    )).scalar() or 0

    cmd_completed = (await db.execute(
        select(func.count()).where(
            CommandQueue.facility_id.in_(fac_ids),
            CommandQueue.issued_at >= since,
            CommandQueue.state == "completed",
        )
    )).scalar() or 0

    cmd_failed = (await db.execute(
        select(func.count()).where(
            CommandQueue.facility_id.in_(fac_ids),
            CommandQueue.issued_at >= since,
            CommandQueue.state == "failed",
        )
    )).scalar() or 0

    # Automation
    rule_fires = (await db.execute(
        select(func.sum(AutomationRule.execution_count_today)).where(
            AutomationRule.facility_id.in_(fac_ids),
        )
    )).scalar() or 0

    # ── Build HTML ───────────────────────────────
    sev_colors = {
        "critical": "#c93131", "high": "#e67700",
        "medium": "#c17e13", "low": "#0e82c8", "info": "#888",
    }

    alert_rows = ""
    for sev in ["critical", "high", "medium", "low", "info"]:
        count = alert_counts[sev]
        if count > 0:
            color = sev_colors[sev]
            alert_rows += f"""
            <tr>
                <td style="padding:6px 12px;border-bottom:1px solid #eee;">
                    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:6px;"></span>
                    {sev.title()}
                </td>
                <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{count}</td>
            </tr>"""

    subject = f"Kelvex Digest — {period}"
    if alert_counts["critical"] > 0:
        subject = f"⚠ Kelvex Digest — {alert_counts['critical']} Critical Alert{'s' if alert_counts['critical'] > 1 else ''}"

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;color:#1a1a1a;">
        <div style="background:#0d9488;padding:20px 24px;border-radius:8px 8px 0 0;">
            <h1 style="color:#fff;margin:0;font-size:20px;">❄ Kelvex Digest</h1>
            <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">
                {period} • {len(facilities)} Facilit{'y' if len(facilities) == 1 else 'ies'}
            </p>
        </div>

        <div style="background:#fff;padding:24px;border:1px solid #e5e5e5;border-top:none;">
            <!-- Alerts Section -->
            <h2 style="font-size:15px;margin:0 0 12px;color:#333;">Alerts</h2>
            <div style="display:flex;gap:16px;margin-bottom:16px;">
                <div style="flex:1;background:#fef2f2;padding:12px;border-radius:6px;text-align:center;">
                    <div style="font-size:24px;font-weight:700;color:#c93131;">{total_new}</div>
                    <div style="font-size:11px;color:#888;">New Active</div>
                </div>
                <div style="flex:1;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center;">
                    <div style="font-size:24px;font-weight:700;color:#0d9f5f;">{resolved}</div>
                    <div style="font-size:11px;color:#888;">Resolved</div>
                </div>
            </div>
            {f'''
            <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;">
                {alert_rows}
            </table>
            ''' if alert_rows else '<p style="font-size:13px;color:#888;margin-bottom:20px;">No new alerts.</p>'}

            <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">

            <!-- Power Section -->
            <h2 style="font-size:15px;margin:0 0 12px;color:#333;">Power Consumption</h2>
            <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;">
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Average Demand</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{avg_kw:.1f} kW</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Peak Demand</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{peak_kw:.1f} kW</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Est. Energy Used</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{est_kwh:,.0f} kWh</td>
                </tr>
            </table>

            <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">

            <!-- Controls Section -->
            <h2 style="font-size:15px;margin:0 0 12px;color:#333;">Control Actions</h2>
            <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;">
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Commands Issued</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{cmd_total}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Completed</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;color:#0d9f5f;">{cmd_completed}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Failed</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;color:#c93131;">{cmd_failed}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;">Automation Fires Today</td>
                    <td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{rule_fires}</td>
                </tr>
            </table>
        </div>

        <div style="background:#f9fafb;padding:16px 24px;border:1px solid #e5e5e5;border-top:none;border-radius:0 0 8px 8px;">
            <p style="font-size:11px;color:#888;margin:0;">
                This digest was generated by ColdGrid at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.
                Manage notification preferences in Settings → Notifications.
            </p>
        </div>
    </div>
    """

    return subject, html


async def send_digest(
    db: AsyncSession, org_id: UUID, hours: int = 24
) -> int:
    """
    Build and send a digest email to all enabled email channels for the org.
    Returns number of channels notified.
    """
    subject, html_body = await build_digest_html(db, org_id, hours)

    # Send via the notification service (it handles routing and logging)
    logs = await send_notification(
        db, org_id, subject, html_body,
        severity="info",
        category="system",
    )

    sent_count = sum(1 for l in logs if l.status == "sent")
    logger.info(f"Digest sent for org {org_id}: {sent_count}/{len(logs)} channels")
    return sent_count


# ── Scheduled Digest Runner ──────────────────────────

class DigestScheduler:
    """
    Background task that sends daily digests to all organizations.

    Runs once per day at the configured hour (default 7:00 UTC).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        send_hour_utc: int = 7,
        digest_hours: int = 24,
    ):
        self._session_factory = session_factory
        self._send_hour = send_hour_utc
        self._digest_hours = digest_hours
        self._running = False

    async def start(self):
        """Start the digest scheduler loop."""
        logger.info(f"Digest scheduler starting (send at {self._send_hour}:00 UTC)")
        self._running = True

        while self._running:
            now = datetime.now(timezone.utc)
            # Calculate next send time
            next_send = now.replace(hour=self._send_hour, minute=0, second=0, microsecond=0)
            if now >= next_send:
                next_send += timedelta(days=1)

            wait_seconds = (next_send - now).total_seconds()
            logger.info(f"Next digest in {wait_seconds / 3600:.1f} hours")

            # Wait until send time (check every 5 minutes in case of drift)
            while self._running and datetime.now(timezone.utc) < next_send:
                await asyncio.sleep(min(300, wait_seconds))
                wait_seconds = (next_send - datetime.now(timezone.utc)).total_seconds()

            if not self._running:
                break

            # Send digests for all orgs
            await self._send_all_digests()

    async def stop(self):
        self._running = False
        logger.info("Digest scheduler stopped")

    async def _send_all_digests(self):
        """Send digest to every organization that has enabled email channels."""
        try:
            async with self._session_factory() as db:
                # Find all orgs with at least one enabled email/slack channel
                result = await db.execute(
                    select(NotificationChannel.org_id)
                    .where(NotificationChannel.enabled == True)
                    .distinct()
                )
                org_ids = [r[0] for r in result.all()]

                for org_id in org_ids:
                    try:
                        await send_digest(db, org_id, self._digest_hours)
                        await db.commit()
                    except Exception as e:
                        logger.error(f"Digest failed for org {org_id}: {e}")
                        await db.rollback()

                logger.info(f"Daily digest complete: {len(org_ids)} organizations")
        except Exception as e:
            logger.error(f"Digest scheduler error: {e}", exc_info=True)


# ── Module-level lifecycle ───────────────────────────

_scheduler: DigestScheduler | None = None


async def start_digest_scheduler(session_factory: async_sessionmaker):
    global _scheduler
    _scheduler = DigestScheduler(session_factory=session_factory)
    asyncio.create_task(_scheduler.start())
    logger.info("Digest scheduler background task started")


async def stop_digest_scheduler():
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None

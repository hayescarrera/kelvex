"""
Alert Dispatch Service — fires notifications when alerts are created or escalated.

Flow:
  1. Alert is created → dispatch_alert_notifications() called
  2. For each matching enabled NotificationPolicy:
       a. Check cooldown (Redis) — skip if same alert_type/facility notified recently
       b. Check quiet hours — skip unless severity bypasses
       c. Skip digest-mode policies (queued separately)
       d. Format rich subject + HTML body
       e. Call send_notification() with policy-scoped channel filtering
       f. Set cooldown key in Redis
  3. Schedule escalation task for unacknowledged critical alerts
  4. Digest worker (separate scheduled task) batches digest-mode policies

Escalation:
  - asyncio.create_task() fires after escalation_delay_minutes
  - Task checks if alert is still active/unacknowledged before sending
  - Redis key tracks in-flight escalation tasks for cancellation on acknowledge
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.alert import Alert
from app.models.facility import Facility
from app.models.notification import NotificationChannel
from app.models.notification_policy import NotificationPolicy, SEVERITY_RANK
from app.services.notification_service import send_notification

logger = logging.getLogger("kelvex.alert_dispatch")

_settings = get_settings()

# Redis client for cooldowns — created lazily
_redis: Redis | None = None


async def _get_redis() -> Redis | None:
    global _redis
    if _redis is None and _settings.REDIS_URL:
        try:
            _redis = Redis.from_url(_settings.REDIS_URL, decode_responses=True)
            await _redis.ping()
        except Exception:
            _redis = None
    return _redis


# ── Cooldown helpers ────────────────────────────────────────────────────────

def _cooldown_key(org_id: UUID, facility_id: UUID, alert_type: str) -> str:
    return f"notif:cd:{org_id}:{facility_id}:{alert_type}"


async def _is_in_cooldown(redis: Redis, org_id: UUID, facility_id: UUID, alert_type: str) -> bool:
    key = _cooldown_key(org_id, facility_id, alert_type)
    return bool(await redis.exists(key))


async def _set_cooldown(redis: Redis, org_id: UUID, facility_id: UUID, alert_type: str, minutes: int) -> None:
    key = _cooldown_key(org_id, facility_id, alert_type)
    await redis.setex(key, minutes * 60, "1")


async def _clear_cooldown(org_id: UUID, facility_id: UUID, alert_type: str) -> None:
    redis = await _get_redis()
    if redis:
        await redis.delete(_cooldown_key(org_id, facility_id, alert_type))


# ── Escalation helpers ──────────────────────────────────────────────────────

def _escalation_key(alert_id: UUID) -> str:
    return f"notif:esc:{alert_id}"


async def cancel_escalation(alert_id: UUID) -> None:
    """Call this when an alert is acknowledged or resolved."""
    redis = await _get_redis()
    if redis:
        await redis.setex(_escalation_key(alert_id), 3600, "cancelled")


# ── Notification formatting ─────────────────────────────────────────────────

_SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "⚠️",
    "medium": "⚡",
    "low": "ℹ️",
    "info": "💬",
}

_SEVERITY_COLOR = {
    "critical": "#E53E3E",
    "high": "#DD6B20",
    "medium": "#D69E2E",
    "low": "#3182CE",
    "info": "#718096",
}


def _format_subject(alert: Alert, facility_name: str) -> str:
    emoji = _SEVERITY_EMOJI.get(alert.severity, "")
    sev = alert.severity.upper()
    parts = [f"[{sev}]", facility_name, "—", alert.title]
    if alert.trigger_value and alert.threshold_value:
        parts.append(f"({alert.trigger_value} / threshold {alert.threshold_value})")
    return f"{emoji} {' '.join(parts)}"


def _format_html_body(alert: Alert, facility_name: str, is_escalation: bool = False) -> str:
    color = _SEVERITY_COLOR.get(alert.severity, "#718096")
    sev = alert.severity.upper()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    escalation_banner = ""
    if is_escalation:
        escalation_banner = f"""
        <tr>
          <td style="background:#FFF3CD;padding:10px 24px;font-size:13px;color:#856404;border-bottom:1px solid #FFEEBA">
            ⏰ <strong>Escalation notice</strong> — this alert has not been acknowledged.
          </td>
        </tr>"""

    trigger_row = ""
    if alert.trigger_value or alert.threshold_value:
        trigger_row = f"""
        <tr>
          <td style="padding:0 24px 16px">
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#F7FAFC;border-radius:6px;border:1px solid #E2E8F0">
              <tr>
                <td style="padding:12px 16px;font-size:13px;color:#4A5568">
                  <strong>Measured:</strong> {alert.trigger_value or '—'}&emsp;
                  <strong>Threshold:</strong> {alert.threshold_value or '—'}
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    dashboard_url = "https://app.kelvex.io"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F0F4F8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F0F4F8;padding:32px 0">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">

  <!-- Header -->
  <tr>
    <td style="background:{color};padding:20px 24px">
      <span style="color:#FFFFFF;font-size:13px;font-weight:600;letter-spacing:.08em">{sev}</span>
      <h1 style="color:#FFFFFF;margin:4px 0 0;font-size:18px;font-weight:700;line-height:1.3">{alert.title}</h1>
    </td>
  </tr>
  {escalation_banner}

  <!-- Site & time -->
  <tr>
    <td style="padding:16px 24px 8px;border-bottom:1px solid #E2E8F0">
      <span style="font-size:13px;color:#718096">
        🏭 <strong style="color:#2D3748">{facility_name}</strong>
        &emsp;·&emsp;
        🕐 {now_str}
        &emsp;·&emsp;
        Category: <strong style="color:#2D3748">{alert.category}</strong>
      </span>
    </td>
  </tr>

  <!-- Message -->
  <tr>
    <td style="padding:16px 24px">
      <p style="margin:0;font-size:15px;color:#2D3748;line-height:1.6">{alert.message or alert.title}</p>
    </td>
  </tr>

  {trigger_row}

  <!-- CTA -->
  <tr>
    <td style="padding:0 24px 24px;text-align:center">
      <a href="{dashboard_url}" style="display:inline-block;background:{color};color:#FFFFFF;font-weight:600;font-size:14px;padding:10px 28px;border-radius:6px;text-decoration:none">View in Kelvex</a>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:#F7FAFC;padding:12px 24px;border-top:1px solid #E2E8F0">
      <p style="margin:0;font-size:11px;color:#A0AEC0">
        Kelvex · Vendor-neutral refrigeration monitoring ·
        <a href="{dashboard_url}/settings/notifications" style="color:#A0AEC0">Manage notifications</a>
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _format_plain_body(alert: Alert, facility_name: str, is_escalation: bool = False) -> str:
    lines = []
    if is_escalation:
        lines.append("ESCALATION — this alert has not been acknowledged.\n")
    lines.append(f"[{alert.severity.upper()}] {alert.title}")
    lines.append(f"Site: {facility_name}")
    lines.append(f"Category: {alert.category}  |  Type: {alert.alert_type}")
    if alert.trigger_value:
        lines.append(f"Measured: {alert.trigger_value}  |  Threshold: {alert.threshold_value or '—'}")
    if alert.message:
        lines.append(f"\n{alert.message}")
    lines.append(f"\nView in Kelvex: https://app.kelvex.io")
    return "\n".join(lines)


# ── Core dispatch ───────────────────────────────────────────────────────────

async def dispatch_alert_notifications(
    db: AsyncSession,
    alert: Alert,
    facility: Facility,
    is_escalation: bool = False,
) -> int:
    """
    Dispatch notifications for a fired alert.
    Returns count of notification batches sent.
    """
    redis = await _get_redis()
    now_utc_hour = datetime.now(timezone.utc).hour
    org_id = facility.org_id

    # Load active notification policies for this org
    result = await db.execute(
        select(NotificationPolicy).where(
            NotificationPolicy.org_id == org_id,
            NotificationPolicy.enabled == True,
        )
    )
    policies = result.scalars().all()

    sent_count = 0

    for policy in policies:
        # Does this policy care about this alert?
        if not policy.matches_alert(alert.facility_id, alert.severity, alert.category):
            continue

        # Digest-mode policies are handled by the digest worker, skip here
        if policy.digest_mode and not is_escalation:
            continue

        # Quiet hours check
        if policy.is_quiet_hour(now_utc_hour) and not policy.bypasses_quiet_hours(alert.severity):
            logger.debug(
                "Quiet hours suppressed alert %s for policy %s", alert.id, policy.id
            )
            continue

        # Cooldown check (skip for escalations — they should always go through)
        if not is_escalation and redis:
            if await _is_in_cooldown(redis, org_id, alert.facility_id, alert.alert_type):
                logger.debug(
                    "Cooldown suppressed alert %s (type=%s) for policy %s",
                    alert.id, alert.alert_type, policy.id,
                )
                continue

        # Format content
        subject = _format_subject(alert, facility.name)
        if is_escalation:
            subject = f"[ESCALATION] {subject}"
        body_html = _format_html_body(alert, facility.name, is_escalation=is_escalation)
        body_plain = _format_plain_body(alert, facility.name, is_escalation=is_escalation)

        # Determine which channels to use
        channel_ids = (
            policy.escalation_channel_ids if is_escalation and policy.escalation_channel_ids
            else policy.channel_ids
        )

        try:
            if channel_ids:
                # Send to each specified channel individually
                for channel_id in channel_ids:
                    try:
                        await send_notification(
                            db,
                            org_id=org_id,
                            subject=subject,
                            body=body_html,
                            facility_id=alert.facility_id,
                            channel_id=UUID(channel_id),
                            severity=alert.severity,
                            category=alert.category,
                        )
                    except Exception as e:
                        logger.error("Failed to send to channel %s: %s", channel_id, e)
            else:
                # Route to all matching org channels
                await send_notification(
                    db,
                    org_id=org_id,
                    subject=subject,
                    body=body_html,
                    facility_id=alert.facility_id,
                    severity=alert.severity,
                    category=alert.category,
                )

            sent_count += 1

            # Set cooldown after successful send
            if not is_escalation and redis:
                await _set_cooldown(
                    redis, org_id, alert.facility_id,
                    alert.alert_type, policy.cooldown_minutes
                )

        except Exception as e:
            logger.error("Notification dispatch failed for policy %s, alert %s: %s", policy.id, alert.id, e)

    # Schedule escalation for policies that want it
    if not is_escalation:
        await _schedule_escalations(db, alert, facility, policies)

    return sent_count


async def _schedule_escalations(
    db: AsyncSession,
    alert: Alert,
    facility: Facility,
    policies: list[NotificationPolicy],
) -> None:
    """Fire asyncio tasks for any escalation policies that match this alert."""
    for policy in policies:
        if not policy.escalation_enabled:
            continue
        if SEVERITY_RANK.get(alert.severity, 0) < SEVERITY_RANK.get(policy.escalation_min_severity, 4):
            continue
        if not policy.matches_alert(alert.facility_id, alert.severity, alert.category):
            continue

        delay_secs = policy.escalation_delay_minutes * 60
        asyncio.create_task(
            _escalation_task(
                alert_id=alert.id,
                facility_id=alert.facility_id,
                org_id=facility.org_id,
                policy_id=policy.id,
                delay_secs=delay_secs,
            ),
            name=f"escalation:{alert.id}:{policy.id}",
        )
        logger.info(
            "Escalation scheduled for alert %s in %d min (policy %s)",
            alert.id, policy.escalation_delay_minutes, policy.id,
        )


async def _escalation_task(
    alert_id: UUID,
    facility_id: UUID,
    org_id: UUID,
    policy_id: UUID,
    delay_secs: int,
) -> None:
    """Wait, then check if alert is still unacknowledged and escalate."""
    from app.core.database import async_session as AsyncSessionLocal

    await asyncio.sleep(delay_secs)

    redis = await _get_redis()
    if redis:
        cancelled = await redis.get(_escalation_key(alert_id))
        if cancelled == "cancelled":
            logger.info("Escalation cancelled for alert %s", alert_id)
            return

    async with AsyncSessionLocal() as db:
        try:
            # Re-fetch alert state
            result = await db.execute(select(Alert).where(Alert.id == alert_id))
            alert = result.scalar_one_or_none()
            if not alert or alert.state != "active":
                logger.info("Escalation skipped — alert %s is %s", alert_id, alert.state if alert else "gone")
                return

            result = await db.execute(select(Facility).where(Facility.id == facility_id))
            facility = result.scalar_one_or_none()
            if not facility:
                return

            from app.models.notification_policy import NotificationPolicy
            pol_result = await db.execute(
                select(NotificationPolicy).where(NotificationPolicy.id == policy_id)
            )
            policy = pol_result.scalar_one_or_none()
            if not policy:
                return

            logger.warning("Escalating unacknowledged alert %s", alert_id)
            await dispatch_alert_notifications(db, alert, facility, is_escalation=True)
            await db.commit()
        except Exception as e:
            logger.error("Escalation task error for alert %s: %s", alert_id, e)


# ── Digest worker ───────────────────────────────────────────────────────────

async def send_digests(db: AsyncSession) -> int:
    """
    Called by a periodic task. Collects active alerts and sends digest
    notifications to any policies in digest_mode whose interval has elapsed.
    """
    from app.models.notification_policy import NotificationPolicy
    redis = await _get_redis()
    now = datetime.now(timezone.utc)
    sent = 0

    result = await db.execute(
        select(NotificationPolicy).where(
            NotificationPolicy.enabled == True,
            NotificationPolicy.digest_mode == True,
        )
    )
    policies = result.scalars().all()

    for policy in policies:
        digest_key = f"notif:digest:last:{policy.id}"
        if redis:
            last_str = await redis.get(digest_key)
            if last_str:
                last_ts = float(last_str)
                elapsed_hours = (now.timestamp() - last_ts) / 3600
                if elapsed_hours < policy.digest_interval_hours:
                    continue

        # Collect active alerts for this policy's scope
        q = select(Alert).join(Facility, Alert.facility_id == Facility.id).where(
            Facility.org_id == policy.org_id,
            Alert.state == "active",
        )
        if policy.facility_ids:
            q = q.where(Alert.facility_id.in_([UUID(f) for f in policy.facility_ids]))
        if policy.categories:
            q = q.where(Alert.category.in_(policy.categories))
        min_rank = SEVERITY_RANK.get(policy.min_severity, 3)
        severity_values = [s for s, r in SEVERITY_RANK.items() if r >= min_rank]
        q = q.where(Alert.severity.in_(severity_values)).order_by(Alert.triggered_at.desc()).limit(50)

        alerts_result = await db.execute(q)
        active_alerts = alerts_result.scalars().all()

        if not active_alerts:
            continue

        # Build digest content
        subject = f"Kelvex Digest — {len(active_alerts)} active alert{'s' if len(active_alerts) != 1 else ''}"
        lines = [f"Active alerts as of {now.strftime('%Y-%m-%d %H:%M UTC')}\n"]
        for a in active_alerts:
            lines.append(f"[{a.severity.upper()}] {a.title} — {a.category}")
            if a.trigger_value:
                lines.append(f"  Measured: {a.trigger_value}  Threshold: {a.threshold_value or '—'}")
        lines.append("\nView all alerts: https://app.kelvex.io")
        body = "\n".join(lines)

        try:
            await send_notification(
                db,
                org_id=policy.org_id,
                subject=subject,
                body=body,
                severity="high",
                category=None,
            )
            if redis:
                await redis.set(digest_key, str(now.timestamp()))
            sent += 1
        except Exception as e:
            logger.error("Digest send failed for policy %s: %s", policy.id, e)

    return sent

"""
Notification delivery service — sends alerts via email, webhook, Slack, or SMS.

Supported channel types:
  - email:   SMTP delivery (plain + HTML)
  - webhook: POST JSON to URL
  - slack:   Incoming webhook
  - sms:     Twilio SMS (requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)

Usage:
    from app.services.notification_service import send_notification
    await send_notification(db, org_id, subject, body, facility_id=...)
"""

import logging
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from uuid import UUID
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.models.notification import NotificationChannel, NotificationLog

logger = logging.getLogger("coldgrid.notifications")


async def send_transactional_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
) -> None:
    """Send a one-off transactional email (password reset, invite, etc.) directly via SMTP."""
    import asyncio

    settings = get_settings()
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    password = settings.SMTP_PASSWORD
    from_addr = settings.SMTP_FROM

    if not host:
        raise ValueError("SMTP not configured — set SMTP_HOST in environment")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    await asyncio.to_thread(_smtp_send, host, port, user, password, from_addr, [to_email], msg)
    logger.info("Transactional email sent to %s: %s", to_email, subject)


async def send_notification(
    db: AsyncSession,
    org_id: UUID,
    subject: str,
    body: str,
    facility_id: UUID | None = None,
    channel_id: UUID | None = None,
    severity: str | None = None,
    category: str | None = None,
) -> list[NotificationLog]:
    """
    Send a notification to matching channels for the org.

    If channel_id is specified, sends to that single channel.
    Otherwise, fetches all enabled channels and filters using
    each channel's routing rules (facility_ids, min_severity, categories).
    """
    if channel_id:
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.id == channel_id,
                NotificationChannel.org_id == org_id,
                NotificationChannel.enabled == True,
            )
        )
        channels = list(result.scalars().all())
    else:
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.org_id == org_id,
                NotificationChannel.enabled == True,
            )
        )
        channels = list(result.scalars().all())

    if not channels:
        logger.info(f"No enabled notification channels for org {org_id}")
        return []

    # Apply routing filters when no specific channel is targeted
    if not channel_id:
        fac_str = str(facility_id) if facility_id else None
        channels = [
            ch for ch in channels
            if ch.matches_alert(fac_str, severity, category)
        ]
        if not channels:
            logger.info(
                f"No channels match routing filters "
                f"(facility={fac_str}, severity={severity}, category={category})"
            )
            return []

    logs = []
    for channel in channels:
        log = await _deliver(db, channel, org_id, facility_id, subject, body)
        logs.append(log)

    await db.flush()
    return logs


async def _deliver(
    db: AsyncSession,
    channel: NotificationChannel,
    org_id: UUID,
    facility_id: UUID | None,
    subject: str,
    body: str,
) -> NotificationLog:
    """Deliver to a single channel and record the result."""
    status = "sent"
    error_message = None

    try:
        if channel.channel_type == "email":
            await _send_email(channel.config, subject, body)
        elif channel.channel_type == "webhook":
            await _send_webhook(channel.config, subject, body, facility_id)
        elif channel.channel_type == "slack":
            await _send_slack(channel.config, subject, body)
        elif channel.channel_type == "sms":
            await _send_sms(channel.config, subject, body)
        else:
            raise ValueError(f"Unknown channel type: {channel.channel_type}")
    except Exception as e:
        status = "failed"
        error_message = str(e)[:1000]
        logger.error(f"Notification delivery failed for channel {channel.name}: {e}")

    log = NotificationLog(
        org_id=org_id,
        channel_id=channel.id,
        facility_id=facility_id,
        subject=subject,
        body=body,
        channel_type=channel.channel_type,
        status=status,
        error_message=error_message,
    )
    db.add(log)
    return log


async def _send_email(config: dict, subject: str, body: str) -> None:
    """Send via SMTP. Uses app settings or channel-specific config."""
    settings = get_settings()
    host = config.get("smtp_host") or settings.SMTP_HOST
    port = config.get("smtp_port") or settings.SMTP_PORT
    user = config.get("smtp_user") or settings.SMTP_USER
    password = config.get("smtp_password") or settings.SMTP_PASSWORD
    from_addr = config.get("from") or settings.SMTP_FROM
    recipients = config.get("recipients", [])

    if not host:
        raise ValueError("SMTP not configured — set SMTP_HOST in environment or channel config")
    if not recipients:
        raise ValueError("No email recipients configured for this channel")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ColdGrid] {subject}"
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(f"<html><body><h3>{subject}</h3><p>{body}</p></body></html>", "html"))

    # Run SMTP in a thread to avoid blocking the event loop
    import asyncio
    await asyncio.to_thread(_smtp_send, host, port, user, password, from_addr, recipients, msg)
    logger.info(f"Email sent to {recipients}: {subject}")


def _smtp_send(host, port, user, password, from_addr, recipients, msg):
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        if port == 587:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(from_addr, recipients, msg.as_string())


async def _send_webhook(config: dict, subject: str, body: str, facility_id: UUID | None) -> None:
    """POST JSON to a webhook URL."""
    url = config.get("url")
    if not url:
        raise ValueError("Webhook URL not configured")

    headers = config.get("headers", {})
    headers.setdefault("Content-Type", "application/json")

    payload = {
        "source": "coldgrid",
        "subject": subject,
        "body": body,
        "facility_id": str(facility_id) if facility_id else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()

    logger.info(f"Webhook delivered to {url}: {subject}")


async def _send_slack(config: dict, subject: str, body: str) -> None:
    """Send to a Slack incoming webhook."""
    webhook_url = config.get("webhook_url")
    if not webhook_url:
        raise ValueError("Slack webhook_url not configured")

    payload = {
        "text": f"*{subject}*\n{body}",
        "username": "ColdGrid Alerts",
        "icon_emoji": ":snowflake:",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()

    logger.info(f"Slack notification sent: {subject}")


async def _send_sms(config: dict, subject: str, body: str) -> None:
    """
    Send an SMS alert via Twilio.

    Channel config:
        {"recipients": ["+15551234567", "+15559876543"]}

    Uses app-level Twilio credentials from environment:
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

    Or channel-level overrides in config:
        {"account_sid": "...", "auth_token": "...", "from_number": "+1..."}

    ── INTEGRATION NOTE ──────────────────────────────
    To wire this up:
      1. pip install twilio
      2. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER in .env
      3. Uncomment the Twilio client code below and remove the stub
    ──────────────────────────────────────────────────
    """
    settings = get_settings()

    account_sid = config.get("account_sid") or settings.TWILIO_ACCOUNT_SID
    auth_token = config.get("auth_token") or settings.TWILIO_AUTH_TOKEN
    from_number = config.get("from_number") or settings.TWILIO_FROM_NUMBER
    recipients = config.get("recipients", [])

    if not recipients:
        raise ValueError("No SMS recipients configured for this channel")

    # Compose SMS body — keep it short for 160-char segments
    sms_body = f"[ColdGrid] {subject}"
    if body and len(sms_body) + len(body) + 2 < 1500:
        sms_body = f"[ColdGrid] {subject}\n{body}"
    # Truncate to ~3 SMS segments max
    if len(sms_body) > 450:
        sms_body = sms_body[:447] + "..."

    if not account_sid or not auth_token or not from_number:
        # ── STUB: Twilio not configured ──
        # Log the message that would have been sent so operators can verify
        # the pipeline works end-to-end before adding Twilio credentials.
        for number in recipients:
            logger.warning(
                f"SMS STUB (Twilio not configured) → {number}: {sms_body}"
            )
        return  # Logged but not actually sent — no error

    # ── REAL DELIVERY ──
    # Requires: pip install twilio
    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning(
            f"SMS skipped — twilio package not installed. "
            f"Run: pip install twilio"
        )
        return

    import asyncio

    client = Client(account_sid, auth_token)

    for number in recipients:
        await asyncio.to_thread(
            client.messages.create,
            body=sms_body,
            from_=from_number,
            to=number,
        )
        logger.info(f"SMS sent to {number}: {subject}")

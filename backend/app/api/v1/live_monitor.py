"""
Live Monitor API — org-wide real-time compressor telemetry.

This powers the Foreman-style cloud dashboard. Operators log into
coldgrid.io and see every compressor across all their facilities
with live-updating metrics — no VPN needed.

Endpoints:
  GET  /live-monitor              — All compressors with latest readings (org-wide)
  GET  /live-monitor/facility/{id} — Single facility live view
"""

from uuid import UUID
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from app.core.database import get_db
from app.core.security import get_current_user, get_accessible_facility_ids
from app.models.user import User
from app.models.facility import Facility
from app.models.compressor import Compressor, CompressorReading
from app.models.agent import EdgeAgent

router = APIRouter(prefix="/live-monitor", tags=["live-monitor"])


@router.get("")
async def org_wide_live(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get live telemetry for ALL compressors across all facilities in the org.

    Returns facility groupings with latest reading per compressor,
    agent connectivity status, and org-wide aggregates.
    Designed to be polled every 5-10 seconds by the frontend.
    """
    # Get all org facilities
    fac_query = select(Facility).where(
        Facility.org_id == current_user.org_id,
        Facility.deleted_at == None,
    ).order_by(Facility.name)
    accessible = await get_accessible_facility_ids(current_user, db)
    if accessible is not None:
        fac_query = fac_query.where(Facility.id.in_(accessible))
    fac_result = await db.execute(fac_query)
    facilities = list(fac_result.scalars().all())

    # Aggregates
    org_total = 0
    org_running = 0
    org_alarm = 0
    org_kw = 0.0
    org_offline = 0

    facility_data = []
    for fac in facilities:
        # Get compressors
        comp_result = await db.execute(
            select(Compressor)
            .where(Compressor.facility_id == fac.id)
            .order_by(Compressor.rack_name, Compressor.name)
        )
        compressors = list(comp_result.scalars().all())

        # Get agents for connectivity status
        agent_result = await db.execute(
            select(EdgeAgent).where(
                EdgeAgent.facility_id == fac.id,
                EdgeAgent.enabled == True,
            )
        )
        agents = list(agent_result.scalars().all())

        agent_status = "offline"
        last_heartbeat = None
        for a in agents:
            if a.connection_state == "connected":
                agent_status = "connected"
            if a.last_heartbeat and (last_heartbeat is None or a.last_heartbeat > last_heartbeat):
                last_heartbeat = a.last_heartbeat

        # If heartbeat is older than 2 minutes, mark as stale
        if last_heartbeat:
            if (datetime.now(timezone.utc) - last_heartbeat).total_seconds() > 120:
                agent_status = "stale"

        fac_compressors = []
        fac_kw = 0.0
        fac_running = 0
        fac_alarm = 0

        for comp in compressors:
            # Get latest reading
            reading_result = await db.execute(
                select(CompressorReading)
                .where(CompressorReading.compressor_id == comp.id)
                .order_by(desc(CompressorReading.recorded_at))
                .limit(1)
            )
            latest = reading_result.scalar_one_or_none()

            # Freshness check — is the reading recent?
            is_stale = True
            if latest and latest.recorded_at:
                age = (datetime.now(timezone.utc) - latest.recorded_at.replace(tzinfo=timezone.utc)
                       if latest.recorded_at.tzinfo is None
                       else datetime.now(timezone.utc) - latest.recorded_at)
                is_stale = age.total_seconds() > 120  # >2 min = stale

            # Detect anomalies
            anomalies = []
            if latest:
                if comp.alarm_discharge_psi_high and latest.discharge_pressure_psi:
                    if latest.discharge_pressure_psi > comp.alarm_discharge_psi_high:
                        anomalies.append({"type": "high_discharge", "value": latest.discharge_pressure_psi, "threshold": comp.alarm_discharge_psi_high})
                if comp.alarm_suction_psi_low and latest.suction_pressure_psi:
                    if latest.suction_pressure_psi < comp.alarm_suction_psi_low:
                        anomalies.append({"type": "low_suction", "value": latest.suction_pressure_psi, "threshold": comp.alarm_suction_psi_low})
                if comp.alarm_oil_temp_high and latest.oil_temp_f:
                    if latest.oil_temp_f > comp.alarm_oil_temp_high:
                        anomalies.append({"type": "high_oil_temp", "value": latest.oil_temp_f, "threshold": comp.alarm_oil_temp_high})
                if comp.alarm_bearing_temp_high and latest.bearing_temp_f:
                    if latest.bearing_temp_f > comp.alarm_bearing_temp_high:
                        anomalies.append({"type": "high_bearing_temp", "value": latest.bearing_temp_f, "threshold": comp.alarm_bearing_temp_high})
                if comp.alarm_vibration_high and latest.vibration_ips:
                    if latest.vibration_ips > comp.alarm_vibration_high:
                        anomalies.append({"type": "high_vibration", "value": latest.vibration_ips, "threshold": comp.alarm_vibration_high})

            compressor_data = {
                "id": str(comp.id),
                "name": comp.name,
                "tag": comp.tag,
                "manufacturer": comp.manufacturer,
                "model": comp.model,
                "state": comp.state,
                "health_score": comp.health_score,
                "refrigerant": comp.refrigerant,
                "hp": comp.hp,
                "rack_name": comp.rack_name,
                "data_stale": is_stale,
                "anomalies": anomalies,
                "readings": {
                    "discharge_pressure_psi": latest.discharge_pressure_psi if latest else None,
                    "suction_pressure_psi": latest.suction_pressure_psi if latest else None,
                    "discharge_temp_f": latest.discharge_temp_f if latest else None,
                    "oil_temp_f": latest.oil_temp_f if latest else None,
                    "bearing_temp_f": latest.bearing_temp_f if latest else None,
                    "vibration_ips": latest.vibration_ips if latest else None,
                    "amp_draw": latest.amp_draw if latest else None,
                    "kw": latest.kw if latest else None,
                    "slide_valve_pct": latest.slide_valve_pct if latest else None,
                    "rpm": latest.rpm if latest else None,
                    "running": latest.running if latest else None,
                    "compression_ratio": latest.compression_ratio if latest else None,
                    "recorded_at": latest.recorded_at.isoformat() if latest else None,
                },
            }
            fac_compressors.append(compressor_data)

            if comp.state == "running":
                fac_running += 1
            if comp.state == "alarm":
                fac_alarm += 1
            if latest and latest.kw:
                fac_kw += latest.kw

        org_total += len(compressors)
        org_running += fac_running
        org_alarm += fac_alarm
        org_kw += fac_kw
        if agent_status == "offline":
            org_offline += 1

        facility_data.append({
            "facility_id": str(fac.id),
            "facility_name": fac.name,
            "location": f"{fac.city}, {fac.state}" if fac.city else None,
            "agent_status": agent_status,
            "last_heartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
            "total_compressors": len(compressors),
            "running": fac_running,
            "in_alarm": fac_alarm,
            "total_kw": round(fac_kw, 1) if fac_kw > 0 else None,
            "compressors": fac_compressors,
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "org_summary": {
            "total_facilities": len(facilities),
            "total_compressors": org_total,
            "running": org_running,
            "in_alarm": org_alarm,
            "offline_agents": org_offline,
            "total_kw": round(org_kw, 1) if org_kw > 0 else None,
        },
        "facilities": facility_data,
    }

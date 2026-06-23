from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.facilities import router as facilities_router
from app.api.v1.bills import router as bills_router
from app.api.v1.equipment import router as equipment_router
from app.api.v1.savings import router as savings_router
from app.api.v1.zones import router as zones_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.controls import router as controls_router
from app.api.v1.agents import router as agents_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.tariffs import router as tariffs_router, assign_router as tariff_assign_router
from app.api.v1.compressors import router as compressors_router
from app.api.v1.energy import router as energy_router
from app.api.v1.device_profiles import profiles_router, agent_devices_router
from app.api.v1.live_monitor import router as live_monitor_router
from app.api.v1.plant_control import router as plant_control_router
from app.api.v1.reports import router as reports_router
from app.api.v1.activity import router as activity_router
from app.api.v1.events import router as events_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.maintenance import router as maintenance_router
from app.api.v1.escalation import router as escalation_router
from app.api.v1.refrigerant import router as refrigerant_router
from app.api.v1.detection import router as detection_router
from app.api.v1.documents import router as documents_router
from app.api.v1.tunnel import router as tunnel_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(facilities_router)
api_router.include_router(bills_router)
api_router.include_router(equipment_router)
api_router.include_router(savings_router)
api_router.include_router(zones_router)
api_router.include_router(alerts_router)
api_router.include_router(controls_router)
api_router.include_router(agents_router)
api_router.include_router(integrations_router)
api_router.include_router(notifications_router)
api_router.include_router(tariffs_router)
api_router.include_router(tariff_assign_router)
api_router.include_router(compressors_router)
api_router.include_router(energy_router)
api_router.include_router(profiles_router)
api_router.include_router(agent_devices_router)
api_router.include_router(live_monitor_router)
api_router.include_router(plant_control_router)
api_router.include_router(reports_router)
api_router.include_router(activity_router)
api_router.include_router(events_router)
api_router.include_router(compliance_router)
api_router.include_router(maintenance_router)
api_router.include_router(escalation_router)
api_router.include_router(refrigerant_router)
api_router.include_router(detection_router)
api_router.include_router(documents_router)
api_router.include_router(tunnel_router)

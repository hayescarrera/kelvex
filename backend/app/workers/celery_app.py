"""
Celery application configuration for Kelvex background tasks.

Broker and result backend: Redis (same URL used by the rest of the platform).
Beat schedule drives:
  - Hourly leak detection batch
  - Daily forecasting batch
"""

from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kelvex",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.detection_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "run-leak-detection-hourly": {
            "task": "app.workers.detection_tasks.run_detection_batch",
            "schedule": 3600.0,  # every hour
        },
        "run-forecasting-daily": {
            "task": "app.workers.detection_tasks.run_forecasting_batch",
            "schedule": 86400.0,  # every 24 hours
        },
    },
)

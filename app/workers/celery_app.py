"""
app/workers/celery_app.py — Bloque 7.1 (actualizado)

Cambios respecto al bloque anterior:
  - Agrega 'app.workers.scheduled_tasks' al include para que Beat
    registre las tareas periódicas al arrancar.
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "docuflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks",
        "app.workers.scheduled_tasks",   # ← NUEVO Bloque 7.1
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.process_document": {"queue": "documents"},
    },
)

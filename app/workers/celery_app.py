from celery import Celery
from app.config import settings

celery_app = Celery(
    "docuflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,           # ACK solo cuando la tarea termina
    worker_prefetch_multiplier=1,  # 1 tarea por worker a la vez
    task_routes={
        "app.workers.tasks.process_document": {"queue": "documents"},
    },
)

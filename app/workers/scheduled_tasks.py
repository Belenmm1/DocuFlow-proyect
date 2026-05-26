"""
app/workers/scheduled_tasks.py — Bloque 7.4 (versión definitiva)

Tareas periódicas de mantenimiento registradas en Celery Beat:

  backup_database          → cada 24hs (00:00 UTC)
                             Ejecuta scripts/backup.sh con verificación
                             de integridad. Registra resultado en DB.
                             Reintentos automáticos: max 3, backoff 5min.

  cleanup_old_uploads      → cada 24hs (01:00 UTC)
                             Elimina uploads huérfanos (sin referencia en DB)
                             con más de 7 días de antigüedad.

  invalidate_stats_cache   → cada 5 minutos
                             Safety-net para mantener las métricas frescas.
"""

import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from celery.schedules import crontab
from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Backup de PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="docuflow.scheduled.backup_database",
    bind=True,
    max_retries=3,
    default_retry_delay=300,   # 5 min entre reintentos
    acks_late=True,
    time_limit=600,            # máximo 10 minutos por ejecución
    soft_time_limit=540,
)
def backup_database(self):
    """
    Ejecuta scripts/backup.sh dentro del contenedor worker.

    Requisitos:
      - pg_dump disponible en PATH (postgresql-client instalado en la imagen)
      - Variables: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DB_HOST

    Retorna dict con status, filename, size_bytes, duration_s, checksum.
    En caso de error reintenta hasta 3 veces con backoff de 5 minutos.
    """
    script = Path(__file__).resolve().parent.parent.parent / "scripts" / "backup.sh"

    if not script.exists():
        logger.error("backup.sh no encontrado en %s", script)
        raise FileNotFoundError(f"backup.sh no encontrado en {script}")

    logger.info("Iniciando backup programado (intento %d/%d)",
                self.request.retries + 1, self.max_retries + 1)

    try:
        env = {**os.environ, "BACKUP_VERIFY": "true"}

        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            timeout=540,
            env=env,
        )

        if result.returncode != 0:
            error_msg = result.stderr[-1000:] if result.stderr else "sin stderr"
            logger.error("backup.sh falló (código %d):\n%s",
                         result.returncode, error_msg)
            raise RuntimeError(f"backup.sh salió con código {result.returncode}: {error_msg}")

        # La última línea del stdout es el path del archivo (ver backup.sh)
        output_lines = result.stdout.strip().splitlines()
        backup_file = output_lines[-1] if output_lines else ""

        # Recopilar métricas del archivo
        file_path = Path(backup_file) if backup_file else None
        size_bytes = file_path.stat().st_size if (file_path and file_path.exists()) else 0
        checksum_file = Path(f"{backup_file}.sha256") if backup_file else None
        checksum = ""
        if checksum_file and checksum_file.exists():
            checksum = checksum_file.read_text().split()[0]

        logger.info(
            "Backup completado | file=%s | size_bytes=%d | sha256=%s",
            backup_file, size_bytes, checksum[:12] + "..." if checksum else "n/a"
        )

        _store_backup_record(
            filename=Path(backup_file).name if backup_file else "unknown",
            size_bytes=size_bytes,
            checksum=checksum,
            status="ok",
        )

        return {
            "status": "ok",
            "filename": Path(backup_file).name if backup_file else "",
            "size_bytes": size_bytes,
            "checksum_sha256": checksum,
            "output_tail": result.stdout[-300:],
        }

    except subprocess.TimeoutExpired:
        logger.error("Backup abortado: tiempo límite excedido (540s)")
        raise self.retry(exc=TimeoutError("backup.sh excedió el tiempo límite"))

    except Exception as exc:
        logger.error("Error en backup (intento %d): %s",
                     self.request.retries + 1, exc)
        _store_backup_record(
            filename="",
            size_bytes=0,
            checksum="",
            status="error",
            error=str(exc),
        )
        raise self.retry(exc=exc)


def _store_backup_record(
    filename: str,
    size_bytes: int,
    checksum: str,
    status: str,
    error: str = "",
) -> None:
    """
    Guarda un registro del backup en la tabla backup_logs.
    Si la tabla no existe (primera vez), lo omite silenciosamente.
    """
    try:
        from app.models.database import SessionLocal
        from app.models.backup_log import BackupLog

        with SessionLocal() as db:
            record = BackupLog(
                filename=filename,
                size_bytes=size_bytes,
                checksum_sha256=checksum,
                status=status,
                error_message=error[:500] if error else None,
                created_at=datetime.now(tz=timezone.utc),
            )
            db.add(record)
            db.commit()
    except Exception as exc:
        # No bloquear el backup por fallo de logging
        logger.warning("No se pudo guardar BackupLog: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Limpieza de uploads huérfanos
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="docuflow.scheduled.cleanup_old_uploads",
    bind=True,
    acks_late=True,
    time_limit=120,
)
def cleanup_old_uploads(self):
    """
    Elimina archivos físicos en UPLOAD_DIR que no tienen referencia en la DB
    y tienen más de 7 días de antigüedad.
    """
    from app.models.database import SessionLocal, Document

    upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads"))
    if not upload_dir.exists():
        return {"status": "skip", "reason": "upload_dir not found"}

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    deleted = 0
    errors = 0

    with SessionLocal() as db:
        known = {
            row.file_path
            for row in db.query(Document.file_path).all()
            if row.file_path
        }

    for f in upload_dir.rglob("*"):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if str(f) not in known and mtime < cutoff:
            try:
                f.unlink()
                deleted += 1
                logger.debug("Upload huérfano eliminado: %s", f)
            except OSError as exc:
                logger.warning("No se pudo eliminar %s: %s", f, exc)
                errors += 1

    logger.info("Limpieza de uploads: %d eliminados, %d errores", deleted, errors)
    return {"status": "ok", "deleted": deleted, "errors": errors}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Invalidar caché de stats (safety net)
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="docuflow.scheduled.invalidate_stats_cache",
    acks_late=False,
    time_limit=10,
)
def invalidate_stats_cache():
    """Borra la clave de stats en Redis para forzar refresco."""
    try:
        import redis
        from app.config import settings

        r = redis.from_url(settings.REDIS_URL)
        deleted = r.delete("stats:summary")
        logger.debug("Caché stats invalidado (keys=%d)", deleted)
        return {"status": "ok", "keys_deleted": deleted}
    except Exception as exc:
        logger.warning("No se pudo invalidar caché de stats: %s", exc)
        return {"status": "skip", "reason": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Registro en Beat
# ─────────────────────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    # Backup diario a las 00:00 UTC
    "backup-database-daily": {
        "task": "docuflow.scheduled.backup_database",
        "schedule": crontab(hour="0", minute="0"),
    },
    # Limpieza de uploads a las 01:00 UTC
    "cleanup-uploads-daily": {
        "task": "docuflow.scheduled.cleanup_old_uploads",
        "schedule": crontab(hour="1", minute="0"),
    },
    # Invalidar caché de stats cada 5 minutos
    "invalidate-stats-cache": {
        "task": "docuflow.scheduled.invalidate_stats_cache",
        "schedule": 300.0,
    },
}

"""
reports.py — Módulo de reportes y exportación.

Bloque 2.2: caché agregada en:
  - GET /stats/summary  → caché con TTL CACHE_TTL_STATS (5 min), key global
  - DELETE /{doc_id}    → invalida caché analysis + stats al eliminar

Rutas:
  GET  /api/v1/reports/                      → lista documentos procesados
  GET  /api/v1/reports/{doc_id}              → detalle documento + análisis
  GET  /api/v1/reports/{doc_id}/export/excel → descarga .xlsx
  GET  /api/v1/reports/{doc_id}/export/pdf   → descarga .pdf
  GET  /api/v1/reports/{doc_id}/export/json  → descarga .json
  GET  /api/v1/reports/stats/summary         → métricas globales (cacheado)
  GET  /api/v1/reports/cache/info            → diagnóstico del caché Redis
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime

from app.models.database import get_db, Document, DocumentStatus
from app.schemas.document import DocumentOut, DocumentListOut
from app.services.report_generator import generate_excel, generate_pdf
from app.utils.logger import get_logger
from app.core.cache import (
    cache_get,
    cache_set,
    cache_delete,
    cache_invalidate_document,
    cache_key_stats_global,
    cache_info,
)
from app.config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["Reportes"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_doc_or_404(doc_id: str, db: Session) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento '{doc_id}' no encontrado.")
    return doc


def _require_done(doc: Document) -> dict:
    if doc.status != DocumentStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=f"El documento está en estado '{doc.status}'. Solo se puede exportar cuando está 'done'.",
        )
    if not doc.analysis:
        raise HTTPException(status_code=422, detail="El documento no tiene análisis IA disponible.")
    return json.loads(doc.analysis)


def _build_stats(db: Session) -> dict:
    """Calcula las métricas globales desde la base de datos."""
    total = db.query(Document).count()
    done = db.query(Document).filter(Document.status == DocumentStatus.DONE).count()
    failed = db.query(Document).filter(Document.status == DocumentStatus.FAILED).count()
    pending = db.query(Document).filter(Document.status == DocumentStatus.PENDING).count()

    today_start = datetime.combine(date.today(), datetime.min.time())
    processed_today = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.DONE)
        .filter(Document.created_at >= today_start)
        .count()
    )

    docs_done = db.query(Document.analysis).filter(
        Document.status == DocumentStatus.DONE,
        Document.analysis.isnot(None),
    ).all()

    total_entities = 0
    for (analysis_json,) in docs_done:
        try:
            analysis = json.loads(analysis_json)
            entidades = analysis.get("entidades", {})
            total_entities += sum(len(v) for v in entidades.values() if isinstance(v, list))
        except (json.JSONDecodeError, AttributeError):
            continue

    type_counts = (
        db.query(Document.file_type, func.count(Document.id).label("count"))
        .group_by(Document.file_type)
        .all()
    )

    success_rate = round((done / total * 100), 1) if total else 0.0

    return {
        "total_documents": total,
        "done": done,
        "failed": failed,
        "pending": pending,
        "processed_today": processed_today,
        "success_rate": success_rate,
        "total_entities": total_entities,
        "by_file_type": {row.file_type: row.count for row in type_counts},
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=DocumentListOut, summary="Listar documentos procesados")
def list_reports(
    status: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Devuelve los documentos del sistema con filtros opcionales por estado y tipo.
    """
    query = db.query(Document)

    if status:
        try:
            query = query.filter(Document.status == DocumentStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Estado inválido: {status}")

    if file_type:
        query = query.filter(Document.file_type == file_type.lower())

    total = query.count()
    items = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    logger.info(f"List reports → total={total}, returned={len(items)}")
    return {"total": total, "items": items}


@router.get("/stats/summary", summary="Métricas globales del sistema [CACHEADO 5 min]")
async def get_stats(db: Session = Depends(get_db)):
    """
    Métricas agregadas para el panel del dashboard.

    **Bloque 2.2 — Caché:**
    - TTL: 5 minutos (CACHE_TTL_STATS)
    - Key: `docuflow:stats:global`
    - Se invalida automáticamente cuando se elimina un documento.
    - El header `X-Cache` indica HIT o MISS.
    """
    stats_key = cache_key_stats_global()

    # 1. Intentar desde caché
    cached = await cache_get(stats_key)
    if cached is not None:
        logger.info("Cache HIT — /stats/summary")
        # Agregar metadata de caché a la respuesta
        cached["_cache"] = "HIT"
        return cached

    # 2. Calcular desde DB
    logger.info("Cache MISS — calculando /stats/summary desde DB")
    stats = _build_stats(db)

    # 3. Guardar en caché
    await cache_set(stats_key, stats, ttl=settings.CACHE_TTL_STATS)
    logger.info(f"Stats cacheados — TTL={settings.CACHE_TTL_STATS}s")

    stats["_cache"] = "MISS"
    return stats


@router.get("/cache/info", summary="Diagnóstico del caché Redis [admin]")
async def get_cache_info():
    """
    Retorna el estado actual del caché Redis:
    keys activas, memoria usada, TTLs configurados y muestra de keys.

    Útil para debugging y monitoreo.
    """
    info = await cache_info()
    return info


@router.get("/stats/activity", summary="Actividad diaria de documentos")
def get_activity(days: int = 14, db: Session = Depends(get_db)):
    """
    Devuelve la cantidad de documentos creados por día en los últimos N días.
    Usado por el gráfico de actividad en el dashboard frontend.

    Respuesta:
      points: [{date: "YYYY-MM-DD", count: int, label: "dd/MM"}, ...]
      total:  int (suma total del período)
      days:   int (días solicitados)
    """
    from datetime import timedelta, date as date_type
    from sqlalchemy import cast, Date as SADate

    if days < 1:
        days = 1
    if days > 90:
        days = 90

    end_date = date_type.today()
    start_date = end_date - timedelta(days=days - 1)

    # Aggregate counts per day using SQLAlchemy
    rows = (
        db.query(
            cast(Document.created_at, SADate).label("day"),
            func.count(Document.id).label("count"),
        )
        .filter(Document.created_at >= datetime.combine(start_date, datetime.min.time()))
        .group_by(cast(Document.created_at, SADate))
        .order_by(cast(Document.created_at, SADate))
        .all()
    )

    counts_by_day = {str(row.day): row.count for row in rows}

    points = []
    current = start_date
    while current <= end_date:
        day_str = current.strftime("%Y-%m-%d")
        points.append({
            "date": day_str,
            "count": counts_by_day.get(day_str, 0),
            "label": current.strftime("%d/%m"),
        })
        current += timedelta(days=1)

    total = sum(p["count"] for p in points)
    return {"points": points, "total": total, "days": days}


@router.get("/{doc_id}", response_model=DocumentOut, summary="Detalle de documento")
def get_report(doc_id: str, db: Session = Depends(get_db)):
    """Devuelve todos los campos de un documento, incluyendo el análisis IA."""
    return _get_doc_or_404(doc_id, db)


@router.delete("/{doc_id}", status_code=204, summary="Eliminar documento [invalida caché]")
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """
    Elimina un documento de la base de datos.

    **Bloque 2.2 — Invalidación de caché:**
    Al eliminar, se borran automáticamente:
    - `docuflow:analysis:{doc_id}` — análisis IA del documento
    - `docuflow:stats:global` — métricas globales (el conteo cambió)
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Documento '{doc_id}' no encontrado.")

    # Invalidar caché ANTES de eliminar el registro
    await cache_invalidate_document(doc_id)

    db.delete(doc)
    db.commit()
    logger.info(f"Documento eliminado — doc_id={doc_id}")


@router.get("/{doc_id}/export/excel", summary="Exportar análisis a Excel")
def export_excel(doc_id: str, db: Session = Depends(get_db)):
    """Genera y descarga un .xlsx con Resumen, Entidades y Campos clave."""
    doc = _get_doc_or_404(doc_id, db)
    analysis = _require_done(doc)

    doc_data = {
        "filename": doc.filename,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
    }

    xlsx_bytes = generate_excel(doc_data, analysis)
    filename = f"docuflow_{doc.filename.rsplit('.', 1)[0]}.xlsx"

    logger.info(f"Export Excel → doc_id={doc_id}, size={len(xlsx_bytes)}B")
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}/export/pdf", summary="Exportar análisis a PDF")
def export_pdf(doc_id: str, db: Session = Depends(get_db)):
    """Genera y descarga un PDF A4 con resumen ejecutivo y tabla de entidades."""
    doc = _get_doc_or_404(doc_id, db)
    analysis = _require_done(doc)

    doc_data = {
        "filename": doc.filename,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
    }

    pdf_bytes = generate_pdf(doc_data, analysis)
    filename = f"docuflow_{doc.filename.rsplit('.', 1)[0]}.pdf"

    logger.info(f"Export PDF → doc_id={doc_id}, size={len(pdf_bytes)}B")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}/export/json", summary="Exportar análisis a JSON")
def export_json(doc_id: str, db: Session = Depends(get_db)):
    """Devuelve el análisis IA como JSON descargable. Útil para integraciones."""
    doc = _get_doc_or_404(doc_id, db)
    analysis = _require_done(doc)

    payload = {
        "doc_id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "analysis": analysis,
    }

    filename = f"docuflow_{doc.filename.rsplit('.', 1)[0]}.json"
    logger.info(f"Export JSON → doc_id={doc_id}")
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

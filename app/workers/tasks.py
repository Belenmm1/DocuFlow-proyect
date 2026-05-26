"""
app/workers/tasks.py

Bloque 3.2 — Cambios respecto al bloque anterior:
  - Antes del análisis IA se corre DocClassifier.classify().
  - El resultado (categoría + confianza) se guarda en doc.doc_category y
    doc.doc_category_confidence.
  - El prompt especializado se pasa a AIAnalyzer.analyze().

Pipeline completo:
  1. Extracción de texto
  2. Clasificación de tipo de documento   ← NUEVO
  3. Análisis IA con prompt especializado ← MODIFICADO
  4. Persistir todo en DB
"""

import asyncio
import logging

from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.models.database import SessionLocal, Document, DocumentStatus
from app.services.extractor import extract_content
from app.services.ai_analyzer import AIAnalyzer
from app.services.doc_classifier import DocClassifier   # ← Bloque 3.2
from app.services.email_service import (               # ← Bloque 5.2
    send_analysis_complete_email,
    send_analysis_failed_email,
)

logger = get_task_logger(__name__)


class BaseDocumentTask(Task):
    """Base task con DB session manejada correctamente."""
    _db: Session | None = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


def _run_async(coro):
    """Ejecuta una coroutine desde un contexto sincrónico (Celery worker)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    base=BaseDocumentTask,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_document(self, doc_id: int) -> dict:
    """
    Pipeline de procesamiento de un documento:
      1. Extracción de texto
      2. Clasificación automática del tipo (Bloque 3.2)
      3. Análisis IA con prompt especializado (Bloque 3.2)
      4. Persistir resultados
    """
    db = self.db

    # ── Cargar y marcar como processing ──────────────────────────────────────
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id)
        .first()
    )
    if not doc:
        logger.error(f"Document {doc_id} not found")
        raise ValueError(f"Document {doc_id} not found")

    # Pre-cargar owner para poder enviar email al final (Bloque 5.2)
    owner = doc.owner  # acceso lazy antes de que empiece el procesamiento

    doc.status = DocumentStatus.PROCESSING
    db.commit()
    logger.info(f"[task={self.request.id}] Processing doc_id={doc_id}")

    try:
        # ── Paso 1: Extracción ────────────────────────────────────────────────
        extracted = extract_content(doc.file_path, doc.file_type)
        doc.extracted_text = extracted.get("text", "")
        doc.page_count = extracted.get("pages")
        db.commit()
        logger.info(f"[task={self.request.id}] Extracción OK — doc_id={doc_id}")

        # ── Paso 2: Clasificación automática ─────────────────────────────────
        classifier = DocClassifier()
        category, confidence, specialized_prompt = _run_async(
            classifier.classify(doc.extracted_text)
        )

        doc.doc_category = category
        doc.doc_category_confidence = confidence
        db.commit()
        logger.info(
            f"[task={self.request.id}] Clasificación OK — "
            f"doc_id={doc_id} | categoría={category} | confianza={confidence}"
        )

        # ── Paso 3: Análisis IA con prompt especializado ──────────────────────
        analyzer = AIAnalyzer()
        analysis = _run_async(
            analyzer.analyze(
                doc_id=doc_id,
                text=doc.extracted_text,
                system_prompt=specialized_prompt,   # ← prompt dinámico
            )
        )

        doc.summary = analysis.get("resumen") or analysis.get("summary")
        doc.key_entities = analysis.get("entidades") or analysis.get("key_entities")
        doc.sentiment = analysis.get("sentimiento") or analysis.get("sentiment")
        doc.keywords = analysis.get("palabras_clave") or analysis.get("keywords")

        # ── Paso 4: Marcar como done ──────────────────────────────────────────
        doc.status = DocumentStatus.DONE
        db.commit()
        logger.info(
            f"[task={self.request.id}] Pipeline completo — "
            f"doc_id={doc_id} | categoría={category}"
        )

        # ── Paso 5: Notificación email (Bloque 5.2) ───────────────────────────
        if doc.owner and doc.owner.email:
            _run_async(
                send_analysis_complete_email(
                    doc.owner.email,
                    filename=doc.filename,
                    doc_id=doc.id,
                    category=doc.doc_category,
                    summary=doc.summary,
                    keywords=doc.keywords,
                    sentiment=doc.sentiment,
                )
            )

        return {"doc_id": doc_id, "status": "done", "category": category}

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(exc)
            db.commit()
            logger.error(
                f"[task={self.request.id}] Reintentos agotados — "
                f"doc_id={doc_id}: {exc}"
            )
            # Notificación email de fallo (Bloque 5.2)
            if doc.owner and doc.owner.email:
                _run_async(
                    send_analysis_failed_email(
                        doc.owner.email,
                        filename=doc.filename,
                        doc_id=doc.id,
                        error_message=str(exc),
                    )
                )
        else:
            logger.warning(
                f"[task={self.request.id}] Reintento {self.request.retries + 1} — "
                f"doc_id={doc_id}: {exc}"
            )
        raise

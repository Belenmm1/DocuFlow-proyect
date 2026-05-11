import logging
from celery import Task
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.models.database import SessionLocal, Document, DocumentStatus
from app.services.extractor import extract_content
from app.services.ai_analyzer import AIAnalyzer

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


@celery_app.task(
    bind=True,
    base=BaseDocumentTask,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=60,      # 1 min primer reintento
    autoretry_for=(Exception,),
    retry_backoff=True,          # backoff exponencial: 60s, 120s, 240s
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_document(self, doc_id: int) -> dict:
    """
    Tarea principal: extrae texto + analiza con IA.
    El endpoint de upload retorna inmediatamente con status 'pending'
    y esta tarea corre en background.
    """
    db = self.db

    # 1. Cargar documento y marcarlo como "processing"
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        logger.error(f"Document {doc_id} not found")
        raise ValueError(f"Document {doc_id} not found")

    doc.status = DocumentStatus.PROCESSING
    db.commit()
    logger.info(f"[task={self.request.id}] Processing doc_id={doc_id}")

    try:
        # 2. Extracción de texto
        extracted = extract_content(doc.file_path, doc.file_type)
        doc.extracted_text = extracted.get("text", "")
        doc.page_count = extracted.get("pages")
        db.commit()
        logger.info(f"[task={self.request.id}] Extraction done for doc_id={doc_id}")

        # 3. Análisis IA
        import asyncio
        analyzer = AIAnalyzer()
        analysis = asyncio.get_event_loop().run_until_complete(
            analyzer.analyze(doc_id, doc.extracted_text)
        )
        doc.summary = analysis.get("summary")
        doc.key_entities = analysis.get("key_entities")
        doc.sentiment = analysis.get("sentiment")
        doc.keywords = analysis.get("keywords")

        # 4. Marcar como completado
        doc.status = DocumentStatus.DONE
        db.commit()
        logger.info(f"[task={self.request.id}] Analysis done for doc_id={doc_id}")

        return {"doc_id": doc_id, "status": "done"}

    except Exception as exc:
        # Marcar como failed solo en el último reintento
        if self.request.retries >= self.max_retries:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(exc)
            db.commit()
            logger.error(
                f"[task={self.request.id}] All retries exhausted for doc_id={doc_id}: {exc}"
            )
        else:
            logger.warning(
                f"[task={self.request.id}] Retry {self.request.retries + 1} "
                f"for doc_id={doc_id}: {exc}"
            )
        raise  # Celery necesita el raise para manejar reintentos

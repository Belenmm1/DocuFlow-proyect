"""
app/models/database.py

Bloque 2.4 — Migración a PostgreSQL + Alembic.

Cambios respecto al bloque anterior:
  - Engine factory que configura pool de conexiones cuando es PostgreSQL.
  - SQLite sigue funcionando en desarrollo (connect_args solo para SQLite).
  - check_same_thread=False solo se aplica a SQLite.
  - Pool recycle / pre-ping habilitados en producción para evitar conexiones muertas.
"""

import enum

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Enum as SAEnum, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import NullPool

from app.config import settings

Base = declarative_base()

# ─────────────────────────────────────────────────────────────────────────────
# Engine factory
# ─────────────────────────────────────────────────────────────────────────────

def _build_engine():
    url = settings.DATABASE_URL

    if settings.is_postgres:
        # PostgreSQL: connection pool configurado, pre-ping para detectar conexiones caídas
        return create_engine(
            url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=settings.DEBUG,
        )
    else:
        # SQLite (desarrollo local)
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=settings.DEBUG,
        )


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ─────────────────────────────────────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────────────────────────────────────

class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(16), nullable=False, index=True)
    file_size = Column(Integer, nullable=True)

    # Bloque 2.1 — async processing
    status = Column(
        SAEnum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    task_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)

    # Bloque 3.2 — clasificación automática de tipo
    doc_category = Column(String(32), nullable=True, index=True)   # contrato | factura | cv | ...
    doc_category_confidence = Column(String(8), nullable=True)     # alta | media | baja

    extracted_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    key_entities = Column(JSON, nullable=True)
    sentiment = Column(String(32), nullable=True)
    keywords = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now, index=True)
    updated_at = Column(DateTime(timezone=True), default=func.now, onupdate=func.now)

    # Bloque 1.1 — Auth
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User", back_populates="documents")


def create_tables() -> None:
    """
    Crea todas las tablas si no existen.

    IMPORTANTE para Bloque 2.4:
    En producción las migraciones las maneja Alembic (`alembic upgrade head`).
    Esta función se conserva solo para desarrollo rápido con SQLite.
    No la uses en producción con PostgreSQL si ya corriste Alembic.
    """
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

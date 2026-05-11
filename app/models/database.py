import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, Enum as SAEnum, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import create_engine
from app.config import settings

Base = declarative_base()
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)

    # --- campos nuevos 2.1 ---
    status = Column(
        SAEnum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    task_id = Column(String, nullable=True)       # ID de la tarea Celery
    error_message = Column(Text, nullable=True)   # Mensaje si falla
    page_count = Column(Integer, nullable=True)
    # -------------------------

    extracted_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    key_entities = Column(JSON, nullable=True)
    sentiment = Column(String, nullable=True)
    keywords = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relación con User (Bloque 1.1 — Auth JWT)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User", back_populates="documents")


def create_tables() -> None:
    """Crea todas las tablas en la base de datos si no existen."""
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
"""
app/models/backup_log.py — Bloque 7.4

Modelo SQLAlchemy para registrar el historial de backups automáticos.
Permite auditar qué backups se ejecutaron, cuándo, con qué resultado
y cuánto pesaban.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.database import Base


class BackupLog(Base):
    """Registro de cada ejecución del job de backup."""

    __tablename__ = "backup_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Nombre del archivo generado (p.ej. docuflow_20240101_000001.sql.gz)
    filename = Column(String(255), nullable=False, default="")

    # Tamaño en bytes del archivo comprimido
    size_bytes = Column(Integer, nullable=False, default=0)

    # Checksum SHA-256 del archivo (para verificación posterior)
    checksum_sha256 = Column(String(64), nullable=True)

    # Estado: "ok" | "error"
    status = Column(String(20), nullable=False, default="ok")

    # Mensaje de error si status == "error"
    error_message = Column(Text, nullable=True)

    # Cuándo se ejecutó el backup
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<BackupLog id={self.id} "
            f"filename={self.filename!r} "
            f"status={self.status!r} "
            f"created_at={self.created_at}>"
        )

    @property
    def size_mb(self) -> float:
        """Tamaño en MB redondeado a 2 decimales."""
        return round(self.size_bytes / (1024 * 1024), 2)

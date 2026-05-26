"""file_handler.py — Validación segura y guardado de archivos subidos."""
import os
import re
import unicodedata
from pathlib import Path

import magic
from fastapi import HTTPException

from app.utils.logger import get_logger

logger = get_logger(__name__)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Magic bytes por tipo de archivo ──────────────────────────────────────────
# Cada tipo mapea a las firmas MIME que libmagic puede devolver
MAGIC_SIGNATURES: dict[str, list[str]] = {
    "pdf": [
        "application/pdf",
    ],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",          # DOCX es un ZIP — libmagic a veces lo reporta así
    ],
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",          # XLSX también es un ZIP
    ],
}

# Para DOCX/XLSX que libmagic detecta como ZIP, verificamos el contenido interno
OFFICE_ZIP_MARKERS = {
    "docx": b"word/",
    "xlsx": b"xl/",
}


def _detect_mime(content: bytes) -> str:
    """Detecta el MIME real del archivo via libmagic (magic bytes)."""
    return magic.from_buffer(content, mime=True)


def _verify_office_zip(content: bytes, file_type: str) -> bool:
    """
    Para DOCX/XLSX que libmagic reporta como 'application/zip',
    verifica que el ZIP contenga los directorios internos correctos.
    """
    marker = OFFICE_ZIP_MARKERS.get(file_type)
    if not marker:
        return False
    return marker in content[:8192]  # busca en los primeros 8KB


def validate_file(content: bytes, file_type: str, max_mb: int = 20) -> None:
    """
    Valida el archivo por:
    1. Contenido no vacío
    2. Tamaño máximo
    3. Magic bytes (tipo real del archivo)
    """
    # 1. Vacío
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    # 2. Tamaño
    max_bytes = max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande. Máximo permitido: {max_mb} MB.",
        )

    # 3. Magic bytes
    detected_mime = _detect_mime(content)
    allowed_mimes = MAGIC_SIGNATURES.get(file_type, [])

    if detected_mime not in allowed_mimes:
        logger.warning(
            f"Archivo rechazado — tipo declarado: {file_type} | "
            f"MIME detectado: {detected_mime}"
        )
        raise HTTPException(
            status_code=415,
            detail=(
                f"El contenido del archivo no coincide con el tipo declarado. "
                f"Se detectó: {detected_mime}."
            ),
        )

    # Para ZIP que pueden ser DOCX o XLSX, verificamos marcadores internos
    if detected_mime == "application/zip" and file_type in OFFICE_ZIP_MARKERS:
        if not _verify_office_zip(content, file_type):
            logger.warning(
                f"Archivo ZIP rechazado — no contiene estructura de {file_type.upper()}"
            )
            raise HTTPException(
                status_code=415,
                detail=f"El archivo ZIP no tiene la estructura esperada de un {file_type.upper()}.",
            )

    logger.debug(f"Archivo validado OK — tipo: {file_type} | MIME: {detected_mime} | tamaño: {len(content)} bytes")


def sanitize_filename(filename: str) -> str:
    """
    Sanitiza el nombre de archivo:
    - Normaliza unicode (NFKD) y convierte a ASCII
    - Elimina caracteres peligrosos (path traversal, shells, etc.)
    - Colapsa espacios y guiones múltiples
    - Limita a 200 caracteres
    - Garantiza que siempre haya un nombre (nunca devuelve string vacío)
    """
    if not filename:
        return "archivo_sin_nombre"

    # Separar nombre y extensión
    name = Path(filename).stem
    ext = Path(filename).suffix.lower()

    # Normalizar unicode → ASCII
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Eliminar caracteres peligrosos: solo letras, números, guión, guión bajo, punto
    name = re.sub(r"[^\w\s\-.]", "", name)

    # Eliminar path traversal explícito
    name = name.replace("..", "").replace("/", "").replace("\\", "")

    # Colapsar espacios y guiones múltiples
    name = re.sub(r"[\s_]+", "_", name).strip("_.-")
    name = re.sub(r"-+", "-", name)

    # Fallback si quedó vacío
    if not name:
        name = "archivo"

    # Limitar longitud total (nombre + extensión ≤ 200 chars)
    max_name_len = 200 - len(ext)
    name = name[:max_name_len]

    sanitized = f"{name}{ext}"
    return sanitized


def save_upload(content: bytes, doc_id: str, file_type: str) -> str:
    """Guarda el archivo con nombre seguro basado en doc_id."""
    dest = UPLOAD_DIR / f"{doc_id}.{file_type}"
    dest.write_bytes(content)
    logger.debug(f"Archivo guardado: {dest}")
    return str(dest)


class FileHandler:
    """Wrapper de conveniencia para validación + guardado de uploads."""

    async def save(self, file) -> dict:
        """Guarda un UploadFile de FastAPI y retorna metadata."""
        content = await file.read()
        ext = Path(file.filename).suffix.lower().lstrip(".")
        if ext not in ("pdf", "docx", "xlsx"):
            raise HTTPException(status_code=415, detail=f"Extensión no soportada: .{ext}")
        validate_file(content, ext)
        safe_name = sanitize_filename(file.filename)
        import uuid
        uid = str(uuid.uuid4())
        file_path = save_upload(content, uid, ext)
        return {
            "filename":  safe_name,
            "file_path": file_path,
            "file_type": ext,
            "file_size": len(content),
        }

    def save_bytes(self, content: bytes, uid: str, file_type: str) -> str:
        """Guarda bytes directamente (usado por integraciones externas)."""
        return save_upload(content, uid, file_type)

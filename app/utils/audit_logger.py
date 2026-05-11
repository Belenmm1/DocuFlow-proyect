"""audit_logger.py — Logs de auditoría para eventos de seguridad."""
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.utils.logger import get_logger

# Logger separado para auditoría — fácil de redirigir a un archivo o servicio externo
_audit_log = get_logger("docuflow.audit")


class AuditEvent(str, Enum):
    # Autenticación
    USER_REGISTER    = "user.register"
    USER_LOGIN       = "user.login"
    USER_LOGIN_FAIL  = "user.login_fail"

    # Documentos
    DOCUMENT_UPLOAD  = "document.upload"
    DOCUMENT_UPLOAD_REJECTED = "document.upload_rejected"
    DOCUMENT_ANALYZE = "document.analyze"
    DOCUMENT_EXPORT  = "document.export"
    DOCUMENT_DELETE  = "document.delete"
    DOCUMENT_ACCESS_DENIED = "document.access_denied"


def audit(
    event: AuditEvent,
    *,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    ip: Optional[str] = None,
    doc_id: Optional[str] = None,
    filename: Optional[str] = None,
    detail: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Registra un evento de auditoría como JSON estructurado.
    Todos los campos son opcionales excepto `event`.
    """
    record = {
        "audit":      True,
        "event":      event.value,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }

    if user_id:    record["user_id"]    = user_id
    if user_email: record["user_email"] = user_email
    if ip:         record["ip"]         = ip
    if doc_id:     record["doc_id"]     = doc_id
    if filename:   record["filename"]   = filename
    if detail:     record["detail"]     = detail
    if extra:      record.update(extra)

    _audit_log.info(json.dumps(record, ensure_ascii=False))


def get_client_ip(request) -> str:
    """Extrae la IP real del cliente (considera proxies)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

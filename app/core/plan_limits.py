"""
app/core/plan_limits.py

Bloque 6.1 — Límites por plan.

Define los límites de cada plan y expone:
  - PLAN_CONFIG        dict con todos los límites
  - enforce_plan_limit  dependency para usar en endpoints
  - PlanLimitExceeded  excepción HTTPException 429
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.models.user import User, UserPlan


# ─────────────────────────────────────────────────────────────────────────────
# Configuración de cada plan
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlanConfig:
    max_file_size_mb: int          # tamaño máximo por archivo
    max_docs_per_month: Optional[int]  # None = ilimitado
    max_api_keys: int              # claves API propias (Bloque 6.2)
    can_export_pdf: bool
    can_export_excel: bool
    can_use_chat: bool             # RAG / chat con documentos
    can_use_webhooks: bool
    can_use_integrations: bool     # Google Drive / Dropbox
    rate_limit: str                # para slowapi


PLAN_CONFIG: dict[UserPlan, PlanConfig] = {
    UserPlan.FREE: PlanConfig(
        max_file_size_mb=5,
        max_docs_per_month=10,
        max_api_keys=0,
        can_export_pdf=False,
        can_export_excel=True,
        can_use_chat=False,
        can_use_webhooks=False,
        can_use_integrations=False,
        rate_limit="10/minute",
    ),
    UserPlan.PRO: PlanConfig(
        max_file_size_mb=20,
        max_docs_per_month=200,
        max_api_keys=5,
        can_export_pdf=True,
        can_export_excel=True,
        can_use_chat=True,
        can_use_webhooks=True,
        can_use_integrations=True,
        rate_limit="60/minute",
    ),
    UserPlan.ENTERPRISE: PlanConfig(
        max_file_size_mb=100,
        max_docs_per_month=None,  # ilimitado
        max_api_keys=50,
        can_export_pdf=True,
        can_export_excel=True,
        can_use_chat=True,
        can_use_webhooks=True,
        can_use_integrations=True,
        rate_limit="1000/minute",
    ),
}


def get_plan_config(plan: UserPlan) -> PlanConfig:
    return PLAN_CONFIG[plan]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de verificación
# ─────────────────────────────────────────────────────────────────────────────

def _require_feature(user: User, feature: str) -> None:
    """Lanza 403 si el plan del usuario no incluye la feature solicitada."""
    config = get_plan_config(user.plan)
    if not getattr(config, feature, False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Tu plan '{user.plan.value}' no incluye esta funcionalidad. "
                "Actualizá tu plan en /billing/upgrade."
            ),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Dependencies de FastAPI para proteger endpoints por feature
# ─────────────────────────────────────────────────────────────────────────────

def require_chat(current_user: User = Depends(get_current_user)) -> User:
    _require_feature(current_user, "can_use_chat")
    return current_user


def require_pdf_export(current_user: User = Depends(get_current_user)) -> User:
    _require_feature(current_user, "can_export_pdf")
    return current_user


def require_webhooks(current_user: User = Depends(get_current_user)) -> User:
    _require_feature(current_user, "can_use_webhooks")
    return current_user


def require_integrations(current_user: User = Depends(get_current_user)) -> User:
    _require_feature(current_user, "can_use_integrations")
    return current_user


def require_api_keys(current_user: User = Depends(get_current_user)) -> User:
    """Pro/Enterprise pueden generar API keys propias (Bloque 6.2)."""
    config = get_plan_config(current_user.plan)
    if config.max_api_keys == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Las API Keys están disponibles en los planes Pro y Enterprise.",
        )
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# Verificación de cuota mensual de documentos
# ─────────────────────────────────────────────────────────────────────────────

def check_monthly_doc_quota(user: User, db) -> None:
    """
    Verifica que el usuario no haya superado su cuota mensual de documentos.
    Llamar desde el endpoint de upload ANTES de guardar el archivo.
    """
    from datetime import datetime, timezone
    from sqlalchemy import func as sqlfunc
    from app.models.database import Document, DocumentStatus

    config = get_plan_config(user.plan)
    if config.max_docs_per_month is None:
        return  # Enterprise: ilimitado

    # Primer día del mes en curso (UTC)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count = (
        db.query(sqlfunc.count())
        .select_from(Document)
        .filter(
            Document.user_id == user.id,
            Document.created_at >= month_start,
        )
        .scalar()
    )

    if count >= config.max_docs_per_month:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Límite mensual alcanzado: {config.max_docs_per_month} documentos "
                f"para el plan '{user.plan.value}'. "
                "Actualizá tu plan en /billing/upgrade."
            ),
            headers={"Retry-After": "0"},
        )


def check_file_size(user: User, file_size_bytes: int) -> None:
    """Lanza 413 si el archivo supera el límite del plan."""
    config = get_plan_config(user.plan)
    max_bytes = config.max_file_size_mb * 1024 * 1024
    if file_size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Archivo demasiado grande ({file_size_bytes / 1024 / 1024:.1f} MB). "
                f"Límite para plan '{user.plan.value}': {config.max_file_size_mb} MB."
            ),
        )

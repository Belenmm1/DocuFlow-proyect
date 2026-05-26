"""
app/api/v1/routes/admin.py

Bloque 6.3 — Dashboard Admin.

Rutas (todas requieren rol "admin"):
  GET  /admin/stats              → métricas globales (usuarios, docs, MRR)
  GET  /admin/users              → listado de usuarios con filtros
  GET  /admin/users/{user_id}    → detalle de un usuario
  PATCH /admin/users/{user_id}   → cambiar plan / suspender cuenta
  GET  /admin/errors             → log de errores recientes (StripeEvents fallidos + docs failed)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_admin_user
from app.models.api_key import APIKey
from app.models.database import Document, DocumentStatus, get_db
from app.models.subscription import Subscription, SubscriptionStatus, StripeEvent
from app.models.user import User, UserPlan, UserRole
from app.utils.logger import get_logger

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class GlobalStats(BaseModel):
    # Usuarios
    total_users: int
    active_users: int
    users_free: int
    users_pro: int
    users_enterprise: int
    new_users_last_30d: int
    # Documentos
    total_documents: int
    docs_done: int
    docs_failed: int
    docs_last_30d: int
    # Billing
    active_subscriptions: int
    past_due_subscriptions: int
    mrr_usd: float          # Monthly Recurring Revenue estimado


class UserAdminOut(BaseModel):
    id: str
    email: str
    role: UserRole
    plan: UserPlan
    is_active: bool
    created_at: datetime
    total_docs: int
    subscription_status: Optional[str] = None
    stripe_customer_id: Optional[str] = None

    class Config:
        from_attributes = True


class UserPatch(BaseModel):
    plan: Optional[UserPlan] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class ErrorLogEntry(BaseModel):
    source: str          # "stripe_event" | "document"
    id: str
    error: Optional[str]
    created_at: datetime
    detail: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Precios de cada plan en USD/mes (para calcular MRR estimado)
_PLAN_PRICE = {
    UserPlan.FREE: 0.0,
    UserPlan.PRO: 19.0,
    UserPlan.ENTERPRISE: 99.0,
}


def _mrr(db: Session) -> float:
    """MRR estimado: suma precios plan de suscripciones activas."""
    rows = (
        db.query(Subscription.plan, func.count().label("n"))
        .filter(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]))
        .group_by(Subscription.plan)
        .all()
    )
    total = 0.0
    for plan_str, count in rows:
        try:
            plan = UserPlan(plan_str)
        except ValueError:
            continue
        total += _PLAN_PRICE.get(plan, 0.0) * count
    return round(total, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=GlobalStats)
def global_stats(
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Métricas globales del sistema."""
    now = datetime.now(timezone.utc)
    last_30d = now - timedelta(days=30)

    # ── Usuarios ──────────────────────────────────────────────────────────────
    total_users       = db.query(func.count()).select_from(User).scalar()
    active_users      = db.query(func.count()).select_from(User).filter(User.is_active == True).scalar()   # noqa: E712
    users_free        = db.query(func.count()).select_from(User).filter(User.plan == UserPlan.FREE).scalar()
    users_pro         = db.query(func.count()).select_from(User).filter(User.plan == UserPlan.PRO).scalar()
    users_enterprise  = db.query(func.count()).select_from(User).filter(User.plan == UserPlan.ENTERPRISE).scalar()
    new_users_last_30d = (
        db.query(func.count()).select_from(User)
        .filter(User.created_at >= last_30d)
        .scalar()
    )

    # ── Documentos ────────────────────────────────────────────────────────────
    total_documents = db.query(func.count()).select_from(Document).scalar()
    docs_done       = db.query(func.count()).select_from(Document).filter(Document.status == DocumentStatus.DONE).scalar()
    docs_failed     = db.query(func.count()).select_from(Document).filter(Document.status == DocumentStatus.FAILED).scalar()
    docs_last_30d   = (
        db.query(func.count()).select_from(Document)
        .filter(Document.created_at >= last_30d)
        .scalar()
    )

    # ── Billing ───────────────────────────────────────────────────────────────
    active_subs   = (
        db.query(func.count()).select_from(Subscription)
        .filter(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]))
        .scalar()
    )
    past_due_subs = (
        db.query(func.count()).select_from(Subscription)
        .filter(Subscription.status == SubscriptionStatus.PAST_DUE)
        .scalar()
    )

    return GlobalStats(
        total_users=total_users,
        active_users=active_users,
        users_free=users_free,
        users_pro=users_pro,
        users_enterprise=users_enterprise,
        new_users_last_30d=new_users_last_30d,
        total_documents=total_documents,
        docs_done=docs_done,
        docs_failed=docs_failed,
        docs_last_30d=docs_last_30d,
        active_subscriptions=active_subs,
        past_due_subscriptions=past_due_subs,
        mrr_usd=_mrr(db),
    )


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    search: Optional[str] = Query(None, description="Filtrar por email (substring)"),
    plan: Optional[UserPlan] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Listado de usuarios con filtros combinables."""
    q = db.query(User)

    if search:
        q = q.filter(User.email.ilike(f"%{search}%"))
    if plan is not None:
        q = q.filter(User.plan == plan)
    if is_active is not None:
        q = q.filter(User.is_active == is_active)

    users = q.order_by(desc(User.created_at)).offset(offset).limit(limit).all()

    result = []
    for u in users:
        total_docs = db.query(func.count()).select_from(Document).filter(Document.user_id == u.id).scalar()
        sub = db.query(Subscription).filter(Subscription.user_id == u.id).first()
        result.append(UserAdminOut(
            id=u.id,
            email=u.email,
            role=u.role,
            plan=u.plan,
            is_active=u.is_active,
            created_at=u.created_at,
            total_docs=total_docs,
            subscription_status=sub.status.value if sub else None,
            stripe_customer_id=sub.stripe_customer_id if sub else None,
        ))
    return result


@router.get("/users/{user_id}", response_model=UserAdminOut)
def get_user(
    user_id: str,
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Detalle completo de un usuario."""
    u = _get_user_or_404(user_id, db)
    total_docs = db.query(func.count()).select_from(Document).filter(Document.user_id == u.id).scalar()
    sub = db.query(Subscription).filter(Subscription.user_id == u.id).first()

    return UserAdminOut(
        id=u.id,
        email=u.email,
        role=u.role,
        plan=u.plan,
        is_active=u.is_active,
        created_at=u.created_at,
        total_docs=total_docs,
        subscription_status=sub.status.value if sub else None,
        stripe_customer_id=sub.stripe_customer_id if sub else None,
    )


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: str,
    body: UserPatch,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Cambia plan, rol o estado activo de un usuario.
    Si se cambia el plan, también se actualiza la fila de Subscription local
    (no genera cambios en Stripe — eso debe hacerse desde el Dashboard de Stripe).
    """
    u = _get_user_or_404(user_id, db)

    if u.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No podés modificar tu propio usuario desde el panel admin.",
        )

    if body.plan is not None:
        u.plan = body.plan
        # Sincronizar en la tabla subscriptions
        sub = db.query(Subscription).filter(Subscription.user_id == u.id).first()
        if sub:
            sub.plan = body.plan.value
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            # Revocar todas las API Keys activas
            db.query(APIKey).filter(
                APIKey.user_id == u.id,
                APIKey.is_active == True,  # noqa: E712
            ).update({"is_active": False})

    db.commit()
    db.refresh(u)
    logger.info("Admin %s modificó usuario %s | changes=%s", admin.id, u.id, body.model_dump(exclude_none=True))

    total_docs = db.query(func.count()).select_from(Document).filter(Document.user_id == u.id).scalar()
    sub = db.query(Subscription).filter(Subscription.user_id == u.id).first()

    return UserAdminOut(
        id=u.id,
        email=u.email,
        role=u.role,
        plan=u.plan,
        is_active=u.is_active,
        created_at=u.created_at,
        total_docs=total_docs,
        subscription_status=sub.status.value if sub else None,
        stripe_customer_id=sub.stripe_customer_id if sub else None,
    )


@router.get("/errors", response_model=list[ErrorLogEntry])
def error_log(
    limit: int = Query(50, ge=1, le=200),
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Errores recientes del sistema:
      - Eventos de Stripe que fallaron al procesarse
      - Documentos en estado FAILED con su mensaje de error
    """
    entries: list[ErrorLogEntry] = []

    # ── Stripe events fallidos ────────────────────────────────────────────────
    failed_events = (
        db.query(StripeEvent)
        .filter(StripeEvent.processed == False, StripeEvent.error.isnot(None))  # noqa: E712
        .order_by(desc(StripeEvent.created_at))
        .limit(limit)
        .all()
    )
    for ev in failed_events:
        entries.append(ErrorLogEntry(
            source="stripe_event",
            id=ev.id,
            error=ev.error,
            created_at=ev.created_at,
            detail=ev.event_type,
        ))

    # ── Documentos fallidos ───────────────────────────────────────────────────
    failed_docs = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.FAILED)
        .order_by(desc(Document.created_at))
        .limit(limit)
        .all()
    )
    for doc in failed_docs:
        entries.append(ErrorLogEntry(
            source="document",
            id=str(doc.id),
            error=doc.error_message,
            created_at=doc.created_at,
            detail=doc.filename,
        ))

    # Ordenar combinados por fecha descendente
    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_user_or_404(user_id: str, db: Session) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return u


# ─────────────────────────────────────────────────────────────────────────────
# Bloque 7.4 — Endpoints de Backup
# ─────────────────────────────────────────────────────────────────────────────

from typing import List as TypingList
from app.models.backup_log import BackupLog


class BackupLogSchema(BaseModel):
    id: int
    filename: str
    size_bytes: int
    size_mb: float
    checksum_sha256: str | None
    status: str
    error_message: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class BackupTriggerResponse(BaseModel):
    task_id: str
    message: str


@router.get(
    "/backups",
    response_model=TypingList[BackupLogSchema],
    summary="Historial de backups",
)
def list_backups(
    limit: int = Query(default=30, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Lista los últimos backups registrados, ordenados del más reciente al más antiguo.

    - `limit`: máximo de resultados (default 30, máximo 100)
    - `status`: filtrar por "ok" o "error"
    """
    q = db.query(BackupLog).order_by(desc(BackupLog.created_at))
    if status_filter in ("ok", "error"):
        q = q.filter(BackupLog.status == status_filter)
    records = q.limit(limit).all()

    return [
        BackupLogSchema(
            id=r.id,
            filename=r.filename,
            size_bytes=r.size_bytes,
            size_mb=r.size_mb,
            checksum_sha256=r.checksum_sha256,
            status=r.status,
            error_message=r.error_message,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.post(
    "/backups/trigger",
    response_model=BackupTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar backup manual",
)
def trigger_backup(
    _: User = Depends(get_admin_user),
):
    """
    Encola un backup inmediato vía Celery (no espera a las 00:00 UTC).
    Retorna el task_id para polling.
    """
    from app.workers.scheduled_tasks import backup_database

    task = backup_database.apply_async()
    logger.info("Backup manual disparado | task_id=%s", task.id)
    return BackupTriggerResponse(
        task_id=task.id,
        message="Backup encolado. Consultá el estado en /admin/backups en unos minutos.",
    )

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from app.models.user import UserPlan


def get_limit_key(request: Request) -> str:
    """
    Clave de identificación para el rate limiter.
    - Si el request tiene usuario autenticado → usa user_id (límite por usuario)
    - Si no → usa IP (límite por IP, para endpoints públicos como /login)
    """
    user = getattr(request.state, "rate_limit_user", None)
    if user:
        return f"user:{user.id}"
    return get_remote_address(request)


# Instancia global del limiter
limiter = Limiter(key_func=get_limit_key, default_limits=["60/minute"])


# ── Límites por plan ──────────────────────────────────────────────────────────

PLAN_LIMITS = {
    UserPlan.FREE:       "10/minute",
    UserPlan.PRO:        "60/minute",
    UserPlan.ENTERPRISE: "1000/minute",  # efectivamente sin límite práctico
}


def get_plan_limit(request: Request) -> str:
    """Devuelve el string de límite según el plan del usuario autenticado."""
    user = getattr(request.state, "rate_limit_user", None)
    if user:
        return PLAN_LIMITS.get(user.plan, "10/minute")
    return "10/minute"  # sin autenticar → límite más restrictivo


# Límites predefinidos para usar como decoradores
LIMIT_FREE       = "10/minute"
LIMIT_PRO        = "60/minute"
LIMIT_AUTH       = "20/minute"   # para /login y /register (por IP)

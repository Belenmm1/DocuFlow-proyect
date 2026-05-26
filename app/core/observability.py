"""
app/core/observability.py — Bloque 7.3
Inicialización de Sentry y middleware de métricas de tiempo de respuesta.
"""
import time
import os
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Sentry
# ─────────────────────────────────────────────────────────────────────────────

def init_sentry() -> None:
    """
    Inicializa Sentry si SENTRY_DSN está configurado.
    Se llama una sola vez en el lifespan de la app.
    """
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        logger.info("Sentry deshabilitado (SENTRY_DSN no configurado)")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        env = os.getenv("APP_ENV", "development")
        release = os.getenv("APP_VERSION", "unknown")

        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            release=f"docuflow@{release}",
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            # No enviar datos personales sensibles
            send_default_pii=False,
            # Ignorar errores esperados (404, 422 de validación, 401)
            ignore_errors=[],
        )

        logger.info("Sentry inicializado | env=%s release=%s", env, release)

    except ImportError:
        logger.warning(
            "sentry-sdk no instalado. Agregá 'sentry-sdk[fastapi]' al requirements.txt"
        )
    except Exception as exc:
        logger.error("Error al inicializar Sentry | error=%s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware — métricas de tiempo de respuesta
# ─────────────────────────────────────────────────────────────────────────────

# Rutas excluidas del logging de métricas (demasiado verbosas)
_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    Para cada request registra:
      - método, path, status_code
      - duración en ms
      - user_id si existe en el JWT (colocado por RateLimitUserMiddleware)

    En producción el log sale en JSON estructurado gracias a JSONFormatter.
    Además agrega el header X-Response-Time-Ms a la respuesta.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # user_id inyectado por RateLimitUserMiddleware (puede ser None)
        user = getattr(request.state, "rate_limit_user", None)
        user_id = str(user.id) if user else "anonymous"

        log_extra = {
            "http_method":   request.method,
            "http_path":     request.url.path,
            "http_status":   response.status_code,
            "duration_ms":   duration_ms,
            "user_id":       user_id,
            "client_ip":     _get_client_ip(request),
        }

        # nivel WARNING si tarda más de 3 segundos
        level = "warning" if duration_ms > 3000 else "info"
        getattr(logger, level)(
            "%s %s → %s  (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            **log_extra,
        )

        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        return response


def _get_client_ip(request: Request) -> str:
    """Extrae la IP real teniendo en cuenta proxies (X-Forwarded-For)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

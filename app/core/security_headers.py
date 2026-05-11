"""
Middleware de headers de seguridad HTTP.

Agrega los headers recomendados por OWASP en cada respuesta:
  - X-Content-Type-Options
  - X-Frame-Options
  - Strict-Transport-Security (solo en producción)
  - X-XSS-Protection
  - Referrer-Policy
  - Permissions-Policy
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # Evita que el browser "adivine" el Content-Type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Impide que la app sea embebida en iframes (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"

        # Desactiva el filtro XSS legacy (modo bloqueo)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Controla qué información envía el browser en el Referer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Deshabilita features del browser que no necesitamos
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # HSTS solo en producción (en dev/local el certificado no existe)
        if settings.APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response

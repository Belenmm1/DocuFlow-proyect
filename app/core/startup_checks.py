"""
Validación de variables de entorno obligatorias al arrancar la app.

Si alguna variable crítica falta o tiene un valor inseguro conocido,
la aplicación lanza un error en startup antes de aceptar tráfico.
Esto evita deploys silenciosamente rotos.
"""

import sys
from app.config import settings
from app.utils.logger import logger

# Valor placeholder que viene del .env de ejemplo — nunca debe llegar a prod
_INSECURE_JWT_PLACEHOLDERS = {
    "change-me-in-production-use-a-long-random-string",
    "changeme",
    "secret",
    "",
}

_REQUIRED_IN_PRODUCTION = [
    "OPENAI_API_KEY",
    "JWT_SECRET_KEY",
    "DATABASE_URL",
]


def run_startup_checks() -> None:
    """
    Ejecutar todas las validaciones. Llama a esta función en el evento
    startup de FastAPI antes de inicializar la base de datos.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. Variables obligatorias en producción ───────────────────────────────
    if settings.APP_ENV == "production":
        for var in _REQUIRED_IN_PRODUCTION:
            value = getattr(settings, var, "")
            if not value or value.startswith("sk-...") or value == "":
                errors.append(
                    f"[STARTUP] Variable de entorno obligatoria ausente o inválida: {var}"
                )

    # ── 2. JWT_SECRET_KEY no debe ser el placeholder de ejemplo ──────────────
    if settings.JWT_SECRET_KEY.strip() in _INSECURE_JWT_PLACEHOLDERS:
        if settings.APP_ENV == "production":
            errors.append(
                "[STARTUP] JWT_SECRET_KEY tiene un valor inseguro conocido. "
                "Generá uno con: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        else:
            warnings.append(
                "[STARTUP] JWT_SECRET_KEY tiene el valor de ejemplo. "
                "Cambiarlo antes de ir a producción."
            )

    # ── 3. JWT_SECRET_KEY debe tener longitud mínima ──────────────────────────
    if len(settings.JWT_SECRET_KEY.strip()) < 32:
        msg = (
            "[STARTUP] JWT_SECRET_KEY es muy corta (mínimo 32 caracteres). "
            "Generá una con: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        if settings.APP_ENV == "production":
            errors.append(msg)
        else:
            warnings.append(msg)

    # ── 4. DATABASE_URL no debe ser SQLite en producción ─────────────────────
    if settings.APP_ENV == "production" and settings.DATABASE_URL.startswith("sqlite"):
        warnings.append(
            "[STARTUP] DATABASE_URL apunta a SQLite en un entorno de producción. "
            "Se recomienda usar PostgreSQL para deploys productivos."
        )

    # ── 5. CORS_ORIGINS debe estar configurado en producción ─────────────────
    if settings.APP_ENV == "production":
        origins = getattr(settings, "CORS_ORIGINS", "")
        if not origins or origins == "*":
            warnings.append(
                "[STARTUP] CORS_ORIGINS está vacío o configurado como '*' en producción. "
                "Especificá los dominios permitidos en el .env."
            )

    # ── Emitir warnings ───────────────────────────────────────────────────────
    for w in warnings:
        logger.warning(w)

    # ── Abortar si hay errores críticos ───────────────────────────────────────
    if errors:
        for e in errors:
            logger.critical(e)
        logger.critical(
            "DocuFlow no puede arrancar con esta configuración. "
            "Corregí los errores anteriores y reiniciá."
        )
        sys.exit(1)

    logger.info(
        f"[STARTUP] Checks OK — env={settings.APP_ENV}, "
        f"db={'sqlite' if 'sqlite' in settings.DATABASE_URL else 'postgres'}"
    )

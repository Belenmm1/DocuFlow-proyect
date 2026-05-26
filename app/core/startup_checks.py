"""
Validación de variables de entorno obligatorias al arrancar la app.

Si alguna variable crítica falta o tiene un valor inseguro conocido,
la aplicación lanza un error en startup antes de aceptar tráfico.
Esto evita deploys silenciosamente rotos.

Bloque 3.4 — Cambios:
  - La validación de OPENAI_API_KEY ahora es condicional: solo se exige
    si LLM_PROVIDER=openai (o si OLLAMA_ENABLED=false).
  - Se agrega verificación de Ollama: si OLLAMA_ENABLED=true, se intenta
    conectar al servidor y se advierte si el modelo no está instalado.
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

# Variables requeridas en producción (se validan condicionalmente abajo)
_ALWAYS_REQUIRED_IN_PRODUCTION = [
    "JWT_SECRET_KEY",
    "DATABASE_URL",
]


def _check_ollama() -> tuple[list[str], list[str]]:
    """
    Verifica el estado de Ollama si está habilitado.
    Retorna (errores, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.OLLAMA_ENABLED:
        return errors, warnings

    # Import aquí para evitar circular imports en startup
    from app.core.ollama_client import is_ollama_available_sync, list_installed_models
    import asyncio

    logger.info("[STARTUP] OLLAMA_ENABLED=true — verificando servidor...")

    # Verificar que el servidor responde
    available = is_ollama_available_sync()

    if not available:
        warnings.append(
            f"[STARTUP] Ollama habilitado pero el servidor no responde en "
            f"{settings.OLLAMA_BASE_URL}. "
            "Asegurate de que Ollama esté corriendo: `ollama serve`"
        )
        return errors, warnings

    logger.info("[STARTUP] Servidor Ollama disponible en %s", settings.OLLAMA_BASE_URL)

    # Verificar modelos instalados
    try:
        loop = asyncio.new_event_loop()
        installed = loop.run_until_complete(list_installed_models())
        loop.close()
    except Exception as exc:
        warnings.append(f"[STARTUP] No se pudo listar modelos Ollama: {exc}")
        return errors, warnings

    def normalize(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    installed_normalized = {normalize(m) for m in installed}

    for label, model in [
        ("OLLAMA_MODEL", settings.OLLAMA_MODEL),
        ("OLLAMA_MODEL_FAST", settings.OLLAMA_MODEL_FAST),
    ]:
        if model and normalize(model) not in installed_normalized:
            warnings.append(
                f"[STARTUP] Modelo '{model}' ({label}) no está instalado en Ollama. "
                f"Instalalo con: `ollama pull {model}`. "
                f"Modelos disponibles: {', '.join(installed) or 'ninguno'}"
            )
        elif model:
            logger.info("[STARTUP] Modelo Ollama OK: %s (%s)", model, label)

    return errors, warnings


def run_startup_checks() -> None:
    """
    Ejecutar todas las validaciones. Llama a esta función en el evento
    startup de FastAPI antes de inicializar la base de datos.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. Variables siempre obligatorias en producción ───────────────────────
    if settings.APP_ENV == "production":
        for var in _ALWAYS_REQUIRED_IN_PRODUCTION:
            value = getattr(settings, var, "")
            if not value or value.startswith("sk-...") or value == "":
                errors.append(
                    f"[STARTUP] Variable de entorno obligatoria ausente o inválida: {var}"
                )

    # ── 2. Validación de API key según proveedor activo ───────────────────────
    # Bloque 3.4: solo exigir OPENAI_API_KEY si realmente se usa OpenAI
    if settings.APP_ENV == "production" and not settings.OLLAMA_ENABLED:
        provider = settings.LLM_PROVIDER.lower()
        if provider == "openai" and not settings.OPENAI_API_KEY:
            errors.append(
                "[STARTUP] LLM_PROVIDER=openai pero OPENAI_API_KEY no está configurada."
            )
        elif provider == "anthropic" and not settings.ANTHROPIC_API_KEY:
            errors.append(
                "[STARTUP] LLM_PROVIDER=anthropic pero ANTHROPIC_API_KEY no está configurada."
            )
        elif provider == "gemini" and not settings.GOOGLE_API_KEY:
            errors.append(
                "[STARTUP] LLM_PROVIDER=gemini pero GOOGLE_API_KEY no está configurada."
            )

    # ── 3. JWT_SECRET_KEY no debe ser el placeholder de ejemplo ──────────────
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

    # ── 4. JWT_SECRET_KEY debe tener longitud mínima ──────────────────────────
    if len(settings.JWT_SECRET_KEY.strip()) < 32:
        msg = (
            "[STARTUP] JWT_SECRET_KEY es muy corta (mínimo 32 caracteres). "
            "Generá una con: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        if settings.APP_ENV == "production":
            errors.append(msg)
        else:
            warnings.append(msg)

    # ── 5. DATABASE_URL no debe ser SQLite en producción ─────────────────────
    if settings.APP_ENV == "production" and settings.DATABASE_URL.startswith("sqlite"):
        warnings.append(
            "[STARTUP] DATABASE_URL apunta a SQLite en un entorno de producción. "
            "Se recomienda usar PostgreSQL para deploys productivos."
        )

    # ── 6. CORS_ORIGINS debe estar configurado en producción ─────────────────
    if settings.APP_ENV == "production":
        origins = getattr(settings, "CORS_ORIGINS", "")
        if not origins or origins == "*":
            warnings.append(
                "[STARTUP] CORS_ORIGINS está vacío o configurado como '*' en producción. "
                "Especificá los dominios permitidos en el .env."
            )

    # ── 7. Verificación Ollama (Bloque 3.4) ──────────────────────────────────
    ollama_errors, ollama_warnings = _check_ollama()
    errors.extend(ollama_errors)
    warnings.extend(ollama_warnings)

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

    provider_label = "ollama" if settings.OLLAMA_ENABLED else settings.LLM_PROVIDER
    logger.info(
        f"[STARTUP] Checks OK — env={settings.APP_ENV}, "
        f"db={'sqlite' if 'sqlite' in settings.DATABASE_URL else 'postgres'}, "
        f"llm_provider={provider_label}"
    )

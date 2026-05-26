"""
app/core/ollama_client.py — Bloque 3.4

Cliente utilitario para interactuar con el servidor Ollama local.

Responsabilidades:
  1. Verificar disponibilidad del servidor (health check HTTP).
  2. Listar los modelos instalados.
  3. Verificar que un modelo específico esté disponible (y sugerir alternativas).
  4. Hacer pull automático de un modelo si no está descargado (opcional).
  5. Exponer get_ollama_status() para el endpoint /health.

NO instancia modelos LangChain — eso lo hace llm_provider.py.
Este módulo solo habla con la API REST de Ollama.

API REST de Ollama:
  GET  /api/tags           → lista modelos instalados
  POST /api/pull           → descarga un modelo
  POST /api/generate       → inferencia (solo para smoke test)
  GET  /                   → health check básico (retorna 200 si está up)
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Timeout para operaciones de red con Ollama (segundos)
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0


# ── Health check ──────────────────────────────────────────────────────────────

async def is_ollama_available() -> bool:
    """
    Verifica si el servidor Ollama está levantado y responde.

    Returns:
        True si el servidor responde con HTTP 200, False en cualquier otro caso.
    """
    if not settings.OLLAMA_ENABLED:
        return False

    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
            resp = await client.get(settings.OLLAMA_BASE_URL)
            available = resp.status_code == 200
            if available:
                logger.debug("Ollama disponible en %s", settings.OLLAMA_BASE_URL)
            else:
                logger.warning(
                    "Ollama respondió con status %d en %s",
                    resp.status_code, settings.OLLAMA_BASE_URL,
                )
            return available
    except (httpx.ConnectError, httpx.TimeoutException, Exception) as exc:
        logger.warning("Ollama no disponible: %s", exc)
        return False


def is_ollama_available_sync() -> bool:
    """
    Versión síncrona de is_ollama_available(). 
    Útil para startup checks (contexto no-async).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(is_ollama_available())


# ── Listado de modelos ────────────────────────────────────────────────────────

async def list_installed_models() -> list[str]:
    """
    Retorna los nombres de los modelos instalados en Ollama.
    Retorna lista vacía si el servidor no está disponible.
    """
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            logger.debug("Modelos Ollama instalados: %s", models)
            return models
    except Exception as exc:
        logger.warning("No se pudo obtener lista de modelos Ollama: %s", exc)
        return []


async def is_model_available(model_name: str) -> bool:
    """
    Verifica si un modelo específico está instalado en Ollama.

    Normaliza el nombre: 'llama3.2' coincide con 'llama3.2:latest'.
    """
    installed = await list_installed_models()

    # Normalizar: si el modelo no tiene tag, agregar ':latest' para comparar
    def normalize(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    target = normalize(model_name)
    return any(normalize(m) == target for m in installed)


# ── Pull automático de modelo ─────────────────────────────────────────────────

async def pull_model(model_name: str) -> bool:
    """
    Descarga un modelo de Ollama si no está instalado.
    Streaming del progreso; retorna True si termina exitosamente.

    ADVERTENCIA: puede tardar varios minutos para modelos grandes.
    Solo llamar en startup o en background, nunca en el hot path de un request.
    """
    logger.info("Iniciando pull de modelo Ollama: %s", model_name)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=600.0, write=60.0, pool=5.0)
        ) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/pull",
                json={"name": model_name},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        # Log del progreso sin parsear JSON para mayor velocidad
                        logger.debug("pull %s: %s", model_name, line[:120])

        logger.info("Pull completado exitosamente: %s", model_name)
        return True

    except Exception as exc:
        logger.error("Error durante pull de %s: %s", model_name, exc)
        return False


# ── Smoke test de inferencia ──────────────────────────────────────────────────

async def smoke_test(model_name: str) -> bool:
    """
    Ejecuta una inferencia mínima para verificar que el modelo responde.
    Útil para validar la configuración en startup.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=READ_TIMEOUT, write=10.0, pool=5.0)
        ) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "Respondé solo con la palabra: OK",
                    "stream": False,
                    "options": {"num_predict": 5},
                },
            )
            resp.raise_for_status()
            result = resp.json()
            response_text = result.get("response", "").strip()
            logger.info(
                "Smoke test OK — modelo=%s | respuesta='%s'",
                model_name, response_text[:50],
            )
            return True

    except Exception as exc:
        logger.warning("Smoke test fallido para %s: %s", model_name, exc)
        return False


# ── Status completo para /health ─────────────────────────────────────────────

async def get_ollama_status() -> dict[str, Any]:
    """
    Retorna el estado completo de Ollama para el endpoint /health.

    Estructura retornada:
    {
        "enabled": bool,
        "available": bool,          # servidor respondiendo
        "base_url": str,
        "model_main": str,
        "model_fast": str,
        "model_main_installed": bool,
        "model_fast_installed": bool,
        "installed_models": [str, ...]
    }
    """
    if not settings.OLLAMA_ENABLED:
        return {"enabled": False}

    available = await is_ollama_available()

    if not available:
        return {
            "enabled": True,
            "available": False,
            "base_url": settings.OLLAMA_BASE_URL,
            "error": "Servidor Ollama no responde",
        }

    installed = await list_installed_models()

    def normalize(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    def check_installed(model: str) -> bool:
        target = normalize(model)
        return any(normalize(m) == target for m in installed)

    return {
        "enabled": True,
        "available": True,
        "base_url": settings.OLLAMA_BASE_URL,
        "model_main": settings.OLLAMA_MODEL,
        "model_fast": settings.OLLAMA_MODEL_FAST,
        "model_main_installed": check_installed(settings.OLLAMA_MODEL),
        "model_fast_installed": check_installed(settings.OLLAMA_MODEL_FAST),
        "installed_models": installed,
    }

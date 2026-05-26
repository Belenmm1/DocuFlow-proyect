"""
app/api/v1/routes/health.py — Bloque 7.3
Endpoint /health detallado: DB, Redis, OpenAI/LLM, disco.
"""
import asyncio
import os
import shutil
import time
from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["infra"])


# ─────────────────────────────────────────────────────────────────────────────
# Checks individuales
# ─────────────────────────────────────────────────────────────────────────────

def _check_db() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from app.models.database import SessionLocal
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "engine": "postgresql" if settings.is_postgres else "sqlite",
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_redis() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "url": _mask_url(settings.REDIS_URL),
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_llm() -> dict[str, Any]:
    """
    Verifica que el proveedor LLM activo responde.
    Usa una llamada mínima (1 token) para reducir coste/latencia.
    """
    t0 = time.perf_counter()
    provider = settings.LLM_PROVIDER.lower()

    try:
        if provider == "openai":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
        elif provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            await asyncio.to_thread(model.generate_content, "ping")
        elif provider == "ollama":
            import httpx
            async with httpx.AsyncClient(timeout=5) as c:
                resp = await c.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                resp.raise_for_status()
        else:
            return {"status": "unknown", "detail": f"Proveedor '{provider}' no soportado"}

        return {
            "status": "ok",
            "provider": provider,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    except Exception as exc:
        return {
            "status": "error",
            "provider": provider,
            "detail": str(exc),
        }


def _check_disk() -> dict[str, Any]:
    try:
        upload_dir = settings.UPLOAD_DIR or "uploads"
        total, used, free = shutil.disk_usage(upload_dir)
        used_pct = round(used / total * 100, 1) if total else 0
        return {
            "status": "warning" if used_pct > 85 else "ok",
            "path": os.path.abspath(upload_dir),
            "total_gb": round(total / 1e9, 2),
            "used_gb":  round(used  / 1e9, 2),
            "free_gb":  round(free  / 1e9, 2),
            "used_pct": used_pct,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health/detailed", summary="Health check detallado")
async def health_detailed():
    """
    Verifica conectividad de todos los servicios críticos.

    - **db**: PostgreSQL / SQLite
    - **redis**: caché y broker de Celery
    - **llm**: proveedor de IA activo
    - **disk**: espacio en el directorio de uploads

    El campo `status` general es `ok` sólo si todos los componentes
    críticos (db, redis) responden. El LLM y disco pueden estar degradados
    sin impedir el arranque.
    """
    t0 = time.perf_counter()

    # Ejecutar checks en paralelo
    db_result, redis_result, llm_result = await asyncio.gather(
        asyncio.to_thread(_check_db),
        asyncio.to_thread(_check_redis),
        _check_llm(),
    )
    disk_result = _check_disk()

    # Status global: "ok" | "degraded" | "error"
    critical_ok = (
        db_result.get("status") == "ok"
        and redis_result.get("status") == "ok"
    )
    any_error = any(
        r.get("status") == "error"
        for r in [db_result, redis_result, llm_result, disk_result]
    )

    if critical_ok and not any_error:
        overall = "ok"
    elif critical_ok:
        overall = "degraded"
    else:
        overall = "error"

    return {
        "status":  overall,
        "version": settings.APP_VERSION,
        "env":     settings.APP_ENV,
        "checks": {
            "db":    db_result,
            "redis": redis_result,
            "llm":   llm_result,
            "disk":  disk_result,
        },
        "total_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@router.get("/health", summary="Health check rápido")
async def health_simple():
    """Ping rápido — verifica sólo que la app está corriendo."""
    return {"status": "ok", "version": settings.APP_VERSION}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mask_url(url: str) -> str:
    """Oculta contraseñas en URLs para no exponerlas en el health endpoint."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname}"
            if p.port:
                netloc += f":{p.port}"
            p = p._replace(netloc=netloc)
        return urlunparse(p)
    except Exception:
        return "***"

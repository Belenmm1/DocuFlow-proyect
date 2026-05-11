# app/core/cache.py
"""
Módulo de caché Redis para DocuFlow.

Bloque 2.2 — Caché con Redis:
  - Análisis IA por doc_id          → TTL CACHE_TTL_ANALYSIS (1 hora)
  - Métricas /stats/summary         → TTL CACHE_TTL_STATS    (5 minutos)
  - Invalidación al eliminar doc    → cache_invalidate_document(doc_id)
"""
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


# ─── Conexión ─────────────────────────────────────────────────────────────────

async def get_redis() -> aioredis.Redis:
    """Retorna el cliente Redis, creándolo si no existe (patrón singleton)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis():
    """Cierra la conexión Redis limpiamente al apagar la app."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


async def ping_redis() -> bool:
    """Verifica que Redis esté disponible. Usado en /health."""
    try:
        redis = await get_redis()
        return await redis.ping()
    except Exception:
        return False


# ─── Keys ─────────────────────────────────────────────────────────────────────

def cache_key_analysis(doc_id: int) -> str:
    return f"docuflow:analysis:{doc_id}"

def cache_key_stats(user_id: int) -> str:
    return f"docuflow:stats:user:{user_id}"

def cache_key_stats_global() -> str:
    return "docuflow:stats:global"


# ─── CRUD de caché ────────────────────────────────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    try:
        redis = await get_redis()
        value = await redis.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache GET error [{key}]: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int) -> bool:
    try:
        redis = await get_redis()
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
        return True
    except Exception as e:
        logger.warning(f"Cache SET error [{key}]: {e}")
        return False


async def cache_delete(key: str) -> bool:
    try:
        redis = await get_redis()
        await redis.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Cache DELETE error [{key}]: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Elimina keys por patrón usando SCAN (no bloquea Redis en producción)."""
    try:
        redis = await get_redis()
        deleted = 0
        async for key in redis.scan_iter(match=pattern):
            await redis.delete(key)
            deleted += 1
        return deleted
    except Exception as e:
        logger.warning(f"Cache DELETE PATTERN error [{pattern}]: {e}")
        return 0


# ─── Invalidación por documento ───────────────────────────────────────────────

async def cache_invalidate_document(doc_id: int) -> None:
    """
    Invalida TODAS las entradas de caché relacionadas a un documento:
      - Análisis IA del documento
      - Métricas globales de stats (el conteo cambia al eliminar)

    Llamar al eliminar o re-procesar un documento.
    """
    analysis_key = cache_key_analysis(doc_id)
    stats_key = cache_key_stats_global()

    deleted_analysis = await cache_delete(analysis_key)
    deleted_stats = await cache_delete(stats_key)

    logger.info(
        f"Cache invalidado — doc_id={doc_id} | "
        f"analysis={'OK' if deleted_analysis else 'miss'} | "
        f"stats={'OK' if deleted_stats else 'miss'}"
    )


# ─── Info de diagnóstico ──────────────────────────────────────────────────────

async def cache_info() -> dict:
    """
    Retorna metadata del estado del caché.
    Usado por GET /api/v1/cache/info y el endpoint /health.
    """
    try:
        redis = await get_redis()

        docuflow_keys = []
        async for key in redis.scan_iter(match="docuflow:*"):
            docuflow_keys.append(key)

        info = await redis.info("memory")
        used_memory_mb = round(info.get("used_memory", 0) / 1024 / 1024, 2)

        # TTLs de las primeras 20 keys para diagnóstico
        key_ttls = {}
        for key in docuflow_keys[:20]:
            ttl = await redis.ttl(key)
            key_ttls[key] = ttl  # -1 = sin TTL, -2 = no existe

        return {
            "status": "connected",
            "active_keys": len(docuflow_keys),
            "used_memory_mb": used_memory_mb,
            "configured_ttls": {
                "analysis_seconds": settings.CACHE_TTL_ANALYSIS,
                "stats_seconds": settings.CACHE_TTL_STATS,
            },
            "sample_keys": key_ttls,
        }
    except Exception as e:
        logger.error(f"Cache INFO error: {e}")
        return {"status": "error", "error": str(e)}

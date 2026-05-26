"""
app/core/llm_provider.py — Bloque 3.3 / actualizado Bloque 3.4

Abstracción LLMProvider: permite cambiar el proveedor de IA sin tocar
la lógica de negocio.

Proveedores soportados:
  openai     → ChatOpenAI       (default: gpt-4o-mini)
  anthropic  → ChatAnthropic    (default: claude-3-haiku-20240307)
  gemini     → ChatGoogleGenerativeAI (default: gemini-1.5-flash)
  ollama     → ChatOllama       (default: llama3.2) — Bloque 3.4

Bloque 3.4 — Cambios:
  - _resolve_model() ahora lee OLLAMA_MODEL / OLLAMA_MODEL_FAST del config
    cuando el proveedor activo es Ollama (en lugar de usar el string hardcodeado).
  - get_embeddings() nueva función pública: retorna OllamaEmbeddings cuando
    OLLAMA_ENABLED=true, OpenAIEmbeddings en cualquier otro caso.
  - _build_ollama_llm() sin cambios de firma (ya estaba en 3.3).

Configuración via .env:
    LLM_PROVIDER=openai          # openai | anthropic | gemini | ollama
    LLM_MODEL=                   # vacío = usa el default del proveedor
    ANTHROPIC_API_KEY=...
    GOOGLE_API_KEY=...
    OLLAMA_ENABLED=true          # activa modo offline
    OLLAMA_BASE_URL=http://localhost:11434
    OLLAMA_MODEL=llama3.2        # modelo principal local
    OLLAMA_MODEL_FAST=llama3.2   # modelo liviano local
"""

import logging
from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.config import settings

logger = logging.getLogger(__name__)

# ── Defaults por proveedor ────────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "openai": {
        "main": "gpt-4o-mini",
        "fast": "gpt-4o-mini",
    },
    "anthropic": {
        "main": "claude-3-haiku-20240307",
        "fast": "claude-3-haiku-20240307",
    },
    "gemini": {
        "main": "gemini-1.5-flash",
        "fast": "gemini-1.5-flash",
    },
    "ollama": {
        "main": "llama3.2",
        "fast": "llama3.2",
    },
}


def _resolve_model(variant: str) -> str:
    """
    Resuelve el nombre de modelo a usar según proveedor y variante.

    Prioridad de resolución:
      1. Si OLLAMA_ENABLED=true:
           variant='main' → OLLAMA_MODEL
           variant='fast' → OLLAMA_MODEL_FAST
      2. Si LLM_MODEL está seteado (y variante es 'main') → LLM_MODEL
      3. Default del proveedor activo para ese variant.
    """
    provider = settings.LLM_PROVIDER.lower()
    is_ollama = settings.OLLAMA_ENABLED or provider == "ollama"

    # Bloque 3.4: resolución explícita para modelos Ollama desde config
    if is_ollama:
        if variant == "fast":
            return settings.OLLAMA_MODEL_FAST or settings.OLLAMA_MODEL or "llama3.2"
        return settings.OLLAMA_MODEL or "llama3.2"

    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai"])

    if variant == "main" and settings.LLM_MODEL:
        return settings.LLM_MODEL

    return defaults.get(variant, defaults["main"])


def _build_openai_llm(model: str, max_tokens: int, temperature: float) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY no configurada")

    return ChatOpenAI(
        model=model,
        api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _build_anthropic_llm(model: str, max_tokens: int, temperature: float) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY no configurada")

    return ChatAnthropic(
        model=model,
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _build_gemini_llm(model: str, max_tokens: int, temperature: float) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY no configurada")

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def _build_ollama_llm(model: str, max_tokens: int, temperature: float) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    base_url = settings.OLLAMA_BASE_URL

    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        num_predict=max_tokens,
    )


# ── Fábrica central ───────────────────────────────────────────────────────────

def _build_llm(
    variant: str,
    max_tokens: int,
    temperature: float,
) -> BaseChatModel:
    """
    Construye el LLM correcto según LLM_PROVIDER.

    Args:
        variant:    'main' (análisis) o 'fast' (clasificación).
        max_tokens: límite de tokens de salida.
        temperature: temperatura de generación.

    Returns:
        Instancia de BaseChatModel lista para usar.
    """
    provider = settings.LLM_PROVIDER.lower()

    # Modo Ollama: tiene prioridad si OLLAMA_ENABLED=true
    if settings.OLLAMA_ENABLED:
        provider = "ollama"

    model = _resolve_model(variant)

    logger.info(
        "Inicializando LLM | provider=%s | model=%s | variant=%s | max_tokens=%d",
        provider, model, variant, max_tokens,
    )

    builders = {
        "openai":    _build_openai_llm,
        "anthropic": _build_anthropic_llm,
        "gemini":    _build_gemini_llm,
        "ollama":    _build_ollama_llm,
    }

    builder = builders.get(provider)
    if builder is None:
        logger.warning(
            "Proveedor '%s' no reconocido, usando OpenAI como fallback", provider
        )
        builder = _build_openai_llm
        model = PROVIDER_DEFAULTS["openai"][variant]

    return builder(model=model, max_tokens=max_tokens, temperature=temperature)


# ── API pública ───────────────────────────────────────────────────────────────

def get_llm(temperature: float = 0.1, max_tokens: int = 1500) -> BaseChatModel:
    """
    Retorna el modelo principal configurado para análisis de documentos.
    Usa LLM_PROVIDER + LLM_MODEL (o el default del proveedor).
    """
    return _build_llm(variant="main", max_tokens=max_tokens, temperature=temperature)


def get_fast_llm(temperature: float = 0.0, max_tokens: int = 120) -> BaseChatModel:
    """
    Retorna el modelo liviano para tareas rápidas (clasificación, etc.).
    Usa el mismo proveedor pero con parámetros de bajo costo.
    """
    return _build_llm(variant="fast", max_tokens=max_tokens, temperature=temperature)


def get_embeddings():
    """
    Bloque 3.4 — Retorna el modelo de embeddings correcto:
      - OLLAMA_ENABLED=true  → OllamaEmbeddings (local, sin API key)
      - cualquier otro caso  → OpenAIEmbeddings (requiere OPENAI_API_KEY)

    Los embeddings son usados por RAGService para construir los índices FAISS.
    IMPORTANTE: una vez construido un índice con un proveedor, debe usarse
    siempre el mismo proveedor para ese índice (los vectores son incompatibles).
    Si cambiás de proveedor, eliminá los índices existentes en ./vector_stores/.
    """
    if settings.OLLAMA_ENABLED:
        from langchain_ollama import OllamaEmbeddings
        model = settings.OLLAMA_MODEL or "llama3.2"
        logger.info("Embeddings: OllamaEmbeddings | model=%s", model)
        return OllamaEmbeddings(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
        )

    from langchain_openai import OpenAIEmbeddings
    logger.info("Embeddings: OpenAIEmbeddings | model=text-embedding-3-small")
    return OpenAIEmbeddings(
        api_key=settings.OPENAI_API_KEY,
        model="text-embedding-3-small",
    )


def get_provider_info() -> dict[str, Any]:
    """
    Retorna información del proveedor activo. Útil para el endpoint /health.
    """
    provider = settings.LLM_PROVIDER.lower()
    if settings.OLLAMA_ENABLED:
        provider = "ollama"

    return {
        "provider": provider,
        "model_main": _resolve_model("main"),
        "model_fast": _resolve_model("fast"),
        "embeddings": "ollama" if settings.OLLAMA_ENABLED else "openai/text-embedding-3-small",
        "ollama_enabled": settings.OLLAMA_ENABLED,
        "ollama_base_url": settings.OLLAMA_BASE_URL if settings.OLLAMA_ENABLED else None,
    }

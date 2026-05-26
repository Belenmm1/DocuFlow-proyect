"""
app/services/ai_analyzer.py

Bloque 3.3 — Cambios respecto al bloque anterior:
  - Ya no instancia ChatOpenAI directamente.
  - Usa get_llm() de app.core.llm_provider, que resuelve el proveedor
    activo según LLM_PROVIDER en .env (openai / anthropic / gemini / ollama).
  - Todo lo demás (caché, prompt especializado, fallback) permanece igual.
"""

import json
import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.cache import cache_get, cache_set, cache_key_analysis
from app.core.llm_provider import get_llm   # ← Bloque 3.3

logger = logging.getLogger(__name__)

# ── Prompt genérico (fallback cuando no hay clasificación) ────────────────────

GENERIC_SYSTEM_PROMPT = """Sos un asistente experto en análisis de documentos.
Tu tarea es analizar el contenido del documento y extraer información estructurada.

Respondé SIEMPRE en el siguiente formato JSON (sin markdown, solo JSON puro):
{
    "resumen": "resumen ejecutivo del documento en 2-3 oraciones",
    "tipo_documento": "tipo inferido del documento",
    "puntos_clave": ["punto 1", "punto 2", "punto 3"],
    "entidades": {
        "personas": ["nombre1", "nombre2"],
        "organizaciones": ["org1", "org2"],
        "fechas": ["fecha1", "fecha2"],
        "montos": ["monto1", "monto2"]
    },
    "sentimiento": "positivo | negativo | neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3", "kw4", "kw5"]
}"""


class AIAnalyzer:
    def __init__(self):
        # Bloque 3.3: el proveedor se resuelve desde .env en tiempo de instanciación
        self.llm = get_llm(temperature=0.1, max_tokens=1500)

    async def analyze(
        self,
        doc_id: int,
        text: str,
        system_prompt: Optional[str] = None,   # ← Bloque 3.2: prompt especializado
    ) -> Dict[str, Any]:
        """
        Analiza el texto del documento.

        Args:
            doc_id:        ID del documento (cache key).
            text:          Texto extraído del documento.
            system_prompt: Prompt especializado del DocClassifier (Bloque 3.2).
                           Si es None, usa el prompt genérico.

        Returns:
            Dict con el análisis estructurado.
        """
        key = cache_key_analysis(doc_id)

        # 1. Caché — si ya existe no re-analizar
        cached = await cache_get(key)
        if cached is not None:
            logger.info(f"Cache HIT — análisis doc_id={doc_id}")
            return cached

        # 2. Generar con IA
        logger.info(f"Cache MISS — generando análisis doc_id={doc_id}")
        result = await self._run_analysis(text, system_prompt=system_prompt)

        # 3. Cachear resultado
        await cache_set(key, result, ttl=settings.CACHE_TTL_ANALYSIS)
        logger.info(f"Análisis cacheado — doc_id={doc_id}")

        return result

    async def _run_analysis(
        self,
        text: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta el análisis contra la API de OpenAI usando el prompt recibido.
        Trunca el texto si supera el límite seguro de tokens.
        """
        max_chars = 12_000
        if len(text) > max_chars:
            logger.warning(
                f"Texto truncado de {len(text)} a {max_chars} chars para análisis"
            )
            text = text[:max_chars] + "\n\n[... texto truncado ...]"

        prompt = system_prompt or GENERIC_SYSTEM_PROMPT

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Analizá el siguiente documento:\n\n{text}"),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            raw_output = response.content.strip()

            # Limpiar markdown si el modelo lo agrega de todas formas
            cleaned = raw_output
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            return json.loads(cleaned)

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON del análisis IA: {e}")
            return self._fallback_result()

        except Exception as e:
            logger.error(f"Error en análisis IA: {e}", exc_info=True)
            raise

    def _fallback_result(self) -> Dict[str, Any]:
        return {
            "resumen": "No se pudo generar el resumen automáticamente.",
            "tipo_documento": "desconocido",
            "puntos_clave": [],
            "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
            "sentimiento": "neutro",
            "idioma": "es",
            "palabras_clave": [],
        }

    async def analyze_without_cache(self, text: str) -> Dict[str, Any]:
        """Análisis directo sin caché. Útil para re-procesar o en tests."""
        return await self._run_analysis(text)

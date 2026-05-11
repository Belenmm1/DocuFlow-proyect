# app/services/ai_analyzer.py
import logging
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from app.config import settings
from app.core.cache import cache_get, cache_set, cache_key_analysis

logger = logging.getLogger(__name__)


ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """Sos un asistente experto en análisis de documentos. 
Tu tarea es analizar el contenido del documento y extraer información estructurada.

Respondé SIEMPRE en el siguiente formato JSON (sin markdown, solo JSON puro):
{{
    "resumen": "resumen ejecutivo del documento en 2-3 oraciones",
    "tipo_documento": "tipo inferido del documento",
    "puntos_clave": ["punto 1", "punto 2", "punto 3"],
    "entidades": {{
        "personas": ["nombre1", "nombre2"],
        "organizaciones": ["org1", "org2"],
        "fechas": ["fecha1", "fecha2"],
        "montos": ["monto1", "monto2"]
    }},
    "sentimiento": "positivo | negativo | neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3", "kw4", "kw5"]
}}""",
    ),
    (
        "human",
        "Analizá el siguiente documento:\n\n{text}",
    ),
])


class AIAnalyzer:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,          # e.g. "gpt-4o-mini"
            api_key=settings.OPENAI_API_KEY,
            temperature=0.1,
            max_tokens=1500,
        )
        self.chain = (
            {"text": RunnablePassthrough()}
            | ANALYSIS_PROMPT
            | self.llm
            | StrOutputParser()
        )

    async def analyze(self, doc_id: int, text: str) -> Dict[str, Any]:
        """
        Analiza el texto del documento con GPT-4o-mini.
        Retorna el resultado desde caché si existe; si no, lo genera y cachea.

        Args:
            doc_id: ID del documento en base de datos (usado como cache key).
            text:   Texto extraído del documento.

        Returns:
            Dict con el análisis estructurado.
        """
        key = cache_key_analysis(doc_id)

        # 1. Intentar desde caché
        cached = await cache_get(key)
        if cached is not None:
            logger.info(f"Cache HIT — análisis doc_id={doc_id}")
            return cached

        # 2. Generar con IA
        logger.info(f"Cache MISS — generando análisis doc_id={doc_id}")
        result = await self._run_analysis(text)

        # 3. Guardar en caché (TTL 1 hora por defecto)
        await cache_set(key, result, ttl=settings.CACHE_TTL_ANALYSIS)
        logger.info(f"Análisis cacheado — doc_id={doc_id}")

        return result

    async def _run_analysis(self, text: str) -> Dict[str, Any]:
        """
        Ejecuta el análisis real contra la API de OpenAI.
        Trunca el texto si supera el límite seguro de tokens.
        """
        import json

        # Truncar texto largo para no exceder context window
        max_chars = 12_000
        if len(text) > max_chars:
            logger.warning(
                f"Texto truncado de {len(text)} a {max_chars} caracteres para análisis"
            )
            text = text[:max_chars] + "\n\n[... texto truncado ...]"

        try:
            raw_output = await self.chain.ainvoke(text)

            # Limpiar posibles bloques markdown que el modelo agregue igual
            cleaned = raw_output.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON del análisis IA: {e}")
            logger.debug(f"Output crudo: {raw_output}")
            # Retornar estructura mínima para no romper el flujo
            return self._fallback_result(text)

        except Exception as e:
            logger.error(f"Error en análisis IA: {e}", exc_info=True)
            raise

    def _fallback_result(self, text: str) -> Dict[str, Any]:
        """Resultado mínimo cuando el parsing del JSON falla."""
        return {
            "resumen": "No se pudo generar el resumen automáticamente.",
            "tipo_documento": "desconocido",
            "puntos_clave": [],
            "entidades": {
                "personas": [],
                "organizaciones": [],
                "fechas": [],
                "montos": [],
            },
            "sentimiento": "neutro",
            "idioma": "es",
            "palabras_clave": [],
        }

    async def analyze_without_cache(self, text: str) -> Dict[str, Any]:
        """
        Análisis directo sin caché. Útil para re-procesar documentos
        o en contextos donde no hay doc_id disponible.
        """
        return await self._run_analysis(text)
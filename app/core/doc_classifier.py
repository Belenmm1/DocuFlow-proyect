"""
app/services/doc_classifier.py — Bloque 3.2 / actualizado Bloque 3.3

Bloque 3.3 — Cambios:
  - Ya no instancia ChatOpenAI directamente.
  - Usa get_fast_llm() de app.core.llm_provider para clasificación rápida.
    El modelo liviano de cada proveedor se configura en .env.
"""

import json
import logging
from typing import Any, Dict, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.llm_provider import get_fast_llm   # ← Bloque 3.3

logger = logging.getLogger(__name__)

# ── Categorías válidas ─────────────────────────────────────────────────────────

VALID_CATEGORIES = {
    "contrato",
    "factura",
    "informe",
    "cv",
    "resolucion",
    "presentacion",
    "academico",
    "legal",
    "medico",
    "otro",
}

# ── Prompt de clasificación (liviano, rápido) ─────────────────────────────────

CLASSIFICATION_SYSTEM = """Sos un clasificador de documentos. Tu única tarea es identificar
el tipo de documento y responder SOLO con un JSON, sin markdown, sin explicaciones.

Categorías disponibles:
  contrato     → contratos, acuerdos, convenios, términos y condiciones
  factura      → facturas, recibos, notas de débito/crédito, comprobantes fiscales
  informe      → reportes, informes técnicos, memorandos, actas de reunión
  cv           → currículums vitae, perfiles profesionales, hojas de vida
  resolucion   → resoluciones, decretos, ordenanzas, disposiciones administrativas
  presentacion → presentaciones, propuestas comerciales, pitches de negocio
  academico    → tesis, papers, artículos científicos, trabajos universitarios
  legal        → escrituras, poderes notariales, demandas, sentencias judiciales
  medico       → historias clínicas, estudios médicos, recetas, informes clínicos
  otro         → cualquier documento que no encaje en las categorías anteriores

Formato de respuesta obligatorio:
{"categoria": "<una de las categorías de arriba>", "confianza": "<alta|media|baja>", "razon": "<una oración breve>"}"""

# ── Prompts especializados por categoría ──────────────────────────────────────

SPECIALIZED_PROMPTS: Dict[str, str] = {

    "contrato": """Sos un abogado experto en análisis contractual.
Analizá el contrato y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "descripción del objeto del contrato en 2-3 oraciones",
    "tipo_documento": "contrato",
    "partes": ["parte 1", "parte 2"],
    "objeto": "objeto principal del contrato",
    "fecha_inicio": "fecha o null",
    "fecha_fin": "fecha o null",
    "monto": "valor económico o null",
    "obligaciones_clave": ["obligación 1", "obligación 2"],
    "clausulas_importantes": ["cláusula rescisión", "penalidades", etc],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positivo | negativo | neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "factura": """Sos un contador experto en documentos fiscales.
Analizá la factura y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "descripción de la transacción en 1-2 oraciones",
    "tipo_documento": "factura",
    "emisor": "nombre del emisor",
    "receptor": "nombre del receptor",
    "numero_factura": "número o null",
    "fecha_emision": "fecha o null",
    "fecha_vencimiento": "fecha o null",
    "subtotal": "monto sin impuestos o null",
    "impuestos": "monto de impuestos o null",
    "total": "monto total o null",
    "moneda": "ARS | USD | EUR | otra",
    "items": [{"descripcion": "...", "cantidad": "...", "precio": "..."}],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "informe": """Sos un analista experto en informes corporativos.
Analizá el informe y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "síntesis ejecutiva en 2-3 oraciones",
    "tipo_documento": "informe",
    "titulo": "título del informe",
    "autor": "autor o área responsable o null",
    "fecha": "fecha del informe o null",
    "puntos_clave": ["punto 1", "punto 2", "punto 3"],
    "conclusiones": ["conclusión 1", "conclusión 2"],
    "recomendaciones": ["recomendación 1"],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positivo | negativo | neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "cv": """Sos un recruiter experto en análisis de perfiles profesionales.
Analizá el CV y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "perfil profesional en 2-3 oraciones",
    "tipo_documento": "cv",
    "nombre": "nombre completo o null",
    "email": "email o null",
    "telefono": "teléfono o null",
    "ubicacion": "ciudad/país o null",
    "titulo_actual": "cargo o título más reciente",
    "experiencia_anos": "años estimados de experiencia o null",
    "habilidades_tecnicas": ["skill 1", "skill 2"],
    "habilidades_blandas": ["habilidad 1"],
    "idiomas": ["idioma 1", "idioma 2"],
    "educacion": [{"titulo": "...", "institucion": "...", "ano": "..."}],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positivo",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "resolucion": """Sos un experto en derecho administrativo.
Analizá la resolución y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "síntesis de la resolución en 2-3 oraciones",
    "tipo_documento": "resolucion",
    "numero": "número de la resolución o null",
    "organismo": "organismo que la emite o null",
    "fecha": "fecha de emisión o null",
    "objeto": "qué se resuelve",
    "considerandos": ["considerando 1", "considerando 2"],
    "articulos_clave": ["artículo 1: ...", "artículo 2: ..."],
    "destinatarios": ["destinatario 1"],
    "vigencia": "fecha de vigencia o null",
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "presentacion": """Sos un consultor experto en estrategia de negocios.
Analizá la presentación y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "propuesta o mensaje central en 2-3 oraciones",
    "tipo_documento": "presentacion",
    "titulo": "título de la presentación",
    "empresa": "empresa o autor o null",
    "propuesta_valor": "propuesta de valor principal",
    "puntos_clave": ["punto 1", "punto 2", "punto 3"],
    "audiencia_objetivo": "a quién va dirigida",
    "llamada_accion": "qué se le pide al receptor o null",
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positivo | neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "academico": """Sos un académico experto en investigación científica.
Analizá el documento académico y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "abstract o síntesis en 2-3 oraciones",
    "tipo_documento": "academico",
    "titulo": "título del trabajo",
    "autores": ["autor 1", "autor 2"],
    "institucion": "institución o null",
    "ano": "año de publicación o null",
    "area_conocimiento": "disciplina o campo de estudio",
    "hipotesis": "hipótesis o pregunta de investigación o null",
    "metodologia": "metodología utilizada o null",
    "conclusiones": ["conclusión 1", "conclusión 2"],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "legal": """Sos un abogado especialista en documentos notariales y judiciales.
Analizá el documento legal y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "síntesis del documento en 2-3 oraciones",
    "tipo_documento": "legal",
    "tipo_acto": "escritura | poder | demanda | sentencia | otro",
    "partes": ["parte 1", "parte 2"],
    "notario_juez": "nombre o null",
    "fecha": "fecha o null",
    "jurisdiccion": "jurisdicción o null",
    "objeto": "qué se instrumenta o dispone",
    "clausulas_importantes": ["cláusula 1"],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "medico": """Sos un médico experto en documentación clínica.
Analizá el documento médico y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "síntesis clínica en 2-3 oraciones",
    "tipo_documento": "medico",
    "tipo_documento_medico": "historia_clinica | estudio | receta | informe | otro",
    "paciente": "nombre o 'anonimizado'",
    "medico": "nombre del profesional o null",
    "fecha": "fecha o null",
    "diagnostico": "diagnóstico principal o null",
    "tratamiento": "tratamiento indicado o null",
    "medicamentos": ["medicamento 1", "medicamento 2"],
    "estudios_solicitados": ["estudio 1"],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "otro": """Sos un asistente experto en análisis de documentos.
Analizá el documento y respondé SOLO con este JSON (sin markdown):
{
    "resumen": "resumen ejecutivo en 2-3 oraciones",
    "tipo_documento": "otro",
    "puntos_clave": ["punto 1", "punto 2", "punto 3"],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positivo | negativo | neutro",
    "idioma": "es | en | otro",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",
}


# ── Servicio ──────────────────────────────────────────────────────────────────

class DocClassifier:
    """
    Clasifica un documento en una categoría y retorna el prompt especializado.

    Uso típico (en tasks.py):
        classifier = DocClassifier()
        category, confidence, prompt = await classifier.classify(text)
        # usar prompt en el análisis principal
    """

    def __init__(self):
        # Bloque 3.3: usa el modelo liviano del proveedor activo
        self.llm_fast = get_fast_llm(temperature=0.0, max_tokens=120)

    async def classify(self, text: str) -> Tuple[str, str, str]:
        """
        Clasifica el documento.

        Args:
            text: Texto completo extraído. Se usan solo los primeros 2000 chars.

        Returns:
            Tuple (categoria, confianza, prompt_especializado)
            donde categoria ∈ VALID_CATEGORIES, confianza ∈ {alta, media, baja}
        """
        # Solo los primeros 2000 chars son suficientes para clasificar
        sample = text[:2000].strip()

        messages = [
            SystemMessage(content=CLASSIFICATION_SYSTEM),
            HumanMessage(content=f"Clasificá este documento:\n\n{sample}"),
        ]

        try:
            response = await self.llm_fast.ainvoke(messages)
            raw = response.content.strip()

            # Limpiar markdown si el modelo lo agrega
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)
            category = result.get("categoria", "otro").lower().strip()
            confidence = result.get("confianza", "baja").lower().strip()
            reason = result.get("razon", "")

            # Validar categoría
            if category not in VALID_CATEGORIES:
                logger.warning(
                    f"Categoría inválida recibida: '{category}' → fallback a 'otro'"
                )
                category = "otro"

            logger.info(
                f"Documento clasificado como '{category}' "
                f"(confianza={confidence}) — {reason}"
            )

            return category, confidence, SPECIALIZED_PROMPTS[category]

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error en clasificación: {e} — usando categoría 'otro'")
            return "otro", "baja", SPECIALIZED_PROMPTS["otro"]

    def get_prompt_for_category(self, category: str) -> str:
        """Retorna el prompt especializado para una categoría conocida."""
        return SPECIALIZED_PROMPTS.get(category, SPECIALIZED_PROMPTS["otro"])

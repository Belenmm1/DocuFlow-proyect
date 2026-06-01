"""
app/services/doc_classifier.py — Bloque 3.2 + Mejoras v2.0

Clasificador automático de tipo de documento.

Mejoras v2.0:
  - Usa get_fast_llm() / get_llm() en lugar de ChatOpenAI hardcodeado
    → ahora funciona con cualquier LLM_PROVIDER (openai, anthropic, gemini, ollama)
  - Prompts especializados enriquecidos con campos adicionales por categoría
  - Soporte multiidioma: si idioma=="en" usa SPECIALIZED_PROMPTS_EN
  - max_tokens de análisis aumentado a 2500
"""

import json
import logging
from typing import Any, Dict, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.llm_provider import get_fast_llm, get_llm

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
{"categoria": "<una de las categorías de arriba>", "confianza": "<alta|media|baja>", "razon": "<una oración breve>", "idioma": "<es|en|otro>"}"""

# ── Prompts especializados por categoría (Español) ────────────────────────────

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
    "clausulas_importantes": ["cláusula rescisión", "penalidades"],
    "riesgos_identificados": ["cláusula abusiva X", "penalidad excesiva Y"],
    "jurisdiccion": "jurisdicción aplicable o null",
    "ley_aplicable": "ley o código aplicable o null",
    "renovacion_automatica": true,
    "rescision_anticipada": "condiciones o null",
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
    "condiciones_pago": "contado | 30 días | 60 días | otro",
    "estado_pago": "pagado | pendiente | vencido | null",
    "numero_orden_compra": "número o null",
    "cuit_emisor": "CUIT/RUC o null",
    "cuit_receptor": "CUIT/RUC o null",
    "alertas": ["item con precio inusual", "fecha vencida"],
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
    "nivel_senioridad": "junior | semi-senior | senior | lead | gerencial",
    "disponibilidad": "inmediata | 15 días | 30 días | null",
    "pretension_salarial": "monto o null",
    "ultima_empresa": "nombre o null",
    "score_perfil": 7,
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
    "tipo_trabajo": "tesis | paper | tesina | monografia | otro",
    "nivel": "grado | posgrado | doctorado | investigacion",
    "hipotesis": "hipótesis o pregunta de investigación o null",
    "metodologia": "metodología utilizada o null",
    "referencias_count": 45,
    "aporte_original": "descripción del aporte original al campo",
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
    "alergias": ["alergia 1"],
    "antecedentes": ["antecedente 1"],
    "estudios_solicitados": ["estudio 1"],
    "proxima_consulta": "fecha o null",
    "urgencia": "alta | media | baja | null",
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

# ── Prompts especializados por categoría (English) ────────────────────────────

SPECIALIZED_PROMPTS_EN: Dict[str, str] = {

    "contrato": """You are an expert contract analysis lawyer.
Analyze the contract and respond ONLY with this JSON (no markdown):
{
    "resumen": "description of the contract object in 2-3 sentences",
    "tipo_documento": "contrato",
    "partes": ["party 1", "party 2"],
    "objeto": "main purpose of the contract",
    "fecha_inicio": "date or null",
    "fecha_fin": "date or null",
    "monto": "economic value or null",
    "obligaciones_clave": ["obligation 1", "obligation 2"],
    "clausulas_importantes": ["termination clause", "penalties"],
    "riesgos_identificados": ["abusive clause X", "excessive penalty Y"],
    "jurisdiccion": "applicable jurisdiction or null",
    "ley_aplicable": "applicable law or code or null",
    "renovacion_automatica": true,
    "rescision_anticipada": "conditions or null",
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positive | negative | neutral",
    "idioma": "en",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "factura": """You are an expert accountant in fiscal documents.
Analyze the invoice and respond ONLY with this JSON (no markdown):
{
    "resumen": "description of the transaction in 1-2 sentences",
    "tipo_documento": "factura",
    "emisor": "issuer name",
    "receptor": "recipient name",
    "numero_factura": "number or null",
    "fecha_emision": "date or null",
    "fecha_vencimiento": "due date or null",
    "subtotal": "amount without taxes or null",
    "impuestos": "tax amount or null",
    "total": "total amount or null",
    "moneda": "ARS | USD | EUR | other",
    "condiciones_pago": "cash | 30 days | 60 days | other",
    "estado_pago": "paid | pending | overdue | null",
    "numero_orden_compra": "number or null",
    "cuit_emisor": "TAX ID or null",
    "cuit_receptor": "TAX ID or null",
    "alertas": ["unusual item price", "overdue date"],
    "items": [{"descripcion": "...", "cantidad": "...", "precio": "..."}],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutral",
    "idioma": "en",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "cv": """You are an expert recruiter in professional profile analysis.
Analyze the CV and respond ONLY with this JSON (no markdown):
{
    "resumen": "professional profile in 2-3 sentences",
    "tipo_documento": "cv",
    "nombre": "full name or null",
    "email": "email or null",
    "telefono": "phone or null",
    "ubicacion": "city/country or null",
    "titulo_actual": "most recent role or title",
    "experiencia_anos": "estimated years of experience or null",
    "nivel_senioridad": "junior | mid | senior | lead | manager",
    "disponibilidad": "immediate | 2 weeks | 1 month | null",
    "pretension_salarial": "amount or null",
    "ultima_empresa": "name or null",
    "score_perfil": 7,
    "habilidades_tecnicas": ["skill 1", "skill 2"],
    "habilidades_blandas": ["soft skill 1"],
    "idiomas": ["language 1", "language 2"],
    "educacion": [{"titulo": "...", "institucion": "...", "ano": "..."}],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "positive",
    "idioma": "en",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "medico": """You are an expert physician in clinical documentation.
Analyze the medical document and respond ONLY with this JSON (no markdown):
{
    "resumen": "clinical summary in 2-3 sentences",
    "tipo_documento": "medico",
    "tipo_documento_medico": "medical_record | study | prescription | report | other",
    "paciente": "name or 'anonymized'",
    "medico": "professional name or null",
    "fecha": "date or null",
    "diagnostico": "main diagnosis or null",
    "tratamiento": "indicated treatment or null",
    "medicamentos": ["medication 1", "medication 2"],
    "alergias": ["allergy 1"],
    "antecedentes": ["background 1"],
    "estudios_solicitados": ["study 1"],
    "proxima_consulta": "date or null",
    "urgencia": "high | medium | low | null",
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutral",
    "idioma": "en",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",

    "academico": """You are an academic expert in scientific research.
Analyze the academic document and respond ONLY with this JSON (no markdown):
{
    "resumen": "abstract or synthesis in 2-3 sentences",
    "tipo_documento": "academico",
    "titulo": "work title",
    "autores": ["author 1", "author 2"],
    "institucion": "institution or null",
    "ano": "publication year or null",
    "area_conocimiento": "discipline or field of study",
    "tipo_trabajo": "thesis | paper | dissertation | monograph | other",
    "nivel": "undergraduate | graduate | doctoral | research",
    "hipotesis": "hypothesis or research question or null",
    "metodologia": "methodology used or null",
    "referencias_count": 45,
    "aporte_original": "description of the original contribution to the field",
    "conclusiones": ["conclusion 1", "conclusion 2"],
    "entidades": {"personas": [], "organizaciones": [], "fechas": [], "montos": []},
    "sentimiento": "neutral",
    "idioma": "en",
    "palabras_clave": ["kw1", "kw2", "kw3"]
}""",
}

# Fill in English prompts with Spanish fallback for categories not yet translated
for cat, prompt in SPECIALIZED_PROMPTS.items():
    if cat not in SPECIALIZED_PROMPTS_EN:
        SPECIALIZED_PROMPTS_EN[cat] = prompt


# ── Servicio ──────────────────────────────────────────────────────────────────

class DocClassifier:
    """
    Clasifica un documento en una categoría y retorna el prompt especializado.

    Mejoras v2.0:
      - Usa get_fast_llm() del llm_provider → compatible con todos los proveedores
      - Detecta idioma en clasificación y usa prompts en el idioma del documento
    """

    def __init__(self):
        # CORRECCIÓN: usar get_fast_llm() en lugar de ChatOpenAI hardcodeado
        # → funciona con openai, anthropic, gemini y ollama según .env
        self.llm_fast = get_fast_llm(temperature=0.0, max_tokens=150)

    async def classify(self, text: str) -> Tuple[str, str, str]:
        """
        Clasifica el documento.

        Args:
            text: Texto completo extraído. Se usan solo los primeros 2000 chars.

        Returns:
            Tuple (categoria, confianza, prompt_especializado)
        """
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
            idioma = result.get("idioma", "es").lower().strip()

            # Validar categoría
            if category not in VALID_CATEGORIES:
                logger.warning(
                    f"Categoría inválida recibida: '{category}' → fallback a 'otro'"
                )
                category = "otro"

            logger.info(
                f"Documento clasificado como '{category}' "
                f"(confianza={confidence}, idioma={idioma}) — {reason}"
            )

            # Seleccionar prompt en el idioma del documento
            if idioma == "en":
                prompt = SPECIALIZED_PROMPTS_EN.get(category, SPECIALIZED_PROMPTS_EN["otro"])
            else:
                prompt = SPECIALIZED_PROMPTS.get(category, SPECIALIZED_PROMPTS["otro"])

            return category, confidence, prompt

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error en clasificación: {e} — usando categoría 'otro'")
            return "otro", "baja", SPECIALIZED_PROMPTS["otro"]

    def get_prompt_for_category(self, category: str, idioma: str = "es") -> str:
        """Retorna el prompt especializado para una categoría y idioma conocidos."""
        if idioma == "en":
            return SPECIALIZED_PROMPTS_EN.get(category, SPECIALIZED_PROMPTS_EN["otro"])
        return SPECIALIZED_PROMPTS.get(category, SPECIALIZED_PROMPTS["otro"])

"""
extractor.py — Extrae texto y metadata de PDF, DOCX y XLSX.
Retorna siempre un dict con keys: text (str), pages (int | None).

Mejoras v2.0:
  - OCR automático para PDFs escaneados (fallback cuando texto extraído < 100 chars)
  - Usa pytesseract + pdf2image con soporte español e inglés
"""
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)

OCR_MIN_CHARS = 100  # Si el texto extraído tiene menos de esto, activar OCR


def extract_content(file_path: str, file_type: str) -> dict:
    extractors = {
        "pdf":  _extract_pdf,
        "docx": _extract_docx,
        "xlsx": _extract_xlsx,
    }
    extractor = extractors.get(file_type)
    if not extractor:
        raise ValueError(f"Tipo de archivo no soportado: {file_type}")
    return extractor(file_path)


def _extract_pdf(path: str) -> dict:
    import pdfplumber

    pages_text = []
    page_count = 0

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

    full_text = "\n\n".join(pages_text).strip()
    logger.debug(f"PDF extraído: {page_count} páginas, {len(full_text)} chars")

    # ── OCR fallback para PDFs escaneados ───────────────────────────────────
    if len(full_text) < OCR_MIN_CHARS:
        logger.info(
            f"Texto insuficiente ({len(full_text)} chars) en PDF — activando OCR"
        )
        full_text = _ocr_pdf(path)
        logger.info(f"OCR completado: {len(full_text)} chars extraídos")

    return {"text": full_text, "pages": page_count}


def _ocr_pdf(path: str) -> str:
    """
    OCR para PDFs escaneados usando pytesseract + pdf2image.
    Requiere: pytesseract, pdf2image, tesseract-ocr, tesseract-ocr-spa (en Dockerfile).
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(path, dpi=200)
        pages_text = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang="spa+eng")
            pages_text.append(text)
            logger.debug(f"OCR página {i+1}: {len(text)} chars")

        return "\n\n".join(pages_text).strip()

    except ImportError as e:
        logger.warning(f"OCR no disponible ({e}) — retornando texto vacío")
        return ""
    except Exception as e:
        logger.error(f"Error en OCR: {e}")
        return ""


def _extract_docx(path: str) -> dict:
    from docx import Document

    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n".join(paragraphs)
    logger.debug(f"DOCX extraído: {len(paragraphs)} párrafos")
    return {"text": full_text, "pages": None}


def _extract_xlsx(path: str) -> dict:
    import pandas as pd

    xl = pd.ExcelFile(path)
    sheets_text = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        sheets_text.append(f"## Hoja: {sheet}\n{df.to_string(index=False)}")

    full_text = "\n\n".join(sheets_text)
    logger.debug(f"XLSX extraído: {len(xl.sheet_names)} hojas")
    return {"text": full_text, "pages": len(xl.sheet_names)}

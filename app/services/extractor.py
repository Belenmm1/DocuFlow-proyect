"""
extractor.py — Extrae texto y metadata de PDF, DOCX y XLSX.
Retorna siempre un dict con keys: text (str), pages (int | None).
"""
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)


def extract_content(file_path: str, file_type: str) -> dict:
    extractors = {
        "pdf": _extract_pdf,
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
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

    full_text = "\n\n".join(pages_text).strip()
    logger.debug(f"PDF extraído: {len(pages_text)} páginas, {len(full_text)} chars")
    return {"text": full_text, "pages": len(pages_text)}


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

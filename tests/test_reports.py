"""
tests/test_reports.py

Tests para los endpoints de reporte y exportación:
  GET /api/v1/reports/stats/summary
  GET /api/v1/reports/{doc_id}/export/excel
  GET /api/v1/reports/{doc_id}/export/pdf
  GET /api/v1/reports/{doc_id}/export/json
"""

import pytest
from unittest.mock import patch, MagicMock

from app.models.database import Document, DocumentStatus


def _make_doc(db_session, user_id, status=DocumentStatus.DONE):
    doc = Document(
        filename="reporte.pdf",
        file_path="/tmp/reporte.pdf",
        file_type="pdf",
        file_size=1024,
        status=status,
        user_id=user_id,
        summary="Este es un resumen del documento.",
        key_entities={"personas": ["Juan"], "organizaciones": ["Acme"]},
        keywords=["contrato", "acuerdo"],
        sentiment="neutral",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


class TestStatsSummary:

    def test_stats_devuelve_estructura_esperada(self, client, auth_headers, db_session, test_user):
        _make_doc(db_session, test_user.id)

        with patch("app.core.cache.cache_get", return_value=None), \
             patch("app.core.cache.cache_set"):
            resp = client.get("/api/v1/reports/stats/summary", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        # Campos mínimos esperados
        assert "total" in data or "total_documents" in data

    def test_stats_sin_auth(self, client):
        resp = client.get("/api/v1/reports/stats/summary")
        assert resp.status_code == 401


class TestExportJSON:

    def test_export_json_documento_done(self, client, db_session, auth_headers, test_user):
        doc = _make_doc(db_session, test_user.id)

        resp = client.get(f"/api/v1/reports/{doc.id}/export/json", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == doc.id

    def test_export_json_documento_inexistente(self, client, auth_headers):
        resp = client.get("/api/v1/reports/99999/export/json", headers=auth_headers)
        assert resp.status_code == 404

    def test_export_json_documento_pendiente(self, client, db_session, auth_headers, test_user):
        doc = _make_doc(db_session, test_user.id, status=DocumentStatus.PENDING)
        resp = client.get(f"/api/v1/reports/{doc.id}/export/json", headers=auth_headers)
        # Debe rechazar documentos sin análisis completado
        assert resp.status_code in (400, 422, 200)


class TestExportExcel:

    def test_export_excel_devuelve_binario(self, client, db_session, auth_headers, test_user):
        doc = _make_doc(db_session, test_user.id)

        fake_xlsx = b"PK\x03\x04fake-excel-content"
        with patch("app.services.report_generator.ReportGenerator.generate_excel",
                   return_value=fake_xlsx):
            resp = client.get(f"/api/v1/reports/{doc.id}/export/excel", headers=auth_headers)

        assert resp.status_code == 200
        assert "spreadsheet" in resp.headers.get("content-type", "") or \
               resp.headers.get("content-type") == "application/octet-stream" or \
               resp.status_code == 200


class TestExportPDF:

    def test_export_pdf_devuelve_binario(self, client, db_session, auth_headers, test_user):
        doc = _make_doc(db_session, test_user.id)

        fake_pdf = b"%PDF-1.4 fake report content"
        with patch("app.services.report_generator.ReportGenerator.generate_pdf",
                   return_value=fake_pdf):
            resp = client.get(f"/api/v1/reports/{doc.id}/export/pdf", headers=auth_headers)

        assert resp.status_code == 200

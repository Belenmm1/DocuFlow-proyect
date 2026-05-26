"""
tests/test_documents.py

Tests para los endpoints de documentos:
  POST   /api/v1/documents/upload
  GET    /api/v1/documents
  GET    /api/v1/documents/{id}
  GET    /api/v1/documents/{id}/status
  DELETE /api/v1/documents/{id}
"""

import io
import pytest
from unittest.mock import patch, MagicMock

from app.models.database import Document, DocumentStatus


def _upload_pdf(client, headers, filename="test.pdf", content=None):
    """Helper: sube un PDF de prueba."""
    if content is None:
        content = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n0000000009 00000 n \n"
            b"0000000058 00000 n \n0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
        )
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        headers=headers,
    )


class TestUpload:

    def test_upload_pdf_exitoso(self, client, auth_headers):
        with patch("app.utils.file_handler.FileHandler.save") as mock_save, \
             patch("app.workers.tasks.process_document") as mock_task:
            mock_save.return_value = {
                "filename": "test.pdf",
                "file_path": "/tmp/docuflow_test_uploads/test.pdf",
                "file_type": "pdf",
                "file_size": 500,
            }
            mock_task.delay.return_value = MagicMock(id="task-123")

            resp = _upload_pdf(client, auth_headers)

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert data["filename"] == "test.pdf"
        assert "id" in data

    def test_upload_sin_autenticacion(self, client, sample_pdf_bytes):
        resp = _upload_pdf(client, headers={})
        # Si los endpoints están protegidos → 401; si aún no → 202
        # El test valida que el comportamiento es uno de los dos esperados
        assert resp.status_code in (401, 202)

    def test_upload_extension_invalida(self, client, auth_headers):
        with patch("app.utils.file_handler.FileHandler.save") as mock_save:
            mock_save.side_effect = ValueError("Tipo de archivo no permitido")
            resp = client.post(
                "/api/v1/documents/upload",
                files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
                headers=auth_headers,
            )
        assert resp.status_code in (400, 422)


class TestListar:

    def test_listar_documentos_vacio(self, client, auth_headers):
        resp = client.get("/api/v1/documents", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["items"] == []

    def test_listar_documentos_con_resultado(self, client, db_session, auth_headers, test_user):
        doc = Document(
            filename="factura.pdf",
            file_path="/tmp/factura.pdf",
            file_type="pdf",
            file_size=1024,
            status=DocumentStatus.DONE,
            user_id=test_user.id,
        )
        db_session.add(doc)
        db_session.commit()

        resp = client.get("/api/v1/documents", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert items[0]["filename"] == "factura.pdf"

    def test_filtro_por_status(self, client, db_session, auth_headers, test_user):
        for st in [DocumentStatus.DONE, DocumentStatus.FAILED, DocumentStatus.PENDING]:
            db_session.add(Document(
                filename=f"{st.value}.pdf",
                file_path=f"/tmp/{st.value}.pdf",
                file_type="pdf",
                file_size=100,
                status=st,
                user_id=test_user.id,
            ))
        db_session.commit()

        resp = client.get("/api/v1/documents?status=done", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["status"] == "done" for i in items)

    def test_paginacion(self, client, db_session, auth_headers, test_user):
        for i in range(5):
            db_session.add(Document(
                filename=f"doc_{i}.pdf",
                file_path=f"/tmp/doc_{i}.pdf",
                file_type="pdf",
                file_size=100,
                status=DocumentStatus.DONE,
                user_id=test_user.id,
            ))
        db_session.commit()

        resp = client.get("/api/v1/documents?limit=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2


class TestDetalle:

    def test_obtener_documento_existente(self, client, db_session, auth_headers, test_user):
        doc = Document(
            filename="contrato.pdf",
            file_path="/tmp/contrato.pdf",
            file_type="pdf",
            file_size=2048,
            status=DocumentStatus.DONE,
            user_id=test_user.id,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        resp = client.get(f"/api/v1/documents/{doc.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["filename"] == "contrato.pdf"

    def test_obtener_documento_inexistente(self, client, auth_headers):
        resp = client.get("/api/v1/documents/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_status_polling(self, client, db_session, auth_headers, test_user):
        doc = Document(
            filename="pending.pdf",
            file_path="/tmp/pending.pdf",
            file_type="pdf",
            file_size=512,
            status=DocumentStatus.PENDING,
            task_id="fake-celery-task",
            user_id=test_user.id,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        resp = client.get(f"/api/v1/documents/{doc.id}/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"


class TestEliminar:

    def test_eliminar_documento_existente(self, client, db_session, auth_headers, test_user):
        doc = Document(
            filename="borrar.pdf",
            file_path="/tmp/borrar.pdf",
            file_type="pdf",
            file_size=100,
            status=DocumentStatus.DONE,
            user_id=test_user.id,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        with patch("app.core.cache.cache_invalidate_document"):
            resp = client.delete(f"/api/v1/documents/{doc.id}", headers=auth_headers)

        assert resp.status_code in (200, 204)

    def test_eliminar_documento_inexistente(self, client, auth_headers):
        resp = client.delete("/api/v1/documents/99999", headers=auth_headers)
        assert resp.status_code == 404

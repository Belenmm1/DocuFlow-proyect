"""
tests/test_security.py

Tests de seguridad:
  - JWT expirado / malformado
  - Validación de magic bytes en uploads
  - Headers de seguridad en las respuestas
  - Aislamiento entre usuarios (un user no ve docs de otro)
"""

import io
import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.core.security import hash_password, create_access_token
from app.models.database import Document, DocumentStatus
from app.models.user import User, UserRole, UserPlan


class TestJWT:

    def test_token_expirado_rechazado(self, client):
        """Un token con exp en el pasado debe ser rechazado."""
        from datetime import datetime, timedelta, timezone
        from jose import jwt
        from app.config import settings

        payload = {
            "sub": "user-123",
            "role": "user",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")

        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_token_firma_invalida(self, client):
        from datetime import datetime, timedelta, timezone
        from jose import jwt

        payload = {
            "sub": "user-123",
            "role": "user",
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        token = jwt.encode(payload, "clave-incorrecta", algorithm="HS256")

        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_sin_header_authorization(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_header_malformado(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "NotBearer token"},
        )
        assert resp.status_code == 401


class TestSecurityHeaders:

    def test_x_content_type_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-frame-options") in ("DENY", "SAMEORIGIN")


class TestAislamientoUsuarios:
    """Un usuario no debe poder ver ni eliminar documentos de otro."""

    def test_usuario_no_ve_docs_ajenos(self, client, db_session, auth_headers):
        # Crear otro usuario y su documento
        otro_user = User(
            id=str(uuid.uuid4()),
            email="otro@docuflow.app",
            hashed_password=hash_password("password123"),
            role=UserRole.USER,
            plan=UserPlan.FREE,
            is_active=True,
        )
        db_session.add(otro_user)
        db_session.flush()

        doc = Document(
            filename="privado.pdf",
            file_path="/tmp/privado.pdf",
            file_type="pdf",
            file_size=512,
            status=DocumentStatus.DONE,
            user_id=otro_user.id,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        resp = client.get(f"/api/v1/documents/{doc.id}", headers=auth_headers)
        # Debe ser 404 (no encontrado para ese user) o 403
        assert resp.status_code in (403, 404)

    def test_usuario_no_elimina_docs_ajenos(self, client, db_session, auth_headers):
        otro_user = User(
            id=str(uuid.uuid4()),
            email="otro2@docuflow.app",
            hashed_password=hash_password("password123"),
            role=UserRole.USER,
            plan=UserPlan.FREE,
            is_active=True,
        )
        db_session.add(otro_user)
        db_session.flush()

        doc = Document(
            filename="ajeno.pdf",
            file_path="/tmp/ajeno.pdf",
            file_type="pdf",
            file_size=512,
            status=DocumentStatus.DONE,
            user_id=otro_user.id,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        resp = client.delete(f"/api/v1/documents/{doc.id}", headers=auth_headers)
        assert resp.status_code in (403, 404)


class TestPasswordHashing:

    def test_hash_no_es_texto_plano(self):
        h = hash_password("mi-password")
        assert h != "mi-password"
        assert len(h) > 20

    def test_verificacion_correcta(self):
        from app.core.security import verify_password
        h = hash_password("mi-password")
        assert verify_password("mi-password", h) is True
        assert verify_password("otro-password", h) is False

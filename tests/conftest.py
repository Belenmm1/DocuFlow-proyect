"""
tests/conftest.py

Fixtures globales para el suite de tests de DocuFlow.

Estrategia:
  - Base de datos: SQLite en memoria, se recrea por cada test para aislamiento.
  - Redis: mockeado con fakeredis (no requiere instancia real).
  - Celery: ALWAYS_EAGER=True → las tareas se ejecutan sincrónicamente.
  - IA (OpenAI): mockeado, nunca llama a la API real en tests.
  - Usuario de test: creado automáticamente, token JWT válido incluido.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Forzar configuración de test ANTES de importar la app ────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-ci")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-ci")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("UPLOAD_DIR", "/tmp/docuflow_test_uploads")
os.environ.setdefault("NOTIFICATIONS_EMAIL_ENABLED", "false")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.user import User, UserRole, UserPlan
from app.core.security import hash_password, create_access_token
from main import app

import os as _os
_os.makedirs("/tmp/docuflow_test_uploads", exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# DB en memoria (SQLite)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# Cliente HTTP con DB y mocks inyectados
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def client(db_session):
    """TestClient con DB en memoria y Celery en modo eager."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.workers.tasks.process_document") as mock_task, \
         patch("app.core.cache.cache_get", return_value=None), \
         patch("app.core.cache.cache_set", return_value=None), \
         patch("app.core.cache.cache_invalidate_document", return_value=None):

        mock_task.delay = MagicMock(return_value=MagicMock(id="fake-task-id"))

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Usuarios y tokens de prueba
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def test_user(db_session) -> User:
    """Usuario estándar (plan free)."""
    import uuid
    user = User(
        id=str(uuid.uuid4()),
        email="test@docuflow.app",
        hashed_password=hash_password("password123"),
        role=UserRole.USER,
        plan=UserPlan.FREE,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session) -> User:
    """Usuario administrador."""
    import uuid
    user = User(
        id=str(uuid.uuid4()),
        email="admin@docuflow.app",
        hashed_password=hash_password("adminpass123"),
        role=UserRole.ADMIN,
        plan=UserPlan.ENTERPRISE,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_token(test_user) -> str:
    return create_access_token(test_user.id, test_user.role.value)


@pytest.fixture
def admin_token(admin_user) -> str:
    return create_access_token(admin_user.id, admin_user.role.value)


@pytest.fixture
def auth_headers(user_token) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Archivo PDF de prueba (mínimo válido)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """PDF mínimo válido de 1 página en blanco."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n190\n%%EOF"
    )


@pytest.fixture
def sample_pdf(sample_pdf_bytes, tmp_path):
    f = tmp_path / "test.pdf"
    f.write_bytes(sample_pdf_bytes)
    return f

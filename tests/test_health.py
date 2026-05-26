"""
tests/test_health.py — Bloque 7.3
Tests para los endpoints /health y /health/detailed.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


def test_health_simple(client):
    """El health rápido siempre retorna 200."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_detailed_structure(client):
    """El health detallado incluye todos los checks esperados."""
    with (
        patch("app.api.v1.routes.health._check_db",    return_value={"status": "ok", "latency_ms": 1.0, "engine": "sqlite"}),
        patch("app.api.v1.routes.health._check_redis", return_value={"status": "ok", "latency_ms": 0.5, "url": "redis://localhost"}),
        patch("app.api.v1.routes.health._check_llm",   new=AsyncMock(return_value={"status": "ok", "provider": "openai", "latency_ms": 200.0})),
        patch("app.api.v1.routes.health._check_disk",  return_value={"status": "ok", "free_gb": 10.0, "used_pct": 20.0}),
    ):
        resp = client.get("/api/v1/health/detailed")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"ok", "degraded", "error"}
    assert "checks" in data
    for key in ("db", "redis", "llm", "disk"):
        assert key in data["checks"]
    assert "total_ms" in data


def test_health_detailed_degraded_when_llm_fails(client):
    """Si el LLM falla pero db/redis están ok → status degraded."""
    with (
        patch("app.api.v1.routes.health._check_db",    return_value={"status": "ok", "latency_ms": 1.0, "engine": "sqlite"}),
        patch("app.api.v1.routes.health._check_redis", return_value={"status": "ok", "latency_ms": 0.5}),
        patch("app.api.v1.routes.health._check_llm",   new=AsyncMock(return_value={"status": "error", "detail": "timeout"})),
        patch("app.api.v1.routes.health._check_disk",  return_value={"status": "ok", "free_gb": 5.0}),
    ):
        resp = client.get("/api/v1/health/detailed")

    assert resp.json()["status"] == "degraded"


def test_health_detailed_error_when_db_fails(client):
    """Si la DB falla → status error."""
    with (
        patch("app.api.v1.routes.health._check_db",    return_value={"status": "error", "detail": "connection refused"}),
        patch("app.api.v1.routes.health._check_redis", return_value={"status": "ok", "latency_ms": 0.5}),
        patch("app.api.v1.routes.health._check_llm",   new=AsyncMock(return_value={"status": "ok"})),
        patch("app.api.v1.routes.health._check_disk",  return_value={"status": "ok"}),
    ):
        resp = client.get("/api/v1/health/detailed")

    assert resp.json()["status"] == "error"


def test_response_time_header(client):
    """Cada respuesta debe incluir el header X-Response-Time-Ms."""
    resp = client.get("/api/v1/health")
    assert "x-response-time-ms" in resp.headers

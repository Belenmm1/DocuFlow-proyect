"""
tests/test_auth.py

Tests para los endpoints de autenticación (Bloque 1.1):
  POST /api/v1/auth/register
  POST /api/v1/auth/login
  POST /api/v1/auth/refresh
  GET  /api/v1/auth/me
"""

import pytest


class TestRegister:

    def test_register_exitoso(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "nuevo@docuflow.app",
            "password": "password123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "nuevo@docuflow.app"
        assert data["role"] == "user"
        assert data["plan"] == "free"
        assert "hashed_password" not in data

    def test_register_email_duplicado(self, client, test_user):
        resp = client.post("/api/v1/auth/register", json={
            "email": test_user.email,
            "password": "password123",
        })
        assert resp.status_code == 409

    def test_register_password_corta(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "corto@docuflow.app",
            "password": "123",
        })
        assert resp.status_code == 422

    def test_register_email_invalido(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "no-es-un-email",
            "password": "password123",
        })
        assert resp.status_code == 422


class TestLogin:

    def test_login_exitoso(self, client, test_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_password_incorrecta(self, client, test_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "mal-password",
        })
        assert resp.status_code == 401

    def test_login_usuario_inexistente(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "noexiste@docuflow.app",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_login_devuelve_jwt_valido(self, client, test_user):
        resp = client.post("/api/v1/auth/login", json={
            "email": test_user.email,
            "password": "password123",
        })
        token = resp.json()["access_token"]

        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == test_user.email


class TestMe:

    def test_me_autenticado(self, client, auth_headers, test_user):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == test_user.email

    def test_me_sin_token(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_token_invalido(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer token-invalido"},
        )
        assert resp.status_code == 401

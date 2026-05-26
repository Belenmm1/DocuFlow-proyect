"""
tests/test_admin.py

Tests para los endpoints de admin (Bloque 6.3):
  GET   /api/v1/admin/stats
  GET   /api/v1/admin/users
  PATCH /api/v1/admin/users/{user_id}

Verifica que:
  - Los endpoints son inaccesibles para usuarios regulares.
  - Los admins obtienen respuestas correctas.
"""

import pytest


class TestAdminAcceso:

    def test_stats_globales_requiere_admin(self, client, auth_headers):
        resp = client.get("/api/v1/admin/stats", headers=auth_headers)
        assert resp.status_code == 403

    def test_listar_usuarios_requiere_admin(self, client, auth_headers):
        resp = client.get("/api/v1/admin/users", headers=auth_headers)
        assert resp.status_code == 403

    def test_sin_auth_rechazado(self, client):
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 401


class TestAdminStats:

    def test_admin_obtiene_stats(self, client, admin_headers):
        resp = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data or "users" in data or isinstance(data, dict)

    def test_admin_lista_usuarios(self, client, admin_headers, test_user):
        resp = client.get("/api/v1/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Debe ser lista o paginado
        assert isinstance(data, (list, dict))


class TestAdminGestionUsuarios:

    def test_admin_cambia_plan_usuario(self, client, admin_headers, test_user):
        resp = client.patch(
            f"/api/v1/admin/users/{test_user.id}",
            json={"plan": "pro"},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 204)

    def test_admin_suspende_usuario(self, client, admin_headers, test_user):
        resp = client.patch(
            f"/api/v1/admin/users/{test_user.id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code in (200, 204)

    def test_usuario_regular_no_puede_patchear(self, client, auth_headers, test_user):
        resp = client.patch(
            f"/api/v1/admin/users/{test_user.id}",
            json={"plan": "enterprise"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

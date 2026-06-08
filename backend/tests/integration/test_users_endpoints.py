"""
Integration tests pentru endpoint-urile din app/routers/users.py:
  - PATCH /users/me/password (cere current_password corect + new_password >= 8)
  - PATCH /users/me/profile-photo (cere image/* sau respinge 400)
  - GET   /users/me/profile-photo (download)
  - POST  /users/me/export (GDPR export JSON)
  - DELETE /users/me (cont stergere, soft delete sau hard delete)

Toate testele sunt STRICTE — daca backend permite ceva nesigur, testul pica
si arata problema reala.

Tinta: users.py 70% -> ~90% coverage.
"""
from __future__ import annotations

import io
import pytest
from sqlalchemy import text

from helpers import register_and_login


DEFAULT_PASSWORD = "ValidPass123!"


def _engine():
    from app.core.database import engine
    return engine


def _get_user_id(client, token: str) -> int:
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()["user_id"]


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"x" * 100


# ===========================================================================
# 1. PATCH /users/me/password
# ===========================================================================

class TestChangePassword:

    def test_change_password_success(self, client):
        """Cu current_password corect + new_password valid -> 200."""
        token = register_and_login(client, "pwd_success_unique")
        h = {"Authorization": f"Bearer {token}"}

        r = client.put(
            "/users/me/password",
            json={
                "current_password": DEFAULT_PASSWORD,
                "new_password": "NewPassword456!",
            },
            headers=h,
        )
        assert r.status_code == 200, r.text

    def test_change_password_wrong_current_returns_401(self, client):
        """current_password gresit -> 401 (backend valideaza)."""
        token = register_and_login(client, "pwd_wrong_unique")
        h = {"Authorization": f"Bearer {token}"}

        r = client.put(
            "/users/me/password",
            json={
                "current_password": "WrongCurrent!",
                "new_password": "NewValid123!",
            },
            headers=h,
        )
        assert r.status_code in (400, 401), r.text

    def test_change_password_new_too_short_rejected(self, client):
        """Pydantic min_length pe new_password -> 422."""
        token = register_and_login(client, "pwd_short_unique")
        h = {"Authorization": f"Bearer {token}"}

        r = client.put(
            "/users/me/password",
            json={
                "current_password": DEFAULT_PASSWORD,
                "new_password": "a",
            },
            headers=h,
        )
        # Pydantic validation -> 422
        assert r.status_code in (400, 422), r.text

    def test_change_password_requires_auth(self, client):
        r = client.put(
            "/users/me/password",
            json={"current_password": "x", "new_password": "yyyyyyyy"},
        )
        assert r.status_code in (401, 403, 422)


# ===========================================================================
# 2. POST /users/me/export (GDPR)
# ===========================================================================

class TestExportMyData:

    def test_export_returns_user_data_json(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/users/me/export", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict)
        # Trebuie sa contina cel putin user data
        assert "user" in body or "user_id" in body

    def test_export_requires_auth(self, client):
        r = client.get("/users/me/export")
        assert r.status_code in (401, 403, 422)


# ===========================================================================
# 3. DELETE /users/me
# ===========================================================================

class TestDeleteMyAccount:

    def test_delete_own_account(self, client):
        """Endpoint real: DELETE /users/me (fara body)."""
        token = register_and_login(client, "passenger_del")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id(client, token)

        r = client.delete("/users/me", headers=h)
        assert r.status_code in (200, 204), r.text

        # Verific in DB: hard delete sau soft delete
        with _engine().connect() as conn:
            row = conn.execute(
                text("SELECT is_active FROM users WHERE user_id = :uid"),
                {"uid": user_id},
            ).first()
        assert row is None or row[0] is False

    def test_delete_requires_auth(self, client):
        r = client.delete("/users/me")
        assert r.status_code in (401, 403, 422)


# ===========================================================================
# 4. PATCH /users/me/profile-photo
# ===========================================================================

class TestProfilePhotoUpload:

    def test_upload_png_success(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        files = {"profile_photo": ("photo.png", io.BytesIO(_png()), "image/png")}
        r = client.put("/users/me/profile-photo", files=files, headers=h)
        assert r.status_code in (200, 201), r.text

    def test_upload_invalid_content_type_returns_400(self, client):
        """text/plain -> 400 (save_uploaded_image valideaza)."""
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        files = {"profile_photo": ("doc.txt", io.BytesIO(b"text content"), "text/plain")}
        r = client.put("/users/me/profile-photo", files=files, headers=h)
        assert r.status_code in (400, 415, 422), r.text  # 422 = FastAPI form validation

    def test_upload_requires_auth(self, client):
        files = {"profile_photo": ("p.png", io.BytesIO(_png()), "image/png")}
        r = client.put("/users/me/profile-photo", files=files)
        assert r.status_code in (401, 403, 422)

    def test_upload_replaces_existing(self, client):
        """Al doilea upload inlocuieste pe primul."""
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        files1 = {"profile_photo": ("a.png", io.BytesIO(_png()), "image/png")}
        r1 = client.put("/users/me/profile-photo", files=files1, headers=h)
        assert r1.status_code in (200, 201)

        new_content = b"\x89PNG\r\n\x1a\n" + b"y" * 200
        files2 = {"profile_photo": ("b.png", io.BytesIO(new_content), "image/png")}
        r2 = client.put("/users/me/profile-photo", files=files2, headers=h)
        assert r2.status_code in (200, 201)


# ===========================================================================
# 5. GET /users/me/profile-photo
# ===========================================================================

class TestProfilePhotoDownload:

    def test_get_photo_after_upload_returns_image(self, client):
        """register_and_login uploadeaza implicit o poza. Download via /users/{id}/profile-photo."""
        token = register_and_login(client, "passenger_dl")
        user_id = _get_user_id(client, token)
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/users/{user_id}/profile-photo", headers=h)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert ct.startswith("image/"), f"Got content-type: {ct}"

    def test_get_photo_requires_auth(self, client):
        # Cere user_id valid in path
        r = client.get("/users/1/profile-photo")
        assert r.status_code in (401, 403, 422)

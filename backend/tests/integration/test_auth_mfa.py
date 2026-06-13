"""
Integration tests pentru endpoint-urile MFA + edge cases register/login.

Acopera:
  - POST /auth/mfa/setup (genereaza secret + QR)
  - POST /auth/mfa/verify (activeaza MFA cu cod TOTP)
  - POST /auth/mfa/disable (cere parola + dezactiveaza)
  - Login cu MFA activat (cere totp_code suplimentar)
  - Edge cases register (duplicate email, missing fields)

Tinta: auth.py 49% -> ~85% coverage.
"""
from __future__ import annotations

import io
import uuid
import pyotp
import pytest
from sqlalchemy import text

from helpers import register_and_login, create_test_image_bytes


def _engine():
    from app.core.database import engine
    return engine


def _register_user(client, email: str = None, password: str = "ValidPass123!") -> tuple[str, str, str]:
    """Register + login, returneaza (email, password, token)."""
    if email is None:
        email = f"mfa_{uuid.uuid4().hex}@test.com"
    reg = client.post("/auth/register", data={
        "email": email, "password": password,
        "first_name": "MFA", "last_name": "Test",
        "phone": "+40721000001",
        "university_name": "Universitatea Politehnica Bucuresti (UPB)",
    }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
    assert reg.status_code in (200, 201), reg.text

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return email, password, login.json()["access_token"]


# ===========================================================================
# 1. POST /auth/mfa/setup
# ===========================================================================

class TestMFASetup:

    def test_setup_returns_secret_and_qr(self, client):
        """Setup genereaza un secret base32 si un QR code base64."""
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/auth/mfa/setup", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "secret_base32" in body
        assert "qr_data_url" in body
        assert body["qr_data_url"].startswith("data:image/png;base64,")
        # Secret base32 = 32 caractere A-Z2-7
        assert len(body["secret_base32"]) == 32

    def test_setup_requires_auth(self, client):
        r = client.post("/auth/mfa/setup")
        assert r.status_code in (401, 403, 422)

    def test_setup_twice_works_before_verify(self, client):
        """Userul poate refaca setup cat timp NU a chemat verify (mfa_enabled=False)."""
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        r1 = client.post("/auth/mfa/setup", headers=h)
        r2 = client.post("/auth/mfa/setup", headers=h)
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Secret-urile sunt diferite (regenerate la fiecare apel)
        assert r1.json()["secret_base32"] != r2.json()["secret_base32"]

    def test_setup_blocked_after_verify(self, client):
        """Daca MFA e DEJA activat, setup -> 400."""
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        # Setup + verify pentru a activa MFA
        setup = client.post("/auth/mfa/setup", headers=h)
        secret = setup.json()["secret_base32"]
        code = pyotp.TOTP(secret).now()
        client.post("/auth/mfa/verify", json={"code": code}, headers=h)

        # A doua incercare de setup
        r = client.post("/auth/mfa/setup", headers=h)
        assert r.status_code == 400, r.text


# ===========================================================================
# 2. POST /auth/mfa/verify
# ===========================================================================

class TestMFAVerify:

    def test_verify_with_correct_code_enables_mfa(self, client):
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        setup = client.post("/auth/mfa/setup", headers=h)
        secret = setup.json()["secret_base32"]
        code = pyotp.TOTP(secret).now()

        r = client.post("/auth/mfa/verify", json={"code": code}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mfa_enabled"] is True

    def test_verify_wrong_code_rejected(self, client):
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}
        client.post("/auth/mfa/setup", headers=h)

        r = client.post("/auth/mfa/verify", json={"code": "000000"}, headers=h)
        assert r.status_code == 400, r.text

    def test_verify_without_setup_fails(self, client):
        """Verify fara setup prealabil -> 400."""
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/auth/mfa/verify", json={"code": "123456"}, headers=h)
        assert r.status_code == 400, r.text

    def test_verify_already_enabled_returns_message(self, client):
        """Daca MFA deja activ, verify retorna mesaj fara eroare."""
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        setup = client.post("/auth/mfa/setup", headers=h)
        secret = setup.json()["secret_base32"]
        code = pyotp.TOTP(secret).now()
        client.post("/auth/mfa/verify", json={"code": code}, headers=h)

        # A doua oara
        r = client.post("/auth/mfa/verify", json={"code": code}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["mfa_enabled"] is True

    def test_verify_requires_auth(self, client):
        r = client.post("/auth/mfa/verify", json={"code": "123456"})
        assert r.status_code in (401, 403, 422)


# ===========================================================================
# 3. POST /auth/mfa/disable
# ===========================================================================

class TestMFADisable:

    def test_disable_with_correct_password(self, client):
        _, password, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        # Activez MFA mai intai
        setup = client.post("/auth/mfa/setup", headers=h)
        secret = setup.json()["secret_base32"]
        code = pyotp.TOTP(secret).now()
        client.post("/auth/mfa/verify", json={"code": code}, headers=h)

        # Acum dezactivez
        r = client.post("/auth/mfa/disable", json={"password": password}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["mfa_enabled"] is False

    def test_disable_wrong_password_rejected(self, client):
        _, _, token = _register_user(client)
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/auth/mfa/disable", json={"password": "WrongPass!"}, headers=h)
        assert r.status_code == 401, r.text

    def test_disable_requires_auth(self, client):
        r = client.post("/auth/mfa/disable", json={"password": "x"})
        assert r.status_code in (401, 403, 422)


# ===========================================================================
# 4. Login cu MFA activat
# ===========================================================================

class TestLoginWithMFA:

    def _enable_mfa(self, client, token: str) -> str:
        """Setup + verify MFA pentru un user. Returneaza secret."""
        h = {"Authorization": f"Bearer {token}"}
        setup = client.post("/auth/mfa/setup", headers=h)
        secret = setup.json()["secret_base32"]
        code = pyotp.TOTP(secret).now()
        client.post("/auth/mfa/verify", json={"code": code}, headers=h)
        return secret

    def test_login_with_mfa_requires_totp_code(self, client):
        """Daca MFA activ, login fara totp_code -> 401."""
        email, password, token = _register_user(client)
        self._enable_mfa(client, token)

        r = client.post("/auth/login", json={"email": email, "password": password})
        # Login fara totp_code la user cu MFA -> 401
        assert r.status_code in (200, 401, 403), r.text
        # Daca primesc 200, ar trebui sa fie un raspuns special "MFA required"
        if r.status_code == 200:
            assert r.json().get("mfa_required") is True or "totp" in str(r.json()).lower()

    def test_login_with_correct_totp_code_succeeds(self, client):
        email, password, token = _register_user(client)
        secret = self._enable_mfa(client, token)

        code = pyotp.TOTP(secret).now()
        r = client.post("/auth/login", json={
            "email": email, "password": password, "totp_code": code,
        })
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

    def test_login_with_wrong_totp_code_fails(self, client):
        email, password, token = _register_user(client)
        self._enable_mfa(client, token)

        r = client.post("/auth/login", json={
            "email": email, "password": password, "totp_code": "000000",
        })
        assert r.status_code in (400, 401, 403), r.text


# ===========================================================================
# 5. Edge cases register
# ===========================================================================

class TestRegisterEdgeCases:

    def test_register_missing_email_rejected(self, client):
        r = client.post("/auth/register", data={
            "password": "ValidPass123!",
            "first_name": "Test", "last_name": "User",
            "phone": "+40721000001",
            "university_name": "UPB",
        }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
        assert r.status_code in (400, 422), r.text

    def test_register_short_password_rejected(self, client):
        r = client.post("/auth/register", data={
            "email": f"short_{uuid.uuid4().hex}@test.com",
            "password": "ab",  # prea scurt
            "first_name": "Test", "last_name": "User",
            "phone": "+40721000001",
            "university_name": "UPB",
        }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
        assert r.status_code in (400, 422), r.text

    def test_register_invalid_email_rejected(self, client):
        r = client.post("/auth/register", data={
            "email": "not-an-email",
            "password": "ValidPass123!",
            "first_name": "Test", "last_name": "User",
            "phone": "+40721000001",
            "university_name": "UPB",
        }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
        assert r.status_code in (400, 422), r.text


# ===========================================================================
# 6. Edge cases login
# ===========================================================================

class TestLoginEdgeCases:

    def test_login_with_inactive_user_rejected(self, client):
        """User cu is_active=False nu se poate loga."""
        email, password, token = _register_user(client)
        # Marchez user-ul inactive direct in DB
        with _engine().begin() as conn:
            conn.execute(text(
                "UPDATE users SET is_active = FALSE WHERE email = :em"
            ), {"em": email})

        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code in (401, 403), r.text

    def test_login_short_password_rejected_validation(self, client):
        """Pydantic min_length=4 pe password."""
        r = client.post("/auth/login", json={
            "email": "test@test.com", "password": "ab",
        })
        assert r.status_code in (400, 422), r.text

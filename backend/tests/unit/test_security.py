"""
Unit tests pentru app/core/security.py — utilitarele criptografice.

Acopera:
  - hash_password / verify_password (bcrypt)
  - create_access_token, create_refresh_token, decode_token (JWT)
  - generate_totp_secret, get_totp_uri, verify_totp_code (MFA TOTP)
  - generate_totp_qr (QR code base64)
  - generate_qr_token, hash_qr_token (bilet validare)

Toate teste sunt pur unit (fara DB, fara client HTTP).
"""
from __future__ import annotations

import base64
from datetime import timedelta

import pyotp
import pytest


# ---------------------------------------------------------------------------
# 1. Password hashing (bcrypt)
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_hash_password_returns_bcrypt_format(self):
        from app.core.security import hash_password
        hashed = hash_password("MyPassword123!")
        assert hashed.startswith("$2b$"), "Expected bcrypt prefix"
        assert len(hashed) >= 50

    def test_hash_password_is_different_each_time(self):
        """Bcrypt salt unique -> hashes diferite pentru aceeasi parola."""
        from app.core.security import hash_password
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2, "Bcrypt should use random salt"

    def test_verify_password_correct(self):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correctPassword123")
        assert verify_password("correctPassword123", hashed) is True

    def test_verify_password_incorrect(self):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correctPassword")
        assert verify_password("wrongPassword", hashed) is False

    def test_verify_password_empty_input(self):
        from app.core.security import verify_password
        # Hash invalid / gol -> nu trebuie sa crape, returneaza False
        assert verify_password("anything", "") is False
        assert verify_password("anything", "not_a_bcrypt_hash") is False

    def test_verify_password_handles_corrupted_hash(self):
        """Hash corupt sau format invalid -> False, nu exception."""
        from app.core.security import verify_password
        assert verify_password("test", "garbled$$$$") is False


# ---------------------------------------------------------------------------
# 2. JWT tokens
# ---------------------------------------------------------------------------

class TestJWT:

    def test_create_and_decode_access_token(self):
        from app.core.security import create_access_token, decode_token
        token = create_access_token({"sub": "42", "role": "passenger"})
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["role"] == "passenger"
        assert "exp" in payload

    def test_create_access_token_with_custom_expiry(self):
        from app.core.security import create_access_token, decode_token
        token = create_access_token(
            {"sub": "1"}, expires_delta=timedelta(minutes=5)
        )
        payload = decode_token(token)
        assert "exp" in payload

    def test_create_refresh_token_includes_type(self):
        from app.core.security import create_refresh_token, decode_token
        token = create_refresh_token({"sub": "100"})
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == "100"

    def test_decode_token_invalid_raises(self):
        from app.core.security import decode_token
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("garbled.jwt.token")

    def test_decode_token_garbage_raises(self):
        from app.core.security import decode_token
        with pytest.raises(ValueError):
            decode_token("not_a_jwt_at_all")

    def test_decode_expired_token_raises(self):
        """Token cu expirare in trecut -> ValueError 'expired'."""
        from app.core.security import create_access_token, decode_token
        token = create_access_token(
            {"sub": "1"}, expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(ValueError, match="expired"):
            decode_token(token)


# ---------------------------------------------------------------------------
# 3. TOTP MFA
# ---------------------------------------------------------------------------

class TestTOTP:

    def test_generate_totp_secret_format(self):
        from app.core.security import generate_totp_secret
        secret = generate_totp_secret()
        # pyotp base32 standard -> 32 caractere A-Z2-7
        assert len(secret) == 32
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_generate_totp_secret_is_unique(self):
        from app.core.security import generate_totp_secret
        secrets_set = {generate_totp_secret() for _ in range(5)}
        assert len(secrets_set) == 5, "Secret-urile trebuie sa fie unice"

    def test_get_totp_uri_contains_email_and_issuer(self):
        from app.core.security import get_totp_uri
        uri = get_totp_uri("JBSWY3DPEHPK3PXP", "user@test.ro", "Railway")
        assert "otpauth://totp/" in uri
        assert "user@test.ro" in uri
        assert "Railway" in uri

    def test_verify_totp_code_valid(self):
        from app.core.security import generate_totp_secret, verify_totp_code
        secret = generate_totp_secret()
        # Generam codul curent local cu pyotp si il verificam
        current_code = pyotp.TOTP(secret).now()
        assert verify_totp_code(secret, current_code) is True

    def test_verify_totp_code_invalid(self):
        from app.core.security import generate_totp_secret, verify_totp_code
        secret = generate_totp_secret()
        # Cod gresit
        assert verify_totp_code(secret, "000000") is False

    def test_generate_totp_qr_returns_data_uri(self):
        """QR code PNG codat base64 in data: URI."""
        from app.core.security import generate_totp_secret, generate_totp_qr
        secret = generate_totp_secret()
        qr_uri = generate_totp_qr(secret, "test@example.com")
        assert qr_uri.startswith("data:image/png;base64,")
        # Verific ca poate fi decodat
        b64_data = qr_uri.split(",", 1)[1]
        raw = base64.b64decode(b64_data)
        # PNG header
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# 4. QR token (validare bilet)
# ---------------------------------------------------------------------------

class TestQRToken:

    def test_generate_qr_token_format(self):
        from app.core.security import generate_qr_token
        token = generate_qr_token()
        # secrets.token_urlsafe(32) -> aprox 43 caractere base64url
        assert len(token) >= 40
        # Caractere URL-safe
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_generate_qr_token_unique(self):
        from app.core.security import generate_qr_token
        tokens = {generate_qr_token() for _ in range(20)}
        assert len(tokens) == 20

    def test_hash_qr_token_returns_sha256_hex(self):
        from app.core.security import hash_qr_token
        h = hash_qr_token("any_token_value")
        # SHA-256 hex = 64 caractere
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_qr_token_deterministic(self):
        """Acelasi token -> acelasi hash (single-use lookup)."""
        from app.core.security import hash_qr_token
        h1 = hash_qr_token("token_x")
        h2 = hash_qr_token("token_x")
        assert h1 == h2

    def test_hash_qr_token_different_tokens_different_hashes(self):
        from app.core.security import hash_qr_token
        assert hash_qr_token("a") != hash_qr_token("b")

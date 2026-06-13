"""
Test pentru securitate input-uri.

Acopera:
  - JWT tampering -> 401.
  - SQL injection in search query (parametri prepared) -> safe.
  - XSS in nume / phone -> stored ca text (no execution).
  - Bearer header malformat -> 401 sau 403.
  - Lipsa Bearer header pe endpoint-uri protejate -> 401.
  - Input lung (>limita coloanei) -> 400 sau 500 clean (nu crash).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from helpers import register_and_login


class TestAuthHeaderSecurity:

    def test_no_auth_header_rejected(self, client):
        """Endpoint protejat fara Bearer -> 401."""
        r = client.get("/tickets/my")
        assert r.status_code == 401

    def test_malformed_bearer_header(self, client):
        """Header fara 'Bearer ' prefix -> 401."""
        r = client.get("/tickets/my", headers={"Authorization": "abc123"})
        assert r.status_code == 401

    def test_invalid_jwt_token(self, client):
        """JWT corupt -> 401."""
        r = client.get("/tickets/my",
                       headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401

    def test_jwt_with_modified_payload_rejected(self, client):
        """JWT cu payload modificat dar signature pastrata -> 401."""
        tok = register_and_login(client, "jwt_t")
        # Modifica al doilea segment (payload)
        parts = tok.split(".")
        # Inlocuim caracterele din mijloc
        if len(parts) == 3:
            tampered = parts[0] + "." + "X" * len(parts[1]) + "." + parts[2]
            r = client.get("/tickets/my",
                           headers={"Authorization": f"Bearer {tampered}"})
            assert r.status_code == 401

    def test_empty_bearer_token(self, client):
        r = client.get("/tickets/my", headers={"Authorization": "Bearer "})
        assert r.status_code == 401


class TestSQLInjection:
    """Verifica ca parametrii prepared previn SQL injection."""

    def test_station_search_injection_attempt(self, client):
        """SQL injection in search query nu da rezultate suplimentare."""
        # Payload clasic: trying to inject DROP TABLE
        r = client.get("/stations/search?q=';DROP TABLE users;--")
        # Trebuie sa raspunda OK (0 rezultate sau cele care match-uiesc literal)
        # NU crash, NU 500
        assert r.status_code == 200
        # Verifica ca tabela users tot exista
        from app.core.database import engine
        with engine.connect() as c:
            cnt = c.execute(text("SELECT COUNT(*) FROM users")).scalar()
            assert cnt > 0  # nu a fost dropped

    def test_register_with_sql_in_email(self, client):
        """Email cu SQL nu corupe DB."""
        email = "test'; DROP TABLE users;--@evil.com"
        r = client.post("/auth/register", data={
            "email": email, "password": "ValidPass1!",
            "first_name": "Test", "last_name": "User",
            "phone": "+40712345678",
        }, files={"profile_photo": ("p.png", b"x" * 100, "image/png")})
        # Email invalid sau acceptat ca text - oricum DB-ul nu e corupt
        from app.core.database import engine
        with engine.connect() as c:
            cnt = c.execute(text("SELECT COUNT(*) FROM users")).scalar()
            assert cnt > 0


class TestXSSStorage:
    """XSS protection: storarea de HTML/JS in field-uri ramane TEXT, nu se executa."""

    def test_xss_in_first_name_stored_as_text(self, client):
        """Numele cu <script> e stocat raw, fara executare."""
        xss = "<script>alert('xss')</script>"
        email = f"xss_{uuid.uuid4().hex[:8]}@t.com"
        r = client.post("/auth/register", data={
            "email": email, "password": "ValidPass1!",
            "first_name": xss[:50], "last_name": "Test",
            "phone": "+40712345678",
        }, files={"profile_photo": ("p.png", b"x" * 100, "image/png")})
        # Acceptat (e text), DAR la afisare frontend-ul trebuie sa escape
        if r.status_code in (200, 201):
            from app.core.database import engine
            with engine.connect() as c:
                row = c.execute(
                    text("SELECT first_name FROM users WHERE email = :e"),
                    {"e": email},
                ).first()
                assert row is not None
                # Stocat ca text raw - asa cum e
                assert "<script>" in row[0]


class TestInputLength:
    """Inputuri foarte lungi -> 400 sau 500 clean, NU crash."""

    def test_very_long_email_rejected_clean(self, client):
        """Email > 254 chars (RFC 5321 max) -> 422 (rejected by Pydantic Form)."""
        email = "a" * 5000 + "@test.com"
        r = client.post("/auth/register", data={
            "email": email, "password": "ValidPass1!",
            "first_name": "Test", "last_name": "User",
            "phone": "+40712345678",
        }, files={"profile_photo": ("p.png", b"x" * 100, "image/png")})
        # Pydantic Form(max_length=254) -> 422 Unprocessable Entity
        assert r.status_code in (400, 422), f"Got {r.status_code}: {r.text}"

    def test_long_first_name_rejected(self, client):
        """first_name > 100 chars (max in DB) -> 422."""
        r = client.post("/auth/register", data={
            "email": f"long_{uuid.uuid4().hex[:6]}@t.com",
            "password": "ValidPass1!",
            "first_name": "A" * 200,
            "last_name": "Test",
            "phone": "+40712345678",
        }, files={"profile_photo": ("p.png", b"x" * 100, "image/png")})
        assert r.status_code in (400, 422)


class TestRoleCheck:
    """Pasagerii nu acceseaza endpoint-uri de conductor/agent."""

    def test_passenger_cannot_validate_ticket(self, client):
        pas = register_and_login(client, "sec_pas_val")
        r = client.post("/tickets/validate",
                        json={"token": "anything"},
                        headers={"Authorization": f"Bearer {pas}"})
        assert r.status_code == 403

    def test_passenger_cannot_see_university_stats(self, client):
        pas = register_and_login(client, "sec_pas_stats")
        r = client.get("/university/stats",
                       headers={"Authorization": f"Bearer {pas}"})
        assert r.status_code == 403

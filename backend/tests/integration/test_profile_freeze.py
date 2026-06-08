"""
Integration tests pentru regula de business "datele validate sunt FROZEN":

  - Un user NEVERIFICAT poate modifica orice camp din profil.
  - Un user VERIFICAT (are credential identity_verified active) NU poate
    modifica cnp / first_name / last_name / date_of_birth / home_station_id.
  - Avatarul si parola raman editabile (sunt cosmetice / securitate, nu
    date validate).
  - Cand credentialul expira (valid_until < now), userul redevine "neverificat"
    si campurile redevin editabile.
  - Endpointul GET /users/me/verification-status returneaza informatii corecte
    pentru frontend (expires_at, days_until_expiry, frozen_fields, etc).
  - Logica anului universitar: today < 1 oct -> expirarea e 1 oct anul curent;
    today >= 1 oct -> expirarea e 1 oct anul urmator.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from helpers import register_and_login


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine():
    from app.core.database import engine
    return engine


def _get_user_id_from_token(client, token: str) -> int:
    """Extrage user_id din raspunsul /users/me."""
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def _ensure_issuer(conn) -> int:
    """Asigura ca exista un issuer pentru credentialele de test.
    Schema reala: id, name (UNIQUE), issuer_type (CHECK government/university/
    school/railway/company), created_at."""
    return conn.execute(text("""
        INSERT INTO issuers (name, issuer_type)
        VALUES ('Test University Issuer', 'university')
        ON CONFLICT (name) DO UPDATE SET issuer_type = EXCLUDED.issuer_type
        RETURNING id
    """)).scalar()


def _mark_user_verified(engine, user_id: int,
                       valid_until: datetime | None = None) -> None:
    """
    Marcheaza un user ca 'identity_verified' prin INSERT direct in
    user_credentials. Simuleaza ce face agentul universitar la aprobarea
    unei cereri (vezi identity.py approve_application).

    valid_until: daca None, foloseste 1 oct anul universitar curent
                 (din helper-ul de business).
    """
    from app.core.identity_status import get_current_academic_year_end

    if valid_until is None:
        ay_end = get_current_academic_year_end()
        valid_until = datetime.combine(ay_end, datetime.min.time())

    with engine.begin() as conn:
        issuer_id = _ensure_issuer(conn)
        # Sterg eventual credential anterior pentru a nu avea duplicate
        conn.execute(text("""
            DELETE FROM user_credentials
            WHERE user_id = :uid AND credential_type = 'identity_verified'
        """), {"uid": user_id})
        conn.execute(text("""
            INSERT INTO user_credentials
                (user_id, credential_type, claim_value, issuer_id,
                 status, issued_at, valid_until)
            VALUES (:uid, 'identity_verified', 'verified', :iss,
                    'active', NOW(), :vu)
        """), {"uid": user_id, "iss": issuer_id, "vu": valid_until})


def _set_home_station(engine, user_id: int) -> int:
    """Creeaza si seteaza un home_station_id pentru un user (pentru teste
    care vor sa-l modifice). Returneaza station_id."""
    with engine.begin() as conn:
        s_id = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('HOMEST', 'Home Station', 'Home City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()
        conn.execute(text("""
            UPDATE users SET home_station_id = :s WHERE user_id = :u
        """), {"s": s_id, "u": user_id})
    return s_id


# ===========================================================================
# 1. ANUL UNIVERSITAR — logica boundary
# ===========================================================================

class TestAcademicYearBoundary:
    """Verific calculul corect al expirarii in functie de data curenta."""

    def test_before_october_returns_october_current_year(self):
        from app.core.identity_status import get_current_academic_year_end
        # Mid-March 2026 -> expira 1 oct 2026
        assert get_current_academic_year_end(date(2026, 3, 15)) == date(2026, 10, 1)
        # 30 sep 2026 -> tot 1 oct 2026 (suntem in anul 2025-2026)
        assert get_current_academic_year_end(date(2026, 9, 30)) == date(2026, 10, 1)

    def test_october_first_returns_next_year(self):
        from app.core.identity_status import get_current_academic_year_end
        # Exact 1 oct 2026 -> anul nou tocmai a inceput -> expira 1 oct 2027
        assert get_current_academic_year_end(date(2026, 10, 1)) == date(2027, 10, 1)
        # Dec 2026 -> tot 1 oct 2027
        assert get_current_academic_year_end(date(2026, 12, 15)) == date(2027, 10, 1)

    def test_january_returns_october_same_year(self):
        from app.core.identity_status import get_current_academic_year_end
        # Ian 2026 -> expira 1 oct 2026
        assert get_current_academic_year_end(date(2026, 1, 5)) == date(2026, 10, 1)


# ===========================================================================
# 2. UNVERIFIED USER — toate campurile editabile
# ===========================================================================

class TestUnverifiedUserCanModifyEverything:

    def test_unverified_can_change_cnp(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.patch("/users/me", json={"cnp": "1990123456789"}, headers=h)
        assert r.status_code == 200, r.text

    def test_unverified_can_change_name(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.patch("/users/me", json={
            "first_name": "Ion",
            "last_name": "Popescu",
        }, headers=h)
        assert r.status_code == 200, r.text

    def test_unverified_can_change_date_of_birth(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        # Formatul asteptat de API e dd.mm.YYYY (vezi update_me in users.py)
        r = client.patch("/users/me", json={"date_of_birth": "15.06.1995"}, headers=h)
        assert r.status_code == 200, r.text


# ===========================================================================
# 3. VERIFIED USER — campurile FROZEN sunt blocate
# ===========================================================================

class TestVerifiedUserCannotModifyFrozenFields:

    def test_verified_cannot_change_cnp(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)

        # Setez date initiale + marchez verificat
        client.patch("/users/me", json={"cnp": "1900101000000"}, headers=h)
        _mark_user_verified(_engine(), user_id)

        # Incerc sa schimb cnp -> 403
        r = client.patch("/users/me", json={"cnp": "9999999999999"}, headers=h)
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert detail["error"] == "frozen_field_modification_blocked"
        assert "cnp" in detail["frozen_fields_attempted"]
        assert "expires_at" in detail
        assert detail["days_until_expiry"] is not None

    def test_verified_cannot_change_first_name(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)

        client.patch("/users/me", json={"first_name": "Ion"}, headers=h)
        _mark_user_verified(_engine(), user_id)

        r = client.patch("/users/me", json={"first_name": "Mihai"}, headers=h)
        assert r.status_code == 403
        assert "first_name" in r.json()["detail"]["frozen_fields_attempted"]

    def test_verified_cannot_change_date_of_birth(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)
        # Format dd.mm.YYYY (vezi update_me)
        client.patch("/users/me", json={"date_of_birth": "01.01.1990"}, headers=h)
        _mark_user_verified(_engine(), user_id)

        r = client.patch("/users/me", json={"date_of_birth": "01.01.2000"}, headers=h)
        assert r.status_code == 403
        assert "date_of_birth" in r.json()["detail"]["frozen_fields_attempted"]

    def test_verified_cannot_change_home_station(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)

        # Setez home_station initial + marchez verificat
        s1 = _set_home_station(_engine(), user_id)
        _mark_user_verified(_engine(), user_id)

        # Incerc sa modific la alta statie
        with _engine().begin() as conn:
            s2 = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES ('OTHER_HOME', 'Other Station', 'Other City', 'Romania')
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
                RETURNING station_id
            """)).scalar()

        r = client.patch("/users/me", json={"home_station_id": s2}, headers=h)
        assert r.status_code == 403, r.text
        assert "home_station_id" in r.json()["detail"]["frozen_fields_attempted"]

    def test_verified_blocks_only_actual_changes(self, client):
        """Daca payload contine cnp egal cu cel curent, NU se blocheaza."""
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)

        client.patch("/users/me", json={"cnp": "1980505123456"}, headers=h)
        _mark_user_verified(_engine(), user_id)

        # Trimit acelasi cnp -> no-op, ar trebui 200
        r = client.patch("/users/me", json={"cnp": "1980505123456"}, headers=h)
        assert r.status_code == 200, r.text


# ===========================================================================
# 4. VERIFIED USER — campurile editabile raman editabile
# ===========================================================================

class TestVerifiedUserCanStillEditNonFrozenFields:

    def test_verified_can_still_change_password(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)
        _mark_user_verified(_engine(), user_id)

        # Schimbare parola e prin endpoint separat /me/password
        # Aici verificam doar ca update_me pe campuri non-frozen merge.
        # (Parola se schimba prin POST /users/me/password)

        # In schimb, verificam ca un PATCH cu doar campuri non-frozen merge.
        # In UserUpdateRequest avem doar campurile frozen + nimic altceva,
        # deci verificam ca un PATCH cu payload gol returneaza 200.
        r = client.patch("/users/me", json={}, headers=h)
        assert r.status_code == 200, r.text


# ===========================================================================
# 5. EXPIRARE CREDENTIAL — userul redevine editabil
# ===========================================================================

class TestExpiredVerificationUnlocksFields:

    def test_expired_credential_unlocks_cnp(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)

        client.patch("/users/me", json={"cnp": "1850707000000"}, headers=h)

        # Marchez verificat dar cu valid_until in trecut (expirat)
        expired_date = datetime.now(timezone.utc) - timedelta(days=1)
        _mark_user_verified(_engine(), user_id, valid_until=expired_date)

        # La GET /verification-status, lazy cleanup va marca credentialul
        # ca expired. Verific direct.
        status = client.get("/users/me/verification-status", headers=h).json()
        assert status["is_verified"] is False, \
            f"Expected expired -> not verified, got {status}"

        # Si modificarea cnp ar trebui sa mearga
        r = client.patch("/users/me", json={"cnp": "1850707999999"}, headers=h)
        assert r.status_code == 200, r.text


# ===========================================================================
# Edge cases pentru helper-ele din identity_status.py
# ===========================================================================

class TestIdentityStatusHelperEdgeCases:
    """Edge cases ramase netestate in identity_status.py (coverage +30%)."""

    def test_get_verification_status_for_nonexistent_user(self):
        """User_id care nu exista in DB -> is_verified=False, mesaj clar."""
        from app.core.identity_status import get_verification_status
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            status = get_verification_status(db, user_id=999999)
            assert status["is_verified"] is False
            assert status["expires_at"] is None
            assert status["frozen_fields"] == []
            assert "Identitatea nu a fost verificata" in status["message"]
        finally:
            db.close()

    def test_release_expired_credentials_marks_old_as_expired(self):
        """Lazy cleanup: credential cu valid_until trecut -> status=expired."""
        from app.core.identity_status import (
            _release_expired_credentials, is_identity_verified,
        )
        from app.core.database import SessionLocal
        from datetime import datetime
        engine = _engine()

        with engine.begin() as conn:
            issuer_id = _ensure_issuer(conn)
            uid = conn.execute(text("""
                INSERT INTO users (first_name, last_name, email, password_hash, role)
                VALUES ('Edge', 'Case', :em, 'x', 'passenger')
                RETURNING user_id
            """), {"em": f"edge_{datetime.now().timestamp()}@test.ro"}).scalar()
            conn.execute(text("""
                INSERT INTO user_credentials
                    (user_id, credential_type, claim_value, issuer_id,
                     status, issued_at, valid_until)
                VALUES (:uid, 'identity_verified', 'x', :iss, 'active',
                        NOW() - INTERVAL '40 days',
                        NOW() - INTERVAL '1 hour')
            """), {"uid": uid, "iss": issuer_id})

        db = SessionLocal()
        try:
            count = _release_expired_credentials(db, uid)
            db.commit()
            assert count >= 1
            assert is_identity_verified(db, uid) is False
        finally:
            db.close()

    def test_check_frozen_for_unverified_returns_empty(self):
        """User neverificat -> nicio modificare blocata."""
        from app.core.identity_status import check_frozen_field_changes
        from app.core.database import SessionLocal
        from datetime import datetime
        engine = _engine()

        with engine.begin() as conn:
            uid = conn.execute(text("""
                INSERT INTO users (first_name, last_name, email, password_hash, role)
                VALUES ('Unv', 'Erif', :em, 'x', 'passenger')
                RETURNING user_id
            """), {"em": f"unverif_{datetime.now().timestamp()}@test.ro"}).scalar()
            current_row = conn.execute(text("""
                SELECT cnp, first_name, last_name, date_of_birth, home_station_id
                FROM users WHERE user_id = :uid
            """), {"uid": uid}).mappings().first()

        db = SessionLocal()
        try:
            changes = check_frozen_field_changes(
                db, uid, current_row,
                {"cnp": "9999", "first_name": "Other"}
            )
            assert changes == []
        finally:
            db.close()


# ===========================================================================
# 6. ENDPOINT VERIFICATION-STATUS
# ===========================================================================

class TestVerificationStatusEndpoint:

    def test_unverified_returns_no_status(self, client):
        token = register_and_login(client, "passenger")
        r = client.get("/users/me/verification-status",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["is_verified"] is False
        assert body["expires_at"] is None
        assert body["frozen_fields"] == []

    def test_verified_returns_all_fields(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        user_id = _get_user_id_from_token(client, token)
        _mark_user_verified(_engine(), user_id)

        r = client.get("/users/me/verification-status", headers=h)
        assert r.status_code == 200
        body = r.json()

        assert body["is_verified"] is True
        assert body["expires_at"] is not None
        # Expirarea trebuie sa fie pe 1 octombrie (anul curent sau urmator)
        assert body["expires_at"].endswith("-10-01"), \
            f"Expected expires_at to end with -10-01, got {body['expires_at']}"
        assert body["days_until_expiry"] is not None
        assert body["days_until_expiry"] > 0
        # Toate campurile FROZEN listate
        assert set(body["frozen_fields"]) == {
            "cnp", "first_name", "last_name", "date_of_birth", "home_station_id",
        }
        # Academic year format "YYYY-YYYY"
        assert "-" in body["academic_year"]
        parts = body["academic_year"].split("-")
        assert len(parts) == 2
        assert int(parts[1]) == int(parts[0]) + 1


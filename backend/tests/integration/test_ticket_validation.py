"""
Integration tests pentru endpoint-urile de VALIDARE BILETE.

Acopera:
  - POST /tickets/validate (single-use QR token + cere rol train_verifier)
  - GET /tickets/validations (history)
  - POST /tickets/quote (edge cases)

Testele sunt STRICTE — verifica fix-urile aplicate la BUG #1 si BUG #2:
  - BUG #2 (REPARAT): /tickets/validate cere strict rol train_verifier sau admin.
    Inainte oricare user autentificat putea valida bilete (privilege escalation).

Tinta: tickets.py 67% -> ~80% coverage.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from helpers import register_and_login, create_test_image_bytes


_seq = itertools.count(1)


def _engine():
    from app.core.database import engine
    return engine


def _get_user_id(client, token: str) -> int:
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()["user_id"]


def _make_verifier_with_fresh_token(client) -> str:
    """
    Register + promote to train_verifier in DB + fresh login.
    UUID4 elimina race conditions cand testele ruleaza in succesiune rapida.
    """
    email = f"verif_{uuid.uuid4().hex}@test.com"
    password = "ValidPass123!"

    reg = client.post("/auth/register", data={
        "email": email, "password": password,
        "first_name": "Test", "last_name": "Verifier",
        "phone": "+40721000001",
        "university_name": "Universitatea Politehnica Bucuresti (UPB)",
    }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
    assert reg.status_code in (200, 201), reg.text

    with _engine().begin() as conn:
        conn.execute(text(
            "UPDATE users SET role = 'train_verifier' WHERE email = :em"
        ), {"em": email})

    # Login fresh -> JWT cu noul rol (decode_token-ul foloseste role din token)
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _setup_route_with_train(engine, code_a: str, code_b: str) -> tuple[int, int, int]:
    nonce = next(_seq)
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": code_a, "n": f"VST A {nonce}"}).scalar()

        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": code_b, "n": f"VST B {nonce}"}).scalar()

        op_id = conn.execute(
            text("SELECT operator_id FROM railway_operators LIMIT 1")
        ).scalar()

        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 300)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {
            "rn": f"VR {nonce}", "rc": f"VR_{nonce}",
            "op": op_id, "s1": s1, "s2": s2,
        }).scalar()

        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 180, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET is_active = TRUE
            RETURNING train_id
        """), {"op": op_id, "rt": route_id, "tn": f"VT_{nonce}"}).scalar()

        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '09:00'::TIME, 0),
                   (:rt, :s2, 2, '13:00'::TIME, NULL, 300)
            ON CONFLICT (route_id, stop_order) DO UPDATE
                SET arrival_time = EXCLUDED.arrival_time,
                    departure_time = EXCLUDED.departure_time
        """), {"rt": route_id, "s1": s1, "s2": s2})

    return s1, s2, train_id


def _buy_ticket_and_get_token(client, token, train_id, s1, s2,
                               travel_date: date) -> tuple[int, str]:
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/tickets/buy", json={
        "train_id": train_id,
        "departure_station_id": s1,
        "arrival_station_id": s2,
        "travel_date": travel_date.isoformat(),
        "ticket_type": "single",
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    return body["ticket_id"], body["qr_token"]


# ===========================================================================
# 1. POST /tickets/validate — TESTE STRICTE dupa fix BUG #1 + #2
# ===========================================================================

class TestValidateTicket:

    def test_validate_valid_ticket_first_time(self, client):
        """Token valid + verifier -> result='valid'."""
        s1, s2, train_id = _setup_route_with_train(_engine(), "VAL_A1", "VAL_B1")
        future = date.today()

        pas_token = register_and_login(client, "pass1")
        _, qr_token = _buy_ticket_and_get_token(
            client, pas_token, train_id, s1, s2, future
        )

        ver_token = _make_verifier_with_fresh_token(client)
        h = {"Authorization": f"Bearer {ver_token}"}
        r = client.post("/tickets/validate", json={
            "token": qr_token,
            "device_id": "mobile-test-001",
        }, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"] == "valid", body

    def test_validate_same_token_twice_marks_already_used(self, client):
        """Single-use: a doua validare -> already_used."""
        s1, s2, train_id = _setup_route_with_train(_engine(), "VAL_A2", "VAL_B2")
        future = date.today()

        pas_token = register_and_login(client, "pass2")
        _, qr_token = _buy_ticket_and_get_token(
            client, pas_token, train_id, s1, s2, future
        )

        ver_token = _make_verifier_with_fresh_token(client)
        h = {"Authorization": f"Bearer {ver_token}"}

        r1 = client.post("/tickets/validate", json={"token": qr_token}, headers=h)
        assert r1.json()["result"] == "valid"

        r2 = client.post("/tickets/validate", json={"token": qr_token}, headers=h)
        assert r2.json()["result"] == "already_used"

    def test_validate_garbage_token_returns_invalid(self, client):
        """Token inexistent -> result='invalid' (NU 'valid')."""
        ver_token = _make_verifier_with_fresh_token(client)
        h = {"Authorization": f"Bearer {ver_token}"}
        r = client.post("/tickets/validate", json={
            "token": "GARBAGE_TOKEN_NEVER_EXISTED:xyz",
        }, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "invalid"

    def test_validate_passenger_role_rejected_403(self, client):
        """
        BUG #2 (REPARAT): pasagerii NU pot valida bilete.
        Inainte de fix: orice user autentificat era acceptat (privilege escalation).
        Dupa fix: cere strict train_verifier sau admin -> 403 pentru passenger.
        """
        s1, s2, train_id = _setup_route_with_train(_engine(), "VAL_A3", "VAL_B3")
        future = date.today()

        pas_token = register_and_login(client, "pass3")
        _, qr_token = _buy_ticket_and_get_token(
            client, pas_token, train_id, s1, s2, future
        )

        other_token = register_and_login(client, "other_pass")
        h = {"Authorization": f"Bearer {other_token}"}
        r = client.post("/tickets/validate", json={"token": qr_token}, headers=h)
        assert r.status_code == 403, r.text

    def test_validate_requires_auth(self, client):
        r = client.post("/tickets/validate", json={"token": "x"})
        assert r.status_code in (401, 403, 422)


# ===========================================================================
# 2. GET /tickets/validations (history)
# ===========================================================================

class TestValidationsHistory:

    def test_history_returns_list_for_new_user(self, client):
        token = register_and_login(client, "newuser_hist")
        h = {"Authorization": f"Bearer {token}"}
        r = client.get("/tickets/validations", headers=h)
        if r.status_code == 404:
            pytest.skip("Path /tickets/validations nu exista in API")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_history_requires_auth(self, client):
        r = client.get("/tickets/validations")
        assert r.status_code != 200


# ===========================================================================
# 3. POST /tickets/quote
# ===========================================================================

class TestQuoteEdgeCases:

    def test_quote_with_same_stations_rejected(self, client):
        """Plecare = sosire -> 400."""
        s1, _, train_id = _setup_route_with_train(_engine(), "PX_A1", "PX_B1")
        token = register_and_login(client, "px_same")
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/tickets/quote", json={
            "train_id": train_id,
            "departure_station_id": s1,
            "arrival_station_id": s1,
        }, headers=h)
        assert r.status_code in (400, 422), r.text

    def test_quote_requires_auth(self, client):
        r = client.post("/tickets/quote", json={
            "train_id": 1,
            "departure_station_id": 1,
            "arrival_station_id": 2,
        })
        assert r.status_code in (401, 403, 422)

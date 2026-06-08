"""
Integration tests pentru edge cases la cancel/reschedule (linii ramase netestate).

Tinta: tickets.py 80% -> ~88%, global 79% -> 80%+.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date, timedelta

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


def _setup_route(engine, code_a: str, code_b: str) -> tuple[int, int, int]:
    """Returns (s1, s2, train_id)."""
    nonce = uuid.uuid4().hex[:8]  # unique per call across runs
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": code_a, "n": f"LC A {nonce}"}).scalar()
        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'City', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """), {"c": code_b, "n": f"LC B {nonce}"}).scalar()

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
        """), {"rn": f"LR {nonce}", "rc": f"LR_{nonce}", "op": op_id, "s1": s1, "s2": s2}).scalar()

        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 180, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET is_active = TRUE
            RETURNING train_id
        """), {"op": op_id, "rt": route_id, "tn": f"LT_{nonce}"}).scalar()

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


def _buy_ticket(client, token, train_id, s1, s2, travel_date):
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/tickets/buy", json={
        "train_id": train_id,
        "departure_station_id": s1,
        "arrival_station_id": s2,
        "travel_date": travel_date.isoformat(),
        "ticket_type": "single",
    }, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ===========================================================================
# Cancel edge cases
# ===========================================================================

class TestCancelEdgeCases:

    def test_cancel_nonexistent_ticket_404(self, client):
        """Cancel pe ID inexistent -> 404."""
        token = register_and_login(client, "cancel_nonex")
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/tickets/999999/cancel", headers=h)
        assert r.status_code == 404, r.text

    def test_cancel_other_user_ticket_403(self, client):
        """Anularea biletului altui user -> 403."""
        s1, s2, train_id = _setup_route(_engine(), "LC_OWN_A", "LC_OWN_B")
        future = date.today() + timedelta(days=10)

        owner = register_and_login(client, "owner")
        ticket = _buy_ticket(client, owner, train_id, s1, s2, future)
        tid = ticket["ticket_id"]

        attacker = register_and_login(client, "attacker")
        h = {"Authorization": f"Bearer {attacker}"}
        r = client.post(f"/tickets/{tid}/cancel", headers=h)
        assert r.status_code in (403, 404), r.text

    def test_cancel_already_cancelled_409(self, client):
        """A doua cancel pe acelasi bilet -> 409."""
        s1, s2, train_id = _setup_route(_engine(), "LC_DBL_A", "LC_DBL_B")
        future = date.today() + timedelta(days=10)

        token = register_and_login(client, "dbl_cancel")
        h = {"Authorization": f"Bearer {token}"}
        ticket = _buy_ticket(client, token, train_id, s1, s2, future)
        tid = ticket["ticket_id"]

        r1 = client.post(f"/tickets/{tid}/cancel", headers=h)
        assert r1.status_code == 200

        r2 = client.post(f"/tickets/{tid}/cancel", headers=h)
        assert r2.status_code == 409, r2.text


# ===========================================================================
# Reschedule edge cases
# ===========================================================================

class TestRescheduleEdgeCases:

    def test_reschedule_nonexistent_ticket_404(self, client):
        token = register_and_login(client, "rs_nonex")
        h = {"Authorization": f"Bearer {token}"}
        future = date.today() + timedelta(days=5)
        r = client.post("/tickets/999999/reschedule", json={
            "new_train_id": 1,
            "new_travel_date": future.isoformat(),
        }, headers=h)
        assert r.status_code == 404, r.text

    def test_reschedule_other_user_ticket_403(self, client):
        s1, s2, train_id = _setup_route(_engine(), "RS_OWN_A", "RS_OWN_B")
        future = date.today() + timedelta(days=10)

        owner = register_and_login(client, "rs_owner")
        ticket = _buy_ticket(client, owner, train_id, s1, s2, future)
        tid = ticket["ticket_id"]

        attacker = register_and_login(client, "rs_attacker")
        h = {"Authorization": f"Bearer {attacker}"}
        r = client.post(f"/tickets/{tid}/reschedule", json={
            "new_train_id": train_id,
            "new_travel_date": (future + timedelta(days=1)).isoformat(),
        }, headers=h)
        assert r.status_code in (403, 404), r.text

    def test_reschedule_to_invalid_date_format_400(self, client):
        s1, s2, train_id = _setup_route(_engine(), "RS_DT_A", "RS_DT_B")
        future = date.today() + timedelta(days=10)

        token = register_and_login(client, "rs_dt")
        h = {"Authorization": f"Bearer {token}"}
        ticket = _buy_ticket(client, token, train_id, s1, s2, future)
        tid = ticket["ticket_id"]

        r = client.post(f"/tickets/{tid}/reschedule", json={
            "new_train_id": train_id,
            "new_travel_date": "not-a-date",
        }, headers=h)
        assert r.status_code in (400, 422), r.text

    def test_reschedule_requires_auth(self, client):
        r = client.post("/tickets/1/reschedule", json={
            "new_train_id": 1,
            "new_travel_date": "2026-01-01",
        })
        assert r.status_code in (401, 403, 422)

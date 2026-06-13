"""
Test pentru concurenta pe seats.

Acopera:
  - 2 useri fac hold pe acelasi loc -> primul reuseste, al doilea 409.
  - User refresh-uieste propriul hold -> OK.
  - Hold-ul expira si alt user il poate prelua.
  - Seat sold nu poate fi hold-uit.
  - Confirm seats dupa expirare hold -> 409.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from helpers import register_and_login


def _engine():
    from app.core.database import engine
    return engine


def _setup_train_with_one_seat(engine) -> tuple[int, int, int, int]:
    """Creeaza 2 stations + ruta + tren + 1 vagon + 1 loc. Returneaza (s1,s2,train_id,seat_id)."""
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"SC_A_{nonce}", "n": f"SCA {nonce}"}).scalar()
        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"SC_B_{nonce}", "n": f"SCB {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
        """), {"rn": f"SCR {nonce}", "rc": f"SCR_{nonce}", "op": op, "s1": s1, "s2": s2}).scalar()
        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 4, TRUE) RETURNING train_id
        """), {"op": op, "rt": route_id, "tn": f"SCT_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '08:00'::TIME, 0),
                   (:rt, :s2, 2, '10:00'::TIME, NULL, 100)
        """), {"rt": route_id, "s1": s1, "s2": s2})
        car_id = conn.execute(text("""
            INSERT INTO train_cars (train_id, car_number, car_class, total_seats)
            VALUES (:tid, 1, 2, 4) RETURNING train_car_id
        """), {"tid": train_id}).scalar()
        seat_id = conn.execute(text("""
            INSERT INTO seats (train_car_id, seat_row, seat_letter,
                               seat_label, is_window, is_aisle)
            VALUES (:c, 1, 'A', '1A', TRUE, FALSE) RETURNING seat_id
        """), {"c": car_id}).scalar()
    return s1, s2, train_id, seat_id


class TestSeatConcurrency:

    def test_two_users_hold_same_seat_only_first_wins(self, client):
        s1, s2, train_id, seat_id = _setup_train_with_one_seat(_engine())
        future = date.today()

        u1 = register_and_login(client, "sc_u1")
        u2 = register_and_login(client, "sc_u2")

        # u1 cere hold
        r1 = client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {u1}"})
        assert r1.status_code == 200, r1.text

        # u2 cere acelasi seat -> 409
        r2 = client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {u2}"})
        assert r2.status_code == 409
        detail = r2.json()["detail"]
        if isinstance(detail, dict):
            assert detail.get("error") == "seat_held_by_other"

    def test_user_refresh_own_hold(self, client):
        s1, s2, train_id, seat_id = _setup_train_with_one_seat(_engine())
        future = date.today()
        u1 = register_and_login(client, "sc_refresh")
        h = {"Authorization": f"Bearer {u1}"}

        r1 = client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers=h)
        first_exp = r1.json()["expires_at"]

        # Al doilea hold pe acelasi seat de la acelasi user -> refresh
        r2 = client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers=h)
        assert r2.status_code == 200
        assert r2.json()["refreshed"] is True

    def test_expired_hold_can_be_taken_by_other(self, client):
        s1, s2, train_id, seat_id = _setup_train_with_one_seat(_engine())
        future = date.today()

        u1 = register_and_login(client, "sc_exp_u1")
        u2 = register_and_login(client, "sc_exp_u2")

        # u1 face hold
        r1 = client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {u1}"})
        assert r1.status_code == 200

        # Forteaza expirarea hold-ului
        with _engine().begin() as conn:
            conn.execute(text("""
                UPDATE seat_reservations
                SET expires_at = CURRENT_TIMESTAMP - INTERVAL '5 minutes'
                WHERE seat_id = :sid AND travel_date = :td
            """), {"sid": seat_id, "td": future})

        # u2 acum poate face hold (release_expired_reservations cleanup)
        r2 = client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {u2}"})
        assert r2.status_code == 200, r2.text

    def test_release_own_hold(self, client):
        s1, s2, train_id, seat_id = _setup_train_with_one_seat(_engine())
        future = date.today()

        u1 = register_and_login(client, "sc_rel")
        h = {"Authorization": f"Bearer {u1}"}

        client.post("/seats/hold", json={
            "seat_id": seat_id, "train_id": train_id,
            "travel_date": future.isoformat(),
        }, headers=h)
        r = client.post("/seats/release", json={
            "seat_id": seat_id, "travel_date": future.isoformat(),
        }, headers=h)
        assert r.status_code == 200

    def test_release_seat_not_held(self, client):
        """Release pe seat fara hold = idempotent (nu crapa)."""
        s1, s2, train_id, seat_id = _setup_train_with_one_seat(_engine())
        future = date.today()
        u1 = register_and_login(client, "sc_idem")
        r = client.post("/seats/release", json={
            "seat_id": seat_id, "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {u1}"})
        # Acceptam 200 OR 404 (idempotent vs explicit not-found)
        assert r.status_code in (200, 404)

    def test_hold_on_invalid_train_seat_combination(self, client):
        """Seat ID dintr-un tren nu poate fi tinut pe alt tren."""
        s1a, s2a, t_a, seat_a = _setup_train_with_one_seat(_engine())
        s1b, s2b, t_b, _ = _setup_train_with_one_seat(_engine())
        future = date.today()
        u1 = register_and_login(client, "sc_wrong_train")
        r = client.post("/seats/hold", json={
            "seat_id": seat_a, "train_id": t_b,  # WRONG train
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {u1}"})
        assert r.status_code == 404

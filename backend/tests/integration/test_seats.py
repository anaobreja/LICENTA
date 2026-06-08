"""
Integration tests pentru noua functionalitate de bilete:
  - Anti-overlap (intervale orare suprapuse)
  - Seat hold/release (rezervare temporara 5 min)
  - Cancel + refund (trepte CFR: full / half / none)
  - Reschedule (acelasi traseu, alt tren)

Toate testele folosesc DB-ul de test creat fresh per sesiune (schema.sql care
contine deja migrarea 06), deci avem train_cars + seats backfill-uite pentru
trenurile din seed_demo.sql.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from helpers import register_and_login


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db(client):
    """Returneaza engine-ul SQLAlchemy din aplicatie (folosit pentru queries directe)."""
    from app.core.database import engine
    return engine


def _ensure_test_infrastructure(conn) -> tuple[int, int, int]:
    """
    Asigura existenta unui operator + 2 statii pentru teste.
    DB-ul de test fresh nu are railway_operators si stations (sunt incarcate
    doar de import_cfr.py in productie).
    Idempotent: foloseste ON CONFLICT.
    Returneaza (operator_id, station_1_id, station_2_id).
    """
    op_id = conn.execute(text("""
        INSERT INTO railway_operators (code, name)
        VALUES ('TEST_OP', 'Test Railway Operator')
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
        RETURNING operator_id
    """)).scalar()
    s1 = conn.execute(text("""
        INSERT INTO stations (code, name, city, country)
        VALUES ('TST01', 'Test Origin Station', 'Test City A', 'Romania')
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
        RETURNING station_id
    """)).scalar()
    s2 = conn.execute(text("""
        INSERT INTO stations (code, name, city, country)
        VALUES ('TST02', 'Test Destination Station', 'Test City B', 'Romania')
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
        RETURNING station_id
    """)).scalar()
    return op_id, s1, s2


# Counter global pentru a evita coliziuni de UNIQUE (route_code, train_number)
# in teste consecutive care insereaza pe acelasi DB
import itertools
_seq = itertools.count(1)


def _seed_two_trains_same_window(engine, base_date: date) -> tuple[int, int]:
    """
    Creeaza 2 trenuri pe acelasi interval orar (08:00–12:00) ca sa testam overlap.
    Creeaza operatorul, statiile si route_stops cu departure/arrival times.

    Returneaza (train_a_id, train_b_id) — ambele trenuri au:
      - Trenul A: 08:00 -> 12:00 (regio)
      - Trenul B: 10:00 -> 14:00 (regio, overlap cu A: 10-12)
    """
    nonce = next(_seq)
    with engine.begin() as conn:
        op_id, s1, s2 = _ensure_test_infrastructure(conn)

        # Creeaza ruta — route_code trebuie UNIQUE
        route_id = conn.execute(
            text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 200)
                RETURNING route_id
            """),
            {
                "rn": f"TEST_OVERLAP_{nonce}",
                "rc": f"TEST_R_{nonce}",
                "op": op_id, "s1": s1, "s2": s2,
            },
        ).scalar()

        # Trenul A — 08:00 -> 12:00 (folosim 'regio' care trece check constraint)
        a_id = conn.execute(
            text("""
                INSERT INTO trains (train_number, train_type, operator_id, route_id,
                                    capacity_seats, is_active)
                VALUES (:tn, 'regio', :op, :rt, 180, TRUE)
                RETURNING train_id
            """),
            {"tn": f"TEST-A-{nonce}", "op": op_id, "rt": route_id},
        ).scalar()

        # Trenul B — 10:00 -> 14:00 (acelasi route, deci acelasi traseu)
        b_id = conn.execute(
            text("""
                INSERT INTO trains (train_number, train_type, operator_id, route_id,
                                    capacity_seats, is_active)
                VALUES (:tn, 'regio', :op, :rt, 180, TRUE)
                RETURNING train_id
            """),
            {"tn": f"TEST-B-{nonce}", "op": op_id, "rt": route_id},
        ).scalar()

        # route_stops — sunt pe RUTA, nu pe tren!
        # Asta inseamna ca toate trenurile pe aceeasi ruta au aceleasi ore.
        # Pentru testul de overlap, fiecare tren are nevoie de RUTA proprie ca
        # sa aiba ore diferite. Refacem trenul B pe alta ruta cu alte ore.

        # Sterg trenul B si refac pe ruta diferita
        conn.execute(text("DELETE FROM trains WHERE train_id = :tid"), {"tid": b_id})
        route_b = conn.execute(
            text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 200)
                RETURNING route_id
            """),
            {
                "rn": f"TEST_OVERLAP_B_{nonce}",
                "rc": f"TEST_RB_{nonce}",
                "op": op_id, "s1": s1, "s2": s2,
            },
        ).scalar()
        b_id = conn.execute(
            text("""
                INSERT INTO trains (train_number, train_type, operator_id, route_id,
                                    capacity_seats, is_active)
                VALUES (:tn, 'regio', :op, :rt, 180, TRUE)
                RETURNING train_id
            """),
            {"tn": f"TEST-B-{nonce}", "op": op_id, "rt": route_b},
        ).scalar()

        # Adaug stop-uri pentru ruta A: plecare 08:00, sosire 12:00
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time)
            VALUES
                (:rt, :s1, 1, NULL, '08:00'::TIME),
                (:rt, :s2, 2, '12:00'::TIME, NULL)
        """), {"rt": route_id, "s1": s1, "s2": s2})

        # Adaug stop-uri pentru ruta B: plecare 10:00, sosire 14:00
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time)
            VALUES
                (:rt, :s1, 1, NULL, '10:00'::TIME),
                (:rt, :s2, 2, '14:00'::TIME, NULL)
        """), {"rt": route_b, "s1": s1, "s2": s2})

        # Genereaza layout pentru ambele
        conn.execute(text("SELECT generate_train_layout(:t)"), {"t": a_id})
        conn.execute(text("SELECT generate_train_layout(:t)"), {"t": b_id})

    return a_id, b_id


def _get_first_free_seat(engine, train_id: int) -> tuple[int, str]:
    """Returneaza (seat_id, seat_label) pentru primul loc al unui tren."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT s.seat_id, s.seat_label
                FROM seats s
                JOIN train_cars tc ON tc.train_car_id = s.train_car_id
                WHERE tc.train_id = :tid
                ORDER BY tc.car_number, s.seat_row, s.seat_letter
                LIMIT 1
            """),
            {"tid": train_id},
        ).first()
    assert row, f"Trenul {train_id} nu are locuri generate"
    return row[0], row[1]


def _route_endpoints(engine, train_id: int) -> tuple[int, int]:
    """Returneaza (origin_station_id, destination_station_id) pentru un tren."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT r.origin_station_id, r.destination_station_id
                FROM trains t JOIN routes r ON r.route_id = t.route_id
                WHERE t.train_id = :tid
            """),
            {"tid": train_id},
        ).first()
    assert row, f"Trenul {train_id} nu are ruta"
    return row[0], row[1]


# ===========================================================================
# 1. ANTI-OVERLAP
# ===========================================================================

class TestAntiOverlap:
    """Verifica ca un user nu poate avea 2 bilete in intervale orare suprapuse."""

    def test_overlap_same_train_blocked(self, client):
        """Cumpararea aceluiasi bilet de 2 ori -> 409."""
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        body = {
            "train_id": a_id,
            "departure_station_id": orig,
            "arrival_station_id": dest,
            "travel_date": future.isoformat(),
            "ticket_type": "single",
        }
        # Primul bilet — OK
        r1 = client.post("/tickets/buy", json=body, headers=h)
        assert r1.status_code == 200, r1.text

        # Al doilea bilet pe acelasi tren / aceeasi data -> overlap (409)
        r2 = client.post("/tickets/buy", json=body, headers=h)
        assert r2.status_code == 409
        detail = r2.json()["detail"]
        assert detail["error"] == "overlap"
        assert "conflicting_ticket_id" in detail

    def test_overlap_partial_blocked(self, client):
        """Trenuri pe acelasi interval orar (08-12 si 10-14) — overlap real."""
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, b_id = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        # Bilet pentru A (08-12)
        r1 = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        assert r1.status_code == 200

        # Bilet pentru B (10-14) — overlap 10-12 -> 409
        r2 = client.post("/tickets/buy", json={
            "train_id": b_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        assert r2.status_code == 409, r2.text

    def test_no_overlap_different_dates(self, client):
        """Acelasi tren, date diferite -> no overlap."""
        engine = _get_db(client)
        a_id, _ = _seed_two_trains_same_window(engine, date.today())
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        d1 = (date.today() + timedelta(days=10)).isoformat()
        d2 = (date.today() + timedelta(days=11)).isoformat()

        body = lambda d: {
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": d,
            "ticket_type": "single",
        }
        r1 = client.post("/tickets/buy", json=body(d1), headers=h)
        r2 = client.post("/tickets/buy", json=body(d2), headers=h)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text  # Date diferite => OK

    def test_overlap_blocked_for_same_user_not_others(self, client):
        """Userul A are bilet — userul B poate cumpara pe acelasi tren fara probleme."""
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token_a = register_and_login(client, "passenger")
        token_b = register_and_login(client, "passenger")
        body = {
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }
        r1 = client.post("/tickets/buy", json=body, headers={"Authorization": f"Bearer {token_a}"})
        r2 = client.post("/tickets/buy", json=body, headers={"Authorization": f"Bearer {token_b}"})
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text  # User diferit => OK


# ===========================================================================
# 2. REFUND TIERS
# ===========================================================================

class TestRefundTiers:
    """Verifica calculul refund-ului direct prin functia helper (unit-like)."""

    def test_refund_full_for_distant_departure(self):
        from app.services.ticket_business import compute_refund
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        dep = now + timedelta(hours=25)
        amount, tier = compute_refund(100.0, dep, now=now)
        assert tier == "full"
        assert amount == 100.0

    def test_refund_half_for_close_departure(self):
        from app.services.ticket_business import compute_refund
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        dep = now + timedelta(hours=10)
        amount, tier = compute_refund(80.0, dep, now=now)
        assert tier == "half"
        assert amount == 40.0

    def test_refund_none_after_departure(self):
        from app.services.ticket_business import compute_refund
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        dep = now - timedelta(hours=1)
        amount, tier = compute_refund(50.0, dep, now=now)
        assert tier == "none"
        assert amount == 0.0


# ===========================================================================
# 3. CANCEL endpoint
# ===========================================================================

class TestCancelTicket:
    """Verifica endpoint-ul POST /tickets/{id}/cancel."""

    def test_cancel_active_ticket_full_refund(self, client):
        engine = _get_db(client)
        # Tren peste 14 zile (>24h) => full refund
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        assert r.status_code == 200, r.text
        ticket_id = r.json()["ticket_id"]
        original_price = float(r.json()["price"])

        # Anuleaza
        cancel = client.post(f"/tickets/{ticket_id}/cancel", headers=h)
        assert cancel.status_code == 200, cancel.text
        body = cancel.json()
        assert body["status"] == "cancelled"
        assert body["refund_tier"] == "full"
        assert abs(float(body["refund_amount"]) - original_price) < 0.01

    def test_cannot_cancel_twice(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        ticket_id = r.json()["ticket_id"]

        # Prima anulare — OK
        c1 = client.post(f"/tickets/{ticket_id}/cancel", headers=h)
        assert c1.status_code == 200
        # A doua — 409 invalid_status
        c2 = client.post(f"/tickets/{ticket_id}/cancel", headers=h)
        assert c2.status_code == 409

    def test_cannot_cancel_other_users_ticket(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token_a = register_and_login(client, "passenger")
        token_b = register_and_login(client, "passenger")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}

        r = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=ha)
        ticket_id = r.json()["ticket_id"]

        # User B incearca sa anuleze biletul lui A
        c = client.post(f"/tickets/{ticket_id}/cancel", headers=hb)
        assert c.status_code == 403

    def test_cancel_after_overlap_allows_rebuy(self, client):
        """Dupa cancel, locul si intervalul orar redevin libere => poti recumpara."""
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}
        body = {
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }
        r1 = client.post("/tickets/buy", json=body, headers=h)
        ticket1 = r1.json()["ticket_id"]

        # Dovedim ca a doua tranzactie e respinsa
        r_dup = client.post("/tickets/buy", json=body, headers=h)
        assert r_dup.status_code == 409

        # Anulam primul bilet
        cancel = client.post(f"/tickets/{ticket1}/cancel", headers=h)
        assert cancel.status_code == 200

        # Acum putem cumpara din nou
        r2 = client.post("/tickets/buy", json=body, headers=h)
        assert r2.status_code == 200, r2.text


# ===========================================================================
# 4. SEAT HOLD / RELEASE / CONFLICT
# ===========================================================================

class TestSeatHoldFlow:

    def test_get_seats_layout_returns_cars_and_seats(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(
            f"/trains/{a_id}/seats?travel_date={future.isoformat()}",
            headers=h,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "cars" in data and "summary" in data and "train" in data
        assert data["summary"]["total"] == 180  # R = 3 vagoane x 60 = 180
        # Toate locurile pornesc 'free' (nimic nu e cumparat/tinut inca)
        assert data["summary"]["free"] == 180
        assert data["summary"]["sold"] == 0

    def test_hold_seat_changes_status_to_mine_held(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        seat_id, seat_label = _get_first_free_seat(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        hold = client.post("/seats/hold", json={
            "train_id": a_id, "seat_id": seat_id,
            "travel_date": future.isoformat(),
        }, headers=h)
        assert hold.status_code == 200, hold.text

        layout = client.get(
            f"/trains/{a_id}/seats?travel_date={future.isoformat()}",
            headers=h,
        ).json()
        # Caut locul si verific statusul
        all_seats = [s for car in layout["cars"] for s in car["seats"]]
        target = next(s for s in all_seats if s["seat_id"] == seat_id)
        assert target["status"] == "mine_held"
        assert layout["summary"]["held"] == 1
        assert layout["summary"]["mine"] == 1

    def test_release_seat_returns_to_free(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        seat_id, _ = _get_first_free_seat(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        client.post("/seats/hold", json={
            "train_id": a_id, "seat_id": seat_id,
            "travel_date": future.isoformat(),
        }, headers=h)

        rel = client.post("/seats/release", json={
            "seat_id": seat_id, "travel_date": future.isoformat(),
        }, headers=h)
        assert rel.status_code == 200
        assert rel.json()["released"] is True

        layout = client.get(
            f"/trains/{a_id}/seats?travel_date={future.isoformat()}",
            headers=h,
        ).json()
        target = next(s for car in layout["cars"] for s in car["seats"] if s["seat_id"] == seat_id)
        assert target["status"] == "free"

    def test_held_by_other_user_blocks_hold(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        seat_id, _ = _get_first_free_seat(engine, a_id)

        token_a = register_and_login(client, "passenger")
        token_b = register_and_login(client, "passenger")

        # User A pune hold
        r_a = client.post("/seats/hold", json={
            "train_id": a_id, "seat_id": seat_id,
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {token_a}"})
        assert r_a.status_code == 200

        # User B incearca acelasi loc — 409
        r_b = client.post("/seats/hold", json={
            "train_id": a_id, "seat_id": seat_id,
            "travel_date": future.isoformat(),
        }, headers={"Authorization": f"Bearer {token_b}"})
        assert r_b.status_code == 409
        assert r_b.json()["detail"]["error"] == "seat_held_by_other"

    def test_buy_with_seats_marks_them_sold(self, client):
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)
        seat_id, _ = _get_first_free_seat(engine, a_id)
        orig, dest = _route_endpoints(engine, a_id)

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        # Hold
        hold = client.post("/seats/hold", json={
            "train_id": a_id, "seat_id": seat_id,
            "travel_date": future.isoformat(),
        }, headers=h)
        assert hold.status_code == 200

        # Buy cu seat_ids
        buy = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single", "seat_ids": [seat_id],
        }, headers=h)
        assert buy.status_code == 200, buy.text

        # Verificam ca seat e acum sold
        layout = client.get(
            f"/trains/{a_id}/seats?travel_date={future.isoformat()}",
            headers=h,
        ).json()
        target = next(s for car in layout["cars"] for s in car["seats"] if s["seat_id"] == seat_id)
        assert target["status"] == "mine_sold"
        assert layout["summary"]["sold"] == 1


# ===========================================================================
# 5. RESCHEDULE
# ===========================================================================

class TestRescheduleTicket:

    def test_reschedule_same_route_ok(self, client):
        """Reprogramare pe alt tren cu acelasi traseu — OK."""
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, b_id = _seed_two_trains_same_window(engine, future)
        orig, dest = _route_endpoints(engine, a_id)
        new_date = (future + timedelta(days=2)).isoformat()

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        # Cumpar bilet pe A
        r = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        ticket_id = r.json()["ticket_id"]

        # Reprogramez pe B la alta data
        resp = client.post(f"/tickets/{ticket_id}/reschedule", json={
            "new_train_id": b_id,
            "new_travel_date": new_date,
        }, headers=h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["new_train_id"] == b_id
        assert body["new_travel_date"] == new_date

        # Biletul vechi e marcat 'rescheduled'
        with engine.connect() as conn:
            old_status = conn.execute(
                text("SELECT ticket_status FROM tickets WHERE ticket_id=:tid"),
                {"tid": ticket_id},
            ).scalar()
        assert old_status == "rescheduled"

    def test_reschedule_different_route_rejected(self, client):
        """Reprogramare pe tren cu alt traseu — 409 different_route."""
        engine = _get_db(client)
        future = date.today() + timedelta(days=14)
        a_id, _ = _seed_two_trains_same_window(engine, future)

        # Adaug un al treilea tren pe traseu DIFERIT — folosim 2 statii NOI
        # (fixture-ul de baza creeaza doar TST01/TST02, ne trebuie altele).
        nonce = next(_seq)
        with engine.begin() as conn:
            op_id = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
            s_new1 = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'Diff City A', 'Romania')
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
                RETURNING station_id
            """), {"c": f"DIFF1_{nonce}", "n": f"Diff Origin {nonce}"}).scalar()
            s_new2 = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'Diff City B', 'Romania')
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
                RETURNING station_id
            """), {"c": f"DIFF2_{nonce}", "n": f"Diff Dest {nonce}"}).scalar()

            route2 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 300)
                RETURNING route_id
            """), {
                "rn": f"DIFF_ROUTE_{nonce}", "rc": f"DIFF_RC_{nonce}",
                "op": op_id, "s1": s_new1, "s2": s_new2,
            }).scalar()

            c_id = conn.execute(text("""
                INSERT INTO trains (train_number, train_type, operator_id, route_id,
                                    capacity_seats, is_active)
                VALUES (:tn, 'regio', :op, :rt, 180, TRUE)
                RETURNING train_id
            """), {"tn": f"TEST-C-{nonce}", "op": op_id, "rt": route2}).scalar()

            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time)
                VALUES
                    (:rt, :s1, 1, NULL, '15:00'::TIME),
                    (:rt, :s2, 2, '19:00'::TIME, NULL)
            """), {"rt": route2, "s1": s_new1, "s2": s_new2})
            conn.execute(text("SELECT generate_train_layout(:t)"), {"t": c_id})

        orig, dest = _route_endpoints(engine, a_id)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.post("/tickets/buy", json={
            "train_id": a_id, "departure_station_id": orig,
            "arrival_station_id": dest, "travel_date": future.isoformat(),
            "ticket_type": "single",
        }, headers=h)
        ticket_id = r.json()["ticket_id"]

        # Trenul C are alt traseu — reschedule respins
        resp = client.post(f"/tickets/{ticket_id}/reschedule", json={
            "new_train_id": c_id,
            "new_travel_date": future.isoformat(),
        }, headers=h)
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error"] == "different_route"

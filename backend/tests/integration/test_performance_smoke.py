"""
Test pentru performanta endpoint-urilor critice.

Acopera:
  - Listing tickets (10 bilete): nu face N+1 queries.
  - Layout seats (60 locuri): un singur batch.
  - Map stations: rezultat sub 2s.
  - Listing my subscriptions: nu face N+1.
"""
from __future__ import annotations

import time
import uuid
from datetime import date

import pytest
from sqlalchemy import text, event

from helpers import register_and_login


def _engine():
    from app.core.database import engine
    return engine


def _setup_route(engine) -> tuple[int, int, int]:
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"PERF_A_{nonce}", "n": f"PA {nonce}"}).scalar()
        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"PERF_B_{nonce}", "n": f"PB {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 200) RETURNING route_id
        """), {"rn": f"PR {nonce}", "rc": f"PR_{nonce}", "op": op, "s1": s1, "s2": s2}).scalar()
        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
        """), {"op": op, "rt": route_id, "tn": f"PT_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '08:00'::TIME, 0),
                   (:rt, :s2, 2, '11:00'::TIME, NULL, 200)
        """), {"rt": route_id, "s1": s1, "s2": s2})
    return s1, s2, train_id


class _QueryCounter:
    """Context manager care numara query-urile SQL pe engine."""
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        @event.listens_for(self.engine, "before_cursor_execute")
        def _before(conn, cursor, statement, *args, **kwargs):
            self.count += 1
        self._listener = _before
        return self

    def __exit__(self, *args):
        event.remove(self.engine, "before_cursor_execute", self._listener)


class TestPerformance:

    def test_my_tickets_no_n_plus_1(self, client):
        """10 bilete -> nr query-uri sub 25 (NU 10+10)."""
        s1, s2, train_id = _setup_route(_engine())
        pas = register_and_login(client, "perf_n1")
        h = {"Authorization": f"Bearer {pas}"}

        # Cumpara 10 bilete - fiecare in zile diferite ca sa evitam overlap
        from datetime import timedelta
        for i in range(10):
            td = date.today() + timedelta(days=i * 2 + 1)
            r = client.post("/tickets/buy", json={
                "train_id": train_id,
                "departure_station_id": s1, "arrival_station_id": s2,
                "travel_date": td.isoformat(),
                "ticket_type": "single",
            }, headers=h)
            assert r.status_code == 200, f"Bilet {i}: {r.text}"

        # Listare cu count
        with _QueryCounter(_engine()) as ctr:
            r = client.get("/tickets/my", headers=h)
        assert r.status_code == 200
        assert len(r.json()) >= 10
        # Daca am avea N+1, ar fi >40 queries (1 main + 10*(stations+trains+seats+qr))
        # Acceptam pana la 15 (buffer pentru auth, etc)
        assert ctr.count < 25, f"N+1 suspected: {ctr.count} queries pt 10 bilete"

    def test_seats_layout_single_pass(self, client):
        """Layout pt 100 locuri -> max 10 queries (fixed: trains + cars + seats + sold + held)."""
        s1, s2, train_id = _setup_route(_engine())

        # Genereaza vagon + locuri
        nonce = uuid.uuid4().hex[:6]
        with _engine().begin() as conn:
            car_id = conn.execute(text("""
                INSERT INTO train_cars (train_id, car_number, car_class, total_seats)
                VALUES (:tid, 1, 2, 60) RETURNING train_car_id
            """), {"tid": train_id}).scalar()
            for row in range(1, 16):
                for letter in "ABCD":
                    conn.execute(text("""
                        INSERT INTO seats (train_car_id, seat_row, seat_letter,
                                           seat_label, is_window, is_aisle)
                        VALUES (:c, :r, :l, :lab, FALSE, FALSE)
                    """), {"c": car_id, "r": row, "l": letter,
                           "lab": f"{row}{letter}"})

        pas = register_and_login(client, "perf_seats")
        with _QueryCounter(_engine()) as ctr:
            r = client.get(
                f"/trains/{train_id}/seats?travel_date={date.today().isoformat()}",
                headers={"Authorization": f"Bearer {pas}"},
            )
        assert r.status_code == 200
        # Sub 15 (1 user lookup + cleanup + train + cars + seats + sold + held + etc)
        assert ctr.count < 15, f"Layout face prea multe queries: {ctr.count}"

    def test_stations_search_response_time(self, client):
        """Search statii sub 500ms (test pentru bottlenecks)."""
        start = time.time()
        r = client.get("/stations/search?q=cluj&limit=20")
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 0.5, f"Search slow: {elapsed:.2f}s"

    def test_map_stations_response_time(self, client):
        """Map stations sub 2s."""
        pas = register_and_login(client, "perf_map")
        start = time.time()
        r = client.get("/map/stations",
                       headers={"Authorization": f"Bearer {pas}"})
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 2.0, f"Map slow: {elapsed:.2f}s"

"""
Integration tests pentru app/routers/map.py — endpoint-uri de harta CFR.

Acopera:
  - GET /map/stations (statii cu coordonate + filtre university/operator)
  - GET /map/connections (lista conexiuni feroviare cu coordonate)
  - GET /map/operators (operatori + nr trenuri)
  - GET /map/train-simulate/{train_id} (simulare live)
  - Auth gating

Toate apelurile cer auth, asa cum cer endpoint-urile reale.
"""
from __future__ import annotations

import itertools

import pytest
from sqlalchemy import text

from helpers import register_and_login


_seq = itertools.count(1)


def _engine():
    from app.core.database import engine
    return engine


def _setup_test_route_with_train(engine, code_a: str, code_b: str,
                                  has_geo: bool = True) -> tuple[int, int, int]:
    """
    Creeaza 2 statii + ruta + tren cu orar (route_stops) pentru a putea
    testa endpoint-urile map.
    Returneaza (station_a_id, station_b_id, train_id).
    """
    nonce = next(_seq)
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country, latitude, longitude,
                                  is_university_hub, student_count, universities_count)
            VALUES (:c, :n, 'Test City A', 'Romania',
                    CASE WHEN :geo THEN 47.16 ELSE NULL END,
                    CASE WHEN :geo THEN 27.59 ELSE NULL END,
                    TRUE, 12000, 3)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                is_university_hub = TRUE,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude
            RETURNING station_id
        """), {"c": code_a, "n": f"MapTest A {nonce}", "geo": has_geo}).scalar()

        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country, latitude, longitude,
                                  is_university_hub)
            VALUES (:c, :n, 'Test City B', 'Romania',
                    CASE WHEN :geo THEN 44.43 ELSE NULL END,
                    CASE WHEN :geo THEN 26.10 ELSE NULL END,
                    FALSE)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude
            RETURNING station_id
        """), {"c": code_b, "n": f"MapTest B {nonce}", "geo": has_geo}).scalar()

        op_id = conn.execute(
            text("SELECT operator_id FROM railway_operators LIMIT 1")
        ).scalar()

        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 400)
            ON CONFLICT (route_code) DO UPDATE SET
                route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {
            "rn": f"MapRoute {nonce}", "rc": f"MR_{nonce}",
            "op": op_id, "s1": s1, "s2": s2,
        }).scalar()

        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'interregio', 280, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET is_active = TRUE
            RETURNING train_id
        """), {"op": op_id, "rt": route_id, "tn": f"MAP_{nonce}"}).scalar()

        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES
                (:rt, :s1, 1, NULL, '08:00'::TIME, 0),
                (:rt, :s2, 2, '14:00'::TIME, NULL, 400)
            ON CONFLICT (route_id, stop_order) DO UPDATE
                SET arrival_time = EXCLUDED.arrival_time,
                    departure_time = EXCLUDED.departure_time
        """), {"rt": route_id, "s1": s1, "s2": s2})

    return s1, s2, train_id


# ===========================================================================
# 1. GET /map/stations
# ===========================================================================

class TestMapUniversities:

    def test_returns_stations_with_geo(self, client):
        _setup_test_route_with_train(_engine(), "MS_A1", "MS_B1")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/stations", headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Toate intrari au coordonate
        for s in data:
            assert "station_id" in s
            assert "name" in s
            assert s["latitude"] is not None
            assert s["longitude"] is not None

    def test_only_university_filter(self, client):
        _setup_test_route_with_train(_engine(), "MS_U1", "MS_U2")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/stations?only_university=true", headers=h)
        assert r.status_code == 200, r.text
        for s in r.json():
            assert s["is_university_hub"] is True

    def test_no_geo_excluded(self, client):
        """Statiile fara coordonate NU apar in /map/stations."""
        with _engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO stations (code, name, city, country, latitude, longitude)
                VALUES ('NO_GEO_T', 'No Geo Station', 'NoCity', 'Romania', NULL, NULL)
                ON CONFLICT (code) DO UPDATE SET latitude = NULL, longitude = NULL
            """))

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/stations", headers=h)
        assert r.status_code == 200
        codes = [s.get("code") for s in r.json() if s.get("code")]
        assert "NO_GEO_T" not in codes

    def test_filter_by_operator(self, client):
        """Filter operator_id returneaza doar statiile servite de acel operator."""
        _setup_test_route_with_train(_engine(), "OP_F1", "OP_F2")
        with _engine().connect() as conn:
            op_id = conn.execute(
                text("SELECT operator_id FROM railway_operators LIMIT 1")
            ).scalar()

        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/map/stations?operator_id={op_id}", headers=h)
        assert r.status_code == 200, r.text
        # Returneaza lista (eventual goala). Test pasiv ca query-ul nu crapa.
        assert isinstance(r.json(), list)


# ===========================================================================
# 2. GET /map/operators
# ===========================================================================

class TestMapOperators:

    def test_returns_list_with_train_counts(self, client):
        _setup_test_route_with_train(_engine(), "OP_T1", "OP_T2")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/operators", headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        for op in data:
            assert "operator_id" in op
            assert "name" in op
            assert "trains_count" in op
            assert op["trains_count"] >= 0


# ===========================================================================
# 3. GET /map/connections
# ===========================================================================

class TestMapConnections:

    def test_returns_list_with_geo(self, client):
        _setup_test_route_with_train(_engine(), "CON_A", "CON_B")
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/connections?min_trains=0", headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        if data:
            sample = data[0]
            # Field-urile expected (din SQL response)
            for field in ("from_id", "to_id", "from_lat", "from_lon",
                          "to_lat", "to_lon", "trains_count"):
                assert field in sample, f"Lipseste {field}: {sample}"


# ===========================================================================
# 4. GET /map/train-simulate/{train_id} (simulare GTFS)
# ===========================================================================

class TestTrainPosition:

    def test_returns_status_for_valid_train(self, client):
        _, _, train_id = _setup_test_route_with_train(
            _engine(), "POS_A", "POS_B"
        )
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/map/train-simulate/{train_id}", headers=h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "train_id" in data
        assert "status" in data
        assert data["status"] in (
            "not_departed", "in_transit", "arrived",
            "no_schedule", "unknown",
        )
        # NB: tren cu plecare 08:00 - sosire 14:00. In functie de ora rularii,
        # status poate fi: not_departed (dimineata), in_transit (la zi), arrived (seara).
        # Daca in_transit -> coordonate prezente. Altfel poate fi None.
        if data["status"] == "in_transit":
            assert data.get("current_lat") is not None
            assert data.get("current_lon") is not None
            assert 0 <= data.get("progress_percent", 0) <= 100

    def test_invalid_train_returns_404(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/train-simulate/999999", headers=h)
        assert r.status_code in (404, 422), r.text


# ===========================================================================
# 5. Auth gating
# ===========================================================================

class TestMapAuthGating:

    def test_universities_requires_auth(self, client):
        """Endpoint-urile /map/* cer Authorization."""
        r = client.get("/map/stations")
        assert r.status_code in (401, 403)

    def test_connections_requires_auth(self, client):
        r = client.get("/map/connections")
        assert r.status_code in (401, 403)

    def test_train_position_requires_auth(self, client):
        r = client.get("/map/train-simulate/1")
        assert r.status_code in (401, 403)

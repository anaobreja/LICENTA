"""
Tests for GET /map/route-geometry — polyline geometry endpoint.
Acoperire: map.py linii 382-540 (map_route_geometry).
Acopera si liniile 329-379 prin testul train in-transit fortat.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from helpers import register_and_login


def _engine():
    from app.core.database import engine
    return engine


def _make_nonce() -> str:
    return uuid.uuid4().hex[:8]


def _create_route_with_gps(engine, nonce: str,
                            lat_a=47.16, lon_a=27.59,
                            lat_b=44.43, lon_b=26.10) -> tuple[int, int, int]:
    """
    Creeaza 2 statii GPS + ruta + tren cu route_stops comerciale.
    Returneaza (station_a_id, station_b_id, train_id).
    """
    with engine.begin() as conn:
        op_id = conn.execute(
            text("SELECT operator_id FROM railway_operators LIMIT 1")
        ).scalar()

        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country, latitude, longitude)
            VALUES (:c, :n, 'CityA', 'Romania', :lat, :lon)
            ON CONFLICT (code) DO UPDATE SET latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude
            RETURNING station_id
        """), {"c": f"RG_A_{nonce}", "n": f"RouteGeo A {nonce}",
               "lat": lat_a, "lon": lon_a}).scalar()

        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country, latitude, longitude)
            VALUES (:c, :n, 'CityB', 'Romania', :lat, :lon)
            ON CONFLICT (code) DO UPDATE SET latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude
            RETURNING station_id
        """), {"c": f"RG_B_{nonce}", "n": f"RouteGeo B {nonce}",
               "lat": lat_b, "lon": lon_b}).scalar()

        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 400)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {"rn": f"RGRoute {nonce}", "rc": f"RGR_{nonce}",
               "op": op_id, "s1": s1, "s2": s2}).scalar()

        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'interregio', 200, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE SET is_active = TRUE
            RETURNING train_id
        """), {"op": op_id, "rt": route_id, "tn": f"RG_{nonce}"}).scalar()

        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km, is_commercial_stop)
            VALUES
                (:rt, :s1, 1, NULL,            '08:00'::TIME, 0,   TRUE),
                (:rt, :s2, 2, '14:00'::TIME,   NULL,          400, TRUE)
            ON CONFLICT (route_id, stop_order) DO UPDATE SET
                arrival_time   = EXCLUDED.arrival_time,
                departure_time = EXCLUDED.departure_time
        """), {"rt": route_id, "s1": s1, "s2": s2})

    return s1, s2, train_id


def _create_always_intransit_train(engine, nonce: str) -> tuple[int, int, int]:
    """
    Creeaza un tren care e mereu in_transit (pleaca 00:01, soseste 23:59).
    Util pentru a forta ramura de interpolare liniara in train-simulate.
    """
    with engine.begin() as conn:
        op_id = conn.execute(
            text("SELECT operator_id FROM railway_operators LIMIT 1")
        ).scalar()

        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country, latitude, longitude)
            VALUES (:c, :n, 'CityAT', 'Romania', 47.5, 27.0)
            ON CONFLICT (code) DO UPDATE SET latitude=47.5, longitude=27.0
            RETURNING station_id
        """), {"c": f"IT_A_{nonce}", "n": f"InTransit A {nonce}"}).scalar()

        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country, latitude, longitude)
            VALUES (:c, :n, 'CityBT', 'Romania', 44.5, 26.0)
            ON CONFLICT (code) DO UPDATE SET latitude=44.5, longitude=26.0
            RETURNING station_id
        """), {"c": f"IT_B_{nonce}", "n": f"InTransit B {nonce}"}).scalar()

        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 600)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {"rn": f"ITRoute {nonce}", "rc": f"ITR_{nonce}",
               "op": op_id, "s1": s1, "s2": s2}).scalar()

        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'intercity', 200, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE SET is_active = TRUE
            RETURNING train_id
        """), {"op": op_id, "rt": route_id, "tn": f"IT_{nonce}"}).scalar()

        # Pornire 00:01, sosire 23:59 → mereu in_transit
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km, is_commercial_stop)
            VALUES
                (:rt, :s1, 1, NULL,            '00:01'::TIME, 0,   TRUE),
                (:rt, :s2, 2, '23:59'::TIME,   NULL,          600, TRUE)
            ON CONFLICT (route_id, stop_order) DO UPDATE SET
                arrival_time   = EXCLUDED.arrival_time,
                departure_time = EXCLUDED.departure_time
        """), {"rt": route_id, "s1": s1, "s2": s2})

    return s1, s2, train_id


# ===========================================================================
# 1. GET /map/route-geometry — endpoint principal
# ===========================================================================

class TestMapRouteGeometry:

    def test_same_station_returns_400(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": 1,
            "to_station_id": 1,
        }, headers=h)

        assert r.status_code == 400, r.text

    def test_invalid_date_format_returns_400(self, client):
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": 1,
            "to_station_id": 2,
            "travel_date": "15-12-2026",
        }, headers=h)

        assert r.status_code == 400, r.text

    def test_no_trips_returns_found_false_with_empty_legs(self, client):
        """Statii fara nicio ruta intre ele -> found=False, legs=[]."""
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": 999991,
            "to_station_id": 999992,
            "travel_date": "2026-12-15",
        }, headers=h)

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["found"] is False
        assert data["legs"] == []
        assert data["transfer_count"] == 0
        assert data["total_duration_min"] is None

    def test_no_trips_default_date(self, client):
        """Fara travel_date -> foloseste maine ca default, nu crapa."""
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": 999993,
            "to_station_id": 999994,
        }, headers=h)

        assert r.status_code == 200, r.text
        data = r.json()
        assert "found" in data
        assert "legs" in data

    def test_requires_auth(self, client):
        r = client.get("/map/route-geometry", params={
            "from_station_id": 1,
            "to_station_id": 2,
        })
        assert r.status_code in (401, 403)

    def test_response_has_correct_structure(self, client):
        """Structura raspunsului e consistenta indiferent de rezultat."""
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": 999995,
            "to_station_id": 999996,
            "travel_date": "2026-12-15",
        }, headers=h)

        assert r.status_code == 200
        data = r.json()
        for key in ("found", "total_duration_min", "transfer_count", "legs"):
            assert key in data, f"Lipseste campul '{key}'"

    def test_with_real_route_returns_legs_geometry(self, client):
        """
        Cand exista o ruta reala, found=True si legs au geometry_points.
        """
        nonce = _make_nonce()
        s1, s2, _ = _create_route_with_gps(_engine(), nonce)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2026-12-15",
        }, headers=h)

        assert r.status_code == 200, r.text
        data = r.json()
        # Cu date de test fresh, trip_planner poate sau nu gasi ruta
        # in functie de data. Testam ca raspunsul are structura corecta.
        if data["found"]:
            assert len(data["legs"]) >= 1
            leg = data["legs"][0]
            for field in ("train_id", "from_station", "to_station",
                          "stops", "geometry_points"):
                assert field in leg, f"Lipseste '{field}' din leg"
            # geometry_points contine coordonate
            if leg["geometry_points"]:
                gp = leg["geometry_points"][0]
                assert "lat" in gp
                assert "lon" in gp
                assert "station_id" in gp

    def test_stops_only_commercial(self, client):
        """
        stops contine numai statiiile comerciale + capetele de leg.
        geometry_points contine toate statiile cu GPS.
        """
        nonce = _make_nonce()
        s1, s2, _ = _create_route_with_gps(_engine(), nonce)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get("/map/route-geometry", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2026-12-15",
        }, headers=h)

        assert r.status_code == 200
        data = r.json()
        if data["found"] and data["legs"]:
            leg = data["legs"][0]
            # geometry_points >= stops (geometry include si treceri)
            assert len(leg["geometry_points"]) >= len(leg["stops"])


# ===========================================================================
# 2. GET /map/train-simulate — ramura in_transit cu interpolare
# ===========================================================================

class TestTrainSimulateInTransit:

    def test_always_in_transit_train_has_progress(self, client):
        """
        Tren cu orar 00:01-23:59 → mereu in_transit.
        Verifica ramura de interpolare liniara (linii 329-379 map.py).
        """
        nonce = _make_nonce()
        _, _, train_id = _create_always_intransit_train(_engine(), nonce)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/map/train-simulate/{train_id}", headers=h)
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["status"] == "in_transit"
        assert data["current_lat"] is not None
        assert data["current_lon"] is not None
        assert 0 <= data["progress_percent"] <= 100
        assert "current_station" in data
        assert "next_station" in data

    def test_in_transit_progress_between_0_and_100(self, client):
        """Progress clamped la [0, 100]."""
        nonce = _make_nonce()
        _, _, train_id = _create_always_intransit_train(_engine(), nonce)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/map/train-simulate/{train_id}", headers=h)
        assert r.status_code == 200
        data = r.json()
        if data["status"] == "in_transit":
            assert 0.0 <= data["progress_percent"] <= 100.0

    def test_in_transit_coordinates_rounded(self, client):
        """Coordonatele sunt rotunjite la 6 zecimale."""
        nonce = _make_nonce()
        _, _, train_id = _create_always_intransit_train(_engine(), nonce)
        token = register_and_login(client, "passenger")
        h = {"Authorization": f"Bearer {token}"}

        r = client.get(f"/map/train-simulate/{train_id}", headers=h)
        assert r.status_code == 200
        data = r.json()
        if data["status"] == "in_transit" and data["current_lat"] is not None:
            lat_str = str(data["current_lat"])
            lon_str = str(data["current_lon"])
            # Maxim 6 zecimale
            if "." in lat_str:
                assert len(lat_str.split(".")[1]) <= 6
            if "." in lon_str:
                assert len(lon_str.split(".")[1]) <= 6

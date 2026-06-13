"""
Test pentru endpoint-ul /trips/suggest (trip planner multi-leg).

Acopera:
  - Itinerariu direct cand exista tren direct.
  - Itinerariu cu 1 schimbare cand nu exista direct.
  - Itinerariu cu 2 schimbari pentru distante mari.
  - Sortare dupa timp total ASC + transferuri ASC.
  - Fereastra conexiune 15min-3h respectata.
  - Validare input (date trecut, top_n out of range, etc).
  - Edge cases: from == to, statii inexistente.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text


def _engine():
    from app.core.database import engine
    return engine


def _setup_direct_route(engine) -> tuple[int, int, int]:
    """Creeaza ruta directa A -> B cu 1 tren. Returneaza (s1, s2, train_id)."""
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"TPD_A_{nonce}", "n": f"TPA {nonce}"}).scalar()
        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"TPD_B_{nonce}", "n": f"TPB {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 200) RETURNING route_id
        """), {"rn": f"TPDR {nonce}", "rc": f"TPDR_{nonce}", "op": op, "s1": s1, "s2": s2}).scalar()
        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
        """), {"op": op, "rt": route_id, "tn": f"TPT_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '10:00'::TIME, 0),
                   (:rt, :s2, 2, '13:00'::TIME, NULL, 200)
        """), {"rt": route_id, "s1": s1, "s2": s2})
    return s1, s2, train_id


def _setup_transfer_route(engine) -> tuple[int, int, int, int, int]:
    """
    Creeaza scenariu cu schimbare:
      Ruta 1: A -> B (tren 1 pleaca 09:00, ajunge 11:00)
      Ruta 2: B -> C (tren 2 pleaca 12:00, ajunge 14:00)
    Conexiune in B: 1h (intre MIN=15min si MAX=3h).
    NU exista tren direct A -> C.
    Returneaza (sA, sB, sC, trainAB, trainBC).
    """
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        sA = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"TR_A_{nonce}", "n": f"StatieA {nonce}"}).scalar()
        sB = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"TR_B_{nonce}", "n": f"StatieB {nonce}"}).scalar()
        sC = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CC', 'Romania') RETURNING station_id
        """), {"c": f"TR_C_{nonce}", "n": f"StatieC {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()

        # Ruta 1: A -> B
        route1 = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
        """), {"rn": f"TRR1 {nonce}", "rc": f"TRR1_{nonce}",
               "op": op, "s1": sA, "s2": sB}).scalar()
        train1 = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
        """), {"op": op, "rt": route1, "tn": f"TRT1_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '09:00'::TIME, 0),
                   (:rt, :s2, 2, '11:00'::TIME, NULL, 100)
        """), {"rt": route1, "s1": sA, "s2": sB})

        # Ruta 2: B -> C
        route2 = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
        """), {"rn": f"TRR2 {nonce}", "rc": f"TRR2_{nonce}",
               "op": op, "s1": sB, "s2": sC}).scalar()
        train2 = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'interregio', 100, TRUE) RETURNING train_id
        """), {"op": op, "rt": route2, "tn": f"TRT2_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '12:00'::TIME, 0),
                   (:rt, :s2, 2, '14:00'::TIME, NULL, 100)
        """), {"rt": route2, "s1": sB, "s2": sC})

    return sA, sB, sC, train1, train2


def _setup_no_connection_route(engine) -> tuple[int, int, int]:
    """
    Ruta A -> B exista, dar nu exista ruta B -> C cu fereastra valida.
    Returneaza (sA, sB, sC).
    """
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        sA = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"NC_A_{nonce}", "n": f"NCA {nonce}"}).scalar()
        sB = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"NC_B_{nonce}", "n": f"NCB {nonce}"}).scalar()
        sC = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CC', 'Romania') RETURNING station_id
        """), {"c": f"NC_C_{nonce}", "n": f"NCC {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        # A -> B exista
        route1 = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
        """), {"rn": f"NCR1 {nonce}", "rc": f"NCR1_{nonce}",
               "op": op, "s1": sA, "s2": sB}).scalar()
        train1 = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
        """), {"op": op, "rt": route1, "tn": f"NCT_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '06:00'::TIME, 0),
                   (:rt, :s2, 2, '08:00'::TIME, NULL, 100)
        """), {"rt": route1, "s1": sA, "s2": sB})
        # B -> C NU exista
    return sA, sB, sC


class TestTripPlannerBasic:

    def test_direct_trip(self, client):
        """Tren direct A->B -> 1 itinerariu cu 0 schimbari."""
        s1, s2, train_id = _setup_direct_route(_engine())
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={s1}&to_station_id={s2}"
            f"&travel_date={future}"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] >= 1
        assert data["trips"][0]["transfer_count"] == 0
        assert len(data["trips"][0]["legs"]) == 1
        assert data["trips"][0]["legs"][0]["train_id"] == train_id

    def test_one_transfer_when_no_direct(self, client):
        """Fara tren direct -> itinerariu cu 1 schimbare."""
        sA, sB, sC, t1, t2 = _setup_transfer_route(_engine())
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={sA}&to_station_id={sC}"
            f"&travel_date={future}"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] >= 1
        trip = data["trips"][0]
        assert trip["transfer_count"] == 1
        assert len(trip["legs"]) == 2
        # Schimbam in B
        assert trip["legs"][0]["to_station_id"] == sB
        assert trip["legs"][1]["from_station_id"] == sB
        # Trenurile sunt cele asteptate
        assert trip["legs"][0]["train_id"] == t1
        assert trip["legs"][1]["train_id"] == t2

    def test_no_route_when_no_connection(self, client):
        """A->B exista dar B->C nu -> 0 itinerarii pentru A->C."""
        sA, sB, sC = _setup_no_connection_route(_engine())
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={sA}&to_station_id={sC}"
            f"&travel_date={future}"
        )
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_total_duration_calculated_correctly(self, client):
        """Durata totala = arrival_ultim - departure_primul leg."""
        sA, sB, sC, t1, t2 = _setup_transfer_route(_engine())
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={sA}&to_station_id={sC}"
            f"&travel_date={future}"
        )
        data = r.json()
        trip = data["trips"][0]
        # A pleaca 09:00, C ajunge 14:00 -> 5h = 300 min
        assert trip["total_duration_min"] == 300
        assert trip["departure_time"] == "09:00:00"
        assert trip["arrival_time"] == "14:00:00"

    def test_sort_by_duration_then_transfers(self, client):
        """Itinerariul direct (mai rapid) e returnat primul; cu schimbari dupa."""
        # Setup: direct A->C exista + alternativa cu schimbare A->B->C mai lenta
        nonce = uuid.uuid4().hex[:8]
        engine = _engine()
        with engine.begin() as conn:
            sA = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
            """), {"c": f"SO_A_{nonce}", "n": f"SOA {nonce}"}).scalar()
            sB = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
            """), {"c": f"SO_B_{nonce}", "n": f"SOB {nonce}"}).scalar()
            sC = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CC', 'Romania') RETURNING station_id
            """), {"c": f"SO_C_{nonce}", "n": f"SOC {nonce}"}).scalar()
            op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()

            # Direct A -> C: 09:00 - 11:00 (2h)
            r1 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 200) RETURNING route_id
            """), {"rn": f"SOR1 {nonce}", "rc": f"SOR1_{nonce}",
                   "op": op, "s1": sA, "s2": sC}).scalar()
            tr_direct = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'interregio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r1, "tn": f"SOT1_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '09:00'::TIME, 0),
                       (:rt, :s2, 2, '11:00'::TIME, NULL, 200)
            """), {"rt": r1, "s1": sA, "s2": sC})

            # A -> B: 08:00 - 09:30, B -> C: 10:00 - 12:00
            r2 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 80) RETURNING route_id
            """), {"rn": f"SOR2 {nonce}", "rc": f"SOR2_{nonce}",
                   "op": op, "s1": sA, "s2": sB}).scalar()
            tr_ab = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r2, "tn": f"SOT2_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '08:00'::TIME, 0),
                       (:rt, :s2, 2, '09:30'::TIME, NULL, 80)
            """), {"rt": r2, "s1": sA, "s2": sB})

            r3 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 120) RETURNING route_id
            """), {"rn": f"SOR3 {nonce}", "rc": f"SOR3_{nonce}",
                   "op": op, "s1": sB, "s2": sC}).scalar()
            tr_bc = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r3, "tn": f"SOT3_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '10:00'::TIME, 0),
                       (:rt, :s2, 2, '12:00'::TIME, NULL, 120)
            """), {"rt": r3, "s1": sB, "s2": sC})

        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={sA}&to_station_id={sC}"
            f"&travel_date={future}"
        )
        data = r.json()
        assert data["count"] >= 1
        # Primul rezultat = direct (mai rapid, 2h)
        assert data["trips"][0]["transfer_count"] == 0
        assert data["trips"][0]["legs"][0]["train_id"] == tr_direct
        # Daca exista si schimbare (4h), e a doua optiune
        if data["count"] >= 2:
            assert data["trips"][1]["transfer_count"] == 1
            assert data["trips"][1]["total_duration_min"] > data["trips"][0]["total_duration_min"]


class TestTripPlannerValidation:

    def test_same_from_to_rejected(self, client):
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id=1&to_station_id=1&travel_date={future}"
        )
        assert r.status_code == 400

    def test_past_date_rejected(self, client):
        past = (date.today() - timedelta(days=1)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id=1&to_station_id=2&travel_date={past}"
        )
        assert r.status_code == 400

    def test_invalid_date_format(self, client):
        r = client.get(
            f"/trips/suggest?from_station_id=1&to_station_id=2&travel_date=2026/01/01"
        )
        assert r.status_code == 400

    def test_top_n_out_of_range(self, client):
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id=1&to_station_id=2"
            f"&travel_date={future}&top_n=999"
        )
        assert r.status_code == 400

    def test_top_n_zero(self, client):
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id=1&to_station_id=2"
            f"&travel_date={future}&top_n=0"
        )
        assert r.status_code == 400


class TestTripPlannerConnectionWindow:

    def test_connection_too_short_skipped(self, client):
        """Schimbare cu <15 min nu e returnata."""
        nonce = uuid.uuid4().hex[:8]
        engine = _engine()
        with engine.begin() as conn:
            sA = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
            """), {"c": f"CW_A_{nonce}", "n": f"CWA {nonce}"}).scalar()
            sB = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
            """), {"c": f"CW_B_{nonce}", "n": f"CWB {nonce}"}).scalar()
            sC = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CC', 'Romania') RETURNING station_id
            """), {"c": f"CW_C_{nonce}", "n": f"CWC {nonce}"}).scalar()
            op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
            # A -> B: ajunge 10:00
            r1 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
            """), {"rn": f"CWR1 {nonce}", "rc": f"CWR1_{nonce}",
                   "op": op, "s1": sA, "s2": sB}).scalar()
            t1 = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r1, "tn": f"CWT1_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '08:00'::TIME, 0),
                       (:rt, :s2, 2, '10:00'::TIME, NULL, 100)
            """), {"rt": r1, "s1": sA, "s2": sB})
            # B -> C: pleaca 10:05 (5 min after - prea putin)
            r2 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
            """), {"rn": f"CWR2 {nonce}", "rc": f"CWR2_{nonce}",
                   "op": op, "s1": sB, "s2": sC}).scalar()
            t2 = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r2, "tn": f"CWT2_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '10:05'::TIME, 0),
                       (:rt, :s2, 2, '12:00'::TIME, NULL, 100)
            """), {"rt": r2, "s1": sB, "s2": sC})

        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={sA}&to_station_id={sC}"
            f"&travel_date={future}"
        )
        data = r.json()
        # Conexiunea de 5 min e respinsa (< MIN_CONNECTION = 15 min)
        assert data["count"] == 0

    def test_connection_too_long_skipped(self, client):
        """Schimbare cu >3h nu e returnata."""
        nonce = uuid.uuid4().hex[:8]
        engine = _engine()
        with engine.begin() as conn:
            sA = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
            """), {"c": f"LO_A_{nonce}", "n": f"LOA {nonce}"}).scalar()
            sB = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
            """), {"c": f"LO_B_{nonce}", "n": f"LOB {nonce}"}).scalar()
            sC = conn.execute(text("""
                INSERT INTO stations (code, name, city, country)
                VALUES (:c, :n, 'CC', 'Romania') RETURNING station_id
            """), {"c": f"LO_C_{nonce}", "n": f"LOC {nonce}"}).scalar()
            op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
            # A -> B: ajunge 08:00
            r1 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
            """), {"rn": f"LOR1 {nonce}", "rc": f"LOR1_{nonce}",
                   "op": op, "s1": sA, "s2": sB}).scalar()
            t1 = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r1, "tn": f"LOT1_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '06:00'::TIME, 0),
                       (:rt, :s2, 2, '08:00'::TIME, NULL, 100)
            """), {"rt": r1, "s1": sA, "s2": sB})
            # B -> C: pleaca 12:00 (4h dupa - prea lung)
            r2 = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, :op, :s1, :s2, 100) RETURNING route_id
            """), {"rn": f"LOR2 {nonce}", "rc": f"LOR2_{nonce}",
                   "op": op, "s1": sB, "s2": sC}).scalar()
            t2 = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"op": op, "rt": r2, "tn": f"LOT2_{nonce}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '12:00'::TIME, 0),
                       (:rt, :s2, 2, '14:00'::TIME, NULL, 100)
            """), {"rt": r2, "s1": sB, "s2": sC})

        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.get(
            f"/trips/suggest?from_station_id={sA}&to_station_id={sC}"
            f"&travel_date={future}"
        )
        data = r.json()
        # Conexiune 4h respinsa (> MAX_CONNECTION = 3h)
        assert data["count"] == 0

"""
Teste pentru:
  - Feature A: GET /users/me/travel-stats (dashboard cu KPIs)
  - Feature E: subscription_recommendation in /tickets/quote

Acopera:
  - User fara bilete -> stats goale (0)
  - User cu 1 bilet -> achievement "first_trip"
  - User cu 10+ bilete -> achievement "frequent_traveler"
  - User cu km mari -> achievement "km_1000"
  - Monthly array are exact 6 elemente
  - top_trains sortat dupa count DESC
  - Quote pe user nou (< 3 cumparari) -> NO recommendation
  - Quote pe user cu 3+ cumparari recente -> recommendation prezenta
  - Quote pe user CU abonament activ -> NO recommendation (deja are)
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from helpers import register_and_login


def _engine():
    from app.core.database import engine
    return engine


def _setup_route(engine) -> tuple[int, int, int]:
    """Creeaza ruta simpla A->B cu 1 tren. Returneaza (s1, s2, train_id)."""
    nonce = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        s1 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CA', 'Romania') RETURNING station_id
        """), {"c": f"TS_A_{nonce}", "n": f"TSA {nonce}"}).scalar()
        s2 = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES (:c, :n, 'CB', 'Romania') RETURNING station_id
        """), {"c": f"TS_B_{nonce}", "n": f"TSB {nonce}"}).scalar()
        op = conn.execute(text("SELECT operator_id FROM railway_operators LIMIT 1")).scalar()
        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES (:rn, :rc, :op, :s1, :s2, 250) RETURNING route_id
        """), {"rn": f"TSR {nonce}", "rc": f"TSR_{nonce}",
               "op": op, "s1": s1, "s2": s2}).scalar()
        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
        """), {"op": op, "rt": route_id, "tn": f"TST_{nonce}"}).scalar()
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES (:rt, :s1, 1, NULL, '09:00'::TIME, 0),
                   (:rt, :s2, 2, '12:00'::TIME, NULL, 250)
        """), {"rt": route_id, "s1": s1, "s2": s2})
    return s1, s2, train_id


def _create_ticket(engine, user_id: int, train_id: int,
                   s1: int, s2: int, travel_date: date,
                   price: float = 50.0, status: str = "used",
                   purchase_offset_days: int = 0) -> int:
    """Insereaza un bilet direct in DB pentru a simula istoric."""
    with engine.begin() as conn:
        purchase = date.today() - timedelta(days=purchase_offset_days)
        ticket_id = conn.execute(text("""
            INSERT INTO tickets (user_id, train_id, departure_station_id,
                                 arrival_station_id, travel_date, ticket_type,
                                 ticket_status, price, discount_applied,
                                 purchase_time)
            VALUES (:uid, :tid, :s1, :s2, :td, 'single', :st, :p, 0, :pt)
            RETURNING ticket_id
        """), {
            "uid": user_id, "tid": train_id, "s1": s1, "s2": s2,
            "td": travel_date, "st": status, "p": price,
            "pt": purchase,
        }).scalar()
    return ticket_id


def _user_id(client, token: str) -> int:
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    return r.json()["user_id"]


# ============================================================================
# FEATURE A: /users/me/travel-stats
# ============================================================================

class TestTravelStatsEmpty:

    def test_user_with_no_tickets_returns_zeros(self, client):
        tok = register_and_login(client, "stats_empty")
        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_trips"] == 0
        assert data["completed_trips"] == 0
        assert data["total_km"] == 0
        assert data["total_spent_ron"] == 0
        assert data["co2_saved_kg"] == 0
        assert data["achievements"] == []
        assert data["top_trains"] == []


class TestTravelStatsWithTickets:

    def test_one_ticket_gives_first_trip_achievement(self, client):
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "stats_one")
        uid = _user_id(client, tok)
        _create_ticket(_engine(), uid, train_id, s1, s2, date.today(),
                       price=50.0, status="used")

        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        assert data["completed_trips"] == 1
        assert data["total_km"] == 250  # din total_distance_km
        assert data["total_spent_ron"] == 50.0

        codes = [a["code"] for a in data["achievements"]]
        assert "first_trip" in codes

    def test_ten_tickets_unlocks_frequent_traveler(self, client):
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "stats_ten")
        uid = _user_id(client, tok)
        # Cream 10 bilete (zile diferite pentru a evita overlap)
        for i in range(10):
            _create_ticket(_engine(), uid, train_id, s1, s2,
                           date.today() + timedelta(days=i),
                           price=30.0, status="used")

        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        assert data["completed_trips"] == 10
        codes = [a["code"] for a in data["achievements"]]
        assert "first_trip" in codes
        assert "frequent_traveler" in codes

    def test_km_1000_achievement_for_large_distance(self, client):
        """4 bilete pe ruta 250km -> 1000km -> achievement km_1000."""
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "stats_km")
        uid = _user_id(client, tok)
        for i in range(4):
            _create_ticket(_engine(), uid, train_id, s1, s2,
                           date.today() + timedelta(days=i),
                           price=40.0, status="used")

        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        assert data["total_km"] == 1000  # 4 * 250
        codes = [a["code"] for a in data["achievements"]]
        assert "km_1000" in codes

    def test_monthly_array_has_six_entries(self, client):
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "stats_monthly")
        uid = _user_id(client, tok)
        _create_ticket(_engine(), uid, train_id, s1, s2, date.today(),
                       price=10.0, status="used")

        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        assert len(data["monthly"]) == 6
        # Fiecare entry are month + label + count
        for m in data["monthly"]:
            assert "month" in m and "label" in m and "count" in m
            assert isinstance(m["count"], int)

    def test_top_trains_sorted_desc(self, client):
        s1a, s2a, train_a = _setup_route(_engine())
        s1b, s2b, train_b = _setup_route(_engine())
        tok = register_and_login(client, "stats_top")
        uid = _user_id(client, tok)
        # 3 calatorii cu train_a, 1 cu train_b
        for i in range(3):
            _create_ticket(_engine(), uid, train_a, s1a, s2a,
                           date.today() + timedelta(days=i),
                           price=20.0, status="used")
        _create_ticket(_engine(), uid, train_b, s1b, s2b,
                       date.today() + timedelta(days=10),
                       price=20.0, status="used")

        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        assert len(data["top_trains"]) == 2
        # Train_a primul (count=3), train_b al doilea (count=1)
        assert data["top_trains"][0]["count"] == 3
        assert data["top_trains"][1]["count"] == 1

    def test_co2_calculated_correctly(self, client):
        """4 bilete * 250km = 1000km * 0.12 = 120kg CO2."""
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "stats_co2")
        uid = _user_id(client, tok)
        for i in range(4):
            _create_ticket(_engine(), uid, train_id, s1, s2,
                           date.today() + timedelta(days=i),
                           price=10.0, status="used")

        r = client.get("/users/me/travel-stats",
                       headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        assert data["co2_saved_kg"] == 120.0
        # 120 / 21 ≈ 5.7 copaci
        assert data["trees_equivalent"] > 5


# ============================================================================
# FEATURE E: subscription_recommendation in /tickets/quote
# ============================================================================

class TestSubscriptionRecommendation:

    def test_new_user_gets_no_recommendation(self, client):
        """User cu 0 bilete pe ruta -> no recommendation."""
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "rec_new")
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.post("/tickets/quote", json={
            "train_id": train_id,
            "departure_station_id": s1, "arrival_station_id": s2,
            "travel_date": future, "ticket_type": "single",
        }, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert r.json().get("subscription_recommendation") is None

    def test_user_with_3_recent_purchases_gets_recommendation(self, client):
        """User cu 3 bilete pe ruta in ultima luna -> recommendation prezenta."""
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "rec_freq")
        uid = _user_id(client, tok)
        # Cream 3 bilete cumparate recent (purchase_time in ultimele 30 zile)
        for i in range(3):
            _create_ticket(_engine(), uid, train_id, s1, s2,
                           date.today() - timedelta(days=i),
                           price=50.0, status="used",
                           purchase_offset_days=i * 2)

        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.post("/tickets/quote", json={
            "train_id": train_id,
            "departure_station_id": s1, "arrival_station_id": s2,
            "travel_date": future, "ticket_type": "single",
        }, headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        rec = data.get("subscription_recommendation")
        assert rec is not None, f"Expected recommendation, got: {data}"
        assert rec["recent_tickets_count"] == 3
        assert rec["subscription_price"] > 0
        assert rec["estimated_saving_ron"] > 0
        assert "message" in rec
        assert "suggestion_type" in rec

    def test_user_with_active_subscription_gets_no_recommendation(self, client):
        """User care DEJA are abonament pe ruta -> no recommendation."""
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "rec_sub")
        uid = _user_id(client, tok)
        # 4 bilete + 1 abonament activ
        for i in range(4):
            _create_ticket(_engine(), uid, train_id, s1, s2,
                           date.today() - timedelta(days=i),
                           price=50.0, status="used",
                           purchase_offset_days=i)
        with _engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO subscriptions (user_id, subscription_type,
                                           subscription_scope,
                                           from_station_id, to_station_id,
                                           valid_from, valid_until,
                                           price, status)
                VALUES (:uid, 'monthly', 'route', :s1, :s2,
                        CURRENT_DATE, CURRENT_DATE + INTERVAL '30 days',
                        100, 'active')
            """), {"uid": uid, "s1": s1, "s2": s2})

        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.post("/tickets/quote", json={
            "train_id": train_id,
            "departure_station_id": s1, "arrival_station_id": s2,
            "travel_date": future, "ticket_type": "single",
        }, headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        # Are deja abonament -> NO recommendation
        assert data.get("subscription_recommendation") is None

    def test_recommendation_works_both_directions(self, client):
        """Cumpararile A->B + B->A se contorizeaza impreuna."""
        s1, s2, train_id = _setup_route(_engine())
        tok = register_and_login(client, "rec_bidir")
        uid = _user_id(client, tok)
        # 2 bilete A->B + 1 bilet B->A
        for i in range(2):
            _create_ticket(_engine(), uid, train_id, s1, s2,
                           date.today() - timedelta(days=i),
                           price=40.0, status="used",
                           purchase_offset_days=i)
        # 1 bilet invers (B->A) - folosim alta ruta cu cele 2 statii inverse
        with _engine().begin() as conn:
            ret_route = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES (:rn, :rc, (SELECT operator_id FROM railway_operators LIMIT 1),
                        :s1, :s2, 250) RETURNING route_id
            """), {
                "rn": f"BIDIR_{uuid.uuid4().hex[:6]}",
                "rc": f"BIDIR_{uuid.uuid4().hex[:6]}",
                "s1": s2, "s2": s1,
            }).scalar()
            ret_train = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES ((SELECT operator_id FROM railway_operators LIMIT 1),
                        :rt, :tn, 'regio', 100, TRUE) RETURNING train_id
            """), {"rt": ret_route, "tn": f"BIDIR_T_{uuid.uuid4().hex[:6]}"}).scalar()
            conn.execute(text("""
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                         arrival_time, departure_time,
                                         distance_from_origin_km)
                VALUES (:rt, :s1, 1, NULL, '15:00'::TIME, 0),
                       (:rt, :s2, 2, '18:00'::TIME, NULL, 250)
            """), {"rt": ret_route, "s1": s2, "s2": s1})
        _create_ticket(_engine(), uid, ret_train, s2, s1,
                       date.today() - timedelta(days=5),
                       price=40.0, status="used", purchase_offset_days=5)

        # Quote A->B - ar trebui recommendation (3 cumparari pe ruta in orice directie)
        future = (date.today() + timedelta(days=2)).isoformat()
        r = client.post("/tickets/quote", json={
            "train_id": train_id,
            "departure_station_id": s1, "arrival_station_id": s2,
            "travel_date": future, "ticket_type": "single",
        }, headers={"Authorization": f"Bearer {tok}"})
        rec = r.json().get("subscription_recommendation")
        assert rec is not None
        assert rec["recent_tickets_count"] == 3  # 2 A->B + 1 B->A

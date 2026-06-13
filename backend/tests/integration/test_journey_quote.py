"""
Tests for POST /tickets/quote-journey.
Acoperire: tickets.py linii 1094-1207 (quote_journey()).

Endpoint-ul calculeaza pretul unui journey multi-leg fara a cumpara.
"""
from __future__ import annotations

import pytest
from helpers import register_and_login


def _get_catalog_train(client) -> dict | None:
    """Returneaza primul tren din catalog (sau None daca catalog e gol)."""
    r = client.get("/tickets/catalog")
    if r.status_code != 200 or not r.json():
        return None
    return r.json()[0]


def _quote(client, token: str, legs: list, ticket_type: str = "single",
           passengers: list | None = None) -> dict:
    body = {
        "legs": legs,
        "ticket_type": ticket_type,
    }
    if passengers is not None:
        body["passengers"] = passengers
    return client.post(
        "/tickets/quote-journey",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


# ===========================================================================
# 1. Happy-path: single leg
# ===========================================================================

class TestJourneyQuoteSingleLeg:

    def test_returns_200_with_price_breakdown(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 200, r.text
        data = r.json()
        assert "legs" in data
        assert "total_base" in data
        assert "total_final" in data
        assert "discount_percent" in data
        assert "is_personal_route" in data

    def test_single_leg_quote_fields(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 200
        leg = r.json()["legs"][0]
        for field in ("leg_order", "train_id", "train_number", "train_type",
                      "departure_station", "arrival_station", "travel_date",
                      "base_price", "final_price", "discount_percent",
                      "is_personal_route", "subscription_covers"):
            assert field in leg, f"Lipseste campul '{field}' din leg"

    def test_leg_order_starts_at_1(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 200
        assert r.json()["legs"][0]["leg_order"] == 1

    def test_total_matches_sum_of_legs(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 200
        data = r.json()
        leg_sum_base = sum(l["base_price"] for l in data["legs"])
        leg_sum_final = sum(l["final_price"] for l in data["legs"])
        assert abs(data["total_base"] - round(leg_sum_base, 2)) < 0.01
        assert abs(data["total_final"] - round(leg_sum_final, 2)) < 0.01

    def test_final_price_lte_base_price(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 200
        for leg in r.json()["legs"]:
            assert leg["final_price"] <= leg["base_price"]


# ===========================================================================
# 2. Happy-path: multiple legs
# ===========================================================================

class TestJourneyQuoteMultiLeg:

    def test_two_legs_returns_two_quotes(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[
            {
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["arrival_id"],
                "travel_date": "2026-12-15",
            },
            {
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["arrival_id"],
                "travel_date": "2026-12-16",
            },
        ])

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["legs"]) == 2
        assert data["legs"][0]["leg_order"] == 1
        assert data["legs"][1]["leg_order"] == 2

    def test_multi_leg_total_is_sum_of_legs(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[
            {
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["arrival_id"],
                "travel_date": "2026-12-15",
            },
            {
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["arrival_id"],
                "travel_date": "2026-12-16",
            },
        ])

        assert r.status_code == 200
        data = r.json()
        leg_sum_final = sum(l["final_price"] for l in data["legs"])
        assert abs(data["total_final"] - round(leg_sum_final, 2)) < 0.01


# ===========================================================================
# 3. Validare input
# ===========================================================================

class TestJourneyQuoteValidation:

    def test_invalid_date_format_returns_400(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "15/12/2026",
        }])

        assert r.status_code == 400, r.text

    def test_nonexistent_train_returns_404(self, client, passenger_token):
        r = _quote(client, passenger_token, legs=[{
            "train_id": 999999,
            "departure_station_id": 1,
            "arrival_station_id": 2,
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 404, r.text

    def test_unauthenticated_returns_401(self, client):
        r = client.post("/tickets/quote-journey", json={
            "legs": [{
                "train_id": 1,
                "departure_station_id": 1,
                "arrival_station_id": 2,
                "travel_date": "2026-12-15",
            }],
            "ticket_type": "single",
        })
        assert r.status_code in (401, 403)

    def test_too_many_legs_returns_422(self, client, passenger_token):
        """Mai mult de 3 legs -> validare Pydantic -> 422."""
        r = _quote(client, passenger_token, legs=[
            {"train_id": 1, "departure_station_id": 1,
             "arrival_station_id": 2, "travel_date": "2026-12-15"},
            {"train_id": 1, "departure_station_id": 1,
             "arrival_station_id": 2, "travel_date": "2026-12-15"},
            {"train_id": 1, "departure_station_id": 1,
             "arrival_station_id": 2, "travel_date": "2026-12-15"},
            {"train_id": 1, "departure_station_id": 1,
             "arrival_station_id": 2, "travel_date": "2026-12-15"},
        ])
        assert r.status_code == 422

    def test_empty_legs_returns_422(self, client, passenger_token):
        """Lista goala de legs -> validare Pydantic -> 422."""
        r = _quote(client, passenger_token, legs=[])
        assert r.status_code == 422

    def test_inactive_train_returns_404(self, client, passenger_token):
        """Train inactiv -> 404."""
        from app.core.database import engine
        from sqlalchemy import text

        # Cream un tren inactiv temporar
        with engine.begin() as conn:
            op_id = conn.execute(
                text("SELECT operator_id FROM railway_operators LIMIT 1")
            ).scalar()
            s1 = conn.execute(text(
                "SELECT station_id FROM stations LIMIT 1 OFFSET 0"
            )).scalar()
            s2 = conn.execute(text(
                "SELECT station_id FROM stations LIMIT 1 OFFSET 1"
            )).scalar()
            route_id = conn.execute(text("""
                INSERT INTO routes (route_name, route_code, operator_id,
                                    origin_station_id, destination_station_id,
                                    total_distance_km)
                VALUES ('InactiveTest', 'INACT_QT', :op, :s1, :s2, 100)
                ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
                RETURNING route_id
            """), {"op": op_id, "s1": s1, "s2": s2}).scalar()
            inactive_id = conn.execute(text("""
                INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                    capacity_seats, is_active)
                VALUES (:op, :rt, 'INACT_TRN_QT', 'regio', 100, FALSE)
                ON CONFLICT (operator_id, train_number) DO UPDATE SET is_active = FALSE
                RETURNING train_id
            """), {"op": op_id, "rt": route_id}).scalar()

        r = _quote(client, passenger_token, legs=[{
            "train_id": inactive_id,
            "departure_station_id": s1,
            "arrival_station_id": s2,
            "travel_date": "2026-12-15",
        }])

        assert r.status_code == 404, r.text


# ===========================================================================
# 4. Ticket type variations
# ===========================================================================

class TestJourneyQuoteTicketType:

    def test_return_ticket_type_accepted(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }], ticket_type="return")

        assert r.status_code == 200, r.text

    def test_invalid_ticket_type_returns_422(self, client, passenger_token):
        train = _get_catalog_train(client)
        if not train:
            pytest.skip("No trains in catalog")

        r = _quote(client, passenger_token, legs=[{
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-15",
        }], ticket_type="invalid_type")

        assert r.status_code == 422

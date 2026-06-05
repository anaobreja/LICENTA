"""Test suite pentru endpoint-urile de ticketing (catalog / buy / validate / history)."""

import pytest
from helpers import register_and_login

def _get_first_train(client) -> dict:
    """Returnează primul tren din catalog."""
    resp = client.get("/tickets/catalog")
    assert resp.status_code == 200, f"Catalog failed: {resp.text}"
    catalog = resp.json()
    assert len(catalog) > 0, "Catalog gol — verifica seed_demo.sql"
    return catalog[0]

def _buy_ticket(client, token: str, train: dict) -> dict:
    """Cumpără un bilet și returnează răspunsul JSON."""
    resp = client.post(
        "/tickets/buy",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "train_id": train["train_id"],
            "departure_station_id": train["departure_id"],
            "arrival_station_id": train["arrival_id"],
            "travel_date": "2026-12-01",
            "ticket_type": "single",
        },
    )
    return resp

class TestTicketCatalog:

    def test_catalog_is_public(self, client):
        """Catalogul e accesibil fără autentificare."""
        resp = client.get("/tickets/catalog")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)

    def test_catalog_has_entries(self, client):
        """Seed-ul demo populează trenuri în catalog."""
        catalog = client.get("/tickets/catalog").json()
        assert len(catalog) > 0, "Catalog gol — verifica seed_demo.sql"

    def test_catalog_entry_has_required_fields(self, client):
        train = _get_first_train(client)
        for field in ("train_id", "train_number", "train_type",
                      "departure_id", "departure_name",
                      "arrival_id", "arrival_name",
                      "route_name", "operator_name"):
            assert field in train, f"Camp lipsa in catalog: {field}"

class TestBuyTicket:

    def test_buy_ticket_success(self, client, passenger_token):
        train = _get_first_train(client)
        resp = _buy_ticket(client, passenger_token, train)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "ticket_id" in data
        assert "qr_token" in data
        assert data["ticket_type"] == "single"
        assert float(data["price"]) > 0

    def test_buy_ticket_requires_auth(self, client):
        train = _get_first_train(client)
        resp = client.post(
            "/tickets/buy",
            json={
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["arrival_id"],
                "travel_date": "2026-12-01",
                "ticket_type": "single",
            },
        )
        assert resp.status_code == 401

    def test_buy_ticket_past_date_fails(self, client, passenger_token):
        train = _get_first_train(client)
        resp = client.post(
            "/tickets/buy",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["arrival_id"],
                "travel_date": "2020-01-01",
                "ticket_type": "single",
            },
        )
        assert resp.status_code in (400, 422), "Data in trecut trebuie refuzata"

    def test_buy_ticket_same_station_fails(self, client, passenger_token):
        train = _get_first_train(client)
        resp = client.post(
            "/tickets/buy",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={
                "train_id": train["train_id"],
                "departure_station_id": train["departure_id"],
                "arrival_station_id": train["departure_id"],   # aceeasi statie
                "travel_date": "2026-12-01",
                "ticket_type": "single",
            },
        )
        assert resp.status_code in (400, 422), "Statie identica plecare=sosire trebuie refuzata"

    def test_conductor_cannot_buy_ticket(self, client, train_verifier_token):
        train = _get_first_train(client)
        resp = _buy_ticket(client, train_verifier_token, train)
        assert resp.status_code == 403, "Conductorul nu trebuie sa poata cumpara bilete"

    def test_student_gets_discount(self, client):
        """user.demo are credential student activ — verificam discount 50%."""
        login = client.post(
            "/auth/login",
            json={"email": "user.demo@railwaydemo.com", "password": "demo2026"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        train = _get_first_train(client)
        resp = _buy_ticket(client, token, train)
        assert resp.status_code == 200, resp.text
        assert resp.json()["discount_applied"] == 50.0, (
            "Student cu credential activ trebuie sa primeasca 50% discount"
        )

class TestListMyTickets:

    def test_new_passenger_has_no_tickets(self, client, passenger_token):
        resp = client.get(
            "/tickets/my",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_after_buy_ticket_appears_in_list(self, client, passenger_token):
        train = _get_first_train(client)
        buy = _buy_ticket(client, passenger_token, train)
        assert buy.status_code == 200

        resp = client.get(
            "/tickets/my",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert resp.status_code == 200
        tickets = resp.json()
        assert len(tickets) == 1
        assert tickets[0]["ticket_type"] == "single"

    def test_list_tickets_requires_auth(self, client):
        resp = client.get("/tickets/my")
        assert resp.status_code == 401

class TestValidateTicket:

    def test_validate_valid_ticket(self, client, passenger_token, train_verifier_token):
        train = _get_first_train(client)
        buy = _buy_ticket(client, passenger_token, train)
        assert buy.status_code == 200
        qr_token = buy.json()["qr_token"]

        resp = client.post(
            "/tickets/validate",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["result"] == "valid"
        assert data["passenger_name"] is not None

    def test_validate_nonexistent_token(self, client, train_verifier_token):
        resp = client.post(
            "/tickets/validate",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": "token_care_nu_exista_nicaieri"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "invalid"

    def test_validate_requires_conductor_role(self, client, passenger_token):
        resp = client.post(
            "/tickets/validate",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"token": "orice_token"},
        )
        assert resp.status_code == 403, "Pasagerul nu poate valida bilete"

    def test_validate_requires_auth(self, client):
        resp = client.post("/tickets/validate", json={"token": "orice"})
        assert resp.status_code == 401

    def test_ticket_single_use_enforcement(self, client, passenger_token, train_verifier_token):
        """SECURITY: al doilea scan al aceluiasi QR trebuie refuzat."""
        train = _get_first_train(client)
        buy = _buy_ticket(client, passenger_token, train)
        assert buy.status_code == 200
        qr_token = buy.json()["qr_token"]

        # Prima validare — trebuie sa reuseasca
        v1 = client.post(
            "/tickets/validate",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )
        assert v1.status_code == 200
        assert v1.json()["result"] == "valid", f"Prima validare a esuat: {v1.json()}"

        # A doua validare cu acelasi token — TREBUIE RESPINSA
        v2 = client.post(
            "/tickets/validate",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )
        assert v2.status_code == 200
        result = v2.json()["result"]
        assert result in ("already_used", "invalid"), (
            f"Replay attack nedetectat! Al doilea scan a returnat '{result}'. "
            "VULNERABILITATE CRITICA DE SECURITATE."
        )

class TestValidationHistory:

    def test_conductor_sees_own_history(self, client, passenger_token, train_verifier_token):
        train = _get_first_train(client)
        buy = _buy_ticket(client, passenger_token, train)
        qr_token = buy.json()["qr_token"]

        client.post(
            "/tickets/validate",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )

        hist = client.get(
            "/validations/history",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
        )
        assert hist.status_code == 200
        entries = hist.json()
        assert len(entries) >= 1

    def test_history_requires_auth(self, client):
        resp = client.get("/validations/history")
        assert resp.status_code == 401

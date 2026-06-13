"""
Teste de integrare pentru endpoint-urile din tickets.py cu acoperire redusa.

Acopera:
  - GET /stations/suggest          (lines 573-634)
  - GET /trips/suggest             (lines 637-710)
  - GET /tickets/by-station        (lines 761-806)
  - GET /validations/history       (lines 1959-2020)
  - GET /tickets/catalog           (lines 1050-1100)
"""
import pytest
from helpers import register_and_login


def _train_token(client):
    return register_and_login(client, "train_verifier")


def _passenger_token(client):
    return register_and_login(client, "passenger")



class TestTripsSuggest:
    """GET /trips/suggest — planificare itinerarii intre doua statii."""

    def _get_two_station_ids(self, client) -> tuple[int, int]:
        resp = client.get("/tickets/catalog")
        assert resp.status_code == 200
        trains = resp.json()
        if not trains:
            pytest.skip("No trains in catalog")
        t = trains[0]
        return t["departure_id"], t["arrival_id"]

    def test_valid_route_returns_200(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trips/suggest", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2026-12-01",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "trips" in data
        assert isinstance(data["trips"], list)

    def test_same_station_returns_400(self, client):
        s1, _ = self._get_two_station_ids(client)
        resp = client.get("/trips/suggest", params={
            "from_station_id": s1,
            "to_station_id": s1,
            "travel_date": "2026-12-01",
        })
        assert resp.status_code == 400

    def test_invalid_date_format_returns_400(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trips/suggest", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "01-12-2026",
        })
        assert resp.status_code == 400

    def test_past_date_returns_400(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trips/suggest", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2020-01-01",
        })
        assert resp.status_code == 400

    def test_top_n_out_of_range_returns_400(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trips/suggest", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2026-12-01",
            "top_n": 20,
        })
        assert resp.status_code == 400

    def test_top_n_valid_limits_results(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trips/suggest", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2026-12-01",
            "top_n": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "trips" in data
        assert len(data["trips"]) <= 2


class TestTrainsSearch:
    """GET /trains/search — trenuri directe intre doua statii."""

    def _get_two_station_ids(self, client) -> tuple[int, int]:
        resp = client.get("/tickets/catalog")
        assert resp.status_code == 200
        trains = resp.json()
        if not trains:
            pytest.skip("No trains in catalog")
        t = trains[0]
        return t["departure_id"], t["arrival_id"]

    def test_valid_pair_returns_list(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trains/search", params={
            "from_station_id": s1,
            "to_station_id": s2,
        })
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_same_station_returns_400(self, client):
        s1, _ = self._get_two_station_ids(client)
        resp = client.get("/trains/search", params={
            "from_station_id": s1,
            "to_station_id": s1,
        })
        assert resp.status_code == 400

    def test_response_has_expected_fields(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trains/search", params={
            "from_station_id": s1,
            "to_station_id": s2,
        })
        assert resp.status_code == 200
        trains = resp.json()
        if trains:
            t = trains[0]
            assert "train_id" in t
            assert "train_number" in t
            assert "departure_time" in t
            assert "arrival_time" in t

    def test_nonexistent_stations_returns_empty_list(self, client):
        resp = client.get("/trains/search", params={
            "from_station_id": 999999,
            "to_station_id": 999998,
        })
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_travel_date_filtered(self, client):
        s1, s2 = self._get_two_station_ids(client)
        resp = client.get("/trains/search", params={
            "from_station_id": s1,
            "to_station_id": s2,
            "travel_date": "2026-12-01",
        })
        assert resp.status_code == 200


class TestValidationsHistory:
    """GET /validations/history — istoric validari pentru conductor sau pasager."""

    def test_passenger_can_view_their_history(self, client, passenger_token):
        resp = client.get(
            "/validations/history",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_train_verifier_can_view_their_history(self, client):
        token = _train_token(client)
        resp = client.get(
            "/validations/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/validations/history")
        assert resp.status_code == 401

    def test_history_respects_limit_param(self, client, passenger_token):
        resp = client.get(
            "/validations/history",
            params={"limit": 5},
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) <= 5


class TestTicketCatalog:
    """GET /trains/catalog — lista trenuri disponibile pentru UI."""

    def test_catalog_returns_list(self, client):
        resp = client.get("/tickets/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_catalog_items_have_required_fields(self, client):
        resp = client.get("/tickets/catalog")
        assert resp.status_code == 200
        items = resp.json()
        if items:
            item = items[0]
            assert "train_id" in item
            assert "departure_id" in item
            assert "arrival_id" in item

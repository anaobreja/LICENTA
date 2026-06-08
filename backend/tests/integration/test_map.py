"""
Teste pentru routerul de harta interactiva (app/routers/map.py).

Strategia:
    Endpoint-urile /map/* citesc din tabelele stations/routes/route_stops/
    trains/railway_operators, care NU sunt populate de seed_demo.sql
    (datele reale vin din `python database/import_cfr.py` cu feed-urile
    GTFS, dar nu rulam importul in pipeline-ul de teste).

    Prin urmare aceste teste verifica CONTRACTUL endpoint-urilor:
        - status code corect,
        - tipul raspunsului (lista vs dict),
        - structura cheilor (cand lista nu e goala, validam shape-ul),
        - tratarea cazurilor 404 / filtre invalide,
        - validitatea SQL-ului (un SQL care arunca eroare ar fi prins
          chiar daca tabelele sunt goale, pentru ca PostgreSQL valideaza
          query-ul la executie).

    Toate endpoint-urile /map/* cer autentificare JWT (orice rol valid).
    Folosim fixture-ul `client` redefinit local care injecteaza automat
    header-ul Authorization cu un token de passenger (din seed-ul demo).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(app):
    """
    Override pe fixture-ul global `client` din conftest.py:
    TestClient cu header Authorization preconfigurat (passenger demo).
    Folosim user.demo seedat (parola demo2026) ca sa nu depinda de
    fixture-uri care la randul lor depind de client.
    """
    from app.core.database import engine
    from conftest import _truncate_transactional_tables
    _truncate_transactional_tables(engine)
    c = TestClient(app)
    resp = c.post(
        "/auth/login",
        json={"email": "user.demo@railwaydemo.com", "password": "demo2026"},
    )
    assert resp.status_code == 200, f"Demo login failed: {resp.text}"
    token = resp.json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


# ======================================================================
# GET /map/stations
# ======================================================================

class TestMapStations:
    """Endpoint-ul pentru lista de statii cu coordonate GPS."""

    STATION_KEYS = {
        "station_id", "name", "code", "city",
        "latitude", "longitude",
        "is_university_hub", "student_count", "universities_count",
        "notes", "trains_count",
    }

    def test_returns_200_and_list(self, client: TestClient):
        """Apel fara parametri: 200 + lista (eventual goala)."""
        response = client.get("/map/stations")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_only_university_filter_accepted(self, client: TestClient):
        """Filtrul `only_university=true` este acceptat si returneaza lista."""
        response = client.get("/map/stations?only_university=true")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_operator_filter_with_nonexistent_id_returns_empty(self, client: TestClient):
        """Filtrul cu operator inexistent -> lista goala (nu 500)."""
        response = client.get("/map/stations?operator_id=999999")
        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_combined_filters_accepted(self, client: TestClient):
        """Filtru combinat only_university + operator_id valid sintactic."""
        response = client.get("/map/stations?only_university=true&operator_id=1")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_response_shape_when_data_exists(self, client: TestClient):
        """Daca exista date in DB, fiecare statie are cheile asteptate."""
        response = client.get("/map/stations")
        assert response.status_code == 200
        rows = response.json()
        if not rows:
            return  # gol => contract de keys verificat indirect prin SQL valid
        first = rows[0]
        missing = self.STATION_KEYS - set(first.keys())
        assert not missing, f"Chei lipsa in response: {missing}"
        # latitudine/longitudine ca numeric (float) sau None
        assert first["latitude"] is None or isinstance(first["latitude"], (int, float))
        assert first["longitude"] is None or isinstance(first["longitude"], (int, float))
        # trains_count: integer >= 0
        assert isinstance(first["trains_count"], int)
        assert first["trains_count"] >= 0


# ======================================================================
# GET /map/connections
# ======================================================================

class TestMapConnections:
    """Perechi de statii conectate prin trenuri directe (CTE + self-join)."""

    CONNECTION_KEYS = {
        "from_id", "from_name", "from_lat", "from_lon",
        "to_id", "to_name", "to_lat", "to_lon",
        "trains_count", "distance_km",
    }

    def test_returns_200_and_list(self, client: TestClient):
        """SQL-ul cu CTE + self-join pe route_stops se executa fara eroare."""
        response = client.get("/map/connections")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_min_trains_filter_accepted(self, client: TestClient):
        """Parametrul min_trains este interpretat ca int si aplicat in HAVING."""
        response = client.get("/map/connections?min_trains=5")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_only_university_false_accepted(self, client: TestClient):
        """Filtrul only_university=false dezactiveaza restrictia pe hub-uri."""
        response = client.get("/map/connections?only_university=false")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_operator_filter_accepted(self, client: TestClient):
        """Filtru pe operator_id inexistent -> lista goala."""
        response = client.get("/map/connections?operator_id=999999")
        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_high_min_trains_returns_empty(self, client: TestClient):
        """min_trains foarte mare => zero conexiuni (clauza HAVING)."""
        response = client.get("/map/connections?min_trains=999999")
        assert response.status_code == 200
        assert response.json() == []

    def test_response_shape_when_data_exists(self, client: TestClient):
        """Cand exista conexiuni, structura raspunsului e completa."""
        response = client.get("/map/connections?only_university=false&min_trains=1")
        rows = response.json()
        if not rows:
            return
        first = rows[0]
        missing = self.CONNECTION_KEYS - set(first.keys())
        assert not missing, f"Chei lipsa in response: {missing}"
        # trains_count >= min_trains
        assert first["trains_count"] >= 1
        # coordonate numerice
        for key in ("from_lat", "from_lon", "to_lat", "to_lon"):
            assert isinstance(first[key], (int, float)), f"{key} nu e numeric"


# ======================================================================
# GET /map/operators
# ======================================================================

class TestMapOperators:
    """Lista operatori feroviari activi (pentru dropdown UI)."""

    OPERATOR_KEYS = {"operator_id", "name", "code", "trains_count"}

    def test_returns_200_and_list(self, client: TestClient):
        response = client.get("/map/operators")
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_response_shape_when_data_exists(self, client: TestClient):
        response = client.get("/map/operators")
        rows = response.json()
        if not rows:
            return
        first = rows[0]
        missing = self.OPERATOR_KEYS - set(first.keys())
        assert not missing, f"Chei lipsa in response: {missing}"
        assert isinstance(first["operator_id"], int)
        assert isinstance(first["name"], str) and first["name"]
        assert isinstance(first["trains_count"], int) and first["trains_count"] >= 0

    def test_operators_ordered_by_trains_count_desc(self, client: TestClient):
        """Lista vine ordonata descrescator dupa trains_count (cand >= 2)."""
        rows = client.get("/map/operators").json()
        if len(rows) < 2:
            return
        counts = [r["trains_count"] for r in rows]
        assert counts == sorted(counts, reverse=True), \
            f"Operatorii nu sunt ordonati desc dupa trains_count: {counts}"


# ======================================================================
# GET /map/train-simulate/{train_id}
# ======================================================================

class TestTrainSimulate:
    """Simulator de pozitie tren (interpolare liniara pe segmentul curent)."""

    VALID_STATUSES = {"in_transit", "not_departed", "arrived", "no_gps"}

    def test_nonexistent_train_returns_404(self, client: TestClient):
        """Train_id inexistent -> 404 cu mesaj clar."""
        response = client.get("/map/train-simulate/999999999")
        assert response.status_code == 404, response.text
        body = response.json()
        assert "detail" in body
        assert "exista" in body["detail"].lower() or "exist" in body["detail"].lower()

    def test_negative_id_returns_404(self, client: TestClient):
        """Train_id negativ -> nu exista in DB -> 404 (nu 422 sau 500)."""
        response = client.get("/map/train-simulate/-1")
        assert response.status_code == 404, response.text

    def test_zero_id_returns_404(self, client: TestClient):
        """Train_id = 0 nu exista (SERIAL incepe de la 1) -> 404."""
        response = client.get("/map/train-simulate/0")
        assert response.status_code == 404, response.text

    def test_non_integer_id_returns_422(self, client: TestClient):
        """Train_id non-numeric -> FastAPI valideaza si returneaza 422."""
        response = client.get("/map/train-simulate/abc")
        assert response.status_code == 422, response.text

    def test_returns_valid_status_when_train_exists(self, client: TestClient):
        """
        Pentru un train_id valid (daca exista in DB de test):
            - 200
            - status in setul cunoscut
            - cheile esentiale prezente.
        Daca tabela trains e goala in DB-ul de test (caz uzual),
        testul devine no-op (pass) prin filtrul cu operatori.
        """
        ops = client.get("/map/operators").json()
        if not ops:
            return  # DB de test fara date de transport — skip silentios

        # Avem operatori => poate avem si trenuri. Incercam o cautare
        # discreta prin search_trains (alternativ: introgam direct DB).
        stations = client.get("/map/stations").json()
        if len(stations) < 2:
            return

        # Nu putem garanta ca exista trenuri intre orice 2 statii,
        # asa ca incercam doar contractul: daca train_id=1 exista,
        # raspunsul respecta shape-ul; daca nu, e 404.
        response = client.get("/map/train-simulate/1")
        if response.status_code == 404:
            return  # ok — pur si simplu nu exista train_id=1

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] in self.VALID_STATUSES, \
            f"Status invalid: {body['status']}"
        for key in ("train_id", "train_number", "train_type", "operator",
                    "status", "current_lat", "current_lon",
                    "current_station", "next_station", "progress_percent"):
            assert key in body, f"Cheia '{key}' lipseste din raspuns"
        # progress_percent in [0, 100]
        assert 0 <= body["progress_percent"] <= 100


# ======================================================================
# Teste cross-endpoint (sanity)
# ======================================================================

class TestMapEndpointsSanity:
    """Verificari globale ca endpoint-urile sunt inregistrate corect."""

    def test_all_endpoints_require_auth(self, app):
        """
        Toate endpoint-urile /map/* cer JWT valid.
        Verificam ca FARA token returneaza 401 (security regression test).
        """
        plain = TestClient(app)  # fara header Authorization
        for path in ("/map/stations", "/map/connections", "/map/operators"):
            response = plain.get(path)
            assert response.status_code == 401, \
                f"{path} ar trebui sa ceara autentificare, a returnat {response.status_code}"

    def test_all_endpoints_reachable_with_auth(self, client: TestClient):
        """Cu token valid de passenger, endpoint-urile raspund cu 200 si lista."""
        for path in ("/map/stations", "/map/connections", "/map/operators"):
            response = client.get(path)
            assert response.status_code != 401, f"{path} a refuzat token-ul valid"
            assert response.status_code != 403, f"{path} este interzis pt. passenger"
            assert response.status_code < 500, \
                f"{path} arunca eroare server: {response.text}"

    def test_invalid_query_param_type_handled(self, client: TestClient):
        """Parametri cu tip gresit -> 422 (FastAPI validation), nu 500."""
        # operator_id ar trebui sa fie int
        response = client.get("/map/stations?operator_id=not-a-number")
        assert response.status_code == 422, response.text

"""
Teste pentru regula de "ruta personala" + discount conditionat (OUG 11/2024).

Conform legii, reducerea de 90% pentru studenti se aplica DOAR pe ruta intre
localitatea de domiciliu si cea a institutiei de invatamint. Pe alte rute,
biletul se cumpara cu tarif intreg.

Testele acopera:
    - GET /users/me returneaza home_station si university_station
    - PUT /users/me accepta home_station_id si valideaza ca statia exista
    - PUT /users/me cu home_station_id = 0 sterge selectia
    - quote_ticket aplica discountul DOAR pe ruta personala
    - quote_ticket nu aplica discount pe alta ruta (chiar daca userul are credential student)
    - user fara home_station declarata -> mereu tarif intreg
    - user fara credential student -> mereu tarif intreg (chiar si pe ruta personala)

Strategia tehnica:
    Userii sunt creati direct in DB cu un hash bcrypt pre-calculat pentru
    parola "demo2026" (acelasi hash folosit in seed_demo.sql). Asta evita
    dependenta de helpers.register_and_login + reduce timpul de test.
    Credential-urile student_verified sunt inserate direct in user_credentials,
    simulind ce face agentul universitar dupa aprobare.

Fixture-uri:
    home_station_iasi  — station_id pentru "Iaşi" (sau prima statie disponibila)
    upb_main_station   — station_id pentru "Bucureşti Nord Gr.A" (setat in
                         seed-ul demo pe universities.main_station_id pt UPB)
    student_with_home  — user UPB cu home_station Iași + credential student activ
    student_no_home    — user UPB cu credential student activ DAR fara home_station
    user_no_credential — user UPB cu home_station setat DAR fara credential
"""

import time
import uuid

import pytest
from sqlalchemy import text


def _unique_email(prefix: str) -> str:
    """Email unic per test pentru a evita coliziuni de UNIQUE(email)."""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}@test.local"


# bcrypt hash pentru parola "demo2026" — acelasi ca in seed_demo.sql
BCRYPT_HASH_DEMO2026 = "$2b$12$HijeaYT9.i7NHMV/w9m4eez/yAa6hzJprroikrkomRWEbSnp7pIgO"


# ============================================================================
# Helpers — manipulare directa DB pentru izolare maxima
# ============================================================================

def _engine():
    """Returneaza engine-ul SQLAlchemy din app."""
    from app.core.database import engine
    return engine


def _get_station_id(name_like: str) -> int | None:
    """Cauta o statie dupa nume (case-insensitive)."""
    with _engine().connect() as conn:
        row = conn.execute(
            text("SELECT station_id FROM stations WHERE name ILIKE :n LIMIT 1"),
            {"n": name_like},
        ).first()
    return row[0] if row else None


def _get_upb_id() -> int:
    with _engine().connect() as conn:
        row = conn.execute(
            text("SELECT university_id FROM universities WHERE short_name = 'UPB'"),
        ).first()
    assert row is not None, "UPB lipseste din seed"
    return row[0]


def _create_user(
    email: str,
    *,
    home_station_id: int | None = None,
    with_student_credential: bool = False,
) -> int:
    """
    Creeaza un user in DB cu parola 'demo2026' (hash pre-calculat).
    Optional: seteaza home_station_id si insereaza credential student activ.
    Returneaza user_id.
    """
    upb_id = _get_upb_id()
    with _engine().begin() as conn:
        user_id = conn.execute(
            text(
                """
                INSERT INTO users
                    (first_name, last_name, email, password_hash,
                     role, university_id, home_station_id, is_active)
                VALUES
                    ('Test', 'User', :email, :hash,
                     'passenger', :uid, :home, TRUE)
                RETURNING user_id
                """
            ),
            {
                "email": email,
                "hash": BCRYPT_HASH_DEMO2026,
                "uid": upb_id,
                "home": home_station_id,
            },
        ).scalar()

        if with_student_credential:
            # Avem nevoie de un issuer_id valid (UPB issuer)
            issuer_id = conn.execute(
                text(
                    "SELECT id FROM issuers WHERE name = 'Universitatea Politehnica Bucuresti (UPB)'"
                ),
            ).scalar()
            assert issuer_id is not None, "UPB issuer lipseste din seed"

            conn.execute(
                text(
                    """
                    INSERT INTO user_credentials
                        (user_id, credential_type, claim_value, issuer_id,
                         status, valid_until)
                    VALUES
                        (:uid, 'student_verified', 'TEST-STUDENT-01', :iid,
                         'active', CURRENT_TIMESTAMP + INTERVAL '365 days')
                    """
                ),
                {"uid": user_id, "iid": issuer_id},
            )
    return user_id


def _issue_token(user_id: int) -> str:
    """Genereaza un JWT pentru user_id (foloseste create_access_token din app)."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(user_id)})


def _get_train_between(from_station_id: int, to_station_id: int) -> dict | None:
    """
    Cauta primul tren direct intre 2 statii (folosind logica din DB,
    nu endpoint-ul HTTP — vrem sa fie izolate de eventuale bug-uri).
    """
    with _engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT DISTINCT ON (t.train_id)
                    t.train_id, t.train_number, t.train_type, r.route_id
                FROM trains t
                JOIN routes r ON r.route_id = t.route_id
                JOIN route_stops rs_from ON rs_from.route_id = r.route_id
                    AND rs_from.station_id = :dep
                JOIN route_stops rs_to ON rs_to.route_id = r.route_id
                    AND rs_to.station_id = :arr
                WHERE t.is_active = TRUE
                  AND rs_from.stop_order < rs_to.stop_order
                ORDER BY t.train_id
                LIMIT 1
                """
            ),
            {"dep": from_station_id, "arr": to_station_id},
        ).mappings().first()
    return dict(row) if row else None


# ============================================================================
# Fixture-uri
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def _seed_railway_minimal():
    """
    Seed minimal de transport pentru testele de pricing.
    Inserat doar daca tabelele sunt goale (DB de test curat).
    Pe DB real cu importul CFR (1818 statii), nu modifica nimic.
    """
    with _engine().begin() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM stations")).scalar() or 0
        if existing > 0:
            return  # DB cu date reale -> nu interferam

        # Insert: 4 statii + 1 operator + 2 rute + 2 trenuri + tarif brackets
        conn.execute(
            text(
                """
                INSERT INTO stations (name, code, city) VALUES
                    ('Iaşi',                'CFR-50000', 'Iasi'),
                    ('Bucureşti Nord Gr.A', 'CFR-10017', 'Bucuresti'),
                    ('Cluj-Napoca',         'CFR-30000', 'Cluj-Napoca'),
                    ('Braşov',              'CFR-30691', 'Brasov')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO railway_operators (name, code, country)
                VALUES ('SNTFC CFR Calatori S.A.', 'CFR', 'Romania')
                """
            )
        )
        op_id = conn.execute(
            text("SELECT operator_id FROM railway_operators WHERE code = 'CFR'")
        ).scalar()
        iasi   = conn.execute(text("SELECT station_id FROM stations WHERE name='Iaşi'")).scalar()
        bucn   = conn.execute(text("SELECT station_id FROM stations WHERE name='Bucureşti Nord Gr.A'")).scalar()
        cluj   = conn.execute(text("SELECT station_id FROM stations WHERE name='Cluj-Napoca'")).scalar()
        brasov = conn.execute(text("SELECT station_id FROM stations WHERE name='Braşov'")).scalar()

        # Ruta 1: Iași -> BUC Nord (~400 km)
        r1 = conn.execute(
            text(
                """
                INSERT INTO routes
                    (operator_id, route_name, route_code,
                     origin_station_id, destination_station_id, total_distance_km)
                VALUES
                    (:op, 'Iași — București Nord', 'TST-IS-BN', :a, :b, 400)
                RETURNING route_id
                """
            ),
            {"op": op_id, "a": iasi, "b": bucn},
        ).scalar()
        conn.execute(
            text(
                """
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                          distance_from_origin_km, departure_time, arrival_time)
                VALUES
                    (:r, :iasi, 1,   0, '08:00', NULL),
                    (:r, :bucn, 2, 400, NULL,    '14:00')
                """
            ),
            {"r": r1, "iasi": iasi, "bucn": bucn},
        )
        conn.execute(
            text(
                """
                INSERT INTO trains (operator_id, route_id, train_number, train_type)
                VALUES (:op, :r, 'IR1668', 'interregio')
                """
            ),
            {"op": op_id, "r": r1},
        )

        # Ruta 1b: BUC Nord -> Iași (sensul invers, pentru testul de
        # discount pe directia opusa)
        r1b = conn.execute(
            text(
                """
                INSERT INTO routes
                    (operator_id, route_name, route_code,
                     origin_station_id, destination_station_id, total_distance_km)
                VALUES
                    (:op, 'București Nord — Iași', 'TST-BN-IS', :a, :b, 400)
                RETURNING route_id
                """
            ),
            {"op": op_id, "a": bucn, "b": iasi},
        ).scalar()
        conn.execute(
            text(
                """
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                          distance_from_origin_km, departure_time, arrival_time)
                VALUES
                    (:r, :bucn, 1,   0, '15:00', NULL),
                    (:r, :iasi, 2, 400, NULL,    '21:00')
                """
            ),
            {"r": r1b, "iasi": iasi, "bucn": bucn},
        )
        conn.execute(
            text(
                """
                INSERT INTO trains (operator_id, route_id, train_number, train_type)
                VALUES (:op, :r, 'IR1669', 'interregio')
                """
            ),
            {"op": op_id, "r": r1b},
        )

        # Ruta 2: Cluj -> Brașov (~250 km, ne-personala pentru un student UPB)
        r2 = conn.execute(
            text(
                """
                INSERT INTO routes
                    (operator_id, route_name, route_code,
                     origin_station_id, destination_station_id, total_distance_km)
                VALUES
                    (:op, 'Cluj — Brașov', 'TST-CJ-BV', :a, :b, 250)
                RETURNING route_id
                """
            ),
            {"op": op_id, "a": cluj, "b": brasov},
        ).scalar()
        conn.execute(
            text(
                """
                INSERT INTO route_stops (route_id, station_id, stop_order,
                                          distance_from_origin_km, departure_time, arrival_time)
                VALUES
                    (:r, :cluj,   1,   0, '07:00', NULL),
                    (:r, :brasov, 2, 250, NULL,    '12:00')
                """
            ),
            {"r": r2, "cluj": cluj, "brasov": brasov},
        )
        conn.execute(
            text(
                """
                INSERT INTO trains (operator_id, route_id, train_number, train_type)
                VALUES (:op, :r, 'IR4321', 'interregio')
                """
            ),
            {"op": op_id, "r": r2},
        )

    # NOTA: tabelele stations/routes/route_stops/trains/railway_operators/
    # tariff_brackets sunt deja in KEEP_TABLES (conftest.py), deci nu vor fi
    # sterse intre teste. Seedul de mai sus este aplicat o singura data per
    # sesiune si pastrat ca date de referinta.


@pytest.fixture
def upb_main_station(client) -> int:
    """station_id pentru Bucuresti Nord Gr.A (statia principala UPB)."""
    sid = _get_station_id("Bucureşti Nord Gr.A")
    if sid is None:
        pytest.skip("Statia Bucuresti Nord Gr.A nu exista")
    return sid


@pytest.fixture
def home_station_iasi(client) -> int:
    """station_id pentru Iași (stație de domiciliu de test)."""
    sid = _get_station_id("Iaşi") or _get_station_id("Iasi")
    if sid is None:
        pytest.skip("Statia Iasi nu exista in DB de test")
    return sid


@pytest.fixture
def home_station_cluj(client) -> int:
    """station_id pentru Cluj — folosit ca destinatie alternativa."""
    sid = _get_station_id("Cluj-Napoca")
    if sid is None:
        pytest.skip("Statia Cluj-Napoca nu exista in DB de test")
    return sid


@pytest.fixture
def upb_main_set(client, upb_main_station):
    """Asigura ca UPB are main_station_id setat la BUC Nord (idempotent)."""
    with _engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE universities SET main_station_id = :sid "
                "WHERE short_name = 'UPB'"
            ),
            {"sid": upb_main_station},
        )


@pytest.fixture
def student_with_home(client, home_station_iasi, upb_main_set):
    """
    User UPB cu:
      - home_station_id = Iasi
      - credential student_verified activ
    """
    user_id = _create_user(
        email=_unique_email("student.iasi"),
        home_station_id=home_station_iasi,
        with_student_credential=True,
    )
    return {
        "user_id": user_id,
        "token": _issue_token(user_id),
        "home_station_id": home_station_iasi,
    }


@pytest.fixture
def student_no_home(client, upb_main_set):
    """User UPB cu credential student DAR fara home_station declarat."""
    user_id = _create_user(
        email=_unique_email("student.nohome"),
        home_station_id=None,
        with_student_credential=True,
    )
    return {
        "user_id": user_id,
        "token": _issue_token(user_id),
    }


@pytest.fixture
def user_no_credential(client, home_station_iasi, upb_main_set):
    """User UPB cu home_station DAR fara credential student."""
    user_id = _create_user(
        email=_unique_email("user.nocred"),
        home_station_id=home_station_iasi,
        with_student_credential=False,
    )
    return {
        "user_id": user_id,
        "token": _issue_token(user_id),
        "home_station_id": home_station_iasi,
    }


# ============================================================================
# Helper: quote-uieste un bilet
# ============================================================================

def _quote(client, token: str, train_id: int, dep_id: int, arr_id: int) -> dict:
    resp = client.post(
        "/tickets/quote",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "train_id": train_id,
            "departure_station_id": dep_id,
            "arrival_station_id": arr_id,
            "travel_date": "2027-01-15",
            "ticket_type": "single",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ============================================================================
# Teste GET / PUT /users/me cu home_station
# ============================================================================

class TestUserHomeStationAPI:

    def test_me_returns_home_station_when_set(
        self, client, student_with_home, home_station_iasi, upb_main_station
    ):
        """GET /users/me returneaza home_station + university_station."""
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {student_with_home['token']}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["home_station"] is not None
        assert data["home_station"]["station_id"] == home_station_iasi
        assert "Ia" in data["home_station"]["name"]  # Iaşi / Iasi

        assert data["university_station"] is not None
        assert data["university_station"]["station_id"] == upb_main_station

    def test_me_home_station_null_when_not_set(self, client, student_no_home):
        """User fara home_station declarat -> home_station: null."""
        resp = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {student_no_home['token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["home_station"] is None

    def test_put_me_sets_home_station(
        self, client, student_no_home, home_station_iasi
    ):
        """PUT /users/me cu home_station_id valid -> seteaza statia."""
        resp = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {student_no_home['token']}"},
            json={"home_station_id": home_station_iasi},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["home_station"]["station_id"] == home_station_iasi

    def test_put_me_clears_home_station_with_zero(
        self, client, student_with_home
    ):
        """PUT /users/me cu home_station_id = 0 -> sterge selectia."""
        resp = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {student_with_home['token']}"},
            json={"home_station_id": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["home_station"] is None

    def test_put_me_rejects_nonexistent_station(self, client, student_with_home):
        """PUT /users/me cu station_id inexistent -> 400."""
        resp = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {student_with_home['token']}"},
            json={"home_station_id": 999999999},
        )
        assert resp.status_code == 400, resp.text
        assert "nu exista" in resp.json()["detail"].lower() \
            or "inactiv" in resp.json()["detail"].lower()


# ============================================================================
# Teste discount conditionat (pricing rule core)
# ============================================================================

class TestPersonalRouteDiscount:

    def test_discount_applied_on_personal_route(
        self, client, student_with_home, home_station_iasi, upb_main_station
    ):
        """
        Iași -> Bucuresti Nord pentru un student verificat cu home=Iași:
        DISCOUNT-ul de student trebuie aplicat.
        """
        train = _get_train_between(home_station_iasi, upb_main_station)
        if train is None:
            pytest.skip("Nu exista tren direct Iași -> BUC Nord in DB")

        q = _quote(
            client,
            student_with_home["token"],
            train["train_id"],
            home_station_iasi,
            upb_main_station,
        )

        assert q["is_personal_route"] is True, (
            f"Ruta Iași -> BUC Nord ar trebui sa fie personala. "
            f"Reason: {q.get('route_reason')}"
        )
        assert q["discount_percent"] > 0, (
            f"Discountul trebuia aplicat. Actual: {q['discount_percent']}%"
        )
        assert q["final_price"] < q["base_price"]
        assert q["savings"] > 0

    def test_discount_applied_on_reverse_direction(
        self, client, student_with_home, home_station_iasi, upb_main_station
    ):
        """
        Bucuresti Nord -> Iași (sensul invers) trebuie sa fie tot ruta personala.
        """
        train = _get_train_between(upb_main_station, home_station_iasi)
        if train is None:
            pytest.skip("Nu exista tren direct BUC Nord -> Iași in DB")

        q = _quote(
            client,
            student_with_home["token"],
            train["train_id"],
            upb_main_station,
            home_station_iasi,
        )

        assert q["is_personal_route"] is True
        assert q["discount_percent"] > 0

    def test_no_discount_on_other_route(
        self, client, student_with_home, home_station_cluj
    ):
        """
        Cluj -> Brașov pentru un student cu home=Iași:
        NU se aplica discount (ruta nu corespunde traseului personal).
        """
        brasov_id = _get_station_id("Braşov")
        if brasov_id is None:
            pytest.skip("Brașov nu exista in DB")

        train = _get_train_between(home_station_cluj, brasov_id)
        if train is None:
            pytest.skip("Nu exista tren direct Cluj -> Brașov in DB")

        q = _quote(
            client,
            student_with_home["token"],
            train["train_id"],
            home_station_cluj,
            brasov_id,
        )

        assert q["is_personal_route"] is False, (
            "Ruta Cluj -> Brașov NU ar trebui sa fie personala "
            "pentru un user cu home=Iași."
        )
        assert q["discount_percent"] == 0, (
            f"Pe alte rute nu se aplica discount student. "
            f"Actual: {q['discount_percent']}%"
        )
        assert q["final_price"] == q["base_price"]

    def test_user_without_home_station_pays_full(
        self, client, student_no_home, home_station_iasi, upb_main_station
    ):
        """
        Student cu credential dar fara home_station -> tarif intreg peste tot,
        chiar daca cumpara pe ce s-ar fi putut considera ruta universitatii.
        """
        train = _get_train_between(home_station_iasi, upb_main_station)
        if train is None:
            pytest.skip("Nu exista tren direct Iași -> BUC Nord")

        q = _quote(
            client,
            student_no_home["token"],
            train["train_id"],
            home_station_iasi,
            upb_main_station,
        )

        assert q["is_personal_route"] is False
        assert q["discount_percent"] == 0
        assert q["final_price"] == q["base_price"]
        # Mesajul trebuie sa indice ca lipseste home_station
        assert "domiciliu" in q["route_reason"].lower() \
            or "declarata" in q["route_reason"].lower()

    def test_user_without_credential_pays_full_even_on_personal_route(
        self, client, user_no_credential, home_station_iasi, upb_main_station
    ):
        """
        User cu home_station setat DAR fara credential student:
        chiar pe ruta personala, discountul = 0 (nu are dreptul la el).
        """
        train = _get_train_between(home_station_iasi, upb_main_station)
        if train is None:
            pytest.skip("Nu exista tren direct Iași -> BUC Nord")

        q = _quote(
            client,
            user_no_credential["token"],
            train["train_id"],
            home_station_iasi,
            upb_main_station,
        )

        # is_personal_route poate fi True (statiile match), DAR discountul
        # ramine 0 pentru ca _user_discount returneaza 0 fara credential.
        assert q["discount_percent"] == 0, (
            "User fara credential student NU primeste discount, "
            "chiar daca ruta e personala."
        )
        assert q["final_price"] == q["base_price"]

    def test_buy_response_includes_route_status(
        self, client, student_with_home, home_station_iasi, upb_main_station
    ):
        """buy_ticket returneaza is_personal_route + route_reason in raspuns."""
        train = _get_train_between(home_station_iasi, upb_main_station)
        if train is None:
            pytest.skip("Nu exista tren direct Iași -> BUC Nord")

        resp = client.post(
            "/tickets/buy",
            headers={"Authorization": f"Bearer {student_with_home['token']}"},
            json={
                "train_id": train["train_id"],
                "departure_station_id": home_station_iasi,
                "arrival_station_id": upb_main_station,
                "travel_date": "2027-01-15",
                "ticket_type": "single",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "is_personal_route" in body
        assert "route_reason" in body
        assert body["is_personal_route"] is True
        assert body["discount_applied"] > 0

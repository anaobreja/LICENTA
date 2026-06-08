
import os
import sys
from pathlib import Path

# ===== 1. Configurare DB de test ============================================
_DEFAULT_TEST_URL = "postgresql+psycopg://railway:railway_dev@localhost:5432/railway_test_db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_URL)
os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-pytest-min-32-characters-long")
TEST_DB_URL = os.environ["DATABASE_URL"]

BACKEND_PATH = Path(__file__).resolve().parent.parent
TESTS_PATH = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_PATH))
sys.path.insert(0, str(TESTS_PATH))

import pytest
import psycopg
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from helpers import register_and_login

# ===== 2. Helpers DB ========================================================
REPO_ROOT = BACKEND_PATH.parent
SCHEMA_PATH = REPO_ROOT / "database" / "schema.sql"
SEED_PATH = REPO_ROOT / "database" / "seed_demo.sql"

# Tabele care raman dupa cleanup (seed-ul demo + datele de transport).
# Includem TOATE tabelele de transport pentru ca:
#   1) test_map.py si test_personal_route.py au nevoie de stations/trains/routes
#      ca date de referinta, inserate o data per sesiune (fie din seed,
#      fie din fixture-ul _seed_railway_minimal).
#   2) cleanup-ul intre teste sterge doar datele tranzitorii (bilete, validari,
#      tokens, audit logs), nu si infrastructura de transport.
KEEP_TABLES = {
    "universities", "users", "issuers", "stations", "trains", "routes",
    "railway_operators", "university_students",
    "route_stops", "tariff_brackets",
    # cardul + credentialul demo seedate pentru user.demo:
    "digital_cards", "user_credentials",
    # Infrastructura statica de vagoane si locuri (generata o data per tren,
    # in fixture-ele de test — nu se modifica intre teste).
    "train_cars", "seats",
}

def _psycopg_dsn(url: str) -> str:
    """Converteste URL SQLAlchemy in DSN psycopg pur (fara '+psycopg')."""
    return url.replace("postgresql+psycopg://", "postgresql://")

def _preflight_check_postgres():
    """
    Verifica daca PostgreSQL e accesibil INAINTE de a porni testele.

    Fara aceasta verificare, daca Docker nu e pornit, psycopg.connect() ar
    astepta ~75s (timeout TCP default pe Windows) la primul test, apoi ar
    crapa cu un traceback lung si confuz. Aici verificam in <3 secunde si
    afisam un mesaj cu instructiuni exacte.
    """
    admin_dsn = _admin_dsn()
    try:
        with psycopg.connect(admin_dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as e:
        msg = (
            "\n"
            + "=" * 70 + "\n"
            + "  EROARE: Nu pot conecta la PostgreSQL.\n"
            + "=" * 70 + "\n"
            + f"  URL incercat: {admin_dsn}\n"
            + f"  Motiv:        {type(e).__name__}: {e}\n"
            + "\n"
            + "  PostgreSQL nu este pornit. Pasii pentru a-l porni:\n"
            + "\n"
            + "    1. Porneste Docker Desktop (asteapta sa devina stabil).\n"
            + "    2. In terminal, din D:\\LICENTA:\n"
            + "         docker-compose up -d postgres\n"
            + "    3. Asteapta ~5 secunde. Verifica cu:\n"
            + "         docker ps --filter name=railway_db\n"
            + "       Trebuie sa vezi STATUS 'Up X seconds (healthy)'.\n"
            + "    4. Re-ruleaza pytest.\n"
            + "\n"
            + "  Pentru a folosi alta DB de test, seteaza TEST_DATABASE_URL\n"
            + "  in environment inainte de pytest.\n"
            + "=" * 70 + "\n"
        )
        pytest.exit(msg, returncode=2)

def _get_test_db_name() -> str:
    return TEST_DB_URL.rsplit("/", 1)[1]

def _admin_dsn() -> str:
    """DSN catre database 'postgres' (pentru DROP/CREATE DATABASE)."""
    return _psycopg_dsn(TEST_DB_URL.rsplit("/", 1)[0] + "/postgres")

def _recreate_test_database():
    """Recreeaza DB-ul de test si incarca schema + seed prin psycopg (multi-statement)."""
    _preflight_check_postgres()
    db_name = _get_test_db_name()

    # 1. DROP + CREATE prin conexiune admin
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            cur.execute(f'CREATE DATABASE "{db_name}"')

    # 2. Incarca schema + seed (psycopg accepta multi-statement direct)
    with psycopg.connect(_psycopg_dsn(TEST_DB_URL), autocommit=True) as conn:
        with conn.cursor() as cur:
            for path in (SCHEMA_PATH, SEED_PATH):
                sql = path.read_text(encoding="utf-8")
                cur.execute(sql)

def _truncate_transactional_tables(engine):
    """Goleste tabelele tranzitorii (pastreaza seed-ul demo)."""
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE'"
        )).fetchall()
        to_truncate = [r[0] for r in rows if r[0] not in KEEP_TABLES]
        if to_truncate:
            conn.execute(text(
                "TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in to_truncate)
                + " RESTART IDENTITY CASCADE"
            ))

# ===== 3. Session-scope: create test DB once =================================
@pytest.fixture(scope="session", autouse=True)
def _setup_test_database():
    """Creeaza DB de test o singura data per sesiune."""
    _recreate_test_database()
    yield


@pytest.fixture(scope="session", autouse=True)
def _seed_default_train_catalog(_setup_test_database):
    """
    Garanteaza ca exista cel putin un tren cu ruta + tariff_brackets in DB-ul
    de test, ca testele care apeleaza GET /tickets/catalog sa primeasca date.

    Schema fresh creeaza tabelele goale, iar seed_demo.sql adauga doar useri si
    universitati (NU trenuri — astea vin in productie din import_cfr.py).
    Aici facem un setup minim, idempotent (ON CONFLICT), pentru ca testele
    preexistente (test_tickets, test_personal_route, etc.) sa aiba pe ce lucra.
    """
    from app.core.database import engine as eng

    with eng.begin() as conn:
        # Operator
        op_id = conn.execute(text("""
            INSERT INTO railway_operators (code, name)
            VALUES ('CFR_DEFAULT', 'CFR Calatori (default test)')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING operator_id
        """)).scalar()

        # Statii — Iasi si Bucuresti Nord Gr.A (asteptate de test_tickets.py)
        s_iasi = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('IS_DEF', 'Iaşi', 'Iaşi', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()
        s_buc = conn.execute(text("""
            INSERT INTO stations (code, name, city, country)
            VALUES ('BN_DEF', 'Bucureşti Nord Gr.A', 'Bucureşti', 'Romania')
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
            RETURNING station_id
        """)).scalar()

        # Ruta — Iasi -> Bucuresti Nord
        route_id = conn.execute(text("""
            INSERT INTO routes (route_name, route_code, operator_id,
                                origin_station_id, destination_station_id,
                                total_distance_km)
            VALUES ('Iasi - Bucuresti Nord', 'IS-BN-DEF', :op, :s1, :s2, 406)
            ON CONFLICT (route_code) DO UPDATE SET route_name = EXCLUDED.route_name
            RETURNING route_id
        """), {"op": op_id, "s1": s_iasi, "s2": s_buc}).scalar()

        # Trenul IR 1582
        train_id = conn.execute(text("""
            INSERT INTO trains (operator_id, route_id, train_number, train_type,
                                capacity_seats, is_active)
            VALUES (:op, :rt, 'IR1582-DEF', 'interregio', 280, TRUE)
            ON CONFLICT (operator_id, train_number) DO UPDATE
                SET train_type = EXCLUDED.train_type, is_active = TRUE
            RETURNING train_id
        """), {"op": op_id, "rt": route_id}).scalar()

        # Route stops cu departure/arrival times pentru test de anti-overlap
        conn.execute(text("""
            INSERT INTO route_stops (route_id, station_id, stop_order,
                                     arrival_time, departure_time,
                                     distance_from_origin_km)
            VALUES
                (:rt, :s1, 1, NULL,            '08:00'::TIME, 0),
                (:rt, :s2, 2, '14:30'::TIME,   NULL,          406)
            ON CONFLICT (route_id, stop_order) DO UPDATE SET
                arrival_time = EXCLUDED.arrival_time,
                departure_time = EXCLUDED.departure_time
        """), {"rt": route_id, "s1": s_iasi, "s2": s_buc})

        # Genereaza vagoane si locuri
        conn.execute(text("SELECT generate_train_layout(:t)"), {"t": train_id})

        # Tariff brackets — schema reala: train_category (R/IR/IC), train_class (1/2),
        # km_from/km_to (intervale de distanta), price_ron.
        # UNIQUE pe (train_category, train_class, km_from, km_to) -> idempotent.
        conn.execute(text("""
            INSERT INTO tariff_brackets (train_category, train_class, km_from, km_to, price_ron)
            VALUES
                ('R',   2,    0,   50, 15.00),
                ('R',   2,   50,  100, 22.00),
                ('R',   2,  100,  200, 35.00),
                ('R',   2,  200,  500, 50.00),
                ('IR',  2,    0,   50, 25.00),
                ('IR',  2,   50,  100, 40.00),
                ('IR',  2,  100,  200, 65.00),
                ('IR',  2,  200,  500, 95.00),
                ('IC',  2,    0,   50, 35.00),
                ('IC',  2,   50,  100, 55.00),
                ('IC',  2,  100,  200, 85.00),
                ('IC',  2,  200,  500, 120.00)
            ON CONFLICT (train_category, train_class, km_from, km_to) DO NOTHING
        """))

    yield

# ===== 4. App + client =======================================================
@pytest.fixture(scope="session")
def app():
    """Import app o singura data dupa ce DB-ul de test e creat."""
    from app.main import app as fastapi_app
    return fastapi_app

@pytest.fixture()
def client(app):
    """TestClient cu cleanup intre teste (truncate tabele tranzitorii)."""
    from app.core.database import engine
    _truncate_transactional_tables(engine)
    return TestClient(app)

# ===== 5. Fixtures de utilizatori (foloseste seed-ul demo) ==================
@pytest.fixture
def passenger_token(client):
    """JWT pentru un pasager nou inregistrat."""
    return register_and_login(client, "passenger")

@pytest.fixture
def train_verifier_token(client):
    """JWT pentru conductorul demo (agent.train / demo2026)."""
    response = client.post(
        "/auth/login",
        json={"email": "agent.train@railwaydemo.com", "password": "demo2026"},
    )
    assert response.status_code == 200, f"Train verifier login failed: {response.text}"
    return response.json()["access_token"]

@pytest.fixture
def upb_agent_token(client):
    """JWT pentru agentul UPB (agent.upb / demo2026)."""
    response = client.post(
        "/auth/login",
        json={"email": "agent.upb@railwaydemo.com", "password": "demo2026"},
    )
    assert response.status_code == 200, f"UPB agent login failed: {response.text}"
    return response.json()["access_token"]

@pytest.fixture
def ase_agent_token(client):
    """JWT pentru agentul ASE (agent.ase / demo2026) — folosit la testele cross-university."""
    response = client.post(
        "/auth/login",
        json={"email": "agent.ase@railwaydemo.com", "password": "demo2026"},
    )
    assert response.status_code == 200, f"ASE agent login failed: {response.text}"
    return response.json()["access_token"]

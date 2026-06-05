
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

# Tabele care raman dupa cleanup (seed-ul demo)
KEEP_TABLES = {
    "universities", "users", "issuers", "stations", "trains", "routes",
    "railway_operators", "university_students",
    # cardul + credentialul demo seedate pentru user.demo:
    "digital_cards", "user_credentials",
}

def _psycopg_dsn(url: str) -> str:
    """Converteste URL SQLAlchemy in DSN psycopg pur (fara '+psycopg')."""
    return url.replace("postgresql+psycopg://", "postgresql://")

def _get_test_db_name() -> str:
    return TEST_DB_URL.rsplit("/", 1)[1]

def _admin_dsn() -> str:
    """DSN catre database 'postgres' (pentru DROP/CREATE DATABASE)."""
    return _psycopg_dsn(TEST_DB_URL.rsplit("/", 1)[0] + "/postgres")

def _recreate_test_database():
    """Recreeaza DB-ul de test si incarca schema + seed prin psycopg (multi-statement)."""
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

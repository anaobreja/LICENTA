import os
import sys
from pathlib import Path

# Must be set BEFORE app modules are imported so database.py picks up the right URL
_TEST_DB = Path(__file__).resolve().parents[2] / "test_railway.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB.as_posix()}")

BACKEND_PATH = Path(__file__).resolve().parent.parent
TESTS_PATH = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_PATH))
sys.path.insert(0, str(TESTS_PATH))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from helpers import create_test_image_bytes, make_unique_email, register_and_login


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def passenger_token(client):
    """JWT for a freshly registered passenger."""
    return register_and_login(client, "passenger")


@pytest.fixture
def train_verifier_token(client):
    """JWT for the seeded demo train verifier (agent.train / demo)."""
    response = client.post(
        "/auth/login",
        json={"email": "agent.train@railwaydemo.com", "password": "demo"},
    )
    assert response.status_code == 200, f"Train verifier login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture
def upb_agent_token(client):
    """JWT for the seeded demo UPB university agent (agent.upb / demo)."""
    response = client.post(
        "/auth/login",
        json={"email": "agent.upb@railwaydemo.com", "password": "demo"},
    )
    assert response.status_code == 200, f"UPB agent login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    """Remove the test DB file after the whole test session."""
    yield
    try:
        _TEST_DB.unlink(missing_ok=True)
    except Exception:
        pass

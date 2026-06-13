"""
Test de CONTRACT pentru fluxul gara de provenienta.

Verifica:
1. POST /documents/validation-request acceptă home_station_id (obligatoriu pt student_card)
2. GET /issuer/documents/pending returnează home_station_name + home_station_city
3. POST /issuer/documents/{id}/approve setează users.home_station_id
"""

import os
import pytest
from sqlalchemy import create_engine, text
from helpers import register_and_login


@pytest.fixture
def db_engine():
    """Engine direct pentru verificari DB. Foloseste DATABASE_URL setat de conftest."""
    url = os.environ["DATABASE_URL"]
    return create_engine(url)


def _get_first_station(client) -> dict:
    """Returneaza prima statie din DB (folosita ca home_station)."""
    # Folosim /stations/search cu query gol -> top stations
    resp = client.get("/stations/search?q=&limit=5")
    assert resp.status_code == 200
    stations = resp.json()
    assert len(stations) > 0, "Nu exista statii in DB pentru test"
    return stations[0]


def _submit_validation_with_home_station(
    client, passenger_token: str, station_id: int | None,
    university_name: str = "Universitatea Politehnica București (UPB)",
):
    """Helper: submit cerere validare cu home_station_id opțional."""
    files = {
        "legitimation_photo_front": ("front.jpg", b"fakefrontimage", "image/jpeg"),
        "legitimation_photo_verso": ("verso.jpg", b"fakeversoimage", "image/jpeg"),
        "profile_photo": ("profile.jpg", b"fakeprofileimage", "image/jpeg"),
    }
    data = {
        "legitimation_type": "student_card",
        "legitimation_number_masked": "ST****1234",
        "university_name": university_name,
        "year_of_study": "2",
        "ci_number": "XZ123456",
        "ci_name": "Test Student",
        "ci_date_of_birth": "2003-05-25",
        "ci_sex": "M",
        "ci_address": "Str. Test Nr. 1",
    }
    if station_id is not None:
        data["home_station_id"] = str(station_id)
    return client.post(
        "/documents/validation-request",
        headers={"Authorization": f"Bearer {passenger_token}"},
        data=data,
        files=files,
    )


class TestSubmitWithHomeStation:
    """Cumparatorul submit cerere cu home_station_id."""

    def test_student_card_without_home_station_fails(self, client, passenger_token):
        """student_card fara home_station_id => 400."""
        resp = _submit_validation_with_home_station(client, passenger_token, None)
        assert resp.status_code == 400, resp.text
        assert "gara" in resp.json()["detail"].lower()

    def test_student_card_with_invalid_home_station_fails(self, client, passenger_token):
        """home_station_id inexistent in stations => 400."""
        resp = _submit_validation_with_home_station(client, passenger_token, 999999)
        assert resp.status_code == 400, resp.text
        assert "exista" in resp.json()["detail"].lower() or "nu exist" in resp.json()["detail"].lower()

    def test_student_card_with_valid_home_station_succeeds(self, client, passenger_token):
        """home_station_id valid => 200 + cerere creata."""
        station = _get_first_station(client)
        resp = _submit_validation_with_home_station(client, passenger_token, station["station_id"])
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "documents" in data
        assert len(data["documents"]) > 0


class TestIssuerPendingContract:
    """Verifica structura raspunsului /issuer/documents/pending."""

    def test_pending_returns_home_station_fields_for_agent_university(
        self, client, passenger_token, upb_agent_token,
    ):
        """Agent UPB vede home_station_name + home_station_city pe cererile UPB."""
        station = _get_first_station(client)
        # User cere cu home_station_id setat
        submit_resp = _submit_validation_with_home_station(
            client, passenger_token, station["station_id"],
            university_name="Universitatea Politehnica București (UPB)",
        )
        assert submit_resp.status_code == 200

        # Agent UPB vede cererea
        resp = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        assert resp.status_code == 200, resp.text
        pending = resp.json()
        assert isinstance(pending, list)
        assert len(pending) > 0, "Agent UPB nu vede cererea proaspata"

        # Gaseste cererea noastra
        ours = next((d for d in pending if d.get("ci_number") == "XZ123456"), None)
        assert ours is not None, "Cererea proaspata nu apare in pending"

        # Cheile asteptate de frontend (UniversityAgentDashboard.jsx):
        expected_keys = {
            "home_station_id",
            "home_station_name",
            "home_station_city",
            "home_station_code",
        }
        missing = expected_keys - set(ours.keys())
        assert not missing, f"Cheile lipsesc din /issuer/documents/pending: {missing}"

        # Valorile efective
        assert ours["home_station_id"] == station["station_id"]
        assert ours["home_station_name"] == station["name"]


class TestApproveSetsHomeStation:
    """Verifica ca approve seteaza users.home_station_id."""

    def test_approve_sets_users_home_station_id(
        self, client, passenger_token, upb_agent_token, db_engine,
    ):
        """Dupa approve, users.home_station_id == source_documents.home_station_id."""
        station = _get_first_station(client)
        # Submit
        submit_resp = _submit_validation_with_home_station(
            client, passenger_token, station["station_id"],
            university_name="Universitatea Politehnica București (UPB)",
        )
        assert submit_resp.status_code == 200
        doc_id = submit_resp.json()["documents"][0]["id"]

        with db_engine.connect() as conn:
            user_id = conn.execute(
                text("SELECT user_id FROM source_documents WHERE id = :d"),
                {"d": doc_id},
            ).scalar()

        # Approve as UPB agent
        approve_resp = client.post(
            f"/issuer/documents/{doc_id}/approve",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
            json={"notes": "OK"},
        )
        assert approve_resp.status_code == 200, approve_resp.text

        # Verifica ca users.home_station_id e setat
        with db_engine.connect() as conn:
            home_station_id_db = conn.execute(
                text("SELECT home_station_id FROM users WHERE user_id = :u"),
                {"u": user_id},
            ).scalar()
        assert home_station_id_db == station["station_id"], (
            f"users.home_station_id={home_station_id_db}, "
            f"expected={station['station_id']}"
        )

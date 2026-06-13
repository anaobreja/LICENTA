"""
Test pentru sincronizarea automata a `date_of_birth` la approve.

Acopera toate formatele suportate:
  - YYYY-MM-DD (ISO)
  - DD.MM.YYYY (RO standard)
  - DD/MM/YYYY (variatia)
  - YYMMDD (MRZ brut)
  - Format invalid -> skip silent (nu blocheaza approve)
"""
from __future__ import annotations

import io
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from helpers import register_and_login, create_test_image_bytes


def _engine():
    from app.core.database import engine
    return engine


def _get_first_univ_name() -> str:
    """Returneaza numele primei universitati din DB (real, cu/fara diacritice)."""
    with _engine().connect() as conn:
        return conn.execute(
            text("SELECT name FROM universities ORDER BY university_id LIMIT 1")
        ).scalar()


def _create_agent_token_for(client, university_name: str | None = None) -> tuple[str, int]:
    """Creeaza un agent universitar pentru prima universitate din DB.
    `university_name` e ignorat - folosim mereu prima existenta in DB.
    Returneaza (token, user_id).
    """
    actual_univ_name = _get_first_univ_name()
    email = f"agt_{uuid.uuid4().hex[:8]}@t.com"
    password = "AgentPass123!"
    client.post("/auth/register", data={
        "email": email, "password": password,
        "first_name": "Agent", "last_name": "Test",
        "phone": "+40712345600",
        "university_name": actual_univ_name,
    }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})

    with _engine().begin() as conn:
        univ_id = conn.execute(
            text("SELECT university_id FROM universities WHERE name = :n LIMIT 1"),
            {"n": actual_univ_name},
        ).scalar()
        assert univ_id is not None, f"University {actual_univ_name!r} not found"
        conn.execute(
            text("UPDATE users SET role='university_agent', university_id=:uid WHERE email=:em"),
            {"uid": univ_id, "em": email},
        )
        uid = conn.execute(
            text("SELECT user_id FROM users WHERE email=:em"),
            {"em": email},
        ).scalar()

    login = client.post("/auth/login", json={"email": email, "password": password})
    return login.json()["access_token"], uid


def _submit_with_dob(client, passenger_token: str, dob_str: str,
                     university: str | None = None) -> int:
    """Submit cerere validare cu dob_str dat. Returneaza document_id."""
    if university is None:
        university = _get_first_univ_name()
    # Gaseste o statie (orice)
    st_r = client.get("/stations/search?q=&limit=1")
    station_id = st_r.json()[0]["station_id"]

    files = {
        "legitimation_photo_front": ("f.jpg", b"x", "image/jpeg"),
        "legitimation_photo_verso": ("v.jpg", b"x", "image/jpeg"),
        "profile_photo": ("p.jpg", b"x", "image/jpeg"),
    }
    data = {
        "legitimation_type": "student_card",
        "legitimation_number_masked": "ST****1234",
        "university_name": university,
        "year_of_study": "2",
        "ci_number": "AB123456",
        "ci_name": "Test Student",
        "ci_date_of_birth": dob_str,
        "ci_sex": "M",
        "ci_address": "Str. Test Nr. 1",
        "home_station_id": str(station_id),
    }
    r = client.post(
        "/documents/validation-request",
        headers={"Authorization": f"Bearer {passenger_token}"},
        data=data,
        files=files,
    )
    assert r.status_code == 200, r.text
    return r.json()["documents"][0]["id"]


def _get_user_dob(user_id: int) -> str | None:
    with _engine().connect() as conn:
        result = conn.execute(
            text("SELECT date_of_birth::text FROM users WHERE user_id = :u"),
            {"u": user_id},
        ).scalar()
    return result


class TestDobFormatSync:

    def test_iso_format(self, client):
        pas = register_and_login(client, "dob_iso")
        with _engine().connect() as conn:
            uid = conn.execute(
                text("SELECT user_id FROM users WHERE email=:e"),
                {"e": f"dob_iso@example.com"},
            ).scalar()
        # register_and_login face email diferit - aflu via /users/me
        me_r = client.get("/users/me", headers={"Authorization": f"Bearer {pas}"})
        uid = me_r.json()["user_id"]

        doc_id = _submit_with_dob(client, pas, "2003-05-25")
        agent, _ = _create_agent_token_for(client)

        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent}"},
                        json={"notes": "ok"})
        assert r.status_code == 200, r.text
        assert _get_user_dob(uid) == "2003-05-25"

    def test_ro_dot_format(self, client):
        pas = register_and_login(client, "dob_dot")
        me_r = client.get("/users/me", headers={"Authorization": f"Bearer {pas}"})
        uid = me_r.json()["user_id"]

        doc_id = _submit_with_dob(client, pas, "25.05.2003")
        agent, _ = _create_agent_token_for(client)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent}"}, json={"notes": "ok"})
        assert r.status_code == 200
        assert _get_user_dob(uid) == "2003-05-25"

    def test_slash_format(self, client):
        pas = register_and_login(client, "dob_slash")
        me_r = client.get("/users/me", headers={"Authorization": f"Bearer {pas}"})
        uid = me_r.json()["user_id"]

        doc_id = _submit_with_dob(client, pas, "25/05/2003")
        agent, _ = _create_agent_token_for(client)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent}"}, json={"notes": "ok"})
        assert r.status_code == 200
        assert _get_user_dob(uid) == "2003-05-25"

    def test_mrz_yymmdd_pivot_after_2000(self, client):
        """030525 -> 2003-05-25 (pivot YY <= 30 -> 2000+)."""
        pas = register_and_login(client, "dob_mrz_2000")
        me_r = client.get("/users/me", headers={"Authorization": f"Bearer {pas}"})
        uid = me_r.json()["user_id"]

        doc_id = _submit_with_dob(client, pas, "030525")
        agent, _ = _create_agent_token_for(client)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent}"}, json={"notes": "ok"})
        assert r.status_code == 200
        assert _get_user_dob(uid) == "2003-05-25"

    def test_mrz_yymmdd_pivot_before_2000(self, client):
        """910525 -> 1991-05-25 (pivot YY > 30 -> 1900+)."""
        pas = register_and_login(client, "dob_mrz_1900")
        me_r = client.get("/users/me", headers={"Authorization": f"Bearer {pas}"})
        uid = me_r.json()["user_id"]

        doc_id = _submit_with_dob(client, pas, "910525")
        agent, _ = _create_agent_token_for(client)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent}"}, json={"notes": "ok"})
        assert r.status_code == 200
        assert _get_user_dob(uid) == "1991-05-25"

    def test_invalid_format_silent_skip(self, client):
        """Format necunoscut nu blocheaza approve, doar nu sincronizeaza dob."""
        pas = register_and_login(client, "dob_bad")
        me_r = client.get("/users/me", headers={"Authorization": f"Bearer {pas}"})
        uid = me_r.json()["user_id"]

        # CI poate avea date_of_birth corupt - approve trebuie sa treaca,
        # date_of_birth ramane neset (sau ce a fost inainte).
        doc_id = _submit_with_dob(client, pas, "junk_string")
        agent, _ = _create_agent_token_for(client)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent}"}, json={"notes": "ok"})
        assert r.status_code == 200  # nu crapă
        # dob ar trebui sa ramana NULL (n-a fost setat niciodata)
        assert _get_user_dob(uid) is None

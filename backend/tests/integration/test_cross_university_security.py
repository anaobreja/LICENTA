"""
Test pentru securitatea cross-university.

Acopera:
  - Agent UPB nu poate aproba/respinge documente de la ASE.
  - Agent fara university_id setat e respins (privilege escalation guard).
  - Pasagerul nu poate apela endpoint-uri /issuer/*.
  - Conductor nu poate aproba documente.
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import text

from helpers import register_and_login, create_test_image_bytes


def _engine():
    from app.core.database import engine
    return engine


def _all_univs():
    with _engine().connect() as c:
        return c.execute(
            text("SELECT university_id, name FROM universities ORDER BY university_id")
        ).fetchall()


def _make_agent_for_univ(client, univ_id: int | None) -> str:
    """Creeaza un agent legat (sau nelegat - daca univ_id=None) de o universitate."""
    email = f"sa_{uuid.uuid4().hex[:8]}@t.com"
    password = "Pass1234!"
    # Folosim numele primei universitati - oricum suprascris in DB
    actual_univ_name = _all_univs()[0][1]
    client.post("/auth/register", data={
        "email": email, "password": password,
        "first_name": "Agent", "last_name": "Test",
        "phone": "+40712345600",
        "university_name": actual_univ_name,
    }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
    with _engine().begin() as conn:
        conn.execute(
            text("UPDATE users SET role='university_agent', university_id=:uid WHERE email=:em"),
            {"uid": univ_id, "em": email},
        )
    return client.post("/auth/login",
                       json={"email": email, "password": password}).json()["access_token"]


def _submit_with_univ(client, passenger_token: str, univ_name: str) -> int:
    """Submit cerere validare pentru o universitate. Returneaza document_id."""
    st_r = client.get("/stations/search?q=&limit=1")
    station_id = st_r.json()[0]["station_id"]
    r = client.post(
        "/documents/validation-request",
        headers={"Authorization": f"Bearer {passenger_token}"},
        data={
            "legitimation_type": "student_card",
            "legitimation_number_masked": "ST****0001",
            "university_name": univ_name,
            "year_of_study": "2",
            "ci_number": "AB123456",
            "ci_name": "Student Test",
            "ci_date_of_birth": "2003-01-01",
            "ci_sex": "M",
            "ci_address": "Str. Test, jud Test",
            "home_station_id": str(station_id),
        },
        files={
            "legitimation_photo_front": ("f.jpg", b"x", "image/jpeg"),
            "legitimation_photo_verso": ("v.jpg", b"x", "image/jpeg"),
            "profile_photo": ("p.jpg", b"x", "image/jpeg"),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["documents"][0]["id"]


class TestCrossUniversitySecurity:

    def test_agent_cannot_approve_other_university_doc(self, client):
        """Agent UPB nu poate aproba document depus pentru ASE."""
        univs = _all_univs()
        if len(univs) < 2:
            pytest.skip("Test requires >=2 universities in DB")
        upb_id, upb_name = univs[0]
        ase_id, ase_name = univs[1]

        # Pasagerul depune cerere pentru ASE
        pas = register_and_login(client, "cx_pas_ase")
        doc_id = _submit_with_univ(client, pas, ase_name)

        # Agent UPB incearca approve -> 403
        agent_upb = _make_agent_for_univ(client, upb_id)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent_upb}"},
                        json={"notes": "trying"})
        assert r.status_code == 403
        assert "alta universitate" in r.json()["detail"].lower()

    def test_agent_without_university_blocked(self, client):
        """Agent cu university_id=NULL e respins de approve (privilege escalation)."""
        univs = _all_univs()
        upb_id, upb_name = univs[0]

        pas = register_and_login(client, "cx_pas_orph")
        doc_id = _submit_with_univ(client, pas, upb_name)

        # Agent FĂRĂ university - test pentru Bug #18
        agent_no_univ = _make_agent_for_univ(client, None)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent_no_univ}"},
                        json={"notes": "trying"})
        assert r.status_code == 403
        assert "nu are universitate" in r.json()["detail"].lower()

    def test_agent_can_approve_own_university_doc(self, client):
        """Agent UPB poate aproba document depus pentru UPB."""
        univs = _all_univs()
        upb_id, upb_name = univs[0]

        pas = register_and_login(client, "cx_pas_upb")
        doc_id = _submit_with_univ(client, pas, upb_name)

        agent_upb = _make_agent_for_univ(client, upb_id)
        r = client.post(f"/issuer/documents/{doc_id}/approve",
                        headers={"Authorization": f"Bearer {agent_upb}"},
                        json={"notes": "OK"})
        assert r.status_code == 200, r.text

    def test_passenger_cannot_call_issuer_endpoints(self, client):
        """Pasagerul fara rol issuer e respins de /issuer/*."""
        pas = register_and_login(client, "cx_pas_block")
        h = {"Authorization": f"Bearer {pas}"}

        # /issuer/documents/pending -> 403
        r = client.get("/issuer/documents/pending", headers=h)
        assert r.status_code == 403

        # /issuer/documents/{id}/approve -> 403 (chiar daca doc-ul nu exista)
        r = client.post("/issuer/documents/1/approve",
                        headers=h, json={"notes": ""})
        assert r.status_code == 403

    def test_conductor_cannot_approve(self, client):
        """Conductorul nu poate aproba documente identitate."""
        email = f"cond_{uuid.uuid4().hex[:8]}@t.com"
        password = "Pass1234!"
        client.post("/auth/register", data={
            "email": email, "password": password,
            "first_name": "Conductor", "last_name": "Test",
            "phone": "+40712345699",
        }, files={"profile_photo": ("p.png", create_test_image_bytes(), "image/png")})
        with _engine().begin() as conn:
            conn.execute(
                text("UPDATE users SET role='conductor' WHERE email=:em"),
                {"em": email},
            )
        tok = client.post("/auth/login",
                          json={"email": email, "password": password}).json()["access_token"]
        r = client.post("/issuer/documents/1/approve",
                        headers={"Authorization": f"Bearer {tok}"},
                        json={"notes": ""})
        assert r.status_code == 403

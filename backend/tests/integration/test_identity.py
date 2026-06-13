"""
Test suite for Identity and Document endpoints.
Covers: document upload, QR card generation, card verification,
        university agent approval flow, notifications, digital card.
"""

import time
import pytest
from helpers import create_test_image_bytes, make_unique_email, register_and_login


class TestDocumentManagement:

    def test_new_user_has_no_documents(self, client, passenger_token):
        response = client.get(
            "/documents/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_submit_validation_request_success(self, client, passenger_token):
        response = client.post(
            "/documents/validation-request",
            headers={"Authorization": f"Bearer {passenger_token}"},
            data={
                "legitimation_type": "student_card",
                "legitimation_number_masked": "ST123456",
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
                "year_of_study": "2",
                "ci_number": "XZ123456",
                "ci_name": "Test User",
                "ci_date_of_birth": "2000-01-01",
                "ci_sex": "M",
                "ci_address": "Str. Test, jud. Test",
                "home_station_id": "1",
            },
            files={
                "legitimation_photo_front": ("front.png", create_test_image_bytes(), "image/png"),
                "legitimation_photo_verso": ("verso.png", create_test_image_bytes(), "image/png"),
            },
        )
        assert response.status_code in (200, 201), response.text

    def test_submit_validation_request_wrong_type_fails(self, client, passenger_token):
        response = client.post(
            "/documents/validation-request",
            headers={"Authorization": f"Bearer {passenger_token}"},
            data={
                "legitimation_type": "student",   # invalid — should be "student_card"
                "legitimation_number_masked": "ST000000",
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
                "year_of_study": "1",
            },
            files={
                "legitimation_photo_front": ("front.png", create_test_image_bytes(), "image/png"),
                "legitimation_photo_verso": ("verso.png", create_test_image_bytes(), "image/png"),
            },
        )
        assert response.status_code in (400, 422), "Invalid legitimation_type must be rejected"

    def test_submit_validation_request_missing_verso_fails(self, client, passenger_token):
        response = client.post(
            "/documents/validation-request",
            headers={"Authorization": f"Bearer {passenger_token}"},
            data={
                "legitimation_type": "student_card",
                "legitimation_number_masked": "ST999999",
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
                "year_of_study": "1",
            },
            files={
                "legitimation_photo_front": ("front.png", create_test_image_bytes(), "image/png"),
                # verso intentionally missing
            },
        )
        assert response.status_code in (400, 422), "Missing verso should be rejected"

    def test_documents_endpoint_requires_auth(self, client):
        response = client.get("/documents/me")
        assert response.status_code == 401


class TestCardGeneration:

    def test_new_user_cannot_generate_qr_token(self, client, passenger_token):
        """A passenger without an approved card gets 404, not a crash."""
        response = client.post(
            "/card/present",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"ttl_seconds": 120},
        )
        assert response.status_code == 404, (
            f"Expected 404 (no active card), got {response.status_code}: {response.text}"
        )

    def test_card_endpoint_requires_auth(self, client):
        response = client.post("/card/present", json={"ttl_seconds": 120})
        assert response.status_code == 401


class TestCardVerification:

    def test_verify_invalid_qr_token_returns_404(self, client, train_verifier_token):
        """Valid train-verifier JWT + non-existent QR token → 404."""
        response = client.post(
            "/train/verify",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": "card_this_token_does_not_exist"},
        )
        assert response.status_code == 404, response.text

    def test_verify_requires_train_verifier_role(self, client, passenger_token):
        """A regular passenger cannot call the train-verify endpoint."""
        response = client.post(
            "/train/verify",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"token": "card_fake_token_passenger"},
        )
        assert response.status_code in (403, 401), (
            "Passenger should not be allowed to verify cards"
        )

    def test_verify_requires_auth(self, client):
        response = client.post("/train/verify", json={"token": "card_fake_token_noauth"})
        assert response.status_code == 401


class TestCredentials:

    def test_new_user_has_no_credentials(self, client, passenger_token):
        response = client.get(
            "/credentials/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_credentials_endpoint_requires_auth(self, client):
        response = client.get("/credentials/me")
        assert response.status_code == 401


class TestNotifications:

    def test_notifications_empty_for_new_user(self, client, passenger_token):
        response = client.get(
            "/notifications/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_notifications_requires_auth(self, client):
        response = client.get("/notifications/me")
        assert response.status_code == 401


class TestDigitalCard:

    def test_card_not_found_before_approval(self, client, passenger_token):
        response = client.get(
            "/card/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code == 404

    def test_card_requires_auth(self, client):
        response = client.get("/card/me")
        assert response.status_code == 401


class TestUniversityAgentWorkflow:
    """Full flow: submit → agent views pending → approve → credentials issued → QR works."""

    def _submit_docs(self, client, token, doc_number):
        return client.post(
            "/documents/validation-request",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "legitimation_type": "student_card",
                "legitimation_number_masked": doc_number,
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
                "year_of_study": "2",
                "ci_number": "XZ999888",
                "ci_name": "Integration Test",
                "ci_date_of_birth": "2001-03-10",
                "ci_sex": "F",
                "ci_address": "Str. Test, jud. Test",
                "home_station_id": "1",
            },
            files={
                "legitimation_photo_front": ("front.png", create_test_image_bytes(), "image/png"),
                "legitimation_photo_verso": ("verso.png", create_test_image_bytes(), "image/png"),
            },
        )

    def test_agent_sees_pending_documents(self, client, upb_agent_token, passenger_token):
        doc_number = f"ST{int(time.time() * 1000) % 100000}"
        submit = self._submit_docs(client, passenger_token, doc_number)
        assert submit.status_code in (200, 201), submit.text

        response = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        assert response.status_code == 200, response.text
        docs = response.json()
        assert isinstance(docs, list)
        numbers = [d.get("document_number_masked") for d in docs]
        assert doc_number in numbers

    def test_agent_cannot_access_as_passenger(self, client, passenger_token):
        response = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code in (401, 403)

    def test_approve_document_issues_credentials(self, client, upb_agent_token):
        # Register a dedicated passenger for this test
        passenger_token = register_and_login(client, "approval_flow")
        doc_number = f"ST{int(time.time() * 1000) % 100000}"

        submit = self._submit_docs(client, passenger_token, doc_number)
        assert submit.status_code in (200, 201), submit.text

        # Agent gets pending list and finds our document
        pending = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        assert pending.status_code == 200
        doc = next((d for d in pending.json() if d.get("document_number_masked") == doc_number), None)
        assert doc is not None, f"Document {doc_number} not found in pending list"

        # Approve it
        approve = client.post(
            f"/issuer/documents/{doc['id']}/approve",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
            json={"notes": "Approved in test"},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json().get("status") == "approved"

        # Passenger now has credentials
        creds = client.get(
            "/credentials/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert creds.status_code == 200
        assert len(creds.json()) > 0, "Credentials should be issued after approval"

        # Passenger has a digital card
        card = client.get(
            "/card/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert card.status_code == 200, "Digital card should exist after approval"

    def test_reject_document_updates_status(self, client, upb_agent_token):
        passenger_token = register_and_login(client, "reject_flow")
        doc_number = f"RJ{int(time.time() * 1000) % 100000}"

        submit = self._submit_docs(client, passenger_token, doc_number)
        assert submit.status_code in (200, 201), submit.text

        pending = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        doc = next((d for d in pending.json() if d.get("document_number_masked") == doc_number), None)
        assert doc is not None

        reject = client.post(
            f"/issuer/documents/{doc['id']}/reject",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
            json={"notes": "Photo unclear"},
        )
        assert reject.status_code == 200, reject.text
        assert reject.json().get("status") == "rejected"

    def test_approve_nonexistent_document_fails(self, client, upb_agent_token):
        response = client.post(
            "/issuer/documents/999999/approve",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
            json={"notes": "test"},
        )
        assert response.status_code == 404

    def test_approved_user_can_generate_qr(self, client, upb_agent_token, train_verifier_token):
        passenger_token = register_and_login(client, "qr_flow")
        doc_number = f"QR{int(time.time() * 1000) % 100000}"

        self._submit_docs(client, passenger_token, doc_number)

        pending = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        doc = next((d for d in pending.json() if d.get("document_number_masked") == doc_number), None)
        assert doc is not None

        client.post(
            f"/issuer/documents/{doc['id']}/approve",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
            json={"notes": "ok"},
        )

        # Generate QR token
        qr = client.post(
            "/card/present",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"ttl_seconds": 120},
        )
        assert qr.status_code in (200, 201), qr.text
        qr_token = qr.json().get("token_value")
        assert qr_token, "QR token must be returned"

        # Train verifier validates the QR
        verify = client.post(
            "/train/verify",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )
        assert verify.status_code == 200, verify.text
        assert verify.json().get("result") == "valid"


class TestQRReplaySecurity:
    """SECURITY: Verify QR tokens are single-use (no replay)"""

    def test_qr_token_single_use_prevention(self, client, upb_agent_token, train_verifier_token):
        """Generate QR token, validate twice - second should fail (replay prevention)"""
        passenger_token = register_and_login(client, "replay_test")
        doc_number = f"REP{int(time.time() * 1000) % 100000}"

        # Submit documents
        submit = client.post(
            "/documents/validation-request",
            headers={"Authorization": f"Bearer {passenger_token}"},
            data={
                "legitimation_type": "student_card",
                "legitimation_number_masked": doc_number,
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
                "year_of_study": "2",
                "ci_number": "REP123456",
                "ci_name": "Replay Test",
                "ci_date_of_birth": "2002-05-15",
                "ci_sex": "M",
                "ci_address": "Str. Test, jud. Test",
                "home_station_id": "1",
            },
            files={
                "legitimation_photo_front": ("front.png", create_test_image_bytes(), "image/png"),
                "legitimation_photo_verso": ("verso.png", create_test_image_bytes(), "image/png"),
            },
        )
        assert submit.status_code in (200, 201)

        # Agent approves
        pending = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        doc = next((d for d in pending.json() if d.get("document_number_masked") == doc_number), None)
        assert doc is not None

        approve = client.post(
            f"/issuer/documents/{doc['id']}/approve",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
            json={"notes": "ok"},
        )
        assert approve.status_code == 200

        # Generate QR token
        qr_resp = client.post(
            "/card/present",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"ttl_seconds": 120},
        )
        assert qr_resp.status_code in (200, 201)
        qr_token = qr_resp.json().get("token_value")
        assert qr_token

        # First validation: SHOULD SUCCEED
        verify1 = client.post(
            "/train/verify",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )
        assert verify1.status_code == 200, f"First validation should succeed, got {verify1.status_code}: {verify1.text}"
        assert verify1.json().get("result") == "valid"

        # Second validation with SAME token: MUST FAIL (replay detection)
        verify2 = client.post(
            "/train/verify",
            headers={"Authorization": f"Bearer {train_verifier_token}"},
            json={"token": qr_token},
        )
        assert verify2.status_code == 200, "Should return 200 but with invalid result"
        result = verify2.json().get("result")
        assert result in ("invalid", "already_used"), (
            f"Second use of same token must be rejected; got result='{result}'. "
            "This is a CRITICAL security vulnerability - token replay detected!"
        )


class TestCrossUniversityAuthorizationSecurity:
    """SECURITY: Verify agents cannot approve documents from other universities"""

    def test_agent_cannot_approve_different_university_student(
        self, client, upb_agent_token, ase_agent_token
    ):
        """
        SECURITY: agentul ASE NU trebuie sa poata aproba un document de la UPB.
        Doua paliere de aparare:
          (1) /issuer/documents/pending — filtrare per universitate
              => agentul ASE NU vede documentul UPB in lista.
          (2) /issuer/documents/{id}/approve — verificare explicita cross-uni
              => chiar daca cunoaste id-ul, approve esueaza cu 403.
        """
        # Pasul 1: creem un student UPB si depunem o cerere
        upb_student_token = register_and_login(client, "upb_student_cross")
        upb_doc_number = f"UPB{int(time.time() * 1000) % 100000}"

        submit = client.post(
            "/documents/validation-request",
            headers={"Authorization": f"Bearer {upb_student_token}"},
            data={
                "legitimation_type": "student_card",
                "legitimation_number_masked": upb_doc_number,
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
                "year_of_study": "1",
                "ci_number": "XUP123456",
                "ci_name": "UPB Test",
                "ci_date_of_birth": "2003-01-01",
                "ci_sex": "F",
                "ci_address": "Str. Test, jud. Test",
                "home_station_id": "1",
            },
            files={
                "legitimation_photo_front": ("f.png", create_test_image_bytes(), "image/png"),
                "legitimation_photo_verso": ("v.png", create_test_image_bytes(), "image/png"),
            },
        )
        assert submit.status_code in (200, 201), submit.text

        # Pasul 2: agentul UPB VEDE documentul; agentul ASE NU.
        pending_upb = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {upb_agent_token}"},
        )
        assert pending_upb.status_code == 200
        upb_docs = pending_upb.json()
        upb_doc = next(
            (d for d in upb_docs if d.get("document_number_masked") == upb_doc_number),
            None,
        )
        assert upb_doc is not None, "Documentul UPB ar trebui vizibil pentru agentul UPB"
        upb_doc_id = upb_doc["id"]

        pending_ase = client.get(
            "/issuer/documents/pending",
            headers={"Authorization": f"Bearer {ase_agent_token}"},
        )
        assert pending_ase.status_code == 200
        ase_docs = pending_ase.json()
        assert not any(
            d.get("document_number_masked") == upb_doc_number for d in ase_docs
        ), "Documentul UPB nu trebuie sa apara pentru agentul ASE"

        # Pasul 3: agentul ASE incearca direct sa aprobe documentul UPB => 403
        approve_attempt = client.post(
            f"/issuer/documents/{upb_doc_id}/approve",
            headers={"Authorization": f"Bearer {ase_agent_token}"},
            json={"notes": "attempted unauthorized approval"},
        )
        assert approve_attempt.status_code == 403, (
            f"Cross-uni approval ar trebui blocat (403), primit {approve_attempt.status_code}: "
            f"{approve_attempt.text}"
        )


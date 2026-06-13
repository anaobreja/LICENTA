"""
End-to-end demo test - full flow verification
Simulates real user journey: register → submit docs → approval → QR generation → validation
"""

import time
import pytest
from helpers import create_test_image_bytes, register_and_login


def test_complete_demo_flow(client, upb_agent_token, train_verifier_token):
    """
    Complete E2E flow:
    1. User registers
    2. User submits identity documents
    3. University agent reviews and approves
    4. User generates digital card QR
    5. Train conductor validates the QR (single-use)
    6. Attempt to reuse QR fails (security)
    """
    # 1. REGISTER & LOGIN
    print("\n✓ Step 1: User registration & login")
    user_email = f"demo_user_{int(time.time() * 1000)}@test.com"
    register_response = client.post(
        "/auth/register",
        data={
            "email": user_email,
            "password": "DemoPass123!",
            "first_name": "Demo",
            "last_name": "User",
            "phone": "+40712345678",
            "university_name": "Universitatea Politehnica Bucuresti (UPB)",
        },
        files={
            "profile_photo": ("demo_photo.png", create_test_image_bytes(), "image/png")
        }
    )
    assert register_response.status_code in (200, 201), register_response.text
    print(f"   ✓ Registered: {user_email}")

    login_response = client.post(
        "/auth/login",
        json={"email": user_email, "password": "DemoPass123!"}
    )
    assert login_response.status_code == 200, login_response.text
    user_token = login_response.json()["access_token"]
    print(f"   ✓ Logged in, token: {user_token[:20]}...")

    # 2. SUBMIT DOCUMENTS
    print("\n✓ Step 2: Submit identity validation request")
    doc_response = client.post(
        "/documents/validation-request",
        headers={"Authorization": f"Bearer {user_token}"},
        data={
            "legitimation_type": "student_card",
            "legitimation_number_masked": f"ST{int(time.time() * 1000) % 100000}",
            "university_name": "Universitatea Politehnica Bucuresti (UPB)",
            "year_of_study": "2",
            "ci_number": "DEMO123456",
            "ci_name": "Demo User",
            "ci_date_of_birth": "2001-01-01",
            "ci_sex": "M",
            "ci_address": "Str. Test, jud. Test",
            "home_station_id": "1",
        },
        files={
            "legitimation_photo_front": ("front.png", create_test_image_bytes(), "image/png"),
            "legitimation_photo_verso": ("verso.png", create_test_image_bytes(), "image/png"),
        }
    )
    assert doc_response.status_code in (200, 201), doc_response.text
    print("   ✓ Documents submitted")

    # 3. UNIVERSITY AGENT REVIEWS & APPROVES
    print("\n✓ Step 3: University agent approval")
    pending_response = client.get(
        "/issuer/documents/pending",
        headers={"Authorization": f"Bearer {upb_agent_token}"}
    )
    assert pending_response.status_code == 200, pending_response.text
    docs = pending_response.json()
    print(f"   ✓ Agent sees {len(docs)} pending document(s)")

    # Find our document
    doc_id = None
    for doc in docs:
        # Our document was just submitted
        if doc.get("email") == user_email:
            doc_id = doc["id"]
            break

    assert doc_id is not None, "Document not found in pending list"
    print(f"   ✓ Found document ID: {doc_id}")

    approve_response = client.post(
        f"/issuer/documents/{doc_id}/approve",
        headers={"Authorization": f"Bearer {upb_agent_token}"},
        json={"notes": "Demo approval"}
    )
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json().get("status") == "approved"
    print("   ✓ Document approved!")

    # 4. USER GENERATES DIGITAL CARD QR
    print("\n✓ Step 4: Generate digital card QR token")
    qr_response = client.post(
        "/card/present",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"ttl_seconds": 120}
    )
    assert qr_response.status_code in (200, 201), qr_response.text
    qr_data = qr_response.json()
    qr_token = qr_data.get("token_value")
    assert qr_token, "No QR token in response"
    print(f"   ✓ QR generated: {qr_token[:30]}...")

    # 5. TRAIN VERIFIER VALIDATES QR (FIRST USE)
    print("\n✓ Step 5: Train conductor validates QR (1st use)")
    verify1_response = client.post(
        "/train/verify",
        headers={"Authorization": f"Bearer {train_verifier_token}"},
        json={"token": qr_token}
    )
    assert verify1_response.status_code == 200, verify1_response.text
    verify1_data = verify1_response.json()
    assert verify1_data.get("result") == "valid", f"First validation should succeed, got: {verify1_data}"
    print(f"   ✓ First validation: VALID")
    print(f"      Passenger: {verify1_data.get('holder', {}).get('first_name')} {verify1_data.get('holder', {}).get('last_name')}")

    # 6. REPLAY ATTACK TEST (SECOND USE SHOULD FAIL)
    print("\n✓ Step 6: Replay attack test - attempt 2nd use of same token")
    verify2_response = client.post(
        "/train/verify",
        headers={"Authorization": f"Bearer {train_verifier_token}"},
        json={"token": qr_token}
    )
    assert verify2_response.status_code == 200, verify2_response.text
    verify2_data = verify2_response.json()
    result = verify2_data.get("result")
    assert result in ("invalid", "already_used"), (
        f"Second validation should be REJECTED (single-use enforcement). "
        f"Got result='{result}' - SECURITY FAILURE!"
    )
    print(f"   ✓ Second validation: REJECTED ({result}) - REPLAY PREVENTED!")

    print("\n" + "="*70)
    print("✓ COMPLETE E2E FLOW SUCCESSFUL")
    print("="*70)
    print(f"Demo User: {user_email}")
    print(f"University: Universitatea Politehnica Bucuresti (UPB)")
    print(f"Status: Verified, Approved, Card Generated, Single-Use Enforced")
    print("="*70)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

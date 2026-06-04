"""
Test suite for User profile endpoints.
Covers: profile update, password change, profile photo, export, account deletion.
"""

import pytest
from helpers import create_test_image_bytes, make_unique_email


class TestProfileUpdate:

    def test_update_profile_fields(self, client, passenger_token):
        response = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"first_name": "Updated", "last_name": "Name", "phone": "+40799000000"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"

    def test_update_single_field(self, client, passenger_token):
        response = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"phone": "+40711222333"},
        )
        assert response.status_code == 200, response.text

    def test_update_profile_no_fields_fails(self, client, passenger_token):
        response = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={},
        )
        assert response.status_code == 400

    def test_update_profile_requires_auth(self, client):
        # FastAPI validates the body before auth, so 422 is also acceptable here
        response = client.put("/users/me", json={"first_name": "X"})
        assert response.status_code in (401, 422)

    def test_update_date_of_birth(self, client, passenger_token):
        response = client.put(
            "/users/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"date_of_birth": "2000-05-15"},
        )
        assert response.status_code == 200
        assert response.json()["date_of_birth"] == "2000-05-15"


class TestPasswordChange:

    def test_change_password_success(self, client):
        email = make_unique_email("pwdchange")
        client.post(
            "/auth/register",
            data={
                "email": email,
                "password": "OldPass123!",
                "first_name": "Pwd",
                "last_name": "Test",
                "phone": "+40721000001",
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
            },
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        login = client.post("/auth/login", json={"email": email, "password": "OldPass123!"})
        token = login.json()["access_token"]

        response = client.put(
            "/users/me/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
        )
        assert response.status_code == 200
        assert "updated" in response.json().get("message", "").lower()

    def test_change_password_wrong_current_fails(self, client, passenger_token):
        response = client.put(
            "/users/me/password",
            headers={"Authorization": f"Bearer {passenger_token}"},
            json={"current_password": "WrongOldPass!", "new_password": "NewPass456!"},
        )
        assert response.status_code == 401

    def test_change_password_requires_auth(self, client):
        response = client.put(
            "/users/me/password",
            json={"current_password": "Old", "new_password": "New123456"},
        )
        assert response.status_code in (401, 422)


class TestProfilePhoto:

    def test_update_profile_photo_success(self, client, passenger_token):
        response = client.put(
            "/users/me/profile-photo",
            headers={"Authorization": f"Bearer {passenger_token}"},
            files={"profile_photo": ("new_photo.png", create_test_image_bytes(), "image/png")},
        )
        assert response.status_code == 200, response.text
        assert "actualizat" in response.json().get("message", "").lower()

    def test_update_profile_photo_requires_auth(self, client):
        response = client.put(
            "/users/me/profile-photo",
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        assert response.status_code == 401

    def test_get_own_profile_photo(self, client, passenger_token):
        profile = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        user_id = profile.json()["user_id"]

        response = client.get(
            f"/users/{user_id}/profile-photo",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/")


class TestExportAndDelete:

    def test_export_data_returns_all_sections(self, client, passenger_token):
        response = client.get(
            "/users/me/export",
            headers={"Authorization": f"Bearer {passenger_token}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "user" in data
        assert "source_documents" in data
        assert "user_credentials" in data

    def test_export_requires_auth(self, client):
        response = client.get("/users/me/export")
        assert response.status_code == 401

    def test_delete_account_deactivates_user(self, client):
        email = make_unique_email("delete_me")
        client.post(
            "/auth/register",
            data={
                "email": email,
                "password": "DeleteMe123!",
                "first_name": "Del",
                "last_name": "User",
                "phone": "+40721000002",
                "university_name": "Universitatea Politehnica Bucuresti (UPB)",
            },
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        login = client.post("/auth/login", json={"email": email, "password": "DeleteMe123!"})
        token = login.json()["access_token"]

        delete_resp = client.delete(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_resp.status_code == 200

        # After deletion, login should fail
        login2 = client.post("/auth/login", json={"email": email, "password": "DeleteMe123!"})
        assert login2.status_code in (401, 403, 404)

    def test_delete_requires_auth(self, client):
        response = client.delete("/users/me")
        assert response.status_code == 401

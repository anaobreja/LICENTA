"""
Test suite for Authentication endpoints.
Covers: registration, login, token validation.
"""

import pytest
from helpers import create_test_image_bytes, make_unique_email


class TestAuthRegister:

    def test_register_new_user_success(self, client):
        email = make_unique_email("reg_success")
        response = client.post(
            "/auth/register",
            data={
                "email": email,
                "password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe",
                "phone": "+40721234567",
                "university_name": "Universitatea Politehnica București (UPB)",
            },
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        assert response.status_code in (200, 201), response.text
        data = response.json()
        assert "user_id" in data or "message" in data

    def test_register_duplicate_email_fails(self, client):
        email = make_unique_email("reg_dup")
        payload = dict(
            email=email,
            password="Pass123!",
            first_name="User",
            last_name="One",
            phone="+40721111111",
            university_name="Universitatea Politehnica București (UPB)",
        )

        r1 = client.post(
            "/auth/register",
            data=payload,
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        assert r1.status_code in (200, 201)

        r2 = client.post(
            "/auth/register",
            data={**payload, "first_name": "User", "last_name": "Two", "phone": "+40722222222"},
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        assert r2.status_code in (400, 409, 422), "Duplicate email should be rejected"

    def test_register_missing_profile_photo_fails(self, client):
        response = client.post(
            "/auth/register",
            data={
                "email": make_unique_email("reg_nophoto"),
                "password": "Pass123!",
                "first_name": "No",
                "last_name": "Photo",
                "phone": "+40723333333",
                "university_name": "Universitatea Politehnica București (UPB)",
            },
        )
        assert response.status_code == 422, "Missing profile_photo should return 422"

    def test_register_missing_phone_fails(self, client):
        response = client.post(
            "/auth/register",
            data={
                "email": make_unique_email("reg_nophone"),
                "password": "Pass123!",
                "first_name": "No",
                "last_name": "Phone",
                "university_name": "Universitatea Politehnica București (UPB)",
            },
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )
        assert response.status_code in (400, 422), "Missing phone should be rejected"


class TestAuthLogin:

    def test_login_success_returns_token(self, client):
        email = make_unique_email("login_ok")
        client.post(
            "/auth/register",
            data={
                "email": email,
                "password": "ValidPass123!",
                "first_name": "Login",
                "last_name": "Test",
                "phone": "+40724444444",
                "university_name": "Universitatea Politehnica București (UPB)",
            },
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )

        response = client.post("/auth/login", json={"email": email, "password": "ValidPass123!"})

        assert response.status_code == 200, response.text
        data = response.json()
        assert "access_token" in data
        assert data.get("token_type") == "bearer"

    def test_login_wrong_password_fails(self, client):
        email = make_unique_email("login_badpwd")
        client.post(
            "/auth/register",
            data={
                "email": email,
                "password": "CorrectPass123!",
                "first_name": "Test",
                "last_name": "User",
                "phone": "+40725555555",
                "university_name": "Universitatea Politehnica București (UPB)",
            },
            files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
        )

        response = client.post("/auth/login", json={"email": email, "password": "WrongPass!"})
        assert response.status_code in (400, 401)

    def test_login_nonexistent_user_fails(self, client):
        response = client.post(
            "/auth/login",
            json={"email": make_unique_email("nobody"), "password": "AnyPass123!"},
        )
        assert response.status_code in (401, 404)


class TestTokenValidation:

    def test_valid_token_returns_user_profile(self, client, passenger_token):
        response = client.get("/users/me", headers={"Authorization": f"Bearer {passenger_token}"})
        assert response.status_code == 200, response.text
        assert "email" in response.json()

    def test_no_token_rejected(self, client):
        response = client.get("/users/me")
        assert response.status_code == 401

    def test_malformed_token_rejected(self, client):
        response = client.get("/users/me", headers={"Authorization": "Bearer not.a.real.token"})
        assert response.status_code == 401

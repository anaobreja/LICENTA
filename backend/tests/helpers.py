import time
from io import BytesIO


def create_test_image_bytes() -> BytesIO:
    """Minimal valid 1×1 red-pixel PNG."""
    png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
        b'\x00\x01\x01\x00\x05(\xe8\xf9W\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return BytesIO(png)


def make_unique_email(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}@test.com"


def register_and_login(client, prefix: str) -> str:
    """Register a new passenger and return its JWT access token."""
    email = make_unique_email(prefix)
    reg = client.post(
        "/auth/register",
        data={
            "email": email,
            "password": "ValidPass123!",
            "first_name": "Test",
            "last_name": "User",
            "phone": "+40721000000",
            "university_name": "Universitatea Politehnica București (UPB)",
        },
        files={"profile_photo": ("photo.png", create_test_image_bytes(), "image/png")},
    )
    assert reg.status_code in (200, 201), f"Register failed: {reg.text}"

    login = client.post(
        "/auth/login",
        json={"email": email, "password": "ValidPass123!"},
    )
    assert login.status_code == 200, f"Login failed: {login.text}"
    return login.json()["access_token"]

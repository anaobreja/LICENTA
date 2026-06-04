"""
Load tests pentru Railway Identity Platform.

Rulare rapidă (CLI):
    locust -f tests/locustfile.py --host http://127.0.0.1:8000 \
           --users 50 --spawn-rate 5 --run-time 60s --headless

Rulare cu UI (browser la http://localhost:8089):
    locust -f tests/locustfile.py --host http://127.0.0.1:8000

Scenarii simulate:
  PassengerUser   — login → profil → documente → credențiale → QR     (cel mai frecvent)
  TrainVerifier   — login → verificare QR cu token demo                (verificare rapidă)
  UniversityAgent — login → lista cereri pending → statistici          (agent universitar)
  ReadOnlyBrowse  — login → profil → notificări                       (utilizator pasiv)
"""

import random
import string
import time

from locust import HttpUser, TaskSet, between, task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEMO_TRAIN_TOKEN = None  # cache token QR demo generat o singură dată


def _random_suffix() -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# Imagine PNG minimală 1×1 pixel (nu declanșează OCR, doar testează upload)
_TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x01\x01\x00\x05(\xe8\xf9W\x00\x00\x00\x00IEND\xaeB`\x82'
)


# ---------------------------------------------------------------------------
# Task sets
# ---------------------------------------------------------------------------

class PassengerTasks(TaskSet):
    """Simulează un pasager logat care navighează platforma."""

    token: str = ""

    def on_start(self):
        """Înregistrare + login la pornirea fiecărui utilizator virtual."""
        email = f"load_{_random_suffix()}@test.com"
        self.client.post(
            "/auth/register",
            data={
                "email": email,
                "password": "LoadTest123!",
                "first_name": "Load",
                "last_name": "User",
                "phone": "+40721000000",
                "university_name": "Universitatea Politehnica București (UPB)",
            },
            files={"profile_photo": ("photo.png", _TINY_PNG, "image/png")},
            name="/auth/register",
        )
        r = self.client.post(
            "/auth/login",
            json={"email": email, "password": "LoadTest123!"},
            name="/auth/login",
        )
        if r.status_code == 200:
            self.token = r.json().get("access_token", "")

    @task(5)
    def get_profile(self):
        self.client.get("/users/me", headers=_auth_header(self.token), name="/users/me")

    @task(4)
    def get_documents(self):
        self.client.get("/documents/me", headers=_auth_header(self.token), name="/documents/me")

    @task(3)
    def get_credentials(self):
        self.client.get("/credentials/me", headers=_auth_header(self.token), name="/credentials/me")

    @task(3)
    def get_notifications(self):
        self.client.get("/notifications/me", headers=_auth_header(self.token), name="/notifications/me")

    @task(2)
    def submit_document(self):
        """Depune o cerere de validare — operație mai costisitoare."""
        self.client.post(
            "/documents/validation-request",
            headers=_auth_header(self.token),
            data={
                "legitimation_type": "student_card",
                "legitimation_number_masked": f"ST{_random_suffix()[:6].upper()}",
                "university_name": "Universitatea Politehnica București (UPB)",
                "year_of_study": "2",
                "ci_number": "XZ123456",
                "ci_name": "Load User",
                "ci_date_of_birth": "2001-01-01",
                "ci_sex": "M",
            },
            files={
                "legitimation_photo_front": ("f.png", _TINY_PNG, "image/png"),
                "legitimation_photo_verso": ("v.png", _TINY_PNG, "image/png"),
            },
            name="/documents/validation-request",
        )

    @task(1)
    def try_generate_qr(self):
        """Încearcă să genereze QR — eșuează cu 404 dacă nu are card activ."""
        self.client.post(
            "/card/present",
            headers=_auth_header(self.token),
            json={"ttl_seconds": 120},
            name="/card/present",
        )

    @task(1)
    def export_data(self):
        self.client.get("/users/me/export", headers=_auth_header(self.token), name="/users/me/export")


class TrainVerifierTasks(TaskSet):
    """Simulează un agent de tren care scanează carduri."""

    token: str = ""

    def on_start(self):
        r = self.client.post(
            "/auth/login",
            json={"email": "agent.train@railwaydemo.com", "password": "demo"},
            name="/auth/login [train]",
        )
        if r.status_code == 200:
            self.token = r.json().get("access_token", "")

    @task(3)
    def verify_invalid_token(self):
        """Verificare cu token inexistent — testează viteza de răspuns la reject."""
        self.client.post(
            "/train/verify",
            headers=_auth_header(self.token),
            json={"token": f"card_invalid_{_random_suffix()}"},
            name="/train/verify [invalid]",
        )

    @task(1)
    def check_history(self):
        self.client.get(
            "/train/verifications/history",
            headers=_auth_header(self.token),
            name="/train/verifications/history",
        )


class AgentTasks(TaskSet):
    """Simulează un agent universitar care revizuiește cereri."""

    token: str = ""

    def on_start(self):
        r = self.client.post(
            "/auth/login",
            json={"email": "agent.upb@railwaydemo.com", "password": "demo"},
            name="/auth/login [agent]",
        )
        if r.status_code == 200:
            self.token = r.json().get("access_token", "")

    @task(4)
    def list_pending(self):
        self.client.get(
            "/issuer/documents/pending",
            headers=_auth_header(self.token),
            name="/issuer/documents/pending",
        )

    @task(2)
    def get_stats(self):
        self.client.get(
            "/university/stats",
            headers=_auth_header(self.token),
            name="/university/stats",
        )

    @task(1)
    def list_credentials(self):
        self.client.get(
            "/issuer/credentials",
            headers=_auth_header(self.token),
            name="/issuer/credentials",
        )


class ReadOnlyTasks(TaskSet):
    """Utilizator pasiv — navighează fără să facă acțiuni."""

    token: str = ""

    def on_start(self):
        r = self.client.post(
            "/auth/login",
            json={"email": "user.demo@railwaydemo.com", "password": "demo"},
            name="/auth/login [demo]",
        )
        if r.status_code == 200:
            self.token = r.json().get("access_token", "")

    @task(5)
    def get_profile(self):
        self.client.get("/users/me", headers=_auth_header(self.token), name="/users/me [demo]")

    @task(3)
    def get_credentials(self):
        self.client.get("/credentials/me", headers=_auth_header(self.token), name="/credentials/me [demo]")

    @task(2)
    def get_card(self):
        self.client.get("/card/me", headers=_auth_header(self.token), name="/card/me")

    @task(1)
    def get_notifications(self):
        self.client.get("/notifications/me", headers=_auth_header(self.token), name="/notifications/me [demo]")


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------

class PassengerUser(HttpUser):
    """Pasager nou — cel mai frecvent tip de utilizator (70%)."""
    tasks = [PassengerTasks]
    weight = 7
    wait_time = between(1, 3)


class TrainVerifierUser(HttpUser):
    """Agent tren — verificări rapide și frecvente (10%)."""
    tasks = [TrainVerifierTasks]
    weight = 1
    wait_time = between(0.5, 2)


class UniversityAgentUser(HttpUser):
    """Agent universitar — cereri mai rare (10%)."""
    tasks = [AgentTasks]
    weight = 1
    wait_time = between(2, 5)


class BrowsingUser(HttpUser):
    """Utilizator pasiv cu cont demo (10%)."""
    tasks = [ReadOnlyTasks]
    weight = 1
    wait_time = between(2, 6)

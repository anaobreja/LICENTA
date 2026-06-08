"""
Tests pentru fluxul OFFLINE: endpointul /card/present trebuie sa returneze
un offline_token care poate fi verificat folosind doar cheia publica
disponibila la /verification-key.

Aceste teste sunt nucleul demonstratiei pentru capitolul de licenta:
demonstreaza ca aplicatia controlorului POATE verifica un token fara
sa apeleze server-ul, doar cu cheia publica si Web Crypto-equivalent.

Strategie de izolare:
    user.demo are deja card activ + credential student emise in seed_demo.sql,
    deci nu avem nevoie de fixtures elaborate. Login-ul cu parola "demo2026"
    functioneaza dupa fix-ul bcrypt 4.1.1.
"""
from __future__ import annotations

import base64
import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization


def _login_user_demo(client) -> str:
    """Login ca user.demo si returneaza JWT token."""
    resp = client.post(
        "/auth/login",
        json={"email": "user.demo@railwaydemo.com", "password": "demo2026"},
    )
    assert resp.status_code == 200, f"user.demo login failed: {resp.text}"
    return resp.json()["access_token"]


def _present_card(client, jwt: str, ttl: int = 180) -> dict:
    """Cere un offline_token via /card/present."""
    resp = client.post(
        "/card/present",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"ttl_seconds": ttl},
    )
    assert resp.status_code == 200, f"/card/present failed: {resp.text}"
    return resp.json()


def _verify_with_endpoint_key(client, token: str) -> dict:
    """
    Reproduce verificarea OFFLINE: descarca cheia publica de la
    /verification-key, decodeaza tokenul, verifica semnatura LOCAL.
    Returneaza payload-ul decodat la succes.
    Arunca InvalidSignature sau ValueError la esuare.
    """
    # Pas 1: descarca cheia publica (operatie care s-ar face o data,
    # cu cache-uire in localStorage la controlor)
    key_resp = client.get("/verification-key")
    assert key_resp.status_code == 200
    public_pem = key_resp.json()["pem"]
    pub_key = serialization.load_pem_public_key(public_pem.encode("ascii"))

    # Pas 2: parseaza tokenul (format: "<b64url_payload>.<b64url_signature>")
    assert "." in token, f"Format token invalid: {token!r}"
    head, sig = token.split(".")

    # Padding b64url -> b64 standard cu padding
    def _decode(s: str) -> bytes:
        padding = "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s + padding)

    canonical = _decode(head)
    signature = _decode(sig)

    # Pas 3: VERIFICA — aici se decide verde/rosu, fara internet
    pub_key.verify(signature, canonical)  # arunca InvalidSignature daca fail

    # Pas 4: deserialeaza payload-ul
    return json.loads(canonical.decode("ascii"))


# ============================================================================
# 1. Smoke tests
# ============================================================================

class TestOfflineTokenResponse:

    def test_response_includes_offline_token(self, client):
        jwt = _login_user_demo(client)
        data = _present_card(client, jwt)
        assert "offline_token" in data, (
            "Raspunsul /card/present trebuie sa includa offline_token. "
            f"Chei prezente: {list(data.keys())}"
        )
        assert isinstance(data["offline_token"], str)
        assert data["offline_token"].count(".") == 1

    def test_response_includes_kid(self, client):
        """kid (key id) e necesar pentru rotirea cheii in viitor."""
        jwt = _login_user_demo(client)
        data = _present_card(client, jwt)
        assert "kid" in data
        assert len(data["kid"]) == 16  # SHA-256 trunchiat

    def test_kid_matches_verification_endpoint(self, client):
        """kid din /card/present == kid din /verification-key."""
        jwt = _login_user_demo(client)
        present_kid = _present_card(client, jwt)["kid"]
        endpoint_kid = client.get("/verification-key").json()["kid"]
        assert present_kid == endpoint_kid

    def test_token_value_short_format_for_manual_entry(self, client):
        """
        Pastram token_value scurt in raspuns (format XXXX-XXXX) pentru a
        permite controlorului sa-l introduca manual cind scanner-ul nu
        functioneaza. Formatul este 8 caractere alfanumerice din alfabet
        fara confuzie + cratima la mijloc (9 chars total).
        """
        import re
        jwt = _login_user_demo(client)
        data = _present_card(client, jwt)
        assert "token_value" in data
        assert re.match(r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$", data["token_value"]), (
            f"token_value nu respecta formatul XXXX-XXXX: {data['token_value']!r}"
        )


# ============================================================================
# 2. Verificare offline: cheia publica de la endpoint verifica tokenul
# ============================================================================

class TestOfflineVerification:
    """
    Demonstratia centrala: o aplicatie EXTERNA poate verifica tokenul
    folosind doar cheia publica + biblioteca crypto standard, FARA acces
    la server in momentul verificarii.
    """

    def test_token_verifies_with_endpoint_public_key(self, client):
        """Roundtrip: emite -> verifica cu cheia publica."""
        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]
        try:
            payload = _verify_with_endpoint_key(client, token)
        except InvalidSignature:
            pytest.fail(
                "Token semnat de server NU verifica cu cheia publica de la "
                "/verification-key. Incompatibilitate critica."
            )
        # Sanity: payload-ul contine ce trebuie
        assert payload["sub"] is not None
        assert payload["holder"]
        assert payload["exp"]

    def test_offline_payload_contains_required_fields(self, client):
        """Payload-ul semnat trebuie sa fie self-contained pentru ecranul controlor."""
        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]
        payload = _verify_with_endpoint_key(client, token)

        for field in ("sub", "pid", "card", "holder", "claims",
                      "issuer", "iat", "exp", "kid"):
            assert field in payload, f"Cimp obligatoriu lipsa in payload: {field}"

        # Tipuri corecte
        assert isinstance(payload["sub"], int)
        assert isinstance(payload["claims"], list)
        assert isinstance(payload["holder"], str) and len(payload["holder"]) > 0

    def test_holder_matches_real_user(self, client):
        """holder din payload trebuie sa fie numele real al userului."""
        jwt = _login_user_demo(client)
        # Ce zice serverul ca e numele meu
        me = client.get("/users/me", headers={"Authorization": f"Bearer {jwt}"}).json()
        expected_name = f"{me['first_name']} {me['last_name']}"

        token = _present_card(client, jwt)["offline_token"]
        payload = _verify_with_endpoint_key(client, token)
        assert payload["holder"] == expected_name

    def test_claims_include_student_verified_for_demo_user(self, client):
        """user.demo are credential student_verified in seed."""
        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]
        payload = _verify_with_endpoint_key(client, token)
        assert "student_verified" in payload["claims"], (
            f"Asteptam student_verified in claims, primit: {payload['claims']}"
        )

    def test_issuer_is_upb_for_demo_user(self, client):
        """user.demo este la UPB conform seed_demo.sql."""
        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]
        payload = _verify_with_endpoint_key(client, token)
        assert payload["issuer"] == "UPB"


# ============================================================================
# 3. Anti-tampering: orice modificare a tokenului sparge verificarea
# ============================================================================

class TestOfflineTampering:

    def test_tampered_payload_fails_verification(self, client):
        """
        Atacatorul modifica payload-ul (ex. vrea sa-si extinda exp).
        Verificarea cu cheia publica trebuie sa esueze.
        """
        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]

        head, sig = token.split(".")
        # Modificare subtila in payload
        idx = len(head) // 2
        new_char = "A" if head[idx] != "A" else "B"
        bad_head = head[:idx] + new_char + head[idx + 1:]
        bad_token = bad_head + "." + sig

        with pytest.raises(InvalidSignature):
            _verify_with_endpoint_key(client, bad_token)

    def test_signature_from_other_token_fails(self, client):
        """
        Atacatorul ia un payload (al sau) si o semnatura (a altui token)
        si incearca sa le combine. Imposibil — semnatura e calculata
        pe payload-ul exact.
        """
        jwt = _login_user_demo(client)
        # Doua prezentari diferite (TTL diferit => exp diferit => alta semnatura)
        token1 = _present_card(client, jwt, ttl=120)["offline_token"]
        token2 = _present_card(client, jwt, ttl=180)["offline_token"]

        head1, _ = token1.split(".")
        _, sig2 = token2.split(".")
        swapped = head1 + "." + sig2

        with pytest.raises(InvalidSignature):
            _verify_with_endpoint_key(client, swapped)

    def test_random_signature_fails(self, client):
        """Semnatura aleatorie (64 bytes zero) trebuie sa esueze."""
        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]
        head, _ = token.split(".")
        # 64 bytes de zero -> b64url
        fake_sig = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode("ascii")
        bad_token = head + "." + fake_sig
        with pytest.raises(InvalidSignature):
            _verify_with_endpoint_key(client, bad_token)


# ============================================================================
# 4. Round-trip prin signing.verify_token (server-side)
# ============================================================================

class TestServerSideVerify:
    """
    Acelasi token trebuie sa fie verificabil si server-side, cu
    signing.verify_token() — pentru cind controlorul e online si vrea
    sa marcheze prezentarea ca folosita.
    """

    def test_server_can_verify_its_own_token(self, client):
        from app.core.signing import verify_token

        jwt = _login_user_demo(client)
        token = _present_card(client, jwt)["offline_token"]
        payload = verify_token(token)
        assert payload["holder"]
        assert payload["sub"] is not None

    def test_expired_token_rejected_server_side(self, client):
        """
        Generam un token cu ttl minim acceptat (30s), apoi simulam expirarea
        prin re-semnare cu exp in trecut. Strategia evita sleep-uri de
        30 secunde in test, dar verifica acelasi cod path.
        """
        from datetime import datetime, timedelta, timezone
        from app.core.signing import sign_payload, verify_token, get_key_id

        # Construim direct un payload expirat si-l semnam.
        # Asta testeaza exact aceeasi logica de verify ca tokenurile reale.
        expired_payload = {
            "sub": 1,
            "pid": 99999,
            "card": 1,
            "holder": "Demo Expired",
            "claims": ["student_verified"],
            "issuer": "UPB",
            "iat": (datetime.now(timezone.utc) - timedelta(minutes=10))
                .isoformat().replace("+00:00", "Z"),
            "exp": (datetime.now(timezone.utc) - timedelta(minutes=5))
                .isoformat().replace("+00:00", "Z"),
            "kid": get_key_id(),
        }
        expired_token = sign_payload(expired_payload)

        with pytest.raises(ValueError, match="(?i)expirat"):
            verify_token(expired_token)

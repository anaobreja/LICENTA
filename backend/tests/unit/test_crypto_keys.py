"""
Tests pentru endpoint-ul /verification-key.

Acest endpoint este public si returneaza cheia publica Ed25519 folosita
de aplicatia controlorului pentru verificarea offline a tokenurilor QR.
"""
from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization


class TestVerificationKeyEndpoint:

    def test_endpoint_is_public_and_returns_200(self, client):
        """Fara auth required — orice aplicatie a controlorului trebuie sa
        poata descarca cheia publica fara cont."""
        resp = client.get("/verification-key")
        assert resp.status_code == 200, resp.text
        assert resp.status_code != 401

    def test_response_has_required_fields(self, client):
        data = client.get("/verification-key").json()
        for field in ("algorithm", "kid", "pem", "raw_base64", "usage"):
            assert field in data, f"Cimp lipsa in raspuns: {field}"
        assert data["algorithm"] == "Ed25519"
        assert data["usage"] == "verify"

    def test_pem_is_valid_public_key(self, client):
        """PEM-ul returnat trebuie sa fie incarcabil cu biblioteca cryptography."""
        data = client.get("/verification-key").json()
        pem = data["pem"]
        # Parseaza cu biblioteca standard — daca esueaza, e bug
        pub_key = serialization.load_pem_public_key(pem.encode("ascii"))
        # Verifica ca e intr-adevar Ed25519
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        assert isinstance(pub_key, Ed25519PublicKey)

    def test_raw_base64_is_32_bytes(self, client):
        """Cheia publica Ed25519 raw = exact 32 bytes."""
        data = client.get("/verification-key").json()
        raw = base64.standard_b64decode(data["raw_base64"])
        assert len(raw) == 32

    def test_pem_and_raw_match_same_key(self, client):
        """PEM-ul si raw-ul trebuie sa reprezinte aceeasi cheie publica."""
        data = client.get("/verification-key").json()
        pem_key = serialization.load_pem_public_key(data["pem"].encode("ascii"))
        raw_bytes = pem_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        raw_from_endpoint = base64.standard_b64decode(data["raw_base64"])
        assert raw_bytes == raw_from_endpoint

    def test_kid_is_stable_across_calls(self, client):
        """Key ID identic intre apeluri = aceeasi cheie pe server."""
        kid1 = client.get("/verification-key").json()["kid"]
        kid2 = client.get("/verification-key").json()["kid"]
        assert kid1 == kid2
        assert len(kid1) == 16  # SHA-256 trunchiat


class TestVerificationKeyUsage:
    """
    Verifica ca o aplicatie EXTERNA poate folosi cheia publica de la
    endpoint ca sa verifice un token semnat de server.
    Asta este testul cel mai important pentru capitolul de licenta:
    demonstreaza ca aplicatia controlorului POATE verifica offline.
    """

    def test_token_signed_by_server_verifies_with_endpoint_key(self, client):
        from datetime import datetime, timedelta, timezone
        from cryptography.exceptions import InvalidSignature

        # 1. Server-ul ne da cheia publica
        public_pem = client.get("/verification-key").json()["pem"]
        pub_key = serialization.load_pem_public_key(public_pem.encode("ascii"))

        # 2. Simulez ca am primit un token semnat de server.
        #    Pentru asta, generez direct cu signing.sign_payload —
        #    in test integration real vom apela /card/present (in faza 2).
        from app.core.signing import sign_payload

        payload = {
            "sub": "test_user",
            "iat": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=3))
                .isoformat().replace("+00:00", "Z"),
            "card_id": 1,
        }
        token = sign_payload(payload)

        # 3. Verific cu cheia publica DOAR (fara acces la cheia privata)
        head, sig = token.split(".")
        from app.core.signing import _b64url_decode
        canonical = _b64url_decode(head)
        signature = _b64url_decode(sig)

        # Daca acest assert trece, controlorul OFFLINE poate verifica
        # tokenuri emise de server.
        try:
            pub_key.verify(signature, canonical)
        except InvalidSignature:
            pytest.fail(
                "Cheia publica de la /verification-key NU verifica tokenul "
                "semnat de server — incompatibilitate critica."
            )

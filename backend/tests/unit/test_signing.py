"""
Unit tests pentru modulul core/signing.py.

Strategia:
    Fiecare test ruleaza intr-un tempdir izolat (fixture `isolated_keys`)
    cu o cheie Ed25519 proprie. Asta inseamna ca:
      * Testele NU depind de cheia "reala" a aplicatiei
      * Testele pot rula in paralel fara coliziuni
      * Nu lasam fisiere de chei in repo

Acoperire:
  Functii pure (fara DB, fara FastAPI):
    1. sign + verify roundtrip cu payload tipic
    2. Determinism: aceeasi cheie + payload = aceeasi semnatura
    3. Anti-tampering: orice modificare in payload spargere semnatura
    4. Expirare: token cu exp < now -> ValueError
    5. Format invalid: token corupt, lipsa separator etc.
    6. Cheia publica derivata corect din cea privata
    7. Key ID stabil pentru aceeasi cheie
    8. Generare automata cind fisierul lipseste
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Aceste teste nu folosesc DB-ul de teste, deci NU avem nevoie de fixture-ul
# `client` din conftest. Totusi, conftest.py face setup la DATABASE_URL care e
# ok sa ramina — nu impacteaza testele de signing.


# ============================================================================
# Fixture-uri
# ============================================================================

@pytest.fixture
def isolated_keys(tmp_path: Path, monkeypatch):
    """
    Forteaza signing.py sa foloseasca o cheie temporara pentru acest test.
    Returneaza modulul signing reimportat cu noua configuratie.
    """
    key_path = tmp_path / "test_signing.pem"
    monkeypatch.setenv("SIGNING_KEY_PATH", str(key_path))

    # Reset state intern + reimport pentru a invalida lazy-cached keys
    import app.core.signing as signing
    signing.reset_keys_for_testing()
    yield signing
    signing.reset_keys_for_testing()


def _payload(ttl_seconds: int = 180, **extra) -> dict:
    """Payload tipic pentru un card_presentation token."""
    now = datetime.now(timezone.utc)
    base = {
        "sub": "user_42",
        "iat": now.isoformat().replace("+00:00", "Z"),
        "exp": (now + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"),
        "card_id": 7,
        "presentation_id": 123,
    }
    base.update(extra)
    return base


# ============================================================================
# 1. Sign + verify roundtrip
# ============================================================================

class TestRoundtrip:

    def test_sign_returns_compact_string(self, isolated_keys):
        token = isolated_keys.sign_payload(_payload())
        assert isinstance(token, str)
        # Format: "<b64url_payload>.<b64url_signature>"
        assert token.count(".") == 1, f"Asteptam un singur separator, primit: {token}"
        parts = token.split(".")
        assert all(len(p) > 0 for p in parts)

    def test_verify_returns_payload(self, isolated_keys):
        original = _payload()
        token = isolated_keys.sign_payload(original)
        verified = isolated_keys.verify_token(token)
        assert verified == original, "Verify trebuie sa returneze acelasi payload"

    def test_roundtrip_preserves_all_fields(self, isolated_keys):
        original = _payload(
            extra_field="some value",
            attributes=["student", "verified"],
            nested={"foo": "bar", "n": 42},
        )
        token = isolated_keys.sign_payload(original)
        verified = isolated_keys.verify_token(token)
        assert verified == original

    def test_token_size_fits_in_qr(self, isolated_keys):
        """
        Token tipic trebuie sa incapa intr-un QR de versiune <= 17 (cu
        ~1000 caractere alfanumerice citibil pe ecran de telefon).
        Limita 500 da marja confortabila pentru payload-urile reale
        din prezentare (~7-8 campuri JSON scurte).
        """
        token = isolated_keys.sign_payload(_payload())
        assert len(token) < 500, (
            f"Token prea lung pentru QR ({len(token)} caractere). "
            "Reconsidera ce metadate semnam."
        )


# ============================================================================
# 2. Determinism — Ed25519 este determinist prin design
# ============================================================================

class TestDeterminism:

    def test_same_payload_same_signature(self, isolated_keys):
        """Ed25519 e determinist: acelasi input -> aceeasi semnatura."""
        payload = _payload()
        t1 = isolated_keys.sign_payload(payload)
        t2 = isolated_keys.sign_payload(payload)
        assert t1 == t2, "Ed25519 ar trebui sa fie determinist"

    def test_field_order_doesnt_matter(self, isolated_keys):
        """
        sign_payload foloseste JSON canonic cu sort_keys=True, deci
        ordinea cheilor in dict-ul de input nu trebuie sa schimbe rezultatul.
        """
        p1 = {"sub": "u", "exp": "2099-01-01T00:00:00Z", "iat": "2099-01-01T00:00:00Z", "card_id": 1}
        p2 = {"card_id": 1, "iat": "2099-01-01T00:00:00Z", "exp": "2099-01-01T00:00:00Z", "sub": "u"}
        assert isolated_keys.sign_payload(p1) == isolated_keys.sign_payload(p2)


# ============================================================================
# 3. Anti-tampering — modificarile sparge semnatura
# ============================================================================

class TestTampering:

    def test_modified_payload_byte_fails_verification(self, isolated_keys):
        """Schimbam un caracter in payload-ul codat -> verify pica."""
        token = isolated_keys.sign_payload(_payload())
        head, sig = token.split(".")
        # Modificare subtila: schimbam o litera la mijloc
        idx = len(head) // 2
        mutated_char = "A" if head[idx] != "A" else "B"
        tampered = head[:idx] + mutated_char + head[idx + 1:]
        bad_token = tampered + "." + sig

        with pytest.raises(ValueError, match="(?i)semnatura invalida|modificat"):
            isolated_keys.verify_token(bad_token)

    def test_modified_signature_fails_verification(self, isolated_keys):
        """Schimbam o litera in semnatura -> verify pica."""
        token = isolated_keys.sign_payload(_payload())
        head, sig = token.split(".")
        idx = len(sig) // 2
        new_char = "A" if sig[idx] != "A" else "B"
        bad_sig = sig[:idx] + new_char + sig[idx + 1:]
        bad_token = head + "." + bad_sig

        with pytest.raises(ValueError, match="(?i)semnatura invalida"):
            isolated_keys.verify_token(bad_token)

    def test_payload_swap_attack_fails(self, isolated_keys):
        """
        Atacatorul ia un token valid emis pentru user_1 si vrea sa-l "rebrand"
        cu payload-ul pentru user_2 — pastrind aceeasi semnatura.
        Imposibil: semnatura e calculata pe payload-ul exact.
        """
        token_a = isolated_keys.sign_payload(_payload(sub="user_1"))
        token_b = isolated_keys.sign_payload(_payload(sub="user_2"))

        head_a, _ = token_a.split(".")
        _, sig_b = token_b.split(".")
        swapped = head_a + "." + sig_b

        with pytest.raises(ValueError):
            isolated_keys.verify_token(swapped)


# ============================================================================
# 4. Expirare — exp e validat la verify
# ============================================================================

class TestExpiration:

    def test_expired_token_rejected(self, isolated_keys):
        """Token cu exp in trecut -> ValueError, mesaj clar."""
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
        token = isolated_keys.sign_payload(_payload(exp=past))

        with pytest.raises(ValueError, match="(?i)expirat"):
            isolated_keys.verify_token(token)

    def test_fresh_token_accepted(self, isolated_keys):
        """Sanity check: token cu exp in viitor trece verify."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        token = isolated_keys.sign_payload(_payload(exp=future))
        result = isolated_keys.verify_token(token)
        assert result["exp"] == future

    def test_missing_exp_rejected(self, isolated_keys):
        """Token fara cimpul `exp` -> ValueError."""
        payload = _payload()
        del payload["exp"]
        token = isolated_keys.sign_payload(payload)
        with pytest.raises(ValueError, match="(?i)exp"):
            isolated_keys.verify_token(token)

    def test_malformed_exp_rejected(self, isolated_keys):
        """exp ne-ISO -> ValueError."""
        token = isolated_keys.sign_payload(_payload(exp="ieri-pe-la-ora-5"))
        with pytest.raises(ValueError, match="(?i)iso 8601|exp"):
            isolated_keys.verify_token(token)

    def test_exp_without_timezone_treated_as_utc(self, isolated_keys):
        """
        Daca exp vine fara TZ (caz limita pentru clienti vechi), il tratam
        ca UTC. Bug-ul opus (interpretare ca local time) e ce am avut in
        front si l-am reparat azi — vrem sa nu apara aici.
        """
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        # Fara sufix Z, fara +offset
        token = isolated_keys.sign_payload(_payload(exp=future))
        # Trebuie sa treaca: 1h in viitor in UTC
        result = isolated_keys.verify_token(token)
        assert result["exp"] == future


# ============================================================================
# 5. Format invalid
# ============================================================================

class TestMalformedToken:

    def test_empty_string_rejected(self, isolated_keys):
        with pytest.raises(ValueError):
            isolated_keys.verify_token("")

    def test_no_separator_rejected(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)separator|format"):
            isolated_keys.verify_token("abcdef")

    def test_too_many_segments_rejected(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)segment|format"):
            isolated_keys.verify_token("a.b.c")

    def test_invalid_base64_rejected(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)base64|corupt|format"):
            isolated_keys.verify_token("!!!.@@@")

    def test_non_string_input_rejected(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)format"):
            isolated_keys.verify_token(None)  # type: ignore


# ============================================================================
# 6. Cheia publica / Key ID
# ============================================================================

class TestPublicKey:

    def test_public_key_pem_is_valid_pem(self, isolated_keys):
        pem = isolated_keys.get_public_key_pem()
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert pem.rstrip().endswith("-----END PUBLIC KEY-----")

    def test_public_key_raw_is_32_bytes(self, isolated_keys):
        """Ed25519 public key = 32 bytes raw."""
        raw_b64 = isolated_keys.get_public_key_raw_b64()
        raw = base64.standard_b64decode(raw_b64)
        assert len(raw) == 32

    def test_public_key_stable_across_calls(self, isolated_keys):
        """Doua apeluri consecutive returneaza acelasi PEM."""
        p1 = isolated_keys.get_public_key_pem()
        p2 = isolated_keys.get_public_key_pem()
        assert p1 == p2

    def test_key_id_stable_for_same_key(self, isolated_keys):
        kid1 = isolated_keys.get_key_id()
        kid2 = isolated_keys.get_key_id()
        assert kid1 == kid2
        assert len(kid1) == 16  # SHA-256 trunchiat la 16 hex chars
        # Trebuie sa fie hex valid
        int(kid1, 16)  # arunca ValueError daca nu


# ============================================================================
# 7. Auto-generare cheie
# ============================================================================

class TestKeyGeneration:

    def test_key_auto_generated_when_missing(self, tmp_path, monkeypatch):
        """
        Daca SIGNING_KEY_PATH pointeaza la un fisier inexistent, signing.py
        genereaza automat o cheie noua si o salveaza.
        """
        key_path = tmp_path / "auto_generated.pem"
        monkeypatch.setenv("SIGNING_KEY_PATH", str(key_path))

        import app.core.signing as signing
        signing.reset_keys_for_testing()
        try:
            assert not key_path.exists()
            # Primul apel -> ar trebui sa creeze fisierul
            signing.get_private_key()
            assert key_path.exists(), "Cheia ar trebui salvata pe disc"

            # Continutul ar trebui sa fie PEM PKCS#8
            pem_text = key_path.read_text()
            assert "BEGIN PRIVATE KEY" in pem_text or "BEGIN PKCS8" in pem_text
        finally:
            signing.reset_keys_for_testing()

    def test_existing_key_reloaded(self, tmp_path, monkeypatch):
        """
        Daca fisierul exista deja, signing.py il incarca — nu suprascrie.
        """
        key_path = tmp_path / "preexisting.pem"
        monkeypatch.setenv("SIGNING_KEY_PATH", str(key_path))

        import app.core.signing as signing

        # Round 1: genereaza
        signing.reset_keys_for_testing()
        kid1 = signing.get_key_id()
        content1 = key_path.read_bytes()

        # Round 2: reload — acelasi kid, acelasi byte content
        signing.reset_keys_for_testing()
        kid2 = signing.get_key_id()
        content2 = key_path.read_bytes()

        assert kid1 == kid2, "Aceeasi cheie ar trebui sa produca acelasi key_id"
        assert content1 == content2, "Fisierul nu trebuie suprascris"
        signing.reset_keys_for_testing()


# ============================================================================
# 8. Cross-verify cu o cheie publica externa
# ============================================================================

class TestExternalVerify:
    """
    Simulam ce face aplicatia controlorului OFFLINE:
        1. Are doar cheia publica (PEM string)
        2. Primeste un token semnat
        3. Verifica semnatura folosind doar cheia publica + biblioteca crypto
    """

    def test_external_party_can_verify_with_public_key_only(self, isolated_keys):
        from cryptography.hazmat.primitives import serialization
        from cryptography.exceptions import InvalidSignature

        # Server-ul ne da cheia publica si tokenul
        public_pem = isolated_keys.get_public_key_pem()
        token = isolated_keys.sign_payload(_payload())

        # Acum simulam clientul: incarca cheia publica si verifica DOAR
        # cu ea (fara acces la cheia privata!)
        pub_key = serialization.load_pem_public_key(public_pem.encode("ascii"))

        head, sig = token.split(".")
        canonical = isolated_keys._b64url_decode(head)
        signature = isolated_keys._b64url_decode(sig)

        # Aceasta verificare NU foloseste niciun state din signing.py —
        # doar cheia publica si tokenul. Daca trece, e dovada ca un client
        # extern poate verifica offline.
        try:
            pub_key.verify(signature, canonical)
        except InvalidSignature:
            pytest.fail("Verificarea cu cheia publica externa ar fi trebuit sa treaca")

    def test_token_signed_by_other_key_fails(self, isolated_keys, tmp_path, monkeypatch):
        """
        Generam un token cu cheia A. Apoi schimbam cheia (cheia B) si
        incercam sa verificam tokenul A — trebuie sa esueze.
        """
        token_a = isolated_keys.sign_payload(_payload())

        # Schimbare cheie: pointam catre alt path, fortam regenerare
        new_path = tmp_path / "different_key.pem"
        monkeypatch.setenv("SIGNING_KEY_PATH", str(new_path))
        isolated_keys.reset_keys_for_testing()

        # Acum get_key_id() returneaza alta cheie
        with pytest.raises(ValueError, match="(?i)semnatura"):
            isolated_keys.verify_token(token_a)


# ============================================================================
# 9. decode_token_unchecked — cai de eroare (linii 341-354)
# ============================================================================

class TestDecodeTokenUnchecked:

    def test_non_string_raises(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)str"):
            isolated_keys.decode_token_unchecked(None)  # type: ignore

    def test_no_separator_raises(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)separator|format"):
            isolated_keys.decode_token_unchecked("noseparator")

    def test_too_many_segments_raises(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)segment|format"):
            isolated_keys.decode_token_unchecked("a.b.c")

    def test_invalid_base64_raises(self, isolated_keys):
        with pytest.raises(ValueError, match="(?i)corupt|base64|payload"):
            isolated_keys.decode_token_unchecked("!!!.@@@")

    def test_valid_payload_decoded_without_sig_check(self, isolated_keys):
        """decode_token_unchecked returneaza payload-ul fara sa verifice semnatura."""
        original = _payload()
        token = isolated_keys.sign_payload(original)
        result = isolated_keys.decode_token_unchecked(token)
        assert result == original

    def test_tampered_payload_still_decoded(self, isolated_keys):
        """
        decode_token_unchecked NU verifica semnatura — payload-ul modificat
        se decodeaza daca e JSON valid (asta e intentionat: doar formatuk e testat).
        """
        import base64
        import json as _json

        # Construim manual un token cu payload modificat + semnatura originala
        # (semnatura nu se potriveste, dar decode_unchecked ignora asta)
        payload_modified = _payload(sub="hacker")
        canonical = _json.dumps(payload_modified, sort_keys=True,
                                separators=(',', ':')).encode()
        # Padding base64url corect
        b64 = base64.urlsafe_b64encode(canonical).rstrip(b"=").decode()
        fake_sig = "A" * 86  # 64 bytes in base64url fara padding = 86 chars
        fake_token = f"{b64}.{fake_sig}"

        result = isolated_keys.decode_token_unchecked(fake_token)
        assert result["sub"] == "hacker"


# ============================================================================
# 10. verify_token — cai de eroare de format (linii 275-305)
# ============================================================================

class TestVerifyTokenEdgeCases:

    def test_empty_payload_segment_raises(self, isolated_keys):
        """
        Token cu payload gol '.<sig>' -> ValueError 'payload gol'.
        Semnatura trebuie sa fie exact 64 bytes (86 chars b64url).
        """
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        # Cream o semnatura de 64 bytes valida pentru payload gol
        priv = isolated_keys.get_private_key()
        sig_bytes = priv.sign(b"")
        sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
        token = f".{sig_b64}"

        with pytest.raises(ValueError, match="(?i)gol|empty|payload"):
            isolated_keys.verify_token(token)

    def test_non_dict_payload_raises(self, isolated_keys):
        """Payload JSON valid dar nu e obiect (e.g., lista) -> ValueError."""
        import base64
        import json as _json

        # Semnam o lista (nu un dict)
        canonical = _json.dumps([1, 2, 3], sort_keys=True,
                                 separators=(',', ':')).encode()
        priv = isolated_keys.get_private_key()
        sig = priv.sign(canonical)
        b64_payload = base64.urlsafe_b64encode(canonical).rstrip(b"=").decode()
        b64_sig = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        token = f"{b64_payload}.{b64_sig}"

        with pytest.raises(ValueError, match="(?i)obiect|dict|payload"):
            isolated_keys.verify_token(token)

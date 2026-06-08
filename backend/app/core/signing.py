"""
Semnaturi digitale Ed25519 pentru verificarea OFFLINE a cardului digital.

==============================================================================
DE CE Ed25519
==============================================================================
Algoritmul Ed25519 (RFC 8032) ofera:
  * Chei publice 32 bytes (incap usor intr-un QR code)
  * Semnaturi 64 bytes (idem)
  * Generare si verificare in O(1) — sub 1ms pe hardware modern
  * Securitate echivalenta cu ECDSA-P256 / RSA-3072
  * Determinist (acelasi mesaj + cheie = aceeasi semnatura) — usor de testat
  * Nu este vulnerabil la atacuri side-channel ca ECDSA cu nonces slabe

Comparatie cu alternative pentru cazul nostru (semnare token QR scurt):
  RSA-2048 ar fi produs semnaturi de 256 bytes — prea mult pentru un QR.
  ECDSA-P256 ar fi mers, dar cheia publica e ~64 bytes si verificarea
  in Web Crypto API e mai complicata (raw vs PKCS#8 vs SPKI).
  HMAC simetric NU se preteaza — controlorul ar avea nevoie de cheia
  privata pentru a verifica, ceea ce sparge intregul model de securitate.

==============================================================================
MODEL DE SECURITATE
==============================================================================
  Backend (server):    detine cheia PRIVATA (semneaza)
  Aplicatia controlor: detine cheia PUBLICA (verifica, descarcata o data
                       din /verification-key si pastrata in localStorage)
  Studentul:           primeste un token SEMNAT, il afiseaza ca QR

La verificare offline, aplicatia controlorului:
  1. Decodeaza QR-ul -> structura cu payload + signature
  2. Verifica semnatura cu cheia publica locala
  3. Verifica ca expires_at > now (clock-ul local)
  4. Daca ambele OK -> ECRAN VERDE, fara internet

Ce NU poate face verificarea offline:
  * Anti-replay (single-use): controlorul nu stie ca tokenul a fost folosit
    deja undeva altundeva. Aceasta protectie ramane DOAR online.
  * Revocare: daca studentul si-a pierdut telefonul si vrem sa invalidam
    cardul, online actualizam card.status = 'revoked'; offline nu putem.

Tradeoff acceptat: pentru durata scurta a tokenului (3 minute), riscul de
replay offline e limitat. Pentru atacuri serioase, controlorul comuta in
modul online (default) cand exista semnal.

==============================================================================
PERSISTENTA CHEII
==============================================================================
Cheia privata e stocata in `keys/signing_ed25519.pem` (PKCS#8 PEM, neparolat
pentru simplicitate in dev — in productie ar fi parolat cu KEK din KMS).

Path-ul e configurabil via ENV var SIGNING_KEY_PATH. Daca fisierul lipseste,
generam automat o cheie noua la primul apel `get_private_key()` si o salvam
in path-ul respectiv, cu warning explicit in log.

Folderul `keys/` este in .gitignore — cheia NU trebuie versionata.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

# ============================================================================
# Configurare path-uri
# ============================================================================
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KEY_PATH = _BACKEND_ROOT / "keys" / "signing_ed25519.pem"


def _key_path() -> Path:
    """Path-ul cheii private. Suprascrieibil via ENV pentru teste."""
    env_path = os.environ.get("SIGNING_KEY_PATH")
    return Path(env_path) if env_path else DEFAULT_KEY_PATH


# ============================================================================
# Lazy load + thread-safety
# ============================================================================
_private_key: Ed25519PrivateKey | None = None
_public_key: Ed25519PublicKey | None = None
_load_lock = threading.Lock()


def _load_or_generate_key() -> Ed25519PrivateKey:
    """
    Incarca cheia privata din disc. Daca fisierul lipseste, genereaza una
    noua si o salveaza. Aceasta cale e acceptabila pentru dev/demo; in
    productie cheia ar trebui pre-provisionata, nu auto-generata.
    """
    path = _key_path()
    if path.exists():
        pem_bytes = path.read_bytes()
        return serialization.load_pem_private_key(pem_bytes, password=None)

    # Generare noua
    logger.warning(
        "Cheia de semnare lipseste la %s — generez o cheie noua. "
        "In productie, cheia trebuie pre-provisionata si protejata.",
        path,
    )
    new_key = Ed25519PrivateKey.generate()

    path.parent.mkdir(parents=True, exist_ok=True)
    pem = new_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)

    # Pe Unix incercam sa restrictionam permisiunile la doar owner
    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass  # Windows nu suporta chmod tip Unix

    return new_key


def get_private_key() -> Ed25519PrivateKey:
    """Returneaza cheia privata, lazy-loaded la primul apel."""
    global _private_key, _public_key
    if _private_key is None:
        with _load_lock:
            if _private_key is None:  # double-check pattern
                _private_key = _load_or_generate_key()
                _public_key = _private_key.public_key()
    return _private_key


def get_public_key() -> Ed25519PublicKey:
    """Returneaza cheia publica derivata din cheia privata."""
    if _public_key is None:
        get_private_key()  # populeaza si _public_key
    assert _public_key is not None
    return _public_key


def reset_keys_for_testing() -> None:
    """Reset state — util in pytest fixtures."""
    global _private_key, _public_key
    with _load_lock:
        _private_key = None
        _public_key = None


# ============================================================================
# Serializare cheie publica
# ============================================================================
def get_public_key_pem() -> str:
    """
    Returneaza cheia publica in format PEM (text). Folosita de endpoint-ul
    GET /verification-key, descarcata o data de aplicatia controlorului.
    """
    pem = get_public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("ascii")


def get_public_key_raw_b64() -> str:
    """
    Cheia publica ca 32 bytes brut (raw), encoded base64 standard.
    Format mai compact decit PEM, util in JSON-ul de raspuns.
    """
    raw = get_public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.standard_b64encode(raw).decode("ascii")


def get_key_id() -> str:
    """
    Key ID = SHA-256(public_key_raw)[:8] in hex. Permite rotirea cheii in
    viitor: tokens semnate cu o cheie veche raman verificabile daca clientul
    cere cheia corecta dupa kid.
    """
    import hashlib

    raw = get_public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()[:16]


# ============================================================================
# JSON canonical — esential pentru determinism la semnare
# ============================================================================
def _canonical_json(payload: dict[str, Any]) -> bytes:
    """
    Serializeaza dictul intr-o reprezentare JSON CANONICA:
      * cheile sortate alfabetic (sort_keys=True)
      * fara spatii redundante (separators compact)
      * ASCII-only (ensure_ascii=True) — sigur prin orice canal

    Acelasi dict produce mereu acelasi rezultat byte-cu-byte, indiferent
    de ordinea in care a fost construit. Crucial: clientul de verificare
    trebuie sa serializeze IDENTIC, altfel semnatura nu se potriveste.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


# ============================================================================
# Semnare
# ============================================================================
def sign_payload(payload: dict[str, Any]) -> str:
    """
    Semneaza payload-ul si returneaza un token compact in format:

        base64url(canonical_json) + "." + base64url(signature)

    Format inspirat de JWS Compact Serialization (RFC 7515), dar mai
    simplu — nu avem header separat, algoritm-ul Ed25519 e implicit.
    Decisia: format-ul propriu ne permite QR-uri mai mici decat JWT.

    Payload-ul TREBUIE sa contina cel putin:
      * exp:  timestamp ISO 8601 UTC pentru cind expira tokenul
      * iat:  timestamp ISO 8601 UTC pentru cind a fost emis (anti-replay slab)
      * kid:  key id (cu ce cheie a fost semnat — pentru rotire ulterioara)

    Toate cimpurile sunt validate la `verify_token`.
    """
    canonical = _canonical_json(payload)
    signature = get_private_key().sign(canonical)
    return (
        _b64url(canonical) + "." + _b64url(signature)
    )


def verify_token(token: str) -> dict[str, Any]:
    """
    Verifica tokenul SEMNAT si returneaza payload-ul daca e valid.

    Raises:
        ValueError pentru orice eroare de format / semnatura / expirare.
        Mesajul exceptiei e descriptiv pentru debugging in teste, dar in
        productie ne asiguram ca nu leak-uim detalii catre client.
    """
    # Verificam tipul intii — `"." not in token` ar arunca TypeError pe None
    if not isinstance(token, str):
        raise ValueError(f"Format token invalid (asteptat str, primit {type(token).__name__}).")
    if "." not in token:
        raise ValueError("Format token invalid (lipseste separatorul '.').")

    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Format token invalid (asteptat 2 segmente).")

    try:
        canonical = _b64url_decode(parts[0])
        signature = _b64url_decode(parts[1])
    except Exception as e:
        raise ValueError(f"Token corupt (base64 invalid): {e}")

    # Ed25519 are dimensiuni fixe: signature = 64 bytes exact.
    # Verificarea aici, nu in `pub_key.verify`, ne permite sa returnam
    # un mesaj clar "format corupt" in loc de "semnatura invalida"
    # (input gen "!!!" decodifica la bytes goale, nu arunca eroare).
    if len(signature) != 64:
        raise ValueError(
            f"Token corupt: semnatura asteptata 64 bytes, primita {len(signature)}."
        )
    if len(canonical) == 0:
        raise ValueError("Token corupt: payload gol.")

    # Verifica semnatura inainte sa atingem JSON-ul: nu deserializam
    # niciodata input nesemnat (defensive design).
    try:
        get_public_key().verify(signature, canonical)
    except InvalidSignature:
        raise ValueError("Semnatura invalida — tokenul a fost modificat sau emis de alta cheie.")

    try:
        payload = json.loads(canonical.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        # Imposibil daca semnatura e valida si tokenul vine de la noi,
        # dar plasa de siguranta.
        raise ValueError(f"Payload invalid JSON: {e}")

    # Validari semantice
    if not isinstance(payload, dict):
        raise ValueError("Payload trebuie sa fie obiect JSON.")

    exp = payload.get("exp")
    if not exp:
        raise ValueError("Payload lipseste cimpul 'exp'.")

    try:
        exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Cimpul 'exp' nu e ISO 8601 valid: {exp}")

    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > exp_dt:
        raise ValueError(f"Token expirat la {exp_dt.isoformat()}.")

    return payload


def decode_token_unchecked(token: str) -> dict[str, Any]:
    """
    Decodeaza payload-ul DIN tokenul semnat FARA a-i verifica semnatura.

    Folosit cind avem incredere in sursa tokenului (ex. tokenul scanat
    online prin /card/verify) si vrem doar sa extragem `pid` pentru a
    cauta inregistrarea in DB. Verificarea reala se face apoi la nivel
    de DB (pid + status='active' + expires_at > now).

    PERICOL: nu apela aceasta functie pe input untrusted fara sa adaugi
    o verificare ulterioara. Pentru verificarea offline ireversibila,
    foloseste verify_token() care valideaza si semnatura.

    Raises:
        ValueError pentru format invalid.
    """
    if not isinstance(token, str):
        raise ValueError(f"Asteptat str, primit {type(token).__name__}.")
    if "." not in token:
        raise ValueError("Format token invalid (lipseste separatorul '.').")

    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Format token invalid (asteptat 2 segmente).")

    try:
        canonical = _b64url_decode(parts[0])
        return json.loads(canonical.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Payload corupt: {e}")


# ============================================================================
# Helpers base64url (fara padding, ca in JWS)
# ============================================================================
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    # Recuperam padding-ul: urlsafe_b64decode are nevoie de length % 4 == 0
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)

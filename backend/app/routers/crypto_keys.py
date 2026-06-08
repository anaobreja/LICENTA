"""
Endpoint pentru distribuirea cheii publice de verificare offline.

Cheia publica este aceeasi pentru toti clientii (un singur server).
Este descarcata o data de aplicatia controlorului (la prim login sau
prima sincronizare) si pastrata local in localStorage. La verificarea
offline a unui token QR, aplicatia controlorului foloseste exclusiv
aceasta cheie publica + biblioteca Web Crypto API a browser-ului.

Securitate:
    * Endpoint PUBLIC — cheia publica nu e secret. Oricine o poate vedea.
    * Niciodata nu expunem aici cheia privata.
    * Returnam si `kid` (key id) ca clientii sa poata detecta rotirea
      cheii in viitor si sa o reactualizeze daca e nevoie.
"""
from fastapi import APIRouter

from app.core.signing import (
    get_key_id,
    get_public_key_pem,
    get_public_key_raw_b64,
)

router = APIRouter(tags=["crypto"])


@router.get("/verification-key")
def get_verification_key():
    """
    Returneaza cheia publica Ed25519 folosita pentru verificarea offline
    a tokenurilor QR de prezentare a cardului digital.

    Formate disponibile in raspuns:
      * `pem`        — PKCS#8 SubjectPublicKeyInfo (compat orice biblioteca)
      * `raw_base64` — 32 bytes brut, base64-standard (pentru Web Crypto API
                       care suporta direct format 'raw' la importKey pentru
                       algoritmul Ed25519)

    Clientii ar trebui sa cache-uiasca raspunsul + kid. La fiecare
    sincronizare ulterioara, daca kid s-a schimbat -> reactualizeaza
    cheia locala (rotire detectata).
    """
    return {
        "algorithm": "Ed25519",
        "kid": get_key_id(),
        "pem": get_public_key_pem(),
        "raw_base64": get_public_key_raw_b64(),
        "usage": "verify",
    }

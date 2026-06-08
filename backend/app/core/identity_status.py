"""
Identity verification status & data immutability rules.

Reguli de business:
  1. Datele personale validate de un agent (CNP, nume, data nasterii,
     home_station_id) sunt FROZEN dupa aprobare.
  2. Aprobarea expira la inceputul anului universitar urmator (1 octombrie).
  3. Dupa expirare, campurile redevin editabile -> userul trebuie sa refaca
     verificarea pentru a primi un nou card digital.
  4. home_station_id este derivat din adresa de domiciliu validata, deci
     intra in setul FROZEN.

Credential-ul cheie care marcheaza "identitate validata" este
`identity_verified` din tabela user_credentials. La aprobarea unei cereri,
agentul universitar creeaza acest credential cu status='active' si
valid_until = sfarsitul anului universitar curent.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constante
# ---------------------------------------------------------------------------

# Lista campurilor care sunt FROZEN cat timp userul are identity_verified activ.
# Aceste campuri sunt derivate din date validate (CI + adresa), deci modificarea
# lor unilaterala = fraudă identitate.
FROZEN_FIELDS_WHEN_VERIFIED = {
    "cnp",
    "first_name",
    "last_name",
    "birth_date",
    "home_station_id",
}

# Anul universitar incepe pe 1 octombrie (regula standard MFE Romania).
# Daca azi e <1 oct => expirarea curenta e 1 oct anul asta.
# Daca azi e >=1 oct => expirarea curenta e 1 oct anul viitor.
ACADEMIC_YEAR_START_MONTH = 10
ACADEMIC_YEAR_START_DAY = 1

# Tipul credentialului care marcheaza "datele personale au fost validate"
IDENTITY_VERIFIED_CREDENTIAL = "identity_verified"


# ---------------------------------------------------------------------------
# Functii helper - logica anului universitar
# ---------------------------------------------------------------------------

def get_current_academic_year_end(today: Optional[date] = None) -> date:
    """
    Returneaza data la care expira anul universitar in curs.

    Anul universitar 2025-2026 = de la 1 oct 2025 pana la 30 sep 2026
    (expira pe 1 oct 2026).

    Exemple (pentru today varianta):
      - today = 2026-03-15  ->  2026-10-01 (suntem in anul universitar 2025-2026)
      - today = 2026-09-30  ->  2026-10-01 (suntem inca in anul universitar 2025-2026)
      - today = 2026-10-01  ->  2027-10-01 (anul universitar nou tocmai a inceput)
      - today = 2026-12-15  ->  2027-10-01 (suntem in anul universitar 2026-2027)

    Logica:
      Daca azi e inainte de 1 octombrie => expirarea e 1 oct anul curent.
      Daca azi e dupa sau exact 1 octombrie => expirarea e 1 oct anul viitor.
    """
    if today is None:
        today = date.today()

    boundary_this_year = date(
        today.year,
        ACADEMIC_YEAR_START_MONTH,
        ACADEMIC_YEAR_START_DAY,
    )

    if today < boundary_this_year:
        return boundary_this_year
    else:
        return date(
            today.year + 1,
            ACADEMIC_YEAR_START_MONTH,
            ACADEMIC_YEAR_START_DAY,
        )


# ---------------------------------------------------------------------------
# Functii helper - status verificare per user
# ---------------------------------------------------------------------------

def _release_expired_credentials(db: Session, user_id: int) -> int:
    """
    Marcheaza ca 'expired' credentialele active care au depasit data
    valid_until. Apelat lazy la fiecare get_verification_status, ca starea
    sa fie mereu consistenta fara cron job.

    Returneaza numarul de credentiale marcate expired.
    """
    result = db.execute(
        text("""
            UPDATE user_credentials
            SET status = 'expired'
            WHERE user_id = :uid
              AND status = 'active'
              AND valid_until < NOW()
            RETURNING id
        """),
        {"uid": user_id},
    ).fetchall()
    return len(result)


def is_identity_verified(db: Session, user_id: int) -> bool:
    """
    Verifica daca userul are un credential 'identity_verified' activ
    (nu expirat). Aceasta este sursa unica de adevar pentru "datele lui
    sunt frozen".

    Apeleaza intai _release_expired_credentials pentru a invalida lazy
    credentialele a caror valid_until a trecut.
    """
    _release_expired_credentials(db, user_id)

    row = db.execute(
        text("""
            SELECT 1
            FROM user_credentials
            WHERE user_id = :uid
              AND credential_type = :ctype
              AND status = 'active'
              AND valid_until > NOW()
            LIMIT 1
        """),
        {"uid": user_id, "ctype": IDENTITY_VERIFIED_CREDENTIAL},
    ).first()
    return row is not None


def get_verification_status(db: Session, user_id: int) -> dict:
    """
    Returneaza statusul complet de verificare al userului, pentru frontend.

    Format raspuns:
    {
      "is_verified": bool,
      "verified_at": "2026-03-15" | None,
      "expires_at":  "2026-10-01" | None,
      "days_until_expiry": int | None,
      "frozen_fields": ["cnp", "first_name", ...] | [],
      "academic_year": "2025-2026" | None,
      "message": "Datele dvs. sunt frozen pana la 1 oct 2026." | None
    }
    """
    _release_expired_credentials(db, user_id)

    cred = db.execute(
        text("""
            SELECT issued_at, valid_until
            FROM user_credentials
            WHERE user_id = :uid
              AND credential_type = :ctype
              AND status = 'active'
              AND valid_until > NOW()
            ORDER BY issued_at DESC
            LIMIT 1
        """),
        {"uid": user_id, "ctype": IDENTITY_VERIFIED_CREDENTIAL},
    ).mappings().first()

    if not cred:
        return {
            "is_verified": False,
            "verified_at": None,
            "expires_at": None,
            "days_until_expiry": None,
            "frozen_fields": [],
            "academic_year": None,
            "message": "Identitatea nu a fost verificata. "
                       "Toate campurile profilului pot fi modificate.",
        }

    issued_at = cred["issued_at"]
    valid_until = cred["valid_until"]
    today = date.today()
    expires_date = valid_until.date() if isinstance(valid_until, datetime) else valid_until
    days_remaining = (expires_date - today).days

    # Format "2025-2026" pentru anul universitar
    if expires_date.month == ACADEMIC_YEAR_START_MONTH:
        year_start = expires_date.year - 1
    else:
        year_start = expires_date.year
    academic_year = f"{year_start}-{year_start + 1}"

    return {
        "is_verified": True,
        "verified_at": issued_at.date().isoformat() if isinstance(issued_at, datetime)
                       else (issued_at.isoformat() if issued_at else None),
        "expires_at": expires_date.isoformat(),
        "days_until_expiry": days_remaining,
        "frozen_fields": sorted(FROZEN_FIELDS_WHEN_VERIFIED),
        "academic_year": academic_year,
        "message": (
            f"Datele dvs. au fost validate de un agent universitar si sunt "
            f"protejate (frozen) pana la {expires_date.strftime('%d %B %Y')}. "
            f"Pentru modificari mai devreme, contactati agentul universitatii."
        ),
    }


def check_frozen_field_changes(
    db: Session,
    user_id: int,
    current_user_row,
    payload: dict,
) -> list[str]:
    """
    Compara campurile din payload cu cele actuale din DB si returneaza
    lista de campuri FROZEN care s-ar schimba. Returneaza lista goala daca
    user-ul nu e verificat sau daca nu modifica niciun camp protejat.

    Folosit in update_me pentru a decide daca raise 403.
    """
    if not is_identity_verified(db, user_id):
        return []

    changes = []
    for field in FROZEN_FIELDS_WHEN_VERIFIED:
        if field not in payload:
            continue
        new_value = payload[field]
        if new_value is None:
            continue  # field absent in payload, no change attempted
        try:
            old_value = current_user_row[field]
        except (KeyError, TypeError):
            old_value = getattr(current_user_row, field, None)
        # Normalize types (date vs str, int vs str)
        old_str = str(old_value) if old_value is not None else None
        new_str = str(new_value) if new_value is not None else None
        if old_str != new_str:
            changes.append(field)

    return changes

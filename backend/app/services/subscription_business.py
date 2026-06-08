"""
Logica de business pentru abonamente CFR.

Acest modul concentreaza in helpere reutilizabile:
  - Calculul pretului (formula pe distanta + reducere conditionata)
  - Verificarea reducerii de student CFR (DOAR pe ruta home_station <-> universitate,
    conform OUG 11/2024 - aceeasi regula ca la bilete in _personal_route_status)
  - Cautarea unui abonament activ care acopera o ruta (folosit la cumpararea
    biletelor pentru a oferi gratuitate automata)
  - Calculul refund-ului pro-rata (CFR-style) la anulare

Toate functiile primesc db: Session si NU fac commit (routerul decide).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constante de business
# ---------------------------------------------------------------------------

# Tipuri valide de abonament (CHECK constraint in schema)
SUBSCRIPTION_TYPES = {"monthly", "annual"}

# Durata in zile per tip
DURATION_DAYS = {
    "monthly": 30,
    "annual": 365,
}

# Reducere CFR pentru studenti, DOAR pe ruta home_station <-> universitate.
# Conform OUG 11/2024: reducere 90% pe ruta personala student.
# Aliniat cu STUDENT_DISCOUNT_PERCENT din tickets.py (consistenta cu logica de bilete).
STUDENT_DISCOUNT_PCT = 90.0

# Formula pret abonament:
#   base = (distanta_km * COEF_PER_KM + BASE_FEE) * MULTIPLIER_TYPE
# unde:
#   COEF_PER_KM = 0.5 RON/km (acopera circa 30 calatorii lunare)
#   BASE_FEE = 50 RON (taxa minima procesare)
#   MULTIPLIER_TYPE: monthly=1, annual=10 (2 luni gratis la anual)
COEF_PER_KM = 0.5
BASE_FEE = 50.0
TYPE_MULTIPLIER = {
    "monthly": 1.0,
    "annual": 10.0,
}


# ---------------------------------------------------------------------------
# Helper: e ruta de student (home <-> universitate)?
# ---------------------------------------------------------------------------

def is_student_route_for_user(
    db: Session,
    user_id: int,
    from_station_id: int,
    to_station_id: int,
) -> dict:
    """
    Verifica daca ruta data corespunde rutei personale a userului
    (home_station <-> universitate). Refoloseste EXACT aceeasi logica
    din tickets._personal_route_status pentru consistenta.

    Returneaza:
      {
        "is_match": bool,              # True daca user e student verificat
                                       # SI ruta = home <-> univ
        "reason": str,                 # explicatie pentru UI
        "home_station_id": int | None,
        "university_station_id": int | None,
        "is_student_verified": bool,
      }
    """
    # 1. Aducem home + universitate
    row = db.execute(
        text("""
            SELECT
                u.home_station_id,
                u.university_id,
                uni.main_station_id AS university_station_id,
                EXISTS (
                    SELECT 1 FROM user_credentials uc
                    WHERE uc.user_id = u.user_id
                      AND uc.credential_type IN ('student_verified', 'student')
                      AND uc.status = 'active'
                      AND uc.valid_until > NOW()
                ) AS is_student_verified
            FROM users u
            LEFT JOIN universities uni ON uni.university_id = u.university_id
            WHERE u.user_id = :uid
        """),
        {"uid": user_id},
    ).mappings().first()

    if not row:
        return {
            "is_match": False,
            "reason": "User inexistent",
            "home_station_id": None,
            "university_station_id": None,
            "is_student_verified": False,
        }

    home_id = row["home_station_id"]
    univ_id = row["university_station_id"]
    is_student = bool(row["is_student_verified"])

    if not is_student:
        return {
            "is_match": False,
            "reason": "Userul nu este student verificat",
            "home_station_id": home_id,
            "university_station_id": univ_id,
            "is_student_verified": False,
        }

    if home_id is None or univ_id is None:
        return {
            "is_match": False,
            "reason": "Statia de domiciliu sau universitatea nu este setata",
            "home_station_id": home_id,
            "university_station_id": univ_id,
            "is_student_verified": True,
        }

    # Match indiferent de directie (home->univ sau univ->home)
    expected_a = {home_id, univ_id}
    actual = {from_station_id, to_station_id}
    is_match = expected_a == actual

    return {
        "is_match": is_match,
        "reason": (
            "Ruta corespunde rutei personale home<->universitate (reducere 90% OUG 11/2024)"
            if is_match
            else "Ruta NU este home<->universitate (pret intreg)"
        ),
        "home_station_id": home_id,
        "university_station_id": univ_id,
        "is_student_verified": True,
    }


# ---------------------------------------------------------------------------
# Helper: calcul pret abonament cu reducere conditionata
# ---------------------------------------------------------------------------

def compute_subscription_price(
    distance_km: float,
    subscription_type: str,
    is_student_route: bool,
) -> tuple[float, float, float]:
    """
    Calculeaza pretul abonamentului.

    Returneaza (base_price, discount_amount, final_price).

    Formula:
      base = (distance_km * COEF_PER_KM + BASE_FEE) * MULTIPLIER_TYPE
      discount = base * 90% (daca is_student_route)
                 0       (altfel)
      final = base - discount
    """
    if subscription_type not in SUBSCRIPTION_TYPES:
        raise ValueError(f"Tip abonament invalid: {subscription_type}")
    if distance_km < 0:
        raise ValueError("Distance must be non-negative")

    multiplier = TYPE_MULTIPLIER[subscription_type]
    base = (distance_km * COEF_PER_KM + BASE_FEE) * multiplier

    if is_student_route:
        discount = base * (STUDENT_DISCOUNT_PCT / 100.0)
    else:
        discount = 0.0

    final_price = max(0.0, base - discount)
    return round(base, 2), round(discount, 2), round(final_price, 2)


# ---------------------------------------------------------------------------
# Helper: distanta pe ruta (din routes table)
# ---------------------------------------------------------------------------

def get_route_distance_km(
    db: Session,
    from_station_id: int,
    to_station_id: int,
) -> Optional[float]:
    """
    Returneaza distanta in km pentru o ruta directa intre 2 statii.
    Cauta in routes table (origin->dest sau dest->origin).
    Returneaza None daca nu gaseste.
    """
    row = db.execute(
        text("""
            SELECT total_distance_km
            FROM routes
            WHERE (origin_station_id = :a AND destination_station_id = :b)
               OR (origin_station_id = :b AND destination_station_id = :a)
            ORDER BY total_distance_km
            LIMIT 1
        """),
        {"a": from_station_id, "b": to_station_id},
    ).first()

    if row and row[0]:
        return float(row[0])

    # Fallback: estimare crude din statiile geo (pentru demo, daca nu exista route)
    # Folosim formula haversinian doar daca avem coordonate
    geo = db.execute(
        text("""
            SELECT
                s1.latitude AS lat1, s1.longitude AS lon1,
                s2.latitude AS lat2, s2.longitude AS lon2
            FROM stations s1, stations s2
            WHERE s1.station_id = :a AND s2.station_id = :b
        """),
        {"a": from_station_id, "b": to_station_id},
    ).mappings().first()

    if geo and all(geo[k] is not None for k in ("lat1", "lon1", "lat2", "lon2")):
        import math
        R = 6371.0
        lat1, lon1 = math.radians(float(geo["lat1"])), math.radians(float(geo["lon1"]))
        lat2, lon2 = math.radians(float(geo["lat2"])), math.radians(float(geo["lon2"]))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return round(2 * R * math.asin(math.sqrt(a)), 2)

    return None


# ---------------------------------------------------------------------------
# Helper: anti-overlap pe ruta
# ---------------------------------------------------------------------------

def check_subscription_overlap(
    db: Session,
    user_id: int,
    from_station_id: int,
    to_station_id: int,
) -> None:
    """
    Verifica daca user-ul are deja un abonament 'active' pe aceeasi ruta
    (in orice directie). Raise HTTPException 409 daca da.
    """
    existing = db.execute(
        text("""
            SELECT
                subscription_id, subscription_type, valid_from, valid_until,
                from_station_id, to_station_id
            FROM subscriptions
            WHERE user_id = :uid
              AND status = 'active'
              AND subscription_scope = 'route'
              AND valid_until >= CURRENT_DATE
              AND (
                   (from_station_id = :a AND to_station_id = :b)
                OR (from_station_id = :b AND to_station_id = :a)
              )
            ORDER BY valid_until DESC
            LIMIT 1
        """),
        {"uid": user_id, "a": from_station_id, "b": to_station_id},
    ).mappings().first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "subscription_overlap",
                "message": (
                    f"Aveti deja un abonament {existing['subscription_type']} "
                    f"activ pe aceasta ruta, valabil pana pe "
                    f"{existing['valid_until'].isoformat()}. "
                    f"Anulati abonamentul curent inainte de a cumpara altul."
                ),
                "conflicting_subscription_id": existing["subscription_id"],
                "valid_until": existing["valid_until"].isoformat(),
            },
        )


# ---------------------------------------------------------------------------
# Helper: gasire abonament activ care acopera o ruta (folosit la buy_ticket)
# ---------------------------------------------------------------------------

def find_active_subscription_for_route(
    db: Session,
    user_id: int,
    from_station_id: int,
    to_station_id: int,
    travel_date: date,
) -> Optional[dict]:
    """
    Cauta un abonament activ al userului care acopera ruta data pentru
    data calatoriei. Returneaza dict cu detalii sau None.
    """
    row = db.execute(
        text("""
            SELECT
                subscription_id, subscription_type, valid_from, valid_until
            FROM subscriptions
            WHERE user_id = :uid
              AND status = 'active'
              AND subscription_scope = 'route'
              AND valid_from <= :td
              AND valid_until >= :td
              AND (
                   (from_station_id = :a AND to_station_id = :b)
                OR (from_station_id = :b AND to_station_id = :a)
              )
            ORDER BY valid_until DESC
            LIMIT 1
        """),
        {"uid": user_id, "a": from_station_id, "b": to_station_id, "td": travel_date},
    ).mappings().first()

    if not row:
        return None

    return {
        "subscription_id": row["subscription_id"],
        "subscription_type": row["subscription_type"],
        "valid_from": row["valid_from"].isoformat(),
        "valid_until": row["valid_until"].isoformat(),
    }


# ---------------------------------------------------------------------------
# Helper: refund pro-rata (CFR-style) la anularea unui abonament
# ---------------------------------------------------------------------------

def compute_subscription_refund(
    price_paid: float,
    valid_from: date,
    valid_until: date,
    cancel_date: Optional[date] = None,
) -> tuple[float, str]:
    """
    Calculeaza refund-ul pro-rata pentru anularea unui abonament.

    Reguli CFR (simplificat pentru licenta):
      - Anulare INAINTE de valid_from (abonament viitor) => 100% refund
      - Anulare in primele 50% din durata utila         => 50% refund pro-rata
        (pentru zilele neutilizate)
      - Anulare dupa 50% din durata                     =>  0% refund

    Returneaza (refund_amount, tier_name).
    """
    if cancel_date is None:
        cancel_date = date.today()

    # Daca abonamentul nu a inceput inca, refund total
    if cancel_date < valid_from:
        return (round(price_paid, 2), "full_not_started")

    # Daca abonamentul a expirat deja, nimic de refund
    if cancel_date >= valid_until:
        return (0.0, "expired")

    total_days = (valid_until - valid_from).days
    if total_days <= 0:
        return (0.0, "zero_duration")

    days_used = (cancel_date - valid_from).days
    pct_used = days_used / total_days

    if pct_used >= 0.5:
        # Mai mult de jumatate folosit -> 0%
        return (0.0, "more_than_half_used")

    # Refund pe zilele neutilizate, ponderat 50% (penalty CFR pentru anulare timpurie)
    days_unused = total_days - days_used
    refund = price_paid * (days_unused / total_days) * 0.5
    return (round(refund, 2), "partial_pro_rata")


# ---------------------------------------------------------------------------
# Helper: cleanup lazy abonamente expirate
# ---------------------------------------------------------------------------

def expire_old_subscriptions(db: Session) -> int:
    """Apel la functia SQL pentru a marca abonamentele expirate."""
    result = db.execute(text("SELECT expire_old_subscriptions()")).scalar()
    return int(result or 0)

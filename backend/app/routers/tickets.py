
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.roles import ROLE_PASSENGER, ROLE_TRAIN_VERIFIER, has_role, normalize_role
from app.core.security import decode_token
from app.services.ticket_business import (
    check_overlap,
    compute_refund,
    confirm_seats_for_ticket,
    get_train_departure_datetime,
    release_ticket_seats,
)

router = APIRouter(tags=["tickets"])
# DB session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# Auth helper
def _extract_user_from_token(authorization: Optional[str], db: Session) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", "0"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    row = db.execute(
        text(
            """
            SELECT user_id, first_name, last_name, email, role, is_active
            FROM users
            WHERE user_id = :uid
            """
        ),
        {"uid": user_id},
    ).mappings().first()

    if not row or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    user = dict(row)
    user["role"] = normalize_role(user["role"])
    return user
# Pydantic models
class BuyTicketRequest(BaseModel):
    train_id: int = Field(..., ge=1)
    departure_station_id: int = Field(..., ge=1)
    arrival_station_id: int = Field(..., ge=1)
    travel_date: str  # YYYY-MM-DD
    ticket_type: str = Field(default="single")  # single | return
    # Lista de seat_id-uri rezervate prin /seats/hold inainte de cumparare.
    # Daca e None sau goala, cumparam fara loc specific (legacy).
    seat_ids: Optional[list[int]] = None

class ValidateTicketRequest(BaseModel):
    token: str
    device_id: Optional[str] = None
    location_name: Optional[str] = None

class ValidateTicketResponse(BaseModel):
    result: str
    message: str
    passenger_name: Optional[str] = None
    ticket_type: Optional[str] = None
    valid_until: Optional[str] = None
# ============================================================================
# Pricing — lookup in tabela tariff_brackets (modeleaza Tariful 100 CFR)
# ============================================================================
# Reducere conform OUG 11/2024 + Legea 245/2024:
#  - studenti < 30 ani, clasa II, transport feroviar intern, numar nelimitat
STUDENT_DISCOUNT_PERCENT = 90.0
# Doctoranzi conform HG 845/2009 (forma cu frecventa)
DOCTORAL_DISCOUNT_PERCENT = 50.0
# Bilet dus-intors = 2x tariful single (CFR nu ofera reducere pe return)
RETURN_MULTIPLIER = 2.0


def _lookup_base_price(
    db: Session, distance_km: float, train_category: str, train_class: int = 2
) -> float:
    """
    Lookup in tariff_brackets pentru tariful clasa indicata.
    Returneaza tariful single-trip ca float RON.
    """
    # Normalizam categoria: schema accepta 'R'/'IR'/'IC'/'IR-N'
    cat_map = {
        "regio": "R", "r": "R",
        "interregio": "IR", "ir": "IR",
        "intercity": "IC", "ic": "IC",
        "express": "IR", "high_speed": "IC",
    }
    cat = cat_map.get((train_category or "IR").lower(), "IR")

    row = db.execute(
        text(
            """
            SELECT price_ron
            FROM tariff_brackets
            WHERE train_category = :cat
              AND train_class    = :cls
              AND km_from <= :km AND km_to >= :km
              AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
            LIMIT 1
            """
        ),
        {"cat": cat, "cls": train_class, "km": int(distance_km)},
    ).first()

    if row:
        return float(row[0])

    # Fallback: daca nu gasim bracket, formula liniara
    base = 17 + distance_km * 0.17
    if cat == "IR":
        base += 15 + distance_km * 0.025
    elif cat == "IC":
        base += 25 + distance_km * 0.04
    if train_class == 1:
        base *= 1.35
    return round(base, 2)


def _user_discount(db: Session, user_id: int) -> float:
    """
    Returneaza discountul aplicabil (in procente) pentru user.
    Prioritizeaza student_verified > doctoral > 0.
    """
    cred_row = db.execute(
        text(
            """
            SELECT credential_type FROM user_credentials
            WHERE user_id = :uid
              AND status = 'active'
              AND valid_until > CURRENT_TIMESTAMP
              AND credential_type IN ('student', 'student_verified', 'doctoral_verified', 'pupil', 'elev_verified')
            ORDER BY
              CASE credential_type
                WHEN 'student_verified'   THEN 1
                WHEN 'student'            THEN 2
                WHEN 'elev_verified'      THEN 3
                WHEN 'pupil'              THEN 4
                WHEN 'doctoral_verified'  THEN 5
              END
            LIMIT 1
            """
        ),
        {"uid": user_id},
    ).first()

    if not cred_row:
        return 0.0

    cred_type = cred_row[0]
    if cred_type in ("student", "student_verified", "elev_verified", "pupil"):
        return STUDENT_DISCOUNT_PERCENT
    if cred_type == "doctoral_verified":
        return DOCTORAL_DISCOUNT_PERCENT
    return 0.0


def _personal_route_status(
    db: Session,
    user_id: int,
    dep_station_id: int,
    arr_station_id: int,
) -> dict:
    """
    Verifica daca (dep, arr) coincide cu ruta personala a studentului,
    definita ca perechea (home_station, university.main_station) — in
    orice sens (dus sau intors).

    Conform OUG 11/2024, reducerea de 90% pentru studenti se aplica pe
    "transportul intern feroviar intre localitatea de domiciliu si cea
    a institutiei de invatamint". Implementam asta verificand statiile
    declarate de utilizator.

    Returneaza un dict cu cheile:
        is_personal_route: bool   — True daca perechea match-uieste
        reason: str               — motiv lizibil pentru UI
        home_station_id: int|None — pentru afisare/debug
        university_station_id: int|None
    """
    row = db.execute(
        text(
            """
            SELECT
                u.home_station_id,
                un.main_station_id AS university_station_id,
                hs.name AS home_station_name,
                us.name AS university_station_name
            FROM users u
            LEFT JOIN universities un ON un.university_id = u.university_id
            LEFT JOIN stations hs ON hs.station_id = u.home_station_id
            LEFT JOIN stations us ON us.station_id = un.main_station_id
            WHERE u.user_id = :uid
            """
        ),
        {"uid": user_id},
    ).mappings().first()

    if not row:
        return {
            "is_personal_route": False,
            "reason": "Utilizator inexistent",
            "home_station_id": None,
            "university_station_id": None,
        }

    home_id = row["home_station_id"]
    uni_id = row["university_station_id"]

    if home_id is None:
        return {
            "is_personal_route": False,
            "reason": "Statia de domiciliu nu este declarata. Adaug-o din profil pentru a beneficia de reducere.",
            "home_station_id": None,
            "university_station_id": uni_id,
        }

    if uni_id is None:
        return {
            "is_personal_route": False,
            "reason": "Centrul universitar nu are statie principala asociata. Contacteaza agentul universitar.",
            "home_station_id": home_id,
            "university_station_id": None,
        }

    pair = {dep_station_id, arr_station_id}
    expected = {home_id, uni_id}

    if pair == expected:
        return {
            "is_personal_route": True,
            "reason": f"Ruta personala ({row['home_station_name']} <-> {row['university_station_name']}). Reducerea de student se aplica.",
            "home_station_id": home_id,
            "university_station_id": uni_id,
        }

    return {
        "is_personal_route": False,
        "reason": f"Ruta nu corespunde traseului tau personal ({row['home_station_name']} <-> {row['university_station_name']}). Tarif intreg conform OUG 11/2024.",
        "home_station_id": home_id,
        "university_station_id": uni_id,
    }


def _compute_price(
    db: Session,
    user_id: int,
    ticket_type: str,
    train_id: int,
    departure_station_id: int,
    arrival_station_id: int,
    train_class: int = 2,
) -> tuple[float, float, float, float, dict]:
    """
    Returns (final_price, discount_percent, base_price_single, distance_km,
             route_status).

    Distanta = diferenta de distance_from_origin_km intre stop-ul de plecare
    si stop-ul de sosire pe ruta trenului (din tabela route_stops).
    Daca pasagerul cere o relatie pe care trenul nu o acopera, fallback la
    total_distance_km pentru a nu bloca cumpararea.

    Discountul de student se aplica DOAR daca ruta cumparata coincide cu
    ruta personala a utilizatorului (home_station <-> main_station al
    universitatii), conform OUG 11/2024. Pe alte rute se aplica tariful
    intreg, indiferent de credentialele utilizatorului.
    """
    train_row = db.execute(
        text(
            """
            SELECT t.train_id, t.train_type, t.route_id, r.total_distance_km
            FROM trains t
            JOIN routes r ON r.route_id = t.route_id
            WHERE t.train_id = :tid
            """
        ),
        {"tid": train_id},
    ).first()
    if not train_row:
        raise HTTPException(status_code=404, detail="Trenul nu exista")

    _, train_type, route_id, total_km = train_row

    # Distanta efectiva intre cele doua statii pe ruta trenului
    seg = db.execute(
        text(
            """
            SELECT
                MIN(CASE WHEN station_id = :dep THEN distance_from_origin_km END) AS dep_km,
                MIN(CASE WHEN station_id = :arr THEN distance_from_origin_km END) AS arr_km,
                MIN(CASE WHEN station_id = :dep THEN stop_order END) AS dep_order,
                MIN(CASE WHEN station_id = :arr THEN stop_order END) AS arr_order
            FROM route_stops
            WHERE route_id = :rid AND station_id IN (:dep, :arr)
            """
        ),
        {"rid": route_id, "dep": departure_station_id, "arr": arrival_station_id},
    ).first()

    if seg and seg.dep_km is not None and seg.arr_km is not None:
        distance_km = abs(float(seg.arr_km) - float(seg.dep_km))
        if distance_km < 1:
            distance_km = float(total_km or 50.0)
    else:
        distance_km = float(total_km or 50.0)

    base_single = _lookup_base_price(db, distance_km, train_type, train_class)
    multiplier = RETURN_MULTIPLIER if ticket_type == "return" else 1.0
    base_total = round(base_single * multiplier, 2)

    # Discountul de utilizator (student / doctorand) se aplica DOAR pe ruta
    # personala declarata. Pe alte rute -> tarif intreg.
    route_status = _personal_route_status(
        db, user_id, departure_station_id, arrival_station_id
    )
    if route_status["is_personal_route"]:
        discount = _user_discount(db, user_id)
    else:
        discount = 0.0

    final_price = round(base_total * (1 - discount / 100), 2)

    return final_price, discount, base_total, distance_km, route_status
# Endpoints


@router.get("/stations/search")
def search_stations(
    q: str = "",
    limit: int = 15,
    db: Session = Depends(get_db),
):
    """
    Autocomplete pentru statii.
    Query: name sau city ILIKE '%q%'. Sortare: nume, alfabetic.
    """
    q = (q or "").strip()
    if len(q) < 2:
        # returnez statii populare (cele mai multe trenuri trecand prin ele)
        rows = db.execute(
            text(
                """
                SELECT s.station_id, s.name, s.city, s.code, COUNT(rs.route_stop_id) AS popularity
                FROM stations s
                LEFT JOIN route_stops rs ON rs.station_id = s.station_id
                WHERE s.is_active = TRUE
                GROUP BY s.station_id
                ORDER BY popularity DESC, s.name ASC
                LIMIT :lim
                """
            ),
            {"lim": limit},
        ).mappings().all()
    else:
        like = f"%{q}%"
        rows = db.execute(
            text(
                """
                SELECT s.station_id, s.name, s.city, s.code, COUNT(rs.route_stop_id) AS popularity
                FROM stations s
                LEFT JOIN route_stops rs ON rs.station_id = s.station_id
                WHERE s.is_active = TRUE
                  AND (unaccent(s.name) ILIKE unaccent(:q) OR unaccent(s.city) ILIKE unaccent(:q) OR s.code ILIKE :q)
                GROUP BY s.station_id
                ORDER BY popularity DESC, s.name ASC
                LIMIT :lim
                """
            ),
            {"q": like, "lim": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/trains/search")
def search_trains(
    from_station_id: int,
    to_station_id: int,
    travel_date: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Cauta trenurile care leaga 2 statii pe acelasi tren (directe).
    Conditia: ambele statii sunt opriri pe aceeasi ruta, ordinea corecta.
    """
    if from_station_id == to_station_id:
        raise HTTPException(status_code=400, detail="Statiile trebuie sa fie diferite")

    # NOTA: route_stops poate contine stop-uri duplicate pe aceeasi ruta
    # (anomalie a datelor CFR — ~2100 rinduri redundante in importul oficial,
    # ex. ruta 612 are "Bucuresti Nord Gr.A" atit pe stop 54 cit si pe 55).
    # Folosim DISTINCT ON (train_id) ca sa intoarcem fiecare tren o singura
    # data, pastrand cea mai timpurie pereche (rs_from, rs_to).
    # PostgreSQL cere ca ORDER BY sa inceapa cu cheia de DISTINCT, asa ca
    # facem sortarea finala dupa departure_time in Python.
    raw_rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (t.train_id)
                t.train_id, t.train_number, t.train_type,
                op.name AS operator_name, op.code AS operator_code,
                r.route_id, r.route_name,
                s_from.station_id AS from_id, s_from.name AS from_name, s_from.code AS from_code,
                s_to.station_id   AS to_id,   s_to.name   AS to_name,   s_to.code   AS to_code,
                rs_from.stop_order AS from_order,
                rs_to.stop_order   AS to_order,
                rs_from.departure_time AS departure_time,
                rs_to.arrival_time     AS arrival_time,
                (rs_to.distance_from_origin_km - rs_from.distance_from_origin_km) AS distance_km
            FROM trains t
            JOIN routes r          ON r.route_id = t.route_id
            JOIN railway_operators op ON op.operator_id = t.operator_id
            JOIN route_stops rs_from ON rs_from.route_id = r.route_id AND rs_from.station_id = :from_id
            JOIN route_stops rs_to   ON rs_to.route_id   = r.route_id AND rs_to.station_id   = :to_id
            JOIN stations s_from ON s_from.station_id = rs_from.station_id
            JOIN stations s_to   ON s_to.station_id   = rs_to.station_id
            WHERE t.is_active = TRUE
              AND rs_from.stop_order < rs_to.stop_order
            ORDER BY t.train_id, rs_from.stop_order, rs_to.stop_order
            """
        ),
        {"from_id": from_station_id, "to_id": to_station_id},
    ).mappings().all()

    from datetime import time as _time
    rows = sorted(
        raw_rows,
        key=lambda r: (r["departure_time"] or _time.max, r["train_number"] or ""),
    )[:50]

    return [
        {
            **dict(r),
            "departure_time": str(r["departure_time"]) if r["departure_time"] else None,
            "arrival_time": str(r["arrival_time"]) if r["arrival_time"] else None,
            "distance_km": float(r["distance_km"]) if r["distance_km"] else None,
        }
        for r in rows
    ]


@router.post("/tickets/quote")
def quote_ticket(
    payload: BuyTicketRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Calculeaza pretul biletului FARA a-l cumpara.
    Foloseste tariff_brackets + discountul utilizatorului curent.
    Util pentru UI: arata pretul inainte de confirmare.
    """
    user = _extract_user_from_token(authorization, db)
    price, discount, base_price, distance_km, route_status = _compute_price(
        db,
        user["user_id"],
        payload.ticket_type,
        payload.train_id,
        payload.departure_station_id,
        payload.arrival_station_id,
    )
    return {
        "base_price": base_price,
        "discount_percent": discount,
        "final_price": price,
        "distance_km": distance_km,
        "ticket_type": payload.ticket_type,
        "savings": round(base_price - price, 2),
        "is_personal_route": route_status["is_personal_route"],
        "route_reason": route_status["reason"],
        "home_station_id": route_status["home_station_id"],
        "university_station_id": route_status["university_station_id"],
    }

@router.get("/tickets/catalog")
def list_catalog(db: Session = Depends(get_db)):
    """Listeaza rute + trenuri disponibile pentru cumparare."""
    rows = db.execute(
        text(
            """
            SELECT
                t.train_id, t.train_number, t.train_type, t.capacity_seats,
                r.route_id, r.route_name,
                op.name AS operator_name,
                s1.station_id AS departure_id, s1.name AS departure_name, s1.code AS departure_code,
                s2.station_id AS arrival_id,   s2.name AS arrival_name,   s2.code AS arrival_code,
                r.total_distance_km
            FROM trains t
            JOIN routes r              ON r.route_id = t.route_id
            JOIN railway_operators op  ON op.operator_id = t.operator_id
            JOIN stations s1           ON s1.station_id = r.origin_station_id
            JOIN stations s2           ON s2.station_id = r.destination_station_id
            WHERE t.is_active = TRUE
            ORDER BY r.route_name
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]

@router.post("/tickets/buy")
def buy_ticket(
    payload: BuyTicketRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Cumpara bilet + creeaza travel_entitlement + qr_token."""
    user = _extract_user_from_token(authorization, db)
    if not has_role(user["role"], ROLE_PASSENGER):
        raise HTTPException(status_code=403, detail="Doar pasagerii pot cumpara bilete")

    # Validare data calatorie
    try:
        travel_date = datetime.strptime(payload.travel_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="travel_date trebuie sa fie YYYY-MM-DD")

    if travel_date < datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="Data calatoriei nu poate fi in trecut")

    if payload.departure_station_id == payload.arrival_station_id:
        raise HTTPException(status_code=400, detail="Statia de plecare nu poate fi aceeasi cu sosirea")

    # Anti-overlap: nu permitem 2 bilete active in intervale orare suprapuse
    # pentru acelasi user. Raise 409 cu detalii despre conflict.
    check_overlap(db, user["user_id"], payload.train_id, travel_date)

    # Validare ca trenul + rutele exista
    train = db.execute(
        text("SELECT train_id, route_id FROM trains WHERE train_id = :tid AND is_active = TRUE"),
        {"tid": payload.train_id},
    ).first()
    if not train:
        raise HTTPException(status_code=404, detail="Trenul nu exista sau este inactiv")

    price, discount, base_price, distance_km, route_status = _compute_price(
        db,
        user["user_id"],
        payload.ticket_type,
        payload.train_id,
        payload.departure_station_id,
        payload.arrival_station_id,
    )

    try:
        # 1. Insereaza biletul
        ticket = db.execute(
            text(
                """
                INSERT INTO tickets (
                    user_id, train_id, departure_station_id, arrival_station_id,
                    travel_date, ticket_type, ticket_status, price, discount_applied
                )
                VALUES (
                    :uid, :tid, :dep_id, :arr_id,
                    :travel_date, :ticket_type, 'active', :price, :discount
                )
                RETURNING ticket_id, travel_date, ticket_type, price
                """
            ),
            {
                "uid": user["user_id"],
                "tid": payload.train_id,
                "dep_id": payload.departure_station_id,
                "arr_id": payload.arrival_station_id,
                "travel_date": travel_date,
                "ticket_type": payload.ticket_type,
                "price": price,
                "discount": discount,
            },
        ).mappings().first()

        # 2. Travel entitlement (bilet valabil pana la sfarsitul zilei calatoriei)
        valid_until = datetime.combine(travel_date, datetime.max.time())
        entitlement = db.execute(
            text(
                """
                INSERT INTO travel_entitlements (
                    user_id, source_type, ticket_id, valid_from, valid_until, status
                )
                VALUES (
                    :uid, 'ticket', :tid, CURRENT_TIMESTAMP, :valid_until, 'active'
                )
                RETURNING entitlement_id
                """
            ),
            {
                "uid": user["user_id"],
                "tid": ticket["ticket_id"],
                "valid_until": valid_until,
            },
        ).mappings().first()

        # 3. QR token single-use
        token_value = secrets.token_urlsafe(32)
        import hashlib
        token_hash = hashlib.sha256(token_value.encode()).hexdigest()

        qr = db.execute(
            text(
                """
                INSERT INTO qr_tokens (
                    entitlement_id, token_value, token_hash, expires_at, status
                )
                VALUES (
                    :ent_id, :token, :token_hash, :expires_at, 'active'
                )
                RETURNING qr_token_id, token_value, expires_at
                """
            ),
            {
                "ent_id": entitlement["entitlement_id"],
                "token": token_value,
                "token_hash": token_hash,
                "expires_at": valid_until,
            },
        ).mappings().first()

        # 4. Confirma locurile rezervate prin /seats/hold (daca exista).
        # Daca hold-ul a expirat sau locul a fost vandut intre timp, raise 409
        # iar tranzactia se anuleaza (db.rollback in exception handler).
        if payload.seat_ids:
            confirm_seats_for_ticket(
                db,
                ticket_id=ticket["ticket_id"],
                user_id=user["user_id"],
                seat_ids=payload.seat_ids,
                travel_date=travel_date,
            )

        db.commit()

        return {
            "ticket_id": ticket["ticket_id"],
            "ticket_type": ticket["ticket_type"],
            "travel_date": str(ticket["travel_date"]),
            "price": float(ticket["price"]),
            "discount_applied": discount,
            "is_personal_route": route_status["is_personal_route"],
            "route_reason": route_status["reason"],
            "qr_token": qr["token_value"],
            "qr_expires_at": (
                qr["expires_at"].isoformat(timespec="seconds") + "Z"
                if qr.get("expires_at") else None
            ),
            "message": "Bilet cumparat cu succes. Prezinta QR-ul controlorului.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Eroare la cumparare: {exc}")

@router.get("/tickets/my")
def list_my_tickets(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Listeaza biletele utilizatorului curent."""
    user = _extract_user_from_token(authorization, db)
    rows = db.execute(
        text(
            """
            SELECT
                t.ticket_id, t.ticket_type, t.ticket_status, t.travel_date,
                t.price, t.discount_applied, t.purchase_time,
                s1.name AS departure_name, s1.code AS departure_code,
                s2.name AS arrival_name,   s2.code AS arrival_code,
                tr.train_number, tr.train_type
            FROM tickets t
            JOIN stations s1 ON s1.station_id = t.departure_station_id
            JOIN stations s2 ON s2.station_id = t.arrival_station_id
            JOIN trains tr   ON tr.train_id = t.train_id
            WHERE t.user_id = :uid
            ORDER BY t.travel_date DESC, t.purchase_time DESC
            """
        ),
        {"uid": user["user_id"]},
    ).mappings().all()
    return [
        {
            **dict(r),
            "travel_date": str(r["travel_date"]),
            "purchase_time": str(r["purchase_time"]),
            "price": float(r["price"]),
            "discount_applied": float(r["discount_applied"] or 0),
        }
        for r in rows
    ]

@router.post("/tickets/validate", response_model=ValidateTicketResponse)
def validate_ticket(
    payload: ValidateTicketRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Conductor scaneaza QR pentru un bilet.
    Single-use: la prima validare reusita marcam token-ul ca 'used'.
    """
    conductor = _extract_user_from_token(authorization, db)
    if not has_role(conductor["role"], ROLE_TRAIN_VERIFIER):
        raise HTTPException(status_code=403, detail="Doar conductorii pot valida bilete")

    try:
        qr = db.execute(
            text(
                """
                SELECT
                    qt.qr_token_id, qt.status, qt.expires_at, qt.used_at,
                    te.entitlement_id, te.user_id, te.source_type, te.valid_until,
                    u.first_name, u.last_name,
                    CASE
                        WHEN te.source_type = 'ticket'       THEN t.ticket_type
                        WHEN te.source_type = 'subscription' THEN s.subscription_type
                        ELSE 'benefit'
                    END AS entitlement_subtype
                FROM qr_tokens qt
                JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                JOIN users u                ON u.user_id = te.user_id
                LEFT JOIN tickets t         ON t.ticket_id = te.ticket_id
                LEFT JOIN subscriptions s   ON s.subscription_id = te.subscription_id
                WHERE qt.token_value = :tv
                """
            ),
            {"tv": payload.token},
        ).mappings().first()

        if not qr:
            _log_validation(db, qr_token_id=None, conductor_id=conductor["user_id"],
                            result="invalid", device_id=payload.device_id, notes="Token not found")
            return ValidateTicketResponse(result="invalid", message="Token-ul nu exista")

        # Single-use enforcement
        if qr["used_at"] is not None:
            _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                            result="already_used", device_id=payload.device_id,
                            notes="Replay attempt")
            return ValidateTicketResponse(
                result="already_used",
                message="Biletul a fost deja folosit",
                passenger_name=f"{qr['first_name']} {qr['last_name']}",
            )

        if qr["status"] != "active":
            _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                            result="invalid", device_id=payload.device_id,
                            notes=f"Status: {qr['status']}")
            return ValidateTicketResponse(result="invalid", message=f"Status token: {qr['status']}")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if qr["expires_at"] and now > qr["expires_at"]:
            _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                            result="expired", device_id=payload.device_id, notes="Token expired")
            return ValidateTicketResponse(result="expired", message="Token-ul a expirat")

        if qr["valid_until"] and now > qr["valid_until"]:
            _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                            result="expired", device_id=payload.device_id,
                            notes="Entitlement expired")
            return ValidateTicketResponse(result="expired", message="Dreptul de calatorie a expirat")

        # SINGLE-USE: mark as used
        db.execute(
            text(
                """
                UPDATE qr_tokens
                SET status = 'used', used_at = CURRENT_TIMESTAMP
                WHERE qr_token_id = :qt_id
                """
            ),
            {"qt_id": qr["qr_token_id"]},
        )
        # Marcam si entitlement-ul ca folosit (pentru biletele single-use)
        if qr["source_type"] == "ticket":
            db.execute(
                text(
                    """
                    UPDATE travel_entitlements SET status = 'used'
                    WHERE entitlement_id = :eid
                    """
                ),
                {"eid": qr["entitlement_id"]},
            )
            db.execute(
                text(
                    """
                    UPDATE tickets SET ticket_status = 'used'
                    WHERE ticket_id = (
                        SELECT ticket_id FROM travel_entitlements WHERE entitlement_id = :eid
                    )
                    """
                ),
                {"eid": qr["entitlement_id"]},
            )

        _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                        result="valid", device_id=payload.device_id, notes=payload.location_name)

        db.commit()

        return ValidateTicketResponse(
            result="valid",
            message="Bilet validat cu succes",
            passenger_name=f"{qr['first_name']} {qr['last_name']}",
            ticket_type=qr["entitlement_subtype"],
            valid_until=str(qr["valid_until"]) if qr["valid_until"] else None,
        )

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        return ValidateTicketResponse(result="invalid", message=f"Eroare validare: {exc}")

def _log_validation(db: Session, qr_token_id, conductor_id, result, device_id=None, notes=None):
    """Insereaza un rand in validations (audit trail). Daca qr_token_id e None, skip."""
    if qr_token_id is None:
        return
    db.execute(
        text(
            """
            INSERT INTO validations (qr_token_id, conductor_id, validation_result, device_id, notes)
            VALUES (:qt_id, :cid, :result, :dev, :notes)
            """
        ),
        {"qt_id": qr_token_id, "cid": conductor_id, "result": result, "dev": device_id, "notes": notes},
    )

@router.get("/validations/history")
def validations_history(
    limit: int = 50,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Istoric validari:
      * conductor -> propriile validari
      * passenger -> validarile facute pe propriile bilete
    """
    user = _extract_user_from_token(authorization, db)
    if has_role(user["role"], ROLE_TRAIN_VERIFIER):
        rows = db.execute(
            text(
                """
                SELECT
                    v.validation_id, v.validation_time, v.validation_result, v.device_id,
                    qt.token_value,
                    te.user_id AS passenger_id,
                    pu.first_name AS passenger_first_name,
                    pu.last_name  AS passenger_last_name,
                    te.source_type
                FROM validations v
                JOIN qr_tokens qt           ON qt.qr_token_id = v.qr_token_id
                JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                JOIN users pu               ON pu.user_id = te.user_id
                WHERE v.conductor_id = :uid
                ORDER BY v.validation_time DESC
                LIMIT :lim
                """
            ),
            {"uid": user["user_id"], "lim": limit},
        ).mappings().all()
    else:
        rows = db.execute(
            text(
                """
                SELECT
                    v.validation_id, v.validation_time, v.validation_result, v.device_id,
                    qt.token_value,
                    v.conductor_id,
                    cu.first_name AS conductor_first_name,
                    cu.last_name  AS conductor_last_name,
                    te.source_type
                FROM validations v
                JOIN qr_tokens qt           ON qt.qr_token_id = v.qr_token_id
                JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                JOIN users cu               ON cu.user_id = v.conductor_id
                WHERE te.user_id = :uid
                ORDER BY v.validation_time DESC
                LIMIT :lim
                """
            ),
            {"uid": user["user_id"], "lim": limit},
        ).mappings().all()

    return [
        {**dict(r), "validation_time": str(r["validation_time"])}
        for r in rows
    ]


# ============================================================================
# === LIFECYCLE: CANCEL + RESCHEDULE ===
# ----------------------------------------------------------------------------
# Endpoint-uri pentru anulare bilet (cu refund pe trepte CFR) si reprogramare
# pe acelasi traseu, alt tren / alta data.
# ============================================================================


class RescheduleRequest(BaseModel):
    new_train_id: int = Field(..., ge=1)
    new_travel_date: str  # YYYY-MM-DD
    new_seat_ids: Optional[list[int]] = None


@router.post("/tickets/{ticket_id}/cancel")
def cancel_ticket(
    ticket_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Anuleaza un bilet activ. Calculeaza refund conform CFR Calatori:
      - >24h inainte de plecare =>  100% refund
      -  1m - 24h inainte       =>   50% refund
      -  0  sau dupa plecare    =>    0% refund
    Locurile sunt eliberate INSTANT si redevin disponibile pentru alti useri.
    """
    actor = _extract_user_from_token(authorization, db)
    user_id = actor["user_id"]

    row = db.execute(
        text("""
            SELECT t.ticket_id, t.user_id, t.train_id, t.travel_date,
                   t.price, t.ticket_status, tr.train_number
            FROM tickets t
            JOIN trains tr ON tr.train_id = t.train_id
            WHERE t.ticket_id = :tid
        """),
        {"tid": ticket_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Bilet inexistent")
    if row["user_id"] != user_id and not has_role(actor.get("role"), "admin"):
        raise HTTPException(status_code=403, detail="Acest bilet nu va apartine")
    if row["ticket_status"] != "active":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_status",
                "message": f"Biletul are statusul '{row['ticket_status']}' "
                           f"si nu mai poate fi anulat.",
            },
        )

    departure_dt = get_train_departure_datetime(
        db, row["train_id"], row["travel_date"]
    )
    if departure_dt is None:
        raise HTTPException(
            status_code=500,
            detail="Trenul nu are ora de plecare, contactati suportul.",
        )

    refund_amount, tier = compute_refund(
        price_paid=float(row["price"] or 0),
        departure_dt=departure_dt,
    )

    now = datetime.now(timezone.utc)

    # 1. Elibereaza locurile (instant disponibile)
    seats_released = release_ticket_seats(db, ticket_id)

    # 2. Marcheaza biletul ca anulat
    db.execute(
        text("""
            UPDATE tickets
            SET ticket_status = 'cancelled',
                cancelled_at = :now,
                cancel_refund_amount = :ref
            WHERE ticket_id = :tid
        """),
        {"now": now, "ref": refund_amount, "tid": ticket_id},
    )

    # 3. Invalideaza entitlement + qr_token
    db.execute(
        text("""
            UPDATE travel_entitlements SET status = 'revoked'
            WHERE source_type = 'ticket' AND ticket_id = :tid AND status = 'active'
        """),
        {"tid": ticket_id},
    )
    db.execute(
        text("""
            UPDATE qr_tokens SET status = 'revoked'
            WHERE entitlement_id IN (
                SELECT entitlement_id FROM travel_entitlements
                WHERE source_type = 'ticket' AND ticket_id = :tid
            )
        """),
        {"tid": ticket_id},
    )

    # 4. Notificare
    tier_msg = {
        "full": "Veti primi inapoi 100% din suma platita.",
        "half": "Conform regulamentului CFR, refund-ul este 50% din suma "
                "(anulare in mai putin de 24h pana la plecare).",
        "none": "Nu se acorda refund pentru anulare dupa plecarea trenului.",
    }[tier]

    db.execute(
        text("""
            INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
            VALUES (:uid, 'ticket', :title, :msg, FALSE, NOW())
        """),
        {
            "uid": user_id,
            "title": "Bilet anulat",
            "msg": f"Biletul pentru trenul {row['train_number']} din "
                   f"{row['travel_date'].isoformat()} a fost anulat. "
                   f"Refund: {refund_amount:.2f} RON. {tier_msg}",
        },
    )

    db.commit()

    return {
        "ticket_id": ticket_id,
        "status": "cancelled",
        "refund_amount": refund_amount,
        "refund_tier": tier,
        "seats_released": seats_released,
        "message": tier_msg,
    }


@router.post("/tickets/{ticket_id}/reschedule")
def reschedule_ticket(
    ticket_id: int,
    body: RescheduleRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Reprogrameaza biletul pe alt tren / alta data, PASTRAND traseul
    (acelasi origin_station si destination_station).

    Reguli CFR:
      - Biletul vechi trebuie sa fie active si trenul sa nu fi plecat inca.
      - Noul tren trebuie sa fie pe acelasi traseu (same from/to stations).
      - Diferenta de pret nu se restituie.
      - Locurile vechi sunt eliberate instant.
    """
    actor = _extract_user_from_token(authorization, db)
    user_id = actor["user_id"]

    old = db.execute(
        text("""
            SELECT t.ticket_id, t.user_id, t.train_id, t.travel_date,
                   t.price, t.discount_applied, t.ticket_type,
                   t.departure_station_id, t.arrival_station_id,
                   t.ticket_status, tr.train_number
            FROM tickets t
            JOIN trains tr ON tr.train_id = t.train_id
            WHERE t.ticket_id = :tid
        """),
        {"tid": ticket_id},
    ).mappings().first()

    if not old:
        raise HTTPException(status_code=404, detail="Bilet inexistent")
    if old["user_id"] != user_id and not has_role(actor.get("role"), "admin"):
        raise HTTPException(status_code=403, detail="Acest bilet nu va apartine")
    if old["ticket_status"] != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Biletul are statusul '{old['ticket_status']}' si nu poate fi reprogramat.",
        )

    old_dep = get_train_departure_datetime(db, old["train_id"], old["travel_date"])
    if old_dep is None or old_dep < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=409,
            detail="Trenul original a plecat deja sau ora plecarii e necunoscuta.",
        )

    # Validare data noua
    try:
        new_date = datetime.strptime(body.new_travel_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Data noua invalida (YYYY-MM-DD)")
    if new_date < datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="Noua data este in trecut")

    # Verifica noul tren si traseul
    new_train = db.execute(
        text("""
            SELECT t.train_id, t.train_number, t.route_id, t.is_active,
                   r.origin_station_id, r.destination_station_id
            FROM trains t
            LEFT JOIN routes r ON r.route_id = t.route_id
            WHERE t.train_id = :tid
        """),
        {"tid": body.new_train_id},
    ).mappings().first()
    if not new_train:
        raise HTTPException(status_code=404, detail="Tren nou inexistent")
    if not new_train["is_active"]:
        raise HTTPException(status_code=409, detail="Trenul nou nu este activ")

    if (new_train["origin_station_id"] != old["departure_station_id"] or
            new_train["destination_station_id"] != old["arrival_station_id"]):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "different_route",
                "message": "Noul tren nu e pe acelasi traseu. Reprogramarea "
                           "este permisa doar intre trenuri cu aceleasi statii "
                           "de plecare si sosire. Anulati biletul si cumparati altul.",
            },
        )

    # 1. Elibereaza locurile vechi
    release_ticket_seats(db, ticket_id)

    # 2. Marcheaza biletul vechi ca 'rescheduled'
    db.execute(
        text("UPDATE tickets SET ticket_status='rescheduled' WHERE ticket_id=:tid"),
        {"tid": ticket_id},
    )

    # 3. Anti-overlap pe noul interval (acum vechiul nu mai e 'active')
    check_overlap(db, user_id, body.new_train_id, new_date)

    # 4. Cloneaza biletul cu noile date
    new_ticket = db.execute(
        text("""
            INSERT INTO tickets (
                user_id, train_id, departure_station_id, arrival_station_id,
                travel_date, ticket_type, ticket_status,
                price, discount_applied,
                rescheduled_from_ticket_id
            ) VALUES (
                :uid, :tid, :dep, :arr,
                :td, :type, 'active',
                :price, :disc, :from_id
            )
            RETURNING ticket_id
        """),
        {
            "uid": user_id, "tid": body.new_train_id,
            "dep": old["departure_station_id"], "arr": old["arrival_station_id"],
            "td": new_date, "type": old["ticket_type"],
            "price": old["price"], "disc": old["discount_applied"],
            "from_id": ticket_id,
        },
    ).mappings().first()
    new_ticket_id = new_ticket["ticket_id"]

    # 5. Leaga si in directia inversa (vechi -> nou)
    db.execute(
        text("UPDATE tickets SET rescheduled_to_ticket_id=:new WHERE ticket_id=:old"),
        {"new": new_ticket_id, "old": ticket_id},
    )

    # 6. Confirma locurile noi (daca s-au transmis)
    seats_count = 0
    if body.new_seat_ids:
        seats_count = confirm_seats_for_ticket(
            db, ticket_id=new_ticket_id, user_id=user_id,
            seat_ids=body.new_seat_ids, travel_date=new_date,
        )

    # 7. Mut entitlement-ul pe biletul nou (re-issued)
    db.execute(
        text("""
            UPDATE travel_entitlements
            SET ticket_id = :new
            WHERE source_type = 'ticket' AND ticket_id = :old AND status = 'active'
        """),
        {"new": new_ticket_id, "old": ticket_id},
    )

    # 8. Notificare
    db.execute(
        text("""
            INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
            VALUES (:uid, 'ticket', :title, :msg, FALSE, NOW())
        """),
        {
            "uid": user_id,
            "title": "Bilet reprogramat",
            "msg": f"Biletul a fost reprogramat pe trenul "
                   f"{new_train['train_number']} din {new_date.isoformat()}.",
        },
    )

    db.commit()

    return {
        "old_ticket_id": ticket_id,
        "new_ticket_id": new_ticket_id,
        "new_train_id": body.new_train_id,
        "new_travel_date": new_date.isoformat(),
        "seats_assigned": seats_count,
        "message": "Reprogramare reusita. Diferenta de pret nu se restituie conform CFR.",
    }

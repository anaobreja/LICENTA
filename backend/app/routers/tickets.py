
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


def _compute_price(
    db: Session,
    user_id: int,
    ticket_type: str,
    train_id: int,
    departure_station_id: int,
    arrival_station_id: int,
    train_class: int = 2,
) -> tuple[float, float, float, float]:
    """
    Returns (final_price, discount_percent, base_price_single, distance_km).
    """
    # 1. Distanta totala intre statiile pe ruta trenului
    train_row = db.execute(
        text(
            """
            SELECT t.train_id, t.train_type, r.total_distance_km
            FROM trains t
            JOIN routes r ON r.route_id = t.route_id
            WHERE t.train_id = :tid
            """
        ),
        {"tid": train_id},
    ).first()
    if not train_row:
        raise HTTPException(status_code=404, detail="Trenul nu exista")

    _, train_type, total_km = train_row
    # Demo: presupunem ca biletul acopera intreaga ruta a trenului
    # (extensie viitoare: route_stops cu distanta de la origine pentru fiecare statie)
    distance_km = float(total_km or 100.0)

    # 2. Tarif single din tabel
    base_single = _lookup_base_price(db, distance_km, train_type, train_class)

    # 3. Multiplier pentru tip bilet (return = 2x)
    multiplier = RETURN_MULTIPLIER if ticket_type == "return" else 1.0
    base_total = round(base_single * multiplier, 2)

    # 4. Discount student / doctoral
    discount = _user_discount(db, user_id)
    final_price = round(base_total * (1 - discount / 100), 2)

    return final_price, discount, base_total, distance_km
# Endpoints

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
    price, discount, base_price, distance_km = _compute_price(
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

    # Validare ca trenul + rutele exista
    train = db.execute(
        text("SELECT train_id, route_id FROM trains WHERE train_id = :tid AND is_active = TRUE"),
        {"tid": payload.train_id},
    ).first()
    if not train:
        raise HTTPException(status_code=404, detail="Trenul nu exista sau este inactiv")

    price, discount, base_price, distance_km = _compute_price(
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

        db.commit()

        return {
            "ticket_id": ticket["ticket_id"],
            "ticket_type": ticket["ticket_type"],
            "travel_date": str(ticket["travel_date"]),
            "price": float(ticket["price"]),
            "discount_applied": discount,
            "qr_token": qr["token_value"],
            "qr_expires_at": str(qr["expires_at"]),
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

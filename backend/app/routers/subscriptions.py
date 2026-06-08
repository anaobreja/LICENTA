"""
Endpoint-uri pentru abonamente CFR cu scope pe ruta.

Toate sub /subscriptions:
  - POST /subscriptions/quote          — preview pret (cu reducere conditionata)
  - POST /subscriptions/buy            — cumparare (cu anti-overlap pe ruta)
  - GET  /subscriptions/my             — abonamentele mele (active + istoric)
  - POST /subscriptions/{id}/cancel    — anulare cu refund pro-rata

Toate apelurile cer Bearer token (Authorization header).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.services.subscription_business import (
    DURATION_DAYS,
    SUBSCRIPTION_TYPES,
    check_subscription_overlap,
    compute_subscription_price,
    compute_subscription_refund,
    expire_old_subscriptions,
    get_route_distance_km,
    is_student_route_for_user,
)

router = APIRouter(tags=["subscriptions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user_id_from_token(authorization: Optional[str]) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    try:
        return int(uid)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user id")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class QuoteRequest(BaseModel):
    from_station_id: int = Field(..., ge=1)
    to_station_id: int = Field(..., ge=1)
    subscription_type: str = Field(..., description="monthly | annual")


class BuyRequest(BaseModel):
    from_station_id: int = Field(..., ge=1)
    to_station_id: int = Field(..., ge=1)
    subscription_type: str = Field(..., description="monthly | annual")
    valid_from: Optional[str] = Field(default=None, description="YYYY-MM-DD. Default: azi")


# ---------------------------------------------------------------------------
# POST /subscriptions/quote
# ---------------------------------------------------------------------------

@router.post("/subscriptions/quote")
def quote_subscription(
    payload: QuoteRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Returneaza preview-ul pretului pentru un abonament, fara a crea ceva in DB.

    Calculeaza:
      - Distanta rutei
      - Pretul de baza (formula pe distanta + tip abonament)
      - Reducerea de student (50% DOAR daca ruta = home <-> universitate
        SI userul are credential student_verified activ)
      - Pretul final

    Returneaza si motivul reducerii (pentru transparenta in UI).
    """
    user_id = _user_id_from_token(authorization)

    if payload.subscription_type not in SUBSCRIPTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tip invalid: {payload.subscription_type}. "
                   f"Permise: {sorted(SUBSCRIPTION_TYPES)}",
        )
    if payload.from_station_id == payload.to_station_id:
        raise HTTPException(
            status_code=400,
            detail="Statia de plecare nu poate fi aceeasi cu sosirea",
        )

    distance = get_route_distance_km(
        db, payload.from_station_id, payload.to_station_id
    )
    if distance is None:
        raise HTTPException(
            status_code=400,
            detail="Nu pot calcula distanta pentru aceasta ruta. "
                   "Verificati ca statiile exista.",
        )

    student_status = is_student_route_for_user(
        db, user_id, payload.from_station_id, payload.to_station_id
    )

    base, discount, final = compute_subscription_price(
        distance_km=distance,
        subscription_type=payload.subscription_type,
        is_student_route=student_status["is_match"],
    )

    return {
        "from_station_id": payload.from_station_id,
        "to_station_id": payload.to_station_id,
        "subscription_type": payload.subscription_type,
        "duration_days": DURATION_DAYS[payload.subscription_type],
        "distance_km": distance,
        "base_price": base,
        "discount_amount": discount,
        "discount_pct": 90.0 if student_status["is_match"] else 0.0,
        "final_price": final,
        "is_student_route": student_status["is_match"],
        "discount_reason": student_status["reason"],
    }


# ---------------------------------------------------------------------------
# POST /subscriptions/buy
# ---------------------------------------------------------------------------

@router.post("/subscriptions/buy")
def buy_subscription(
    payload: BuyRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Cumparare abonament cu scope=route. Verifica anti-overlap (un singur
    abonament activ per ruta) si calculeaza pretul exact ca la quote.
    """
    user_id = _user_id_from_token(authorization)

    # Validari de baza
    if payload.subscription_type not in SUBSCRIPTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tip invalid: {payload.subscription_type}",
        )
    if payload.from_station_id == payload.to_station_id:
        raise HTTPException(
            status_code=400,
            detail="Statia de plecare nu poate fi aceeasi cu sosirea",
        )

    # Data inceput abonament
    if payload.valid_from:
        try:
            vf = datetime.strptime(payload.valid_from, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Format valid_from invalid (YYYY-MM-DD)")
        if vf < date.today():
            raise HTTPException(status_code=400, detail="valid_from nu poate fi in trecut")
    else:
        vf = date.today()

    vu = vf + timedelta(days=DURATION_DAYS[payload.subscription_type])

    # Anti-overlap
    check_subscription_overlap(
        db, user_id, payload.from_station_id, payload.to_station_id
    )

    # Calcul distanta + pret
    distance = get_route_distance_km(
        db, payload.from_station_id, payload.to_station_id
    )
    if distance is None:
        raise HTTPException(
            status_code=400,
            detail="Nu pot calcula distanta. Verificati statiile.",
        )

    student_status = is_student_route_for_user(
        db, user_id, payload.from_station_id, payload.to_station_id
    )
    base, discount, final = compute_subscription_price(
        distance_km=distance,
        subscription_type=payload.subscription_type,
        is_student_route=student_status["is_match"],
    )

    # Operator implicit (primul activ — pentru demo)
    op_row = db.execute(
        text("SELECT operator_id FROM railway_operators WHERE is_active = TRUE LIMIT 1")
    ).first()
    operator_id = op_row[0] if op_row else None

    # INSERT abonament
    sub_id = db.execute(
        text("""
            INSERT INTO subscriptions (
                user_id, subscription_type, operator_id,
                valid_from, valid_until, price, discount_applied, status,
                from_station_id, to_station_id, subscription_scope, route_distance_km
            ) VALUES (
                :uid, :stype, :op,
                :vf, :vu, :price, :disc, 'active',
                :fs, :ts, 'route', :dist
            )
            RETURNING subscription_id
        """),
        {
            "uid": user_id, "stype": payload.subscription_type, "op": operator_id,
            "vf": vf, "vu": vu, "price": final, "disc": discount,
            "fs": payload.from_station_id, "ts": payload.to_station_id, "dist": distance,
        },
    ).scalar()

    # Notificare confirmare
    try:
        db.execute(
            text("""
                INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
                VALUES (:uid, 'subscription', :title, :msg, FALSE, NOW())
            """),
            {
                "uid": user_id,
                "title": "Abonament cumparat",
                "msg": f"Abonament {payload.subscription_type} cumparat, "
                       f"valabil pana pe {vu.isoformat()}. "
                       f"Pret: {final:.2f} RON" +
                       (f" (cu reducere student 50%)" if student_status["is_match"] else "") + ".",
            },
        )
    except Exception:
        pass

    db.commit()

    return {
        "subscription_id": sub_id,
        "subscription_type": payload.subscription_type,
        "valid_from": vf.isoformat(),
        "valid_until": vu.isoformat(),
        "from_station_id": payload.from_station_id,
        "to_station_id": payload.to_station_id,
        "distance_km": distance,
        "base_price": base,
        "discount_amount": discount,
        "final_price": final,
        "is_student_route": student_status["is_match"],
        "message": (
            f"Abonament activ pana pe {vu.isoformat()}. "
            f"Biletele pe aceasta ruta vor fi gratuite automat."
        ),
    }


# ---------------------------------------------------------------------------
# GET /subscriptions/my
# ---------------------------------------------------------------------------

@router.get("/subscriptions/my")
def list_my_subscriptions(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Lista abonamentelor mele, sortate desc dupa valid_until.
    Aplica lazy cleanup pentru abonamentele cu valid_until trecut.
    Trimite notificari "expira in 7 zile" pentru abonamentele care expira curand.
    """
    user_id = _user_id_from_token(authorization)

    # Lazy: marcheaza ca expired abonamentele depasite
    expire_old_subscriptions(db)

    # Notificare preventiva: abonamente active care expira in ≤7 zile
    soon_to_expire = db.execute(
        text("""
            SELECT subscription_id, subscription_type, valid_until
            FROM subscriptions
            WHERE user_id = :uid
              AND status = 'active'
              AND valid_until BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
              AND NOT EXISTS (
                  SELECT 1 FROM notifications n
                  WHERE n.user_id = :uid
                    AND n.category = 'subscription_expiry'
                    AND n.created_at > NOW() - INTERVAL '3 days'
                    AND n.message LIKE '%' || subscriptions.subscription_id || '%'
              )
        """),
        {"uid": user_id},
    ).mappings().all()

    for s in soon_to_expire:
        try:
            days = (s["valid_until"] - date.today()).days
            db.execute(
                text("""
                    INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
                    VALUES (:uid, 'subscription_expiry', :title, :msg, FALSE, NOW())
                """),
                {
                    "uid": user_id,
                    "title": "Abonament expira curand",
                    "msg": f"Abonamentul {s['subscription_type']} #{s['subscription_id']} "
                           f"expira pe {s['valid_until'].isoformat()} ({days} zile ramase). "
                           f"Cumparati unul nou inainte pentru continuitate.",
                },
            )
        except Exception:
            pass

    db.commit()

    # Lista propriu-zisa
    rows = db.execute(
        text("""
            SELECT
                s.subscription_id, s.subscription_type, s.status,
                s.valid_from, s.valid_until, s.price, s.discount_applied,
                s.from_station_id, s.to_station_id, s.subscription_scope,
                s.route_distance_km, s.purchase_time,
                fs.name AS from_station_name, ts.name AS to_station_name,
                op.name AS operator_name
            FROM subscriptions s
            LEFT JOIN stations fs ON fs.station_id = s.from_station_id
            LEFT JOIN stations ts ON ts.station_id = s.to_station_id
            LEFT JOIN railway_operators op ON op.operator_id = s.operator_id
            WHERE s.user_id = :uid
            ORDER BY
                CASE s.status
                    WHEN 'active' THEN 1
                    WHEN 'expired' THEN 2
                    WHEN 'cancelled' THEN 3
                    ELSE 4
                END,
                s.valid_until DESC
        """),
        {"uid": user_id},
    ).mappings().all()

    result = []
    for r in rows:
        days_remaining = None
        if r["status"] == "active" and r["valid_until"]:
            days_remaining = max(0, (r["valid_until"] - date.today()).days)
        result.append({
            "subscription_id": r["subscription_id"],
            "subscription_type": r["subscription_type"],
            "status": r["status"],
            "valid_from": r["valid_from"].isoformat() if r["valid_from"] else None,
            "valid_until": r["valid_until"].isoformat() if r["valid_until"] else None,
            "days_remaining": days_remaining,
            "price": float(r["price"]) if r["price"] is not None else 0.0,
            "discount_applied": float(r["discount_applied"] or 0),
            "from_station_id": r["from_station_id"],
            "to_station_id": r["to_station_id"],
            "from_station_name": r["from_station_name"],
            "to_station_name": r["to_station_name"],
            "subscription_scope": r["subscription_scope"],
            "route_distance_km": float(r["route_distance_km"]) if r["route_distance_km"] else None,
            "operator_name": r["operator_name"],
            "purchase_time": r["purchase_time"].isoformat() if r["purchase_time"] else None,
        })

    return result


# ---------------------------------------------------------------------------
# POST /subscriptions/{id}/cancel
# ---------------------------------------------------------------------------

@router.post("/subscriptions/{subscription_id}/cancel")
def cancel_subscription(
    subscription_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Anuleaza un abonament activ. Refund pro-rata CFR:
      - inainte de valid_from         => 100% refund
      - in primele 50% din durata     => refund pe zilele neutilizate * 0.5
      - dupa 50% din durata           => 0% refund
    """
    user_id = _user_id_from_token(authorization)

    row = db.execute(
        text("""
            SELECT subscription_id, user_id, valid_from, valid_until,
                   price, status, subscription_type
            FROM subscriptions
            WHERE subscription_id = :sid
        """),
        {"sid": subscription_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Abonament inexistent")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Abonamentul nu va apartine")
    if row["status"] != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Abonament cu status '{row['status']}' nu poate fi anulat.",
        )

    refund, tier = compute_subscription_refund(
        price_paid=float(row["price"] or 0),
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
    )

    db.execute(
        text("""
            UPDATE subscriptions
            SET status = 'cancelled'
            WHERE subscription_id = :sid
        """),
        {"sid": subscription_id},
    )

    tier_messages = {
        "full_not_started": "Abonamentul nu incepuse inca. Refund integral.",
        "partial_pro_rata": f"Refund pro-rata pentru zilele neutilizate (penalty 50% CFR).",
        "more_than_half_used": "Mai mult de jumatate din abonament a fost folosit. Fara refund.",
        "expired": "Abonamentul era deja expirat.",
        "zero_duration": "Eroare durata zero.",
    }

    try:
        db.execute(
            text("""
                INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
                VALUES (:uid, 'subscription', :title, :msg, FALSE, NOW())
            """),
            {
                "uid": user_id,
                "title": "Abonament anulat",
                "msg": f"Abonamentul {row['subscription_type']} #{subscription_id} "
                       f"a fost anulat. Refund: {refund:.2f} RON. "
                       f"{tier_messages.get(tier, '')}",
            },
        )
    except Exception:
        pass

    db.commit()

    return {
        "subscription_id": subscription_id,
        "status": "cancelled",
        "refund_amount": refund,
        "refund_tier": tier,
        "message": tier_messages.get(tier, ""),
    }

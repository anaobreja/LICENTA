"""
Endpoint-uri pentru gestionarea locurilor in tren.

Toate endpoint-urile sunt sub /api/seats si /api/trains/{train_id}/seats:
  - GET  /trains/{train_id}/seats?travel_date=YYYY-MM-DD
      Returneaza layout-ul complet al trenului + status fiecarui loc.
  - POST /seats/hold
      Tine un loc rezervat pentru 5 minute.
  - POST /seats/release
      Elibereaza un hold.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.services.ticket_business import (
    release_expired_reservations,
    hold_seat,
    release_seat,
)

router = APIRouter(tags=["seats"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user_from_token(authorization: Optional[str], db: Session) -> int:
    """Extrage user_id din Bearer token. Returneaza doar id-ul (light)."""
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

class HoldRequest(BaseModel):
    train_id: int
    seat_id: int
    travel_date: date


class ReleaseRequest(BaseModel):
    seat_id: int
    travel_date: date


# ---------------------------------------------------------------------------
# GET /trains/{train_id}/seats  — layout cu status per loc
# ---------------------------------------------------------------------------

@router.get("/trains/{train_id}/seats")
def get_train_seats_layout(
    train_id: int,
    travel_date: date = Query(..., description="Data calatoriei (YYYY-MM-DD)"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Returneaza layout-ul trenului si statusul fiecarui loc pentru data data:
      - "free"     — disponibil
      - "sold"     — vandut (alt user)
      - "held"     — rezervat temporar de alt user
      - "mine_held"— rezervat de userul curent (hold inca valid)
      - "mine_sold"— deja cumparat de userul curent

    Structura raspuns:
    {
      "train": { ... info tren + ruta },
      "cars": [
        { "car_number": 1, "car_class": 1, "seats": [
            { "seat_id": ..., "label": "1A", "row": 1, "letter": "A",
              "is_window": true, "is_aisle": false, "status": "free" },
            ...
        ]},
        ...
      ],
      "summary": { "total": 180, "free": 175, "sold": 3, "held": 1, "mine": 1 }
    }
    """
    # Best-effort: aflu userul (poate fi optional la GET pentru afisare publica)
    current_user_id: Optional[int] = None
    if authorization:
        try:
            current_user_id = _user_from_token(authorization, db)
        except HTTPException:
            current_user_id = None

    # Cleanup la fiecare GET ca statusul "held" sa fie real-time accurate
    release_expired_reservations(db)

    # 1. Info tren — orele vin de la route_stops (prima/ultima oprire)
    train = db.execute(
        text("""
            SELECT t.train_id, t.train_number, t.train_type,
                   op.code AS operator_code, op.name AS operator_name,
                   s_orig.station_id AS origin_station_id,
                   s_orig.name      AS origin_station,
                   s_dest.station_id AS dest_station_id,
                   s_dest.name      AS dest_station,
                   (SELECT rs.departure_time FROM route_stops rs
                       WHERE rs.route_id = t.route_id
                       ORDER BY rs.stop_order ASC LIMIT 1) AS departure_time,
                   (SELECT rs.arrival_time FROM route_stops rs
                       WHERE rs.route_id = t.route_id
                       ORDER BY rs.stop_order DESC LIMIT 1) AS arrival_time
            FROM trains t
            LEFT JOIN railway_operators op ON op.operator_id = t.operator_id
            LEFT JOIN routes r ON r.route_id = t.route_id
            LEFT JOIN stations s_orig ON s_orig.station_id = r.origin_station_id
            LEFT JOIN stations s_dest ON s_dest.station_id = r.destination_station_id
            WHERE t.train_id = :tid
        """),
        {"tid": train_id},
    ).mappings().first()

    if not train:
        raise HTTPException(status_code=404, detail="Tren inexistent")

    # 2. Vagoane + locuri
    cars_rows = db.execute(
        text("""
            SELECT tc.train_car_id, tc.car_number, tc.car_class, tc.total_seats
            FROM train_cars tc
            WHERE tc.train_id = :tid
            ORDER BY tc.car_number
        """),
        {"tid": train_id},
    ).mappings().all()

    seats_rows = db.execute(
        text("""
            SELECT s.seat_id, s.train_car_id, s.seat_row, s.seat_letter,
                   s.seat_label, s.is_window, s.is_aisle
            FROM seats s
            JOIN train_cars tc ON tc.train_car_id = s.train_car_id
            WHERE tc.train_id = :tid
            ORDER BY tc.car_number, s.seat_row, s.seat_letter
        """),
        {"tid": train_id},
    ).mappings().all()

    # 3. Locuri vandute pentru travel_date
    sold_rows = db.execute(
        text("""
            SELECT ts.seat_id, t.user_id
            FROM ticket_seats ts
            JOIN tickets t ON t.ticket_id = ts.ticket_id
            WHERE ts.travel_date = :td
              AND t.train_id = :tid
              AND t.ticket_status = 'active'
        """),
        {"td": travel_date, "tid": train_id},
    ).fetchall()
    sold_map = {r[0]: r[1] for r in sold_rows}  # seat_id -> owner user_id

    # 4. Locuri tinute pentru travel_date
    held_rows = db.execute(
        text("""
            SELECT seat_id, user_id, expires_at
            FROM seat_reservations
            WHERE travel_date = :td
              AND train_id = :tid
        """),
        {"td": travel_date, "tid": train_id},
    ).fetchall()
    held_map = {r[0]: (r[1], r[2]) for r in held_rows}

    # 5. Asambleaza raspunsul
    cars_by_id = {
        c["train_car_id"]: {
            "car_number": c["car_number"],
            "car_class": c["car_class"],
            "total_seats": c["total_seats"],
            "seats": [],
        }
        for c in cars_rows
    }

    summary = {"total": 0, "free": 0, "sold": 0, "held": 0, "mine": 0}

    for s in seats_rows:
        sid = s["seat_id"]
        if sid in sold_map:
            owner = sold_map[sid]
            status = "mine_sold" if owner == current_user_id else "sold"
            summary["sold"] += 1
            if owner == current_user_id:
                summary["mine"] += 1
        elif sid in held_map:
            owner, expires = held_map[sid]
            status = "mine_held" if owner == current_user_id else "held"
            summary["held"] += 1
            if owner == current_user_id:
                summary["mine"] += 1
        else:
            status = "free"
            summary["free"] += 1
        summary["total"] += 1

        cars_by_id[s["train_car_id"]]["seats"].append({
            "seat_id": sid,
            "label": s["seat_label"],
            "row": s["seat_row"],
            "letter": s["seat_letter"],
            "is_window": s["is_window"],
            "is_aisle": s["is_aisle"],
            "status": status,
        })

    return {
        "train": {
            "train_id": train["train_id"],
            "train_number": train["train_number"],
            "train_type": train["train_type"],
            "departure_time": train["departure_time"].strftime("%H:%M")
                              if train["departure_time"] else None,
            "arrival_time": train["arrival_time"].strftime("%H:%M")
                            if train["arrival_time"] else None,
            "operator": train["operator_code"],
            "operator_name": train["operator_name"],
            "origin": train["origin_station"],
            "destination": train["dest_station"],
        },
        "travel_date": travel_date.isoformat(),
        "cars": sorted(cars_by_id.values(), key=lambda c: c["car_number"]),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# POST /seats/hold
# ---------------------------------------------------------------------------

@router.post("/seats/hold")
def hold_seat_endpoint(
    req: HoldRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Tine un loc rezervat pentru 5 minute pentru user.

    Posibile erori:
      - 401 daca nu e autentificat
      - 404 daca locul nu apartine trenului
      - 409 daca locul e deja vandut sau tinut de alt user
    """
    user_id = _user_from_token(authorization, db)
    result = hold_seat(db, user_id, req.seat_id, req.train_id, req.travel_date)
    db.commit()
    return {
        "seat_id": result["seat_id"],
        "expires_at": result["expires_at"].isoformat(),
        "refreshed": result["refreshed"],
        "hold_duration_seconds": 300,
    }


# ---------------------------------------------------------------------------
# POST /seats/release
# ---------------------------------------------------------------------------

@router.post("/seats/release")
def release_seat_endpoint(
    req: ReleaseRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Elibereaza hold-ul userului curent pe un loc.
    Idempotent: daca nu exista hold, returneaza released=false fara eroare.
    """
    user_id = _user_from_token(authorization, db)
    released = release_seat(db, user_id, req.seat_id, req.travel_date)
    db.commit()
    return {"seat_id": req.seat_id, "released": released}

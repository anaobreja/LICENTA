"""
Logica de business pentru lifecycle-ul biletelor.

Acest modul concentreaza in helpere reutilizabile:
  - Verificarea anti-overlap (acelasi user nu poate avea 2 bilete in
    intervale orare suprapuse pe data aceea).
  - Calcularea refund-ului conform regulilor CFR Calatori.
  - Operatii pe locuri (hold / release / sold).

Toate functiile primesc `db: Session` din router si fac doar query-uri/INSERT-uri.
Nu face commit. Routerul decide cand face commit, ca sa pastreze tranzactia
end-to-end (de ex. INSERT ticket + INSERT ticket_seats + INSERT notification
trebuie sa fie ATOMIC).
"""
from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Constante de business (centralizate ca sa fie usor de modificat / testat)
# ---------------------------------------------------------------------------

# Cat timp tinem locul rezervat pana userul confirma cumpararea
HOLD_DURATION = timedelta(minutes=5)

# Praguri refund CFR (delta intre acum si plecarea trenului)
REFUND_FULL_THRESHOLD = timedelta(hours=24)   # >24h => 100% refund
REFUND_HALF_THRESHOLD = timedelta(hours=0)    # 0-24h => 50% refund
# <0 (tren plecat deja) sau status used => 0% refund


# ---------------------------------------------------------------------------
# Helper: dt-ul de plecare al trenului pentru o data calatorie
# ---------------------------------------------------------------------------

def get_train_departure_datetime(
    db: Session, train_id: int, travel_date: date
) -> Optional[datetime]:
    """
    Returneaza datetime-ul plecarii (tz=UTC) pentru un tren intr-o data data.

    Trenurile au mai multe opriri (route_stops), fiecare cu departure_time /
    arrival_time. "Plecarea trenului" = ora plecarii din PRIMA statie a rutei
    (stop_order ASC). Combinam travel_date cu acea ora.
    """
    row = db.execute(
        text("""
            SELECT rs.departure_time
            FROM route_stops rs
            JOIN trains t ON t.route_id = rs.route_id
            WHERE t.train_id = :tid
            ORDER BY rs.stop_order ASC
            LIMIT 1
        """),
        {"tid": train_id},
    ).first()
    if not row or row[0] is None:
        return None
    return datetime.combine(travel_date, row[0]).replace(tzinfo=timezone.utc)


def get_train_arrival_datetime(
    db: Session, train_id: int, travel_date: date
) -> Optional[datetime]:
    """
    Returneaza datetime-ul sosirii (tz=UTC) la ultima statie a rutei.
    Daca arrival_time < departure_time (tren de noapte), sosirea e a doua zi.
    """
    row = db.execute(
        text("""
            SELECT rs.arrival_time
            FROM route_stops rs
            JOIN trains t ON t.route_id = rs.route_id
            WHERE t.train_id = :tid
            ORDER BY rs.stop_order DESC
            LIMIT 1
        """),
        {"tid": train_id},
    ).first()
    if not row or row[0] is None:
        return None
    arr_time = row[0]

    # Pentru a determina daca e tren de noapte, comparam cu departure-ul.
    dep_dt = get_train_departure_datetime(db, train_id, travel_date)
    arr_date = travel_date
    if dep_dt is not None and arr_time < dep_dt.time():
        arr_date = travel_date + timedelta(days=1)
    return datetime.combine(arr_date, arr_time).replace(tzinfo=timezone.utc)


def get_segment_departure_datetime(
    db: Session, train_id: int, departure_station_id: int, travel_date: date,
) -> Optional[datetime]:
    """
    Ora plecarii din statia SPECIFICA a biletului (nu origin-ul rutei).
    Foloseste route_stops.departure_time pentru station_id dat.
    """
    row = db.execute(
        text("""
            SELECT rs.departure_time
            FROM route_stops rs
            JOIN trains t ON t.route_id = rs.route_id
            WHERE t.train_id = :tid AND rs.station_id = :sid
            ORDER BY rs.stop_order ASC
            LIMIT 1
        """),
        {"tid": train_id, "sid": departure_station_id},
    ).first()
    if not row or row[0] is None:
        # Fallback la origine ruta daca statia nu apare in route_stops
        return get_train_departure_datetime(db, train_id, travel_date)
    return datetime.combine(travel_date, row[0]).replace(tzinfo=timezone.utc)


def get_segment_arrival_datetime(
    db: Session, train_id: int, departure_station_id: int,
    arrival_station_id: int, travel_date: date,
) -> Optional[datetime]:
    """
    Ora sosirii in statia SPECIFICA a biletului. Gestioneaza si overnight
    (daca arrival_time < segment departure_time -> ziua urmatoare).
    """
    row = db.execute(
        text("""
            SELECT rs.arrival_time
            FROM route_stops rs
            JOIN trains t ON t.route_id = rs.route_id
            WHERE t.train_id = :tid AND rs.station_id = :sid
            ORDER BY rs.stop_order DESC
            LIMIT 1
        """),
        {"tid": train_id, "sid": arrival_station_id},
    ).first()
    if not row or row[0] is None:
        return get_train_arrival_datetime(db, train_id, travel_date)
    arr_time = row[0]

    # Detect overnight: arrival < segment departure
    dep_dt = get_segment_departure_datetime(
        db, train_id, departure_station_id, travel_date
    )
    arr_date = travel_date
    if dep_dt is not None and arr_time < dep_dt.time():
        arr_date = travel_date + timedelta(days=1)
    return datetime.combine(arr_date, arr_time).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Anti-overlap
# ---------------------------------------------------------------------------

def check_overlap(
    db: Session,
    user_id: int,
    train_id: int,
    travel_date: date,
    departure_station_id: Optional[int] = None,
    arrival_station_id: Optional[int] = None,
    source_train_id: Optional[int] = None,
) -> None:
    """
    Verifica daca user-ul mai are deja un bilet activ care se suprapune
    cu intervalul [departure, arrival] al noului tren.

    Algoritm:
      - Calculam [new_dep, new_arr] pentru trenul cerut.
      - Selectam toate biletele active ale userului care au travel_date in
        intervalul [travel_date - 1, travel_date + 1] (acopera trenuri de noapte).
      - Pentru fiecare, calculam intervalul lor [dep, arr] si verificam overlap.
      - Daca overlap -> HTTPException 409 cu mesaj clar.

    Reguli de overlap: intervalele [a1,a2] si [b1,b2] se suprapun daca
      a1 < b2 AND b1 < a2  (strict, deci doua intervale ce se ating in capete
      NU sunt considerate overlap — un tren care soseste la 12:00 si altul
      care pleaca la 12:00 sunt acceptate).
    """
    # Bug #38 FIX: foloseste orele SEGMENTULUI biletului (statiile dep/arr),
    # nu orele rutei intregi. Inainte trenuri lung-distanta erau validate pe
    # orele rutei origin->dest, nu pe segmentul real cumparat.
    if departure_station_id is not None and arrival_station_id is not None:
        new_dep = get_segment_departure_datetime(
            db, train_id, departure_station_id, travel_date,
        )
        new_arr = get_segment_arrival_datetime(
            db, train_id, departure_station_id, arrival_station_id, travel_date,
        )
    else:
        # Fallback compat retroactiv
        new_dep = get_train_departure_datetime(db, train_id, travel_date)
        new_arr = get_train_arrival_datetime(db, train_id, travel_date)
    if new_dep is None or new_arr is None:
        # Daca trenul nu are ore (date incomplete), sarim peste verificare.
        # Mai bine permitem decat sa blocam pe demo.
        return

    # Selectam biletele active +/- 1 zi pentru a acoperi cazurile de noapte.
    # Orele plecare/sosire vin din route_stops (prima/ultima oprire pe ruta).
    source_filter = "AND t.train_id != :source_train" if source_train_id is not None else ""
    params: dict = {
        "uid": user_id,
        "dmin": travel_date - timedelta(days=1),
        "dmax": travel_date + timedelta(days=1),
        "new_train": train_id,
    }
    if source_train_id is not None:
        params["source_train"] = source_train_id

    candidates = db.execute(
        text(f"""
            SELECT t.ticket_id, t.train_id, t.travel_date,
                   t.departure_station_id, t.arrival_station_id,
                   tr.train_number,
                   sd.name AS from_station, sa.name AS to_station
            FROM tickets t
            JOIN trains tr ON tr.train_id = t.train_id
            LEFT JOIN stations sd ON sd.station_id = t.departure_station_id
            LEFT JOIN stations sa ON sa.station_id = t.arrival_station_id
            WHERE t.user_id = :uid
              AND t.ticket_status = 'active'
              AND t.passenger_name IS NULL
              AND t.travel_date BETWEEN :dmin AND :dmax
              AND t.train_id != :new_train
              {source_filter}
        """),
        params,
    ).mappings().all()

    for existing in candidates:
        # Folosim orele SEGMENTULUI biletului existent (statiile lui dep/arr)
        ex_dep = get_segment_departure_datetime(
            db, existing["train_id"], existing["departure_station_id"],
            existing["travel_date"],
        )
        ex_arr = get_segment_arrival_datetime(
            db, existing["train_id"], existing["departure_station_id"],
            existing["arrival_station_id"], existing["travel_date"],
        )
        if ex_dep is None or ex_arr is None:
            continue

        if new_dep < ex_arr and ex_dep < new_arr:
            # Overlap detectat
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "overlap",
                    "message": (
                        f"Aveti deja un bilet activ pentru trenul "
                        f"{existing['train_number']} "
                        f"({existing['from_station']} → {existing['to_station']}) "
                        f"in intervalul {ex_dep.strftime('%H:%M')}–"
                        f"{ex_arr.strftime('%H:%M')} pe data de "
                        f"{existing['travel_date'].isoformat()}. "
                        f"Anulati sau reprogramati biletul existent inainte "
                        f"de a cumpara altul in acelasi interval."
                    ),
                    "conflicting_ticket_id": existing["ticket_id"],
                },
            )


# ---------------------------------------------------------------------------
# Refund (regulament CFR)
# ---------------------------------------------------------------------------

def compute_refund(
    price_paid: float,
    departure_dt: datetime,
    now: Optional[datetime] = None,
) -> tuple[float, str]:
    """
    Calculeaza suma de restituit conform regulilor CFR:
      - >24h inainte de plecare    => 100% refund
      - 1m – 24h inainte de plecare =>  50% refund (penalizare anulare tarzie)
      -  0h sau dupa plecare       =>   0% refund

    Returneaza (refund_amount, tier_name) — tier_name e folosit la mesaj UI.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if departure_dt.tzinfo is None:
        departure_dt = departure_dt.replace(tzinfo=timezone.utc)

    delta = departure_dt - now

    if delta >= REFUND_FULL_THRESHOLD:
        return (round(price_paid, 2), "full")
    if delta > REFUND_HALF_THRESHOLD:
        return (round(price_paid * 0.5, 2), "half")
    return (0.0, "none")


# ---------------------------------------------------------------------------
# Seat operations
# ---------------------------------------------------------------------------

def release_expired_reservations(db: Session) -> int:
    """
    Apel lazy la functia SQL de cleanup. Returneaza numarul de hold-uri sterse.
    Trebuie apelat la inceputul oricarui endpoint care citeste/modifica
    seat_reservations sau seats, ca sa avem stare consistenta.
    """
    result = db.execute(text("SELECT release_expired_reservations()")).scalar()
    return int(result or 0)


def hold_seat(
    db: Session,
    user_id: int,
    seat_id: int,
    train_id: int,
    travel_date: date,
) -> dict:
    """
    Tine un loc rezervat pentru 5 minute pentru user.

    Reguli:
      - Locul nu poate fi vandut deja (in ticket_seats pentru aceeasi data).
      - Locul nu poate fi tinut de alt user (in seat_reservations active).
      - Daca userul tine deja locul, extinde expirarea (refresh).
      - Verifica ca seat_id apartine train_id (prin train_car).

    Returneaza {seat_id, expires_at, refreshed: bool}.
    """
    release_expired_reservations(db)

    # 1. Verifica ca locul apartine trenului
    valid = db.execute(
        text("""
            SELECT s.seat_id
            FROM seats s
            JOIN train_cars tc ON tc.train_car_id = s.train_car_id
            WHERE s.seat_id = :sid AND tc.train_id = :tid
        """),
        {"sid": seat_id, "tid": train_id},
    ).scalar()
    if not valid:
        raise HTTPException(
            status_code=404,
            detail={"error": "seat_not_in_train",
                    "message": "Locul nu apartine acestui tren."},
        )

    # 2. Verifica ca nu e deja vandut pentru travel_date
    sold = db.execute(
        text("""
            SELECT ts.ticket_seat_id
            FROM ticket_seats ts
            JOIN tickets t ON t.ticket_id = ts.ticket_id
            WHERE ts.seat_id = :sid
              AND ts.travel_date = :td
              AND t.ticket_status = 'active'
        """),
        {"sid": seat_id, "td": travel_date},
    ).scalar()
    if sold:
        raise HTTPException(
            status_code=409,
            detail={"error": "seat_sold",
                    "message": "Locul este deja ocupat. Alegeti altul."},
        )

    # 3. Verifica reservation existenta
    existing = db.execute(
        text("""
            SELECT reservation_id, user_id
            FROM seat_reservations
            WHERE seat_id = :sid AND travel_date = :td
        """),
        {"sid": seat_id, "td": travel_date},
    ).mappings().first()

    new_expires = datetime.now(timezone.utc) + HOLD_DURATION

    if existing:
        if existing["user_id"] != user_id:
            raise HTTPException(
                status_code=409,
                detail={"error": "seat_held_by_other",
                        "message": "Locul este rezervat momentan de alt utilizator. "
                                   "Mai incercati in cateva minute sau alegeti altul."},
            )
        # Refresh
        db.execute(
            text("""
                UPDATE seat_reservations
                SET expires_at = :exp, held_at = NOW()
                WHERE reservation_id = :rid
            """),
            {"exp": new_expires, "rid": existing["reservation_id"]},
        )
        return {"seat_id": seat_id, "expires_at": new_expires, "refreshed": True}

    # 4. INSERT nou
    db.execute(
        text("""
            INSERT INTO seat_reservations
                (seat_id, user_id, train_id, travel_date, held_at, expires_at)
            VALUES (:sid, :uid, :tid, :td, NOW(), :exp)
        """),
        {"sid": seat_id, "uid": user_id, "tid": train_id,
         "td": travel_date, "exp": new_expires},
    )
    return {"seat_id": seat_id, "expires_at": new_expires, "refreshed": False}


def release_seat(
    db: Session,
    user_id: int,
    seat_id: int,
    travel_date: date,
) -> bool:
    """
    Elibereaza un hold facut de userul curent (idempotent).
    Returneaza True daca a sters ceva, False daca nu exista hold.
    """
    result = db.execute(
        text("""
            DELETE FROM seat_reservations
            WHERE seat_id = :sid AND travel_date = :td AND user_id = :uid
            RETURNING reservation_id
        """),
        {"sid": seat_id, "td": travel_date, "uid": user_id},
    ).first()
    return result is not None


def pick_available_seats(
    db: Session,
    train_id: int,
    travel_date: date,
    n: int,
    excluded: list[int] | None = None,
) -> list[int]:
    """
    Auto-asignare locuri: returneaza primele `n` seat_ids din tren care nu sunt
    vandute si nu sunt in hold activ pentru travel_date.

    Folosit la cumparare cand userul nu si-a ales explicit locul (in loc sa
    cream un bilet fara loc, dam automat un loc liber).

    Argumente:
      - train_id, travel_date: identifica setul de seats valid
      - n: cate locuri vrem
      - excluded: seat_ids deja alocate in iteratia curenta (ex. cand cerem
        seats pentru pax 2 dupa ce am alocat 1 pentru pax 1 in aceeasi tranzactie)

    Returneaza lista cu seat_ids (poate fi mai scurta decat n daca trenul e
    aproape plin). Caller-ul trebuie sa verifice ca len() == n.
    """
    release_expired_reservations(db)
    excluded = excluded or []

    rows = db.execute(
        text("""
            SELECT s.seat_id
            FROM seats s
            JOIN train_cars tc ON tc.train_car_id = s.train_car_id
            WHERE tc.train_id = :tid
              AND s.seat_id <> ALL(:excluded)
              -- Locul nu trebuie sa fie deja vandut pe travel_date pentru un
              -- bilet activ.
              AND NOT EXISTS (
                  SELECT 1 FROM ticket_seats ts
                  JOIN tickets t ON t.ticket_id = ts.ticket_id
                  WHERE ts.seat_id = s.seat_id
                    AND ts.travel_date = :td
                    AND t.ticket_status = 'active'
              )
              -- Locul nu trebuie sa fie in hold pentru alt user (orice hold
              -- activ blocheaza auto-asignarea, ca sa nu suprapunem cu un user
              -- care e in proces de cumparare).
              AND NOT EXISTS (
                  SELECT 1 FROM seat_reservations sr
                  WHERE sr.seat_id = s.seat_id
                    AND sr.travel_date = :td
                    AND sr.expires_at > NOW()
              )
            ORDER BY tc.car_number, s.seat_row, s.seat_letter
            LIMIT :n
        """),
        {"tid": train_id, "td": travel_date, "excluded": excluded, "n": n},
    ).fetchall()
    return [r[0] for r in rows]


def confirm_seats_for_ticket(
    db: Session,
    ticket_id: int,
    user_id: int,
    seat_ids: list[int],
    travel_date: date,
) -> int:
    """
    Converteste hold-urile active ale userului in vanzari (ticket_seats).

    Apelat dupa INSERT-ul ticket-ului dar inainte de commit.
    Raise daca un seat nu e in hold pentru user sau a fost intre timp vandut.
    """
    release_expired_reservations(db)

    if not seat_ids:
        return 0

    # Verifica ca toate seat_ids sunt in hold-uri valide ale userului.
    # Folosim IN (...) cu parametri individuali pentru a evita problemele de
    # bind a array-urilor SQLAlchemy/psycopg.
    held = set()
    for sid in seat_ids:
        row = db.execute(
            text("""
                SELECT 1 FROM seat_reservations
                WHERE user_id = :uid AND travel_date = :td AND seat_id = :sid
            """),
            {"uid": user_id, "td": travel_date, "sid": sid},
        ).first()
        if row:
            held.add(sid)
    missing = set(seat_ids) - held
    if missing:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "hold_expired",
                "message": (
                    f"Rezervarea pentru locurile {sorted(missing)} a expirat. "
                    f"Reselectati locurile si reincercati."
                ),
                "missing_seat_ids": sorted(missing),
            },
        )

    # INSERT-uri in ticket_seats — loop simplu pentru a evita problema de
    # bind a array-urilor cu UNNEST in SQLAlchemy. UNIQUE(seat_id, travel_date)
    # garanteaza ca daca cineva a vandut intre timp pe alta tranzactie, vom
    # primi IntegrityError si tranzactia va fi anulata in router.
    for sid in seat_ids:
        db.execute(
            text("""
                INSERT INTO ticket_seats (ticket_id, seat_id, travel_date)
                VALUES (:tid, :sid, :td)
            """),
            {"tid": ticket_id, "sid": sid, "td": travel_date},
        )

    # Sterge hold-urile (au devenit vanzari)
    for sid in seat_ids:
        db.execute(
            text("""
                DELETE FROM seat_reservations
                WHERE user_id = :uid AND travel_date = :td AND seat_id = :sid
            """),
            {"uid": user_id, "td": travel_date, "sid": sid},
        )
    return len(seat_ids)


def release_ticket_seats(db: Session, ticket_id: int) -> int:
    """
    Sterge toate randurile din ticket_seats pentru un ticket. Apelat la cancel.
    Locurile redevin instant libere pentru alti useri.
    """
    result = db.execute(
        text("DELETE FROM ticket_seats WHERE ticket_id = :tid RETURNING ticket_seat_id"),
        {"tid": ticket_id},
    ).fetchall()
    return len(result)

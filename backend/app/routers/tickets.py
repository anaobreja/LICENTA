
import secrets
from datetime import date, datetime, timedelta, timezone
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
from app.services.subscription_business import find_active_subscription_for_route

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
class PassengerSeat(BaseModel):
    """Un pasager pentru un loc specific (multi-pasager checkout)."""
    # seat_id poate fi None — backend-ul aloca automat primul loc liber
    # (vezi blocul Auto-asignare din buy_ticket). Necesar cand utilizatorul
    # nu si-a ales explicit locul in interfata.
    seat_id: Optional[int] = Field(None, ge=1)
    passenger_name: Optional[str] = None  # None = cumparator (default)

class BuyTicketRequest(BaseModel):
    train_id: int = Field(..., ge=1)
    departure_station_id: int = Field(..., ge=1)
    arrival_station_id: int = Field(..., ge=1)
    travel_date: str  # YYYY-MM-DD
    ticket_type: str = Field(default="single", pattern="^(single|return|Single|Return|SINGLE|RETURN)$")
    # LEGACY: lista de seat_id-uri (fara pasager distinct).
    # Daca e setata, toti pasagerii sunt cumparatorul insusi.
    seat_ids: Optional[list[int]] = None
    # NEW: lista de pasageri cu nume distinct (1 loc = 1 bilet).
    # Daca e setata, ignora seat_ids si creeaza N bilete cu QR-uri separate.
    passengers: Optional[list[PassengerSeat]] = None

# --- Multi-leg journey models ---
class JourneyPassenger(BaseModel):
    """Un pasager pentru un journey multi-leg."""
    passenger_name: Optional[str] = None  # None = cumpărătorul însuși

class JourneyLegInput(BaseModel):
    """Un segment de tren dintr-un journey cu schimbare."""
    train_id: int = Field(..., ge=1)
    departure_station_id: int = Field(..., ge=1)
    arrival_station_id: int = Field(..., ge=1)
    travel_date: str  # YYYY-MM-DD
    # seat_ids[i] = locul pasagerului i pe acest segment (None = auto-asignare)
    seat_ids: Optional[list[Optional[int]]] = None

class BuyJourneyRequest(BaseModel):
    """Cumpărare journey cu 1–3 segmente și 1–4 pasageri."""
    legs: list[JourneyLegInput] = Field(..., min_length=1, max_length=3)
    ticket_type: str = Field("single", pattern="^(single|return|Single|Return|SINGLE|RETURN)$")
    passengers: list[JourneyPassenger] = Field(
        default_factory=lambda: [JourneyPassenger()],
        min_length=1, max_length=4,
    )

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
    Prioritizeaza student_verified > student > elev > 0.
    """
    cred_row = db.execute(
        text(
            """
            SELECT credential_type FROM user_credentials
            WHERE user_id = :uid
              AND status = 'active'
              AND valid_until > CURRENT_TIMESTAMP
              AND credential_type IN ('student', 'student_verified', 'pupil', 'elev_verified')
            ORDER BY
              CASE credential_type
                WHEN 'student_verified'   THEN 1
                WHEN 'student'            THEN 2
                WHEN 'elev_verified'      THEN 3
                WHEN 'pupil'              THEN 4
                ELSE 99
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
    return 0.0


def _segment_on_personal_path(
    db: Session,
    home_id: int,
    uni_id: int,
    dep_id: int,
    arr_id: int,
) -> dict:
    """
    Verifica daca segmentul (dep_id -> arr_id) face parte din traseul
    feroviar dintre home_id si uni_id (in orice sens).

    Cazuri acoperite:

    A. ENDPOINT EXACT: {dep, arr} == {home, uni}  -> match trivial.

    B. SEGMENT PE RUTA UNICA (fara transfer): exista o ruta activa care
       contine TOATE 4 statiile (home, uni, dep, arr), iar (dep, arr)
       sunt strict in interiorul intervalului [home..uni] (sau invers,
       intre [uni..home]) ordonate prin stop_order.

    C. SEGMENT PE RUTA CU TRANSFER (1 schimbare): exista 2 rute conectate
       printr-o statie comuna X astfel incat:
         - O ruta R1 contine home si una din {dep, arr}.
         - O alta ruta R2 contine uni si cealalta dintre {dep, arr}.
         - R1 si R2 impart cel putin o statie comuna (= transfer point).

    Returneaza dict:
        match: bool
        match_kind: 'endpoint' | 'direct_segment' | 'transfer_segment' | None
    """
    if dep_id == arr_id:
        return {"match": False, "match_kind": None}

    pair = {dep_id, arr_id}
    expected = {home_id, uni_id}

    # ---- A. Endpoint exact ----
    if pair == expected:
        return {"match": True, "match_kind": "endpoint"}

    # ---- B. Segment pe ruta unica ----
    rows = db.execute(
        text(
            """
            SELECT
                rs_home.route_id,
                rs_home.stop_order AS home_order,
                rs_uni.stop_order  AS uni_order,
                rs_dep.stop_order  AS dep_order,
                rs_arr.stop_order  AS arr_order
            FROM route_stops rs_home
            JOIN route_stops rs_uni
              ON rs_uni.route_id = rs_home.route_id
             AND rs_uni.station_id = :uni
            JOIN route_stops rs_dep
              ON rs_dep.route_id = rs_home.route_id
             AND rs_dep.station_id = :dep
            JOIN route_stops rs_arr
              ON rs_arr.route_id = rs_home.route_id
             AND rs_arr.station_id = :arr
            JOIN routes r ON r.route_id = rs_home.route_id AND r.is_active = TRUE
            WHERE rs_home.station_id = :home
            """
        ),
        {"home": home_id, "uni": uni_id, "dep": dep_id, "arr": arr_id},
    ).mappings().all()

    for r in rows:
        ho, uo, do, ao = r["home_order"], r["uni_order"], r["dep_order"], r["arr_order"]
        lo, hi = min(ho, uo), max(ho, uo)
        # (dep, arr) trebuie ambele in intervalul [lo, hi], in ORICE ordine
        # (calatorul poate merge in directia rutei sau invers).
        if lo <= do <= hi and lo <= ao <= hi and do != ao:
            return {"match": True, "match_kind": "direct_segment"}

    # ---- C. Segment pe ruta cu transfer (1 schimbare) ----
    # Cazul tipic: studentul Faurei->Bucuresti cu schimbare in Buzau.
    # R1 = ruta care contine (home=Faurei, dep_sau_arr).
    # R2 = ruta care contine (uni=Bucuresti, cealalta dintre {dep, arr}).
    # R1 si R2 trebuie sa aiba cel putin o statie comuna (transfer point).
    #
    # ⚠ PRECONDITIE ANTI-FALSE-POSITIVE:
    # Aplicam blocul C DOAR daca NU exista o ruta directa (fara schimbare)
    # intre home si uni. Daca exista ruta directa, atunci schimbarea NU e
    # necesara - orice match prin blocul C ar fi un drum ocolitor pe care un
    # abonament real CFR nu il acopera.
    #
    # Exemplu bug istoric (fixat aici):
    #   abonament Bucuresti Nord (267) <-> Buzau (284) - exista ruta directa
    #   pe linia Bucuresti-Ploiesti-Buzau (~274 km, ~3h);
    #   bilet Brasov -> Bucuresti Nord - algoritmul vechi gasea ca exista o
    #   "calatorie" BucNord->Brasov->Buzau prin Sf.Gheorghe (cu schimbare in
    #   Brasov) si zicea ca abonamentul acopera leg-ul 1 (BucNord-Brasov).
    #   Asta e fals: abonamentul real CFR acopera DOAR drumul natural intre
    #   home si uni, nu orice ocol prin schimbare.
    has_direct_route_home_uni = db.execute(
        text("""
            SELECT 1
            FROM route_stops rs_home
            JOIN route_stops rs_uni
              ON rs_uni.route_id = rs_home.route_id
             AND rs_uni.station_id = :uni
            JOIN routes r ON r.route_id = rs_home.route_id AND r.is_active = TRUE
            WHERE rs_home.station_id = :home
            LIMIT 1
        """),
        {"home": home_id, "uni": uni_id},
    ).first()
    if has_direct_route_home_uni:
        # Drumul natural home<->uni e direct: blocul B (segment pe ruta unica)
        # ar fi prins deja orice segment legitim. Daca nu a prins, NU mai aplicam
        # C (ar fi un match prin drum ocolit, fals).
        return {"match": False, "match_kind": None}

    transfer_match = db.execute(
        text(
            """
            WITH
            r1_candidates AS (
                -- Rute care contin (home, transfer_point) unde transfer_point
                -- e una dintre statiile {dep, arr} (dar nu egala cu home/uni,
                -- ca sa fie cu adevarat o statie intermediara de transfer).
                SELECT DISTINCT
                       rs_home.route_id,
                       rs_ep.station_id AS ep_station
                FROM route_stops rs_home
                JOIN route_stops rs_ep
                  ON rs_ep.route_id = rs_home.route_id
                 AND rs_ep.station_id IN (:dep, :arr)
                 AND rs_ep.station_id <> :home
                 AND rs_ep.station_id <> :uni
                JOIN routes r ON r.route_id = rs_home.route_id AND r.is_active = TRUE
                WHERE rs_home.station_id = :home
            ),
            r2_candidates AS (
                SELECT DISTINCT
                       rs_uni.route_id,
                       rs_ep.station_id AS ep_station
                FROM route_stops rs_uni
                JOIN route_stops rs_ep
                  ON rs_ep.route_id = rs_uni.route_id
                 AND rs_ep.station_id IN (:dep, :arr)
                 AND rs_ep.station_id <> :home
                 AND rs_ep.station_id <> :uni
                JOIN routes r ON r.route_id = rs_uni.route_id AND r.is_active = TRUE
                WHERE rs_uni.station_id = :uni
            )
            SELECT 1
            FROM r1_candidates r1
            JOIN r2_candidates r2
              ON r1.route_id <> r2.route_id
            WHERE
              -- Cele 2 rute trebuie sa imparta cel putin o statie (transfer point).
              -- In cazul tipic, transfer point = r1.ep_station (= statia unde se
              -- incheie primul leg) si trebuie sa apara si pe r2.
              EXISTS (
                  SELECT 1 FROM route_stops rs_common
                  WHERE rs_common.route_id = r2.route_id
                    AND rs_common.station_id = r1.ep_station
              )
            LIMIT 1
            """
        ),
        {"home": home_id, "uni": uni_id, "dep": dep_id, "arr": arr_id},
    ).first()

    if transfer_match:
        return {"match": True, "match_kind": "transfer_segment"}

    return {"match": False, "match_kind": None}


def _personal_route_status(
    db: Session,
    user_id: int,
    dep_station_id: int,
    arr_station_id: int,
) -> dict:
    """
    Verifica daca (dep, arr) face parte din traseul personal al studentului
    (legatura home_station <-> universitate), inclusiv ca segment intermediar
    sau ca leg al unei calatorii cu schimbare.

    Conform OUG 11/2024, reducerea de 90% pentru studenti se aplica pe
    "transportul intern feroviar intre localitatea de domiciliu si cea
    a institutiei de invatamint". Implementarea acopera:
      - Calatorii directe home <-> uni (endpoint exact).
      - Segmente intermediare pe o ruta directa (ex: Faurei->Buzau ca parte
        din Faurei->Bucuresti).
      - Segmente dintr-o calatorie cu transfer (ex: Buzau->Bucuresti dintr-o
        calatorie Faurei->Buzau->Bucuresti).

    Returneaza dict cu cheile:
        is_personal_route: bool
        reason: str
        home_station_id: int|None
        university_station_id: int|None
        match_kind: str|None  -- 'endpoint' / 'direct_segment' / 'transfer_segment'
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

    seg = _segment_on_personal_path(db, home_id, uni_id, dep_station_id, arr_station_id)
    home_name = row["home_station_name"]
    uni_name = row["university_station_name"]

    if seg["match"]:
        kind = seg["match_kind"]
        if kind == "endpoint":
            reason = (
                f"Ruta personala ({home_name} <-> {uni_name}). "
                f"Reducerea de student se aplica."
            )
        elif kind == "direct_segment":
            reason = (
                f"Segment pe traseul personal ({home_name} <-> {uni_name}). "
                f"Reducerea de student se aplica conform OUG 11/2024."
            )
        else:  # transfer_segment
            reason = (
                f"Segment al unei calatorii cu schimbare pe traseul personal "
                f"({home_name} <-> {uni_name}). Reducerea de student se aplica "
                f"conform OUG 11/2024."
            )
        return {
            "is_personal_route": True,
            "reason": reason,
            "home_station_id": home_id,
            "university_station_id": uni_id,
            "match_kind": kind,
        }

    return {
        "is_personal_route": False,
        "reason": (
            f"Ruta nu corespunde traseului tau personal ({home_name} <-> "
            f"{uni_name}). Tarif intreg conform OUG 11/2024."
        ),
        "home_station_id": home_id,
        "university_station_id": uni_id,
        "match_kind": None,
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
    # Validare: nu poti cumpara bilet pe aceeasi statie (origin == destination)
    if departure_station_id == arrival_station_id:
        raise HTTPException(
            status_code=400,
            detail="Statia de plecare si cea de sosire trebuie sa fie diferite.",
        )

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
        # FIX Bug #28: daca dep si arr sunt foarte apropiate (ex: <1km),
        # NU facem fallback la total_km (suprapret). Folosim minim 1km.
        if distance_km < 1:
            distance_km = 1.0
    else:
        # Statiile NU sunt in route_stops pentru acest tren. Doua scenarii:
        # 1. Date demo/test simplificate (lipsa route_stops pe rute scurte)
        # 2. User cere o relatie invalida
        # Compromis: folosim total_distance_km / 2 (estimare la mijloc), max 100km
        # pentru a NU plati pretul rutei intregi cand relatia e mai scurta.
        distance_km = min(float(total_km or 50.0) / 2.0, 100.0)
        if distance_km < 1:
            distance_km = 50.0  # fallback minim acceptabil

    base_single = _lookup_base_price(db, distance_km, train_type, train_class)
    # Case-insensitive match pentru ticket_type (Return / RETURN / return).
    normalized_ticket_type = (ticket_type or "").strip().lower()
    multiplier = RETURN_MULTIPLIER if normalized_ticket_type == "return" else 1.0
    base_total = round(base_single * multiplier, 2)

    # Discountul de utilizator (student / elev) se aplica DOAR pe ruta
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


@router.get("/stations/suggest")
def suggest_stations_from_address(
    address: str = "",
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Sugereaza gari de provenienta pe baza adresei CI.

    Strategie:
    1. Parseaza judetul din adresa (Jud. XXX / Sector N / Bucuresti)
    2. Returneaza statiile populare DIN acel judet, sortate dupa popularitate

    Daca judetul nu poate fi detectat, returneaza statii populare nationale
    (fallback ca utilizatorul sa caute manual).

    Raspuns: {
        "detected_county": str | None,
        "stations": [{station_id, name, city, county, code, popularity}]
    }
    """
    from app.core.romania_geo import county_from_address

    detected = county_from_address(address)
    if detected:
        rows = db.execute(
            text(
                """
                SELECT s.station_id, s.name, s.city, s.county, s.code,
                       COUNT(rs.route_stop_id) AS popularity
                FROM stations s
                LEFT JOIN route_stops rs ON rs.station_id = s.station_id
                WHERE s.is_active = TRUE AND s.county = :county
                GROUP BY s.station_id
                ORDER BY popularity DESC, s.name ASC
                LIMIT :lim
                """
            ),
            {"county": detected, "lim": limit},
        ).mappings().all()
    else:
        # Fallback: top statii nationale
        rows = db.execute(
            text(
                """
                SELECT s.station_id, s.name, s.city, s.county, s.code,
                       COUNT(rs.route_stop_id) AS popularity
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

    return {
        "detected_county": detected,
        "stations": [dict(r) for r in rows],
    }


@router.get("/trips/suggest")
def suggest_trips(
    from_station_id: int,
    to_station_id: int,
    travel_date: str,
    departure_after: Optional[str] = None,
    top_n: int = 5,
    db: Session = Depends(get_db),
):
    """
    Sugereaza itinerarii (directe + cu 1-2 schimbari) intre 2 statii.

    Cazul de uz principal:
      Studentul din Faurei vrea acasa, nu exista tren direct din Bucuresti la
      ora dorita. Sistemul gaseste: BUC -> Buzau (IR ora 14:00) + schimbare ->
      Buzau -> Faurei (R ora 17:00).

    Sortare: timp total minim, apoi nr schimbari minim.

    Returneaza max 5 itinerarii (configurabil prin top_n, 1-10).
    """
    from app.services.trip_planner import plan_trips

    if top_n < 1 or top_n > 10:
        raise HTTPException(status_code=400, detail="top_n trebuie intre 1 si 10")

    if from_station_id == to_station_id:
        raise HTTPException(
            status_code=400,
            detail="Statia de plecare si cea de sosire trebuie sa fie diferite.",
        )

    try:
        td = datetime.strptime(travel_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="travel_date format invalid (YYYY-MM-DD)")

    if td < date.today():
        raise HTTPException(status_code=400, detail="travel_date e in trecut")

    dep_after_min = None
    if departure_after:
        try:
            t = datetime.strptime(departure_after, "%H:%M").time()
            dep_after_min = t.hour * 60 + t.minute
        except ValueError:
            raise HTTPException(status_code=400, detail="departure_after format invalid (HH:MM)")

    trips = plan_trips(
        db,
        from_station_id=from_station_id,
        to_station_id=to_station_id,
        travel_date=td,
        departure_after_minutes=dep_after_min,
        top_n=top_n,
    )

    return {
        "from_station_id": from_station_id,
        "to_station_id": to_station_id,
        "travel_date": td.isoformat(),
        "count": len(trips),
        "trips": trips,
    }


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
    # IMPORTANT: filtram doar statiile care apar cel putin o data ca oprire COMERCIALA
    # (is_commercial_stop = TRUE). Nodurile tehnice (ramificatii, triaje, halte de
    # trecere cu TipOprire='N' din XML CFR) nu pot fi alese ca origine/destinatie
    # de un calator -- trenul nu opreste acolo pentru imbarcare. Popularitatea
    # reflecta nr. de aparitii ca oprire reala (trafic comercial estimat).
    if len(q) < 2:
        rows = db.execute(
            text(
                """
                SELECT s.station_id, s.name, s.city, s.code,
                       COUNT(rs.route_stop_id) AS popularity
                FROM stations s
                JOIN route_stops rs
                  ON rs.station_id = s.station_id
                 AND rs.is_commercial_stop = TRUE
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
                SELECT s.station_id, s.name, s.city, s.code,
                       COUNT(rs.route_stop_id) AS popularity
                FROM stations s
                JOIN route_stops rs
                  ON rs.station_id = s.station_id
                 AND rs.is_commercial_stop = TRUE
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


def _build_subscription_recommendation(
    db: Session,
    user_id: int,
    departure_station_id: int,
    arrival_station_id: int,
    current_ticket_price: float,
) -> Optional[dict]:
    """
    Verifica daca userul ar economisi cumparand un abonament in loc de bilete individuale.

    Logica:
      1. Cate bilete a cumparat utilizatorul in ULTIMELE 30 ZILE pe aceasta ruta
         (in orice directie)?
      2. Daca >= 3, calculeaza ce ar costa un abonament monthly pentru ruta.
      3. Estimeaza ce ar plati userul pentru ramasita lunii in bilete individuale.
      4. Daca abonamentul e mai ieftin → returneaza recomandare cu pricing concret.

    Returneaza None daca nu merita recomandare.
    """
    from app.services.subscription_business import (
        compute_subscription_price,
        get_route_distance_km,
        is_student_route_for_user,
    )

    # Verifica daca userul are deja abonament activ pe ruta (nu mai recomandam)
    existing_sub = db.execute(
        text("""
            SELECT subscription_id FROM subscriptions
            WHERE user_id = :uid
              AND status = 'active'
              AND subscription_scope = 'route'
              AND valid_until >= CURRENT_DATE
              AND (
                   (from_station_id = :a AND to_station_id = :b)
                OR (from_station_id = :b AND to_station_id = :a)
              )
            LIMIT 1
        """),
        {"uid": user_id, "a": departure_station_id, "b": arrival_station_id},
    ).first()
    if existing_sub:
        return None  # are deja abonament, nu recomandam altul

    # Numara cumparari recente pe ruta (orice directie), doar bilete proprii
    # (passenger_name IS NULL = cumparat pentru sine, nu pentru altcineva)
    count_row = db.execute(
        text("""
            SELECT COUNT(*) FROM tickets
            WHERE user_id = :uid
              AND ticket_status IN ('active', 'used')
              AND passenger_name IS NULL
              AND purchase_time >= CURRENT_DATE - INTERVAL '30 days'
              AND (
                   (departure_station_id = :a AND arrival_station_id = :b)
                OR (departure_station_id = :b AND arrival_station_id = :a)
              )
        """),
        {"uid": user_id, "a": departure_station_id, "b": arrival_station_id},
    ).first()
    recent_count = int(count_row[0] if count_row else 0)

    # Threshold: minim 3 cumparari/luna pentru a recomanda abonament
    if recent_count < 3:
        return None

    # Calcul pret abonament monthly
    distance_km = get_route_distance_km(db, departure_station_id, arrival_station_id)
    if distance_km is None or distance_km <= 0:
        return None

    student_status = is_student_route_for_user(
        db, user_id, departure_station_id, arrival_station_id,
    )
    is_student = student_status.get("is_match", False)

    sub_base, sub_discount, sub_final = compute_subscription_price(
        distance_km=distance_km,
        subscription_type="monthly",
        is_student_route=is_student,
    )

    # Estimeaza cat ar mai cumpara in restul lunii
    # Conservativ: 1 cumparare aditionala / saptamana ramasa
    from datetime import date as _date
    today = _date.today()
    days_remaining_in_month = 30  # presupunem mereu o luna completa pt simplitate
    # Mai realist: extrapolam frecventa curenta
    # ex: 5 cumparari in 30 zile -> ar mai face inca 5 cumparari/30 zile
    projected_tickets_remaining = recent_count

    estimated_cost_individual = projected_tickets_remaining * current_ticket_price * 2  # 2x = dus + intors estimat
    saving = round(estimated_cost_individual - sub_final, 2)

    if saving <= 0:
        return None  # abonamentul nu economiseste, nu recomandam

    return {
        "recent_tickets_count": recent_count,
        "subscription_price": sub_final,
        "subscription_base_price": sub_base,
        "subscription_discount": sub_discount,
        "estimated_individual_cost": round(estimated_cost_individual, 2),
        "estimated_saving_ron": saving,
        "message": (
            f"Ai cumparat {recent_count} bilete pe aceasta ruta in ultima luna. "
            f"Un abonament monthly te-ar costa {sub_final:.0f} RON in loc de ~"
            f"{estimated_cost_individual:.0f} RON in bilete individuale. "
            f"Economisesti {saving:.0f} RON pe luna."
        ),
        "suggestion_type": "monthly_subscription",
    }


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

    Include si o recomandare opciunala de abonament (daca userul cumpara
    frecvent pe aceasta ruta si ar economisi).
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
    # Numar pasageri (din passengers sau seat_ids; minim 1)
    n_pax = max(
        1,
        len(payload.passengers) if payload.passengers else
        (len(payload.seat_ids) if payload.seat_ids else 1),
    )

    # Cati pasageri sunt "pentru mine" (passenger_name = null)?
    if payload.passengers:
        n_self = sum(
            1 for p in payload.passengers
            if p.passenger_name is None or (p.passenger_name or "").strip() == ""
        )
    else:
        n_self = 1  # comportament legacy: fara lista => 1 bilet pentru sine
    n_others = n_pax - n_self
    buyer_is_passenger = n_self > 0

    has_discount = (discount > 0)

    covering_sub = None
    try:
        travel_date_for_sub = datetime.strptime(payload.travel_date, "%Y-%m-%d").date()
        covering_sub = find_active_subscription_for_route(
            db=db,
            user_id=user["user_id"],
            from_station_id=payload.departure_station_id,
            to_station_id=payload.arrival_station_id,
            travel_date=travel_date_for_sub,
        )
    except Exception:
        covering_sub = None
    # Abonamentul / discountul se aplica NUMAI daca cumparatorul calatoreste si el.
    subscription_covers_holder = (covering_sub is not None) and buyer_is_passenger

    # Calcul total tichete:
    #   - biletele "pentru mine" (n_self): pret cu discount / 0 daca abonament
    #   - biletele "pentru altcineva" (n_others): tarif intreg mereu
    if not buyer_is_passenger:
        # Toate biletele pentru altii -> tarif intreg, fara discount
        price_holder_effective = base_price
        price_companion_effective = base_price
        total_for_seats = round(base_price * n_pax, 2)
        savings = 0.0
    elif subscription_covers_holder:
        price_holder_effective = 0.0
        price_companion_effective = base_price
        total_for_seats = round(base_price * n_others, 2)
        savings = round(base_price * n_self, 2)
    elif has_discount and n_others > 0:
        # Biletele proprii cu discount; biletele altora la pret intreg
        price_holder_effective = price
        price_companion_effective = base_price
        total_for_seats = round(price * n_self + base_price * n_others, 2)
        savings = round((base_price - price) * n_self, 2)
    else:
        price_holder_effective = price
        price_companion_effective = price
        total_for_seats = round(price * n_pax, 2)
        savings = round((base_price - price) * n_pax, 2)

    # Recomandare abonament (silent failure - nu blocam quote daca crapa)
    subscription_recommendation = None
    try:
        subscription_recommendation = _build_subscription_recommendation(
            db,
            user["user_id"],
            payload.departure_station_id,
            payload.arrival_station_id,
            price,
        )
    except Exception:
        subscription_recommendation = None

    return {
        "base_price": base_price,
        "discount_percent": discount,
        "final_price": price,                            # pret cumparator cu discount student (backwards compat)
        "price_per_seat": price,                         # alias - DEPRECATED
        "price_holder": price_holder_effective,          # pret efectiv titular (0 daca acoperit de abonament)
        "price_companion": price_companion_effective,    # pret efectiv insotitor (mereu intreg cand exista discount/abonament)
        "total_for_seats": total_for_seats,
        "passenger_count": n_pax,
        "distance_km": distance_km,
        "ticket_type": payload.ticket_type,
        "savings": savings,
        "is_personal_route": route_status["is_personal_route"],
        "route_reason": route_status["reason"],
        "home_station_id": route_status["home_station_id"],
        "university_station_id": route_status["university_station_id"],
        "subscription_recommendation": subscription_recommendation,
        # ===== Flag-uri abonament (UI le foloseste sa explice de ce price_holder=0) =====
        "subscription_covers_holder": subscription_covers_holder,
        "subscription_id": covering_sub["subscription_id"] if covering_sub else None,
    }

@router.post("/tickets/quote-journey")
def quote_journey(
    payload: BuyJourneyRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Calculeaza pretul unui journey multi-leg FARA a cumpara.
    Returneaza pretul per segment (cu/fara reducere) si totalul.
    Folosit de UI pentru a arata pretul inainte de confirmare.
    """
    user = _extract_user_from_token(authorization, db)

    # Verifică dacă journey-ul total (prima dep → ultima arr) e ruta personală.
    # Dacă da, reducerea se aplică la TOATE leg-urile chiar dacă per-leg nu trece testul.
    journey_discount_pct = 0.0
    journey_is_personal = False
    journey_sub_covers = False  # abonament acoperă întregul journey → titular călătorește gratuit

    first_dep = payload.legs[0].departure_station_id
    last_arr = payload.legs[-1].arrival_station_id

    # Verifică abonament pentru întreaga călătorie (primul dep → ultimul arr)
    try:
        td0 = datetime.strptime(payload.legs[0].travel_date, "%Y-%m-%d").date()
        covering_sub = find_active_subscription_for_route(
            db=db, user_id=user["user_id"],
            from_station_id=first_dep, to_station_id=last_arr,
            travel_date=td0,
        )
        if covering_sub:
            journey_sub_covers = True
    except Exception:
        covering_sub = None

    if not journey_sub_covers and len(payload.legs) > 1:
        overall_status = _personal_route_status(db, user["user_id"], first_dep, last_arr)
        if overall_status["is_personal_route"]:
            journey_discount_pct = _user_discount(db, user["user_id"])
            journey_is_personal = True
    elif not journey_sub_covers:
        overall_status = _personal_route_status(db, user["user_id"], first_dep, last_arr)
        if overall_status["is_personal_route"]:
            journey_discount_pct = _user_discount(db, user["user_id"])
            journey_is_personal = True

    leg_quotes = []
    total_base = 0.0
    total_final = 0.0
    any_discount = False

    for i, leg in enumerate(payload.legs, 1):
        try:
            td = datetime.strptime(leg.travel_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Leg {i}: travel_date invalid")

        train_row = db.execute(
            text("SELECT train_id, train_number, train_type FROM trains WHERE train_id = :tid AND is_active = TRUE"),
            {"tid": leg.train_id},
        ).first()
        if not train_row:
            raise HTTPException(status_code=404, detail=f"Leg {i}: trenul {leg.train_id} nu există")

        dep_name = db.execute(text("SELECT name FROM stations WHERE station_id = :s"), {"s": leg.departure_station_id}).scalar()
        arr_name = db.execute(text("SELECT name FROM stations WHERE station_id = :s"), {"s": leg.arrival_station_id}).scalar()

        final_price, leg_discount_pct, base_price, distance_km, route_status = _compute_price(
            db,
            user["user_id"],
            payload.ticket_type,
            leg.train_id,
            leg.departure_station_id,
            leg.arrival_station_id,
        )

        # Abonamentul are prioritate: dacă acoperă journey-ul → titular merge gratuit
        if journey_sub_covers:
            final_price = 0.0
            leg_discount_pct = 100.0
            route_status = {**route_status, "is_personal_route": True}
        else:
            # Ia maximul dintre discountul per-leg și discountul journey total
            effective_discount = max(leg_discount_pct, journey_discount_pct)
            if effective_discount > leg_discount_pct and effective_discount > 0:
                final_price = round(base_price * (1 - effective_discount / 100), 2)
                leg_discount_pct = effective_discount
                route_status = {**route_status, "is_personal_route": True}

        if leg_discount_pct > 0:
            any_discount = True

        total_base += base_price
        total_final += final_price

        leg_quotes.append({
            "leg_order": i,
            "train_id": leg.train_id,
            "train_number": train_row[1],
            "train_type": train_row[2],
            "departure_station": dep_name,
            "arrival_station": arr_name,
            "travel_date": str(td),
            "base_price": round(base_price, 2),
            "final_price": round(final_price, 2),
            "discount_percent": leg_discount_pct,
            "is_personal_route": route_status["is_personal_route"],
            "route_reason": route_status["reason"],
            "subscription_covers": journey_sub_covers,
        })

    overall_is_personal = journey_is_personal or journey_sub_covers or any(l["is_personal_route"] for l in leg_quotes)
    effective_pct = max((l["discount_percent"] for l in leg_quotes), default=0.0)

    return {
        "legs": leg_quotes,
        "total_base": round(total_base, 2),
        "total_final": round(total_final, 2),
        "total_savings": round(total_base - total_final, 2),
        "any_discount": any_discount,
        "discount_percent": effective_pct,
        "is_personal_route": overall_is_personal,
        "subscription_covers": journey_sub_covers,
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

    # Verifica duplicat DOAR daca noua comanda include un bilet pentru cumparator
    # (passenger_name = null). Daca toate biletele sunt pentru altii, nu blocam.
    buyer_is_passenger = not payload.passengers or any(
        (p.passenger_name is None or (p.passenger_name or "").strip() == "")
        for p in payload.passengers
    )
    if buyer_is_passenger:
        own_duplicate = db.execute(
            text("""
                SELECT ticket_id FROM tickets
                WHERE user_id = :uid
                  AND train_id = :tid
                  AND travel_date = :td
                  AND ticket_status = 'active'
                  AND passenger_name IS NULL
                LIMIT 1
            """),
            {"uid": user["user_id"], "tid": payload.train_id, "td": travel_date},
        ).first()
        if own_duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "overlap",
                    "message": "Ai deja un bilet activ pe acest tren pentru tine. "
                               "Daca vrei sa adaugi pasageri suplimentari, adauga-i la cumparatura initiala.",
                    "conflicting_ticket_id": own_duplicate[0],
                },
            )

    # Anti-overlap: nu permitem 2 bilete active in intervale orare suprapuse
    # pentru acelasi user. Folosim orele SEGMENTULUI biletului (dep/arr statii),
    # nu orele rutei intregi (Bug #38). Raise 409 cu detalii.
    check_overlap(
        db, user["user_id"], payload.train_id, travel_date,
        departure_station_id=payload.departure_station_id,
        arrival_station_id=payload.arrival_station_id,
    )

    # Verificare abonament activ care acopera ruta (pentru gratuitate automata).
    # Daca user-ul are subscription_scope='route' activ pe (from,to) sau (to,from),
    # biletul va fi gratuit (price=0) si va fi marcat cu uses_subscription_id.
    _covering_sub = find_active_subscription_for_route(
        db,
        user_id=user["user_id"],
        from_station_id=payload.departure_station_id,
        to_station_id=payload.arrival_station_id,
        travel_date=travel_date,
    )

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
        # Multi-pasager: daca avem payload.passengers, cream N bilete (1 per pasager).
        # Daca nu, comportament legacy: 1 bilet + opional seat_ids cu acelasi pasager.
        if payload.passengers and len(payload.passengers) > 0:
            passengers_list = list(payload.passengers)
            # Validare: pentru pasagerii suplimentari (indicele >= 1),
            # passenger_name este obligatoriu (cumparatorul prezinta nume CI proprii).
            for idx, pax in enumerate(passengers_list):
                if idx == 0:
                    continue  # primul pasager = cumparatorul (numele vine din users)
                name = (pax.passenger_name or "").strip()
                if not name:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Numele pasagerului {idx + 1} este obligatoriu "
                            "(va aparea la control si pe bilet)."
                        ),
                    )
        elif payload.seat_ids:
            # Legacy: cumparator = pasager pentru fiecare loc
            passengers_list = [
                PassengerSeat(seat_id=sid, passenger_name=None)
                for sid in payload.seat_ids
            ]
        else:
            # Fara loc, 1 bilet fara seat
            passengers_list = [None]

        import hashlib
        valid_until = datetime.combine(travel_date, datetime.max.time())
        created_tickets = []

        # === Auto-asignare locuri pentru pasagerii fara seat_id explicit ===
        # Cerinta UX: biletul trebuie sa aiba INTOTDEAUNA vagon+loc afisat
        # (conductorul are nevoie de el la verificare). Daca utilizatorul nu si-a
        # ales locul, alocam automat primul disponibil din tren.
        from app.services.ticket_business import pick_available_seats, hold_seat
        # Pentru fallback-ul legacy `passengers_list = [None]` (cumparare fara
        # seats specificate explicit), transformam in obiecte PassengerSeat ca
        # sa putem aplica auto-asignarea uniform fara AttributeError pe None.
        passengers_list = [
            p if p is not None else PassengerSeat(seat_id=None, passenger_name=None)
            for p in passengers_list
        ]
        explicit_seat_ids = [p.seat_id for p in passengers_list if p.seat_id]
        n_missing = sum(1 for p in passengers_list if not p.seat_id)
        if n_missing > 0:
            # Verificam intai daca trenul are deloc layout (train_cars + seats).
            # Trenurile legacy / sandbox pot exista fara layout — in acel caz nu
            # putem auto-asigna locuri, dar nici nu blocam cumpararea: biletul ramane
            # fara loc (cum era inainte de feature-ul de auto-asignare).
            total_seats_in_train = db.execute(
                text("""
                    SELECT COUNT(*) FROM seats s
                    JOIN train_cars tc ON tc.train_car_id = s.train_car_id
                    WHERE tc.train_id = :tid
                """),
                {"tid": payload.train_id},
            ).scalar() or 0

            if total_seats_in_train == 0:
                # Tren fara layout — skip auto-asignare, biletul va fi fara loc.
                pass
            else:
                auto_seats = pick_available_seats(
                    db=db,
                    train_id=payload.train_id,
                    travel_date=travel_date,
                    n=n_missing,
                    excluded=explicit_seat_ids,
                )
                if len(auto_seats) < n_missing:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "no_seats_available",
                            "message": (
                                f"Nu mai sunt suficiente locuri libere in trenul "
                                f"{payload.train_id} pentru {n_missing} pasager(i). "
                                f"Mai sunt doar {len(auto_seats)} disponibile."
                            ),
                        },
                    )
                # Hold rapid pe locurile auto-asignate ca sa treaca verificarea
                # din confirm_seats_for_ticket (care cere ca seat_id sa fie in
                # seat_reservations pentru userul curent). Daca alt user a luat
                # locul intre timp, hold_seat arunca 409 (rollback tranzactie).
                auto_iter = iter(auto_seats)
                for pax in passengers_list:
                    if not pax.seat_id:
                        pax.seat_id = next(auto_iter)
                        hold_seat(
                            db=db,
                            user_id=user["user_id"],
                            seat_id=pax.seat_id,
                            train_id=payload.train_id,
                            travel_date=travel_date,
                        )

        for pax_idx, current_passenger in enumerate(passengers_list):
            current_seat_id = current_passenger.seat_id if current_passenger else None
            current_name = (
                (current_passenger.passenger_name or "").strip() or None
                if current_passenger else None
            )
            # Discountul (abonament / student) se aplica DOAR la biletul cumparatorului
            # insusi (passenger_name IS NULL). Daca biletul e cumparat pentru altcineva,
            # se aplica tariful intreg — abonamentul si credentialul sunt nominale/personale.
            is_self_ticket = (current_name is None)
            apply_subscription_discount = (_covering_sub is not None and is_self_ticket)

            if is_self_ticket:
                ticket_price = price
                ticket_discount = discount
            else:
                ticket_price = base_price
                ticket_discount = 0.0

            # 1. Insereaza biletul (cu passenger_name optional)
            ticket = db.execute(
                text(
                    """
                    INSERT INTO tickets (
                        user_id, train_id, departure_station_id, arrival_station_id,
                        travel_date, ticket_type, ticket_status, price, discount_applied,
                        passenger_name
                    )
                    VALUES (
                        :uid, :tid, :dep_id, :arr_id,
                        :travel_date, :ticket_type, 'active', :price, :discount,
                        :passenger_name
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
                    "price": ticket_price,
                    "discount": ticket_discount,
                    "passenger_name": current_name,
                },
            ).mappings().first()

            # 2. Travel entitlement
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

            # 3. QR token single-use (UNUL per bilet/pasager)
            token_value = secrets.token_urlsafe(32)
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

            # 4a. Abonament activ acopera ruta -> bilet gratuit (DOAR primul pasager)
            if apply_subscription_discount:
                db.execute(
                    text("""
                        UPDATE tickets
                        SET price = 0, discount_applied = 100,
                            uses_subscription_id = :sub_id
                        WHERE ticket_id = :tid
                    """),
                    {"sub_id": _covering_sub["subscription_id"], "tid": ticket["ticket_id"]},
                )

            # 4. Confirma locul rezervat pentru acest bilet
            if current_seat_id:
                confirm_seats_for_ticket(
                    db,
                    ticket_id=ticket["ticket_id"],
                    user_id=user["user_id"],
                    seat_ids=[current_seat_id],
                    travel_date=travel_date,
                )

            created_tickets.append({
                "ticket_id": ticket["ticket_id"],
                "ticket_type": ticket["ticket_type"],
                "travel_date": str(ticket["travel_date"]),
                "price": 0.0 if apply_subscription_discount else float(ticket["price"]),
                "passenger_name": current_name,
                "seat_id": current_seat_id,
                "qr_token": qr["token_value"],
                "qr_expires_at": (
                    qr["expires_at"].isoformat(timespec="seconds") + "Z"
                    if qr.get("expires_at") else None
                ),
            })

        db.commit()

        first = created_tickets[0]
        total_price = sum(t["price"] for t in created_tickets)
        return {
            # Legacy compatibility - primul bilet la radacina
            "ticket_id": first["ticket_id"],
            "ticket_type": first["ticket_type"],
            "travel_date": first["travel_date"],
            "price": first["price"],
            "discount_applied": discount,
            "is_personal_route": route_status["is_personal_route"],
            "route_reason": route_status["reason"],
            "qr_token": first["qr_token"],
            "qr_expires_at": first["qr_expires_at"],
            # Multi-pasager
            "tickets": created_tickets,
            "total_price": round(total_price, 2),
            "count": len(created_tickets),
            "message": (
                f"{len(created_tickets)} bilete cumparate cu succes."
                if len(created_tickets) > 1
                else "Bilet cumparat cu succes. Prezinta QR-ul controlorului."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Eroare la cumparare: {exc}")


@router.post("/tickets/buy-journey")
def buy_journey(
    payload: BuyJourneyRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Cumpără un journey cu 1–3 segmente de tren într-o singură tranzacție.
    Creează un ticket (container) și N ticket_legs (câte un row per tren).
    Fiecare leg primește un QR token propriu, scanabil de inspectorul de tren.
    """
    import hashlib

    user = _extract_user_from_token(authorization, db)
    if not has_role(user["role"], ROLE_PASSENGER):
        raise HTTPException(status_code=403, detail="Doar pasagerii pot cumpăra bilete")

    if not payload.legs:
        raise HTTPException(status_code=400, detail="Journey-ul trebuie să aibă cel puțin un segment")

    from app.services.ticket_business import pick_available_seats, hold_seat

    passengers_list = payload.passengers  # garantat 1-4 elemente via Field validator
    n_pax = len(passengers_list)

    # ── 1. Validare și parsare date per leg ──────────────────────────────────
    parsed_legs = []
    for i, leg in enumerate(payload.legs, 1):
        try:
            td = datetime.strptime(leg.travel_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Leg {i}: travel_date invalid (YYYY-MM-DD)")
        if td < datetime.now(timezone.utc).date():
            raise HTTPException(status_code=400, detail=f"Leg {i}: data călătoriei nu poate fi în trecut")
        if leg.departure_station_id == leg.arrival_station_id:
            raise HTTPException(status_code=400, detail=f"Leg {i}: stația de plecare = sosire")

        train = db.execute(
            text("SELECT train_id, route_id FROM trains WHERE train_id = :tid AND is_active = TRUE"),
            {"tid": leg.train_id},
        ).first()
        if not train:
            raise HTTPException(status_code=404, detail=f"Leg {i}: trenul {leg.train_id} nu există")

        # seat_ids[pax_idx] = locul pasagerului j pe acest leg (None = auto)
        raw_sids = leg.seat_ids or []
        seat_ids = list(raw_sids) + [None] * (n_pax - len(raw_sids))
        seat_ids = seat_ids[:n_pax]

        parsed_legs.append({
            "leg_order": i,
            "train_id": leg.train_id,
            "departure_station_id": leg.departure_station_id,
            "arrival_station_id": leg.arrival_station_id,
            "travel_date": td,
            "seat_ids": seat_ids,  # list[int|None], len = n_pax
        })

    # ── 2. Calcul preț per leg (base + final pentru titular) ─────────────────
    first_dep = parsed_legs[0]["departure_station_id"]
    last_arr = parsed_legs[-1]["arrival_station_id"]
    td0 = parsed_legs[0]["travel_date"]

    # Verifică dacă abonamentul activ acoperă întreaga rută (titular călătorește gratuit)
    journey_sub_covers = False
    try:
        covering_sub = find_active_subscription_for_route(
            db=db, user_id=user["user_id"],
            from_station_id=first_dep, to_station_id=last_arr,
            travel_date=td0,
        )
        if covering_sub:
            journey_sub_covers = True
    except Exception:
        pass

    # Discount pe rută personală (se aplică dacă abonamentul nu acoperă)
    journey_discount_pct = 0.0
    if not journey_sub_covers and len(parsed_legs) > 1:
        overall_status = _personal_route_status(db, user["user_id"], first_dep, last_arr)
        if overall_status["is_personal_route"]:
            journey_discount_pct = _user_discount(db, user["user_id"])

    leg_base_prices = []   # base_price per leg (fără discount)
    leg_self_prices = []   # prețul titularului per leg (cu discount max)
    leg_discounts = []     # discount_pct efectiv per leg pentru titular

    for leg_data in parsed_legs:
        final_price, leg_discount_pct, base_price, _, _ = _compute_price(
            db, user["user_id"], payload.ticket_type,
            leg_data["train_id"],
            leg_data["departure_station_id"],
            leg_data["arrival_station_id"],
        )
        if journey_sub_covers:
            self_price = 0.0
            effective_discount = 100.0
        else:
            effective_discount = max(leg_discount_pct, journey_discount_pct)
            if effective_discount > 0:
                self_price = round(base_price * (1 - effective_discount / 100), 2)
            else:
                self_price = final_price
        leg_base_prices.append(base_price)
        leg_self_prices.append(self_price)
        leg_discounts.append(effective_discount)

    # ── 3. Auto-asignare locuri per leg per pasager ──────────────────────────
    for leg_idx, leg_data in enumerate(parsed_legs):
        # Colectăm locurile deja atribuite (să nu le alocăm de două ori)
        already_assigned = [s for s in leg_data["seat_ids"] if s]
        need_auto = [pax_idx for pax_idx, sid in enumerate(leg_data["seat_ids"]) if not sid]
        if not need_auto:
            continue

        total_in_train = db.execute(
            text("""
                SELECT COUNT(*) FROM seats s
                JOIN train_cars tc ON tc.train_car_id = s.train_car_id
                WHERE tc.train_id = :tid
            """),
            {"tid": leg_data["train_id"]},
        ).scalar() or 0
        if total_in_train == 0:
            continue  # tren fără hartă locuri — merge fără loc

        auto = pick_available_seats(
            db=db, train_id=leg_data["train_id"],
            travel_date=leg_data["travel_date"],
            n=len(need_auto), excluded=already_assigned,
        )
        if not auto and need_auto:
            raise HTTPException(
                status_code=409,
                detail={"error": "no_seats_available",
                        "message": f"Leg {leg_idx+1}: nu mai sunt {len(need_auto)} locuri libere în trenul {leg_data['train_id']}"}
            )
        for pax_idx, seat_id in zip(need_auto, auto or []):
            leg_data["seat_ids"][pax_idx] = seat_id
            hold_seat(db=db, user_id=user["user_id"], seat_id=seat_id,
                      train_id=leg_data["train_id"], travel_date=leg_data["travel_date"])

    # ── 4. Info tren + stații (fetch o singură dată) ─────────────────────────
    train_infos = {}
    station_names = {}
    for leg_data in parsed_legs:
        tid = leg_data["train_id"]
        if tid not in train_infos:
            row = db.execute(
                text("SELECT train_number, train_type FROM trains WHERE train_id = :tid"),
                {"tid": tid},
            ).mappings().first()
            train_infos[tid] = row
        for sid in [leg_data["departure_station_id"], leg_data["arrival_station_id"]]:
            if sid not in station_names:
                station_names[sid] = db.execute(
                    text("SELECT name FROM stations WHERE station_id = :s"), {"s": sid}
                ).scalar()

    first_leg = parsed_legs[0]
    last_leg = parsed_legs[-1]

    # ── 5. Creare câte un ticket container + legs pentru fiecare pasager ─────
    try:
        all_ticket_ids = []
        all_passengers_data = []

        for pax_idx, pax in enumerate(passengers_list):
            pax_name = (pax.passenger_name or "").strip() or None
            is_self = (pax_name is None)

            # Prețul total al pasagerului = suma prețurilor per leg
            pax_total = 0.0
            pax_discount_sum = 0.0
            pax_leg_entries = []

            for leg_idx, leg_data in enumerate(parsed_legs):
                if is_self:
                    leg_price = leg_self_prices[leg_idx]
                    leg_discount = leg_discounts[leg_idx]
                else:
                    leg_price = leg_base_prices[leg_idx]
                    leg_discount = 0.0
                pax_total += leg_price
                pax_discount_sum += leg_discount
                pax_leg_entries.append((leg_price, leg_discount, leg_data["seat_ids"][pax_idx]))

            # Creare ticket container
            ticket = db.execute(
                text("""
                    INSERT INTO tickets (
                        user_id, train_id, departure_station_id, arrival_station_id,
                        travel_date, ticket_type, ticket_status, price, discount_applied,
                        passenger_name
                    )
                    VALUES (
                        :uid, :tid, :dep_id, :arr_id,
                        :travel_date, :ticket_type, 'active', :price, :discount,
                        :passenger_name
                    )
                    RETURNING ticket_id, travel_date, ticket_type, price
                """),
                {
                    "uid": user["user_id"],
                    "tid": first_leg["train_id"],
                    "dep_id": first_leg["departure_station_id"],
                    "arr_id": last_leg["arrival_station_id"],
                    "travel_date": first_leg["travel_date"],
                    "ticket_type": payload.ticket_type,
                    "price": round(pax_total, 2),
                    "discount": round(pax_discount_sum / len(parsed_legs), 2),
                    "passenger_name": pax_name,
                },
            ).mappings().first()
            ticket_id = ticket["ticket_id"]
            all_ticket_ids.append(ticket_id)

            # Creare ticket_legs
            created_legs = []
            for leg_idx, (leg_price, leg_discount, seat_id) in enumerate(pax_leg_entries):
                leg_data = parsed_legs[leg_idx]
                qr_token = secrets.token_urlsafe(32)
                qr_hash = hashlib.sha256(qr_token.encode()).hexdigest()

                leg_row = db.execute(
                    text("""
                        INSERT INTO ticket_legs (
                            ticket_id, leg_order, train_id,
                            departure_station_id, arrival_station_id,
                            travel_date, seat_id, price, discount_applied,
                            qr_token, qr_token_hash
                        )
                        VALUES (
                            :ticket_id, :leg_order, :train_id,
                            :dep_id, :arr_id,
                            :travel_date, :seat_id, :price, :discount,
                            :qr_token, :qr_hash
                        )
                        RETURNING leg_id, leg_order, qr_token
                    """),
                    {
                        "ticket_id": ticket_id,
                        "leg_order": leg_data["leg_order"],
                        "train_id": leg_data["train_id"],
                        "dep_id": leg_data["departure_station_id"],
                        "arr_id": leg_data["arrival_station_id"],
                        "travel_date": leg_data["travel_date"],
                        "seat_id": seat_id,
                        "price": round(leg_price, 2),
                        "discount": round(leg_discount, 2),
                        "qr_token": qr_token,
                        "qr_hash": qr_hash,
                    },
                ).mappings().first()

                if seat_id:
                    confirm_seats_for_ticket(
                        db, ticket_id=ticket_id, user_id=user["user_id"],
                        seat_ids=[seat_id], travel_date=leg_data["travel_date"],
                    )

                tinfo = train_infos.get(leg_data["train_id"])
                created_legs.append({
                    "leg_id": leg_row["leg_id"],
                    "leg_order": leg_row["leg_order"],
                    "train_id": leg_data["train_id"],
                    "train_number": tinfo["train_number"] if tinfo else None,
                    "train_type": tinfo["train_type"] if tinfo else None,
                    "departure_station": station_names.get(leg_data["departure_station_id"]),
                    "arrival_station": station_names.get(leg_data["arrival_station_id"]),
                    "travel_date": str(leg_data["travel_date"]),
                    "seat_id": seat_id,
                    "price": round(leg_price, 2),
                    "qr_token": leg_row["qr_token"],
                })

            all_passengers_data.append({
                "ticket_id": ticket_id,
                "passenger_name": pax_name,
                "is_self": is_self,
                "total_price": round(pax_total, 2),
                "legs": created_legs,
            })

        db.commit()

        grand_total = sum(p["total_price"] for p in all_passengers_data)
        return {
            # Primul ticket_id pentru redirect (backward compat)
            "ticket_id": all_ticket_ids[0],
            "ticket_type": payload.ticket_type,
            "total_price": round(grand_total, 2),
            "leg_count": len(parsed_legs),
            "passenger_count": n_pax,
            "tickets": all_passengers_data,
            "message": (
                f"{n_pax} bilet{'e' if n_pax > 1 else ''} cu {len(parsed_legs)} segmente "
                f"cumpărat{'e' if n_pax > 1 else ''} cu succes."
            ),
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Eroare la cumpărare journey: {exc}")


@router.post("/tickets/validate-leg")
def validate_leg(
    payload: ValidateTicketRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Validare QR pentru un leg dintr-un journey multi-segment."""
    import hashlib

    _extract_user_from_token(authorization, db)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()

    leg = db.execute(
        text("""
            SELECT tl.leg_id, tl.ticket_id, tl.train_id, tl.travel_date,
                   tl.departure_station_id, tl.arrival_station_id,
                   tl.qr_token, tl.price,
                   t.ticket_status, t.passenger_name, t.user_id,
                   tr.train_number,
                   s1.name AS dep_station, s2.name AS arr_station,
                   COALESCE(NULLIF(TRIM(t.passenger_name),''),
                            TRIM(CONCAT_WS(' ', u.first_name, u.last_name))) AS display_name
            FROM ticket_legs tl
            JOIN tickets t ON t.ticket_id = tl.ticket_id
            JOIN trains tr ON tr.train_id = tl.train_id
            JOIN stations s1 ON s1.station_id = tl.departure_station_id
            JOIN stations s2 ON s2.station_id = tl.arrival_station_id
            JOIN users u ON u.user_id = t.user_id
            WHERE tl.qr_token_hash = :hash
        """),
        {"hash": token_hash},
    ).mappings().first()

    if not leg:
        return {"result": "invalid", "message": "Token necunoscut sau expirat"}

    if leg["ticket_status"] not in ("active",):
        return {"result": "invalid",
                "message": f"Biletul are statusul '{leg['ticket_status']}'"}

    if leg["travel_date"] < datetime.now(timezone.utc).date():
        return {"result": "invalid", "message": "Data călătoriei a trecut"}

    return {
        "result": "valid",
        "message": "Bilet valid",
        "passenger_name": leg["display_name"],
        "train_number": leg["train_number"],
        "departure_station": leg["dep_station"],
        "arrival_station": leg["arr_station"],
        "travel_date": str(leg["travel_date"]),
        "leg_id": leg["leg_id"],
        "ticket_id": leg["ticket_id"],
    }


@router.get("/tickets/my")
def list_my_tickets(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Listeaza biletele utilizatorului curent."""
    user = _extract_user_from_token(authorization, db)

    # === Lazy expire: bilete active cu travel_date < azi devin 'expired' ===
    # Acoperim cazul in care pasagerul nu a urcat in tren (deci nicio validare
    # n-a marcat biletul ca 'used'). Trimitem o notificare per bilet expirat,
    # ca pasagerul sa stie ca biletul s-a mutat in tab-ul "Onorate".
    expired_now = db.execute(
        text("""
            UPDATE tickets
            SET ticket_status = 'expired'
            WHERE user_id = :uid
              AND ticket_status = 'active'
              AND travel_date < CURRENT_DATE
            RETURNING ticket_id, train_id, travel_date
        """),
        {"uid": user["user_id"]},
    ).mappings().all()

    if expired_now:
        # Aducem train_number pentru fiecare bilet ca sa includem in mesaj.
        train_ids = [r["train_id"] for r in expired_now]
        train_no_map = {
            t["train_id"]: t["train_number"]
            for t in db.execute(
                text("SELECT train_id, train_number FROM trains WHERE train_id = ANY(:ids)"),
                {"ids": train_ids},
            ).mappings().all()
        }
        for r in expired_now:
            train_no = train_no_map.get(r["train_id"]) or "?"
            db.execute(
                text("""
                    INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
                    VALUES (:uid, 'ticket', :title, :msg, FALSE, NOW())
                """),
                {
                    "uid": user["user_id"],
                    "title": "Bilet expirat",
                    "msg": (
                        f"Biletul pentru trenul {train_no} din {r['travel_date'].isoformat()} "
                        f"a expirat (calatoria a trecut fara validare in tren). "
                        f"L-am mutat in sectiunea \"Onorate\"."
                    ),
                },
            )
        db.commit()

    rows = db.execute(
        text(
            """
            SELECT
                t.ticket_id, t.train_id,
                t.departure_station_id, t.arrival_station_id,
                t.ticket_type, t.ticket_status, t.travel_date,
                t.price, t.discount_applied, t.purchase_time,
                t.cancel_refund_amount, t.passenger_name,
                t.uses_subscription_id,
                sub.subscription_type AS subscription_type,
                COALESCE(
                    NULLIF(TRIM(t.passenger_name), ''),
                    TRIM(CONCAT_WS(' ', u.first_name, u.last_name))
                ) AS display_passenger_name,
                s1.name AS departure_station, s1.code AS departure_code,
                s2.name AS arrival_station,   s2.code AS arrival_code,
                tr.train_number, tr.train_type,
                op.name AS operator_name,
                -- Subquery scalar pentru a evita duplicatele cauzate de
                -- multiple rânduri pe route_stops cu același station_id.
                (SELECT rs.departure_time
                 FROM route_stops rs
                 WHERE rs.route_id = tr.route_id
                   AND rs.station_id = t.departure_station_id
                 ORDER BY rs.stop_order
                 LIMIT 1) AS departure_time,
                (SELECT rs.arrival_time
                 FROM route_stops rs
                 WHERE rs.route_id = tr.route_id
                   AND rs.station_id = t.arrival_station_id
                 ORDER BY rs.stop_order DESC
                 LIMIT 1) AS arrival_time,
                COALESCE(
                    (
                        SELECT array_agg(
                            CASE
                                WHEN tc.car_number IS NOT NULL THEN
                                    'V' || tc.car_number || '-' || s.seat_label
                                ELSE s.seat_label
                            END
                            ORDER BY tc.car_number NULLS LAST, s.seat_label
                        )
                        FROM ticket_seats ts
                        JOIN seats s           ON s.seat_id = ts.seat_id
                        LEFT JOIN train_cars tc ON tc.train_car_id = s.train_car_id
                        WHERE ts.ticket_id = t.ticket_id
                    ),
                    ARRAY[]::text[]
                ) AS seats,
                -- QR token activ (single-use, valabil) pentru afisare la pasager
                (
                    SELECT qt.token_value
                    FROM qr_tokens qt
                    JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                    WHERE te.ticket_id = t.ticket_id
                      AND qt.status = 'active'
                      AND qt.expires_at > CURRENT_TIMESTAMP
                    ORDER BY qt.issued_at DESC
                    LIMIT 1
                ) AS qr_token,
                (
                    SELECT qt.expires_at
                    FROM qr_tokens qt
                    JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                    WHERE te.ticket_id = t.ticket_id
                      AND qt.status = 'active'
                      AND qt.expires_at > CURRENT_TIMESTAMP
                    ORDER BY qt.issued_at DESC
                    LIMIT 1
                ) AS qr_expires_at
            FROM tickets t
            JOIN stations s1 ON s1.station_id = t.departure_station_id
            JOIN stations s2 ON s2.station_id = t.arrival_station_id
            JOIN trains tr   ON tr.train_id = t.train_id
            JOIN railway_operators op ON op.operator_id = tr.operator_id
            LEFT JOIN subscriptions sub ON sub.subscription_id = t.uses_subscription_id
            LEFT JOIN users u ON u.user_id = t.user_id
            WHERE t.user_id = :uid
            ORDER BY t.travel_date DESC, t.purchase_time DESC
            """
        ),
        {"uid": user["user_id"]},
    ).mappings().all()
    # Lazy import - reutilizam helper-ul din identity.py
    from app.routers.identity import _build_qr_data_url

    result = []
    for r in rows:
        price_final = float(r["price"])
        discount_pct = float(r["discount_applied"] or 0)
        # Pretul intreg (inainte de reducere). Daca biletul e gratis prin abonament
        # (price=0, uses_subscription_id != NULL), nu putem deduce pretul brut
        # din procent, deci il lasam None.
        if r.get("uses_subscription_id") and price_final == 0:
            base_price = None
        elif discount_pct > 0 and discount_pct < 100:
            base_price = round(price_final / (1 - discount_pct / 100), 2)
        else:
            base_price = price_final

        # Construim lista de reduceri aplicate (detaliata pentru afisare)
        discounts = []
        if r.get("uses_subscription_id"):
            sub_type = r.get("subscription_type") or "abonament"
            discounts.append({
                "label": f"Abonament {sub_type}",
                "percent": 100.0,
                "amount": round((base_price or 0) - price_final, 2) if base_price else None,
                "kind": "subscription",
            })
        elif discount_pct > 0:
            discounts.append({
                "label": "Reducere student (ruta personala)",
                "percent": discount_pct,
                "amount": round((base_price or price_final) - price_final, 2),
                "kind": "student",
            })

        result.append({
            **dict(r),
            "travel_date": str(r["travel_date"]),
            "purchase_time": str(r["purchase_time"]),
            "price": price_final,
            "base_price": base_price,
            "discount_applied": discount_pct,
            "discounts": discounts,
            "cancel_refund_amount": float(r["cancel_refund_amount"]) if r["cancel_refund_amount"] is not None else None,
            "seats": list(r["seats"] or []),
            "qr_token": r.get("qr_token"),
            "qr_expires_at": str(r["qr_expires_at"]) if r.get("qr_expires_at") else None,
            # Data URL gata pentru <img src=...> (PNG base64) - doar daca exista token activ.
            "qr_data_url": _build_qr_data_url(r["qr_token"]) if r.get("qr_token") else None,
            # Orele plecare/sosire (din route_stops)
            "departure_time": str(r["departure_time"])[:5] if r.get("departure_time") else None,
            "arrival_time": str(r["arrival_time"])[:5] if r.get("arrival_time") else None,
            # Campuri populate de _group_journey_legs:
            "journey_group_id": None,
            "leg_index": 0,
            "total_legs": 1,
            "transfer_minutes": None,
            # Legs (populate mai jos pentru biletele cu ticket_legs)
            "legs": None,
        })

    # Fetch ticket_legs pentru biletele care au journey multi-segment
    if result:
        ticket_ids = [t["ticket_id"] for t in result]
        legs_rows = db.execute(
            text("""
                SELECT tl.leg_id, tl.ticket_id, tl.leg_order,
                       tl.train_id, tl.departure_station_id, tl.arrival_station_id,
                       tl.travel_date, tl.seat_id, tl.price, tl.discount_applied,
                       tl.qr_token,
                       tr.train_number, tr.train_type,
                       s1.name AS departure_station, s2.name AS arrival_station,
                       seat.seat_label,
                       tc.car_number,
                       CASE
                           WHEN tc.car_number IS NOT NULL
                           THEN 'V' || tc.car_number || '-' || seat.seat_label
                           ELSE seat.seat_label
                       END AS seat_display,
                       (SELECT rs.departure_time FROM route_stops rs
                        WHERE rs.route_id = tr.route_id
                          AND rs.station_id = tl.departure_station_id
                        ORDER BY rs.stop_order LIMIT 1) AS departure_time,
                       (SELECT rs.arrival_time FROM route_stops rs
                        WHERE rs.route_id = tr.route_id
                          AND rs.station_id = tl.arrival_station_id
                        ORDER BY rs.stop_order DESC LIMIT 1) AS arrival_time
                FROM ticket_legs tl
                JOIN trains tr ON tr.train_id = tl.train_id
                JOIN stations s1 ON s1.station_id = tl.departure_station_id
                JOIN stations s2 ON s2.station_id = tl.arrival_station_id
                LEFT JOIN seats seat ON seat.seat_id = tl.seat_id
                LEFT JOIN train_cars tc ON tc.train_car_id = seat.train_car_id
                WHERE tl.ticket_id = ANY(:ids)
                ORDER BY tl.ticket_id, tl.leg_order
            """),
            {"ids": ticket_ids},
        ).mappings().all()

        # Grupează legs per ticket_id
        from collections import defaultdict
        legs_by_ticket: dict = defaultdict(list)
        for leg in legs_rows:
            legs_by_ticket[leg["ticket_id"]].append({
                "leg_id": leg["leg_id"],
                "leg_order": leg["leg_order"],
                "train_id": leg["train_id"],
                "train_number": leg["train_number"],
                "train_type": leg["train_type"],
                "departure_station_id": leg["departure_station_id"],
                "departure_station": leg["departure_station"],
                "arrival_station_id": leg["arrival_station_id"],
                "arrival_station": leg["arrival_station"],
                "travel_date": str(leg["travel_date"]),
                "seat_id": leg["seat_id"],
                "seat_display": leg.get("seat_display"),
                "car_number": str(leg["car_number"]) if leg.get("car_number") else None,
                "price": float(leg["price"]),
                "qr_token": leg["qr_token"],
                "qr_data_url": _build_qr_data_url(leg["qr_token"]) if leg.get("qr_token") else None,
                "departure_time": str(leg["departure_time"])[:5] if leg.get("departure_time") else None,
                "arrival_time": str(leg["arrival_time"])[:5] if leg.get("arrival_time") else None,
            })

        for ticket in result:
            tid = ticket["ticket_id"]
            if legs_by_ticket[tid]:
                ticket["legs"] = legs_by_ticket[tid]
                # Dacă biletul are multiple legs, marchează total_legs
                if len(legs_by_ticket[tid]) > 1:
                    ticket["total_legs"] = len(legs_by_ticket[tid])

    # Grupam biletele in calatorii multi-leg (rute cu schimbare)
    _group_journey_legs(result)
    return result


def _group_journey_legs(tickets: list[dict]) -> None:
    """
    Detecteaza biletele care fac parte din aceeasi calatorie cu schimbare
    si seteaza in-place campurile journey_group_id / leg_index / total_legs /
    transfer_minutes pentru fiecare bilet.

    Algoritm:
      1. Filtram doar biletele 'single' (cele 'return' nu sunt parte din
         lanturi multi-leg in modelul curent).
      2. Grupam dupa (travel_date, passenger_name normalizat, ticket_status
         activ/folosit/expirat). Biletele 'cancelled'/'refunded' raman izolate.
      3. In cadrul fiecarui grup candidat, sortam dupa departure_time si
         construim lanturi: arrival_station al biletului N == departure_station
         al biletului N+1, iar diferenta intre purchase_time-uri e < 15 min
         (cumparate "impreuna").
      4. Pentru fiecare lant cu len >= 2, generam un journey_group_id unic si
         setam leg_index/total_legs/transfer_minutes.
    """
    from collections import defaultdict
    from datetime import datetime as _dt

    # Excludem biletele anulate/refundate - nu fac parte din calatoria activa
    eligible = [
        t for t in tickets
        if t.get("ticket_type") == "single"
        and t.get("ticket_status") in ("active", "used", "expired")
    ]
    if len(eligible) < 2:
        return

    def _pax_key(t: dict) -> str:
        name = (t.get("passenger_name") or "").strip().lower()
        return name  # NULL = cumparator (acelasi user)

    def _parse_dt(s: str):
        if not s:
            return None
        s2 = s.split(".")[0] if "." in s else s  # strip microseconds
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M"):
            try:
                return _dt.strptime(s2, fmt)
            except ValueError:
                continue
        return None

    def _parse_hm(s: str):
        if not s:
            return None
        try:
            h, m = s.split(":")[:2]
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None

    # Grupare candidata: (travel_date, passenger_name)
    candidates: dict[tuple, list[dict]] = defaultdict(list)
    for t in eligible:
        key = (t.get("travel_date"), _pax_key(t))
        candidates[key].append(t)

    journey_seq = 0
    for key, group in candidates.items():
        if len(group) < 2:
            continue

        # Sortam dupa departure_time (lipsa = la final)
        group_sorted = sorted(
            group,
            key=lambda x: _parse_hm(x.get("departure_time")) or 9999,
        )

        # Construim lanturi
        used: set[int] = set()
        for i, leg in enumerate(group_sorted):
            if id(leg) in used:
                continue
            chain = [leg]
            used.add(id(leg))
            current = leg
            cur_pt = _parse_dt(current.get("purchase_time"))
            cur_arr_min = _parse_hm(current.get("arrival_time"))
            # Statiile deja vizitate in lant (anti-cycle: nu te poti intoarce
            # intr-o statie din care ai mai plecat in cadrul aceleiasi calatorii).
            visited_stations: set = {leg.get("departure_station_id"), leg.get("arrival_station_id")}

            # Cautam urmatorul leg: arrival_station == departure_station al unui
            # bilet ulterior nefolosit, cu purchase_time apropiat
            while True:
                next_leg = None
                for cand in group_sorted[i + 1:]:
                    if id(cand) in used:
                        continue
                    if cand.get("departure_station_id") != current.get("arrival_station_id"):
                        continue
                    # Anti-cycle: destinatia candidatului nu trebuie sa fi fost vizitata
                    cand_arr = cand.get("arrival_station_id")
                    if cand_arr in visited_stations:
                        continue
                    cand_dep_min = _parse_hm(cand.get("departure_time"))
                    if cur_arr_min is not None and cand_dep_min is not None:
                        # Pleaca dupa sosirea legului curent (intre 0 si 4h)
                        gap = cand_dep_min - cur_arr_min
                        if gap < 0 or gap > 240:
                            continue
                    # Cumparate aproape simultan (≤ 2 min). Pragul strans
                    # evita fals-pozitivele cand userul cumpara un retur si
                    # imediat un alt bilet de la statia de plecare (chain
                    # incidental dar nu calatorie planificata cu schimbare).
                    cand_pt = _parse_dt(cand.get("purchase_time"))
                    if cur_pt and cand_pt:
                        delta = abs((cand_pt - cur_pt).total_seconds())
                        if delta > 2 * 60:
                            continue
                    elif not (cur_pt and cand_pt):
                        # Nu putem verifica gap-ul → conservativ: nu grupam
                        continue
                    next_leg = cand
                    break

                if not next_leg:
                    break
                chain.append(next_leg)
                used.add(id(next_leg))
                visited_stations.add(next_leg.get("arrival_station_id"))
                current = next_leg
                cur_arr_min = _parse_hm(current.get("arrival_time"))

            # Daca avem un lant de minim 2 → e calatorie multi-leg
            if len(chain) >= 2:
                journey_seq += 1
                jgid = f"journey-{key[0]}-{journey_seq}"
                total = len(chain)
                for idx, leg_t in enumerate(chain):
                    leg_t["journey_group_id"] = jgid
                    leg_t["leg_index"] = idx
                    leg_t["total_legs"] = total
                    if idx > 0:
                        prev_arr = _parse_hm(chain[idx - 1].get("arrival_time"))
                        this_dep = _parse_hm(leg_t.get("departure_time"))
                        if prev_arr is not None and this_dep is not None:
                            leg_t["transfer_minutes"] = max(0, this_dep - prev_arr)

def _passenger_display_name(qr_row) -> str:
    """Returneaza numele pasagerului afisat conductorului.
    Daca biletul are passenger_name setat (cumparat pentru altcineva),
    foloseste acela; altfel foloseste numele cumparatorului din users.
    """
    ticket_pax = (qr_row.get("ticket_passenger_name") or "").strip() if qr_row.get("ticket_passenger_name") else ""
    if ticket_pax:
        return ticket_pax
    return f"{qr_row['first_name']} {qr_row['last_name']}"


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
                    t.passenger_name AS ticket_passenger_name,
                    t.ticket_id      AS ticket_id,
                    t.travel_date    AS ticket_travel_date,
                    tr.train_number  AS ticket_train_number,
                    CASE
                        WHEN te.source_type = 'ticket'       THEN t.ticket_type
                        WHEN te.source_type = 'subscription' THEN s.subscription_type
                        ELSE 'benefit'
                    END AS entitlement_subtype
                FROM qr_tokens qt
                JOIN travel_entitlements te ON te.entitlement_id = qt.entitlement_id
                JOIN users u                ON u.user_id = te.user_id
                LEFT JOIN tickets t         ON t.ticket_id = te.ticket_id
                LEFT JOIN trains tr         ON tr.train_id = t.train_id
                LEFT JOIN subscriptions s   ON s.subscription_id = te.subscription_id
                WHERE qt.token_value = :tv
                """
            ),
            {"tv": payload.token},
        ).mappings().first()

        if not qr:
            # Fallback: token-ul ar putea fi de la un journey (ticket_legs.qr_token_hash)
            import hashlib as _hashlib
            token_hash = _hashlib.sha256(payload.token.encode()).hexdigest()
            leg = db.execute(
                text("""
                    SELECT tl.leg_id, tl.ticket_id, tl.train_id, tl.travel_date,
                           tl.departure_station_id, tl.arrival_station_id, tl.leg_order,
                           t.ticket_status, t.passenger_name, t.user_id,
                           tr.train_number,
                           s1.name AS dep_station, s2.name AS arr_station,
                           COALESCE(NULLIF(TRIM(t.passenger_name),''),
                                    TRIM(CONCAT_WS(' ', u.first_name, u.last_name))) AS display_name
                    FROM ticket_legs tl
                    JOIN tickets t ON t.ticket_id = tl.ticket_id
                    JOIN trains tr ON tr.train_id = tl.train_id
                    JOIN stations s1 ON s1.station_id = tl.departure_station_id
                    JOIN stations s2 ON s2.station_id = tl.arrival_station_id
                    JOIN users u ON u.user_id = t.user_id
                    WHERE tl.qr_token_hash = :hash
                """),
                {"hash": token_hash},
            ).mappings().first()
            if leg:
                if leg["ticket_status"] not in ("active",):
                    return ValidateTicketResponse(
                        result="invalid",
                        message=f"Biletul are statusul '{leg['ticket_status']}'",
                        passenger_name=leg["display_name"],
                    )
                if leg["travel_date"] < datetime.now(timezone.utc).date():
                    return ValidateTicketResponse(result="expired", message="Data călătoriei a trecut")
                _log_validation(db, qr_token_id=None, conductor_id=conductor["user_id"],
                                result="valid", device_id=payload.device_id,
                                notes=f"leg_id={leg['leg_id']} {payload.location_name or ''}")
                db.commit()
                return ValidateTicketResponse(
                    result="valid",
                    message=f"Journey valid — {leg['dep_station']} → {leg['arr_station']} (tren {leg['train_number']})",
                    passenger_name=leg["display_name"],
                    ticket_type="journey",
                    valid_until=None,
                )
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
                passenger_name=_passenger_display_name(qr),
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

        # SINGLE-USE: mark as used. Folosim CAS (used_at IS NULL AND status='active')
        # ca sa prevenim race condition: 2 conductori scaneaza simultan -> doar
        # primul reuseste UPDATE-ul, al doilea primeste 0 rows si raspunde already_used.
        cas_result = db.execute(
            text(
                """
                UPDATE qr_tokens
                SET status = 'used', used_at = CURRENT_TIMESTAMP
                WHERE qr_token_id = :qt_id
                  AND used_at IS NULL
                  AND status = 'active'
                """
            ),
            {"qt_id": qr["qr_token_id"]},
        )
        if cas_result.rowcount == 0:
            # Alt conductor a marcat token-ul intre SELECT si UPDATE.
            _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                            result="already_used", device_id=payload.device_id,
                            notes="Race detected (CAS failed)")
            db.commit()
            return ValidateTicketResponse(
                result="already_used",
                message="Biletul a fost deja folosit",
                passenger_name=_passenger_display_name(qr),
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

            # Notificare: biletul a fost validat (tranzitie active -> used).
            # Trimitem doar pentru tickets (nu pentru subscriptions, care sunt
            # multi-use si ar genera spam de notificari la fiecare validare).
            train_no = qr["ticket_train_number"] or "?"
            travel_date_str = (
                qr["ticket_travel_date"].isoformat()
                if qr["ticket_travel_date"] else "?"
            )
            db.execute(
                text("""
                    INSERT INTO notifications (user_id, category, title, message, is_read, created_at)
                    VALUES (:uid, 'ticket', :title, :msg, FALSE, NOW())
                """),
                {
                    "uid": qr["user_id"],
                    "title": "Bilet validat",
                    "msg": (
                        f"Biletul pentru trenul {train_no} din {travel_date_str} "
                        f"a fost validat in tren. Calatorie placuta!"
                    ),
                },
            )

        _log_validation(db, qr_token_id=qr["qr_token_id"], conductor_id=conductor["user_id"],
                        result="valid", device_id=payload.device_id, notes=payload.location_name)

        db.commit()

        return ValidateTicketResponse(
            result="valid",
            message="Bilet validat cu succes",
            passenger_name=_passenger_display_name(qr),
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
    if row["ticket_status"] not in ("active", "rescheduled"):
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
                   t.ticket_status, t.passenger_name, tr.train_number,
                   t.purchase_time
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

    # Verifica ca noul tren opreste la ambele statii (dep < arr in stop_order).
    # Folosim route_stops (ca search_trains), nu origin/destination din routes —
    # astfel sunt permise trenuri cu traseu mai lung care acopera segmentul.
    stop_orders = db.execute(
        text("""
            SELECT
                MIN(CASE WHEN station_id = :dep THEN stop_order END) AS dep_order,
                MIN(CASE WHEN station_id = :arr THEN stop_order END) AS arr_order
            FROM route_stops
            WHERE route_id = :rid
        """),
        {
            "rid": new_train["route_id"],
            "dep": old["departure_station_id"],
            "arr": old["arrival_station_id"],
        },
    ).mappings().first()

    dep_order = stop_orders["dep_order"] if stop_orders else None
    arr_order = stop_orders["arr_order"] if stop_orders else None

    if dep_order is None or arr_order is None or dep_order >= arr_order:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "different_route",
                "message": "Noul tren nu trece prin ambele statii ale biletului original "
                           "(sau le trece in ordine inversa). Anulati biletul si cumparati altul.",
            },
        )

    # 1. Elibereaza locurile vechi
    release_ticket_seats(db, ticket_id)

    # 2. Marcheaza biletul vechi ca 'rescheduled'
    db.execute(
        text("UPDATE tickets SET ticket_status='rescheduled' WHERE ticket_id=:tid"),
        {"tid": ticket_id},
    )

    # 3. Anti-overlap pe noul interval (acum vechiul nu mai e 'active').
    # Folosim aceleasi statii dep/arr ca biletul original (reschedule pastreaza traseul).
    check_overlap(
        db, user_id, body.new_train_id, new_date,
        departure_station_id=old["departure_station_id"],
        arrival_station_id=old["arrival_station_id"],
        source_train_id=old["train_id"],
    )

    # 4. Cloneaza biletul cu noile date (pastram passenger_name si purchase_time
    #    pentru ca biletele din acelasi grup multi-pax sa ramana grupate dupa reprogramare)
    new_ticket = db.execute(
        text("""
            INSERT INTO tickets (
                user_id, train_id, departure_station_id, arrival_station_id,
                travel_date, ticket_type, ticket_status,
                price, discount_applied,
                rescheduled_from_ticket_id, passenger_name,
                purchase_time
            ) VALUES (
                :uid, :tid, :dep, :arr,
                :td, :type, 'active',
                :price, :disc, :from_id, :pax_name,
                :pt
            )
            RETURNING ticket_id
        """),
        {
            "uid": user_id, "tid": body.new_train_id,
            "dep": old["departure_station_id"], "arr": old["arrival_station_id"],
            "td": new_date, "type": old["ticket_type"],
            "price": old["price"], "disc": old["discount_applied"],
            "from_id": ticket_id,
            "pax_name": old.get("passenger_name"),
            "pt": old["purchase_time"],
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

"""
Endpoint-uri pentru harta interactiva a centrelor universitare si retelei
feroviare CFR.

Expune:
  - GET /map/stations         : toate statiile cu coordonate GPS
  - GET /map/connections      : perechi (origine, destinatie) cu trenuri directe
  - GET /map/operators        : lista operatorilor cu nr. trenuri
  - GET /map/train-simulate/{train_id} : pozitia simulata a unui tren
  - GET /map/route-geometry   : geometria celei mai favorabile rute intre 2 statii
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token


router = APIRouter(tags=["map"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_auth(authorization: Optional[str]) -> int:
    """Cere un Bearer token valid si returneaza user_id."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token lipsa")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalid")
    uid = payload.get("sub") or payload.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="Token fara user_id")
    return int(uid)


@router.get("/map/stations")
def map_stations(
    only_university: bool = Query(False, description="Doar centre universitare"),
    operator_id: Optional[int] = Query(None, description="Filtreaza statiile servite de acest operator"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Returneaza toate statiile cu GPS + numarul de trenuri care le deservesc.
    """
    _require_auth(authorization)

    where_parts = ["s.latitude IS NOT NULL"]
    params: dict = {}

    if only_university:
        where_parts.append("s.is_university_hub = TRUE")
    else:
        # Afiseaza pe harta doar statiile "comerciale vizibile":
        # - sufix CFR la sfarsit de nume: Gr., hm., Sat h., h.
        # - sau indicator directional la sfarsit: Nord, Sud, Est, Vest, Calatori
        # - sau cuvant tehnic oriunde: Triaj, Depou, Aeroport, Rampa etc.
        # - sau nod major (>=100 aparitii route_stops) = orase fara sufix (Brasov, Cluj, Galati)
        # - sau hub universitar
        # Statii care sunt DOAR nume de localitate cu putine rute (Huedin, Mizil, Barlad) nu apar.
        where_parts.append(r"""(
            s.is_university_hub = TRUE
            OR s.name ~* '(Gr\.?|hm\.?|Sat h\.|h\.)(\s*)$'
            OR s.name ~* '(Nord|Sud|Est|Vest|C[aă]l[aă]tori)(\s*)$'
            OR s.name ~* 'Triaj|Depou|Tehnic|Aeroport|Macaz|Pasaj|Rampa|R\. \d'
            OR (SELECT COUNT(*) FROM route_stops rs_cnt WHERE rs_cnt.station_id = s.station_id) >= 100
        )""")

    operator_join = ""
    if operator_id:
        operator_join = """
            AND EXISTS (
                SELECT 1 FROM route_stops rs
                JOIN trains t ON t.route_id = rs.route_id
                WHERE rs.station_id = s.station_id AND t.operator_id = :op_id
            )
        """
        params["op_id"] = operator_id

    sql = f"""
        SELECT
            s.station_id,
            s.name,
            s.code,
            s.city,
            s.latitude::float  AS latitude,
            s.longitude::float AS longitude,
            s.is_university_hub,
            s.student_count,
            s.universities_count,
            s.notes,
            (SELECT COUNT(DISTINCT t.train_id)
             FROM route_stops rs
             JOIN trains t ON t.route_id = rs.route_id
             WHERE rs.station_id = s.station_id AND t.is_active = TRUE) AS trains_count
        FROM stations s
        WHERE {' AND '.join(where_parts)}
        {operator_join}
        ORDER BY s.is_university_hub DESC NULLS LAST, s.student_count DESC NULLS LAST, s.name ASC
    """

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/map/connections")
def map_connections(
    min_trains: int = Query(1, description="Numar minim de trenuri pe conexiune"),
    only_university: bool = Query(True, description="Doar conexiuni intre centre universitare"),
    operator_id: Optional[int] = Query(None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Returneaza perechile de statii (origine, destinatie) conectate prin
    cel putin un tren direct, cu numarul de trenuri pe acea relatie.

    NOTA: acest endpoint NU mai e folosit de UI (liniile drepte intre puncte
    au fost eliminate). Pastrat pentru retrocompatibilitate si pentru
    debugging / analize topologice.
    """
    _require_auth(authorization)

    where_extra = ""
    params: dict = {"min_trains": min_trains}

    if only_university:
        where_extra += " AND s1.is_university_hub = TRUE AND s2.is_university_hub = TRUE"

    if operator_id:
        where_extra += " AND t.operator_id = :op_id"
        params["op_id"] = operator_id

    sql = f"""
        SELECT
            s1.station_id AS from_id,
            s1.name       AS from_name,
            s1.latitude::float  AS from_lat,
            s1.longitude::float AS from_lon,
            s2.station_id AS to_id,
            s2.name       AS to_name,
            s2.latitude::float  AS to_lat,
            s2.longitude::float AS to_lon,
            COUNT(DISTINCT t.train_id) AS trains_count
        FROM trains t
            JOIN route_stops rs1 ON rs1.route_id = t.route_id
            JOIN route_stops rs2 ON rs2.route_id = t.route_id AND rs2.stop_order > rs1.stop_order
            JOIN stations s1 ON s1.station_id = rs1.station_id
            JOIN stations s2 ON s2.station_id = rs2.station_id
        WHERE t.is_active = TRUE
          AND s1.latitude IS NOT NULL
          AND s2.latitude IS NOT NULL
          {where_extra}
        GROUP BY s1.station_id, s1.name, s1.latitude, s1.longitude,
                 s2.station_id, s2.name, s2.latitude, s2.longitude
        HAVING COUNT(DISTINCT t.train_id) >= :min_trains
        ORDER BY trains_count DESC
        LIMIT 500
    """

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/map/rail-segments")
def map_rail_segments(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Returneaza segmentele adiacente ale rețelei feroviare (stop N -> stop N+1),
    deduplicate, pentru ambele stații cu GPS. Folosit pentru a trasa liniile
    rețelei pe hartă pe baza datelor reale de orar CFR.
    """
    _require_auth(authorization)

    rows = db.execute(text("""
        SELECT DISTINCT
            LEAST(rs1.station_id, rs2.station_id)   AS sid_a,
            GREATEST(rs1.station_id, rs2.station_id) AS sid_b,
            s1.latitude::float  AS lat_a,
            s1.longitude::float AS lon_a,
            s2.latitude::float  AS lat_b,
            s2.longitude::float AS lon_b
        FROM route_stops rs1
        JOIN route_stops rs2
            ON rs2.route_id   = rs1.route_id
           AND rs2.stop_order = rs1.stop_order + 1
        JOIN stations s1 ON s1.station_id = rs1.station_id
                         AND s1.latitude IS NOT NULL
        JOIN stations s2 ON s2.station_id = rs2.station_id
                         AND s2.latitude IS NOT NULL
    """)).mappings().all()

    return [
        {"a": [r["lat_a"], r["lon_a"]], "b": [r["lat_b"], r["lon_b"]]}
        for r in rows
    ]


@router.get("/map/operators")
def map_operators(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Lista operatorilor activi cu numarul de trenuri."""
    _require_auth(authorization)

    sql = """
        SELECT
            op.operator_id,
            op.name,
            op.code,
            COUNT(DISTINCT t.train_id) AS trains_count
        FROM railway_operators op
        LEFT JOIN trains t ON t.operator_id = op.operator_id AND t.is_active = TRUE
        GROUP BY op.operator_id, op.name, op.code
        HAVING COUNT(DISTINCT t.train_id) > 0
        ORDER BY trains_count DESC, op.name ASC
    """
    rows = db.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/map/train-simulate/{train_id}")
def simulate_train_position(
    train_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Simuleaza pozitia unui tren la momentul curent, prin interpolare liniara
    intre stop-urile route_stops dupa orarul planificat.

    DEPRECATED: nu mai e folosit de UI (pozitiile erau aproximative). Pastrat
    pentru testare / posibila reintroducere cu GTFS-Realtime in productie.
    """
    _require_auth(authorization)

    train_row = db.execute(
        text(
            """
            SELECT
                t.train_id, t.train_number, t.train_type, t.route_id,
                op.name AS operator_name
            FROM trains t
            JOIN railway_operators op ON op.operator_id = t.operator_id
            WHERE t.train_id = :tid AND t.is_active = TRUE
            """
        ),
        {"tid": train_id},
    ).first()
    if not train_row:
        raise HTTPException(status_code=404, detail="Tren inexistent")

    # Toate stop-urile cu coordonate, ordonate.
    stops = db.execute(
        text(
            """
            SELECT
                rs.stop_order,
                rs.arrival_time,
                rs.departure_time,
                s.station_id,
                s.name AS station_name,
                s.latitude::float  AS lat,
                s.longitude::float AS lon
            FROM route_stops rs
            JOIN stations s ON s.station_id = rs.station_id
            WHERE rs.route_id = :rid
              AND s.latitude IS NOT NULL
            ORDER BY rs.stop_order
            """
        ),
        {"rid": train_row.route_id},
    ).mappings().all()

    if len(stops) < 2:
        raise HTTPException(status_code=404, detail="Tren fara stop-uri suficiente")

    now = datetime.now().time()

    # Identific stop-ul curent + urmatorul. Daca acum < primul dep -> not_departed.
    first = stops[0]
    last = stops[-1]
    first_dep = first["departure_time"]
    last_arr = last["arrival_time"]

    if first_dep and now < first_dep:
        return {
            "train_id": train_id,
            "train_number": train_row.train_number,
            "train_type": train_row.train_type,
            "operator": train_row.operator_name,
            "status": "not_departed",
            "current_lat": first["lat"],
            "current_lon": first["lon"],
            "current_station": first["station_name"],
            "next_station": stops[1]["station_name"],
            "progress_percent": 0,
        }
    if last_arr and now > last_arr:
        return {
            "train_id": train_id,
            "train_number": train_row.train_number,
            "train_type": train_row.train_type,
            "operator": train_row.operator_name,
            "status": "arrived",
            "current_lat": last["lat"],
            "current_lon": last["lon"],
            "current_station": last["station_name"],
            "next_station": None,
            "progress_percent": 100,
        }

    cur = first
    nxt = stops[1]
    for i in range(len(stops) - 1):
        s1 = stops[i]
        s2 = stops[i + 1]
        s1_dep = s1["departure_time"]
        s2_arr = s2["arrival_time"]
        if s1_dep and s2_arr and s1_dep <= now <= s2_arr:
            cur = s1
            nxt = s2
            break

    if not (cur["departure_time"] and nxt["arrival_time"]):
        return {
            "train_id": train_id,
            "train_number": train_row.train_number,
            "train_type": train_row.train_type,
            "operator": train_row.operator_name,
            "status": "in_transit",
            "current_lat": cur["lat"],
            "current_lon": cur["lon"],
            "current_station": cur["station_name"],
            "next_station": nxt["station_name"],
            "progress_percent": 50,
        }

    # Interpolare liniara in segmentul curent
    cur_dep_s = cur["departure_time"].hour * 3600 + cur["departure_time"].minute * 60 + cur["departure_time"].second
    nxt_arr_s = nxt["arrival_time"].hour * 3600 + nxt["arrival_time"].minute * 60 + nxt["arrival_time"].second
    now_s = now.hour * 3600 + now.minute * 60 + now.second

    segment_duration = nxt_arr_s - cur_dep_s
    elapsed = now_s - cur_dep_s
    progress = elapsed / segment_duration if segment_duration > 0 else 0.5
    progress = max(0.0, min(1.0, progress))

    cur_lat = cur["lat"] + (nxt["lat"] - cur["lat"]) * progress
    cur_lon = cur["lon"] + (nxt["lon"] - cur["lon"]) * progress

    return {
        "train_id": train_id,
        "train_number": train_row.train_number,
        "train_type": train_row.train_type,
        "operator": train_row.operator_name,
        "status": "in_transit",
        "current_lat": round(cur_lat, 6),
        "current_lon": round(cur_lon, 6),
        "current_station": cur["station_name"],
        "next_station": nxt["station_name"],
        "progress_percent": round(progress * 100, 1),
    }


@router.get("/map/route-geometry")
def map_route_geometry(
    from_station_id: int = Query(..., description="Statia de plecare"),
    to_station_id: int = Query(..., description="Statia de destinatie"),
    travel_date: Optional[str] = Query(None, description="Data calatorie YYYY-MM-DD (default: maine)"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Returneaza geometria celei mai favorabile rute intre 2 statii.

    Foloseste trip_planner.plan_trips() pentru a gasi cea mai buna optiune
    (directa sau cu 1-2 schimbari, sortata dupa timp total). Apoi extrage,
    pentru fiecare leg, toate stop-urile intermediare cu coordonate GPS
    pentru a desena polyline-ul real pe sina, nu o linie dreapta.
    """
    _require_auth(authorization)

    if from_station_id == to_station_id:
        raise HTTPException(
            status_code=400,
            detail="Statia de plecare si cea de sosire trebuie sa fie diferite",
        )

    if travel_date:
        try:
            td = datetime.strptime(travel_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Format data invalid (YYYY-MM-DD)")
    else:
        td = (datetime.now() + timedelta(days=1)).date()

    from app.services.trip_planner import plan_trips

    trips = plan_trips(
        db,
        from_station_id=from_station_id,
        to_station_id=to_station_id,
        travel_date=td,
        departure_after_minutes=None,
        top_n=1,
        max_intermediates=2000,
    )

    if not trips:
        return {
            "found": False,
            "total_duration_min": None,
            "transfer_count": 0,
            "legs": [],
        }

    best = trips[0]

    legs_with_geometry = []
    for leg in best.get("legs", []):
        train_id = leg.get("train_id")
        leg_from = leg.get("from_station_id")
        leg_to = leg.get("to_station_id")
        if not (train_id and leg_from and leg_to):
            continue

        stops_rows = db.execute(
            text(
                """
                WITH bounds AS (
                    SELECT
                        MIN(CASE WHEN rs.station_id = :s1 THEN rs.stop_order END) AS o1,
                        MIN(CASE WHEN rs.station_id = :s2 THEN rs.stop_order END) AS o2,
                        t.route_id
                    FROM trains t
                    JOIN route_stops rs ON rs.route_id = t.route_id
                    WHERE t.train_id = :tid
                      AND rs.station_id IN (:s1, :s2)
                    GROUP BY t.route_id
                )
                SELECT
                    s.station_id,
                    s.name,
                    s.latitude::float  AS lat,
                    s.longitude::float AS lon,
                    rs.stop_order,
                    -- Distincție oprire comercială (cu îmbarcare) vs nod tehnic
                    -- de trecere. Sursa = atributul TipOprire din XML CFR/Ferotrafic.
                    rs.is_commercial_stop,
                    to_char(rs.arrival_time,   'HH24:MI:SS') AS arrival_time,
                    to_char(rs.departure_time, 'HH24:MI:SS') AS departure_time
                FROM bounds b
                JOIN route_stops rs ON rs.route_id = b.route_id
                JOIN stations s    ON s.station_id = rs.station_id
                WHERE rs.stop_order BETWEEN LEAST(b.o1, b.o2) AND GREATEST(b.o1, b.o2)
                  AND s.latitude IS NOT NULL
                  AND s.longitude IS NOT NULL
                ORDER BY
                    CASE WHEN b.o1 <= b.o2 THEN rs.stop_order ELSE -rs.stop_order END
                """
            ),
            {"tid": train_id, "s1": leg_from, "s2": leg_to},
        ).mappings().all()

        # =====================================================================
        # SEPARARE CRITICA: stops (markere pe harta) vs geometry_points (polyline)
        # =====================================================================
        # `stops` = doar opririle REALE (unde trenul opreste comercial pt urcare/
        # coborare calatori) + cele 2 capete de leg (origine + destinatie). Acestea
        # devin markerele violet (intermediate) pe harta. Sursa autoritativa =
        # `is_commercial_stop` (mapat 1:1 din `TipOprire` XML CFR/Ferotrafic).
        #
        # `geometry_points` = TOATE statiile cu GPS intre cele 2 capete, in ordinea
        # parcurgerii. Polyline-ul (linia colorata a rutei) trebuie sa urmeze sina
        # reala, deci include si stafiile de trecere (TipOprire='N'): ramificatii,
        # halte de trecere, posturi macaz. ALTFEL polyline-ul ar sari peste curbe
        # si ar arata linii drepte nerealiste intre opriri (de ex. Bucuresti -> Buzau
        # ar fi o linie dreapta in loc sa urmeze sina prin Ploiesti, Mizil etc.).
        #
        # Bug-fix: inainte trimiteam toate statiile in `stops`, iar frontend-ul
        # le folosea atat pentru polyline cat si pentru markere. Asta facea ca
        # Inotesti, Mizil, Urlati etc. sa apara ca puncte violet pe harta, desi
        # IC 11762 NU OPRESTE acolo. Acum sunt separate.
        all_stops = [dict(r) for r in stops_rows]
        # Capetele de leg sunt mereu pastrate (origin + destination ale trenului
        # pe acest segment). Sunt intotdeauna comerciale din perspectiva user-ului:
        # acolo (de)imbarca pasagerul. Capetele se identifica prin station_id.
        real_stops = [
            s for s in all_stops
            if s["is_commercial_stop"]
               or s["station_id"] == leg_from
               or s["station_id"] == leg_to
        ]

        legs_with_geometry.append({
            "train_id": train_id,
            "train_number": leg.get("train_number"),
            "train_type": leg.get("train_type"),
            # Operatorul transmis catre UI pentru transparenta sursei datelor.
            "operator_name": leg.get("operator_name"),
            "operator_code": leg.get("operator_code"),
            "from_station": leg.get("from_station"),
            "to_station": leg.get("to_station"),
            "departure_time": leg.get("departure_time"),
            "arrival_time": leg.get("arrival_time"),
            "distance_km": leg.get("distance_km"),
            # `stops` = numai opriri reale + capete de leg (afisate ca markere)
            "stops": real_stops,
            # `geometry_points` = toate statiile cu GPS (folosit pentru polyline)
            "geometry_points": [
                {"lat": s["lat"], "lon": s["lon"], "station_id": s["station_id"]}
                for s in all_stops
            ],
        })

    return {
        "found": True,
        "total_duration_min": best.get("total_duration_min"),
        "transfer_count": best.get("transfer_count", 0),
        "transfer_stations": best.get("transfer_stations", []),
        "departure_time": best.get("departure_time"),
        "arrival_time": best.get("arrival_time"),
        "legs": legs_with_geometry,
    }

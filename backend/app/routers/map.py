"""
Endpoint-uri pentru harta interactiva a centrelor universitare si retelei feroviare.

GET  /map/stations           — toate statiile cu GPS + meta universitati
GET  /map/connections        — perechi de statii conectate prin trenuri directe
GET  /map/train-simulate/{id} — simulator pozitie tren (interpolare liniara pe segment)
"""
from datetime import datetime
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
    """Verifica ca exista un token JWT valid. Returneaza user_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
        return int(payload.get("sub", "0"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/map/stations")
def map_stations(
    only_university: bool = Query(False, description="Doar centre universitare"),
    operator_id: Optional[int] = Query(None, description="Filtreaza statiile servite de acest operator"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_auth(authorization)
    """
    Returneaza toate statiile cu GPS + numarul de trenuri care le deservesc.
    """
    where_parts = ["s.latitude IS NOT NULL"]
    params: dict = {}

    if only_university:
        where_parts.append("s.is_university_hub = TRUE")

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
    _require_auth(authorization)
    """
    Returneaza perechile de statii (origine, destinatie) conectate prin
    cel putin un tren direct, cu numarul de trenuri pe acea relatie.
    Util pentru a desena linii intre pin-uri pe harta.
    """
    where_extra = ""
    params: dict = {"min_trains": min_trains}

    if only_university:
        where_extra += " AND s1.is_university_hub = TRUE AND s2.is_university_hub = TRUE"

    if operator_id:
        where_extra += " AND t.operator_id = :op_id"
        params["op_id"] = operator_id

    sql = f"""
        WITH directs AS (
            SELECT
                rs1.station_id AS from_id,
                rs2.station_id AS to_id,
                COUNT(DISTINCT t.train_id) AS trains_count,
                MAX(rs2.distance_from_origin_km - rs1.distance_from_origin_km)::float AS distance_km
            FROM trains t
            JOIN route_stops rs1 ON rs1.route_id = t.route_id
            JOIN route_stops rs2 ON rs2.route_id = t.route_id AND rs2.stop_order > rs1.stop_order
            JOIN stations s1 ON s1.station_id = rs1.station_id
            JOIN stations s2 ON s2.station_id = rs2.station_id
            WHERE s1.latitude IS NOT NULL AND s2.latitude IS NOT NULL
              AND t.is_active = TRUE
              {where_extra}
            GROUP BY rs1.station_id, rs2.station_id
            HAVING COUNT(DISTINCT t.train_id) >= :min_trains
        )
        SELECT
            d.from_id, s1.name AS from_name,
            s1.latitude::float AS from_lat, s1.longitude::float AS from_lon,
            d.to_id, s2.name AS to_name,
            s2.latitude::float AS to_lat, s2.longitude::float AS to_lon,
            d.trains_count, d.distance_km
        FROM directs d
        JOIN stations s1 ON s1.station_id = d.from_id
        JOIN stations s2 ON s2.station_id = d.to_id
        ORDER BY d.trains_count DESC
        LIMIT 200
    """

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/map/operators")
def map_operators(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_auth(authorization)
    """Lista operatori (pentru filtre UI)."""
    rows = db.execute(
        text("""
            SELECT op.operator_id, op.name, op.code, COUNT(t.train_id) AS trains_count
            FROM railway_operators op
            LEFT JOIN trains t ON t.operator_id = op.operator_id AND t.is_active = TRUE
            WHERE op.is_active = TRUE
            GROUP BY op.operator_id
            ORDER BY trains_count DESC, op.name
        """)
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/map/train-simulate/{train_id}")
def simulate_train_position(
    train_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_auth(authorization)
    """
    Simulator de pozitie tren in timp real.

    Folosim orarul planificat (route_stops + departure_time/arrival_time) si
    timpul curent pentru a interpola pozitia GPS aproximativa intre 2 statii.

    NOTA: Acest endpoint este intentionat un simulator. In productie ar fi
    inlocuit cu un feed GTFS-Realtime atunci cand CFR Calatori il va expune
    (cf. modelelor open data DB/SNCF/SBB — vezi discutia din lucrare).
    """
    train_row = db.execute(
        text("""
            SELECT t.train_id, t.train_number, t.train_type, t.route_id,
                   r.route_name, op.name AS operator_name
            FROM trains t
            JOIN routes r ON r.route_id = t.route_id
            JOIN railway_operators op ON op.operator_id = t.operator_id
            WHERE t.train_id = :tid
        """),
        {"tid": train_id},
    ).first()
    if not train_row:
        raise HTTPException(status_code=404, detail="Trenul nu exista")

    # Obtinem toate opririle ordonate
    stops = db.execute(
        text("""
            SELECT rs.stop_order, rs.station_id, s.name AS station_name,
                   s.latitude::float AS lat, s.longitude::float AS lon,
                   rs.arrival_time, rs.departure_time,
                   rs.distance_from_origin_km::float AS km
            FROM route_stops rs
            JOIN stations s ON s.station_id = rs.station_id
            WHERE rs.route_id = :rid
            ORDER BY rs.stop_order
        """),
        {"rid": train_row.route_id},
    ).mappings().all()

    if not stops:
        raise HTTPException(status_code=404, detail="Trenul nu are opriri")

    # Calculam pozitia bazata pe ora curenta vs orarul planificat
    now = datetime.now().time()

    # Gasim segmentul curent
    current_segment = None
    for i in range(len(stops) - 1):
        cur = stops[i]
        nxt = stops[i + 1]
        cur_dep = cur["departure_time"]
        nxt_arr = nxt["arrival_time"]
        if cur_dep and nxt_arr and cur_dep <= now <= nxt_arr:
            current_segment = (i, cur, nxt)
            break

    if current_segment is None:
        # Inainte de plecare sau dupa sosire — afisez la prima/ultima statie
        if stops[0]["departure_time"] and now < stops[0]["departure_time"]:
            return {
                "train_id": train_id, "train_number": train_row.train_number,
                "train_type": train_row.train_type, "operator": train_row.operator_name,
                "status": "not_departed",
                "current_lat": stops[0]["lat"], "current_lon": stops[0]["lon"],
                "current_station": stops[0]["station_name"],
                "next_station": stops[1]["station_name"] if len(stops) > 1 else None,
                "progress_percent": 0,
            }
        return {
            "train_id": train_id, "train_number": train_row.train_number,
            "train_type": train_row.train_type, "operator": train_row.operator_name,
            "status": "arrived",
            "current_lat": stops[-1]["lat"], "current_lon": stops[-1]["lon"],
            "current_station": stops[-1]["station_name"],
            "next_station": None,
            "progress_percent": 100,
        }

    idx, cur, nxt = current_segment
    if not cur["lat"] or not nxt["lat"]:
        # Statie fara GPS — afisez la cea mai apropiata cu GPS
        return {
            "train_id": train_id, "train_number": train_row.train_number,
            "train_type": train_row.train_type, "operator": train_row.operator_name,
            "status": "no_gps",
            "current_lat": None, "current_lon": None,
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

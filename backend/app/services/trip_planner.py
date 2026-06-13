"""
Trip planner pentru sugestii multi-leg.

Cazul de uz principal:
  Studentul din Făurei (Brăila) vrea să ajungă acasă din București dar nu există
  tren direct la ora dorită. Sistemul sugerează itinerariu: BUC Nord → Buzău (IR
  ora 14:00, sosire 16:30) + Buzău → Făurei (R local ora 17:00, sosire 18:15).

Algoritm: BFS modificat pe graful route_stops cu constrangeri temporale.

Constrange:
  - MAX_LEGS = 3 (max 2 schimbari)
  - MIN_CONNECTION = 15 minute (timp schimbare peron)
  - MAX_CONNECTION = 180 minute (peste 3h: prea lung)
  - Toate trenurile in aceeasi zi
  - Sortare: (timp_total ASC, nr_schimbari ASC)
  - Top N rezultate

Output:
  [
    {
      "legs": [
        {
          "train_id": 12, "train_number": "IR1582",
          "from_station_id": 5, "from_station": "BUC Nord",
          "to_station_id": 22, "to_station": "Buzau",
          "departure_time": "14:00:00", "arrival_time": "16:30:00",
          "distance_km": 130, "train_type": "interregio",
        },
        ...
      ],
      "total_duration_min": 285,
      "transfer_count": 1,
      "total_distance_km": 250,
      "departure_time": "14:00:00",  # plecare prima leg
      "arrival_time": "18:45:00",    # sosire ultima leg
    },
    ...
  ]
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


MAX_LEGS = 3
MIN_CONNECTION_MIN = 15
MAX_CONNECTION_MIN = 180
DEFAULT_TOP_N = 5


def _time_to_minutes(t: time | None) -> int | None:
    """Converteste time -> minute din miezul noptii."""
    if t is None:
        return None
    return t.hour * 60 + t.minute


def _minutes_to_str(mins: int) -> str:
    """Format HH:MM:SS pentru afisare."""
    h, m = divmod(mins, 60)
    return f"{h:02d}:{m:02d}:00"


def _trains_passing_station(
    db: Session, station_id: int, travel_date: date,
    min_departure_minutes: Optional[int] = None,
    _cache: dict | None = None,
) -> list[dict]:
    """
    Returneaza toate trenurile care opresc in `station_id` la travel_date,
    cu plecare > min_departure_minutes (daca dat).

    Pentru fiecare tren, info despre stop-ul curent + toate stop-urile
    ulterioare pe ruta (pentru a permite cautarea destinatiei).

    Daca primesti _cache (dict per-request), reutilizam rezultatul brut per
    `station_id` (independent de min_departure_minutes) - reducem masiv N+1.
    """
    cache_key = ("trains", station_id)
    if _cache is not None and cache_key in _cache:
        all_rows = _cache[cache_key]
    else:
        rows = db.execute(
            text(
                """
                SELECT
                    t.train_id, t.train_number, t.train_type, t.route_id,
                    op.name AS operator_name,
                    op.code AS operator_code,
                    rs.stop_order      AS from_stop_order,
                    rs.departure_time  AS from_departure,
                    rs.arrival_time    AS from_arrival,
                    rs.distance_from_origin_km AS from_km
                FROM trains t
                JOIN route_stops rs ON rs.route_id = t.route_id
                LEFT JOIN railway_operators op ON op.operator_id = t.operator_id
                WHERE rs.station_id = :sid
                  AND t.is_active = TRUE
                  AND rs.departure_time IS NOT NULL  -- statia trebuie sa fie origin/intermediar
                ORDER BY rs.departure_time
                """
            ),
            {"sid": station_id},
        ).mappings().all()
        all_rows = [dict(r) for r in rows]
        if _cache is not None:
            _cache[cache_key] = all_rows

    out = []
    for r in all_rows:
        dep_min = _time_to_minutes(r["from_departure"])
        if dep_min is None:
            continue
        if min_departure_minutes is not None and dep_min < min_departure_minutes:
            continue
        # dict(r) deja - dar facem copie sa nu mutam cache-ul
        out.append(dict(r))
    return out


def _stops_on_route_after(
    db: Session, route_id: int, from_stop_order: int,
    _cache: dict | None = None,
) -> list[dict]:
    """
    Returneaza toate stop-urile dintr-o ruta dupa from_stop_order
    (stations la care trenul ajunge dupa from_station).

    Daca primesti _cache (dict per-request), incarcam o singura data TOATE
    stop-urile rutei si filtram in Python. Asta elimina N+1 (acelasi route_id
    interogat de zeci de ori cu stop_order diferit).
    """
    if _cache is not None:
        all_key = ("route_stops_all", route_id)
        if all_key in _cache:
            all_stops = _cache[all_key]
        else:
            rows = db.execute(
                text(
                    """
                    SELECT
                        rs.station_id,
                        rs.stop_order,
                        rs.arrival_time,
                        rs.departure_time,
                        rs.distance_from_origin_km,
                        s.name AS station_name
                    FROM route_stops rs
                    JOIN stations s ON s.station_id = rs.station_id
                    WHERE rs.route_id = :rid
                    ORDER BY rs.stop_order
                    """
                ),
                {"rid": route_id},
            ).mappings().all()
            all_stops = [dict(r) for r in rows]
            _cache[all_key] = all_stops
        return [dict(s) for s in all_stops if s["stop_order"] > from_stop_order]

    # Fallback (fara cache - vechi behavior)
    return [
        dict(r)
        for r in db.execute(
            text(
                """
                SELECT
                    rs.station_id,
                    rs.stop_order,
                    rs.arrival_time,
                    rs.departure_time,
                    rs.distance_from_origin_km,
                    s.name AS station_name
                FROM route_stops rs
                JOIN stations s ON s.station_id = rs.station_id
                WHERE rs.route_id = :rid AND rs.stop_order > :ord
                ORDER BY rs.stop_order
                """
            ),
            {"rid": route_id, "ord": from_stop_order},
        ).mappings().all()
    ]


def _station_name(db: Session, station_id: int) -> str:
    row = db.execute(
        text("SELECT name FROM stations WHERE station_id = :sid"),
        {"sid": station_id},
    ).first()
    return row[0] if row else f"Statia {station_id}"


def _make_leg(train: dict, from_station_name: str, to_stop: dict) -> dict:
    """Construieste un dict de leg cu toate cele necesare frontendului."""
    dep_min = _time_to_minutes(train["from_departure"])
    arr_min = _time_to_minutes(to_stop["arrival_time"])
    # FIX: trenuri de noapte (arrival < departure) - adaugam 24h (1440 min).
    if arr_min is not None and dep_min is not None:
        duration = arr_min - dep_min
        if duration < 0:
            duration += 1440  # trenul ajunge in ziua urmatoare
    else:
        duration = 0
    distance = float(to_stop["distance_from_origin_km"]) - float(train["from_km"] or 0)
    return {
        "train_id": train["train_id"],
        "train_number": train["train_number"],
        "train_type": train["train_type"],
        # Operatorul trenului (SNTFC CFR Calatori, Ferotrafic, Astra Trans Carpatic etc.)
        # — afisat in UI pentru transparenta sursei. Conventiile de marcare a opririlor
        # difera intre operatori (de ex. Ferotrafic vs CFR Calatori), iar afisarea
        # explicita previne confuzii cand utilizatorul compara cu orarul oficial.
        "operator_name": train.get("operator_name"),
        "operator_code": train.get("operator_code"),
        "from_station_id": None,  # va fi populat de caller
        "from_station": from_station_name,
        "to_station_id": to_stop["station_id"],
        "to_station": to_stop["station_name"],
        "departure_time": _minutes_to_str(dep_min),
        "arrival_time": _minutes_to_str(arr_min) if arr_min is not None else None,
        "duration_min": duration,
        "distance_km": round(distance, 1) if distance > 0 else 0,
        "arrival_min": arr_min,  # internal: pentru cautari de conexiune
        "departure_min": dep_min,
    }


def plan_trips(
    db: Session,
    from_station_id: int,
    to_station_id: int,
    travel_date: date,
    departure_after_minutes: Optional[int] = None,
    top_n: int = DEFAULT_TOP_N,
    max_intermediates: int = 500,
) -> list[dict]:
    """
    Returneaza top_n itinerarii sortate (timp total ASC, transferuri ASC).

    `departure_after_minutes`: ora minima de plecare in minute (00:00 = 0).
    Daca None: pentru azi = ora curenta + 15 min; pentru zile viitoare = 0.
    """
    if from_station_id == to_station_id:
        return []

    # Default minimal departure
    if departure_after_minutes is None:
        if travel_date == date.today():
            now = datetime.now()
            departure_after_minutes = now.hour * 60 + now.minute + 15
        else:
            departure_after_minutes = 0

    from_name = _station_name(db, from_station_id)
    results = []
    # Cache per-request pentru a elimina N+1 (acelasi route/statie interogate
    # de zeci de ori in cele 3 niveluri imbricate).
    cache: dict = {}

    # === Pasul 1: cauta itinerarii DIRECTE ===
    trains_leg1 = _trains_passing_station(
        db, from_station_id, travel_date, departure_after_minutes, _cache=cache,
    )
    for tr in trains_leg1:
        stops = _stops_on_route_after(db, tr["route_id"], tr["from_stop_order"], _cache=cache)
        for stop in stops:
            if stop["station_id"] == to_station_id:
                leg = _make_leg(tr, from_name, stop)
                leg["from_station_id"] = from_station_id
                results.append({
                    "legs": [leg],
                    "transfer_count": 0,
                    "total_duration_min": leg["duration_min"],
                    "total_distance_km": leg["distance_km"],
                    "departure_time": leg["departure_time"],
                    "arrival_time": leg["arrival_time"],
                    "departure_min": leg["departure_min"],
                    "arrival_min": leg["arrival_min"],
                })
                break  # un tren trece doar o data prin destinatie

    # === Pasul 2: cauta itinerarii cu 1 schimbare (A -> B -> C) ===
    # Pentru fiecare tren leg1, vad toate statiile intermediare (potentiale B).
    # Pentru fiecare B, caut trenuri spre to_station_id cu plecare in [arr_B + 15min, arr_B + 180min].
    for tr1 in trains_leg1:
        stops1 = _stops_on_route_after(db, tr1["route_id"], tr1["from_stop_order"], _cache=cache)
        for stop_b in stops1:
            if stop_b["station_id"] == to_station_id:
                continue  # itinerariu direct, deja procesat in pasul 1
            arr_b_min = _time_to_minutes(stop_b["arrival_time"])
            if arr_b_min is None:
                continue
            window_min = arr_b_min + MIN_CONNECTION_MIN
            window_max = arr_b_min + MAX_CONNECTION_MIN

            # Caut tren din B spre C in fereastra
            trains_leg2 = _trains_passing_station(
                db, stop_b["station_id"], travel_date, window_min, _cache=cache,
            )
            for tr2 in trains_leg2:
                dep_b_min = _time_to_minutes(tr2["from_departure"])
                if dep_b_min is None or dep_b_min > window_max:
                    continue
                # Verific daca tr2 ajunge in to_station_id
                stops2 = _stops_on_route_after(db, tr2["route_id"], tr2["from_stop_order"], _cache=cache)
                for stop_c in stops2:
                    if stop_c["station_id"] == to_station_id:
                        leg1 = _make_leg(tr1, from_name, stop_b)
                        leg1["from_station_id"] = from_station_id
                        leg2 = _make_leg(tr2, stop_b["station_name"], stop_c)
                        leg2["from_station_id"] = stop_b["station_id"]
                        # Calcul corect al duratei totale pentru calatorie cu transfer:
                        # = durata_leg1 + asteptare_transfer + durata_leg2
                        # (fiecare durata_leg* deja are fix pentru peste-noapte)
                        wait_transfer = leg2["departure_min"] - leg1["arrival_min"]
                        if wait_transfer < 0:
                            wait_transfer += 1440
                        total_dur = leg1["duration_min"] + wait_transfer + leg2["duration_min"]
                        total_dist = leg1["distance_km"] + leg2["distance_km"]
                        results.append({
                            "legs": [leg1, leg2],
                            "transfer_count": 1,
                            "transfer_stations": [stop_b["station_name"]],
                            "total_duration_min": total_dur,
                            "total_distance_km": round(total_dist, 1),
                            "departure_time": leg1["departure_time"],
                            "arrival_time": leg2["arrival_time"],
                            "departure_min": leg1["departure_min"],
                            "arrival_min": leg2["arrival_min"],
                        })
                        break

    # === Pasul 3: cauta itinerarii cu 2 schimbari (A -> B -> C -> D) ===
    # Cautam doar daca nu am rezultate suficiente cu <= 1 schimbare.
    # Performanta: 2 schimbari are complexitate O(N^3) - limitam la ~500 combinatii.
    if len(results) < top_n:
        # Pentru fiecare combinatie leg1+leg2 deja gasita, incercam un al 3-lea leg.
        # Pentru simplificare: iteram din nou prin tr1 + intermediar B + tr2 + intermediar C + tr3
        intermediates_count = 0
        MAX_INTERMEDIATES = max_intermediates

        for tr1 in trains_leg1[:30]:  # limitam top 30 trenuri leg1
            if intermediates_count >= MAX_INTERMEDIATES:
                break
            stops1 = _stops_on_route_after(db, tr1["route_id"], tr1["from_stop_order"], _cache=cache)
            for stop_b in stops1:
                if stop_b["station_id"] == to_station_id:
                    continue
                arr_b = _time_to_minutes(stop_b["arrival_time"])
                if arr_b is None:
                    continue
                trains_leg2 = _trains_passing_station(
                    db, stop_b["station_id"], travel_date, arr_b + MIN_CONNECTION_MIN, _cache=cache,
                )
                for tr2 in trains_leg2[:5]:  # limitam top 5 trenuri leg2
                    dep_b = _time_to_minutes(tr2["from_departure"])
                    if dep_b is None or dep_b > arr_b + MAX_CONNECTION_MIN:
                        continue
                    stops2 = _stops_on_route_after(db, tr2["route_id"], tr2["from_stop_order"], _cache=cache)
                    for stop_c in stops2:
                        if stop_c["station_id"] == to_station_id:
                            continue  # ar fi direct cu 1 schimbare
                        if stop_c["station_id"] in (from_station_id, stop_b["station_id"]):
                            continue
                        arr_c = _time_to_minutes(stop_c["arrival_time"])
                        if arr_c is None:
                            continue
                        intermediates_count += 1
                        if intermediates_count >= MAX_INTERMEDIATES:
                            break
                        trains_leg3 = _trains_passing_station(
                            db, stop_c["station_id"], travel_date, arr_c + MIN_CONNECTION_MIN, _cache=cache,
                        )
                        for tr3 in trains_leg3[:5]:
                            dep_c = _time_to_minutes(tr3["from_departure"])
                            if dep_c is None or dep_c > arr_c + MAX_CONNECTION_MIN:
                                continue
                            stops3 = _stops_on_route_after(db, tr3["route_id"], tr3["from_stop_order"], _cache=cache)
                            for stop_d in stops3:
                                if stop_d["station_id"] == to_station_id:
                                    leg1 = _make_leg(tr1, from_name, stop_b)
                                    leg1["from_station_id"] = from_station_id
                                    leg2 = _make_leg(tr2, stop_b["station_name"], stop_c)
                                    leg2["from_station_id"] = stop_b["station_id"]
                                    leg3 = _make_leg(tr3, stop_c["station_name"], stop_d)
                                    leg3["from_station_id"] = stop_c["station_id"]
                                    # Suma duratelor leg-urilor + asteptari intre ele
                                    wait12 = leg2["departure_min"] - leg1["arrival_min"]
                                    if wait12 < 0:
                                        wait12 += 1440
                                    wait23 = leg3["departure_min"] - leg2["arrival_min"]
                                    if wait23 < 0:
                                        wait23 += 1440
                                    total_dur = (
                                        leg1["duration_min"] + wait12 +
                                        leg2["duration_min"] + wait23 +
                                        leg3["duration_min"]
                                    )
                                    total_dist = (
                                        leg1["distance_km"] + leg2["distance_km"] + leg3["distance_km"]
                                    )
                                    results.append({
                                        "legs": [leg1, leg2, leg3],
                                        "transfer_count": 2,
                                        "transfer_stations": [
                                            stop_b["station_name"], stop_c["station_name"]
                                        ],
                                        "total_duration_min": total_dur,
                                        "total_distance_km": round(total_dist, 1),
                                        "departure_time": leg1["departure_time"],
                                        "arrival_time": leg3["arrival_time"],
                                        "departure_min": leg1["departure_min"],
                                        "arrival_min": leg3["arrival_min"],
                                    })
                                    break
                    if intermediates_count >= MAX_INTERMEDIATES:
                        break
                if intermediates_count >= MAX_INTERMEDIATES:
                    break

    # === Sortare + top_n ===
    # Criteriu principal: timp total. Tie-breaker: nr transferuri. Ulterior: plecare.
    results.sort(key=lambda r: (
        r["total_duration_min"],
        r["transfer_count"],
        r["departure_min"],
    ))

    # Deduplicare cu key (combinatie de train_id-uri)
    seen_keys = set()
    deduped = []
    for r in results:
        key = tuple(leg["train_id"] for leg in r["legs"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        # Curatim campurile interne
        for leg in r["legs"]:
            leg.pop("arrival_min", None)
            leg.pop("departure_min", None)
        r.pop("departure_min", None)
        r.pop("arrival_min", None)
        deduped.append(r)
        if len(deduped) >= top_n:
            break

    return deduped

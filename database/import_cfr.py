"""
Import oficial CFR — populeaza catalogul de trenuri din XML-urile data.gov.ro.

Sursa: database/external/*.xml (snapshot oficial 2025-2026, licenta CC-BY 4.0)
       Furnizor: S.C. Informatica Feroviara S.A. (filiala CFR S.A.)

Foloseste:
  python database/import_cfr.py             # import complet
  python database/import_cfr.py --quick     # doar top 200 trenuri (CFR Calatori)
  python database/import_cfr.py --reset     # sterge si recreeaza datele de transport

Idempotent: poate fi rulat de oricate ori, foloseste ON CONFLICT.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

# Asigur ca putem importa app.* din backend
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

import psycopg


# ============================================================================
# Configuratie
# ============================================================================
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://railway:railway_dev@localhost:5432/railway_db",
).replace("postgresql+psycopg://", "postgresql://")

EXT_DIR = REPO / "database" / "external"

# Operatorii reali (cod intern XML -> nume + cod scurt)
OPERATORS = {
    # Fisierele XML disponibile -> operator
    "cfr_sntfc.xml":   ("SNTFC CFR Calatori S.A.", "CFR-C", "office@cfrcalatori.ro"),
    "regio.xml":       ("Regio Calatori S.R.L.", "REG-C", "office@regiocalatori.ro"),
    "tfc.xml":         ("Transferoviar Calatori S.R.L.", "TFC", "office@transferoviar.ro"),
    "interregional.xml": ("Interregional Calatori S.R.L.", "IRC", "office@interregional.ro"),
    "astra.xml":       ("Astra Trans Carpatic S.R.L.", "ATC", "office@astratranscarpatic.ro"),
    "softrans.xml":    ("Softrans S.R.L.", "SOF", "office@softrans.ro"),
    "ferotrafic.xml":  ("Ferotrafic TFI S.R.L.", "FER", "office@ferotrafic.ro"),
}

# CategorieTren XML -> train_type DB (schema CHECK)
# Schema accepta: regio, interregio, intercity, express, high_speed
CATEGORY_MAP = {
    "R":    "regio",
    "R-E":  "regio",       # Regio Express
    "REG":  "regio",
    "IR":   "interregio",
    "IRE":  "interregio",  # Inter Regio Express
    "IR-N": "interregio",
    "IC":   "intercity",
    "ICE":  "intercity",
    "EC":   "intercity",   # EuroCity
    "EN":   "intercity",   # EuroNight
    "TIS":  "intercity",   # TGV pe ROEC
    "Tj":   "regio",       # Train Joint (regio mostly)
}


def _to_train_type(category: str) -> str:
    if not category:
        return "regio"
    return CATEGORY_MAP.get(category.upper().strip(), "regio")


def _seconds_to_time(secs):
    """Conversie OraP/OraS din XML (secunde de la 00:00) la HH:MM:SS."""
    if secs is None or secs == "":
        return None
    try:
        s = int(secs)
        s = s % 86400  # normalizez pentru trenuri ce traverseaza miezul noptii
        h, rem = divmod(s, 3600)
        m, ss = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{ss:02d}"
    except (ValueError, TypeError):
        return None


def _km_to_decimal(km_str):
    """XML are Km in metri (9455 = 9.455 km)."""
    if not km_str:
        return 0.0
    try:
        return round(int(km_str) / 1000.0, 3)
    except (ValueError, TypeError):
        return 0.0


# ============================================================================
# Parser XML CFR
# ============================================================================
def parse_xml_file(path: Path, max_trains=None):
    """
    Returneaza un dict cu:
      - 'trains': list of (train_number, category, operator_xml_code, stops)
      - 'stations': dict {code: name}
    Unde 'stops' este list of dicts cu cheile:
      seq, dep_code, dep_name, arr_code, arr_name, km_segment, ora_p, ora_s, tip_oprire
    """
    print(f"  parsing {path.name} ({path.stat().st_size // 1024} KB)...")
    tree = ET.parse(path)
    root = tree.getroot()

    trains_data = []
    stations = {}  # cod -> nume

    trenuri = root.findall(".//Tren")
    if max_trains:
        trenuri = trenuri[:max_trains]

    for tren in trenuri:
        nr = (tren.attrib.get("Numar") or "").strip()
        cat = (tren.attrib.get("CategorieTren") or "R").strip()
        operator_xml = (tren.attrib.get("Operator") or "").strip()
        if not nr:
            continue

        # Elementele trasei = succesiunea de segmente intre statii
        elements = tren.findall(".//ElementTrasa")
        if not elements:
            continue

        stops = []
        for el in elements:
            a = el.attrib
            dep_code = (a.get("CodStaOrigine") or "").strip()
            dep_name = (a.get("DenStaOrigine") or "").strip()
            arr_code = (a.get("CodStaDest") or "").strip()
            arr_name = (a.get("DenStaDestinatie") or "").strip()
            km_segment = _km_to_decimal(a.get("Km"))
            ora_p = _seconds_to_time(a.get("OraP"))
            ora_s = _seconds_to_time(a.get("OraS"))
            tip_oprire = (a.get("TipOprire") or "").strip()  # 'C' = comerciala, 'N' = tehnic
            seq = int(a.get("Secventa", 0))

            if dep_code:
                stations[dep_code] = dep_name
            if arr_code:
                stations[arr_code] = arr_name

            stops.append({
                "seq": seq,
                "dep_code": dep_code, "dep_name": dep_name,
                "arr_code": arr_code, "arr_name": arr_name,
                "km_segment": km_segment,
                "ora_p": ora_p, "ora_s": ora_s,
                "tip_oprire": tip_oprire,
            })

        if not stops:
            continue

        trains_data.append({
            "number": nr,
            "category": cat,
            "operator_xml": operator_xml,
            "stops": stops,
        })

    print(f"    -> {len(trains_data)} trenuri, {len(stations)} statii unice")
    return {"trains": trains_data, "stations": stations}


# ============================================================================
# Import in BD
# ============================================================================
def import_to_db(all_data: dict[str, dict], reset: bool = False):
    """
    Importa datele agregate de la toate operatorii in PostgreSQL.

    all_data = {filename: parsed_data}
    """
    conn = psycopg.connect(DATABASE_URL, autocommit=False)
    cur = conn.cursor()

    if reset:
        print("Reset: stergem datele de transport existente (pastram users/universities/issuers)...")
        cur.execute("TRUNCATE TABLE qr_tokens, validations, travel_entitlements, tickets, subscriptions RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE TABLE route_stops, routes, trains RESTART IDENTITY CASCADE")
        cur.execute("DELETE FROM stations WHERE code LIKE 'CFR-%'")
        cur.execute("DELETE FROM railway_operators WHERE code IN ('CFR-C','REG-C','TFC','IRC','ATC','SOF','FER')")
        conn.commit()
        print("Reset done.")

    # ---- 1. Operators ----
    print("\n[1/4] Inserare operators...")
    operator_id_by_filename = {}
    for filename, (name, code, email) in OPERATORS.items():
        if filename not in all_data:
            continue
        cur.execute(
            """
            INSERT INTO railway_operators (name, code, country, contact_email, is_active)
            VALUES (%s, %s, 'Romania', %s, TRUE)
            ON CONFLICT (code) DO UPDATE
              SET name = EXCLUDED.name, contact_email = EXCLUDED.contact_email
            RETURNING operator_id
            """,
            (name, code, email),
        )
        operator_id_by_filename[filename] = cur.fetchone()[0]
        print(f"  {code}: {name}")

    conn.commit()

    # ---- 2. Stations (agregare globala) ----
    print("\n[2/4] Inserare statii unice...")
    global_stations = {}  # xml_code -> name (dedup)
    for parsed in all_data.values():
        for code, name in parsed["stations"].items():
            if code and name:
                global_stations[code] = name

    # Insert in batch
    station_id_by_xml_code = {}
    rows = [(name, f"CFR-{code}", _extract_city(name)) for code, name in global_stations.items()]
    cur.executemany(
        """
        INSERT INTO stations (name, code, city, country, is_active)
        VALUES (%s, %s, %s, 'Romania', TRUE)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
        RETURNING station_id
        """,
        rows,
    )
    # executemany nu returneaza ID-uri; refetch
    cur.execute("SELECT station_id, code FROM stations WHERE code LIKE 'CFR-%'")
    for sid, scode in cur.fetchall():
        xml_code = scode.replace("CFR-", "", 1)
        station_id_by_xml_code[xml_code] = sid
    print(f"  {len(station_id_by_xml_code)} statii inserate/actualizate")

    conn.commit()

    # ---- 3. Trains + Routes + RouteStops ----
    print("\n[3/4] Inserare trenuri + rute + opriri...")
    total_trains = 0
    total_routes = 0
    total_stops = 0

    for filename, parsed in all_data.items():
        operator_id = operator_id_by_filename.get(filename)
        if not operator_id:
            continue

        print(f"  -> {filename}: {len(parsed['trains'])} trenuri")
        for tdata in parsed["trains"]:
            train_number = tdata["number"]
            train_type = _to_train_type(tdata["category"])
            stops = tdata["stops"]

            # Statia origine = dep_code primul element
            # Statia destinatie = arr_code ultimul element
            origin_xml = stops[0]["dep_code"]
            dest_xml = stops[-1]["arr_code"]
            if not origin_xml or not dest_xml:
                continue
            origin_id = station_id_by_xml_code.get(origin_xml)
            dest_id = station_id_by_xml_code.get(dest_xml)
            if not origin_id or not dest_id or origin_id == dest_id:
                continue

            # Distanta totala = suma km_segment
            total_km = round(sum(s["km_segment"] for s in stops), 2)

            # Route name = "<Den origine> -> <Den destinatie>"
            route_name = f"{stops[0]['dep_name']} -> {stops[-1]['arr_name']}"
            # Route code = unic per (operator, train_number) — folosesc compus
            route_code = f"{OPERATORS[filename][1]}-T{train_number}"

            cur.execute(
                """
                INSERT INTO routes (operator_id, route_name, route_code,
                                    origin_station_id, destination_station_id,
                                    total_distance_km, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (route_code) DO UPDATE SET
                  route_name = EXCLUDED.route_name,
                  total_distance_km = EXCLUDED.total_distance_km
                RETURNING route_id
                """,
                (operator_id, route_name, route_code, origin_id, dest_id, total_km),
            )
            route_id = cur.fetchone()[0]
            total_routes += 1

            # Train (UNIQUE pe operator + train_number)
            cur.execute(
                """
                INSERT INTO trains (operator_id, route_id, train_number, train_type, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (operator_id, train_number) DO UPDATE SET
                  route_id = EXCLUDED.route_id,
                  train_type = EXCLUDED.train_type
                RETURNING train_id
                """,
                (operator_id, route_id, train_number, train_type),
            )
            train_id = cur.fetchone()[0]
            total_trains += 1

            # Route stops
            # Sterg vechile stops pentru aceasta ruta (idempotent)
            cur.execute("DELETE FROM route_stops WHERE route_id = %s", (route_id,))

            # Insert toate statiile pe ruta (origine + destinatii din elemente)
            cum_km = 0.0
            stops_to_insert = []
            # Adaug originea ca primul stop
            stops_to_insert.append({
                "station_id": origin_id,
                "stop_order": 1,
                "distance_from_origin_km": 0.0,
                "arrival_time": None,
                "departure_time": stops[0]["ora_p"],
            })
            # Apoi pentru fiecare element, statia de destinatie devine urmatorul stop
            for i, el in enumerate(stops):
                cum_km += el["km_segment"]
                arr_id = station_id_by_xml_code.get(el["arr_code"])
                if not arr_id:
                    continue
                next_dep = None
                if i + 1 < len(stops):
                    next_dep = stops[i + 1]["ora_p"]
                stops_to_insert.append({
                    "station_id": arr_id,
                    "stop_order": i + 2,
                    "distance_from_origin_km": round(cum_km, 2),
                    "arrival_time": el["ora_s"],
                    "departure_time": next_dep,
                })

            try:
                cur.executemany(
                    """
                    INSERT INTO route_stops (route_id, station_id, stop_order,
                                             distance_from_origin_km, arrival_time, departure_time)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [(route_id, s["station_id"], s["stop_order"],
                      s["distance_from_origin_km"], s["arrival_time"], s["departure_time"])
                     for s in stops_to_insert],
                )
                total_stops += len(stops_to_insert)
            except psycopg.errors.UniqueViolation:
                # Aceeasi statie apare de mai multe ori in ruta (caz rar, dar exista)
                conn.rollback()
                # Skip silentios — pastram doar prima aparitie a fiecarei statii pe ruta
                seen = set()
                dedup = []
                for s in stops_to_insert:
                    key = (s["station_id"],)
                    if key not in seen:
                        seen.add(key)
                        s["stop_order"] = len(dedup) + 1
                        dedup.append(s)
                cur.executemany(
                    """
                    INSERT INTO route_stops (route_id, station_id, stop_order,
                                             distance_from_origin_km, arrival_time, departure_time)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [(route_id, s["station_id"], s["stop_order"],
                      s["distance_from_origin_km"], s["arrival_time"], s["departure_time"])
                     for s in dedup],
                )
                total_stops += len(dedup)

        conn.commit()

    # ---- 4. Summary ----
    print(f"\n[4/4] DONE.")
    print(f"  Trenuri inserate:  {total_trains}")
    print(f"  Rute inserate:     {total_routes}")
    print(f"  Opriri inserate:   {total_stops}")
    print(f"  Statii in catalog: {len(station_id_by_xml_code)}")

    cur.close()
    conn.close()


def _extract_city(station_name: str) -> str:
    """Extrage orasul din numele statiei (e.g., 'Bucuresti Nord Gr.A' -> 'Bucuresti')."""
    if not station_name:
        return "Romania"
    # Heuristica simpla: primul cuvant care nu e ['Gara', 'Halta']
    parts = station_name.split()
    for p in parts:
        if p.lower() not in ("gara", "halta", "h.", "g.", "h", "g"):
            return p[:100]
    return parts[0][:100] if parts else "Romania"


# ============================================================================
# Main
# ============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Doar top 200 trenuri CFR Calatori")
    ap.add_argument("--reset", action="store_true", help="Sterge datele de transport inainte de import")
    ap.add_argument("--only", help="Importa doar un fisier (ex. cfr_sntfc.xml)")
    args = ap.parse_args()

    print(f"=== Import CFR — sursa: {EXT_DIR} ===")
    print(f"DATABASE_URL: {DATABASE_URL[:50]}...\n")

    files_to_import = list(OPERATORS.keys())
    if args.only:
        files_to_import = [args.only]
    elif args.quick:
        files_to_import = ["cfr_sntfc.xml"]

    all_data = {}
    max_trains = 200 if args.quick else None

    for filename in files_to_import:
        path = EXT_DIR / filename
        if not path.exists():
            print(f"  SKIP {filename} (file not found)")
            continue
        all_data[filename] = parse_xml_file(path, max_trains=max_trains)

    if not all_data:
        print("Nimic de importat.")
        return

    import_to_db(all_data, reset=args.reset)
    print("\n=== Import complet ===")


if __name__ == "__main__":
    main()

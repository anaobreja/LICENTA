# -*- coding: utf-8 -*-
import psycopg, re

conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()

# ── Pasul 1: Redenumesc Bucuresti Nord Gr.A → Bucuresti Nord ──────────────────
BUC_GRA = 5721
BUC_GRB = 6355

cur.execute("UPDATE stations SET name = 'Bucureşti Nord' WHERE station_id = %s", (BUC_GRA,))
print(f"Redenumit Gr.A → Bucuresti Nord (id={BUC_GRA})")

# ── Pasul 2: Remapez Gr.B → Gr.A (acum Bucuresti Nord) ───────────────────────
cur.execute("UPDATE route_stops SET station_id = %s WHERE station_id = %s", (BUC_GRA, BUC_GRB))
print(f"Route_stops Gr.B remapate: {cur.rowcount}")

cur.execute("UPDATE routes SET origin_station_id = %s WHERE origin_station_id = %s", (BUC_GRA, BUC_GRB))
print(f"Routes origin Gr.B remapate: {cur.rowcount}")

cur.execute("UPDATE routes SET destination_station_id = %s WHERE destination_station_id = %s", (BUC_GRA, BUC_GRB))
print(f"Routes dest Gr.B remapate: {cur.rowcount}")

cur.execute("UPDATE tickets SET departure_station_id = %s WHERE departure_station_id = %s", (BUC_GRA, BUC_GRB))
cur.execute("UPDATE tickets SET arrival_station_id = %s WHERE arrival_station_id = %s", (BUC_GRA, BUC_GRB))

# Sterg Gr.B
cur.execute("DELETE FROM route_stops WHERE station_id = %s", (BUC_GRB,))
cur.execute("DELETE FROM stations WHERE station_id = %s", (BUC_GRB,))
print(f"Sters Gr.B (id={BUC_GRB})")

# ── Pasul 3: Identific toate statiile tehnice ramase ─────────────────────────
TECHNICAL = [
    r'\bRam\b',
    r'\bTriaj\b',
    r'\bP\.M\b',
    r'\bP\.Mac\b',
    r'\bGr\.[A-Z]\b',
    r'\bKm\.\s*\d',
    r'\bTunel\b',
]
compiled = [re.compile(p, re.IGNORECASE) for p in TECHNICAL]

cur.execute("SELECT station_id, name FROM stations ORDER BY name")
rows = cur.fetchall()

to_delete = []
for sid, name in rows:
    for pat in compiled:
        if pat.search(name):
            to_delete.append((sid, name))
            break

ids = [sid for sid, _ in to_delete]
print(f"\nStatii tehnice ramase de sters: {len(to_delete)}")
for sid, name in to_delete:
    print(f"  [{sid}] {name}")

# Verific ca niciuna nu mai e in routes ca origin/dest
cur.execute("""
    SELECT COUNT(*) FROM routes
    WHERE origin_station_id = ANY(%s) OR destination_station_id = ANY(%s)
""", (ids, ids))
remaining_in_routes = cur.fetchone()[0]
print(f"\nStatii tehnice inca in routes: {remaining_in_routes}")
if remaining_in_routes > 0:
    print("ATENTIE: exista inca statii tehnice referentiate in routes!")
    conn.rollback()
    conn.close()
    exit(1)

# ── Pasul 4: Sterge route_stops si statii tehnice ────────────────────────────
cur.execute("DELETE FROM route_stops WHERE station_id = ANY(%s)", (ids,))
print(f"\nRoute_stops sterse: {cur.rowcount}")

# Curata tickets care pointeaza la statii tehnice
cur.execute("UPDATE tickets SET departure_station_id = NULL WHERE departure_station_id = ANY(%s)", (ids,))
cur.execute("UPDATE tickets SET arrival_station_id = NULL WHERE arrival_station_id = ANY(%s)", (ids,))

cur.execute("DELETE FROM stations WHERE station_id = ANY(%s)", (ids,))
print(f"Statii sterse: {cur.rowcount}")

# ── Raport final ──────────────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM stations")
total = cur.fetchone()[0]
print(f"\nTotal statii ramase: {total}")

conn.commit()
conn.close()
print("Gata.")

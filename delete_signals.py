# -*- coding: utf-8 -*-
import psycopg, re

conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()

# Gaseste statii cu "Semnal" in nume
cur.execute("SELECT station_id, name FROM stations WHERE name ILIKE '%semnal%' ORDER BY name")
signals = cur.fetchall()
print(f"Statii semnal gasite: {len(signals)}")
for sid, name in signals:
    print(f"  [{sid}] {name}")

ids = [sid for sid, _ in signals]
if not ids:
    print("Nimic de sters.")
    conn.close()
    exit(0)

# Verifica FK in routes
cur.execute("""
    SELECT COUNT(*) FROM routes
    WHERE origin_station_id = ANY(%s) OR destination_station_id = ANY(%s)
""", (ids, ids))
in_routes = cur.fetchone()[0]
print(f"\nSemnal statii in routes ca origin/dest: {in_routes}")

# Sterge route_stops
cur.execute("DELETE FROM route_stops WHERE station_id = ANY(%s)", (ids,))
print(f"Route_stops sterse: {cur.rowcount}")

# Sterge statii
cur.execute("DELETE FROM stations WHERE station_id = ANY(%s)", (ids,))
print(f"Statii sterse: {cur.rowcount}")

cur.execute("SELECT COUNT(*) FROM stations")
print(f"Total statii ramase: {cur.fetchone()[0]}")

conn.commit()
conn.close()
print("Gata.")

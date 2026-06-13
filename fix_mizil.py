# -*- coding: utf-8 -*-
import requests, psycopg

# Overpass cu GET in loc de POST
query = '[out:json][timeout:30];(node["railway"~"station|halt"]["name"~"Mizil"](44.9,26.3,45.1,26.6););out center;'
try:
    resp = requests.get(
        "https://overpass-api.de/api/interpreter",
        params={"data": query},
        headers={"Accept": "application/json"},
        timeout=40
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Elemente OSM: {len(data.get('elements', []))}")
    for el in data.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        name = el.get("tags", {}).get("name", "?")
        railway = el.get("tags", {}).get("railway", "?")
        print(f"  [{railway}] {name}: lat={lat}, lon={lon}")
except Exception as e:
    print(f"Overpass error: {e}")

conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()
cur.execute("SELECT station_id, name, latitude, longitude, gps_source FROM stations WHERE name ILIKE '%Mizil%'")
for r in cur.fetchall():
    print(f"\nDB: [{r[0]}] {r[1]} -> lat={r[2]}, lon={r[3]} (sursa: {r[4]})")
conn.close()

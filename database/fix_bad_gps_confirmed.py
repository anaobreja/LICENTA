"""
Sterge GPS-ul DOAR pentru statiile confirmate ca outlier pe >= 100 de rute.
Aceasta lista a fost verificata manual din output-ul check_route_gps.py.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg

DB_URL = "postgresql://railway:railway_dev@localhost:5432/railway_db"

# Statii confirmate cu GPS gresit (geocodate in locul greșit de algoritmul automat)
# Verificate prin check_route_gps.py: salt > 60km confirmat pe > 100 rute
CONFIRMED_BAD = [
    (980,  "Mera Hm."),
    (886,  "Grozavesti Hm."),
    (305,  "Sacuieni Roman Hm."),
    (1712, "Roscani h."),
    (497,  "Balteni Hm."),
    (705,  "Sibiu Triaj"),
    (310,  "Pascani Gr. Triaj"),
    (279,  "Inotesti Hm."),
]

conn = psycopg.connect(DB_URL)
cur = conn.cursor()

for sid, name in CONFIRMED_BAD:
    cur.execute("SELECT name, latitude, longitude FROM stations WHERE station_id = %s", (sid,))
    row = cur.fetchone()
    if row:
        print(f"  Sterg GPS pentru {row[0]}: {row[1]}, {row[2]}")

cur.execute(
    "UPDATE stations SET latitude=NULL, longitude=NULL WHERE station_id = ANY(%s)",
    ([s[0] for s in CONFIRMED_BAD],)
)
conn.commit()
print(f"\n✓ GPS sters pentru {cur.rowcount} statii greșit geocodificate")
conn.close()

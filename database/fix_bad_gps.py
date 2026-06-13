"""
Detecteaza si sterge coordonatele GPS gresite din tabelul stations.
Logica: parcurge fiecare ruta, calculeaza saltul km intre statii consecutive cu GPS.
Daca un salt depaseste MAX_JUMP_KM (60km) si statia respectiva apare ca outlier
pe mai multe rute, ii seteaza GPS la NULL.
"""
import sys, math
sys.stdout.reconfigure(encoding='utf-8')
import psycopg

DB_URL = "postgresql://railway:railway_dev@localhost:5432/railway_db"
MAX_JUMP_KM = 60  # salt maxim realist intre statii consecutive CFR

def dist_km(a, b):
    R = 6371
    la1, lo1, la2, lo2 = float(a[0]), float(a[1]), float(b[0]), float(b[1])
    dlat = (la2-la1) * math.pi/180
    dlon = (lo2-lo1) * math.pi/180
    x = math.sin(dlat/2)**2 + math.cos(la1*math.pi/180)*math.cos(la2*math.pi/180)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))

conn = psycopg.connect(DB_URL)
cur = conn.cursor()

# Incarca toate rutele cu statiile lor in ordine
cur.execute("""
    SELECT rs.route_id, rs.stop_order, s.station_id, s.name, s.latitude, s.longitude
    FROM route_stops rs
    JOIN stations s ON s.station_id = rs.station_id
    WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL
    ORDER BY rs.route_id, rs.stop_order
""")
rows = cur.fetchall()

# Grupeaza pe route_id
from collections import defaultdict
routes = defaultdict(list)
for route_id, order, sid, name, lat, lon in rows:
    routes[route_id].append((order, sid, name, float(lat), float(lon)))

# Numara de cate ori fiecare statie e "outlier" (salt mare fata de precedenta SAU urmatoarea)
suspect_count = defaultdict(int)
suspect_names = {}

for route_id, stops in routes.items():
    for i in range(1, len(stops)):
        prev = stops[i-1]
        curr = stops[i]
        d = dist_km((prev[3], prev[4]), (curr[3], curr[4]))
        if d > MAX_JUMP_KM:
            # Marcheaza statia curenta ca suspect
            suspect_count[curr[1]] += 1
            suspect_names[curr[1]] = curr[2]
            # Verifica si daca urmatoarea statie e la distanta normala de precedenta
            # (confirma ca statia curenta e problema, nu cea precedenta)
            if i + 1 < len(stops):
                nxt = stops[i+1]
                d_skip = dist_km((prev[3], prev[4]), (nxt[3], nxt[4]))
                if d_skip <= MAX_JUMP_KM:
                    suspect_count[curr[1]] += 2  # confirmat outlier

# Afiseaza suspectii
print(f"Statii cu GPS suspect (apar ca outlier pe rute):")
print(f"{'ID':>6}  {'Aparitii':>8}  Nume")
print("-"*60)
to_fix = []
for sid, count in sorted(suspect_count.items(), key=lambda x: -x[1]):
    if count >= 1:
        print(f"{sid:>6}  {count:>8}  {suspect_names[sid]}")
        to_fix.append(sid)

print(f"\nTotal: {len(to_fix)} statii de corectat")

if to_fix:
    confirm = input("\nStergi GPS-ul pentru aceste statii? (da/nu): ").strip().lower()
    if confirm == 'da':
        cur.execute(
            "UPDATE stations SET latitude=NULL, longitude=NULL WHERE station_id = ANY(%s)",
            (to_fix,)
        )
        conn.commit()
        print(f"✓ GPS sters pentru {cur.rowcount} statii")
    else:
        print("Anulat.")
else:
    print("Nicio statie suspecta gasita.")

conn.close()

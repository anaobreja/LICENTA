"""Sterge GPS-ul greșit pentru stațiile Buzău geocodificate în locuri greșite."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg

DB_URL = "postgresql://railway:railway_dev@localhost:5432/railway_db"

# Buzau Ram. Gr. A (283): 45.0533, 26.8250 - 10km sud de Buzau, gresit
# Buzau Nord Hm. (1739) si Buzau Sud (1012): ambele la 45.1213, 26.8687 - una e gresita
# Stergem ambele duplicate, lasam doar Buzau principal (284) cu GPS corect
TO_NULL = [
    (283, "Buzău Ram. Gr. A"),
    (1739, "Buzău Nord Hm."),
    (1012, "Buzău Sud"),
]

conn = psycopg.connect(DB_URL)
cur = conn.cursor()

for sid, name in TO_NULL:
    cur.execute("SELECT station_id, name, latitude, longitude FROM stations WHERE station_id = %s", (sid,))
    row = cur.fetchone()
    if row and row[2]:
        print(f"  Sterg GPS pentru {row[1]}: {row[2]:.4f}, {row[3]:.4f}")
    elif row:
        print(f"  {row[1]}: deja fara GPS")

cur.execute(
    "UPDATE stations SET latitude=NULL, longitude=NULL WHERE station_id = ANY(%s)",
    ([s[0] for s in TO_NULL],)
)
conn.commit()
print(f"\n✓ GPS sters pentru {cur.rowcount} statii Buzău greșit geocodificate")
conn.close()

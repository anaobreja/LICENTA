"""Sterge GPS-ul pentru Ulmeni Hm. (station_id=282), geocodata gresit."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg

DB_URL = "postgresql://railway:railway_dev@localhost:5432/railway_db"

conn = psycopg.connect(DB_URL)
cur = conn.cursor()

cur.execute("SELECT station_id, name, latitude, longitude FROM stations WHERE station_id = 282")
row = cur.fetchone()
print(f"Inainte: {row[1]} -> {row[2]}, {row[3]}")

cur.execute("UPDATE stations SET latitude=NULL, longitude=NULL WHERE station_id = 282")
conn.commit()
print(f"GPS sters pentru Ulmeni Hm. (station_id=282)")

conn.close()

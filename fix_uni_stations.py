import psycopg, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()

BUC_NORD = 5721  # Bucureşti Nord - 762 rute, cea mai mare statie din Bucuresti

# Seteaza main_station_id pentru toate universitatile din Bucuresti
cur.execute("""
    UPDATE universities
    SET main_station_id = %s
    WHERE main_station_id IS NULL AND city ILIKE %s
    RETURNING university_id, name
""", (BUC_NORD, "%Bucuresti%"))
updated = cur.fetchall()
print("Universitati actualizate:")
for r in updated:
    print(" ", r[0], r[1])

# Verifica userul cu home_station_id setat (userFl din screenshot)
cur.execute("""
    SELECT u.user_id, u.email, u.university_id, un.name AS uni_name,
           u.home_station_id, hs.name AS home_station,
           un.main_station_id, ms.name AS uni_station
    FROM users u
    LEFT JOIN universities un ON un.university_id = u.university_id
    LEFT JOIN stations hs ON hs.station_id = u.home_station_id
    LEFT JOIN stations ms ON ms.station_id = un.main_station_id
    WHERE u.home_station_id IS NOT NULL
""")
print("\nUseri cu home_station:")
for r in cur.fetchall():
    print(f"  user_id={r[0]} {r[1]}")
    print(f"    home_station: {r[5]} (id={r[4]})")
    print(f"    universitate: {r[3]} -> statie: {r[7]} (id={r[6]})")

conn.commit()
conn.close()
print("\nDone.")

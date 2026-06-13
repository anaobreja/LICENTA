import psycopg
conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()
for tbl in ["ticket_seats", "seat_reservations", "train_cars", "seats"]:
    cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (tbl,))
    print(f"\n{tbl}:")
    for r in cur.fetchall():
        print(f"  {r[0]:35s} {r[1]:20s} nullable={r[2]}")
conn.close()

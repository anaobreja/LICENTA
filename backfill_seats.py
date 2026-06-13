import psycopg
conn = psycopg.connect(host="localhost", port=5432, dbname="railway_db", user="railway", password="railway_dev")
cur = conn.cursor()

sql = """
DO $$
DECLARE
    r RECORD;
    n INT;
    total_trains INT := 0;
    total_seats INT := 0;
BEGIN
    FOR r IN SELECT train_id FROM trains LOOP
        n := generate_train_layout(r.train_id);
        IF n > 0 THEN
            total_trains := total_trains + 1;
            total_seats := total_seats + n;
        END IF;
    END LOOP;
    RAISE NOTICE 'Backfill: generated layout for % trains, % seats total', total_trains, total_seats;
END $$;
"""

cur.execute(sql)
conn.commit()

cur.execute("SELECT COUNT(*) FROM train_cars")
print("train_cars:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM seats")
print("seats:", cur.fetchone()[0])

# Verifica trenul 11533
cur.execute("SELECT train_id FROM trains WHERE train_number = %s", ("11533",))
row = cur.fetchone()
if row:
    tid = row[0]
    cur.execute("SELECT car_number, car_class, total_seats FROM train_cars WHERE train_id = %s ORDER BY car_number", (tid,))
    print("Vagoane IR 11533:", cur.fetchall())

conn.close()
